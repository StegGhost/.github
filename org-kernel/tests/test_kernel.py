#!/usr/bin/env python3
import importlib.util, json, shutil, tempfile
from pathlib import Path
spec=importlib.util.spec_from_file_location("kernel","org-kernel/kernel.py"); k=importlib.util.module_from_spec(spec); spec.loader.exec_module(k)

TREE=Path("org-kernel/kernel.py").resolve().parents[1]
CONTRACT="docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json"
#: A synthetic root is a dispatch root like any other, so it has to carry every
#: surface the kernel resolves from it -- standing, and the manifest selection
#: that decides how processing was chosen. Copied rather than stubbed: a test
#: root that admits a crossing this organization's real root would refuse proves
#: nothing about the real root.
def provision_standing(root:Path)->None:
    (root/"org-boundary/runtime").mkdir(parents=True,exist_ok=True)
    shutil.copy2(TREE/"org-boundary/runtime/node_standing.py",root/"org-boundary/runtime/node_standing.py")
    shutil.copy2(TREE/"org-boundary/runtime/manifest_selection.py",
                 root/"org-boundary/runtime/manifest_selection.py")
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


# Egress closability and far-side receipt recomputation. Before this, a payload
# declaring a class the profile answers with nothing was published, consumed and
# receipted by the far side and never answered, and a response carrying a forged
# terminal receipt was accepted and counted complete.
with tempfile.TemporaryDirectory() as td:
    mesh=Path(td)/"mesh"
    a=Path(td)/"a"; b=Path(td)/"b"
    for root,org in ((a,"Org-A"),(b,"Org-B")):
        (root/"org-boundary/registry").mkdir(parents=True); provision_standing(root)
        slug=org.lower()
        reg={"organization":org,"services":[{"service_id":slug+".org-control","repository":org+"/.github","boundary_role":"BOUNDARY_LOCAL_CONTROL","accepts":list(k.RESPONDED_REQUEST_CLASSES)}]}
        (root/"org-boundary/registry/services.json").write_text(json.dumps(reg))

    # An unanswerable class is refused at emission rather than published.
    try:
        k.build_ecosystem_packets(origin_org="Org-A",origin_service="org-a.org-control",
                                  organizations=["Org-B"],standing=STANDING,
                                  message_class="ecosystem.status.query",subject="unclosable",
                                  body={},communication_id="unclosable-001")
        raise AssertionError("an unclosable crossing was emitted")
    except ValueError as refused:
        assert str(refused).startswith("unclosable_crossing:message_class_is_answered_by_no_acknowledgement"), refused
    assert not (mesh/"frames.d").exists(), "a refused crossing published a frame"

    # A blank communication_id leaves closure nothing to correlate on.
    try:
        k.build_ecosystem_packets(origin_org="Org-A",origin_service="org-a.org-control",
                                  organizations=["Org-B"],standing=STANDING,
                                  message_class="ecosystem.communication",subject="blank",
                                  body={},communication_id="   ")
        raise AssertionError("a crossing with a blank communication_id was emitted")
    except ValueError as refused:
        assert "closure_correlates_on_communication_id" in str(refused), refused

    # Every answered class is emittable, so the refusal is the profile's set and
    # not a narrower one invented here.
    for cls in k.RESPONDED_REQUEST_CLASSES:
        built=k.build_ecosystem_packets(origin_org="Org-A",origin_service="org-a.org-control",
                                        organizations=["Org-B"],standing=STANDING,
                                        message_class=cls,subject="closable",body={},
                                        communication_id="closable-"+cls)
        assert len(built["packets"])==1

    # A real crossing: emit, let the far side answer, then recompute its chain.
    COMM="recompute-001"
    out=k.publish_ecosystem_message(origin_org="Org-A",origin_service="org-a.org-control",
                                    organizations=["Org-B"],standing=STANDING,
                                    message_class="ecosystem.communication",subject="recompute",
                                    body={"probe":"recompute"},communication_id=COMM,
                                    root=mesh,repo_root=a)
    assert out["emissions_recorded"] is True
    pid=out["publications"][0]["packet"]["packet_id"]
    # The request frame is clock-flagged and lends no epoch, so the response is
    # published at the epoch supplied to the cycle, never from a clock.
    served=k.consume_and_respond(b,mesh_root=mesh,hb_epoch=4096)
    assert [x["result"]["status"] for x in served]==["CONSUMED"]
    assert served[0]["response_publication"]["frame"]["heartbeat_reference"]["derived_from_clock"] is False
    assert served[0]["response_publication"] is not None

    collected=k.collect_ecosystem_responses("Org-A",COMM,mesh_root=mesh,repo_root=a)
    assert collected["far_side_receipts_recomputed_here"] is True
    assert collected["response_count"]==1, collected
    assert collected["refused_count"]==0, collected["refused"]
    row=collected["organizations"][0]
    assert row["receipt_terminal_recomputes"] is True, row
    assert row["receipt_terminal"]==row["far_side_terminal_receipt_recomputed"]
    assert row["findings"]==[]
    # The recomputation matches what the far side actually minted, so this is a
    # recomputation of the real chain and not two copies of one derivation.
    assert row["receipt_terminal"]==served[0]["result"]["execution_result"]["reconstruction"]["terminal_receipt_id"]

    # Without an emission to recompute against, the absence is stated rather
    # than a carried terminal being reported as a checked one.
    unchecked=k.collect_ecosystem_responses("Org-A",COMM,mesh_root=mesh)
    assert unchecked["far_side_receipts_recomputed_here"] is False
    assert unchecked["organizations"][0]["receipt_terminal_recomputes"] is None
    assert unchecked["organizations"][0]["far_side_terminal_receipt_recomputed"] is None

    # A forged terminal receipt is refused, not counted.
    import base64
    for path in sorted((mesh/"frames.d").glob("*.json")):
        frame=json.loads(path.read_text())
        if frame["destination_org"]!="Org-A": continue
        forged_packet=k.recover_packet(frame)
        forged_packet["payload"]["body"]["receipt_terminal"]="egress_emitted-"+("0"*24)
        raw=k.canon(forged_packet)
        body={key:value for key,value in frame.items() if key!="frame_sha256"}
        body["packet_base64"]=base64.b64encode(raw).decode("ascii"); body["packet_sha256"]=k.sha(raw)
        path.write_text(json.dumps({**body,"frame_sha256":k.sha(body)},indent=2,sort_keys=True)+"\n")
    forged=k.collect_ecosystem_responses("Org-A",COMM,mesh_root=mesh,repo_root=a)
    assert forged["response_count"]==0, forged
    assert forged["refused_count"]==1, forged
    assert any(f.startswith("FAR_SIDE_TERMINAL_RECEIPT_DOES_NOT_RECOMPUTE")
               for f in forged["refused"][0]["findings"]), forged["refused"]

    # A response to a crossing this organization has no record of emitting is
    # refused too, whatever its terminal asserts.
    assert k.recorded_emissions(b,COMM)=={}
    stranger=k.collect_ecosystem_responses("Org-A",COMM,mesh_root=mesh,repo_root=b)
    assert stranger["response_count"]==0, stranger
    assert any(f.startswith("THIS_ORGANIZATION_HAS_NO_EMISSION_RECORD_FOR_THIS_PACKET")
               for f in stranger["refused"][0]["findings"]), stranger["refused"]
print("EGRESS_CLOSABILITY_AND_RECOMPUTATION_PASS")
