#!/usr/bin/env python3
"""Outbound-only Service Gateway transport for organization federation."""
from __future__ import annotations

from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("org_kernel", ROOT / "org-kernel" / "kernel.py")
K = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(K)

GATEWAY_ENV = "STEGVERSE_ORG_FEDERATION_GATEWAY_URL"
TIMEOUT_ENV = "STEGVERSE_ORG_FEDERATION_GATEWAY_TIMEOUT_SECONDS"


class FederationGatewayTransportError(RuntimeError):
    pass


def gateway_base_url() -> str:
    raw = os.getenv(GATEWAY_ENV, "").strip().rstrip("/")
    if not raw:
        raise FederationGatewayTransportError("organization federation gateway URL not configured")
    if not raw.startswith("https://"):
        raise FederationGatewayTransportError("organization federation gateway must use HTTPS")
    return raw


def timeout_seconds() -> float:
    raw = os.getenv(TIMEOUT_ENV, "10").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise FederationGatewayTransportError("invalid federation gateway timeout") from exc
    if value <= 0 or value > 60:
        raise FederationGatewayTransportError("federation gateway timeout outside bounds")
    return value


def _json_request(method: str, path: str, *, body: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> dict[str, Any]:
    url = gateway_base_url() + path
    raw = None if body is None else json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")
    hdrs = {"Accept": "application/json", **(headers or {})}
    if raw is not None:
        hdrs["Content-Type"] = "application/json"
    req = Request(url, data=raw, headers=hdrs, method=method)
    try:
        with urlopen(req, timeout=timeout_seconds()) as resp:
            payload = resp.read()
    except (HTTPError, URLError, TimeoutError) as exc:
        raise FederationGatewayTransportError(f"gateway request failed: {exc}") from exc
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception as exc:
        raise FederationGatewayTransportError("gateway response is not JSON") from exc


def submit_frame(frame: dict[str, Any]) -> dict[str, Any]:
    validated = K.recover_packet(frame)
    origin_org = validated["origin"]["org"]
    return _json_request(
        "POST",
        "/api/org-federation/v1/frames",
        body=frame,
        headers={"X-StegVerse-Origin-Organization": origin_org},
    )


def fetch_frame(organization: str) -> dict[str, Any]:
    query = urlencode({"organization": organization})
    return _json_request(
        "GET",
        "/api/org-federation/v1/frames?" + query,
        headers={"X-StegVerse-Organization": organization},
    )


def acknowledge_frame(organization: str, frame: dict[str, Any], state: str) -> dict[str, Any]:
    ack = {
        "schema": "stegverse.org-federation-rendezvous.ack/v1",
        "organization": organization,
        "packet_id": frame["packet_id"],
        "frame_sha256": frame["frame_sha256"],
        "state": state,
        "observed_at": datetime.now(timezone.utc).isoformat(),
        # A host clock reading, marked as one rather than read as a heartbeat tick.
        "derived_from_clock": True,
        "gateway_execution_authority": "NONE",
        "authority_effect": "NONE_OBSERVATION_ONLY",
    }
    return _json_request(
        "POST",
        "/api/org-federation/v1/acknowledgements",
        body=ack,
        headers={"X-StegVerse-Organization": organization},
    )


def publish_ecosystem_via_gateway(
    *,
    repo_root: Path,
    standing: dict[str, Any],
    message_class: str,
    subject: str,
    body: dict[str, Any],
    requested_action: str | None = None,
    communication_id: str | None = None,
) -> dict[str, Any]:
    registry = K.load_registry(repo_root)
    directory = K.load_federation_directory(repo_root)
    orgs = [row["organization"] for row in directory["organizations"]]
    built = K.build_ecosystem_packets(
        origin_org=registry["organization"],
        origin_service=K.organization_slug(registry["organization"]) + ".org-control",
        organizations=orgs,
        standing=standing,
        message_class=message_class,
        subject=subject,
        body=body,
        requested_action=requested_action,
        communication_id=communication_id,
    )
    results = []
    for packet in built["packets"]:
        frame = K.carrier_frame(packet)
        stored = submit_frame(frame)
        # Recorded after the gateway accepted the frame, for the same reason the
        # spool lane records after publishing: the record is of an emission.
        # Without it this lane's closure would have nothing to recompute the far
        # side against and would be back to trusting the carried terminal.
        K.persist_outbox(repo_root, frame)
        results.append({
            "organization": packet["destination"]["org"],
            "packet_id": packet["packet_id"],
            "frame_sha256": frame["frame_sha256"],
            "gateway_state": stored.get("state"),
        })
    return {
        "communication_id": built["communication_id"],
        "organization_count": len(results),
        "published_count": sum(1 for row in results if row["gateway_state"] == "PENDING"),
        "gateway_execution_authority": "NONE",
        "organizations": results,
    }


def _persist_response(repo_root: Path, packet: dict[str, Any], execution_result: dict[str, Any]) -> Path:
    payload = packet.get("payload") or {}
    communication_id = str(payload.get("communication_id") or "unknown")
    out = repo_root / "resident-runtime" / "control" / "responses.d"
    out.mkdir(parents=True, exist_ok=True)
    name = K.sha({
        "communication_id": communication_id,
        "packet_id": packet["packet_id"],
        "origin_org": packet["origin"]["org"],
    }).split(":", 1)[1] + ".json"
    record = {
        "schema_version": "stegverse.ecosystem-response-observation.v1",
        "communication_id": communication_id,
        "packet_id": packet["packet_id"],
        "origin_org": packet["origin"]["org"],
        "message_class": payload.get("message_class"),
        "application_result": execution_result.get("application_result"),
        "request_packet_id": (payload.get("body") or {}).get("request_packet_id"),
        # Stored so closure can recompute it. The response's own assertion is
        # what gets checked, so it has to survive to the point of checking.
        "receipt_terminal": (payload.get("body") or {}).get("receipt_terminal"),
        "reconstruction": execution_result.get("reconstruction"),
        "authority_effect": execution_result.get("authority_effect"),
    }
    path = out / name
    if path.exists():
        if json.loads(path.read_text()) != record:
            raise FederationGatewayTransportError("response observation write-once collision")
    else:
        path.write_text(json.dumps(record, indent=2, sort_keys=True) + "\n")
    return path


def resident_gateway_cycle(repo_root: Path, hb_epoch: int | None = None) -> dict[str, Any]:
    registry = K.load_registry(repo_root)
    organization = registry["organization"]
    fetched = fetch_frame(organization)
    if fetched.get("state") == "NO_FRAME":
        return {
            "schema_version": "stegverse.org-federation-gateway-cycle.v1",
            "organization": organization,
            "state": "NO_FRAME",
            "frames_consumed": 0,
            "responses_emitted": 0,
            "gateway_execution_authority": "NONE",
        }
    if fetched.get("state") != "FRAME_AVAILABLE":
        raise FederationGatewayTransportError("unexpected gateway fetch state")
    frame = fetched["frame"]
    packet = K.recover_packet(frame)
    result = K.ingest_frame(repo_root, frame, hb_epoch=hb_epoch)
    epoch = K.frame_supplied_epoch(frame)
    epoch = hb_epoch if epoch is None else epoch
    response_emitted = 0
    response_ref = None
    if result.get("status") == "CONSUMED":
        execution = result["execution_result"]
        message_class = (packet.get("payload") or {}).get("message_class")
        # The map, not a third copy of it. This lane had the same literal set
        # as the spool lane and would answer three of the four classes the map
        # declares answered.
        if message_class in K.RESPONDED_REQUEST_CLASSES:
            response = K.build_control_response(packet, execution)
            response_frame = K.carrier_frame(response, epoch=epoch)
            submit_frame(response_frame)
            response_emitted = 1
            response_ref = response_frame["frame_sha256"]
        elif message_class in K.ACK_CLASSES:
            _persist_response(repo_root, packet, execution)
        ack_state = "CONSUMED"
    else:
        ack_state = "BLOCKED"
    ack = acknowledge_frame(organization, frame, ack_state)
    return {
        "schema_version": "stegverse.org-federation-gateway-cycle.v1",
        "organization": organization,
        "state": ack_state,
        "packet_id": frame["packet_id"],
        "frame_sha256": frame["frame_sha256"],
        "frames_consumed": 1 if ack_state == "CONSUMED" else 0,
        "responses_emitted": response_emitted,
        "response_frame_sha256": response_ref,
        "ack_state": ack.get("state"),
        "gateway_execution_authority": "NONE",
    }


def collect_local_responses(repo_root: Path, communication_id: str) -> dict[str, Any]:
    """Collect gateway-lane responses, recomputing each far-side receipt chain.

    A response observation is checked against this organization's own emission
    record, exactly as the spool lane's collection is: a terminal receipt that
    does not recompute did not come from a boundary that ran the packet, so the
    response is refused rather than counted.
    """
    directory = repo_root / "resident-runtime" / "control" / "responses.d"
    emissions = K.recorded_emissions(repo_root, communication_id)
    rows = []
    if directory.exists():
        for path in sorted(directory.glob("*.json")):
            try:
                value = json.loads(path.read_text())
            except Exception:
                continue
            if value.get("communication_id") == communication_id:
                rows.append(value)
    verified, refused = [], []
    for row in rows:
        org = row.get("origin_org")
        if not org:
            continue
        emission = emissions.get(str(row.get("request_packet_id")))
        if emission is None:
            refused.append({"organization": org,
                            "finding": "THIS_ORGANIZATION_HAS_NO_EMISSION_RECORD_FOR_THIS_PACKET:"
                                       + str(row.get("request_packet_id"))})
            continue
        recomputed = K.far_side_receipt_chain(
            emission["packet_id"], emission["far_side_service_id"],
            emission["far_side_payload_hash"])[-1]
        if row.get("receipt_terminal") != recomputed:
            refused.append({"organization": org,
                            "finding": "FAR_SIDE_TERMINAL_RECEIPT_DOES_NOT_RECOMPUTE:"
                                       + str(row.get("receipt_terminal"))})
            continue
        verified.append(org)
    orgs = sorted(set(verified))
    directory_rows = K.load_federation_directory(repo_root).get("organizations", [])
    return {
        "communication_id": communication_id,
        "response_count": len(orgs),
        "organizations": orgs,
        "refused_count": len(refused),
        "refused": refused,
        "far_side_receipts_recomputed_here": True,
        # Read from the directory rather than hard-coded, so the denominator
        # tracks the peer set instead of drifting from it.
        "complete": bool(directory_rows) and len(orgs) == len(directory_rows),
    }
