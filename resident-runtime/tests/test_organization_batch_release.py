#!/usr/bin/env python3
"""Prove organization receipts are recorded at the organization level, then batched.

Two acts, and the suite's job is to keep them from collapsing into one:

    recorded at the organization level .... real under the organization ledger
                                            lock, the moment it is appended
    batched to master-records ............. a verified segment this organization
                                            released and handed over

The dangerous failure here is not a missing batch. It is a batch that *gates*:
a release that only counts once a recorder acknowledges it, or a submission
that waits. `master-records` holds custody and no transition authority, so a
submission that cannot be addressed must refuse immediately and leave the
release standing -- an unrecorded batch is a value in evidence state, not a
blocker and not proof of non-occurrence.

Driven against a scratch ledger, so a run never touches the operator's chain.
"""
import importlib.util, json, os, shutil, sys, tempfile
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
_T = tempfile.mkdtemp()
os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(Path(_T) / "repo-ledger")
os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(Path(_T) / "org-ledger")


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, TREE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


B = load("release_organization_batch", "resident-runtime/release_organization_batch.py")
E = load("egress", "resident-runtime/organization_egress_boundary.py")
LS = load("ledger_store", "resident-runtime/ledger_store.py")

STANDING = {"mode": "ESTABLISH_GENESIS", "node_ref": "batch-test-node", "predecessor": None}
PEER = "StegVerse-Labs"


def payload(communication_id):
    return {"message_class": "ecosystem.communication",
            "communication_id": communication_id, "subject": "batch-test",
            "body": {"probe": True}, "requested_action": None,
            "audience": "ORIGIN", "target_organization": PEER, "target_count": 1}


def peer_root(base):
    root = Path(base) / "peer"
    (root / "org-boundary/registry").mkdir(parents=True, exist_ok=True)
    (root / "org-boundary/runtime").mkdir(parents=True, exist_ok=True)
    for module in ("node_standing.py", "manifest_selection.py"):
        shutil.copy2(TREE / "org-boundary/runtime" / module,
                     root / "org-boundary/runtime" / module)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TREE / "docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json",
                 root / "docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json")
    (root / "org-boundary/registry/services.json").write_text(json.dumps({
        "organization": PEER,
        "services": [{"service_id": "stegverse-labs.org-control",
                      "repository": PEER + "/.github",
                      "boundary_role": "BOUNDARY_LOCAL_CONTROL"}]}))
    return root


# -------------------------------------------- an empty chain releases nothing
empty = B.release(hb_epoch=4000)
assert empty["released"] is False, empty
assert empty["reason"] == "NO_UNRELEASED_ORGANIZATION_RECEIPTS"
# Not an empty batch. An empty batch receipt would assert a handover that did
# not happen, which is worse than no receipt at all.
assert "batch_sha256" not in empty
assert empty["release_predecessor"].startswith("sha256:")
print("EMPTY_CHAIN_RELEASES_NOTHING_RATHER_THAN_AN_EMPTY_BATCH=PASS")


# ------------------------------------------------- put real transitions on the chain
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    peer_root(td)
    for index in range(3):
        emitted = E.emit(PEER, payload("batch-emit-%03d" % index), standing=STANDING,
                         root=TREE, mesh_root=mesh, hb_epoch=4100 + index)
        assert emitted["disposition"] == E.ALLOW, emitted

chain = B.organization_chain()
assert len(chain) == 3, [r.get("org_transition_class") for r in chain]
# Chain order is the ledger's own: each receipt names the one before it.
for earlier, later in zip(chain, chain[1:]):
    assert later["previous_receipt_sha256"] == earlier["receipt_sha256"]
print("ORGANIZATION_RECEIPTS_ARE_RECORDED_AT_THE_ORGANIZATION_LEVEL=PASS")


# ----------------------------------------------------------- release the segment
segment = B.verified_segment()
assert segment["segment_length"] == 3, segment
assert segment["already_released"] == 0
assert segment["every_receipt_verified_against_its_own_body"] is True

released = B.release(hb_epoch=4200)
assert released["released"] is True, released
assert released["released_count"] == 3
assert released["batch_sha256"].startswith("sha256:")
record = released["release_record"]
assert record["release_predecessor_required"] == "VERIFIED_ORGANIZATION_RECEIPT_CHAIN_SEGMENT"
assert record["released_organization_receipts"] == [r["receipt_sha256"] for r in chain]
assert record["first_released_receipt_sha256"] == chain[0]["receipt_sha256"]
assert record["last_released_receipt_sha256"] == chain[-1]["receipt_sha256"]

# The three statements that keep a batch from reading as a transfer of authority.
assert record["recorder_role"] == "RELEASED_ORGANIZATION_BATCH_RECEIPT_RECORDER"
assert record["recorder_holds_transition_authority"] is False
assert record["recorder_is_this_organizations_runtime_reality_authority"] is False
assert record["recorder_may_gate_organization_runtime_reality"] is False
assert record["release_is_real_at_the_organization_ledger"] is True
assert record["release_awaits_the_recorder"] is False

# The release is itself a transition in this organization, so it emitted a
# receipt at both levels like every other one.
assert released["release_repository_receipt_sha256"].startswith("sha256:")
assert released["release_organization_receipt_sha256"].startswith("sha256:")
print("RELEASE_IS_A_RECORDED_TRANSITION_AT_BOTH_LEDGER_LEVELS=PASS")


# -------------------------------------------------------- exactly once, by reading
after = B.verified_segment()
assert after["already_released"] == 3, after
assert after["segment_length"] == 1, (
    "the release's own organization receipt is the only unreleased receipt left")
assert after["segment"][0]["receipt_sha256"] == released["release_organization_receipt_sha256"]

second = B.release(hb_epoch=4300)
assert second["released"] is True
assert second["released_count"] == 1, second
assert second["release_predecessor"] == released["batch_sha256"], (
    "the second release must chain onto the first batch's digest, not onto a "
    "sorted receipt digest and not onto the genesis absence")
assert released["batch_sha256"] not in second["release_record"][
    "released_organization_receipts"]

third = B.release(hb_epoch=4400)
assert third["released"] is True and third["released_count"] == 1
# Re-releasing the same receipts would duplicate custody of transitions already
# handed over, so the only thing each later run carries is the prior release.
assert third["release_predecessor"] == second["batch_sha256"]
print("EXACTLY_ONCE_IS_READ_OFF_THE_CHAIN_NOT_REMEMBERED=PASS")


# --------------------------------------- an unverifiable receipt is not released
store = LS.PosixLedgerStore(Path(os.environ["STEGVERSE_ORG_LEDGER_ROOT"]))
victim = chain[1]
key = LS.receipt_key(victim["receipt_sha256"])
original = store.get(key)
tampered = {**original, "org_transition_class": "TAMPERED_AFTER_THE_FACT"}
store.put(key, tampered)
try:
    B.organization_chain()
    raise AssertionError("a receipt whose digest does not match its body was accepted")
except B.ReleaseRefused as refused:
    assert refused.failed_predicate == B.SEGMENT_PREDICATE
    assert "HASH_MISMATCH" in refused.reason
finally:
    store.put(key, original)
assert B.organization_chain(), "the chain must read again once the receipt is restored"
print("AN_UNVERIFIABLE_RECEIPT_REFUSES_THE_WHOLE_SEGMENT=PASS")


# ------------------------------------------- the custody destination is not improvised
try:
    B.custody_destination()
    raise AssertionError("resolved a custody service this organization never declared")
except B.ReleaseRefused as refused:
    assert refused.failed_predicate == B.CUSTODY_PREDICATE, refused.failed_predicate
    assert "CUSTODY_SERVICE_NOT_DECLARED_FOR_master-records" in refused.reason
    # The refusal must name what the row *does* declare, so the reader can see
    # that a control service was available and deliberately not used.
    assert "master-records.org-control" in refused.reason
print("CUSTODY_IS_NOT_ADDRESSED_TO_THE_CONTROL_SERVICE_THAT_HAPPENS_TO_EXIST=PASS")


# ------------------------------------------ a refused submission leaves the release
fourth = B.release(hb_epoch=4500)
if not fourth["released"]:
    fourth = {"batch_sha256": third["batch_sha256"],
              "release_record": third["release_record"]}
submission = B.submit(fourth["batch_sha256"],
                      fourth["release_record"]["released_organization_receipts"],
                      standing=STANDING, hb_epoch=4600)
assert submission["disposition"] == B.DENY, submission
assert submission["submitted"] is False
assert submission["failed_predicate"] == B.CUSTODY_PREDICATE
assert submission["release_stands"] is True
assert submission["awaits_an_external_machine"] is False

refusal = submission["submission_refusal_record"]
assert refusal["refused_immediately_at_this_organization"] is True
assert refusal["queued_against_a_future_declaration"] is False
assert refusal["absence_is_not_a_transition"] is True
assert refusal["unrecorded_batch_is_evidence_state_not_a_blocker"] is True
assert refusal["unrecorded_batch_is_proof_of_non_occurrence"] is False
# The refusal is recorded, not swallowed: a submission that failed silently
# would leave the operator unable to tell it from one never attempted.
assert submission["submission_repository_receipt_sha256"].startswith("sha256:")
assert submission["submission_organization_receipt_sha256"].startswith("sha256:")

# And the batch it carried is still released. This is the invariant that makes
# the recorder non-gating rather than merely described as non-gating.
still = B.prior_releases(B.organization_chain())
assert any(entry["batch_sha256"] == fourth["batch_sha256"] for entry in still), (
    "the refused submission removed the release from the chain")
print("A_REFUSED_SUBMISSION_IS_RECORDED_AND_THE_RELEASE_STANDS=PASS")


# ---------------------------- release_and_submit never lets the second undo the first
combined = B.release_and_submit(standing=STANDING, hb_epoch=4700)
if combined["submission"] is not None:
    assert combined["release"]["released"] is True
    assert combined["release_is_final_regardless_of_the_submission"] is True
    assert combined["submission"]["release_stands"] is True
print("RELEASE_IS_FINAL_REGARDLESS_OF_THE_SUBMISSION=PASS")


# -------------------------- and the submission crosses once the service IS declared
# A submit() proven only able to refuse is indistinguishable from one that is
# broken. This case declares the custody service in a scratch directory and
# requires the batch to actually cross -- addressed at the custody service, not
# at the control service the same row still carries.
CUSTODY_SERVICE = "master-records.ecosystem-transition-ledger"


def tree_root(base):
    """A scratch tree whose federation directory declares a custody service."""
    root = Path(base) / "tree"
    (root / "org-boundary/registry").mkdir(parents=True, exist_ok=True)
    (root / "org-boundary/runtime").mkdir(parents=True, exist_ok=True)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    for module in ("node_standing.py", "manifest_selection.py"):
        shutil.copy2(TREE / "org-boundary/runtime" / module,
                     root / "org-boundary/runtime" / module)
    shutil.copy2(TREE / "docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json",
                 root / "docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json")
    shutil.copy2(TREE / "org-boundary/registry/services.json",
                 root / "org-boundary/registry/services.json")

    directory = json.loads(
        (TREE / "org-boundary/registry/federation.json").read_text(encoding="utf-8"))
    for row in directory["organizations"]:
        if row["organization"] == "master-records":
            # The SV-011 shape: the row records where the peer declares the
            # service in its OWN registry, so this organization is not
            # declaring a service on another's behalf.
            row["addressed_service"] = CUSTODY_SERVICE
            row["addressed_service_role"] = "INTERNAL_ENDPOINT"
            row["serves_an_organization_control_service"] = False
            row["peer_declares_this_in_its_own_registry"] = (
                "master-records/.github:org-boundary/registry/services.json")
    (root / "org-boundary/registry/federation.json").write_text(
        json.dumps(directory, indent=2))
    return root


with tempfile.TemporaryDirectory() as td:
    scratch = tree_root(td)
    mesh = Path(td) / "custody-mesh"

    destination = B.custody_destination(root=scratch)
    assert destination["custody_service"] == CUSTODY_SERVICE, destination
    assert destination["custody_organization"] == "master-records"
    assert destination["propagation_target"] == "master-records/.github"
    assert destination["peer_declares_this_in_its_own_registry"].startswith(
        "master-records/.github:"), (
        "the directory must record where the peer declares the service, not "
        "declare it here")

    crossed = B.release_and_submit(standing=STANDING, root=scratch,
                                   mesh_root=mesh, hb_epoch=4800)
    assert crossed["release"]["released"] is True, crossed["release"]
    outbound = crossed["submission"]
    assert outbound["disposition"] == E.ALLOW, outbound
    assert outbound["submitted"] is True
    assert outbound["custody_service"] == CUSTODY_SERVICE

    emission = outbound["emission"]
    # Addressed at the custody service. The control service is still on the row
    # and is still not what carried the batch.
    assert emission["destination_service"] == CUSTODY_SERVICE, emission
    assert emission["destination_org_control_service"] == "master-records.org-control"
    assert emission["crossed_an_organization_boundary"] is True
    assert emission["emission_organization_receipt_sha256"].startswith("sha256:")

    # The batch travelled, and claimed nothing for the recorder.
    assert outbound["release_stands"] is True
    assert outbound["awaits_an_external_machine"] is False
print("THE_BATCH_CROSSES_TO_THE_DECLARED_CUSTODY_SERVICE=PASS")


# --------------------- the two resolvers must agree, and disagreement is refused
# `submit` resolves the custody service to decide whether a batch may be
# addressed; the boundary resolves it again to address it. They read the same
# directory field, so today they cannot disagree -- which is exactly why the
# guard would rot unnoticed. Forced here, because the failure it prevents is
# silent: the boundary addressing the control service while this module
# believed it had refused that.
with tempfile.TemporaryDirectory() as td:
    scratch = tree_root(td)
    mesh = Path(td) / "drift-mesh"
    genuine = B.custody_destination

    def lying_destination(root=None):
        resolved = genuine(root=root)
        return {**resolved, "custody_service": "master-records.some-other-service"}

    B.custody_destination = lying_destination
    try:
        released_for_drift = B.release(hb_epoch=4900)
        assert released_for_drift["released"] is True
        B.submit(released_for_drift["batch_sha256"],
                 released_for_drift["release_record"]["released_organization_receipts"],
                 standing=STANDING, root=scratch, mesh_root=mesh, hb_epoch=4910)
        raise AssertionError(
            "the boundary addressed a service this module did not resolve, and "
            "the submission reported success anyway")
    except B.ReleaseRefused as refused:
        assert refused.failed_predicate == B.CUSTODY_PREDICATE
        assert "THE_BOUNDARY_ADDRESSED_" in refused.reason
        assert "master-records.ecosystem-transition-ledger" in refused.reason
    finally:
        B.custody_destination = genuine
print("A_RESOLVER_DISAGREEMENT_IS_REFUSED_NOT_ADDRESSED_ANYWAY=PASS")


print()
print("ORGANIZATION_BATCH_RELEASE=PASS")
print("AUTHORITY_EFFECT=NONE_VALIDATION_ONLY")
