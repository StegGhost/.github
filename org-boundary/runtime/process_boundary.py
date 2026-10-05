#!/usr/bin/env python3
import argparse, hashlib, importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
# Standing is an ingress precondition. This file is a separately invocable
# ingress surface -- `resident-runtime/run_once.py` runs it directly as a
# subprocess, never through `kernel.dispatch` -- so a gate that lives only in
# the kernel leaves this lane ungated. It is resolved here too, before any
# receipt is minted.
_NSSPEC=importlib.util.spec_from_file_location(
    "node_standing", Path(__file__).resolve().parent/"node_standing.py")
node_standing=importlib.util.module_from_spec(_NSSPEC)
_NSSPEC.loader.exec_module(node_standing)
# Processing is selected by the admitted manifest, not by the addressed row.
# This surface is invoked directly as a subprocess, so a selection that lived
# only in the kernel would leave this lane selecting by identity.
_SELSPEC=importlib.util.spec_from_file_location(
    "manifest_selection", Path(__file__).resolve().parent/"manifest_selection.py")
selection=importlib.util.module_from_spec(_SELSPEC)
_SELSPEC.loader.exec_module(selection)
KINDS=["INGRESS_ACCEPTED","DISPATCHED","CONSUMED","RESULT_BOUND","EGRESS_EMITTED"]
def canon(v): return json.dumps(v,sort_keys=True,separators=(",",":")).encode()
def hid(prefix,v): return prefix+"-"+hashlib.sha256(canon(v)).hexdigest()[:24]
def load(path): return json.loads(Path(path).read_text())
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--envelope",required=True); ap.add_argument("--registry",default="org-boundary/registry/services.json"); ap.add_argument("--out",required=True); a=ap.parse_args()
 env=load(a.envelope); reg=load(a.registry)
 req=["schema_version","packet_id","direction","origin","destination","carrier","intr_profile","transition","payload","evidence"]
 miss=[k for k in req if k not in env]
 if miss: raise SystemExit("missing:"+",".join(miss))
 if env["destination"]["org"]!=reg["organization"]: raise SystemExit("wrong-destination-org")
 svc=next((s for s in reg["services"] if s["service_id"]==env["destination"]["service"]),None)
 if not svc: raise SystemExit("unknown-service")
 if svc.get("boundary_role")!="BOUNDARY_LOCAL_DIAGNOSTIC": raise SystemExit("endpoint-adapter-not-installed")
 # Resolved before any receipt is minted: a refused crossing must not leave a
 # chain implying it was consumed.
 standing=node_standing.require(node_standing.load_contract(ROOT),env)
 # Refuse a declaration this service does not admit before any receipt is
 # minted: a refused crossing must not leave a chain implying it was consumed.
 selected=selection.select_processing(svc,env["payload"])
 base={"packet_id":env["packet_id"],"service_id":svc["service_id"],"payload_hash":hashlib.sha256(canon(env["payload"])).hexdigest()}
 receipts=[]; prev=None
 for kind in KINDS:
  subject={**base,"kind":kind,"previous_receipt_id":prev}; rid=hid(kind.lower(),subject)
  receipts.append({"kind":kind,"receipt_id":rid,"subject":svc["service_id"],"evidence_hash":hashlib.sha256(canon(subject)).hexdigest(),"previous_receipt_id":prev}); prev=rid
 result={"schema_version":reg["organization"].lower().replace(" ","-")+".boundary-execution.v1","packet_id":env["packet_id"],"organization":reg["organization"],"service_id":svc["service_id"],"consumed":True,"application_result":{"echo":env["payload"]},"authority_effect":env["transition"]["authority_effect"],**selected,**standing,"receipts":receipts,"reconstruction":{"same_execution_required":True,"status":"RECONSTRUCTED","terminal_receipt_id":prev}}
 Path(a.out).parent.mkdir(parents=True,exist_ok=True); Path(a.out).write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); print(json.dumps({"status":"PASS","terminal_receipt_id":prev}))
if __name__=="__main__": main()
