#!/usr/bin/env python3
"""Read frames out of the outbox the kernel already writes them into.

The carrier was half-built and the two halves pointed at different
filesystems:

* `kernel.persist_outbox(root, frame)` writes to
  `root/resident-runtime/federation/outbox/<sha256(packet_id)>.json` -- inside
  the repository, which is exactly where a frame has to be for git to carry it.
* `kernel.scan_addressed_frames(organization)` reads
  `federation_root()/frames.d`, which defaults to
  `~/.local/state/stegverse/org-federation/frames.d` -- outside any repository,
  local to one machine, gone when that machine is.

So a frame written by the write side could never be found by the read side, and
`resident-runtime/federation/outbox` has never been committed in this
repository at all. Nothing was broken in either function; they were simply
never pointed at the same place, and every surface downstream -- the standing
gate, the manifest selector, the receipt chain -- is only reachable after a
frame arrives.

This is the read side against the path the write side already uses. A peer's
frames arrive because a peer's repository is checked out: git is the carrier,
the commit is the transfer, and the outbox is the drop point that
`persist_outbox` has always named. No new convention is introduced here, and
the published path is not renamed -- `OUTBOX` is read off the kernel's own
behavior rather than redeclared, so the two cannot drift apart again.

`CANONICAL-NODE-INGRESS-CONTRACT-001` requires this shape:

    no_new_endpoint_required: true
    no_new_host_required: true

A repository checkout is not a host and a committed directory is not an
endpoint. There is no network client in this module and no service to stand up.

A frame found in a peer's checkout is untrusted bytes. `kernel.ingest_frame`
recomputes the frame digest, the packet digest and the heartbeat reference, and
the standing gate runs inside `dispatch`, before anything is consumed. Being
readable is not being admitted.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]

#: The path `kernel.persist_outbox` writes into. Named here once so the read
#: side cannot be pointed somewhere the write side does not use -- the defect
#: this module exists to close.
OUTBOX = "resident-runtime/federation/outbox"

#: Transport, not authority. Stated because a carrier is the surface most
#: likely to be mistaken for one.
CARRIER_AUTHORITY_EFFECT = "NONE_TRANSPORT_ONLY"


class GitCarrierError(RuntimeError):
    """A carrier failure. Never an admission decision -- that is the kernel's."""


def _kernel(root: Path | None = None):
    path = (root or ROOT) / "org-kernel/kernel.py"
    if not path.is_file():
        raise GitCarrierError("checkout-carries-no-kernel:" + str(path))
    spec = importlib.util.spec_from_file_location("carried_kernel", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def outbox_dir(root: Path | None = None) -> Path:
    return (root or ROOT) / OUTBOX


def frame_filename(packet_id: str) -> str:
    """Name a frame the way `persist_outbox` names it, not a second way."""
    return hashlib.sha256(packet_id.encode()).hexdigest() + ".json"


def published(root: Path | None = None) -> list[dict[str, Any]]:
    """Every frame a checkout has in its own outbox.

    A missing outbox is an empty one: a repository that has published nothing
    is not malformed. A frame that will not parse is a carrier failure and is
    raised rather than skipped -- quietly dropping it would make an
    unreadable frame indistinguishable from an absent one.
    """
    directory = outbox_dir(root)
    if not directory.is_dir():
        return []
    frames = []
    for path in sorted(directory.glob("*.json")):
        try:
            frame = json.loads(path.read_text())
        except json.JSONDecodeError:
            raise GitCarrierError("outbox-frame-not-json:" + str(path)) from None
        if not isinstance(frame, dict):
            raise GitCarrierError("outbox-frame-not-an-object:" + str(path))
        frames.append(frame)
    return frames


def addressed_to(organization: str, *, peer_root: Path) -> list[dict[str, Any]]:
    """The frames in a peer's checkout that name this organization.

    Filtered on the frame's own `destination_org`, which `recover_packet`
    later holds against the packet it carries -- so a frame cannot be
    addressed to us in its envelope and to someone else in its payload.
    """
    return [f for f in published(peer_root) if f.get("destination_org") == organization]


def peer_repository(organization: str, *, root: Path | None = None) -> str:
    """Resolve a peer's repository from the federation directory, not a caller.

    The rule `organization_egress_boundary.resolve_destination` already holds:
    the directory is the authority on who this organization's peers are. A
    repository taken from an argument alone would let a caller point ingress at
    a checkout of its own choosing.
    """
    path = (root or ROOT) / "org-boundary/registry/federation.json"
    directory = json.loads(path.read_text())
    for row in directory.get("organizations", []):
        if row.get("organization") == organization:
            repository = row.get("repository")
            if not repository:
                raise GitCarrierError("peer-declares-no-repository:" + organization)
            return str(repository)
    raise GitCarrierError("not-a-declared-peer:" + organization)


def verify_peer_checkout(organization: str, peer_root: Path, *, root: Path | None = None) -> str:
    """Refuse a checkout that is not the repository the directory names.

    Without this the carrier would accept any directory handed to it, which is
    the `CALLER_EDITABLE_CLASSIFICATION_DOES_NOT_ESTABLISH_IDENTITY` problem
    moved from the packet to the filesystem. The checkout's own registry has to
    agree that it belongs to the organization whose frames we are about to read.
    """
    declared = peer_repository(organization, root=root)
    registry = peer_root / "org-boundary/registry/services.json"
    if not registry.is_file():
        raise GitCarrierError("peer-checkout-carries-no-registry:" + str(peer_root))
    organization_in_checkout = json.loads(registry.read_text()).get("organization")
    if organization_in_checkout != organization:
        raise GitCarrierError(
            "peer-checkout-declares-a-different-organization:"
            + str(organization_in_checkout) + "!=" + organization)
    return declared


def consume(frame: dict[str, Any], *, root: Path | None = None,
            persist_egress: bool = True) -> dict[str, Any]:
    """Ingest one carried frame, and put the egress frame in our own outbox.

    The egress frame goes where `persist_outbox` puts it, so the response is
    carried back by the same mechanism that brought the request: the peer reads
    it out of this repository the way we read theirs.
    """
    base = root or ROOT
    kernel = _kernel(base)
    result = kernel.ingest_frame(base, frame)
    if result.get("status") != "CONSUMED" or not persist_egress:
        return {**result, "egress_persisted": None}

    spec = importlib.util.spec_from_file_location(
        "intr_transport", base / "org-boundary/runtime/intr_transport.py")
    transport = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(transport)

    egress = transport.build_egress(result["packet"], result["execution_result"])
    path = kernel.persist_outbox(base, kernel.carrier_frame(egress))
    return {**result, "egress_persisted": str(path), "egress_packet_id": egress["packet_id"]}


def cross(organization: str, *, peer_root: Path, root: Path | None = None) -> dict[str, Any]:
    """Read what a peer addressed to us out of their checkout, and answer it."""
    base = root or ROOT
    kernel = _kernel(base)
    us = kernel.load_registry(base)["organization"]
    repository = verify_peer_checkout(organization, peer_root, root=base)
    frames = addressed_to(us, peer_root=peer_root)
    results = []
    for frame in frames:
        # Per frame, because a refusal is this frame's outcome and not the
        # batch's. Letting it propagate meant one malformed or standing-less
        # frame in a peer's outbox blocked every good frame behind it -- a
        # carrier that stops carrying because one artifact was bad.
        try:
            results.append(consume(frame, root=base))
        except (GitCarrierError, ValueError) as refused:
            results.append({"status": "REFUSED", "packet_id": frame.get("packet_id"),
                            "refused": str(refused), "egress_persisted": None})
    return {
        "schema_version": "stegverse.org-git-carrier-crossing.v1",
        "organization": us,
        "peer": organization,
        "peer_repository": repository,
        "peer_checkout": str(peer_root),
        "carrier": "GIT_REPOSITORY_CHECKOUT",
        "frames_addressed_to_us": len(frames),
        "consumed": [r for r in results if r.get("status") == "CONSUMED"],
        "refused": [r for r in results if r.get("status") == "REFUSED"],
        "not_consumed": [r for r in results if r.get("status") not in {"CONSUMED", "REFUSED"}],
        "authority_effect": CARRIER_AUTHORITY_EFFECT,
        # Said plainly: carrying a frame is not proving who wrote it.
        "peer_authorship_established_here": False,
    }


def emit(*, destination_org: str, destination_service: str, payload: dict[str, Any],
         standing: dict[str, Any], root: Path | None = None,
         packet_id: str | None = None) -> dict[str, Any]:
    """Build a packet for a peer and put its frame in our outbox for them to read.

    `standing` is required and has no default, the rule `kernel.build_packet`
    holds: a caller states its chain position or it does not get a packet. The
    carrier adds no exemption -- where a frame is written is not a way around
    declaring one.
    """
    base = root or ROOT
    kernel = _kernel(base)
    registry = kernel.load_registry(base)
    control = next((s["service_id"] for s in registry["services"]
                    if s.get("boundary_role") == "BOUNDARY_LOCAL_CONTROL"), None)
    if control is None:
        raise GitCarrierError("this-organization-declares-no-control-service")
    packet = kernel.build_packet(
        origin_org=registry["organization"], origin_service=control,
        destination_org=destination_org, destination_service=destination_service,
        payload=payload, standing=standing, packet_id=packet_id)
    frame = kernel.carrier_frame(packet)
    path = kernel.persist_outbox(base, frame)
    return {"schema_version": "stegverse.org-git-carrier-emission.v1",
            "packet_id": packet["packet_id"], "destination_org": destination_org,
            "destination_service": destination_service,
            "frame_sha256": frame["frame_sha256"], "persisted": str(path),
            "authority_effect": CARRIER_AUTHORITY_EFFECT}


def _main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(
        prog="git_carrier.py",
        description="Carry frames between organizations in their repositories.")
    parser.add_argument("--root", default=None, help="this organization's checkout")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("published", help="list frames in this checkout's outbox")

    emission = sub.add_parser("emit", help="put a frame for a peer in our outbox")
    emission.add_argument("--peer", required=True)
    emission.add_argument("--service", required=True)
    emission.add_argument("--payload", default="{}")
    emission.add_argument("--node-ref", required=True)
    emission.add_argument("--packet-id", default=None)
    emission.add_argument("--predecessor", default=None,
                          help="JSON predecessor binding; omit for explicit genesis")
    emission.add_argument("--generation", type=int, default=None)
    emission.add_argument("--no-standing", action="store_true",
                          help="emit without declaring standing, to show it is refused")

    crossing = sub.add_parser("cross", help="read a peer's outbox and answer it")
    crossing.add_argument("--peer", required=True)
    crossing.add_argument("--peer-root", required=True, help="the peer's checkout")

    args = parser.parse_args(argv)
    root = Path(args.root).resolve() if args.root else ROOT

    try:
        if args.cmd == "published":
            frames = published(root)
            print(json.dumps(
                {"outbox": OUTBOX, "count": len(frames),
                 "frames": [{"packet_id": f.get("packet_id"),
                             "destination_org": f.get("destination_org"),
                             "frame_sha256": f.get("frame_sha256")} for f in frames]},
                indent=2, sort_keys=True))
            return 0
        if args.cmd == "emit":
            predecessor = json.loads(args.predecessor) if args.predecessor else None
            standing: dict[str, Any] = {
                "mode": "ESTABLISH_GENESIS" if predecessor is None else "VERIFY_EXISTING",
                "node_ref": args.node_ref, "predecessor": predecessor}
            if args.generation is not None:
                standing["generation"] = args.generation
            emitted = emit(destination_org=args.peer, destination_service=args.service,
                           payload=json.loads(args.payload), standing=standing,
                           root=root, packet_id=args.packet_id)
            if args.no_standing:
                # Strip the declaration from the published frame, so the refusal
                # is shown on the carried artifact rather than asserted about it.
                kernel = _kernel(root)
                path = Path(emitted["persisted"])
                frame = json.loads(path.read_text())
                packet = kernel.recover_packet(frame)
                packet.pop("standing", None)
                path.write_text(json.dumps(kernel.carrier_frame(packet),
                                           indent=2, sort_keys=True) + "\n")
                emitted["standing_declared"] = False
            print(json.dumps(emitted, indent=2, sort_keys=True))
            return 0
        print(json.dumps(cross(args.peer, peer_root=Path(args.peer_root).resolve(), root=root),
                         indent=2, sort_keys=True, default=str))
        return 0
    except (GitCarrierError, ValueError) as failure:
        # A carrier failure is an outcome, reported as data rather than a
        # traceback. `ValueError` is caught alongside the carrier's own error
        # because the kernel raises it both for a frame whose digests do not
        # recompute and for a refused standing, and a carried frame failing
        # either check is the most ordinary thing this surface will see.
        print(json.dumps({"schema_version": "stegverse.org-git-carrier-refusal.v1",
                          "refused": str(failure)}, indent=2, sort_keys=True))
        return 1


if __name__ == "__main__":
    raise SystemExit(_main())
