#!/usr/bin/env python3
import importlib.util, json, shutil, tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location("kernel","org-kernel/kernel.py"); k=importlib.util.module_from_spec(spec); spec.loader.exec_module(k)

TREE=Path("org-kernel/kernel.py").resolve().parents[1]
CONTRACT="docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json"
#: A synthetic root is a dispatch root like any other, so it has to carry the
#: standing surfaces the kernel resolves from it. Copied rather than stubbed:
#: a test root that admits a crossing this organization's real root would refuse
#: proves nothing about the real root.
def provision_standing(root:Path)->None:
    (root/"org-boundary/runtime").mkdir(parents=True,exist_ok=True)
    shutil.copy2(TREE/"org-boundary/runtime/node_standing.py",root/"org-boundary/runtime/node_standing.py")
    (root/"docs").mkdir(parents=True,exist_ok=True)
    shutil.copy2(TREE/CONTRACT,root/CONTRACT)

STANDING={"mode":"ESTABLISH_GENESIS","node_ref":"kernel-test-node","predecessor":None}
with tempfile.TemporaryDirectory() as td:
 root=Path(td); (root/"org-boundary/registry").mkdir(parents=True); provision_standing(root)
 reg={"organization":"Kernel-Test","services":[{"service_id":"kernel-test.boundary-diagnostic","repository":"Kernel-Test/.github","boundary_role":"BOUNDARY_LOCAL_DIAGNOSTIC"}]}
 (root/"org-boundary/registry/services.json").write_text(json.dumps(reg))
 packet={"schema_version":"stegverse.intr.org-boundary.v1","packet_id":"kernel-test-001","direction":"INGRESS",
 "origin":{"org":"Peer","service":"peer.boundary-diagnostic"},"destination":{"org":"Kernel-Test","service":"kernel-test.boundary-diagnostic"},
 "carrier":{"kind":"HB_DERIVED","reference":"canonical"},"intr_profile":"stegverse.intr.org-boundary.v1",
 "transition":{"reference":"diagnostic","authority_effect":"NONE"},"payload":{"probe":"ping"},"standing":STANDING,
 "evidence":{"ingress_receipt":None,"dispatch_receipt":None,"consumption_receipt":None,"egress_receipt":None,"reconstruction_reference":None}}
 frame=k.carrier_frame(packet,now_ns=k.HB_ANCHOR_UNIX_NS+1_000_000_000)
 recovered=k.recover_packet(frame); assert recovered==packet
 out=k.ingest_frame(root,frame); assert out["status"]=="CONSUMED"; assert out["execution_result"]["reconstruction"]["status"]=="RECONSTRUCTED"
 assert [x["kind"] for x in out["execution_result"]["receipts"]]==["INGRESS_ACCEPTED","DISPATCHED","CONSUMED","RESULT_BOUND","EGRESS_EMITTED"]
 print("PASS")


# node-standing gate proof: this organization's kernel-manifest.json declares
# kernel_version 1.3.1 and every peer directory entry declares kernel_required
# 1.3.0, both of which name this gate. A declared version does not establish the
# enforcement it implies, so the gate is proven here instead.
with tempfile.TemporaryDirectory() as td:
    root=Path(td)/"gate"
    (root/"org-boundary/registry").mkdir(parents=True); provision_standing(root)
    org="Gate-Test"
    reg={"organization":org,"services":[{"service_id":"gate-test.org-control","repository":"Gate-Test/.github","boundary_role":"BOUNDARY_LOCAL_CONTROL"}]}
    (root/"org-boundary/registry/services.json").write_text(json.dumps(reg))

    # A standing-less packet cannot be constructed: `standing` has no default.
    try:
        k.build_packet(origin_org="Anyone-At-All",origin_service="anyone.org-control",
                       destination_org=org,destination_service="gate-test.org-control",
                       payload={"probe":"unstanding"})
        raise AssertionError("build_packet accepted a packet with no standing")
    except TypeError as expected:
        assert "standing" in str(expected)

    # A hand-forged envelope that skips the constructor is refused fail-closed,
    # as the contract's own disposition rather than a bare error. This is the
    # exact packet that was CONSUMED with a full five-receipt chain before the
    # gate: origin "Anyone-At-All", no standing at all.
    forged={"schema_version":k.PACKET_SCHEMA,"packet_id":"gate-test-001","direction":"INGRESS",
            "origin":{"org":"Anyone-At-All","service":"anyone.org-control"},
            "destination":{"org":org,"service":"gate-test.org-control"},
            "carrier":{"kind":"HB_DERIVED","reference":"org-federation"},
            "intr_profile":"stegverse.intr.org-boundary.v1",
            "transition":{"reference":"federation.v1","authority_effect":"NONE","conditions":[]},
            "payload":{"probe":"unstanding"},
            "evidence":{"ingress_receipt":None,"dispatch_receipt":None,"consumption_receipt":None,"egress_receipt":None,"reconstruction_reference":None}}
    try:
        k.dispatch(root,forged)
        raise AssertionError("dispatch consumed a crossing with no standing")
    except ValueError as refused:
        assert str(refused).startswith("node_standing_refused:"), refused
        assert "no-standing-declared" in str(refused), refused

    # An empty declaration is refused too, rather than falling back to a
    # genesis: the contract forbids silent_fallback and silent_reenrollment.
    try:
        k.dispatch(root,{**forged,"standing":{}})
        raise AssertionError("dispatch consumed a crossing with an empty standing declaration")
    except ValueError as refused:
        assert str(refused).startswith("node_standing_refused:"), refused

    # The same crossing, carrying standing, is admitted and the resolved
    # standing travels on the result.
    admitted=k.dispatch(root,{**forged,"standing":STANDING})
    assert admitted["consumed"] is True
    assert admitted["application_result"]["execution_authority_inferred"] is False
    assert admitted["node_standing_disposition"]=="ALLOW"
    assert admitted["standing_mode"]=="ESTABLISH_GENESIS"
    assert admitted["standing_node_ref"]=="kernel-test-node"
    assert admitted["standing_generation"]==1
    assert [x["kind"] for x in admitted["receipts"]]==["INGRESS_ACCEPTED","DISPATCHED","CONSUMED","RESULT_BOUND","EGRESS_EMITTED"]
    # The gate makes the crossing provable by node chain. It does not validate
    # the caller-written origin string, and the result says so rather than
    # letting a reader of the chain assume otherwise -- the origin above is
    # still "Anyone-At-All" and the crossing is admitted on its standing.
    assert admitted["caller_editable_origin_established_identity"] is False
    assert admitted["structural_standing_only"] is True
    assert admitted["structural_standing_is_authenticated_standing"] is False
    assert admitted["standing_authority_effect"]=="NONE_STANDING_ONLY"

    # A response is not a new crossing: it carries the request's standing
    # forward, marked as carried.
    response=k.build_control_response({**forged,"standing":STANDING,
                                       "payload":{"message_class":"ecosystem.communication",
                                                  "communication_id":"gate-test-comm-001","subject":"gate"}},
                                      admitted)
    assert response["standing"]["standing_carried_forward_from_request"] is True
    assert response["standing"]["mode"]==STANDING["mode"]
print("NODE_STANDING_GATE_PASS")
