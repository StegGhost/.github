#!/usr/bin/env python3
"""Release a verified organization receipt-chain segment, and submit it as a record.

Organization receipts are recorded at the organization level and then batched to
`master-records`. Those are two different acts and the distinction is the whole
point of this module:

    recorded at the organization level .... the transition is real here, under
                                            the organization ledger lock
    batched to master-records ............. a segment this organization has
                                            independently verified and released
                                            is handed over as an organization
                                            record

`master-records` is the `RELEASED_ORGANIZATION_BATCH_RECEIPT_RECORDER`. It holds
organization records and serves reconstruction from them. Custody of this
organization's receipts, its retained evidence, its authoritative history and
its runtime reality stay with the Organization, under the organization ledger
lock; a transition is real when it is appended there -- not when a batch
carrying it is recorded downstream. Admission and closure of the handover
belong to Interlock/InTr.

Which is why release and submission are separated here rather than fused into
one call. `release` completes against this organization's own ledger and is
final the moment it returns. `submit` is an ordinary recorded crossing that may
refuse, and its refusal changes nothing about the release it carries. A batch
that has not been released or recorded is a value in the attempted transition's
evidence state -- not a blocker, and not proof of non-occurrence.

The release predecessor is a *verified* segment, and verified means each receipt
re-digested against its own body. A segment containing one receipt whose claimed
digest is not the digest of its body is not released: the receipts before it are
not made trustworthy by it, and releasing them under a batch digest would put
this organization's signature on a chain it had not actually checked.

Exactly-once, by reading rather than remembering. A segment already carried by a
prior release is skipped, read off the organization chain itself, so a second run
is a no-op instead of a duplicate batch.

What this module will not do is address an organization record to a service
that has not been declared. The contract names `master-records/.github` as the
propagation target; the federation directory's row for that organization
declares an `org_control_service` and nothing else. A control service is the
control plane, not an organization record service, and submitting a batch to it
because it is the service that happens to exist is the same substitution this
boundary refuses everywhere else. So the submission refuses with a named
predicate until the organization record service is declared. It refuses
*immediately* and locally: nothing is queued against the day it appears, nothing
polls for it, and no machine is awaited.

Nothing here grants authority. A release records that this organization verified
and handed over a segment of its own chain. It does not make the segment true --
the ledger already did that -- and it confers nothing on the recorder.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(Path(__file__).resolve().parent))
from ledger_store import (HEAD_KEY, RECEIPT_PREFIX, PosixLedgerStore,  # noqa: E402
                          receipt_key)

ORG_CONTRACT = ROOT / ".stegverse/transition-ledger/org-contract.json"
FEDERATION = ROOT / "org-boundary/registry/federation.json"

ORGANIZATION_RECEIPT_SCHEMA = "stegverse.organization-transition-receipt/v1"
BATCH_SCHEMA = "stegghost.organization-batch-release-record/v1"
RESULT_SCHEMA = "stegghost.organization-batch-release/v1"
RELEASE_CLASS = "ORGANIZATION_BATCH_RELEASED"
SUBMIT_CLASS = "ORGANIZATION_BATCH_SUBMITTED_AS_ORGANIZATION_RECORD"
SUBMIT_REFUSED_CLASS = "ORGANIZATION_BATCH_ORGANIZATION_RECORD_SUBMISSION_REFUSED"

#: The role the recorder holds, and the two it does not. Restated on every
#: release record so a batch cannot be read as a transfer of authority.
RECORDER_ROLE = "RELEASED_ORGANIZATION_BATCH_RECEIPT_RECORDER"
RELEASE_PREDECESSOR_REQUIRED = "VERIFIED_ORGANIZATION_RECEIPT_CHAIN_SEGMENT"

#: A release with nothing in it. Named rather than represented by a zero digest,
#: which would read like a real state this organization had been in.
NO_PRIOR_RELEASE = "NO_PRIOR_ORGANIZATION_BATCH_RELEASE"

ALLOW = "ALLOW"
DENY = "DENY"

RECORD_SERVICE_PREDICATE = (
    "AN_ORGANIZATION_RECORD_SERVICE_IS_DECLARED_FOR_THE_PROPAGATION_TARGET")
SEGMENT_PREDICATE = "EVERY_RECEIPT_IN_THE_SEGMENT_VERIFIES_AGAINST_ITS_OWN_BODY"
TARGET_PREDICATE = "THE_PROPAGATION_TARGET_IS_DECLARED_IN_THE_FEDERATION_DIRECTORY"


def _module(name: str, relative: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


organization_ledger = _module("aggregate_repo_transition",
                              "resident-runtime/aggregate_repo_transition.py")
repository_ledger = _module("transition_ledger_emit",
                            ".stegverse/transition-ledger/emit.py")
egress = _module("organization_egress_boundary",
                 "resident-runtime/organization_egress_boundary.py")

sha = organization_ledger.sha


class ReleaseRefused(Exception):
    """A release or submission that must not complete, with its predicate named."""

    def __init__(self, failed_predicate: str, reason: str) -> None:
        super().__init__(reason)
        self.failed_predicate = failed_predicate
        self.reason = reason


def contract() -> dict[str, Any]:
    return json.loads(ORG_CONTRACT.read_text(encoding="utf-8"))


# --------------------------------------------------------------- the segment

def organization_chain() -> list[dict[str, Any]]:
    """Every organization receipt in chain order, genesis first, each verified.

    Walked backwards from the published head and reversed, so the order is the
    ledger's own rather than a directory listing's. A receipt whose claimed
    digest is not the digest of its body stops the walk: this is the check that
    makes the word "verified" in `RELEASE_PREDECESSOR_REQUIRED` mean something.
    """
    store = PosixLedgerStore(organization_ledger.ledger_root())
    head = store.get(HEAD_KEY)
    if head is None:
        return []
    chain: list[dict[str, Any]] = []
    cursor = head.get("receipt_sha256")
    seen: set[str] = set()
    while cursor:
        if cursor in seen:
            raise ReleaseRefused(SEGMENT_PREDICATE,
                                 "ORGANIZATION_LEDGER_CHAIN_CYCLE:" + cursor)
        seen.add(cursor)
        # Addressed through `receipt_key`, which is what wrote the key: a
        # digest carries a `sha256:` prefix the key does not.
        receipt = store.get(receipt_key(cursor))
        if receipt is None:
            raise ReleaseRefused(SEGMENT_PREDICATE,
                                 "ORGANIZATION_LEDGER_RECEIPT_MISSING:" + cursor)
        if receipt.get("schema") != ORGANIZATION_RECEIPT_SCHEMA:
            raise ReleaseRefused(
                SEGMENT_PREDICATE,
                "ORGANIZATION_LEDGER_RECEIPT_SCHEMA_MISMATCH:" + cursor)
        body = {k: v for k, v in receipt.items() if k != "receipt_sha256"}
        if receipt.get("receipt_sha256") != sha(body):
            raise ReleaseRefused(
                SEGMENT_PREDICATE,
                "ORGANIZATION_LEDGER_RECEIPT_HASH_MISMATCH:" + cursor)
        chain.append(receipt)
        cursor = receipt.get("previous_receipt_sha256")
    chain.reverse()
    return chain


def prior_releases(chain: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Every prior release, in the organization chain's own order.

    Walked over the verified chain rather than a directory listing, because the
    *order* matters here: the next release's predecessor is the batch digest of
    the one before it, and a listing would answer in whatever order the store
    happened to enumerate.
    """
    releases: list[dict[str, Any]] = []
    for receipt in chain:
        evidence = receipt.get("boundary_evidence")
        if not isinstance(evidence, Mapping):
            continue
        if evidence.get("operation") != RELEASE_CLASS:
            continue
        releases.append({
            "batch_sha256": evidence.get("batch_sha256"),
            "released_organization_receipts":
                list(evidence.get("released_organization_receipts") or ()),
            "organization_receipt_sha256": receipt.get("receipt_sha256"),
        })
    return releases


def already_released(chain: list[dict[str, Any]]) -> set[str]:
    """The organization receipts a prior release already carried.

    Read off the chain rather than remembered, so exactly-once survives a lost
    file, a fresh process, and a second node holding the same ledger.
    """
    carried: set[str] = set()
    for release_entry in prior_releases(chain):
        for digest in release_entry["released_organization_receipts"]:
            if isinstance(digest, str) and digest:
                carried.add(digest)
    return carried


def release_predecessor(chain: list[dict[str, Any]]) -> str:
    """The batch digest this release chains onto, or the named genesis absence.

    Lexicographic order over receipt digests would be meaningless here -- a
    digest sorts by its bytes, not by when it was written -- so the predecessor
    is the last prior release in chain order.
    """
    releases = prior_releases(chain)
    for entry in reversed(releases):
        digest = entry["batch_sha256"]
        if isinstance(digest, str) and digest:
            return digest
    if releases:
        # A prior release exists and recorded no batch digest. Chaining onto the
        # genesis absence would claim this is the first release, which it is not.
        raise ReleaseRefused(
            SEGMENT_PREDICATE,
            "A_PRIOR_RELEASE_RECORDED_NO_BATCH_DIGEST_SO_THIS_RELEASE_HAS_NO_PREDECESSOR")
    return sha({"state": NO_PRIOR_RELEASE})


def verified_segment() -> dict[str, Any]:
    """The contiguous, verified, not-yet-released tail of the organization chain."""
    chain = organization_chain()
    carried = already_released(chain)
    segment = [r for r in chain if r["receipt_sha256"] not in carried]
    return {
        "release_predecessor": release_predecessor(chain),
        "organization_chain_length": len(chain),
        "already_released": len(chain) - len(segment),
        "segment": segment,
        "segment_length": len(segment),
        "every_receipt_verified_against_its_own_body": True,
        "segment_is_contiguous_tail_of_the_organization_chain": True,
    }


# ----------------------------------------- the organization record destination

def organization_record_destination(root: Path | None = None) -> dict[str, Any]:
    """Resolve the target's declared organization record service, or refuse.

    The contract names the target repository. The federation directory is where
    a peer's addressable services are recorded -- and recorded is the operative
    word: the directory row says *where the peer declares the service in its own
    registry*, so this organization never declares a service on another's
    behalf. A row with no organization record service is not a row to improvise
    against.
    """
    declared = contract()
    target = declared.get("propagation_target")
    if not isinstance(target, str) or not target:
        raise ReleaseRefused(
            TARGET_PREDICATE,
            "THE_ORGANIZATION_LEDGER_CONTRACT_DECLARES_NO_PROPAGATION_TARGET")

    organization = target.split("/", 1)[0]
    federation = ((root or ROOT) / "org-boundary/registry/federation.json"
                  if root is not None else FEDERATION)
    directory = json.loads(federation.read_text(encoding="utf-8"))
    rows = [row for row in directory.get("organizations", [])
            if row.get("organization") == organization]
    if not rows:
        raise ReleaseRefused(
            TARGET_PREDICATE,
            "PROPAGATION_TARGET_NOT_DECLARED_IN_FEDERATION_DIRECTORY:" + organization)
    row = rows[0]
    if row.get("repository") != target:
        raise ReleaseRefused(
            TARGET_PREDICATE,
            "FEDERATION_ROW_REPOSITORY_DOES_NOT_MATCH_THE_PROPAGATION_TARGET:"
            + str(row.get("repository")) + "!=" + target)

    service = row.get("addressed_service")
    if not isinstance(service, str) or not service:
        # The honest refusal. `org_control_service` exists on this row and would
        # accept a crossing, which is exactly why it must not be used: the
        # control plane is not an organization record service, and reaching for
        # the service that happens to exist is how a boundary ends up addressing
        # by identity instead of by what the manifest declared.
        raise ReleaseRefused(
            RECORD_SERVICE_PREDICATE,
            "ORGANIZATION_RECORD_SERVICE_NOT_DECLARED_FOR_" + organization
            + "_THE_ROW_DECLARES_ONLY_"
            + str(row.get("org_control_service")))
    if row.get("serves_an_organization_control_service") is not False:
        raise ReleaseRefused(
            RECORD_SERVICE_PREDICATE,
            "ORGANIZATION_RECORD_SERVICE_ROW_DOES_NOT_DISTINGUISH_ITSELF_"
            "FROM_THE_CONTROL_SERVICE:"
            + service)
    where = row.get("peer_declares_this_in_its_own_registry")
    if not isinstance(where, str) or not where:
        raise ReleaseRefused(
            RECORD_SERVICE_PREDICATE,
            "ORGANIZATION_RECORD_SERVICE_DOES_NOT_RECORD_WHERE_THE_PEER_DECLARES_IT:"
            + service)

    return {
        "propagation_target": target,
        "record_organization": organization,
        "record_service": service,
        "peer_declares_this_in_its_own_registry": where,
        "destination_resolution_source": "FEDERATION_DIRECTORY_ROW",
    }


# ----------------------------------------------------------------- the release

def release_record(segment: Mapping[str, Any], predecessor: str) -> dict[str, Any]:
    digests = [r["receipt_sha256"] for r in segment["segment"]]
    return {
        "schema": BATCH_SCHEMA,
        "organization": contract()["organization"],
        "intended_action": RELEASE_CLASS,
        "disposition": ALLOW,
        "release_predecessor_required": RELEASE_PREDECESSOR_REQUIRED,
        "release_predecessor": predecessor,
        "released_organization_receipts": digests,
        "released_count": len(digests),
        "batch_sha256": sha({"released_organization_receipts": digests,
                             "release_predecessor": predecessor}),
        "first_released_receipt_sha256": digests[0] if digests else None,
        "last_released_receipt_sha256": digests[-1] if digests else None,
        "every_receipt_verified_against_its_own_body": True,
        "segment_is_contiguous_tail_of_the_organization_chain": True,
        "recorder_role": RECORDER_ROLE,
        # Restated on the record itself, because a batch travelling to a
        # recorder is exactly where an authority claim would be inferred.
        "recorder_holds_transition_authority": False,
        "recorder_is_this_organizations_runtime_reality_authority": False,
        "recorder_may_gate_organization_runtime_reality": False,
        "release_is_real_at_the_organization_ledger": True,
        "release_awaits_the_recorder": False,
        "authority_effect": "NONE",
    }


def _record(transition_id: str, transition_class: str, predecessor: str,
            successor: str, record: Mapping[str, Any],
            hb_epoch: int | None) -> dict[str, Any]:
    """Append at both levels: the repository first, the organization consuming it.

    The same shape the egress boundary uses. The release is a state transition
    occurring within this organization, so `organization_scope_rule` requires it
    to emit an organization receipt like any other -- a batch release that left
    no organization receipt would be the one transition here that the ledger
    could not replay.
    """
    # Resumable (B-P36q): a retry after a fault part-way through returns the
    # repository receipt already recorded for this exact transition, and the
    # organization append returns the receipt already consuming it, so the
    # pair completes exactly once.
    repository_receipt = repository_ledger.append(
        transition_id, transition_class, predecessor, successor,
        dict(record), "NONE", hb_epoch=hb_epoch, idempotent_on=())
    organization_receipt = organization_ledger.append(
        repository_receipt, "REPO_STATE_PROPAGATION", predecessor, successor,
        {"operation": transition_class,
         "intended_action": record["intended_action"],
         "disposition": record["disposition"],
         "released_organization_receipts":
             record.get("released_organization_receipts", []),
         "batch_sha256": record.get("batch_sha256"),
         "crossed_an_organization_boundary": False},
        "NONE", hb_epoch=hb_epoch, idempotent=True)
    return {"repository_receipt": repository_receipt,
            "organization_receipt": organization_receipt}


def release(*, hb_epoch: int | None = None) -> dict[str, Any]:
    """Verify and release the organization chain's unreleased tail.

    Returns with the release final. Nothing in this function consults the
    recorder, and no later submission can undo what it appended.
    """
    segment = verified_segment()
    if not segment["segment"]:
        # Nothing to release is not a failure and not an empty batch: an empty
        # batch receipt would assert a handover that did not happen.
        return {
            "schema": RESULT_SCHEMA,
            "operation": RELEASE_CLASS,
            "disposition": ALLOW,
            "released": False,
            "reason": "NO_UNRELEASED_ORGANIZATION_RECEIPTS",
            **{k: v for k, v in segment.items() if k != "segment"},
            "authority_effect": "NONE_RELEASE_RECORD_ONLY",
        }

    predecessor = segment["release_predecessor"]
    record = release_record(segment, predecessor)
    appended = _record(RELEASE_CLASS + ":" + record["batch_sha256"][:24],
                       RELEASE_CLASS, predecessor, record["batch_sha256"],
                       record, hb_epoch)
    return {
        "schema": RESULT_SCHEMA,
        "operation": RELEASE_CLASS,
        "disposition": ALLOW,
        "released": True,
        "batch_sha256": record["batch_sha256"],
        "released_count": record["released_count"],
        "release_predecessor": predecessor,
        "release_record": record,
        "release_repository_receipt_sha256":
            appended["repository_receipt"]["receipt_sha256"],
        "release_organization_receipt_sha256":
            appended["organization_receipt"]["receipt_sha256"],
        **{k: v for k, v in segment.items() if k != "segment"},
        "authority_effect": "NONE_RELEASE_RECORD_ONLY",
    }


# -------------------------------------------------------------- the submission

def submission_refusal_record(failed_predicate: str, reason: str,
                              batch_sha256: Any) -> dict[str, Any]:
    return {
        "schema": BATCH_SCHEMA,
        "organization": contract()["organization"],
        "intended_action": SUBMIT_CLASS,
        "disposition": DENY,
        "failed_predicate": failed_predicate,
        "reason": reason,
        "batch_sha256": batch_sha256,
        "released_organization_receipts": [],
        # The three statements that keep a refused submission from reading as
        # either a lost batch or a pending one.
        "release_stands": True,
        "refused_immediately_at_this_organization": True,
        "awaits_an_external_machine": False,
        "queued_against_a_future_declaration": False,
        "absence_is_not_a_transition": True,
        "unrecorded_batch_is_evidence_state_not_a_blocker": True,
        "unrecorded_batch_is_proof_of_non_occurrence": False,
        "authority_effect": "NONE",
    }


def submit(batch_sha256: str, released: list[str], *,
           standing: Mapping[str, Any],
           root: Path | None = None, mesh_root: Path | None = None,
           hb_epoch: int | None = None) -> dict[str, Any]:
    """Hand a released batch to the declared organization record service, or refuse.

    The crossing goes through the recorded egress boundary rather than a private
    path, so a submission is subject to the same standing gate, closability
    refusal and receipt chain as every other crossing this organization makes.
    """
    try:
        destination = organization_record_destination(root=root)
    except ReleaseRefused as refused:
        record = submission_refusal_record(refused.failed_predicate,
                                          refused.reason, batch_sha256)
        appended = _record(SUBMIT_REFUSED_CLASS + ":" + sha(record)[:24],
                           SUBMIT_REFUSED_CLASS, str(batch_sha256),
                           sha(record), record, hb_epoch)
        return {
            "schema": RESULT_SCHEMA,
            "operation": SUBMIT_CLASS,
            "disposition": DENY,
            "submitted": False,
            "failed_predicate": refused.failed_predicate,
            "reason": refused.reason,
            "batch_sha256": batch_sha256,
            "release_stands": True,
            "awaits_an_external_machine": False,
            "submission_refusal_record": record,
            "submission_repository_receipt_sha256":
                appended["repository_receipt"]["receipt_sha256"],
            "submission_organization_receipt_sha256":
                appended["organization_receipt"]["receipt_sha256"],
            "authority_effect": "NONE_SUBMISSION_RECORD_ONLY",
        }

    payload = {
        # An organization record handover is a communication to the recorder,
        # carrying the batch and closable by the recorder's acknowledgement of it.
        #
        # The kernel's `RESPONDED_REQUEST_CLASSES` was deliberately NOT extended
        # with a record-handover class. That map does double duty: it is the set
        # a crossing may declare to be closable, and it is the set
        # `consume_and_respond` answers. Adding a record-handover class would
        # therefore make *this* organization acknowledge an inbound record
        # request -- claiming to be a recorder it is not. The specificity the class would
        # have carried is in `operation` instead, and under
        # SDK-GENERIC-MANIFEST-ECOSYSTEM-INVARIANT-005 it is the declared
        # capability that selects processing anyway, never the message class.
        #
        # `subject`, `operation` and the `communication_id` prefix below are wire
        # names carried across to the recorder. They are a cross-repository
        # contract, left as they stand until the rename is coordinated there.
        #
        # Closable is not awaited. `emit` returns as soon as the frame is
        # published; closure is a separate transition that may never occur, and
        # a batch the recorder has not acknowledged is a value in evidence
        # state, not a blocker and not proof of non-occurrence.
        "message_class": "ecosystem.communication",
        "communication_id": "custody-" + str(batch_sha256).split(":", 1)[-1][:24],
        "subject": "CUSTODY_RELEASED_ORGANIZATION_BATCH",
        "requested_action": None,
        "audience": "ORIGIN",
        "target_organization": destination["record_organization"],
        "target_count": 1,
        "operation": "CUSTODY_RELEASED_ORGANIZATION_BATCH",
        "batch_sha256": batch_sha256,
        "released_organization_receipts": list(released),
        "released_count": len(released),
        "release_predecessor_required": RELEASE_PREDECESSOR_REQUIRED,
        "recorder_role": RECORDER_ROLE,
        "recorder_holds_transition_authority": False,
        "recorder_may_gate_organization_runtime_reality": False,
        "authority_transfer": False,
    }
    result = egress.emit(destination["record_organization"], payload,
                         standing=standing, root=root, mesh_root=mesh_root,
                         hb_epoch=hb_epoch)

    # The organization record service is resolved twice -- here, to decide whether a batch
    # may be addressed at all, and inside the boundary, to address it. Two
    # resolvers reading one directory should agree, and the one failure that
    # would matter is silent: the boundary falling back to the control service
    # while this module believed it had refused that. So the agreement is
    # checked rather than assumed.
    addressed = result.get("destination_service")
    if result.get("emitted") and addressed != destination["record_service"]:
        raise ReleaseRefused(
            RECORD_SERVICE_PREDICATE,
            "THE_BOUNDARY_ADDRESSED_" + str(addressed)
            + "_BUT_THE_DECLARED_ORGANIZATION_RECORD_SERVICE_IS_"
            + destination["record_service"])
    return {
        "schema": RESULT_SCHEMA,
        "operation": SUBMIT_CLASS,
        "disposition": result.get("disposition"),
        "submitted": bool(result.get("emitted")),
        "batch_sha256": batch_sha256,
        **destination,
        "release_stands": True,
        "awaits_an_external_machine": False,
        "emission": result,
        "authority_effect": "NONE_SUBMISSION_RECORD_ONLY",
    }


def release_and_submit(*, standing: Mapping[str, Any],
                       root: Path | None = None, mesh_root: Path | None = None,
                       hb_epoch: int | None = None) -> dict[str, Any]:
    """Release, then submit. The second result never changes the first."""
    released = release(hb_epoch=hb_epoch)
    if not released.get("released"):
        return {"release": released, "submission": None,
                "authority_effect": "NONE_RELEASE_RECORD_ONLY"}
    submission = submit(released["batch_sha256"],
                        released["release_record"]["released_organization_receipts"],
                        standing=standing, root=root, mesh_root=mesh_root,
                        hb_epoch=hb_epoch)
    return {"release": released, "submission": submission,
            "release_is_final_regardless_of_the_submission": True,
            "authority_effect": "NONE_RELEASE_RECORD_ONLY"}


#: Releasing writes receipts, so the CLI's epoch is refused six-field FAIL_CLOSED
#: before it runs. Reporting the segment writes nothing and needs none.
EPOCH_RETRY_ENTRYPOINT = "resident-runtime/release_organization_batch.py --hb-epoch"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Release a verified organization receipt-chain segment "
                    "as an organization record.")
    parser.add_argument("--standing", type=Path, default=None,
                        help="JSON file declaring mode, node_ref and the predecessor key; "
                             "required to submit, unused by --release-only")
    parser.add_argument("--release-only", action="store_true",
                        help="release against this organization's ledger and stop")
    parser.add_argument("--segment", action="store_true",
                        help="report the unreleased verified segment without releasing")
    # Taken as the raw string: an int() here would read "+33" or " 33" as 33
    # before the kernel's shared rule could refuse it.
    parser.add_argument("--hb-epoch", default=None,
                        help="supplied heartbeat epoch (ASCII digits, >= 32); refused FAIL_CLOSED "
                             "when absent, never read from a clock; unused by --segment")
    parser.add_argument("--out", type=Path, default=None)
    args = parser.parse_args()

    if not args.segment:
        refusal = organization_ledger.kernel.writer_epoch_refusal(
            args.hb_epoch, retry_entrypoint=EPOCH_RETRY_ENTRYPOINT)
        if refusal is not None:
            print(json.dumps(refusal, sort_keys=True))
            return 1
    try:
        if args.segment:
            result = {k: v for k, v in verified_segment().items() if k != "segment"}
        elif args.release_only:
            result = release(hb_epoch=args.hb_epoch)
        else:
            if args.standing is None:
                raise SystemExit(
                    "--standing is required to submit; standing is declared, never derived")
            standing = json.loads(args.standing.read_text(encoding="utf-8"))
            if not isinstance(standing, dict) or "predecessor" not in standing:
                raise SystemExit(
                    "standing must declare the predecessor key; null is explicit genesis")
            result = release_and_submit(standing=standing, hb_epoch=args.hb_epoch)
    except ReleaseRefused as refused:
        print(json.dumps({"disposition": DENY,
                          "failed_predicate": refused.failed_predicate,
                          "reason": refused.reason}, sort_keys=True))
        return 1

    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(rendered)
    print(rendered)
    return 0


if __name__ == "__main__":
    sys.exit(main())
