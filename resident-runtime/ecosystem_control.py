#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("org_kernel",ROOT/"org-kernel"/"kernel.py")
K=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(K)
EPOCH_RETRY_ENTRYPOINT="resident-runtime/ecosystem_control.py send-* --hb-epoch (or HB_EPOCH)"

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
        # The epoch every published frame carries is supplied, never read from a
        # clock (data/sv-work-items/invariants.json:133, B-P40): --hb-epoch, else
        # HB_EPOCH as a committed-request gate exports it. Absent is refused.
        p.add_argument("--hb-epoch",default=None,
                       help="supplied heartbeat epoch (ASCII digits, >= 32); refused FAIL_CLOSED when absent")
        p.set_defaults(message_class=cls)
    p=sub.add_parser("collect")
    p.add_argument("--communication-id",required=True)
    sub.add_parser("status")
    args=ap.parse_args()
    reg=K.load_registry(ROOT)
    org=reg["organization"]
    if args.cmd=="status":
        print(json.dumps(K.resident_status(ROOT),indent=2,sort_keys=True))
        return 0
    if args.cmd=="collect":
        result=K.collect_ecosystem_responses(org,args.communication_id,repo_root=ROOT)
        print(json.dumps(result,indent=2,sort_keys=True))
        return 0
    raw=args.hb_epoch if args.hb_epoch is not None else os.environ.get("HB_EPOCH")
    refusal=K.writer_epoch_refusal(raw,retry_entrypoint=EPOCH_RETRY_ENTRYPOINT)
    if refusal is not None:
        print(json.dumps(refusal,sort_keys=True))
        return 1
    # Inputs are read strictly (no NaN or Infinity) before anything is published.
    body=K.read_input_json(args.body_json,argument="--body-json",retry_entrypoint=EPOCH_RETRY_ENTRYPOINT,inline=True)
    standing=K.read_input_json(args.standing,argument="--standing",retry_entrypoint=EPOCH_RETRY_ENTRYPOINT)
    request=K.committed_request()
    # The repo-local spool is the only route (B-P40): nothing is sent to a
    # hosted gateway, so a crossing never waits on a destination being up.
    out=K.publish_ecosystem_from_directory(
        ROOT,
        standing=standing,
        message_class=args.message_class,
        subject=args.subject,
        body=body,
        requested_action=args.requested_action,
        communication_id=args.communication_id,
        epoch=int(raw)
    )
    record={
      "status":"PUBLISHED",
      "organization":org,
      "communication_id":out["communication_id"],
      "published_count":out["published_count"],
      "heartbeat_reference":K.hb_reference(epoch=int(raw))
    }
    if request is not None:
        record["committed_request"]=request
    print(json.dumps(record,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(K.run_writer_cli(main,retry_entrypoint=EPOCH_RETRY_ENTRYPOINT))
