#!/usr/bin/env python3
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
from typing import Any
ROOT=Path(__file__).resolve().parents[1]; ACT=ROOT/"org-runtime/activation.json"; TR=ROOT/"org-runtime/interlock-intr.json"; ORG="StegGhost"
def load(path:Path)->dict[str,Any]:
    value=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value,dict): raise SystemExit(f"object required: {path}")
    return value
def canonical(value:Any)->str: return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()
ATTESTATION_MODULE=ROOT/"org-boundary/runtime/origin_attestation.py"
def origin_attestation_is_bound(t:dict[str,Any])->bool:
    """The attestation binding is declared, and so is what it does not establish.

    `origin_attestation_state` read NOT_PROVEN on every inter-organization
    record this organization wrote, with no code path that could reach anything
    else. This holds the binding to the credential authority that already holds
    the primitive: the declared authority and its two operations, a statement
    the receiver reconstructs rather than one travelling beside its own
    signature, no key material and no verification algorithm here, and an
    unreachable authority refused rather than passed.

    What attestation does not establish must be declared too. It proves the
    authority signed the statement; it does not prove the authority
    authenticated the asker, and claiming otherwise would be the overclaim this
    check exists to refuse.

    This organization's own ceiling is declared as well: the authority's
    resident host is not reachable from here, so the seam exists and every
    crossing emitted today is unattested. Declaring the binding without
    declaring that would be the defect this repository has corrected three
    times already -- a declaration with nothing behind it.
    """
    a=(t.get("egress") or {}).get("origin_attestation")
    if not isinstance(a,dict): return False
    if not ATTESTATION_MODULE.is_file(): return False
    if a.get("credential_authority")!="TV/TVC": return False
    if a.get("sign_operation")!="TV_EXPORT_HMAC_SIGN": return False
    if a.get("verify_operation")!="TV_EXPORT_HMAC_VERIFY": return False
    if a.get("signature_algorithm")!="hmac-sha256": return False
    if a.get("statement_fields")!=["origin_organization","destination_organization",
                                   "destination_service","packet_id","payload_sha256",
                                   "transport_profile"]: return False
    for required in ("statement_reconstructed_by_the_receiver_from_the_packet",
                     "signature_travels_inside_the_packet",
                     "authority_is_asked_to_sign_then_asked_to_verify",
                     "unreachable_authority_is_a_hold_not_a_pass",
                     "offered_attestation_that_failed_refuses_the_emission",
                     "proves_the_authority_signed_the_statement",
                     "initiator_identification_also_requires_the_bilateral_match",
                     "signer_is_supplied_by_the_operator_not_held_here",
                     "every_crossing_emitted_here_today_is_unattested"):
        if a.get(required) is not True: return False
    for forbidden in ("statement_travels_beside_its_signature","boundary_holds_key_material",
                      "verification_algorithm_implemented_here",
                      "proves_the_authority_authenticated_the_asker",
                      "credential_authority_resident_host_available_to_this_organization"):
        if a.get(forbidden) is not False: return False
    # The algorithm must not live here, or this repository becomes a second
    # credential authority, which the TV/TVC split exists to prevent.
    source=ATTESTATION_MODULE.read_text(encoding="utf-8")
    if any(token in source for token in ("import hmac","hmac.new","hashlib.sha256",
                                         "compare_digest")): return False
    return True

def validate()->dict[str,Any]:
    a,t=load(ACT),load(TR); h=t["heartbeat_derived_carrier"]; checks={"activation_owner":a.get("organization")==ORG and a.get("owner_repository")==f"{ORG}/.github","activation_local":a.get("activation_source_scope")=="ORG_DOT_GITHUB_ONLY","runtime_sovereign":a.get("runtime_execution_surface")=="SOVEREIGN_RESIDENT_PROCESS","transport_owner":t.get("organization")==ORG and t.get("owner_repository")==f"{ORG}/.github","all_io_here":t.get("communication_policy")=="ALL_ORGANIZATION_INGRESS_EGRESS_GENERATED_AT_ORG_DOT_GITHUB_BOUNDARY","tvtvc":a.get("credential_authority")=="TV/TVC" and t.get("credential_authority")=="TV/TVC","github_none":a.get("github_token_runtime_authority")=="NONE" and t.get("github_token_runtime_authority")=="NONE","effects_transition_derived":a.get("authority_effect_resolution")=="DERIVED_FROM_APPLICABLE_TRANSITION_ELEMENTS" and t.get("authority_effect_resolution")=="DERIVED_FROM_APPLICABLE_TRANSITION_ELEMENTS","hb_non_authorizing":all(h.get(k) is False for k in ("carrier_grants_admission_authority","carrier_grants_execution_authority","carrier_grants_credential_authority","carrier_grants_routing_authority","carrier_grants_transition_authority","carrier_grants_receiving_authority")),"origin_attestation_is_bound":origin_attestation_is_bound(t)}; return {"schema":"stegverse.organization-boundary-validation/v1","organization":ORG,"checks":checks,"valid":all(checks.values()),"authority_effect":"NONE_VALIDATION_ONLY"}
def activation_request(runtime_id:str)->dict[str,Any]:
    body={"schema":"stegverse.organization-resident-runtime-activation-request/v1","organization":ORG,"runtime_id":runtime_id,"owner_repository":f"{ORG}/.github","state":"REQUESTED","credential_authority":"TV/TVC","request_granted_authority":False,"github_token_runtime_authority":"NONE","authority_transfer_assumed":False,"authority_effect_resolution":"DERIVED_FROM_APPLICABLE_TRANSITION_ELEMENTS"}; return {**body,"request_sha256":canonical(body)}
def envelope(direction:str,peer_org:str,interlock_id:str,payload_sha256:str,transition_elements_ref:str,authority_ref:str|None)->dict[str,Any]:
    if direction not in {"INGRESS","EGRESS"}: raise SystemExit("direction")
    if len(payload_sha256)!=64: raise SystemExit("payload_sha256 must be 64 hex chars")
    body={"schema":"stegverse.organization-intr-envelope/v1","organization":ORG,"boundary_repository":f"{ORG}/.github","direction":direction,"peer_organization":peer_org,"interlock_id":interlock_id,"protocol":"InTr","payload_sha256":payload_sha256.lower(),"transition_elements_ref":transition_elements_ref,"authority_ref":authority_ref,"credential_authority":"TV/TVC","authority_transfer_assumed":False,"authority_effect_resolution":"DERIVED_FROM_APPLICABLE_TRANSITION_ELEMENTS","hb_carrier":{"frequency_hz":100,"period_ms":10,"progression_dependency":"OSCILLATOR_ONLY","authority_effect":"NONE_CARRIER_ONLY"},"github_token_runtime_authority":"NONE"}; return {**body,"envelope_sha256":canonical(body)}
def main()->int:
    p=argparse.ArgumentParser(); sub=p.add_subparsers(dest="cmd",required=True); sub.add_parser("validate"); a=sub.add_parser("activation-request"); a.add_argument("--runtime-id",required=True)
    for name in ("ingress","egress"):
      q=sub.add_parser(name); q.add_argument("--peer-org",required=True); q.add_argument("--interlock-id",required=True); q.add_argument("--payload-sha256",required=True); q.add_argument("--transition-elements-ref",required=True); q.add_argument("--authority-ref")
    ns=p.parse_args(); out=validate() if ns.cmd=="validate" else activation_request(ns.runtime_id) if ns.cmd=="activation-request" else envelope(ns.cmd.upper(),ns.peer_org,ns.interlock_id,ns.payload_sha256,ns.transition_elements_ref,ns.authority_ref); print(json.dumps(out,sort_keys=True)); return 0 if out.get("valid",True) else 1
if __name__=="__main__": raise SystemExit(main())
