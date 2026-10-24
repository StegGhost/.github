#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("org_kernel",ROOT/"org-kernel"/"kernel.py")
K=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(K)

def main():
    ap=argparse.ArgumentParser()
    sub=ap.add_subparsers(dest="cmd",required=True)
    for name,cls in (("send-monitor","ecosystem.monitor.request"),("send-work","ecosystem.work.request"),("send-message","ecosystem.communication")):
        p=sub.add_parser(name)
        p.add_argument("--subject",required=True)
        p.add_argument("--body-json",required=True)
        p.add_argument("--requested-action")
        p.add_argument("--communication-id")
        # Required, with no default. Every outbound crossing declares canonical
        # node standing, and a standing this runtime manufactured for itself
        # would be the gate answering its own question. The operator supplies
        # the declaration; `node_standing` checks its shape at the far side.
        p.add_argument("--standing",required=True,
                       help="JSON file declaring mode, node_ref and the predecessor key")
        p.set_defaults(message_class=cls)
    p=sub.add_parser("collect")
    p.add_argument("--communication-id",required=True)
    sub.add_parser("status")
    args=ap.parse_args()
    reg=K.load_registry(ROOT)
    org=reg["organization"]
    if args.cmd=="status":
        print(json.dumps(K.resident_status(ROOT),indent=2,sort_keys=True))
        return
    if args.cmd=="collect":
        result=K.collect_ecosystem_responses(org,args.communication_id,repo_root=ROOT)
        print(json.dumps(result,indent=2,sort_keys=True))
        return
    body=json.loads(args.body_json)
    standing=json.loads(Path(args.standing).read_text())
    # The repo-local spool is the only route (B-P40): nothing is sent to a
    # hosted gateway, so a crossing never waits on a destination being up.
    out=K.publish_ecosystem_from_directory(
        ROOT,
        standing=standing,
        message_class=args.message_class,
        subject=args.subject,
        body=body,
        requested_action=args.requested_action,
        communication_id=args.communication_id
    )
    print(json.dumps({
      "status":"PUBLISHED",
      "organization":org,
      "communication_id":out["communication_id"],
      "published_count":out["published_count"]
    },indent=2,sort_keys=True))

if __name__=="__main__":
    main()
