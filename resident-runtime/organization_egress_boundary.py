#!/usr/bin/env python3
"""`ORGANIZATION_INTER_ORG_EGRESS` -- cross this organization's boundary outbound, on the record.

Inter-organization transport already worked here as a mechanism. A packet
addressed to a peer publishes into the federation mesh, that organization's
resident cycle consumes frames addressed to it, and its response comes back
addressed to the origin. What this organization could not do was *initiate* a
crossing and record its disposition: a crossing from `StegVerse-org` completed
all four of its steps, but three of them were that organization's operations.
This one performed only the consuming step. There was no `resolve`, no `emit`
and no `close` here, so leaving the organization -- the most consequential
transition the organization makes -- emitted no receipt, while the organization
ledger contract's `organization_scope_rule` is that *every* state transition
occurring within the organization emits an organization receipt.

An outbound crossing is two transitions, not one, because they are separated in
time and either can be refused on its own:

    emit    CROSS_AN_ORGANIZATION_BOUNDARY_OUTBOUND
            ORGANIZATION_EGRESS_EMITTED  / ORGANIZATION_EGRESS_REFUSED
    close   OBSERVE_THE_FAR_SIDE_CLOSURE_OF_AN_OUTBOUND_CROSSING
            ORGANIZATION_EGRESS_CLOSED   / ORGANIZATION_EGRESS_CLOSURE_REFUSED

Both dispositions are recorded at both levels -- the repository ledger first and
the organization ledger consuming that receipt -- because a crossing is not an
exception to the layering `preserves_repo_receipt` requires.

What is deliberately *not* recorded is an absence. `close` returns `PENDING` and
writes nothing when no response is in the mesh yet: nothing crossed the
boundary, so there is no arrival to dispose of, and a chain that appended a
refusal on every poll would record the polling rather than the crossing. A
response that *is* present and does not verify is a crossing with disposition
DENY, and is recorded.

The destination is resolved from `org-boundary/registry/federation.json`, this
organization's own directory of its peers, and never from a caller's argument
alone. A peer absent from the directory is refused, and so is one whose declared
`transport_profile` is not the profile this boundary speaks: a peer that cannot
be addressed is a refusal to record, not a packet to send hopefully.

Three things this records honestly rather than claiming:

* **Origin is attested only when an authority is supplied, and is asserted
  otherwise.** The frame says it came from this organization, and without an
  attestation nothing verifies that: any writer of the shared mesh can publish
  a frame claiming any origin. `emit` takes a `credential_authority` and, given
  one, asks it to sign a statement binding this origin to this packet and then
  asks it to confirm its own signature -- only the authority's verification
  receipt moves the state to `PROVEN`. An attestation that was offered and
  failed refuses the emission rather than recording it as an ordinary
  unattested crossing.

  What this organization cannot do is supply the authority. The key lives on a
  TV/TVC resident host it has no access to by design, so the signer is the
  operator's to pass in, and every crossing emitted here today is unattested.
  `signer_supplied` records which case a record is, so `NOT_PROVEN` cannot be
  read as an attempt that failed. No signing or verification algorithm appears
  in this repository, and the boundary validator refuses if one does: a second
  implementation here would make this organization a second credential
  authority, which the TV/TVC split exists to prevent.
* **The far side's receipt is recomputed, not carried.** A boundary receipt id
  is derived from the packet id, the service id and the payload digest, all of
  which this organization already holds, so the terminal id that comes back is
  recomputed and compared rather than trusted. That proves a boundary ran this
  packet and minted the chain this packet determines. It does *not* prove which
  organization that boundary belongs to, and it does not prove the far side
  persisted the chain on its own ledger -- that is the bilateral match, which
  needs the far side's chain readable and is not available at closure.
* **A peer's kernel generation is not proven here.** `kernel_required` is
  carried from the directory and compared to nothing, because a peer's kernel is
  not readable at resolution time. A local assertion about a remote kernel would
  be the same defect relocated.

Nothing here grants authority. It records a crossing that occurred and the
disposition it reached.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]

OPERATION_ID = "ORGANIZATION_INTER_ORG_EGRESS"
OWNER_REPOSITORY = "StegGhost/.github"
RESULT_SCHEMA = "stegghost.organization-egress-result/v1"
EMISSION_SCHEMA = "stegghost.organization-egress-emission-record/v1"
CLOSURE_SCHEMA = "stegghost.organization-egress-closure-record/v1"
TRANSPORT_PROFILE = "stegverse.intr.org-boundary.v1"
#: The directory field naming the service a peer is addressed at when it is not
#: an organization control service.
ADDRESSED_SERVICE_FIELD = "addressed_service"
CREDENTIAL_AUTHORITY = "TV/TVC"

#: The intended action each half of an outbound crossing carries.
INTENDED_ACTION_EMIT = "CROSS_AN_ORGANIZATION_BOUNDARY_OUTBOUND"
INTENDED_ACTION_CLOSE = "OBSERVE_THE_FAR_SIDE_CLOSURE_OF_AN_OUTBOUND_CROSSING"

#: The third transition an outbound crossing can reach, after emit and close.
#: Separate from both because it is separated in time from both and can be
#: refused on its own: closure verifies the chain the packet determines, the
#: match asks the claimed origin's own chain whether it records emitting it.
INTENDED_ACTION_MATCH = "CORROBORATE_A_CLAIMED_ORIGIN_AGAINST_ITS_OWN_CHAIN"
MATCH_SCHEMA = "stegghost.organization-bilateral-match-record/v1"

#: One class per disposition, so no reader can mistake a refusal for a crossing
#: that left, or an unverified response for a closed one.
EMITTED_CLASS = "ORGANIZATION_EGRESS_EMITTED"
MATCH_SATISFIED_CLASS = "ORGANIZATION_BILATERAL_MATCH_SATISFIED"
MATCH_REFUSED_CLASS = "ORGANIZATION_BILATERAL_MATCH_REFUSED"
EMIT_REFUSED_CLASS = "ORGANIZATION_EGRESS_REFUSED"
CLOSED_CLASS = "ORGANIZATION_EGRESS_CLOSED"
CLOSURE_REFUSED_CLASS = "ORGANIZATION_EGRESS_CLOSURE_REFUSED"

ALLOW = "ALLOW"
DENY = "DENY"
PENDING = "PENDING"


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kernel = _module("org_kernel", "org-kernel/kernel.py")
repository_ledger = _module("repo_transition_emit", ".stegverse/transition-ledger/emit.py")
organization_ledger = _module("aggregate_repo_transition",
                              "resident-runtime/aggregate_repo_transition.py")
ledger_store = _module("ledger_store", "resident-runtime/ledger_store.py")
disclosure_module = _module("emission_chain_disclosure",
                            "org-boundary/runtime/emission_chain_disclosure.py")
attestation_module = _module("origin_attestation",
                             "org-boundary/runtime/origin_attestation.py")

#: The acknowledgement classes a response may carry. Read from the kernel rather
#: than restated, so this boundary cannot disagree with the surface that mints
#: them about what an acknowledgement is.
ACK_CLASSES = kernel.ACK_CLASSES


class EgressRefused(Exception):
    """A refusal carrying its own disposition, so a caller is never left guessing."""

    def __init__(self, failed_predicate: str, reason: str) -> None:
        super().__init__(reason)
        self.failed_predicate = failed_predicate
        self.reason = reason


def canon(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canon(value)).hexdigest()


def this_organization(root: Path | None = None) -> str:
    return kernel.load_registry(root or ROOT)["organization"]


def resolve_destination(organization: str, *, root: Path | None = None) -> dict[str, Any]:
    """Resolve a peer from this organization's own peer directory.

    The directory is the authority on who this organization's peers are and how
    each is addressed. A destination taken from a caller's argument alone would
    let the caller name its own peer, which is the same error as letting a
    caller name its own organization at ingress.
    """
    directory = kernel.load_federation_directory(root or ROOT)
    for row in directory.get("organizations", []):
        if row.get("organization") != organization:
            continue
        profile = row.get("transport_profile")
        if profile != TRANSPORT_PROFILE:
            raise EgressRefused(
                "DESTINATION_SPEAKS_THIS_BOUNDARY_TRANSPORT_PROFILE",
                "peer declares transport_profile " + str(profile)
                + "; this boundary speaks " + TRANSPORT_PROFILE)
        control = row.get("org_control_service")
        # A peer is addressed at the service it declares it serves, which is not
        # always a control service. `addressed_service` says so when it differs;
        # `org_control_service` remains the default for every peer that serves
        # one.
        addressed = row.get(ADDRESSED_SERVICE_FIELD) or control
        if not addressed:
            raise EgressRefused(
                "DESTINATION_DECLARES_A_SERVICE_THIS_DIRECTORY_CAN_ADDRESS",
                "peer declares neither " + ADDRESSED_SERVICE_FIELD
                + " nor org_control_service: " + str(organization))
        return {
            "disposition": ALLOW,
            "destination_organization": organization,
            "destination_repository": row.get("repository"),
            "destination_org_control_service": control,
            "destination_addressed_service": addressed,
            "destination_service": addressed,
            "destination_serves_an_organization_control_service": bool(control),
            "destination_kernel_required": row.get("kernel_required"),
            "transport_profile": profile,
            "destination_resolution_source": "ORGANIZATION_FEDERATION_DIRECTORY",
            "destination_resolved_from_caller_argument": False,
            # `kernel_required` is carried from the directory and checked by
            # nothing, unlike `transport_profile`, which is refused on mismatch.
            # A peer's kernel generation is not readable from here at resolution
            # time, so the field is a requirement this organization declares and
            # cannot verify. This organization was itself an instance: it
            # declared kernel_version 1.3.1 while running a kernel that gated no
            # node standing at all, until
            # PEER_KERNEL_GENERATION_ADMISSION_APPLIED_002.
            "destination_kernel_generation_is_proven_here": False,
            "destination_kernel_required_is_checked_at_resolution": False,
            "declared_kernel_version_does_not_establish_the_enforcement_it_implies": True,
        }
    raise EgressRefused(
        "DESTINATION_IS_A_DECLARED_PEER_OF_THIS_ORGANIZATION",
        "organization not in org-boundary/registry/federation.json: " + str(organization))


def closability_refusal(payload: Mapping[str, Any]) -> tuple[str, str] | None:
    """Why this payload's crossing could never close, or None if it can.

    The decision belongs to the kernel, which owns `RESPONDED_REQUEST_CLASSES`
    and is the surface that answers them; a second copy of that rule here would
    be a second authority on closability. What this adds is the boundary's own
    disposition vocabulary, so a refusal names the predicate that failed rather
    than only the condition.
    """
    reason = kernel.closability_refusal(dict(payload))
    if reason is None:
        return None
    if "message_class_is_answered_by_no_acknowledgement" in reason:
        return ("PAYLOAD_DECLARES_A_REQUEST_CLASS_THE_BOUNDARY_ANSWERS", reason)
    return ("PAYLOAD_CARRIES_THE_COMMUNICATION_ID_CLOSURE_CORRELATES_ON", reason)


def resolve_standing(standing: Mapping[str, Any], root: Path | None = None):
    """Resolve a standing declaration through this organization's own ingress contract.

    Returns `(None, disposition)` when it holds, or `(refusal, None)` when it
    does not. The contract is the same one `node_standing` enforces at ingress,
    read from the same place, so this boundary cannot admit outbound what it
    would refuse inbound.

    This is stricter than the reference boundary, which passes `standing`
    straight to the constructor. `kernel.build_packet` requires the argument but
    does not check its shape, so an empty or incoherent declaration is buildable
    and publishable here and then refused fail-closed at the far side's ingress.
    That is a crossing emitted that can never close -- the same defect
    `closability_refusal` exists to prevent, arriving by a different route -- so
    it is refused at emission and recorded, rather than sent and lost.
    """
    base = Path(root or ROOT)
    module = kernel.node_standing(base)
    try:
        resolved = module.require(module.load_contract(base),
                                  {"standing": dict(standing or {})})
    except SystemExit as refused:
        # node_standing refuses with the contract's own disposition name, which
        # is more useful to a reader of the chain than a restatement here.
        return (("STANDING_DECLARATION_THIS_ORGANIZATIONS_OWN_INGRESS_WOULD_ADMIT",
                 str(refused)), None)
    return (None, resolved)


def _attestation(attested: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What this boundary can say about who sent the packet.

    With an attestation record, that record is what is carried: the credential
    authority signed a statement naming this origin for this packet and
    confirmed its own signature, so `origin_attestation_state` is `PROVEN`
    rather than the assertion it replaces.

    Without one the gap is recorded rather than hidden. A frame in a shared mesh
    carries whatever origin its writer put in it, and an unattested crossing
    says so. The unattested record is the module's own, so this boundary cannot
    drift from the authority's vocabulary about its own absence.

    What changed with the seam is narrow and worth stating exactly: a path to
    `PROVEN` now exists, and nothing in this organization reaches it on its own.
    The authority's key lives on a TV/TVC resident host this organization
    cannot reach, so the signer is the operator's to supply and every crossing
    emitted here today is unattested. `signer_supplied` records which of those
    two it was, so an unattested record cannot be read as a failed attempt.
    """
    if attested is not None:
        return {**dict(attested), "signer_supplied": True}
    return {**attestation_module.unattested_record(), "signer_supplied": False}


def emission_record(resolved: Mapping[str, Any], origin: str, packet: Mapping[str, Any],
                    frame: Mapping[str, Any], payload: Mapping[str, Any],
                    standing: Mapping[str, Any],
                    attested: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """What an emitted crossing recorded.

    Digests, not payloads: the body a caller sent is its own, and what the chain
    needs is that this organization addressed that peer and what left, bound so
    neither can be swapped afterwards.

    `far_side_service_id` and `far_side_payload_hash` are carried because
    closure recomputes the far side's chain from them. Reading them back off
    this record at closure is what makes the recomputation a check against what
    this organization recorded emitting, rather than against what the response
    asserts about itself.
    """
    return {
        "schema": EMISSION_SCHEMA,
        "operation": OPERATION_ID,
        "owner_repository": OWNER_REPOSITORY,
        "intended_action": INTENDED_ACTION_EMIT,
        "disposition": ALLOW,
        "origin_organization": origin,
        "origin_service": packet["origin"]["service"],
        **{key: resolved[key] for key in (
            "destination_organization", "destination_repository",
            "destination_org_control_service", "destination_addressed_service",
            "destination_service", "destination_kernel_required",
            "transport_profile", "destination_resolution_source",
            "destination_resolved_from_caller_argument",
            "destination_kernel_generation_is_proven_here",
            "destination_kernel_required_is_checked_at_resolution",
            "declared_kernel_version_does_not_establish_the_enforcement_it_implies")},
        "packet_id": packet["packet_id"],
        "communication_id": payload.get("communication_id"),
        "message_class": payload.get("message_class"),
        "payload_sha256": sha(dict(payload)),
        "packet_sha256": frame["packet_sha256"],
        "frame_sha256": frame["frame_sha256"],
        # Read from the resolved disposition rather than from the declaration,
        # so the record states what this organization's own ingress contract
        # made of the standing, not what the caller wrote.
        "standing_declared": True,
        "node_standing_disposition": standing.get("node_standing_disposition"),
        "standing_mode": standing.get("standing_mode"),
        "standing_node_ref": standing.get("standing_node_ref"),
        "standing_generation": standing.get("standing_generation"),
        "standing_resolved_through_this_organizations_ingress_contract": True,
        "structural_standing_is_authenticated_standing": False,
        # The three inputs closure recomputes the far side's chain from.
        "far_side_service_id": resolved["destination_service"],
        "far_side_payload_hash": kernel.sha(dict(payload)),
        "crossed_an_organization_boundary": True,
        "interlock_intr_involved": True,
        **_attestation(attested),
        "authority_effect": "NONE_EGRESS_RECORD_ONLY",
    }


def emit_refusal_record(failed_predicate: str, reason: str, organization: Any,
                        origin: str, payload: Mapping[str, Any]) -> dict[str, Any]:
    """What a refused crossing recorded. Nothing left, and the record says which predicate failed."""
    return {
        "schema": EMISSION_SCHEMA,
        "operation": OPERATION_ID,
        "owner_repository": OWNER_REPOSITORY,
        "intended_action": INTENDED_ACTION_EMIT,
        "disposition": DENY,
        "origin_organization": origin,
        "destination_organization_requested": organization
        if isinstance(organization, str) else repr(organization),
        "failed_predicate": failed_predicate,
        "refusal_reason": reason,
        "payload_sha256": sha(dict(payload or {})),
        "communication_id": (payload or {}).get("communication_id"),
        "message_class": (payload or {}).get("message_class"),
        "nothing_crossed_the_boundary": True,
        "crossed_an_organization_boundary": False,
        "interlock_intr_involved": True,
        **_attestation(),
        "authority_effect": "NONE_EGRESS_RECORD_ONLY",
    }


def closure_record(resolved: Mapping[str, Any], origin: str, packet_id: str,
                   communication_id: str, response: Mapping[str, Any],
                   findings: list[str], recomputed: list[str]) -> dict[str, Any]:
    """What an observed closure recorded, verified or refused."""
    verified = not findings
    return {
        "schema": CLOSURE_SCHEMA,
        "operation": OPERATION_ID,
        "owner_repository": OWNER_REPOSITORY,
        "intended_action": INTENDED_ACTION_CLOSE,
        "disposition": ALLOW if verified else DENY,
        "origin_organization": origin,
        "destination_organization": resolved["destination_organization"],
        "destination_service": resolved["destination_service"],
        "request_packet_id": packet_id,
        "communication_id": communication_id,
        "responding_organization": response.get("organization"),
        "response_packet_id": response.get("response_packet_id"),
        "response_message_class": response.get("message_class"),
        "far_side_terminal_receipt": response.get("receipt_terminal"),
        "far_side_receipt_chain_recomputed_here": recomputed,
        "far_side_terminal_receipt_recomputed": recomputed[-1] if recomputed else None,
        "far_side_terminal_receipt_matches_recomputation": verified,
        # What the recomputation proves, and the three things it does not.
        "reconstruction_proves_the_boundary_ran_this_packet": verified,
        "reconstruction_proves_who_the_far_side_is": False,
        "reconstruction_proves_the_far_side_persisted_its_chain": False,
        # Still required, and still not established by closure: a closure
        # verifies the chain this packet determines, which is a different
        # question from whose boundary minted it. What changed is that the
        # match is now a reachable operation rather than an acknowledged gap,
        # and this organization serves the half a peer would ask of it.
        "bilateral_match_requires_the_far_side_chain_to_be_readable": True,
        "bilateral_match_is_a_separate_transition": (
            "resident-runtime/organization_egress_boundary.py::observe_bilateral_match"),
        "this_organization_serves_its_half_of_the_bilateral_match": True,
        "closure_findings": findings,
        "crossed_an_organization_boundary": True,
        "interlock_intr_involved": True,
        **_attestation(),
        "authority_effect": "NONE_CLOSURE_RECORD_ONLY",
    }


def _record(transition_id: str, transition_class: str, predecessor: str, successor: str,
            record: Mapping[str, Any], hb_epoch: int | None) -> dict[str, Any]:
    """Append at both levels: the repository first, the organization consuming it."""
    repository_receipt = repository_ledger.append(
        transition_id, transition_class, predecessor, successor,
        dict(record), "NONE", hb_epoch=hb_epoch)
    organization_receipt = organization_ledger.append(
        repository_receipt, "REPO_STATE_PROPAGATION", predecessor, successor,
        {"operation": OPERATION_ID,
         "intended_action": record["intended_action"],
         "disposition": record["disposition"],
         "crossed_an_organization_boundary": record["crossed_an_organization_boundary"]},
        "NONE", hb_epoch=hb_epoch)
    return {"repository_receipt": repository_receipt,
            "organization_receipt": organization_receipt}


def emit(destination_organization: Any, payload: Mapping[str, Any], *,
         standing: Mapping[str, Any],
         credential_authority: Mapping[str, Any] | None = None,
         transition_reference: str = "ecosystem.transition.interorg.v1",
         root: Path | None = None, mesh_root: Path | None = None,
         hb_epoch: int | None = None) -> dict[str, Any]:
    """Emit an outbound crossing to a declared peer, and record its disposition.

    The record is appended *after* the frame is published, because the record is
    of an emission and carries the frame's digest. Minting it first would be a
    receipt claiming a crossing that had not happened yet.
    """
    origin = this_organization(root)
    try:
        unclosable = closability_refusal(payload or {})
        if unclosable is not None:
            raise EgressRefused(*unclosable)
        standing_refused, standing_disposition = resolve_standing(standing, root=root)
        if standing_refused is not None:
            raise EgressRefused(*standing_refused)
        resolved = resolve_destination(destination_organization, root=root)
        packet = kernel.build_packet(
            origin_org=origin,
            origin_service=kernel.organization_slug(origin) + ".org-control",
            destination_org=resolved["destination_organization"],
            destination_service=resolved["destination_service"],
            payload=dict(payload), standing=dict(standing),
            transition_reference=transition_reference, authority_effect="NONE")
        # Attested after the packet exists, because the statement binds the
        # packet id, and before it is published, because the signature travels
        # inside the packet where `packet_sha256` binds it. The statement itself
        # does not include the signature, so attaching it changes nothing the
        # authority signed.
        attested = None
        if credential_authority is not None:
            declared = attestation_module.statement_from_packet(
                packet, kernel.sha(dict(payload)))
            try:
                signature, receipt = attestation_module.attest(
                    declared, credential_authority)
            except attestation_module.AttestationRefused as refused:
                # An attestation was offered and did not establish. Emitting
                # anyway would record it as an ordinary unattested crossing and
                # lose the fact that one was attempted and failed, so the
                # emission is refused instead.
                raise EgressRefused(refused.failed_predicate, refused.reason) from None
            attested = attestation_module.record(declared, signature, receipt)
            packet = {**packet, "attestation": signature}
        published = kernel.publish_packet(packet, root=mesh_root)
    except EgressRefused as exc:
        record = emit_refusal_record(exc.failed_predicate, exc.reason,
                                     destination_organization, origin, payload)
        appended = _record(EMIT_REFUSED_CLASS + ":" + sha(record)[7:23], EMIT_REFUSED_CLASS,
                           record["payload_sha256"], sha(record), record, hb_epoch)
        return _refusal_result(record, appended)
    except (ValueError, KeyError, TypeError) as exc:
        record = emit_refusal_record("PACKET_IS_BUILDABLE_AND_PUBLISHABLE_AS_DECLARED",
                                     str(exc), destination_organization, origin, payload)
        appended = _record(EMIT_REFUSED_CLASS + ":" + sha(record)[7:23], EMIT_REFUSED_CLASS,
                           record["payload_sha256"], sha(record), record, hb_epoch)
        return _refusal_result(record, appended)

    record = emission_record(resolved, origin, packet, published["frame"], payload,
                             standing_disposition, attested)
    appended = _record(EMITTED_CLASS + ":" + packet["packet_id"], EMITTED_CLASS,
                       record["payload_sha256"], sha(record), record, hb_epoch)
    return {
        "schema": RESULT_SCHEMA,
        "operation": OPERATION_ID,
        "disposition": ALLOW,
        "emitted": True,
        "packet_id": packet["packet_id"],
        "communication_id": (payload or {}).get("communication_id"),
        **{k: record[k] for k in ("destination_organization", "destination_repository",
                                  "destination_org_control_service", "destination_service",
                                  "transport_profile", "destination_resolution_source",
                                  "frame_sha256", "crossed_an_organization_boundary",
                                  "origin_attestation_state",
                                  "origin_is_attested_by_the_credential_authority",
                                  "signer_supplied")},
        "emission_record": record,
        "emission_transition_class": EMITTED_CLASS,
        "emission_repository_receipt_sha256": appended["repository_receipt"]["receipt_sha256"],
        "emission_organization_receipt_sha256": appended["organization_receipt"]["receipt_sha256"],
        "authority_effect": "NONE_EGRESS_RECORD_ONLY",
    }


def _refusal_result(record: Mapping[str, Any], appended: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": RESULT_SCHEMA,
        "operation": OPERATION_ID,
        "disposition": DENY,
        "emitted": False,
        "failed_predicate": record["failed_predicate"],
        "detail": record["refusal_reason"],
        "refusal_recorded": True,
        "emission_transition_class": EMIT_REFUSED_CLASS,
        "emission_record": dict(record),
        "emission_repository_receipt_sha256": appended["repository_receipt"]["receipt_sha256"],
        "emission_organization_receipt_sha256": appended["organization_receipt"]["receipt_sha256"],
        "authority_effect": "NONE_EGRESS_RECORD_ONLY",
    }


def recorded_emission(packet_id: str) -> dict[str, Any] | None:
    """This organization's own emission record for a packet, read off its chain.

    A closure is verified against what this organization recorded emitting, not
    against what the response asserts. Walking its own chain is also the local
    half of the bilateral match: a crossing with no emission receipt here is one
    this organization has no record of making, and it cannot be closed.
    """
    store = ledger_store.PosixLedgerStore(repository_ledger.lr())
    head = store.get(ledger_store.HEAD_KEY)
    cursor = (head or {}).get("receipt_sha256")
    wanted = EMITTED_CLASS + ":" + packet_id
    while cursor:
        receipt = store.get(ledger_store.receipt_key(cursor))
        if receipt is None:
            return None
        if (receipt.get("transition_class") == EMITTED_CLASS
                and receipt.get("transition_id") == wanted):
            evidence = receipt.get("evidence")
            return dict(evidence) if isinstance(evidence, Mapping) else None
        cursor = receipt.get("previous_receipt_sha256")
    return None


def verify_closure(resolved: Mapping[str, Any], packet_id: str,
                   response: Mapping[str, Any],
                   emission: Mapping[str, Any] | None = None) -> list[str]:
    """What fails to hold about a response that arrived. Empty means it closes."""
    findings = []
    if response.get("request_packet_id") != packet_id:
        findings.append("RESPONSE_ANSWERS_A_DIFFERENT_PACKET:"
                        + str(response.get("request_packet_id")))
    if response.get("organization") != resolved["destination_organization"]:
        findings.append("RESPONSE_CAME_FROM_A_DIFFERENT_ORGANIZATION:"
                        + str(response.get("organization")))
    if response.get("message_class") not in ACK_CLASSES:
        findings.append("RESPONSE_CARRIES_NO_ACKNOWLEDGEMENT_CLASS:"
                        + str(response.get("message_class")))
    terminal = response.get("receipt_terminal")
    if not isinstance(terminal, str) or not terminal.strip():
        findings.append("RESPONSE_CARRIES_NO_FAR_SIDE_TERMINAL_RECEIPT")
        return findings
    # Recomputed, not trusted. Without this organization's own emission record
    # there is nothing to recompute against, and a crossing it has no record of
    # emitting is not one it can close.
    if emission is None:
        findings.append("THIS_ORGANIZATION_HAS_NO_EMISSION_RECORD_FOR_THIS_PACKET")
        return findings
    recomputed = kernel.far_side_receipt_chain(
        packet_id, emission["far_side_service_id"], emission["far_side_payload_hash"])
    if terminal != recomputed[-1]:
        findings.append("FAR_SIDE_TERMINAL_RECEIPT_DOES_NOT_RECOMPUTE:" + terminal)
    return findings


def close(destination_organization: str, packet_id: str, communication_id: str, *,
          root: Path | None = None, mesh_root: Path | None = None,
          hb_epoch: int | None = None) -> dict[str, Any]:
    """Observe the far side's closure of an emitted crossing, and record it.

    Returns `PENDING` and records nothing when no response is in the mesh. An
    absence is not an arrival: nothing crossed the boundary, so there is no
    disposition to record, and appending a refusal per poll would record the
    polling rather than the crossing.
    """
    origin = this_organization(root)
    resolved = resolve_destination(destination_organization, root=root)
    collected = kernel.collect_ecosystem_responses(origin, communication_id,
                                                   mesh_root=mesh_root)
    responses = [row for row in collected.get("organizations", [])
                 if row.get("organization") == resolved["destination_organization"]]
    if not responses:
        return {
            "schema": RESULT_SCHEMA,
            "operation": OPERATION_ID,
            "disposition": PENDING,
            "closed": False,
            "closure_recorded": False,
            "absence_is_not_a_transition": True,
            "communication_id": communication_id,
            "request_packet_id": packet_id,
            "destination_organization": resolved["destination_organization"],
            "authority_effect": "NONE_OBSERVATION_ONLY",
        }
    response = responses[0]
    emission = recorded_emission(packet_id)
    findings = verify_closure(resolved, packet_id, response, emission)
    recomputed = kernel.far_side_receipt_chain(
        packet_id, emission["far_side_service_id"], emission["far_side_payload_hash"]
    ) if emission else []
    record = closure_record(resolved, origin, packet_id, communication_id, response,
                            findings, recomputed)
    transition_class = CLOSED_CLASS if not findings else CLOSURE_REFUSED_CLASS
    appended = _record(transition_class + ":" + packet_id, transition_class,
                       sha({"packet_id": packet_id, "communication_id": communication_id}),
                       sha(record), record, hb_epoch)
    return {
        "schema": RESULT_SCHEMA,
        "operation": OPERATION_ID,
        "disposition": record["disposition"],
        "closed": not findings,
        "closure_recorded": True,
        "closure_findings": findings,
        "communication_id": communication_id,
        "request_packet_id": packet_id,
        "destination_organization": resolved["destination_organization"],
        "responding_organization": response.get("organization"),
        "far_side_terminal_receipt": response.get("receipt_terminal"),
        "far_side_receipt_reconstructed_here": True,
        "far_side_terminal_receipt_recomputed": recomputed[-1] if recomputed else None,
        "closure_record": record,
        "closure_transition_class": transition_class,
        "closure_repository_receipt_sha256": appended["repository_receipt"]["receipt_sha256"],
        "closure_organization_receipt_sha256": appended["organization_receipt"]["receipt_sha256"],
        "authority_effect": "NONE_CLOSURE_RECORD_ONLY",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--destination-organization", required=True)
    parser.add_argument("--payload", help="JSON file carrying the payload")
    parser.add_argument("--standing",
                        help="JSON file declaring mode, node_ref and the predecessor key")
    parser.add_argument("--transition-reference", default="ecosystem.transition.interorg.v1")
    parser.add_argument("--hb-epoch", type=int, default=None,
                        help="heartbeat epoch; derived from the host clock, and marked as "
                             "derived, when absent")
    parser.add_argument("--resolve", action="store_true",
                        help="resolve the peer and print the resolution without emitting")
    parser.add_argument("--close", action="store_true",
                        help="observe the far side's closure of --packet-id instead of emitting")
    parser.add_argument("--packet-id")
    parser.add_argument("--communication-id")
    parser.add_argument("--out")
    args = parser.parse_args()

    if args.resolve:
        try:
            result = resolve_destination(args.destination_organization)
        except EgressRefused as refused:
            result = {"disposition": DENY, "failed_predicate": refused.failed_predicate,
                      "detail": refused.reason}
    elif args.close:
        if not args.packet_id or not args.communication_id:
            raise SystemExit("--close requires --packet-id and --communication-id")
        result = close(args.destination_organization, args.packet_id, args.communication_id,
                       hb_epoch=args.hb_epoch)
    else:
        if not args.payload or not args.standing:
            raise SystemExit("emitting requires --payload and --standing")
        standing = json.loads(Path(args.standing).read_text(encoding="utf-8"))
        if not isinstance(standing, dict) or "predecessor" not in standing:
            raise SystemExit("standing must declare the predecessor key; null is explicit genesis")
        payload = json.loads(Path(args.payload).read_text(encoding="utf-8"))
        result = emit(args.destination_organization, payload, standing=standing,
                      transition_reference=args.transition_reference, hb_epoch=args.hb_epoch)
    rendered = json.dumps(result, indent=2, sort_keys=True)
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result["disposition"] in (ALLOW, PENDING) else 1


if __name__ == "__main__":
    sys.exit(main())


# --------------------------------------------------------------------------
# The bilateral match: corroborate a claimed origin against its own chain.
#
# Recomputing a far-side receipt chain proves a boundary ran the packet and not
# whose boundary it was, because every input is held by the recomputing side.
# The other half is the claimed origin's own ledger holding an emission receipt
# for that packet id, addressed here -- which a forged origin cannot produce,
# because it cannot write that organization's chain.
#
# Two operations, for the same reason emit and close are two: asking and
# observing are separated in time and either can be refused on its own. The ask
# is itself an ordinary governed crossing, emitted and recorded like any other,
# so the match does not need a transport of its own.
# --------------------------------------------------------------------------

def request_bilateral_match(claimed_origin: str, packet_id: str, *,
                            standing: Mapping[str, Any],
                            communication_id: str | None = None,
                            root: Path | None = None, mesh_root: Path | None = None,
                            hb_epoch: int | None = None) -> dict[str, Any]:
    """Ask a claimed origin whether its own chain records emitting this packet.

    Emitted through `emit`, deliberately. The ask crosses an organization
    boundary outbound, so it is that transition and is recorded as one; giving
    it a private path would be the outbound boundary exempting its own traffic
    from the record it exists to keep.
    """
    identifier = communication_id or ("bilateral-match:" + str(packet_id))
    payload = {
        "message_class": disclosure_module.REQUEST_CLASS,
        "communication_id": identifier,
        "subject": "emission-chain-disclosure",
        "body": {"request_packet_id": str(packet_id),
                 "asks_only_about_this_packet": True,
                 "asks_for_no_payload": True},
        "requested_action": None,
        "audience": "ORIGIN",
        "target_organization": claimed_origin,
        "target_count": 1,
    }
    result = emit(claimed_origin, payload, standing=standing, root=root,
                  mesh_root=mesh_root, hb_epoch=hb_epoch)
    return {**result, "bilateral_match_communication_id": identifier,
            "bilateral_match_subject_packet_id": str(packet_id)}


def observe_bilateral_match(claimed_origin: str, packet_id: str,
                            communication_id: str, *,
                            root: Path | None = None, mesh_root: Path | None = None,
                            hb_epoch: int | None = None) -> dict[str, Any]:
    """Observe the disclosure a claimed origin returned, and record the match.

    `PENDING` when nothing has come back, recording nothing, for the reason
    `close` does the same: an absence is not an arrival, and appending a refusal
    per poll would record the polling rather than the crossing.

    A peer that answers it serves no disclosure is a refusal with its own
    finding, not a pass and not an error. Most peers answer exactly that today:
    this organization serves its half first, and the match completes only where
    a peer serves the other.
    """
    asker = this_organization(root)
    resolved = resolve_destination(claimed_origin, root=root)
    collected = kernel.collect_ecosystem_responses(asker, communication_id,
                                                   mesh_root=mesh_root)
    responses = [row for row in collected.get("organizations", [])
                 if row.get("organization") == resolved["destination_organization"]]
    if not responses:
        return {
            "schema": RESULT_SCHEMA,
            "operation": OPERATION_ID,
            "disposition": PENDING,
            "bilateral_match_satisfied": False,
            "match_recorded": False,
            "absence_is_not_a_transition": True,
            "communication_id": communication_id,
            "request_packet_id": str(packet_id),
            "claimed_origin_organization": resolved["destination_organization"],
            "authority_effect": "NONE_OBSERVATION_ONLY",
        }
    response = responses[0]
    disclosure = ((response.get("application_result") or {}).get("emission_disclosure"))
    match = disclosure_module.match(disclosure, packet_id=str(packet_id),
                                    claimed_origin=resolved["destination_organization"],
                                    asker=asker)
    record = {
        "schema": MATCH_SCHEMA,
        "operation": OPERATION_ID,
        "owner_repository": OWNER_REPOSITORY,
        "intended_action": INTENDED_ACTION_MATCH,
        "disposition": ALLOW if match["bilateral_match_satisfied"] else DENY,
        "asking_organization": asker,
        "claimed_origin_organization": resolved["destination_organization"],
        "request_packet_id": str(packet_id),
        "communication_id": communication_id,
        "disclosure": dict(disclosure) if isinstance(disclosure, Mapping) else None,
        **{k: match[k] for k in (
            "bilateral_match_satisfied", "bilateral_match_findings",
            "peer_chain_was_readable", "peer_emission_receipt_sha256",
            "corroborates_the_claimed_origin_against_its_own_chain",
            "makes_standing_authenticated",
            "makes_origin_attested_by_the_credential_authority")},
        "crossed_an_organization_boundary": True,
        "interlock_intr_involved": True,
        **_attestation(),
        "authority_effect": "NONE_MATCH_RECORD_ONLY",
    }
    transition_class = (MATCH_SATISFIED_CLASS if match["bilateral_match_satisfied"]
                        else MATCH_REFUSED_CLASS)
    appended = _record(transition_class + ":" + str(packet_id), transition_class,
                       sha({"packet_id": str(packet_id),
                            "communication_id": communication_id}),
                       sha(record), record, hb_epoch)
    return {
        "schema": RESULT_SCHEMA,
        "operation": OPERATION_ID,
        "disposition": record["disposition"],
        "bilateral_match_satisfied": match["bilateral_match_satisfied"],
        "match_recorded": True,
        "bilateral_match_findings": match["bilateral_match_findings"],
        "peer_chain_was_readable": match["peer_chain_was_readable"],
        "communication_id": communication_id,
        "request_packet_id": str(packet_id),
        "claimed_origin_organization": resolved["destination_organization"],
        "match_record": record,
        "match_transition_class": transition_class,
        "match_repository_receipt_sha256": appended["repository_receipt"]["receipt_sha256"],
        "match_organization_receipt_sha256": appended["organization_receipt"]["receipt_sha256"],
        "authority_effect": "NONE_MATCH_RECORD_ONLY",
    }
