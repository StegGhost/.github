#!/usr/bin/env python3
import argparse, hashlib, json, os, subprocess, sys, tempfile
from pathlib import Path
from org_boundary_runtime import build_egress, validate_org_crossing

ROOT=Path(__file__).resolve().parents[1]
PROCESS_BOUNDARY=["python3","org-boundary/runtime/process_boundary.py"]
#: process_boundary's exit split (DC#10). Only 75 -- its own state faulting -- is
#: non-terminal: no marker, and the same envelope is processed once on the next
#: run (B-P36j/B-P36o). 65 is the envelope's own defect: terminal and
#: quarantined. Any other exit (1, a crash, an unknown code) is refused terminal
#: and quarantined too, so an unknown failure never stays pending forever.
EXIT_INPUT_FAULT=65
EXIT_WRITE_FAULT=75
QUARANTINE=ROOT/"resident-runtime/federation/quarantine.d"
RETRY="resident-runtime/run_once.py --ingress <envelope> --egress <path>"

def record(code,failed,detail,terminal):
    return {"disposition":"FAIL_CLOSED","failure_code":code,"failed_predicate":failed,"detail":detail,
            "required_evidence_or_repair":("a well-formed, admissible envelope" if terminal
                                           else "this organization's own state reads and writes"),
            "retry_entrypoint":RETRY,"owning_existing_goal":"INTERLOCK-INTR-RUNTIME-INDEPENDENT-PROTOCOL-001",
            "next_attempt":("none: the envelope is quarantined" if terminal
                            else "re-run with the same envelope; it is consumed once, nothing was quarantined"),
            "terminal":terminal,"derived_from_clock":False,"consequence_committed":False}

def marker_path(packet_id,quarantine):
    return Path(quarantine)/(hashlib.sha256(str(packet_id).encode()).hexdigest()+".json")

def quarantine_envelope(packet_id,refusal,quarantine):
    """Write the quarantine marker for a terminal input fault (atomically)."""
    path=marker_path(packet_id,quarantine); path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix(".tmp"); temp.write_text(json.dumps({"packet_id":packet_id,**refusal},sort_keys=True)+"\n")
    os.replace(temp,path)

def run(ingress_path,egress_path,quarantine=QUARANTINE):
    """Process one envelope; return (exit status, printed record)."""
    try:
        ingress=json.loads(Path(ingress_path).read_text())
        if not isinstance(ingress,dict): raise ValueError("envelope is not a JSON object")
    except (OSError,ValueError) as error:
        return EXIT_INPUT_FAULT,record("FRAME_INGEST_FAILED","ENVELOPE_IS_READABLE_JSON",
                                       type(error).__name__+": "+str(error),True)
    packet_id=ingress.get("packet_id")
    if packet_id is not None and marker_path(packet_id,quarantine).exists():
        return EXIT_INPUT_FAULT,record("FRAME_REFUSED_QUARANTINED","ENVELOPE_IS_NOT_QUARANTINED",
                                       "packet "+str(packet_id)+" is quarantined",True)
    try:
        validate_org_crossing(ingress,"INGRESS")
    except (ValueError,KeyError,TypeError) as error:
        refusal=record("FRAME_INGEST_FAILED","ENVELOPE_IS_A_VALID_ORG_CROSSING",str(error),True)
        if packet_id is not None: quarantine_envelope(packet_id,refusal,quarantine)
        return EXIT_INPUT_FAULT,refusal
    with tempfile.TemporaryDirectory() as td:
        result_path=Path(td)/"execution.json"
        done=subprocess.run(PROCESS_BOUNDARY+["--envelope",str(ingress_path),"--out",str(result_path)],
                            capture_output=True,text=True)
        if done.returncode==EXIT_INPUT_FAULT:
            refusal=record("FRAME_INGEST_FAILED","PROCESS_BOUNDARY_INPUT_FAULT",done.stderr.strip(),True)
            quarantine_envelope(packet_id,refusal,quarantine)
            return EXIT_INPUT_FAULT,refusal
        if done.returncode==EXIT_WRITE_FAULT:
            return EXIT_WRITE_FAULT,record("PROCESS_BOUNDARY_WRITE_FAULT","PROCESS_BOUNDARY_COMPLETES",
                                           done.stderr.strip(),False)
        if done.returncode!=0:
            refusal=record("PROCESS_BOUNDARY_REFUSED_EXIT_"+str(done.returncode),"PROCESS_BOUNDARY_EXITS_0_65_OR_75",
                           "exit "+str(done.returncode)+": "+done.stderr.strip(),True)
            quarantine_envelope(packet_id,refusal,quarantine)
            return EXIT_INPUT_FAULT,refusal
        result=json.loads(result_path.read_text())
    egress=build_egress(ingress,result)
    validate_org_crossing(egress,"EGRESS")
    try:
        Path(egress_path).parent.mkdir(parents=True,exist_ok=True)
        Path(egress_path).write_text(json.dumps(egress,indent=2,sort_keys=True)+"\n")
    except OSError as error:
        return EXIT_WRITE_FAULT,record("PROCESS_BOUNDARY_WRITE_FAULT","EGRESS_PATH_IS_WRITABLE",
                                       type(error).__name__+": "+str(error),False)
    return 0,{"status":"PASS","packet_id":ingress["packet_id"],"egress_packet_id":egress["packet_id"],"consumed":result["consumed"],"reconstruction":result["reconstruction"]["status"]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ingress",required=True)
    ap.add_argument("--egress",required=True)
    ap.add_argument("--quarantine-dir",default=str(QUARANTINE))
    args=ap.parse_args()
    code,printed=run(args.ingress,args.egress,args.quarantine_dir)
    print(json.dumps(printed,sort_keys=True))
    return code

if __name__=="__main__":
    sys.exit(main())
