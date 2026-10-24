#!/usr/bin/env python3
import argparse,hashlib,importlib.util,json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];C=json.loads((ROOT/".stegverse/transition-ledger/contract.json").read_text())
# The heartbeat is the ecosystem's time base; the kernel owns its derivation so
# a receipt and a carrier frame cannot disagree about what an epoch is.
_spec=importlib.util.spec_from_file_location("kernel",ROOT/"org-kernel/kernel.py")
kernel=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(kernel)
# The repository ledger published HEAD with no lock and no atomic replacement,
# so two concurrent appends read one HEAD, bound receipts to the same
# predecessor, and the later HEAD write silently won -- forking the chain and
# orphaning a receipt. The organization ledger above it serializes its append;
# this one addresses the same store so it does too.
_sspec=importlib.util.spec_from_file_location("ledger_store",ROOT/"resident-runtime/ledger_store.py")
ledger_store=importlib.util.module_from_spec(_sspec);_sspec.loader.exec_module(ledger_store)
# allow_nan=False: a non-finite number never reaches a receipt (B-P40 row 2).
def canon(v):return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def sha(v):return "sha256:"+hashlib.sha256(v if isinstance(v,(bytes,bytearray)) else canon(v)).hexdigest()
def lr():
 o=os.getenv("STEGVERSE_REPO_LEDGER_ROOT")
 # A git+<repository>#<ref>[:namespace] locator is the designated durable root.
 # A plain path stays a filesystem root. With neither supplied, XDG_STATE_HOME
 # as the caller set it, else the repo-relative run root; never the host home.
 if o:return ledger_store.parse_locator(o)
 return (kernel.state_home()/"stegverse/repo-ledgers"/C["repository"]).resolve()
# A transition occurring in this repository emits its receipt here. An
# in-process caller needs the same append the CLI performs, with the same lock
# and the same HEAD publication -- a second implementation of this would be a
# second writer to one store, which is the fork this lock exists to prevent.
def recorded(target,head,transition_id,transition_class):
 """The receipt this chain already holds for a transition, walking back from `head`."""
 found=None
 cursor=(head or {}).get("receipt_sha256") if isinstance(head,dict) else None
 while cursor:
  receipt=target.get(ledger_store.receipt_key(cursor))
  if receipt is None: return found
  if found is None and receipt.get("transition_id")==transition_id and receipt.get("transition_class")==transition_class: found=receipt
  cursor=receipt.get("previous_receipt_sha256")
 return found
_ABSENT=object()
# The receipt references the epoch its caller supplies. An absent or invalid one
# is refused six-field FAIL_CLOSED before the store is opened; no clock is read
# to stand in for it (StegVerse-Labs/.github@bc608a3, WU-B13a).
EPOCH_RETRY_ENTRYPOINT=".stegverse/transition-ledger/emit.py::append (hb_epoch=, or --hb-epoch)"
RepoLedgerEpochRefused=kernel.SuppliedEpochRefused
def append(transition_id,transition_class,predecessor_state_sha256,successor_state_sha256,evidence=None,authority_effect="NONE",hb_epoch=None,idempotent_on=None,hb_carried=None):
 """Append one repository transition receipt and publish HEAD atomically.

 With `idempotent_on` (a tuple of evidence keys) a transition the chain already
 records is returned rather than minted again. Identity is the transition id
 and class. An exact retry must also carry the same predecessor state,
 successor state, authority effect and named evidence fields, or the call
 refuses with `ledger_receipt_collision`. The heartbeat reference is not
 compared: a retry legitimately arrives at another epoch.

 `hb_epoch` is required. An absent or invalid epoch raises
 `RepoLedgerEpochRefused` carrying the six-field refusal, and nothing is written.
 With `hb_carried` the reference carries that CARRIED claim, verified against
 the organization's current ledger head or refused CARRIED_PROVENANCE_UNVERIFIED.
 """
 hb=kernel.supplied_hb_reference(hb_epoch,retry_entrypoint=EPOCH_RETRY_ENTRYPOINT,carried=hb_carried,root=ROOT)
 # The committed request this run answers rides in the receipt (B-P40 clause b);
 # a half-set or malformed pair raises kernel.CommittedRequestInvalid, nothing written.
 request=kernel.committed_request()
 # Only that pair sets committed_request; the key inside caller evidence, at
 # any depth, is refused before anything is opened (kernel.CommittedRequestForged).
 kernel.refuse_caller_committed_request(evidence,argument="evidence")
 # A store-phase fault is this repository's, never the transition's (F-TRANSIENT-RT).
 with kernel.ledger_write(EPOCH_RETRY_ENTRYPOINT):
  store=ledger_store.open_store(lr());store.initialize()
  with store.exclusive():
   head=store.get(ledger_store.HEAD_KEY);prev=(head or {}).get("receipt_sha256")
   if idempotent_on is not None:
    prior=recorded(store,head,transition_id,transition_class)
    if prior is not None:
     mine=evidence if isinstance(evidence,dict) else {}; theirs=prior.get("evidence") if isinstance(prior.get("evidence"),dict) else {}
     if (prior.get("predecessor_state_sha256")!=predecessor_state_sha256
         or prior.get("successor_state_sha256")!=successor_state_sha256
         or prior.get("authority_effect")!=authority_effect
         or any(theirs.get(k,_ABSENT)!=mine.get(k,_ABSENT) for k in idempotent_on)):
      raise ValueError("ledger_receipt_collision")
     return prior
   b={"schema":"stegverse.repo-transition-receipt/v1","repository":C["repository"],"transition_id":transition_id,"transition_class":transition_class,"predecessor_state_sha256":predecessor_state_sha256,"successor_state_sha256":successor_state_sha256,"evidence":evidence if evidence is not None else {},"authority_effect":authority_effect,"hb_reference":hb,"previous_receipt_sha256":prev}
   if request is not None:b["committed_request"]=request
   dg=sha(b);r={**b,"receipt_sha256":dg};key=ledger_store.receipt_key(dg)
   # One substrate transaction: a fault before HEAD names the receipt rolls the
   # receipt back, so a failed append leaves no orphan for a retry to duplicate.
   if not store.append_transaction(key,r,head,{"repository":C["repository"],"receipt_sha256":dg,"receipt_path":store.locator(key)}):raise SystemExit("REPO_LEDGER_APPEND_CONTENTION_EXHAUSTED")
  return r
def main():
 p=argparse.ArgumentParser();p.add_argument("--transition-id",required=True);p.add_argument("--transition-class",required=True);p.add_argument("--predecessor-state-sha256",required=True);p.add_argument("--successor-state-sha256",required=True);p.add_argument("--evidence-json",default="{}");p.add_argument("--authority-effect",default="NONE");p.add_argument("--hb-epoch",default=None,help="supplied heartbeat epoch (ASCII digits, >= 32); refused FAIL_CLOSED when absent, never read from a clock");a=p.parse_args()
 evidence=kernel.read_input_json(a.evidence_json,argument="--evidence-json",retry_entrypoint=EPOCH_RETRY_ENTRYPOINT,inline=True)
 try:r=append(a.transition_id,a.transition_class,a.predecessor_state_sha256,a.successor_state_sha256,evidence,a.authority_effect,a.hb_epoch)
 except (RepoLedgerEpochRefused,kernel.LedgerWriteFailed) as exc:
  print(json.dumps(exc.refusal,sort_keys=True));raise SystemExit(1)
 print(json.dumps(r,sort_keys=True))
if __name__=="__main__":raise SystemExit(kernel.run_writer_cli(main,retry_entrypoint=EPOCH_RETRY_ENTRYPOINT))
