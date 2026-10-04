#!/usr/bin/env python3
import json, subprocess, sys, tempfile
from pathlib import Path
reg=json.loads(Path("org-boundary/registry/services.json").read_text())
svc=next(s["service_id"] for s in reg["services"] if s.get("boundary_role")=="BOUNDARY_LOCAL_DIAGNOSTIC")
STANDING={"mode":"ESTABLISH_GENESIS","node_ref":"boundary-test-node","predecessor":None}
env={"schema_version":"test","packet_id":"pkt-001","direction":"INGRESS","origin":{"org":"peer","service":"peer.boundary-diagnostic"},"destination":{"org":reg["organization"],"service":svc},"carrier":{"kind":"HB_DERIVED","reference":"HB-test"},"intr_profile":"stegverse.intr.org-boundary.v1","transition":{"reference":"test","authority_effect":"NONE"},"payload":{"probe":"ping"},"standing":STANDING,"evidence":{"ingress_receipt":None,"dispatch_receipt":None,"consumption_receipt":None,"egress_receipt":None,"reconstruction_reference":None}}

def run(envelope,td):
 (td/"in.json").write_text(json.dumps(envelope))
 return subprocess.run([sys.executable,"org-boundary/runtime/process_boundary.py","--envelope",str(td/"in.json"),"--out",str(td/"out.json")],capture_output=True,text=True)

with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)
 done=run(env,p); assert done.returncode==0, done.stderr
 out=json.loads((p/"out.json").read_text()); assert out["consumed"] is True; assert out["reconstruction"]["status"]=="RECONSTRUCTED"; assert out["authority_effect"]=="NONE"
 # The resolved standing travels on the execution result.
 assert out["node_standing_disposition"]=="ALLOW"
 assert out["standing_mode"]=="ESTABLISH_GENESIS"
 assert out["standing_node_ref"]=="boundary-test-node"
 assert out["standing_generation"]==1
 assert out["caller_editable_origin_established_identity"] is False
 assert out["standing_authority_effect"]=="NONE_STANDING_ONLY"
print("PASS")

# This surface is invoked directly as a subprocess by resident-runtime/run_once.py,
# never through kernel.dispatch, so it is gated here in its own right. Before the
# gate this exact envelope -- origin "Anyone-At-All", no standing at all -- exited
# 0 with a full five-receipt chain and a terminal receipt.
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp)
 unstanding={k:v for k,v in env.items() if k!="standing"}
 unstanding["origin"]={"org":"Anyone-At-All","service":"anyone.boundary-diagnostic"}
 refused=run(unstanding,p)
 assert refused.returncode!=0, "process boundary consumed a crossing with no standing"
 assert "node-standing-fail_closed" in refused.stderr, refused.stderr
 assert "no-standing-declared" in refused.stderr, refused.stderr
 assert not (p/"out.json").exists(), "a refused crossing left an execution result behind"

 # An empty declaration is refused too rather than falling back to a genesis:
 # the contract forbids silent_fallback and silent_reenrollment.
 empty=run({**unstanding,"standing":{}},p)
 assert empty.returncode!=0, "process boundary consumed an empty standing declaration"
 assert "node-standing-" in empty.stderr, empty.stderr

 # An absent predecessor key is an unstated chain position, not a genesis.
 nopred=run({**unstanding,"standing":{"mode":"ESTABLISH_GENESIS","node_ref":"n"}},p)
 assert nopred.returncode!=0, "process boundary consumed a standing with no predecessor key"
 assert "predecessor-key-absent" in nopred.stderr, nopred.stderr
print("PROCESS_BOUNDARY_NODE_STANDING_GATE_PASS")

# The transport helpers hold the same rule: standing is required at construction
# and carried, not re-declared, on the egress side.
import importlib.util
_s=importlib.util.spec_from_file_location("intr_transport","org-boundary/runtime/intr_transport.py")
T=importlib.util.module_from_spec(_s); _s.loader.exec_module(T)
try:
 T.build_ingress({"org":"peer","service":"peer.boundary-diagnostic"},{"org":reg["organization"],"service":svc},{"probe":"ping"},"HB-test","test")
 raise AssertionError("build_ingress accepted an envelope with no standing")
except TypeError as expected:
 assert "standing" in str(expected)
ing=T.build_ingress({"org":"peer","service":"peer.boundary-diagnostic"},{"org":reg["organization"],"service":svc},{"probe":"ping"},"HB-test","test",standing=STANDING)
assert T.validate_org_crossing(ing,"INGRESS") is True
for bad in ({k:v for k,v in ing.items() if k!="standing"},{**ing,"standing":"declared"}):
 try:
  T.validate_org_crossing(bad,"INGRESS")
  raise AssertionError("validate_org_crossing accepted an envelope with no declared standing")
 except ValueError as refused:
  assert str(refused) in ("missing-standing","standing-not-declared"), refused
with tempfile.TemporaryDirectory() as tmp:
 p=Path(tmp); done=run(ing,p); assert done.returncode==0, done.stderr
 eg=T.build_egress(ing,json.loads((p/"out.json").read_text()))
 assert eg["standing"]["standing_carried_forward_from_request"] is True
 assert eg["standing"]["mode"]==STANDING["mode"]
 assert T.validate_org_crossing(eg,"EGRESS") is True
print("INTR_TRANSPORT_STANDING_PASS")
