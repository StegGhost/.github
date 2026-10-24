#!/usr/bin/env python3
from __future__ import annotations
import argparse, importlib.util, json, os
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SPEC=importlib.util.spec_from_file_location("org_kernel",ROOT/"org-kernel"/"kernel.py")
K=importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(K)

#: The epoch is supplied (--hb-epoch, else HB_EPOCH) and checked by the kernel's
#: shared rule; absent or invalid is refused six-field FAIL_CLOSED before
#: anything is written. It stamps the cycle record and every response the cycle
#: publishes. No clock is read.
EPOCH_RETRY_ENTRYPOINT="resident-runtime/federation_cycle.py --hb-epoch (or HB_EPOCH)"

def main(argv=None):
    parser=argparse.ArgumentParser(prog="federation_cycle.py")
    parser.add_argument("--hb-epoch",default=None,
                        help="supplied heartbeat epoch (ASCII digits, >= 32); refused FAIL_CLOSED when invalid")
    args=parser.parse_args(argv)
    raw=args.hb_epoch if args.hb_epoch is not None else os.environ.get("HB_EPOCH")
    refusal=K.writer_epoch_refusal(raw,retry_entrypoint=EPOCH_RETRY_ENTRYPOINT)
    if refusal is not None:
        print(json.dumps(refusal,sort_keys=True))
        return 1
    hb_epoch=int(raw)
    heartbeat=K.hb_reference(epoch=hb_epoch)
    # The repo-local spool is the only route (B-P40): no hosted gateway is
    # polled or awaited, so the cycle does not depend on a destination being up
    # (derived from StegVerse-Labs/.github@149f16e
    # task-registry-global-invariants.json:58,60,160-161).
    results=K.consume_and_respond(ROOT,hb_epoch=hb_epoch)
    consumed=sum(1 for x in results if (x.get("result") or {}).get("status")=="CONSUMED")
    responses=sum(1 for x in results if x.get("response_publication"))
    # Each refusal is surfaced six-field, never silently passed over; the
    # frame itself was quarantined by the kernel so it is not met again.
    refusals=[x["result"]["refusal"] for x in results
              if (x.get("result") or {}).get("status")=="REFUSED" and x["result"].get("refusal")]
    receipt={
      "schema_version":"stegverse.org-federation-cycle.v1",
      "organization":K.load_registry(ROOT)["organization"],
      "heartbeat_reference":heartbeat,
      "frames_seen":len(results),
      "frames_consumed":consumed,
      "responses_emitted":responses,
      "frames_refused":len(refusals),
      "refusals":refusals,
      "authority_effect":"NONE_CARRIER_ONLY",
      "transport":"REPO_LOCAL_SPOOL"
    }
    out=ROOT/"resident-runtime"/"federation"/"latest-cycle.json"
    out.parent.mkdir(parents=True,exist_ok=True)
    K.write_atomic(out,json.dumps(receipt,indent=2,sort_keys=True)+"\n")
    print(json.dumps(receipt,sort_keys=True))
    # A cycle that met frames and consumed none of them did not succeed.
    if receipt.get("frames_refused") and not receipt.get("frames_consumed"):
        return 1
    return 0

if __name__=="__main__":
    # A fault in the cycle's own writes prints six fields, not a traceback.
    raise SystemExit(K.run_writer_cli(main,retry_entrypoint=EPOCH_RETRY_ENTRYPOINT))
