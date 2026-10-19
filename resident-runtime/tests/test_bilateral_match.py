#!/usr/bin/env python3
"""Prove the bilateral match: corroborate a claimed origin against its own chain.

Recomputing a far-side receipt chain proves a boundary ran the packet, not whose
boundary it was -- every input is held by the recomputing side. The other half
is the claimed origin's own ledger holding an emission receipt for that packet
id, addressed here. A forged origin cannot produce that, because it cannot write
the claimed organization's chain.

Nothing in this ecosystem served that half, so the gap was recorded everywhere
and closed nowhere. These cases prove both halves here: this organization
answers a disclosure about its own chain, and asks one of a peer.

Two organizations run in one process, so each must have its own chain. The
ledger roots are already per-repository and per-organization when no override is
set, so the overrides are cleared and XDG_STATE_HOME is pointed at a scratch
directory. Setting STEGVERSE_REPO_LEDGER_ROOT instead would give both
organizations one store, and the forged case would pass by accident.
"""
import atexit, importlib.util, json, os, shutil, sys, tempfile
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
_STATE = tempfile.mkdtemp()
os.environ["XDG_STATE_HOME"] = _STATE
os.environ.pop("STEGVERSE_REPO_LEDGER_ROOT", None)
os.environ.pop("STEGVERSE_ORG_LEDGER_ROOT", None)

# Consuming a frame marks it seen under this tree. A frame built from a supplied
# epoch has the same name on every run, so a marker left behind would make the
# next run skip the round trip's frame. The markers this run adds are removed.
_SEEN = TREE / "resident-runtime/federation/seen.d"
_SEEN_BEFORE = set(_SEEN.glob("*.json")) if _SEEN.exists() else set()


@atexit.register
def _forget_seen_markers():
    for path in (set(_SEEN.glob("*.json")) if _SEEN.exists() else set()) - _SEEN_BEFORE:
        path.unlink()

#: A peer this organization's own directory already declares, so the crossing
#: resolves without editing the real directory for a test. The identity is real
#: and the tree is synthetic: this is what that peer would be if it served a
#: disclosure. The final case removes the surface, which is that peer today.
PEER = "StegVerse-Labs"
PEER_SLUG = "stegverse-labs"
PEER_SERVICE = PEER_SLUG + ".org-control"
STANDING = {"mode": "ESTABLISH_GENESIS", "node_ref": "bilateral-test", "predecessor": None}


def load(name, relative, root=TREE):
    spec = importlib.util.spec_from_file_location(name, Path(root) / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


K = load("kernel", "org-kernel/kernel.py")
D = load("disclosure", "org-boundary/runtime/emission_chain_disclosure.py")
E = load("egress", "resident-runtime/organization_egress_boundary.py")
HERE = K.load_registry(TREE)["organization"]


def peer_tree(base):
    """A full peer root: this organization's modules under the peer's identity.

    Copied rather than stubbed. The peer must really emit, really append to its
    own chain, and really answer from it; a stub that returned the answer the
    match wants would prove nothing about the match.
    """
    root = Path(base) / "peer-tree"
    shutil.copytree(TREE, root, ignore=shutil.ignore_patterns(
        ".git", "__pycache__", "federation", "*.pyc"))
    (root / "org-boundary/registry/services.json").write_text(json.dumps({
        "schema_version": "peer.service-registry.v1",
        "organization": PEER,
        "services": [{"service_id": PEER_SERVICE, "repository": PEER + "/.github",
                      "boundary_role": "BOUNDARY_LOCAL_CONTROL",
                      "accepts": list(K.RESPONDED_REQUEST_CLASSES)}]}))
    contract = json.loads((root / ".stegverse/transition-ledger/contract.json").read_text())
    contract["repository"] = PEER + "/.github"
    (root / ".stegverse/transition-ledger/contract.json").write_text(json.dumps(contract))
    org_contract = json.loads((root / ".stegverse/transition-ledger/org-contract.json").read_text())
    org_contract["organization"] = PEER
    (root / ".stegverse/transition-ledger/org-contract.json").write_text(json.dumps(org_contract))
    # The copied directory already declares this organization, so the peer can
    # address a crossing back without the row count changing.
    directory = json.loads((root / "org-boundary/registry/federation.json").read_text())
    assert any(row["organization"] == HERE for row in directory["organizations"]), \
        "the peer directory must declare this organization"
    return root


# ------------------------------------------------- the serving half, directly
with tempfile.TemporaryDirectory() as td:
    # No chain at all is not a denial that the receipt exists.
    bare = Path(td) / "bare"
    (bare / "org-boundary/registry").mkdir(parents=True)
    (bare / "org-boundary/registry/services.json").write_text(
        json.dumps({"organization": "Bare-Org", "services": []}))
    answer = D.disclose(bare, "pkt-anything", HERE)
    assert answer["disposition"] == D.NOT_AVAILABLE, answer
    assert answer["holds_emission_receipt"] is False

    # A packet this chain never emitted is answered no, not unavailable.
    answer = D.disclose(TREE, "pkt-never-emitted-anywhere", HERE)
    assert answer["disposition"] == D.NO_RECORD, answer
    assert answer["holds_emission_receipt"] is False
    assert answer["discloses_payloads"] is False
    assert answer["discloses_other_packets"] is False

    # A blank ask is answered unavailable rather than searched for.
    assert D.disclose(TREE, "   ", HERE)["disposition"] == D.NOT_AVAILABLE
    assert D.disclose(TREE, None, HERE)["disposition"] == D.NOT_AVAILABLE
print("DISCLOSURE_SERVING_HALF_PASS")


# ------------------------------------------------- the asking half, directly
GOOD = {"schema": D.DISCLOSURE_SCHEMA, "disposition": D.HOLDS,
        "holds_emission_receipt": True, "disclosing_organization": PEER,
        "request_packet_id": "pkt-1", "emission_receipt_sha256": "sha256:" + "a" * 64,
        "recorded_destination_organization": HERE}
ok = D.match(GOOD, packet_id="pkt-1", claimed_origin=PEER, asker=HERE)
assert ok["bilateral_match_satisfied"] is True, ok
assert ok["peer_chain_was_readable"] is True
assert ok["corroborates_the_claimed_origin_against_its_own_chain"] is True
# A satisfied match does not make standing authenticated or origin attested.
assert ok["makes_standing_authenticated"] is False
assert ok["makes_origin_attested_by_the_credential_authority"] is False

for bad, expect in (
    (None, "PEER_SERVED_NO_DISCLOSURE"),
    ({**GOOD, "disposition": D.NOT_AVAILABLE}, "PEER_COULD_NOT_CONSULT_ITS_CHAIN"),
    ({**GOOD, "disposition": D.NO_RECORD, "holds_emission_receipt": False},
     "PEER_CHAIN_HOLDS_NO_EMISSION_RECEIPT_FOR_THIS_PACKET"),
    ({**GOOD, "request_packet_id": "pkt-other"}, "DISCLOSURE_ANSWERS_A_DIFFERENT_PACKET"),
    ({**GOOD, "disclosing_organization": "Someone-Else"},
     "DISCLOSURE_CAME_FROM_A_DIFFERENT_ORGANIZATION"),
    # A receipt recording a crossing addressed elsewhere corroborates that
    # crossing, not this one.
    ({**GOOD, "recorded_destination_organization": "Someone-Else"},
     "PEER_RECORDED_EMITTING_TO_A_DIFFERENT_ORGANIZATION"),
):
    result = D.match(bad, packet_id="pkt-1", claimed_origin=PEER, asker=HERE)
    assert result["bilateral_match_satisfied"] is False, (expect, result)
    assert any(f.startswith(expect) for f in result["bilateral_match_findings"]), \
        (expect, result["bilateral_match_findings"])
print("DISCLOSURE_ASKING_HALF_PASS")


# ------------------------------- the round trip, over the real crossing path
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    peer = peer_tree(td)
    PE = load("peer_egress", "resident-runtime/organization_egress_boundary.py", root=peer)
    PK = load("peer_kernel", "org-kernel/kernel.py", root=peer)
    assert PK.load_registry(peer)["organization"] == PEER

    # The peer really emits a crossing to this organization, recording it on the
    # peer's own chain.
    sent = PE.emit(HERE, {"message_class": "ecosystem.communication",
                          "communication_id": "peer-to-here-001",
                          "subject": "real", "body": {"probe": True},
                          "requested_action": None, "audience": "ORIGIN",
                          "target_organization": HERE, "target_count": 1},
                   standing=STANDING, root=peer, mesh_root=mesh, hb_epoch=6000)
    assert sent["disposition"] == PE.ALLOW, sent
    real_packet = sent["packet_id"]

    # This organization consumes it, then asks the claimed origin whether its
    # own chain records emitting it here.
    served = K.consume_and_respond(TREE, mesh_root=mesh)
    assert any(r["result"]["status"] == "CONSUMED" for r in served), served

    asked = E.request_bilateral_match(PEER, real_packet, standing=STANDING,
                                      root=TREE, mesh_root=mesh, hb_epoch=6001)
    assert asked["disposition"] == E.ALLOW, asked
    comm = asked["bilateral_match_communication_id"]

    # Before the peer answers, the match is PENDING and records nothing.
    pending = E.observe_bilateral_match(PEER, real_packet, comm, root=TREE,
                                        mesh_root=mesh, hb_epoch=6002)
    assert pending["disposition"] == E.PENDING, pending
    assert pending["match_recorded"] is False

    # The peer answers from its own chain.
    PK.consume_and_respond(peer, mesh_root=mesh)
    satisfied = E.observe_bilateral_match(PEER, real_packet, comm, root=TREE,
                                          mesh_root=mesh, hb_epoch=6003)
    assert satisfied["disposition"] == E.ALLOW, satisfied
    assert satisfied["bilateral_match_satisfied"] is True, satisfied
    assert satisfied["bilateral_match_findings"] == []
    assert satisfied["peer_chain_was_readable"] is True
    assert satisfied["match_transition_class"] == E.MATCH_SATISFIED_CLASS
    assert satisfied["match_repository_receipt_sha256"].startswith("sha256:")
    assert satisfied["match_organization_receipt_sha256"].startswith("sha256:")
    disclosed = satisfied["match_record"]["disclosure"]
    assert disclosed["disclosing_organization"] == PEER, disclosed
    assert disclosed["recorded_destination_organization"] == HERE
    assert disclosed["recorded_destination_is_the_asker"] is True
print("BILATERAL_MATCH_ROUND_TRIP_PASS")


# ------------------------------------- a forged origin cannot satisfy the match
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    peer = peer_tree(td)
    PK = load("peer_kernel2", "org-kernel/kernel.py", root=peer)

    # A frame claiming the peer as its origin, which the peer never emitted: any
    # writer of a shared mesh can publish one, which is the whole asker gap.
    forged = K.build_packet(origin_org=PEER, origin_service=PEER_SERVICE,
                            destination_org=HERE,
                            destination_service=K.organization_slug(HERE) + ".org-control",
                            payload={"message_class": "ecosystem.communication",
                                     "communication_id": "forged-001",
                                     "subject": "forged", "body": {},
                                     "requested_action": None, "audience": "ORIGIN",
                                     "target_organization": HERE, "target_count": 1},
                            standing=STANDING)
    K.publish_packet(forged, root=mesh)
    consumed = K.consume_and_respond(TREE, mesh_root=mesh)
    # It is consumed and receipted, exactly as before: the gate is standing, and
    # this packet declares valid standing. That is the point -- consumption was
    # never the question.
    assert any(r["result"]["status"] == "CONSUMED" for r in consumed), consumed

    asked = E.request_bilateral_match(PEER, forged["packet_id"], standing=STANDING,
                                      root=TREE, mesh_root=mesh, hb_epoch=6010)
    comm = asked["bilateral_match_communication_id"]
    PK.consume_and_respond(peer, mesh_root=mesh)
    refused = E.observe_bilateral_match(PEER, forged["packet_id"], comm, root=TREE,
                                        mesh_root=mesh, hb_epoch=6011)
    assert refused["disposition"] == E.DENY, refused
    assert refused["bilateral_match_satisfied"] is False
    assert refused["match_transition_class"] == E.MATCH_REFUSED_CLASS
    assert refused["match_recorded"] is True
    # The peer's chain was readable and said no. That is the distinction the
    # match exists to draw, and it is the forged origin being caught.
    assert refused["peer_chain_was_readable"] is True, refused
    assert any(f.startswith("PEER_CHAIN_HOLDS_NO_EMISSION_RECEIPT_FOR_THIS_PACKET")
               for f in refused["bilateral_match_findings"]), refused["bilateral_match_findings"]
print("FORGED_ORIGIN_REFUSED_PASS")


# ------------------------------ a peer serving no disclosure is a refusal
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    peer = peer_tree(td)
    # Remove the peer's disclosure surface: the state every peer is in today.
    (peer / "org-boundary/runtime/emission_chain_disclosure.py").unlink()
    PK = load("peer_kernel3", "org-kernel/kernel.py", root=peer)

    asked = E.request_bilateral_match(PEER, "pkt-unserved-001", standing=STANDING,
                                      root=TREE, mesh_root=mesh, hb_epoch=6020)
    comm = asked["bilateral_match_communication_id"]
    PK.consume_and_respond(peer, mesh_root=mesh)
    unserved = E.observe_bilateral_match(PEER, "pkt-unserved-001", comm, root=TREE,
                                         mesh_root=mesh, hb_epoch=6021)
    assert unserved["disposition"] == E.DENY, unserved
    assert unserved["bilateral_match_satisfied"] is False
    # Unavailable, not "no": a peer that cannot consult its chain has not
    # declined to hold the receipt.
    assert unserved["peer_chain_was_readable"] is False, unserved
    assert any(f.startswith("PEER_COULD_NOT_CONSULT_ITS_CHAIN")
               for f in unserved["bilateral_match_findings"]), unserved["bilateral_match_findings"]
print("PEER_WITHOUT_DISCLOSURE_REFUSED_PASS")
print("BILATERAL_MATCH_PASS")
