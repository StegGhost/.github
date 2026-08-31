#!/usr/bin/env python3
import argparse, json, subprocess, tempfile
from pathlib import Path
from org_boundary_runtime import build_egress, validate_org_crossing

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--ingress",required=True)
    ap.add_argument("--egress",required=True)
    args=ap.parse_args()
    ingress=json.loads(Path(args.ingress).read_text())
    validate_org_crossing(ingress,"INGRESS")
    with tempfile.TemporaryDirectory() as td:
        result_path=Path(td)/"execution.json"
        subprocess.run(["python3","org-boundary/runtime/process_boundary.py","--envelope",args.ingress,"--out",str(result_path)],check=True)
        result=json.loads(result_path.read_text())
    egress=build_egress(ingress,result)
    validate_org_crossing(egress,"EGRESS")
    Path(args.egress).parent.mkdir(parents=True,exist_ok=True)
    Path(args.egress).write_text(json.dumps(egress,indent=2,sort_keys=True)+"\n")
    print(json.dumps({"status":"PASS","packet_id":ingress["packet_id"],"egress_packet_id":egress["packet_id"],"consumed":result["consumed"],"reconstruction":result["reconstruction"]["status"]}))

if __name__=="__main__":
    main()
