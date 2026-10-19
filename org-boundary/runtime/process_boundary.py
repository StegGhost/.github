#!/usr/bin/env python3
import argparse, hashlib, importlib.util, json, os, sys
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
#: DC#10's exit split, kept so a caller can tell the two apart: 65 is the
#: envelope's defect (terminal, the caller may quarantine it); 75 is this
#: organization's own state faulting (non-terminal, never quarantined, the
#: same envelope is processed once on the next run).
EXIT_INPUT_FAULT=65
EXIT_WRITE_FAULT=75
def fault(code,failed,detail):
 """Print the six-field record (and the reason on stderr) and exit with the split code."""
 terminal=code==EXIT_INPUT_FAULT
 record={"disposition":"FAIL_CLOSED","failure_code":"PROCESS_BOUNDARY_INPUT_FAULT" if terminal else "PROCESS_BOUNDARY_WRITE_FAULT",
         "failed_predicate":failed,"detail":detail,
         "required_evidence_or_repair":"a well-formed, admissible envelope" if terminal else "this organization's own state reads and the result path is writable",
         "retry_entrypoint":"org-boundary/runtime/process_boundary.py --envelope <envelope> --out <result>",
         "owning_existing_goal":"INTERLOCK-INTR-RUNTIME-INDEPENDENT-PROTOCOL-001",
         "next_attempt":"none: the envelope is refused" if terminal else "re-run with the same envelope; nothing durable was written",
         "terminal":terminal,"derived_from_clock":False,"consequence_committed":False}
 sys.stderr.write(detail+"\n"); print(json.dumps(record,sort_keys=True)); raise SystemExit(code)
def main():
 ap=argparse.ArgumentParser(); ap.add_argument("--envelope",required=True); ap.add_argument("--registry",default="org-boundary/registry/services.json"); ap.add_argument("--out",required=True); a=ap.parse_args()
 try: env=load(a.envelope)
 except (OSError,ValueError,RecursionError,MemoryError) as e: fault(EXIT_INPUT_FAULT,"ENVELOPE_IS_READABLE_JSON",type(e).__name__+": "+str(e))
 if not isinstance(env,dict): fault(EXIT_INPUT_FAULT,"ENVELOPE_IS_READABLE_JSON","envelope is not a JSON object")
 try: reg=load(a.registry)
 except (OSError,ValueError,RecursionError,MemoryError) as e: fault(EXIT_WRITE_FAULT,"OWN_REGISTRY_READS",type(e).__name__+": "+str(e))
 try: result,prev=process(env,reg)
 except OSError as e: fault(EXIT_WRITE_FAULT,"OWN_STATE_READS",type(e).__name__+": "+str(e))
 except SystemExit as e: fault(EXIT_INPUT_FAULT,"ENVELOPE_IS_ADMISSIBLE",str(e.code))
 except (KeyError,TypeError,ValueError,AttributeError,RecursionError) as e: fault(EXIT_INPUT_FAULT,"ENVELOPE_IS_ADMISSIBLE",type(e).__name__+": "+str(e))
 # Atomic: staged beside the result and replaced, so a fault leaves no partial result.
 out=Path(a.out); temp=out.with_name("."+out.name+".tmp")
 try:
  out.parent.mkdir(parents=True,exist_ok=True); temp.write_text(json.dumps(result,indent=2,sort_keys=True)+"\n"); os.replace(temp,out)
 except OSError as e:
  try: temp.unlink()
  except OSError: pass
  fault(EXIT_WRITE_FAULT,"RESULT_PATH_IS_WRITABLE",type(e).__name__+": "+str(e))
 print(json.dumps({"status":"PASS","terminal_receipt_id":prev}))
def process(env,reg):
 req=["schema_version","packet_id","direction","origin","destination","carrier","intr_profile","transition","payload","evidence"]
 miss=[k for k in req if k not in env]
 if miss: raise SystemExit("missing:"+",".join(miss))
 # The fields the receipts and the egress are built from are checked here, so a
 # wrong-typed one is refused 65 at the boundary rather than crashing a caller
 # after an exit 0.
 if not isinstance(env["packet_id"],str) or not env["packet_id"]: raise SystemExit("invalid-field:packet_id")
 for side in ("origin","destination"):
  if not isinstance(env[side],dict) or not all(isinstance(env[side].get(k),str) for k in ("org","service")): raise SystemExit("invalid-field:"+side)
 if not isinstance(env["carrier"],dict) or not all(isinstance(env["carrier"].get(k),str) for k in ("kind","reference")): raise SystemExit("invalid-field:carrier")
 if not isinstance(env["transition"],dict) or not all(isinstance(env["transition"].get(k),str) for k in ("reference","authority_effect")): raise SystemExit("invalid-field:transition")
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
 return result,prev
if __name__=="__main__": main()
