#!/usr/bin/env python3
import hashlib, json, uuid
from datetime import datetime, timezone

def _canon(v):
    return json.dumps(v,sort_keys=True,separators=(",",":")).encode()

def _now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def build_ingress(origin,destination,payload,carrier_reference,transition_reference,*,standing,authority_effect="NONE",packet_id=None):
    """Build an ingress envelope. `standing` is required and has no default.

    The same rule `kernel.build_packet` holds to: every ingress class the
    canonical node ingress contract covers requires declared node standing, so
    a standing-less envelope is not something this helper can construct. A
    default here would be the silent defaulting the contract exists to prevent.
    """
    return {
      "schema_version":"stegverse.intr.org-boundary.v1",
      "packet_id":packet_id or str(uuid.uuid4()),
      "direction":"INGRESS",
      "origin":origin,
      "destination":destination,
      "carrier":{"kind":"HB_DERIVED","reference":carrier_reference,"observed_at":_now()},
      "intr_profile":"stegverse.intr.org-boundary.v1",
      "transition":{"reference":transition_reference,"authority_effect":authority_effect,"conditions":[]},
      "payload":payload,
      "standing":standing,
      "evidence":{"ingress_receipt":None,"dispatch_receipt":None,"consumption_receipt":None,"egress_receipt":None,"reconstruction_reference":None}
    }

def build_egress(ingress, execution_result):
    """Build the egress envelope for a consumed ingress.

    The standing travels forward from the request, marked as carried: an egress
    is the far side of one crossing, not a new one, so it declares neither a
    fresh genesis nor a standing of its own.
    """
    payload={"request_packet_id":ingress["packet_id"],"execution_result":execution_result}
    declared=ingress.get("standing")
    if not isinstance(declared,dict):
        raise ValueError("egress-requires-ingress-standing")
    return {
      "schema_version":"stegverse.intr.org-boundary.v1",
      "packet_id":ingress["packet_id"]+":egress",
      "direction":"EGRESS",
      "origin":ingress["destination"],
      "destination":ingress["origin"],
      "carrier":{"kind":ingress["carrier"]["kind"],"reference":ingress["carrier"]["reference"],"observed_at":_now()},
      "intr_profile":ingress["intr_profile"],
      "transition":{"reference":ingress["transition"]["reference"],"authority_effect":ingress["transition"]["authority_effect"],"conditions":ingress["transition"].get("conditions",[])},
      "payload":payload,
      "standing":{**declared,"standing_carried_forward_from_request":True},
      "evidence":{
        "ingress_receipt":execution_result["receipts"][0]["receipt_id"],
        "dispatch_receipt":execution_result["receipts"][1]["receipt_id"],
        "consumption_receipt":execution_result["receipts"][2]["receipt_id"],
        "egress_receipt":execution_result["receipts"][-1]["receipt_id"],
        "reconstruction_reference":execution_result["reconstruction"]["terminal_receipt_id"]
      },
      "payload_hash":hashlib.sha256(_canon(payload)).hexdigest()
    }

def validate_org_crossing(envelope, expected_direction):
    if envelope.get("direction") != expected_direction:
        raise ValueError("wrong-direction")
    # `standing` joins the required set in both directions. Checking it here
    # refuses a standing-less envelope before `process_boundary.py` is run as a
    # subprocess at all; that surface resolves standing itself and is the
    # enforcement, so this is the earlier refusal rather than the only one.
    for key in ("packet_id","origin","destination","carrier","intr_profile","transition","payload","standing","evidence"):
        if key not in envelope:
            raise ValueError("missing-"+key)
    if not isinstance(envelope["standing"],dict):
        raise ValueError("standing-not-declared")
    return True
