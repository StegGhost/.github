#!/usr/bin/env python3
import json, subprocess, tempfile
from pathlib import Path
reg=json.loads(Path("org-boundary/registry/services.json").read_text())
svc=next(s["service_id"] for s in reg["services"] if s.get("boundary_role")=="BOUNDARY_LOCAL_DIAGNOSTIC")
env={"schema_version":"test","packet_id":"pkt-001","direction":"INGRESS","origin":{"org":"peer","service":"peer.boundary-diagnostic"},"destination":{"org":reg["organization"],"service":svc},"carrier":{"kind":"HB_DERIVED","reference":"HB-test"},"intr_profile":"stegverse.intr.org-boundary.v1","transition":{"reference":"test","authority_effect":"NONE"},"payload":{"probe":"ping"},"evidence":{"ingress_receipt":None,"dispatch_receipt":None,"consumption_receipt":None,"egress_receipt":None,"reconstruction_reference":None}}
with tempfile.TemporaryDirectory() as td:
 p=Path(td); (p/"in.json").write_text(json.dumps(env)); subprocess.run(["python3","org-boundary/runtime/process_boundary.py","--envelope",str(p/"in.json"),"--out",str(p/"out.json")],check=True)
 out=json.loads((p/"out.json").read_text()); assert out["consumed"] is True; assert out["reconstruction"]["status"]=="RECONSTRUCTED"; assert out["authority_effect"]=="NONE"
print("PASS")
