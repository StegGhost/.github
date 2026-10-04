#!/usr/bin/env python3
"""Disclose whether this organization's own chain records emitting a packet.

The closure record has carried this, in these words, since the outbound
boundary was built:

    reconstruction_proves_the_boundary_ran_this_packet       true
    reconstruction_proves_who_the_far_side_is                false
    bilateral_match_requires_the_far_side_chain_to_be_readable true

Recomputing a far-side receipt chain proves a boundary ran the packet. It does
not say *whose* boundary, because the inputs are all held by the recomputing
side. What would say whose is the other half: the claimed organization's own
ledger holding an emission receipt for that packet id, addressed to the asker.
A forged origin cannot produce that, because it cannot write the claimed
organization's chain.

Nothing in this ecosystem made a chain readable, so that half existed nowhere
and the field above was true everywhere. This module is this organization's
half: it answers, from its own repository ledger, whether that ledger records
emitting a given packet id, and to whom.

What it discloses is deliberately narrow. A disclosure answers a yes or no
about one packet id the asker already holds, and carries digests and the
destination organization it recorded -- never a payload, never the chain, never
another packet. An asker learns whether its own crossing is corroborated and
nothing else about this organization's traffic.

What a satisfied match proves, and what it still does not:

    the claimed origin's own ledger records emitting this packet to this asker
      -> a forged origin would need that organization's chain to say so

    it does not prove the asker is who it says it is in the other direction,
    and it does not make standing authenticated: a disclosure corroborates one
    crossing against one chain. `origin_attestation_state` is untouched by it.

An unreachable or silent peer is `NOT_AVAILABLE`, never a pass. A peer that
serves no disclosure is indistinguishable from one that would answer no, so
both leave the match unsatisfied and say which case it was.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any, Mapping

DISCLOSURE_SCHEMA = "stegghost.emission-chain-disclosure/v1"
REQUEST_CLASS = "ecosystem.emission.disclosure.request"
RESPONSE_CLASS = "ecosystem.emission.disclosure.response"

#: The transition class the outbound boundary records an emission under. Read
#: from the boundary rather than restated, so a rename cannot leave this module
#: silently answering "no" for every packet.
EMITTED_CLASS = "ORGANIZATION_EGRESS_EMITTED"

HOLDS = "HOLDS_EMISSION_RECEIPT"
NO_RECORD = "NO_EMISSION_RECEIPT_ON_THIS_CHAIN"
NOT_AVAILABLE = "DISCLOSURE_NOT_AVAILABLE"


def _module(root: Path, name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, Path(root) / relative)
    if spec is None or not (Path(root) / relative).is_file():
        raise SystemExit("emission_chain_disclosure_requires:" + relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def chain_receipts(root: Path):
    """Walk this organization's repository ledger from HEAD, newest first.

    Resolved from the dispatch root for the same reason `node_standing` is: the
    kernel is organization-neutral and runs against whichever root it is handed.
    A root carrying no ledger cannot answer, and says so rather than answering
    no -- an organization with no chain has not declined to hold the receipt,
    it has no chain to consult.
    """
    ledger = _module(root, "repo_transition_emit", ".stegverse/transition-ledger/emit.py")
    store_module = _module(root, "ledger_store", "resident-runtime/ledger_store.py")
    store = store_module.PosixLedgerStore(ledger.lr())
    head = store.get(store_module.HEAD_KEY)
    cursor = (head or {}).get("receipt_sha256")
    while cursor:
        receipt = store.get(store_module.receipt_key(cursor))
        if receipt is None:
            return
        yield receipt
        cursor = receipt.get("previous_receipt_sha256")


def emission_receipt(root: Path, packet_id: str) -> dict[str, Any] | None:
    """The emission receipt this organization's chain holds for a packet id."""
    wanted = EMITTED_CLASS + ":" + str(packet_id)
    for receipt in chain_receipts(root):
        if (receipt.get("transition_class") == EMITTED_CLASS
                and receipt.get("transition_id") == wanted):
            return receipt
    return None


def disclose(root: Path, packet_id: Any, asker: Any = None) -> dict[str, Any]:
    """Answer whether this chain records emitting `packet_id`, and to whom.

    `asker` is the organization asking. When supplied, the answer states whether
    the recorded destination is that organization -- which is the question a
    bilateral match actually has. Recording the comparison here rather than
    leaving the asker to make it keeps the answer self-describing: a disclosure
    that merely said "yes, to someone" would corroborate a crossing addressed
    elsewhere.
    """
    answer = {
        "schema": DISCLOSURE_SCHEMA,
        "disclosing_organization": None,
        "request_packet_id": str(packet_id) if packet_id is not None else None,
        "asked_by": asker,
        "discloses_payloads": False,
        "discloses_other_packets": False,
        "authority_effect": "NONE_DISCLOSURE_ONLY",
    }
    try:
        registry = json.loads(
            (Path(root) / "org-boundary/registry/services.json").read_text())
        answer["disclosing_organization"] = registry.get("organization")
    except (OSError, ValueError):
        pass
    if not isinstance(packet_id, str) or not packet_id.strip():
        return {**answer, "disposition": NOT_AVAILABLE,
                "holds_emission_receipt": False,
                "detail": "no packet id was asked about"}
    try:
        receipt = emission_receipt(root, packet_id)
    except SystemExit as unavailable:
        # No chain to consult is not a denial that the receipt exists.
        return {**answer, "disposition": NOT_AVAILABLE,
                "holds_emission_receipt": False, "detail": str(unavailable)}
    if receipt is None:
        return {**answer, "disposition": NO_RECORD, "holds_emission_receipt": False}
    evidence = receipt.get("evidence") or {}
    recorded_destination = evidence.get("destination_organization")
    return {
        **answer,
        "disposition": HOLDS,
        "holds_emission_receipt": True,
        "emission_receipt_sha256": receipt.get("receipt_sha256"),
        "recorded_destination_organization": recorded_destination,
        "recorded_destination_service": evidence.get("destination_service"),
        "recorded_payload_sha256": evidence.get("payload_sha256"),
        "recorded_frame_sha256": evidence.get("frame_sha256"),
        "recorded_destination_is_the_asker": (
            None if asker is None else recorded_destination == asker),
    }


def match(disclosure: Mapping[str, Any] | None, *, packet_id: str,
          claimed_origin: str, asker: str) -> dict[str, Any]:
    """Whether a disclosure satisfies the bilateral match for this crossing.

    Unsatisfied is the default and every failure path keeps it. A peer that
    serves no disclosure, one that cannot reach its chain, and one whose chain
    holds no such receipt are three different answers and the record keeps them
    apart -- but none of them is a match.
    """
    findings = []
    if not isinstance(disclosure, Mapping):
        findings.append("PEER_SERVED_NO_DISCLOSURE:" + str(claimed_origin))
        return _match_result(False, findings, None, packet_id, claimed_origin, asker)
    disposition = disclosure.get("disposition")
    if disposition == NOT_AVAILABLE:
        findings.append("PEER_COULD_NOT_CONSULT_ITS_CHAIN:"
                        + str(disclosure.get("detail")))
    elif disposition != HOLDS or disclosure.get("holds_emission_receipt") is not True:
        findings.append("PEER_CHAIN_HOLDS_NO_EMISSION_RECEIPT_FOR_THIS_PACKET:"
                        + str(packet_id))
    if disclosure.get("request_packet_id") not in (None, packet_id):
        findings.append("DISCLOSURE_ANSWERS_A_DIFFERENT_PACKET:"
                        + str(disclosure.get("request_packet_id")))
    if disclosure.get("disclosing_organization") not in (None, claimed_origin):
        findings.append("DISCLOSURE_CAME_FROM_A_DIFFERENT_ORGANIZATION:"
                        + str(disclosure.get("disclosing_organization")))
    # A receipt recording a crossing addressed elsewhere corroborates that
    # crossing, not this one.
    if (disposition == HOLDS
            and disclosure.get("recorded_destination_organization") != asker):
        findings.append("PEER_RECORDED_EMITTING_TO_A_DIFFERENT_ORGANIZATION:"
                        + str(disclosure.get("recorded_destination_organization")))
    return _match_result(not findings, findings, disclosure, packet_id,
                         claimed_origin, asker)


def _match_result(satisfied: bool, findings: list[str],
                  disclosure: Mapping[str, Any] | None, packet_id: str,
                  claimed_origin: str, asker: str) -> dict[str, Any]:
    return {
        "schema": "stegghost.bilateral-match/v1",
        "bilateral_match_satisfied": satisfied,
        "bilateral_match_findings": findings,
        "request_packet_id": packet_id,
        "claimed_origin_organization": claimed_origin,
        "asking_organization": asker,
        "peer_chain_was_readable": bool(
            disclosure is not None
            and disclosure.get("disposition") != NOT_AVAILABLE),
        "peer_emission_receipt_sha256": (
            (disclosure or {}).get("emission_receipt_sha256") if satisfied else None),
        # What a satisfied match establishes, and what it leaves untouched.
        "corroborates_the_claimed_origin_against_its_own_chain": satisfied,
        "makes_standing_authenticated": False,
        "makes_origin_attested_by_the_credential_authority": False,
        "authority_effect": "NONE_MATCH_RECORD_ONLY",
    }
