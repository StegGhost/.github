#!/usr/bin/env python3
"""Prove this organization can initiate a crossing and record its disposition.

Before this boundary existed, a crossing involving this organization completed
all four reference steps -- but `resolve`, `emit` and `close` were the *peer's*
operations and this organization performed only the consuming step. These cases
drive all four from here.

The far side is this organization's own kernel run against a synthetic peer
root, so the suite needs no second repository checked out beside it. That is
sound for what is being proven: the receipt chain a boundary mints is derived by
the shared `process_boundary` sequence, so recomputing it is the same check
whoever runs it. The cross-organization run against the real `StegVerse-Labs`
head is recorded in docs/ORGANIZATION_EGRESS_BOUNDARY_004.md, which a test in
this repository cannot perform.
"""
import importlib.util, json, os, shutil, sys, tempfile
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
_T = tempfile.mkdtemp()
# Point both ledgers at a scratch root before the boundary appends anything, so
# a test run never writes to the operator's real chain.
os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(Path(_T) / "repo-ledger")
os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(Path(_T) / "org-ledger")


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, TREE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


E = load("egress", "resident-runtime/organization_egress_boundary.py")
K = load("kernel", "org-kernel/kernel.py")

STANDING = {"mode": "ESTABLISH_GENESIS", "node_ref": "egress-test-node", "predecessor": None}
PEER = "StegVerse-Labs"
PEER_SERVICE = "stegverse-labs.org-control"


def peer_root(base):
    """A synthetic root for the far side, carrying the standing surfaces.

    Copied rather than stubbed: a peer root that admits a crossing the real root
    would refuse proves nothing about the crossing.
    """
    root = Path(base) / "peer"
    (root / "org-boundary/registry").mkdir(parents=True, exist_ok=True)
    (root / "org-boundary/runtime").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TREE / "org-boundary/runtime/node_standing.py",
                 root / "org-boundary/runtime/node_standing.py")
    (root / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TREE / "docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json",
                 root / "docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json")
    (root / "org-boundary/registry/services.json").write_text(json.dumps({
        "organization": PEER,
        "services": [{"service_id": PEER_SERVICE, "repository": PEER + "/.github",
                      "boundary_role": "BOUNDARY_LOCAL_CONTROL"}]}))
    return root


def payload(communication_id, message_class="ecosystem.communication"):
    return {"message_class": message_class, "communication_id": communication_id,
            "subject": "egress-test", "body": {"probe": True}, "requested_action": None,
            "audience": "ORIGIN", "target_organization": PEER, "target_count": 1}


# ---------------------------------------------------------------- resolve
resolved = E.resolve_destination(PEER, root=TREE)
assert resolved["disposition"] == E.ALLOW
assert resolved["destination_service"] == PEER_SERVICE
assert resolved["destination_resolved_from_caller_argument"] is False
assert resolved["destination_resolution_source"] == "ORGANIZATION_FEDERATION_DIRECTORY"
# A peer's kernel generation is not readable here, and the record says so
# rather than implying the requirement was checked.
assert resolved["destination_kernel_generation_is_proven_here"] is False
assert resolved["destination_kernel_required_is_checked_at_resolution"] is False

# A peer this organization's directory does not declare cannot be addressed.
try:
    E.resolve_destination("Not-A-Declared-Peer", root=TREE)
    raise AssertionError("resolved an organization the directory does not declare")
except E.EgressRefused as refused:
    assert refused.failed_predicate == "DESTINATION_IS_A_DECLARED_PEER_OF_THIS_ORGANIZATION"
print("RESOLVE_PASS")


# ---------------------------------------------------------------- emit
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    far = peer_root(td)
    comm = "egress-emit-001"

    emitted = E.emit(PEER, payload(comm), standing=STANDING, root=TREE,
                     mesh_root=mesh, hb_epoch=5000)
    assert emitted["disposition"] == E.ALLOW, emitted
    assert emitted["emitted"] is True
    assert emitted["destination_service"] == PEER_SERVICE
    # Both ledger levels recorded the crossing, repository first.
    assert emitted["emission_repository_receipt_sha256"].startswith("sha256:")
    assert emitted["emission_organization_receipt_sha256"].startswith("sha256:")
    record = emitted["emission_record"]
    assert record["intended_action"] == E.INTENDED_ACTION_EMIT
    assert record["crossed_an_organization_boundary"] is True
    assert record["standing_mode"] == "ESTABLISH_GENESIS"
    assert record["node_standing_disposition"] == "ALLOW"
    assert record["standing_node_ref"] == "egress-test-node"
    assert record["standing_generation"] == 1
    assert record["standing_resolved_through_this_organizations_ingress_contract"] is True
    # Standing admitted is not origin authenticated, and the record says so.
    assert record["structural_standing_is_authenticated_standing"] is False
    # Origin is asserted, and this organization has no path to attesting it.
    assert record["origin_attestation_state"] == "NOT_PROVEN"
    assert record["origin_is_attested_by_the_credential_authority"] is False
    assert record["attestation_is_unavailable_at_this_organization"] is True
    assert record["attestation_was_attempted"] is False
    # The record carries the two inputs closure recomputes the far side from.
    assert record["far_side_service_id"] == PEER_SERVICE
    assert record["far_side_payload_hash"] == K.sha(payload(comm))
    packet_id = emitted["packet_id"]
print("EMIT_PASS")


# ------------------------------------------------- emit refuses, and records it
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"

    # A class the profile answers with nothing could be consumed and never
    # closed, so it is refused before anything is published.
    unclosable = E.emit(PEER, payload("egress-unclosable-001", "ecosystem.status.query"),
                        standing=STANDING, root=TREE, mesh_root=mesh, hb_epoch=5000)
    assert unclosable["disposition"] == E.DENY, unclosable
    assert unclosable["emitted"] is False
    assert unclosable["failed_predicate"] == "PAYLOAD_DECLARES_A_REQUEST_CLASS_THE_BOUNDARY_ANSWERS"
    # A refusal is a transition too: it is recorded, at both levels.
    assert unclosable["refusal_recorded"] is True
    assert unclosable["emission_transition_class"] == E.EMIT_REFUSED_CLASS
    assert unclosable["emission_record"]["nothing_crossed_the_boundary"] is True
    assert unclosable["emission_record"]["crossed_an_organization_boundary"] is False
    assert unclosable["emission_repository_receipt_sha256"].startswith("sha256:")
    assert unclosable["emission_organization_receipt_sha256"].startswith("sha256:")
    # Nothing was published.
    assert not (mesh / "frames.d").exists(), "a refused crossing published a frame"

    # A blank communication_id leaves closure nothing to correlate on.
    blank = E.emit(PEER, payload("   "), standing=STANDING, root=TREE,
                   mesh_root=mesh, hb_epoch=5000)
    assert blank["disposition"] == E.DENY
    assert blank["failed_predicate"] == "PAYLOAD_CARRIES_THE_COMMUNICATION_ID_CLOSURE_CORRELATES_ON"

    # An undeclared peer is refused and recorded, not sent hopefully.
    stranger = E.emit("Not-A-Declared-Peer", payload("egress-stranger-001"),
                      standing=STANDING, root=TREE, mesh_root=mesh, hb_epoch=5000)
    assert stranger["disposition"] == E.DENY
    assert stranger["failed_predicate"] == "DESTINATION_IS_A_DECLARED_PEER_OF_THIS_ORGANIZATION"

    # An empty standing declaration is buildable by the kernel's constructor and
    # would be refused fail-closed at the far side's ingress -- a crossing
    # emitted that can never close. This boundary resolves standing through its
    # own ingress contract first, so it is refused here and recorded.
    for bad, why in (({}, "empty"),
                     ({"mode": "ESTABLISH_GENESIS", "node_ref": "n"}, "no predecessor key"),
                     ({"mode": "NOT-A-MODE", "node_ref": "n", "predecessor": None}, "unknown mode")):
        refused = E.emit(PEER, payload("egress-standing-" + why.replace(" ", "-")),
                         standing=bad, root=TREE, mesh_root=mesh, hb_epoch=5000)
        assert refused["disposition"] == E.DENY, (why, refused)
        assert refused["failed_predicate"] == \
            "STANDING_DECLARATION_THIS_ORGANIZATIONS_OWN_INGRESS_WOULD_ADMIT", (why, refused)
        assert refused["refusal_recorded"] is True
        # The refusal carries the contract's own disposition name.
        assert "node-standing-" in refused["detail"], (why, refused["detail"])
    assert not (mesh / "frames.d").exists(), "a refused crossing published a frame"
print("EMIT_REFUSAL_PASS")


# ---------------------------------------------------------------- close
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    far = peer_root(td)
    comm = "egress-close-001"

    emitted = E.emit(PEER, payload(comm), standing=STANDING, root=TREE,
                     mesh_root=mesh, hb_epoch=5000)
    assert emitted["disposition"] == E.ALLOW
    packet_id = emitted["packet_id"]

    # Before the far side answers, closure is PENDING and records nothing. An
    # absence is not a transition.
    pending = E.close(PEER, packet_id, comm, root=TREE, mesh_root=mesh, hb_epoch=5001)
    assert pending["disposition"] == E.PENDING, pending
    assert pending["closed"] is False
    assert pending["closure_recorded"] is False
    assert pending["absence_is_not_a_transition"] is True

    # The far side consumes and answers.
    served = K.consume_and_respond(far, mesh_root=mesh)
    assert [row["result"]["status"] for row in served] == ["CONSUMED"], served
    far_terminal = served[0]["result"]["execution_result"]["reconstruction"]["terminal_receipt_id"]
    assert served[0]["response_publication"] is not None

    closed = E.close(PEER, packet_id, comm, root=TREE, mesh_root=mesh, hb_epoch=5002)
    assert closed["disposition"] == E.ALLOW, closed
    assert closed["closed"] is True
    assert closed["closure_findings"] == []
    assert closed["closure_transition_class"] == E.CLOSED_CLASS
    assert closed["closure_repository_receipt_sha256"].startswith("sha256:")
    assert closed["closure_organization_receipt_sha256"].startswith("sha256:")
    # Recomputed from this organization's own emission record, and matching what
    # the far side actually minted.
    assert closed["far_side_terminal_receipt"] == closed["far_side_terminal_receipt_recomputed"]
    assert closed["far_side_terminal_receipt"] == far_terminal
    crecord = closed["closure_record"]
    assert crecord["far_side_terminal_receipt_matches_recomputation"] is True
    assert crecord["reconstruction_proves_the_boundary_ran_this_packet"] is True
    # What the recomputation does not establish, stated rather than left open.
    assert crecord["reconstruction_proves_who_the_far_side_is"] is False
    assert crecord["reconstruction_proves_the_far_side_persisted_its_chain"] is False
    assert crecord["bilateral_match_requires_the_far_side_chain_to_be_readable"] is True
print("CLOSE_PASS")


# ------------------------------------------- close refuses what does not verify
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    far = peer_root(td)
    comm = "egress-forged-001"

    emitted = E.emit(PEER, payload(comm), standing=STANDING, root=TREE,
                     mesh_root=mesh, hb_epoch=5000)
    packet_id = emitted["packet_id"]
    K.consume_and_respond(far, mesh_root=mesh)

    # Forge the terminal receipt the response carries.
    import base64
    for path in sorted((mesh / "frames.d").glob("*.json")):
        frame = json.loads(path.read_text())
        if frame["destination_org"] != E.this_organization(TREE):
            continue
        pkt = K.recover_packet(frame)
        pkt["payload"]["body"]["receipt_terminal"] = "egress_emitted-" + ("0" * 24)
        raw = K.canon(pkt)
        body = {k: v for k, v in frame.items() if k != "frame_sha256"}
        body["packet_base64"] = base64.b64encode(raw).decode("ascii")
        body["packet_sha256"] = K.sha(raw)
        path.write_text(json.dumps({**body, "frame_sha256": K.sha(body)},
                                   indent=2, sort_keys=True) + "\n")

    refused = E.close(PEER, packet_id, comm, root=TREE, mesh_root=mesh, hb_epoch=5003)
    assert refused["disposition"] == E.DENY, refused
    assert refused["closed"] is False
    assert refused["closure_recorded"] is True
    assert refused["closure_transition_class"] == E.CLOSURE_REFUSED_CLASS
    assert any(f.startswith("FAR_SIDE_TERMINAL_RECEIPT_DOES_NOT_RECOMPUTE")
               for f in refused["closure_findings"]), refused["closure_findings"]
    assert refused["closure_record"]["reconstruction_proves_the_boundary_ran_this_packet"] is False

    # A crossing this organization has no emission record for cannot be closed,
    # whatever the response asserts about it.
    unknown = E.close(PEER, "pkt-never-emitted-here", comm, root=TREE,
                      mesh_root=mesh, hb_epoch=5004)
    assert unknown["disposition"] == E.DENY, unknown
    assert any("NO_EMISSION_RECORD" in f or "ANSWERS_A_DIFFERENT_PACKET" in f
               for f in unknown["closure_findings"]), unknown["closure_findings"]
print("CLOSE_REFUSAL_PASS")


# ------------------------------------------------- the chain holds both halves
store = load("ledger_store", "resident-runtime/ledger_store.py")
repo_ledger = load("repo_emit", ".stegverse/transition-ledger/emit.py")
s = store.PosixLedgerStore(repo_ledger.lr())
head = s.get(store.HEAD_KEY)
cursor = (head or {}).get("receipt_sha256")
classes = []
while cursor:
    receipt = s.get(store.receipt_key(cursor))
    if receipt is None:
        break
    classes.append(receipt["transition_class"])
    cursor = receipt.get("previous_receipt_sha256")
# Every disposition this suite produced is on the chain, each under its own
# class, so no reader can mistake a refusal for a crossing that left.
for required in (E.EMITTED_CLASS, E.EMIT_REFUSED_CLASS, E.CLOSED_CLASS,
                 E.CLOSURE_REFUSED_CLASS):
    assert required in classes, (required, classes)
print("LEDGER_CHAIN_PASS")
print("ORGANIZATION_EGRESS_BOUNDARY_PASS")
