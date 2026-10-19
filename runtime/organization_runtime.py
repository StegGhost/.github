#!/usr/bin/env python3
"""Organization-resident runtime boundary for StegGhost."""
from __future__ import annotations
import argparse, base64, hashlib, importlib.util, json
from pathlib import Path
from typing import Any, Mapping
ROOT=Path(__file__).resolve().parents[1]; CONFIG=ROOT/"control/organization-runtime.json"
ACTIVATIONS=ROOT/"runtime/activations"; INGRESS=ROOT/"runtime/ingress"; EGRESS=ROOT/"runtime/egress"
class RuntimeBoundaryError(ValueError): pass
_KSPEC=importlib.util.spec_from_file_location("org_kernel",ROOT/"org-kernel/kernel.py")
kernel=importlib.util.module_from_spec(_KSPEC); _KSPEC.loader.exec_module(kernel)
#: Activation and ingress write receipts, so each references the heartbeat epoch
#: its caller supplies. An absent or invalid one is refused six-field FAIL_CLOSED
#: (kernel.SuppliedEpochRefused) before anything is written; no clock is read.
EPOCH_RETRY_ENTRYPOINT="runtime/organization_runtime.py --hb-epoch"
def supplied_reference(hb_epoch:Any)->dict[str,Any]:
    return kernel.supplied_hb_reference(hb_epoch,retry_entrypoint=EPOCH_RETRY_ENTRYPOINT)
def canon(v:Any)->bytes:return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()
def sha(v:Any)->str:return "sha256:"+hashlib.sha256(v if isinstance(v,bytes) else canon(v)).hexdigest()
def config()->dict[str,Any]:
    v=json.loads(CONFIG.read_text())
    if v.get("organization")!="StegGhost" or v.get("runtime_owner_repo")!="StegGhost/.github": raise RuntimeBoundaryError("runtime owner mismatch")
    if v.get("cross_boundary_communication_requires_interlock_intr") is not True: raise RuntimeBoundaryError("Interlock/InTr disabled")
    if v.get("credential_authority")!="TV/TVC" or v.get("github_actions_runtime_authority")!="NONE": raise RuntimeBoundaryError("authority boundary mismatch")
    return v
def safe_id(v:str)->str:
    if not v or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-" for c in v): raise RuntimeBoundaryError("invalid id")
    return v
def write_once(p:Path,v:Mapping[str,Any])->Path:
    raw=json.dumps(dict(v),sort_keys=True,indent=2,ensure_ascii=False).encode()+b"\n"; p.parent.mkdir(parents=True,exist_ok=True)
    if p.exists():
        if p.read_bytes()==raw:return p
        raise RuntimeBoundaryError("write-once collision")
    kernel.write_atomic(p,raw.decode())  # whole or not at all: never a torn record (B-P36q)
    if p.read_bytes()!=raw: raise RuntimeBoundaryError("write verification failed")
    return p
def activate(activation_id:str,node_ref:str,hb_epoch:Any=None)->dict[str,Any]:
    config(); activation_id=safe_id(activation_id); hb=supplied_reference(hb_epoch)
    r={"schema":"stegverse.organization-runtime-activation/v1","organization":"StegGhost","runtime_owner_repo":"StegGhost/.github","activation_id":activation_id,"node_ref":node_ref,"state":"ACTIVATION_REQUESTED_NOT_OBSERVED","hb_reference":hb,"credential_authority":"TV/TVC","github_actions_runtime_authority":"NONE","heartbeat_grants_execution_authority":False,"request_grants_execution_authority":False,"authority_effect":"NONE_REQUEST_ONLY"}
    r["activation_hash"]=sha(r); write_once(ACTIVATIONS/(activation_id+".json"),r); return r
def egress(message_id:str,operation_id:str,destination:Mapping[str,str],payload:bytes,hb_reference:str|None=None)->dict[str,Any]:
    config(); message_id=safe_id(message_id)
    intent={"schema":"stegverse.universal-intr-transport/v1","protocol":"InTr","operation_id":operation_id,"packet_id":message_id,"payload_hash":sha(payload),"source":{"boundary":"ORGANIZATION","subsystem":"StegGhost:.github"},"destination":dict(destination),"boundary_path":["ORGANIZATION","EXTERNAL_OR_ADJACENT"],"interlock_required":True,"transport_semantics":{"event_triggered":True,"always_on_receiver_required":False,"second_user_device_required":False,"receiver_unavailable_disposition":"DURABLE_QUEUE_OR_EVENT_EPHEMERAL_MATERIALIZATION","exact_packet_transport_retry_allowed":True,"blind_consequence_retry_allowed":False},"authority":{"authority_transfer":False,"transport_grants_execution_authority":False,"credential_authority":"TV/TVC"}}
    env={"schema":"stegverse.organization-interlock-envelope/v1","organization":"StegGhost","direction":"EGRESS","interlock_required":True,"intr_intent":intent,"payload_base64":base64.b64encode(payload).decode(),"hb_reference":hb_reference,"heartbeat_grants_authority":False,"credential_authority":"TV/TVC","authority_effect":"NONE_TRANSPORT_ONLY"}
    env["envelope_hash"]=sha(env); write_once(EGRESS/(message_id+".json"),env); return env
def ingress(env:Mapping[str,Any],hb_epoch:Any=None)->dict[str,Any]:
    config(); hb=supplied_reference(hb_epoch)
    if env.get("schema")!="stegverse.organization-interlock-envelope/v1": raise RuntimeBoundaryError("schema mismatch")
    intent=env.get("intr_intent")
    if not isinstance(intent,Mapping) or intent.get("schema")!="stegverse.universal-intr-transport/v1" or intent.get("protocol")!="InTr": raise RuntimeBoundaryError("InTr invalid")
    body=dict(env); claimed=body.pop("envelope_hash",None)
    if claimed!=sha(body): raise RuntimeBoundaryError("envelope hash mismatch")
    try: raw=base64.b64decode(env.get("payload_base64",""),validate=True)
    except Exception as exc: raise RuntimeBoundaryError("payload invalid") from exc
    if sha(raw)!=intent.get("payload_hash"): raise RuntimeBoundaryError("payload hash mismatch")
    if intent.get("authority",{}).get("transport_grants_execution_authority") is not False: raise RuntimeBoundaryError("transport authority drift")
    r={"schema":"stegverse.organization-interlock-ingress-receipt/v1","organization":"StegGhost","packet_id":intent.get("packet_id"),"payload_hash":intent.get("payload_hash"),"state":"INGRESS_VALIDATED_NOT_EXECUTED","hb_reference":hb,"interlock_validated":True,"intr_validated":True,"execution_authorized":False,"credential_authority":"TV/TVC","authority_effect":"NONE"}
    r["receipt_hash"]=sha(r); write_once(INGRESS/(safe_id(str(intent.get("packet_id")))+".json"),r); return r
def main()->int:
    ap=argparse.ArgumentParser(); sub=ap.add_subparsers(dest="cmd",required=True)
    a=sub.add_parser("activate"); a.add_argument("--activation-id",required=True); a.add_argument("--node-ref",required=True); a.add_argument("--hb-epoch",default=None)
    e=sub.add_parser("egress"); e.add_argument("--message-id",required=True); e.add_argument("--operation-id",required=True); e.add_argument("--destination-boundary",required=True); e.add_argument("--destination-subsystem",required=True); e.add_argument("--payload",required=True); e.add_argument("--hb-reference")
    i=sub.add_parser("ingress"); i.add_argument("--file",type=Path,required=True); i.add_argument("--hb-epoch",default=None)
    x=ap.parse_args()
    try:
        if x.cmd=="activate": r=activate(x.activation_id,x.node_ref,x.hb_epoch)
        elif x.cmd=="egress": r=egress(x.message_id,x.operation_id,{"boundary":x.destination_boundary,"subsystem":x.destination_subsystem},x.payload.encode(),x.hb_reference)
        else:r=ingress(json.loads(x.file.read_text()),x.hb_epoch)
    except kernel.SuppliedEpochRefused as exc:
        print(json.dumps(exc.refusal,sort_keys=True)); return 1
    print(json.dumps(r,sort_keys=True)); return 0
if __name__=="__main__": raise SystemExit(kernel.run_writer_cli(main,retry_entrypoint=EPOCH_RETRY_ENTRYPOINT))
