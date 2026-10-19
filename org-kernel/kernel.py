#!/usr/bin/env python3
"""Universal StegVerse organization resident kernel.

Organization-neutral runtime behavior extracted from StegVerse-Labs/.github.
Authority and time are constraint variables. A disposition is transition evidence only.
"""
from __future__ import annotations
import base64, hashlib, importlib.util, json, os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

HB_ANCHOR_EPOCH=32
HB_ANCHOR_UNIX_NS=1_787_511_600_000_000_000
HB_PERIOD_NS=10_000_000
HB_HZ=100
CHANNEL_COUNT=16
SCHEMA="stegverse.org-resident-kernel/v1"
CARRIER_SCHEMA="stegverse.org-resident-kernel.carrier/v1"
PACKET_SCHEMA="stegverse.intr.org-boundary.v1"

def canon(v:Any)->bytes:
    return json.dumps(v,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False).encode()

def sha(v:Any)->str:
    raw=v if isinstance(v,(bytes,bytearray)) else canon(v)
    return "sha256:"+hashlib.sha256(bytes(raw)).hexdigest()

def validate_hb_reference(ref:dict[str,Any])->dict[str,Any]:
    """A heartbeat reference is part of what a frame or a receipt asserts.

    `recover_packet` verified the frame and packet digests but never the
    reference, so an incoherent or fabricated epoch rode through a validly
    digested frame unchallenged.
    """
    if not isinstance(ref,dict): raise ValueError("heartbeat_reference_invalid")
    epoch=ref.get("epoch")
    if not isinstance(epoch,int) or isinstance(epoch,bool) or epoch<HB_ANCHOR_EPOCH:
        raise ValueError("heartbeat_epoch_invalid")
    if ref.get("generation")!=epoch: raise ValueError("heartbeat_generation_mismatch")
    if ref.get("heartbeat_id")!=f"HB:{epoch}": raise ValueError("heartbeat_id_mismatch")
    if ref.get("frequency_hz")!=HB_HZ: raise ValueError("heartbeat_frequency_mismatch")
    if ref.get("progression_dependency")!="OSCILLATOR_ONLY":
        raise ValueError("heartbeat_progression_not_oscillator")
    return ref

def hb_reference(now_ns:int|None=None, *, epoch:int|None=None)->dict[str,Any]:
    """Build a heartbeat reference.

    Progression is OSCILLATOR_ONLY: the epoch is a count of heartbeat periods,
    not a reading of a wall clock. Supply `epoch` where the tick is available
    and the reference is reproducible, so the same packet at the same epoch
    yields the same digest -- which is what lets a ledger receipt be replayed.

    Deriving the epoch from a host clock instead makes the reference depend on
    that host's clock discipline: an NTP step moves or reverses it, and two
    nodes with skewed clocks assign different epochs to one event. A derived
    reference therefore says so in `derived_from_clock` and carries the sample
    it came from, rather than reading as though a tick had been observed.
    """
    if epoch is not None:
        if now_ns is not None: raise ValueError("supply_epoch_or_sample_not_both")
        if not isinstance(epoch,int) or isinstance(epoch,bool) or epoch<HB_ANCHOR_EPOCH:
            raise ValueError("epoch_precedes_hb32_anchor")
        return validate_hb_reference({"epoch":epoch,"generation":epoch,"heartbeat_id":f"HB:{epoch}",
                "phase_offset_ns":0,"frequency_hz":HB_HZ,"progression_dependency":"OSCILLATOR_ONLY",
                "derived_from_clock":False,"authority_effect":"NONE"})
    if now_ns is None:
        now_ns=int(datetime.now(timezone.utc).timestamp()*1_000_000_000)
    if now_ns<HB_ANCHOR_UNIX_NS:
        raise ValueError("sample_precedes_hb32_anchor")
    q,phase=divmod(now_ns-HB_ANCHOR_UNIX_NS,HB_PERIOD_NS)
    epoch=HB_ANCHOR_EPOCH+q
    return validate_hb_reference({"epoch":epoch,"generation":epoch,"heartbeat_id":f"HB:{epoch}",
            "sampled_unix_ns":now_ns,"phase_offset_ns":phase,"frequency_hz":HB_HZ,
            "progression_dependency":"OSCILLATOR_ONLY","derived_from_clock":True,
            "authority_effect":"NONE"})

HB_EPOCH_NOT_SUPPLIED="HB_EPOCH_NOT_SUPPLIED"
HB_EPOCH_INVALID="HB_EPOCH_INVALID"
HB_EPOCH_PROVENANCE_UNMARKED="HB_EPOCH_PROVENANCE_UNMARKED"
HB_EPOCH_PREDICATE="SUBMISSION_CARRIES_THE_SUPPLIED_HB_EPOCH"
HB_EPOCH_OWNING_EXISTING_GOAL="INTERLOCK-INTR-RUNTIME-INDEPENDENT-PROTOCOL-001"

def supplied_epoch_failure(hb_epoch: Any, reference: Any = None) -> tuple[str, str] | None:
    """The shared supplied-epoch rule (SUBMISSION_CARRIES_THE_SUPPLIED_HB_EPOCH).

    Byte-identical in StegVerse-org/.github#185 and StegVerse-Labs/.github#3212
    and #3213. `hb_epoch` absent (None) is HB_EPOCH_NOT_SUPPLIED. Otherwise it
    must be ASCII [0-9]+ only -- an int is read as its decimal text; a bool, a
    float or anything coerced ('+33', ' 33', '3_3', '33.0') is refused -- with
    integer value >= 32 (the HB32 anchor). `reference`, the carrier frame's
    heartbeat reference when there is one, must be an object, and a
    `derived_from_clock` it carries must be exactly false. Any failure is
    HB_EPOCH_INVALID. Returns (failure_code, detail), or None when the epoch is
    supplied. No clock is read.
    """
    if reference is not None and not isinstance(reference, dict):
        return "HB_EPOCH_INVALID", "the carrier's heartbeat reference is not an object"
    if hb_epoch is None:
        return "HB_EPOCH_NOT_SUPPLIED", "no hb_epoch was supplied and no clock is read"
    if isinstance(hb_epoch, bool):
        text = None
    elif isinstance(hb_epoch, int):
        text = str(hb_epoch)
    elif isinstance(hb_epoch, str):
        text = hb_epoch
    else:
        text = None
    if text is None or not text.isascii() or not text.isdigit():
        return "HB_EPOCH_INVALID", "hb_epoch " + repr(hb_epoch) + " is not ASCII [0-9]+"
    if int(text) < 32:
        return "HB_EPOCH_INVALID", "hb_epoch " + text + " is below the HB32 anchor (32)"
    if reference is not None and "derived_from_clock" in reference \
            and reference["derived_from_clock"] is not False:
        return "HB_EPOCH_INVALID", ("the carrier's derived_from_clock is not exactly false; "
                                    "a clock-derived epoch is not a supplied one")
    if reference is not None and "sampled_unix_ns" in reference: return "HB_EPOCH_INVALID", "the carrier's heartbeat reference carries sampled_unix_ns; a sampled clock value is CLOCK, never a supplied epoch"
    if reference is not None and "derived_from_clock" not in reference: return "HB_EPOCH_PROVENANCE_UNMARKED", "the carrier's heartbeat reference carries no derived_from_clock; an unmarked clock value is laundering, and a carrier cannot self-assert CARRIED provenance"
    return None

#: sha256(inspect.getsource(supplied_epoch_failure).encode()) of the FINAL shared
#: rule, StegVerse-Labs/.github#3282 @e1b3ac8. Pinned so a local edit is caught.
SHARED_VALIDATOR_SHA256="ad8ff52936d5bcd9a2ad6caceb2d9a637a099518989b34bbb3370301c7a4cce2"

class SuppliedEpochRefused(ValueError):
    """A receipt writer's refusal of an absent or invalid supplied epoch.

    `refusal` is the six-field FAIL_CLOSED from `writer_epoch_refusal`. Raised
    before anything is written; no clock is read to stand in for the epoch.
    """
    def __init__(self, refusal:dict[str,Any])->None:
        super().__init__(refusal["failure_code"]+": "+refusal["detail"])
        self.disposition=refusal["disposition"]
        self.failed_predicate=refusal["failed_predicate"]
        self.refusal=dict(refusal)

def writer_epoch_refusal(hb_epoch:Any, *, retry_entrypoint:str, reference:Any=None)->dict[str,Any]|None:
    """The six-field FAIL_CLOSED of a receipt writer's epoch, or None when it is supplied.

    A receipt references the heartbeat epoch its caller supplies, checked by
    `supplied_epoch_failure`; an absent one is HB_EPOCH_NOT_SUPPLIED and is
    never derived from a clock. Ported from StegVerse-Labs/.github@bc608a3 (WU-B13a).
    """
    failure=supplied_epoch_failure(hb_epoch,reference)
    if failure is None:
        return None
    code,detail=failure
    return {"disposition":"FAIL_CLOSED","failure_code":code,"failed_predicate":HB_EPOCH_PREDICATE,
            "detail":detail,
            "required_evidence_or_repair":("the caller supplies hb_epoch= (or --hb-epoch): ASCII digits with "
                                           "value >= "+str(HB_ANCHOR_EPOCH)+"; it is never derived from a clock"),
            "retry_entrypoint":retry_entrypoint,
            "owning_existing_goal":HB_EPOCH_OWNING_EXISTING_GOAL,
            "next_attempt":"call again with the supplied epoch; nothing was written",
            "derived_from_clock":False,"consequence_committed":False}

def frame_supplied_epoch(frame:Any)->int|None:
    """The validated epoch an inbound frame carries, or None when it has none.

    A frame whose heartbeat reference is a supplied epoch (derived_from_clock
    exactly false, passing the shared rule) lends that epoch to everything done
    in response to it, so a response is never stamped from a clock. A
    clock-derived, unmarked or CARRIED-only reference lends nothing.
    """
    ref=frame.get("heartbeat_reference") if isinstance(frame,dict) else None
    if not isinstance(ref,dict) or ref.get("derived_from_clock") is not False:
        return None
    if any(field in ref for field in CARRIED_CLAIM_FIELDS):
        return None
    if supplied_epoch_failure(ref.get("epoch"),ref) is not None:
        return None
    try:
        validate_hb_reference(dict(ref))
    except ValueError:
        return None
    return int(str(ref["epoch"]))

def supplied_hb_reference(hb_epoch:Any, *, retry_entrypoint:str, carried:Any=None,
                          root:Path|None=None)->dict[str,Any]:
    """The heartbeat reference of a supplied epoch, or SuppliedEpochRefused. No clock is read.

    With `carried` ({"source", "head_receipt_sha"}) the reference reads CARRIED:
    the claim is verified against this organization's current verified ledger
    head under `root` first, and refused six-field CARRIED_PROVENANCE_UNVERIFIED
    when it does not verify. It is never stripped to a bare supplied stamp.
    """
    refusal=writer_epoch_refusal(hb_epoch,retry_entrypoint=retry_entrypoint)
    if refusal is not None:
        raise SuppliedEpochRefused(refusal)
    reference=hb_reference(epoch=int(str(hb_epoch)))
    if carried is None:
        return reference
    if not isinstance(carried,dict) or set(carried)!={"source","head_receipt_sha"}:
        failure="a CARRIED claim names exactly source and head_receipt_sha"
    else:
        reference={**reference,"source":carried["source"],"head_receipt_sha":carried["head_receipt_sha"]}
        failure=("no root to verify the CARRIED claim against" if root is None
                 else carried_claim_failure(Path(root),reference))
    if failure is not None:
        raise SuppliedEpochRefused({**writer_epoch_refusal(None,retry_entrypoint=retry_entrypoint),
                                    "failure_code":CARRIED_PROVENANCE_UNVERIFIED,"detail":failure,
                                    "required_evidence_or_repair":("a CARRIED claim naming this organization's "
                                                                   "current verified ledger head at its epoch"),
                                    "next_attempt":"supply a claim that verifies, or a plain supplied epoch; nothing was written"})
    return reference

def derive_channel(payload_hash:str)->dict[str,Any]:
    if not isinstance(payload_hash,str) or not payload_hash.startswith("sha256:") or len(payload_hash)!=71:
        raise ValueError("payload_hash_invalid")
    slot=int(payload_hash[7:23],16)%CHANNEL_COUNT
    return {"channel_id":f"HB:H1:P{slot}","phase_slot":slot,"phase_slot_count":CHANNEL_COUNT,
            "derivation":"PAYLOAD_SHA256_FIRST64_MOD_16","authority_effect":"NONE_CARRIER_ONLY"}

def carrier_frame(packet:dict[str,Any], *, now_ns:int|None=None, epoch:int|None=None)->dict[str,Any]:
    raw=canon(packet); payload_hash=sha(packet.get("payload",{})); ref=hb_reference(now_ns,epoch=epoch); channel=derive_channel(payload_hash)
    body={"schema":CARRIER_SCHEMA,"packet_id":packet["packet_id"],"packet_sha256":sha(raw),
          "packet_base64":base64.b64encode(raw).decode("ascii"),"heartbeat_reference":ref,
          "channel":channel,"origin_org":packet["origin"]["org"],"destination_org":packet["destination"]["org"],
          "intr_profile":packet["intr_profile"],"authority_effect":"NONE_CARRIER_ONLY"}
    return {**body,"frame_sha256":sha(body)}

def recover_packet(frame:dict[str,Any])->dict[str,Any]:
    body=dict(frame); claimed=body.pop("frame_sha256",None)
    if claimed!=sha(body): raise ValueError("carrier_frame_hash_mismatch")
    raw=base64.b64decode(frame["packet_base64"].encode("ascii"),validate=True)
    if sha(raw)!=frame["packet_sha256"]: raise ValueError("packet_hash_mismatch")
    packet=json.loads(raw)
    if packet["packet_id"]!=frame["packet_id"]: raise ValueError("packet_id_mismatch")
    if packet["destination"]["org"]!=frame["destination_org"]: raise ValueError("destination_org_mismatch")
    return packet

def receipt(kind:str, packet_id:str, subject:str, previous:str|None, detail:dict[str,Any])->dict[str,Any]:
    body={"kind":kind,"packet_id":packet_id,"subject":subject,"previous_receipt_id":previous,"detail":detail}
    rid=kind.lower()+"-"+hashlib.sha256(canon(body)).hexdigest()[:24]
    return {**body,"receipt_id":rid,"evidence_hash":sha(body)}

def load_registry(root:Path)->dict[str,Any]:
    return json.loads((root/"org-boundary/registry/services.json").read_text())

def node_standing(root:Path):
    """Load the organization's node-standing module from its boundary runtime.

    Standing is a precondition of ingress, not a capability, so it resolves here
    rather than being something a crossing can be addressed to. Resolved from the
    dispatch root because this kernel is organization-neutral, and a root without
    it fails closed: a boundary that cannot validate the predecessor it is
    required to carry must not admit a crossing claiming one.
    """
    path=root/"org-boundary/runtime/node_standing.py"
    if not path.is_file(): raise ValueError("org_boundary_node_standing_missing")
    spec=importlib.util.spec_from_file_location("node_standing",path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def manifest_selection(root:Path):
    """Load this organization's processing-selection surface from its root.

    Resolved from the dispatch root for the same reason `node_standing` is, and
    fail-closed for the same reason: a boundary that cannot state how processing
    was selected must not dispatch. `SDK-GENERIC-MANIFEST-ECOSYSTEM-INVARIANT-005`
    requires every processing action to be manifest-driven, so a root with no
    selection surface cannot satisfy the invariant and must not pretend to.
    """
    path=root/"org-boundary/runtime/manifest_selection.py"
    if not path.is_file(): raise ValueError("org_boundary_manifest_selection_missing")
    spec=importlib.util.spec_from_file_location("manifest_selection",path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def emission_chain_disclosure(root:Path):
    """Load this organization's emission-chain disclosure surface from its root.

    Resolved from the dispatch root for the same reason `node_standing` is: the
    kernel is organization-neutral and runs against whichever root it is handed.
    Unlike `node_standing` a missing module is not fail-closed, because serving
    a disclosure is this organization's offer rather than a precondition of
    ingress -- a root that does not carry one answers that no disclosure is
    available, which is what a peer must be told.
    """
    path=root/"org-boundary/runtime/emission_chain_disclosure.py"
    if not path.is_file(): return None
    spec=importlib.util.spec_from_file_location("emission_chain_disclosure",path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

#: The boundary role whose dispatch resolves a bound capability's address.
#:
#: The role vocabulary is this kernel's, as `BOUNDARY_LOCAL_DIAGNOSTIC` and
#: `BOUNDARY_LOCAL_CONTROL` already are. `capability_ingress.ROLE` is that
#: module's assertion of which role it serves. A resolver serving a role the
#: kernel never dispatches would be unreachable.
CAPABILITY_INGRESS_ROLE="BOUNDARY_LOCAL_CAPABILITY_INGRESS"

def capability_ingress(root:Path):
    """Load the organization's capability-ingress module from its boundary runtime.

    A registered capability is bound to a receiving operation in the
    organization's own overlay. This resolves the address to that operation.
    Loaded only when a capability address is dispatched: a root that never
    serves one is not defective for having no resolver until it is addressed.
    """
    path=root/"org-boundary/runtime/capability_ingress.py"
    if not path.is_file(): raise ValueError("org_boundary_capability_ingress_missing")
    spec=importlib.util.spec_from_file_location("capability_ingress",path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def carried_standing(request_packet:dict[str,Any])->dict[str,Any]:
    """Carry a request's standing onto its response, unchanged and marked as carried.

    A response is not a new crossing and has no standing of its own to establish,
    so the only truthful options are to carry the request's standing forward or
    to refuse.
    """
    declared=request_packet.get("standing")
    if not isinstance(declared,dict): raise ValueError("response_requires_request_standing")
    return {**declared,"standing_carried_forward_from_request":True}

def dispatch(root:Path, packet:dict[str,Any], *, mesh_root:Path|None=None,
             hb_epoch:int|None=None, hb_carried:dict[str,Any]|None=None)->dict[str,Any]:
    registry=load_registry(root)
    if packet["destination"]["org"]!=registry["organization"]: raise ValueError("wrong_destination_org")
    service=next((s for s in registry["services"] if s["service_id"]==packet["destination"]["service"]),None)
    if service is None: raise ValueError("unknown_service")
    # Resolved before any receipt is minted, and before the role branch, because
    # the contract covers every ingress class rather than every boundary role.
    # Refused as the contract's own disposition rather than a bare error, so a
    # caller is never left guessing which of ALLOW/DENY/FAIL_CLOSED it earned.
    standing_module=node_standing(root)
    try:
        standing=standing_module.require(standing_module.load_contract(root),packet)
    except SystemExit as refused:
        raise ValueError("node_standing_refused:"+str(refused)) from None
    role=service.get("boundary_role")
    if role not in {"BOUNDARY_LOCAL_DIAGNOSTIC","BOUNDARY_LOCAL_CONTROL",CAPABILITY_INGRESS_ROLE}:
        raise ValueError("endpoint_adapter_not_installed")
    # Processing is selected by the admitted manifest, not by the addressed row.
    # Resolved before any receipt is minted: a dispatch that cannot state how
    # processing was selected must not leave a chain implying it was consumed,
    # and a declaration the service does not admit must not be completed under
    # whichever processor the addressed row happened to name.
    try:
        selected=manifest_selection(root).select_processing(service,packet["payload"])
    except SystemExit as refused:
        raise ValueError("manifest_selection_refused:"+str(refused)) from None
    prev=None; receipts=[]
    for kind in ("INGRESS_ACCEPTED","DISPATCHED","CONSUMED","RESULT_BOUND","EGRESS_EMITTED"):
        r=receipt(kind,packet["packet_id"],service["service_id"],prev,{"payload_hash":sha(packet["payload"])})
        receipts.append(r); prev=r["receipt_id"]
    if role=="BOUNDARY_LOCAL_CONTROL":
        application_result=handle_control_message(root,packet,registry,hb_epoch=hb_epoch,hb_carried=hb_carried)
    elif role==CAPABILITY_INGRESS_ROLE:
        # The address resolves to the receiving operation the overlay binds.
        # That operation records both ledger levels itself. This kernel's
        # receipt chain stays in the execution result; it is not a second
        # ledger append for the same frame. A refusal here is this boundary's
        # refusal, not a consumed crossing with the refusal buried in the
        # application result. Loaded only for this role.
        try:
            application_result=capability_ingress(root).receive(
                root,service,packet,registry=registry,mesh_root=mesh_root,hb_epoch=hb_epoch,
                hb_carried=hb_carried)
        except SystemExit as refused:
            raise ValueError("capability_ingress_refused:"+str(refused)) from None
    else:
        application_result={"echo":packet["payload"]}
    return {"schema_version":SCHEMA,"organization":registry["organization"],"packet_id":packet["packet_id"],
            "service_id":service["service_id"],"consumed":True,"application_result":application_result,
            **selected,**standing,
            "authority_effect":packet["transition"]["authority_effect"],"receipts":receipts,
            "reconstruction":{"same_execution_required":True,"status":"RECONSTRUCTED","terminal_receipt_id":prev}}

def persist_outbox(root:Path, frame:dict[str,Any])->Path:
    out=root/"resident-runtime/federation/outbox"; out.mkdir(parents=True,exist_ok=True)
    path=out/(hashlib.sha256(frame["packet_id"].encode()).hexdigest()+".json")
    if path.exists():
        if json.loads(path.read_text())!=frame: raise ValueError("write_once_collision")
        return path
    path.write_text(json.dumps(frame,indent=2,sort_keys=True)+"\n")
    return path

#: Fields by which a carrier reference claims CARRIED provenance. A carrier
#: cannot self-assert CARRIED: a claim is verified against this organization's
#: current verified ledger head or the frame is refused, never stripped (B-P36k).
CARRIED_CLAIM_FIELDS=("source","head_receipt_sha","provenance")
CARRIED_SOURCE="ORGANIZATION_LEDGER_HEAD"
CARRIED_PROVENANCE_UNVERIFIED="CARRIED_PROVENANCE_UNVERIFIED"
HB_EPOCH_CONFLICT="HB_EPOCH_CONFLICT"
FRAME_REFUSED_QUARANTINED="FRAME_REFUSED_QUARANTINED"
FRAME_PREDICATE="FRAME_CARRIES_A_SUPPLIED_OR_VERIFIED_HEARTBEAT_REFERENCE"
INGEST_RETRY_ENTRYPOINT="org-kernel/kernel.py::ingest_frame"
RESPONSE_RETRY_ENTRYPOINT="org-kernel/kernel.py::consume_and_respond (hb_epoch=)"

def carried_claim_failure(root:Path, ref:dict[str,Any])->str|None:
    """Why a CARRIED claim does not verify against the current organization ledger head, or None.

    Read-only: the ledger is opened without initializing it and nothing is written.
    """
    if ref.get("source")!=CARRIED_SOURCE:
        return "source "+repr(ref.get("source"))+" is not "+CARRIED_SOURCE
    path=root/"resident-runtime/aggregate_repo_transition.py"
    if not path.is_file():
        return "this root carries no organization ledger to verify the claim against"
    try:
        spec=importlib.util.spec_from_file_location("carried_claim_org_ledger",path)
        ledger=importlib.util.module_from_spec(spec); spec.loader.exec_module(ledger)
        store=ledger.open_store(ledger.ledger_root())
        head_sha=ledger._validate_existing_head(store)
        head=store.get(ledger.receipt_key(head_sha)) if head_sha else None
    except (SystemExit,Exception) as error:
        return "the organization ledger head is not verifiable: "+type(error).__name__+": "+str(error)
    if head is None or ref.get("head_receipt_sha")!=head_sha:
        return "head_receipt_sha "+repr(ref.get("head_receipt_sha"))+" is not the current organization ledger head"
    head_ref=head.get("hb_reference")
    if not isinstance(head_ref,dict) or supplied_epoch_failure(head_ref.get("epoch"),head_ref) is not None:
        return "the organization ledger head's epoch is not a supplied one"
    if ref.get("epoch")!=head_ref["epoch"]:
        return "the reference's epoch is not the organization ledger head's"
    return None

def frame_refusal(root:Path, frame:dict[str,Any])->dict[str,Any]|None:
    """The six-field FAIL_CLOSED refusal of an inbound frame's heartbeat reference, or None.

    Applied at ingest, before dispatch, for every role, from the shared rule's
    own classification (supplied_epoch_failure). Refused: an UNMARKED reference
    (no flag, no sample), a reference that is not an object, and a CARRIED claim
    the rule does not pass or that does not verify against the current verified
    ledger head (CARRIED_PROVENANCE_UNVERIFIED). Anything else the rule fails is
    CLOCK (flag true, or a legacy bare sample): consumed as a frame-only crossing
    pending WU-B13, lending no epoch (CLOCK_FLAGGED_FRAMES_CONSUMED_PENDING_WU_B13).
    No clock is read.
    """
    ref=frame.get("heartbeat_reference")
    code=detail=None
    # The marker is classified by the rule itself, at the anchor epoch, so an
    # unmarked reference is UNMARKED whatever epoch it carries.
    marker=supplied_epoch_failure(HB_ANCHOR_EPOCH,ref if ref is not None else "absent")
    if not isinstance(ref,dict):
        code,detail=marker
    elif any(field in ref for field in CARRIED_CLAIM_FIELDS):
        # The CARRIED claim is judged before any CLOCK classification: with a
        # well-formed epoch, a claim on a clock-form or sampled reference is an
        # unverified claim, not a malformed epoch (GCAT b2328cd).
        failure=supplied_epoch_failure(ref.get("epoch"))
        if failure is None:
            failure=supplied_epoch_failure(ref.get("epoch"),ref)
            if failure is not None and failure[0]!=HB_EPOCH_PROVENANCE_UNMARKED:
                failure=(CARRIED_PROVENANCE_UNVERIFIED,failure[1])
        if failure is not None:
            code,detail=failure
        else:
            unverified=carried_claim_failure(root,ref)
            if unverified is not None:
                code,detail=CARRIED_PROVENANCE_UNVERIFIED,unverified
    elif marker is not None and marker[0]==HB_EPOCH_PROVENANCE_UNMARKED:
        code,detail=marker
    else:
        # Every carrier epoch, clock-flagged or bare-sampled included, passes the
        # shared digit/anchor check; a malformed or missing one is refused, not
        # consumed silently (lead 08:27Z).
        failure=supplied_epoch_failure(ref.get("epoch"))
        if failure is not None:
            code,detail=failure
    # Any reference whose epoch passes must cohere with it: generation and
    # heartbeat_id agree with the epoch whatever the flag (lead 08:35Z), and a
    # supplied one also has the oscillator's frequency and progression (B-P36o).
    if code is None and isinstance(ref,dict) and supplied_epoch_failure(ref.get("epoch")) is None:
        epoch=int(str(ref["epoch"]))
        if ref.get("generation")!=epoch:
            code,detail=HB_REFERENCE_INVALID,"heartbeat_generation_mismatch"
        elif ref.get("heartbeat_id")!="HB:"+str(epoch):
            code,detail=HB_REFERENCE_INVALID,"heartbeat_id_mismatch"
        elif supplied_epoch_failure(ref.get("epoch"),ref) is None:
            try:
                validate_hb_reference(dict(ref))
            except ValueError as incoherent:
                code,detail=HB_REFERENCE_INVALID,str(incoherent)
    if code is None:
        return None
    return ingest_refusal(code,detail)

def ingest_refusal(code:str, detail:str)->dict[str,Any]:
    """The six-field FAIL_CLOSED of a frame refused at ingest."""
    return {"disposition":"FAIL_CLOSED","failure_code":code,"failed_predicate":FRAME_PREDICATE,"detail":detail,
            "required_evidence_or_repair":("the sender re-emits the frame with a supplied heartbeat reference "
                                           "(derived_from_clock false, no sample) or a CARRIED reference naming "
                                           "this organization's current verified ledger head"),
            "retry_entrypoint":INGEST_RETRY_ENTRYPOINT,"owning_existing_goal":HB_EPOCH_OWNING_EXISTING_GOAL,
            "next_attempt":"re-emit under a supplied epoch; nothing was dispatched or written",
            "derived_from_clock":False,"consequence_committed":False}

def ingest_frame(root:Path, frame:dict[str,Any], *, mesh_root:Path|None=None,
                 hb_epoch:int|None=None)->dict[str,Any]:
    packet=recover_packet(frame)
    registry=load_registry(root)
    if frame["destination_org"]!=registry["organization"]:
        return {"status":"IGNORED_NOT_ADDRESSED","packet_id":frame["packet_id"]}
    # An explicit epoch is held to the shared rule whatever the frame says
    # (B-P36l). Refused as the caller's input, not the frame's: nothing is
    # written and the frame is not quarantined.
    if hb_epoch is not None:
        failure=supplied_epoch_failure(hb_epoch)
        if failure is not None:
            return {"status":"REFUSED","packet_id":frame["packet_id"],"quarantine":False,
                    "refusal":ingest_refusal(*failure)}
    # Refused before dispatch, so no role writes anything for it: no receipt,
    # no inbox intake. The fields are never stripped to admit it as supplied.
    refusal=frame_refusal(root,frame)
    if refusal is not None:
        return {"status":"REFUSED","packet_id":frame["packet_id"],"refusal":refusal}
    # The frame's validated epoch is the supplied one for this crossing, so
    # the receiving operation records at it rather than refusing for want of one.
    # A frame without one takes the epoch supplied to this ingestion, if any.
    # A CARRIED claim that verified above names a supplied head epoch, and
    # everything recorded for the crossing carries the claim (B-P36m).
    epoch=frame_supplied_epoch(frame)
    ref=frame.get("heartbeat_reference")
    carried=None
    if epoch is None and isinstance(ref,dict) and any(field in ref for field in CARRIED_CLAIM_FIELDS):
        epoch=int(str(ref["epoch"]))
        carried={"source":ref["source"],"head_receipt_sha":ref["head_receipt_sha"]}
    # Both supplied and disagreeing: neither is chosen over the other. The
    # frame is quarantined (B-P36j), so it does not stall every later cycle.
    if hb_epoch is not None and epoch is not None and int(str(hb_epoch))!=epoch:
        return {"status":"REFUSED","packet_id":frame["packet_id"],
                "refusal":ingest_refusal(HB_EPOCH_CONFLICT,"the supplied hb_epoch "+str(hb_epoch)+
                                         " disagrees with the frame's epoch "+str(epoch))}
    if epoch is None and hb_epoch is not None:
        epoch=int(str(hb_epoch))
    result=dispatch(root,packet,mesh_root=mesh_root,hb_epoch=epoch,hb_carried=carried)
    return {"status":"CONSUMED","packet":packet,"execution_result":result}

__all__=["hb_reference","derive_channel","carrier_frame","recover_packet","dispatch","persist_outbox","ingest_frame",
         "capability_ingress","CAPABILITY_INGRESS_ROLE",
         "supplied_epoch_failure","HB_EPOCH_NOT_SUPPLIED","HB_EPOCH_INVALID","HB_EPOCH_PROVENANCE_UNMARKED",
         "SuppliedEpochRefused","writer_epoch_refusal","supplied_hb_reference","frame_supplied_epoch"]


# --- Federation mesh v1.1 additions ---
FEDERATION_ROOT_ENV="STEGVERSE_ORG_FEDERATION_ROOT"

def federation_root(env:dict[str,str]|None=None)->Path:
    values=os.environ if env is None else env
    override=values.get(FEDERATION_ROOT_ENV)
    if override:
        return Path(override).expanduser().resolve()
    base=Path(values.get("XDG_STATE_HOME",str(Path.home()/".local"/"state")))
    return (base/"stegverse"/"org-federation").resolve()

def publish_frame(frame:dict[str,Any], *, root:Path|None=None)->Path:
    mesh=(root or federation_root()).resolve()
    frames=mesh/"frames.d"
    frames.mkdir(parents=True,exist_ok=True)
    frame_id=hashlib.sha256((frame["packet_id"]+"|"+frame["frame_sha256"]).encode()).hexdigest()
    path=frames/(frame_id+".json")
    if path.exists():
        existing=json.loads(path.read_text())
        if existing!=frame:
            raise ValueError("federation_frame_write_once_collision")
        return path
    path.write_text(json.dumps(frame,indent=2,sort_keys=True)+"\n")
    return path

#: The largest frames.d file the scan reads. A carrier frame is a few KiB; a
#: larger file is refused unread rather than loaded (B-P36p).
FRAME_FILE_MAX_BYTES=1_048_576

def scan_addressed_frames(organization:str, *, root:Path|None=None, seen:set[str]|None=None,
                          include_malformed:bool=False)->list[dict[str,Any]]:
    mesh=(root or federation_root()).resolve()
    frames=mesh/"frames.d"
    if not frames.exists():
        return []
    consumed=seen or set()
    out=[]
    for path in sorted(frames.glob("*.json")):
        if path.name in consumed:
            continue
        # Parsed per file: one unreadable file is that file's outcome, not the
        # scan's, so it never stalls the frames behind it (F-SCAN, B-P36p): a
        # read error, non-UTF-8 bytes, non-JSON, a non-object, or an oversized
        # file. It names no destination, so it is offered only to a caller that
        # quarantines it.
        try:
            if path.stat().st_size>FRAME_FILE_MAX_BYTES:
                raise ValueError("frame_file_oversized:"+str(path.stat().st_size)+">"+str(FRAME_FILE_MAX_BYTES))
            frame=json.loads(path.read_bytes().decode("utf-8"))
            if not isinstance(frame,dict):
                raise ValueError("frame_is_not_an_object:"+type(frame).__name__)
        except Exception as error:
            if include_malformed:
                out.append({"path":str(path),"frame":None,"error":error})
            continue
        if frame.get("destination_org")==organization:
            out.append({"path":str(path),"frame":frame})
    return out

def build_packet(*, origin_org:str, origin_service:str, destination_org:str, destination_service:str,
                 payload:dict[str,Any], standing:dict[str,Any], transition_reference:str="federation.v1",
                 authority_effect:str="NONE", packet_id:str|None=None)->dict[str,Any]:
    """Build an ingress packet. `standing` is required and has no default.

    Every ingress class the contract covers requires canonical node standing, so
    a standing-less packet is not a packet this boundary can construct. A default
    here would be a caller-editable claim, and the contract holds that a
    caller-editable classification does not establish identity.
    """
    pid=packet_id or "pkt-"+hashlib.sha256(canon({
        "origin_org":origin_org,"origin_service":origin_service,"destination_org":destination_org,
        "destination_service":destination_service,"payload":payload,"transition_reference":transition_reference
    })).hexdigest()[:24]
    return {
      "schema_version":PACKET_SCHEMA,
      "packet_id":pid,
      "direction":"INGRESS",
      "origin":{"org":origin_org,"service":origin_service},
      "destination":{"org":destination_org,"service":destination_service},
      "carrier":{"kind":"HB_DERIVED","reference":"org-federation"},
      "intr_profile":"stegverse.intr.org-boundary.v1",
      "transition":{"reference":transition_reference,"authority_effect":authority_effect,"conditions":[]},
      "payload":payload,
      "standing":standing,
      "evidence":{"ingress_receipt":None,"dispatch_receipt":None,"consumption_receipt":None,"egress_receipt":None,"reconstruction_reference":None}
    }

def publish_packet(packet:dict[str,Any], *, root:Path|None=None, now_ns:int|None=None,
                   epoch:int|None=None)->dict[str,Any]:
    frame=carrier_frame(packet,now_ns=now_ns,epoch=epoch)
    path=publish_frame(frame,root=root)
    return {"packet":packet,"frame":frame,"path":str(path)}

def consume_addressed_frames(repo_root:Path, *, mesh_root:Path|None=None, seen:set[str]|None=None)->list[dict[str,Any]]:
    registry=load_registry(repo_root)
    organization=registry["organization"]
    results=[]
    for item in scan_addressed_frames(organization,root=mesh_root,seen=seen):
        result=ingest_frame(repo_root,item["frame"],mesh_root=mesh_root)
        results.append({"path":item["path"],"result":result})
    return results


# --- Ecosystem-wide communication v1.2 additions ---
def organization_slug(organization:str)->str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in organization).strip("-")

def build_ecosystem_packets(*, origin_org:str, origin_service:str, organizations:list[str], standing:dict[str,Any],
                            message_class:str, subject:str, body:dict[str,Any],
                            requested_action:str|None=None, transition_reference:str="ecosystem.communication.v1",
                            authority_effect:str="NONE", communication_id:str|None=None)->dict[str,Any]:
    ordered=sorted(dict.fromkeys(organizations))
    if not ordered:
        raise ValueError("organizations_required")
    comm_id=communication_id or "ecosystem-"+hashlib.sha256(canon({
        "origin_org":origin_org,"origin_service":origin_service,"organizations":ordered,
        "message_class":message_class,"subject":subject,"body":body,
        "requested_action":requested_action,"transition_reference":transition_reference
    })).hexdigest()[:24]
    packets=[]
    for org in ordered:
        service=organization_slug(org)+".org-control"
        payload={
          "communication_id":comm_id,
          "message_class":message_class,
          "subject":subject,
          "body":body,
          "requested_action":requested_action,
          "audience":"ECOSYSTEM",
          "target_organization":org,
          "target_count":len(ordered)
        }
        unclosable=closability_refusal(payload)
        if unclosable is not None:
            # Refused before anything is published: a crossing that could be
            # consumed and never answered is not emitted at all, rather than
            # left for a caller to discover as a response that never arrives.
            raise ValueError(unclosable)
        packet=build_packet(
          origin_org=origin_org,
          origin_service=origin_service,
          destination_org=org,
          destination_service=service,
          payload=payload,
          standing=standing,
          transition_reference=transition_reference,
          authority_effect=authority_effect,
          packet_id=comm_id+":"+organization_slug(org)
        )
        packets.append(packet)
    return {"communication_id":comm_id,"organization_count":len(ordered),"packets":packets}

def publish_ecosystem_message(*, origin_org:str, origin_service:str, organizations:list[str],
                              standing:dict[str,Any], message_class:str, subject:str, body:dict[str,Any],
                              requested_action:str|None=None, transition_reference:str="ecosystem.communication.v1",
                              authority_effect:str="NONE", communication_id:str|None=None,
                              root:Path|None=None, now_ns:int|None=None,
                              repo_root:Path|None=None)->dict[str,Any]:
    built=build_ecosystem_packets(
      origin_org=origin_org,origin_service=origin_service,organizations=organizations,standing=standing,
      message_class=message_class,subject=subject,body=body,requested_action=requested_action,
      transition_reference=transition_reference,authority_effect=authority_effect,
      communication_id=communication_id
    )
    publications=[]
    for packet in built["packets"]:
        published=publish_packet(packet,root=root,now_ns=now_ns)
        if repo_root is not None:
            # Written after the frame is published, because the record is of an
            # emission and carries the frame's digest. Recording it first would
            # claim a crossing that had not happened yet. Write-once, so a
            # replayed publish cannot rewrite what closure recomputes against.
            persist_outbox(repo_root,published["frame"])
        publications.append(published)
    return {"communication_id":built["communication_id"],"organization_count":built["organization_count"],
            "published_count":len(publications),"publications":publications,
            "emissions_recorded":repo_root is not None}

def aggregate_ecosystem_results(communication_id:str, results_by_org:dict[str,list[dict[str,Any]]])->dict[str,Any]:
    rows=[]
    for org,items in sorted(results_by_org.items()):
        matched=[]
        for item in items:
            result=item.get("result") or {}
            packet=result.get("packet") or {}
            payload=packet.get("payload") or {}
            if payload.get("communication_id")==communication_id:
                matched.append(item)
        status="CONSUMED" if any((x.get("result") or {}).get("status")=="CONSUMED" for x in matched) else "NOT_OBSERVED"
        terminal=None
        for x in matched:
            er=(x.get("result") or {}).get("execution_result") or {}
            terminal=(er.get("reconstruction") or {}).get("terminal_receipt_id") or terminal
        rows.append({"organization":org,"status":status,"terminal_receipt_id":terminal})
    consumed=sum(1 for row in rows if row["status"]=="CONSUMED")
    return {"communication_id":communication_id,"organization_count":len(rows),
            "consumed_count":consumed,"pending_count":len(rows)-consumed,
            "complete":consumed==len(rows) and len(rows)>0,"organizations":rows}


# --- Ecosystem control/response v1.3 additions ---
def load_federation_directory(root:Path)->dict[str,Any]:
    path=root/"org-boundary/registry/federation.json"
    value=json.loads(path.read_text())
    if value.get("denominator")!=len(value.get("organizations") or []):
        raise ValueError("federation_directory_denominator_mismatch")
    return value

def resident_status(root:Path, registry:dict[str,Any]|None=None, *, hb_epoch:int|None=None,
                    hb_carried:dict[str,Any]|None=None)->dict[str,Any]:
    reg=registry or load_registry(root)
    activation_path=root/"resident-runtime/activation-manifest.json"
    activation=json.loads(activation_path.read_text()) if activation_path.exists() else {}
    kernel=(activation.get("kernel") or {})
    return {
      "organization":reg["organization"],
      "kernel_version":kernel.get("version"),
      "activation_state":activation.get("state"),
      "registered_service_count":len(reg.get("services") or []),
      "registered_services":[s.get("service_id") for s in reg.get("services") or []],
      "org_control_service":organization_slug(reg["organization"])+".org-control",
      # The supplied epoch when the request carried one; the clock default,
      # marked derived_from_clock true, only for a request that did not.
      "heartbeat_reference":hb_reference() if hb_epoch is None else {**hb_reference(epoch=hb_epoch),**(hb_carried or {})},
      "runtime_observation_claimed":False
    }

def persist_work_request(root:Path, packet:dict[str,Any])->dict[str,Any]:
    payload=packet.get("payload") or {}
    communication_id=payload.get("communication_id")
    inbox=root/"resident-runtime/control/inbox"
    inbox.mkdir(parents=True,exist_ok=True)
    name=hashlib.sha256((packet["packet_id"]+"|"+str(communication_id)).encode()).hexdigest()+".json"
    path=inbox/name
    record={
      "schema_version":"stegverse.ecosystem-work-intake.v1",
      "communication_id":communication_id,
      "packet_id":packet["packet_id"],
      "origin":packet["origin"],
      "destination":packet["destination"],
      "requested_action":payload.get("requested_action"),
      "body":payload.get("body"),
      "transition":packet["transition"],
      "state":"QUEUED_FOR_LOCAL_ADMISSION_EVALUATION",
      "execution_authority_inferred":False,
      "execution_authority_constraint":"CONSTRAINT_VARIABLE",
      "time_constraint":"CONSTRAINT_VARIABLE",
      "disposition_role":"TRANSITION_EVIDENCE_ONLY"
    }
    if path.exists():
        if json.loads(path.read_text())!=record:
            raise ValueError("work_intake_write_once_collision")
    else:
        path.write_text(json.dumps(record,indent=2,sort_keys=True)+"\n")
    return {"state":record["state"],"intake_ref":str(path),"execution_authority_inferred":False}

def handle_control_message(root:Path, packet:dict[str,Any], registry:dict[str,Any], *,
                           hb_epoch:int|None=None, hb_carried:dict[str,Any]|None=None)->dict[str,Any]:
    payload=packet.get("payload") or {}
    message_class=payload.get("message_class")
    result={
      "message_received":True,
      "message_class":message_class,
      "communication_id":payload.get("communication_id"),
      "requested_action":payload.get("requested_action"),
      "execution_authority_inferred":False,
      "execution_authority_effect":packet["transition"]["authority_effect"]
    }
    if message_class=="ecosystem.monitor.request":
        # A consumed request is answered at a supplied epoch or not at all: a
        # clock-flagged frame lends none, and the clock default is not reached.
        if hb_epoch is None:
            result["monitor_status_refusal"]=writer_epoch_refusal(None,retry_entrypoint=INGEST_RETRY_ENTRYPOINT+" (hb_epoch=)")
        else:
            result["monitor_status"]=resident_status(root,registry,hb_epoch=hb_epoch,hb_carried=hb_carried)
    elif message_class=="ecosystem.work.request":
        result["work_intake"]=persist_work_request(root,packet)
    elif message_class=="ecosystem.communication":
        result["communication_acknowledged"]=True
    elif message_class=="ecosystem.emission.disclosure.request":
        # This organization's half of the bilateral match: it answers, from its
        # own chain, whether it records emitting the packet the asker names. The
        # answer is narrow by construction -- one packet id, digests and the
        # recorded destination, never a payload and never another packet.
        surface=emission_chain_disclosure(root)
        body=payload.get("body") or {}
        if surface is None:
            result["emission_disclosure"]={
              "schema":"stegghost.emission-chain-disclosure/v1",
              "disposition":"DISCLOSURE_NOT_AVAILABLE",
              "holds_emission_receipt":False,
              "detail":"this root carries no emission chain disclosure surface",
              "authority_effect":"NONE_DISCLOSURE_ONLY"}
        else:
            result["emission_disclosure"]=surface.disclose(
              root, body.get("request_packet_id"), packet["origin"]["org"])
        result["routing_authority_constraint"]="CONSTRAINT_VARIABLE"
        result["time_constraint"]="CONSTRAINT_VARIABLE"
        result["disposition_role"]="TRANSITION_EVIDENCE_ONLY"
    elif message_class in ACK_CLASSES:
        result["response_acknowledged"]=True
    return result

#: The request classes this boundary answers, each mapped to the acknowledgement
#: it is answered with. `consume_and_respond` responds to exactly these keys, so
#: this is the set a crossing must declare to be closable at all -- which is why
#: emission reads it too rather than keeping a second copy.
RESPONDED_REQUEST_CLASSES={
  "ecosystem.monitor.request":"ecosystem.monitor.response",
  "ecosystem.work.request":"ecosystem.work.ack",
  "ecosystem.communication":"ecosystem.communication.ack",
  # The bilateral match's asking half. Declared here rather than given its own
  # transport because an emission disclosure is a governed request answered by
  # an acknowledgement, which is exactly what this map is: adding it makes the
  # crossing closable by construction, so `closability_refusal` admits it with
  # no special case and `close` correlates it like any other.
  "ecosystem.emission.disclosure.request":"ecosystem.emission.disclosure.response"
}
ACK_CLASSES=frozenset(RESPONDED_REQUEST_CLASSES.values())

def response_message_class(request_class:str|None)->str:
    return RESPONDED_REQUEST_CLASSES.get(request_class or "","ecosystem.communication.ack")

def closability_refusal(payload:dict[str,Any])->str|None:
    """Why this payload's crossing could never close, or None if it can.

    A payload declaring a class outside `RESPONDED_REQUEST_CLASSES` is still
    published, consumed and receipted by the far side -- and never answered. Its
    closure is not pending, which is a crossing still in flight; it is
    unreachable, which is a different state that a pending count cannot express.
    Closure also correlates a response by `communication_id`, so a blank one
    leaves nothing to correlate.

    Both conditions are readable in this organization's own payload before
    anything is published, which is why they are refused here rather than
    discovered as a crossing that never comes back.
    """
    declared=payload.get("message_class")
    if declared not in RESPONDED_REQUEST_CLASSES:
        return ("unclosable_crossing:message_class_is_answered_by_no_acknowledgement:"
                +repr(declared)+"; answered: "+", ".join(sorted(RESPONDED_REQUEST_CLASSES)))
    identifier=payload.get("communication_id")
    if not isinstance(identifier,str) or not identifier.strip():
        return ("unclosable_crossing:closure_correlates_on_communication_id_and_this_payload_declares:"
                +repr(identifier))
    return None

#: The boundary receipt kinds `dispatch` mints, in order.
RECEIPT_KINDS=("INGRESS_ACCEPTED","DISPATCHED","CONSUMED","RESULT_BOUND","EGRESS_EMITTED")

def far_side_receipt_chain(packet_id:str, service_id:str, payload_hash:str)->list[str]:
    """Recompute the receipt chain the far side must have minted for this packet.

    Not a claim about the far side's honesty -- a recomputation. A receipt id is
    derived by `receipt()` from the kind, the packet id, the subject service and
    the payload hash, and every input is something the emitting organization
    already holds: the packet id it minted, the service it addressed from its
    own directory, and the digest of its own payload. So a terminal receipt that
    comes back on a response is checkable rather than carried, and a response
    whose terminal does not recompute did not come from a boundary that ran this
    packet.
    """
    chain,previous=[],None
    for kind in RECEIPT_KINDS:
        rid=receipt(kind,packet_id,service_id,previous,{"payload_hash":payload_hash})["receipt_id"]
        chain.append(rid); previous=rid
    return chain

def build_control_response(request_packet:dict[str,Any], execution_result:dict[str,Any])->dict[str,Any]:
    req_payload=request_packet.get("payload") or {}
    origin_org=request_packet["origin"]["org"]
    local_org=request_packet["destination"]["org"]
    cls=response_message_class(req_payload.get("message_class"))
    payload={
      "communication_id":req_payload.get("communication_id"),
      "message_class":cls,
      "subject":"response:"+str(req_payload.get("subject") or ""),
      "body":{
        "request_packet_id":request_packet["packet_id"],
        "responding_organization":local_org,
        "application_result":execution_result.get("application_result"),
        "receipt_terminal":(execution_result.get("reconstruction") or {}).get("terminal_receipt_id")
      },
      "requested_action":None,
      "audience":"ORIGIN",
      "target_organization":origin_org,
      "target_count":1
    }
    return build_packet(
      origin_org=local_org,
      origin_service=organization_slug(local_org)+".org-control",
      destination_org=origin_org,
      destination_service=organization_slug(origin_org)+".org-control",
      payload=payload,
      standing=carried_standing(request_packet),
      transition_reference=str((request_packet.get("transition") or {}).get("reference") or "ecosystem.communication.v1")+".response",
      authority_effect="NONE",
      packet_id=str(req_payload.get("communication_id"))+":response:"+organization_slug(local_org)
    )

def consume_and_respond(repo_root:Path, *, mesh_root:Path|None=None, seen:set[str]|None=None,
                        now_ns:int|None=None, hb_epoch:int|None=None)->list[dict[str,Any]]:
    registry=load_registry(repo_root)
    organization=registry["organization"]
    durable_seen=federation_seen_frame_names(repo_root)
    effective_seen=set(seen or set())|durable_seen
    out=[]
    for item in scan_addressed_frames(organization,root=mesh_root,seen=effective_seen,include_malformed=True):
        if item["frame"] is None:
            # An unreadable file is quarantined by its filename (F-SCAN).
            result={"status":"REFUSED","packet_id":None,"refusal":{
                **ingest_refusal(FRAME_INGEST_FAILED,str(item["error"])),"failed_predicate":type(item["error"]).__name__}}
            marker=str(mark_federation_frame_seen(repo_root,item["path"],{},result))
            out.append({"path":item["path"],"result":result,"response_publication":None,
                        "response_refusal":None,"seen_marker":marker})
            continue
        try:
            result,response_publication,response_refusal=_consume_one(
                repo_root,item,mesh_root=mesh_root,hb_epoch=hb_epoch)
        except Exception as error:
            # Total: one frame's failure is that frame's refusal, not the cycle's,
            # so it never starves the valid frames behind it (B-P36o, F-TYPE). A
            # defect of the frame itself is quarantined. An OSError is this
            # repository's own I/O failing, not the frame: it is refused
            # FRAME_DISPATCH_IO_FAILED with no marker, so the frame stays pending
            # and is consumed once when the I/O recovers. No clock is read.
            frame=item["frame"] if isinstance(item["frame"],dict) else {}
            if isinstance(error,OSError):
                result={"status":"REFUSED","packet_id":frame.get("packet_id"),"quarantine":False,
                        "refusal":{**ingest_refusal(FRAME_DISPATCH_IO_FAILED,type(error).__name__+": "+str(error)),
                                   "failed_predicate":type(error).__name__,
                                   "next_attempt":"the frame stays pending and is consumed by the next cycle"}}
            else:
                result={"status":"REFUSED","packet_id":frame.get("packet_id"),"refusal":frame_error_refusal(error)}
            response_publication=response_refusal=None
        # A refusal of the caller's epoch is not the frame's: nothing is written
        # for it, so the frame is processed when a valid epoch is supplied.
        marker=None
        if result.get("quarantine") is not False:
            marker=str(mark_federation_frame_seen(repo_root,item["path"],item["frame"],result))
        out.append({"path":item["path"],"result":result,"response_publication":response_publication,
                    "response_refusal":response_refusal,"seen_marker":marker})
    return out

#: Messages the frame-integrity checks raise (recover_packet).
FRAME_INTEGRITY_ERRORS=("carrier_frame_hash_mismatch","packet_hash_mismatch","packet_id_mismatch",
                        "destination_org_mismatch")
HB_REFERENCE_INVALID="HB_REFERENCE_INVALID"
FRAME_INTEGRITY_INVALID="FRAME_INTEGRITY_INVALID"
FRAME_INGEST_FAILED="FRAME_INGEST_FAILED"
FRAME_DISPATCH_IO_FAILED="FRAME_DISPATCH_IO_FAILED"

def frame_error_refusal(error:BaseException)->dict[str,Any]:
    """The six-field refusal of an error raised while ingesting one frame."""
    message=str(error)
    if message.startswith("heartbeat_epoch") or message.startswith("epoch_"):
        return ingest_refusal(HB_EPOCH_INVALID,message)
    if message.startswith("heartbeat_"):
        return ingest_refusal(HB_REFERENCE_INVALID,message)
    if message in FRAME_INTEGRITY_ERRORS or type(error).__name__ in ("Error","JSONDecodeError","UnicodeDecodeError"):
        return ingest_refusal(FRAME_INTEGRITY_INVALID,type(error).__name__+": "+message)
    return {**ingest_refusal(FRAME_INGEST_FAILED,message),"failed_predicate":type(error).__name__}

def _consume_one(repo_root:Path, item:dict[str,Any], *, mesh_root:Path|None,
                 hb_epoch:Any)->tuple[dict[str,Any],dict[str,Any]|None,dict[str,Any]|None]:
    """Ingest one addressed frame and answer it; raises for the caller to quarantine."""
    packet=recover_packet(item["frame"])
    payload=packet.get("payload") or {}
    message_class=payload.get("message_class")
    result=ingest_frame(repo_root,item["frame"],mesh_root=mesh_root,hb_epoch=hb_epoch)
    response_publication=None
    response_refusal=None
    # Read from RESPONDED_REQUEST_CLASSES, not a second copy of it. A
    # literal set here disagreed with the map the moment the map gained a
    # class: it declared four answered classes while this responded to
    # three, so an emission the closability gate admitted was consumed and
    # never answered -- the unclosable crossing, arriving through the one
    # surface that is supposed to decide what is closable.
    if result.get("status")=="CONSUMED" and message_class in RESPONDED_REQUEST_CLASSES:
        response=build_control_response(packet,result["execution_result"])
        # Published at the request frame's validated epoch, else at the
        # epoch supplied to this call (ingest refused any disagreement).
        epoch=frame_supplied_epoch(item["frame"])
        if epoch is None and hb_epoch is not None:
            epoch=int(str(hb_epoch))
        if epoch is None:
            # A clock-flagged request lends no epoch and none was supplied:
            # the response is refused six-field, never stamped from a clock.
            response_refusal=writer_epoch_refusal(None,retry_entrypoint=RESPONSE_RETRY_ENTRYPOINT)
        else:
            response_publication=publish_packet(response,root=mesh_root,epoch=epoch)
    return result,response_publication,response_refusal

def recorded_emissions(repo_root:Path, communication_id:str)->dict[str,dict[str,Any]]:
    """What this organization recorded emitting for a communication, by packet id.

    Read off the write-once outbox rather than from the responses, because a
    closure is verified against what this organization recorded emitting, not
    against what the response asserts. Each record yields the three inputs
    `far_side_receipt_chain` needs: the packet id this organization minted, the
    service it addressed, and the digest of its own payload.
    """
    out=repo_root/"resident-runtime/federation/outbox"
    emissions={}
    if not out.exists():
        return emissions
    for path in sorted(out.glob("*.json")):
        try:
            frame=json.loads(path.read_text())
            packet=recover_packet(frame)
        except Exception:
            # An unreadable or tampered outbox record is not an emission this
            # organization can verify against, so it is not offered as one.
            continue
        payload=packet.get("payload") or {}
        if payload.get("communication_id")!=communication_id:
            continue
        emissions[packet["packet_id"]]={
          "packet_id":packet["packet_id"],
          "destination_org":packet["destination"]["org"],
          "far_side_service_id":packet["destination"]["service"],
          "far_side_payload_hash":sha(payload),
          "frame_sha256":frame.get("frame_sha256")
        }
    return emissions

def collect_ecosystem_responses(origin_org:str, communication_id:str, *, mesh_root:Path|None=None,
                                repo_root:Path|None=None)->dict[str,Any]:
    """Collect the responses to a communication, recomputing each far-side chain.

    With `repo_root`, each response's `receipt_terminal` is recomputed from this
    organization's own emission record and a response whose terminal does not
    recompute is refused rather than counted. Without it there is no emission to
    recompute against, and the result says so in
    `far_side_receipts_recomputed_here` rather than reporting a carried terminal
    as a checked one.
    """
    emissions={} if repo_root is None else recorded_emissions(repo_root,communication_id)
    responses=[]
    for item in scan_addressed_frames(origin_org,root=mesh_root):
        packet=recover_packet(item["frame"])
        payload=packet.get("payload") or {}
        if payload.get("communication_id")!=communication_id:
            continue
        if payload.get("message_class") not in ACK_CLASSES:
            continue
        body=payload.get("body") or {}
        row={
          "organization":body.get("responding_organization") or packet["origin"]["org"],
          "message_class":payload.get("message_class"),
          "request_packet_id":body.get("request_packet_id"),
          "application_result":body.get("application_result"),
          "receipt_terminal":body.get("receipt_terminal"),
          "response_packet_id":packet["packet_id"],
          "frame_sha256":item["frame"].get("frame_sha256")
        }
        if repo_root is None:
            # Stated, not implied: the terminal on this row was carried and
            # nothing checked it.
            row["receipt_terminal_recomputes"]=None
            row["far_side_terminal_receipt_recomputed"]=None
            row["findings"]=[]
        else:
            row.update(_verified_response(row,emissions))
        responses.append(row)
    dedup={}
    for row in responses:
        dedup[row["organization"]]=row
    ordered=[dedup[k] for k in sorted(dedup)]
    rows=[row for row in ordered if row["receipt_terminal_recomputes"] is not False]
    refused=[row for row in ordered if row["receipt_terminal_recomputes"] is False]
    return {
      "communication_id":communication_id,
      "response_count":len(rows),
      "organizations":rows,
      "refused_count":len(refused),
      "refused":refused,
      "far_side_receipts_recomputed_here":repo_root is not None,
      "emission_record_count":len(emissions)
    }

def _verified_response(row:dict[str,Any], emissions:dict[str,dict[str,Any]])->dict[str,Any]:
    """Whether a response's terminal receipt recomputes against our own emission."""
    findings=[]
    emission=emissions.get(str(row.get("request_packet_id")))
    if emission is None:
        # A crossing this organization has no record of emitting is not one it
        # can close, whatever the response asserts about it.
        findings.append("THIS_ORGANIZATION_HAS_NO_EMISSION_RECORD_FOR_THIS_PACKET:"
                        +str(row.get("request_packet_id")))
        return {"receipt_terminal_recomputes":False,"far_side_terminal_receipt_recomputed":None,
                "findings":findings}
    if row.get("organization")!=emission["destination_org"]:
        findings.append("RESPONSE_CAME_FROM_A_DIFFERENT_ORGANIZATION:"+str(row.get("organization")))
    recomputed=far_side_receipt_chain(emission["packet_id"],emission["far_side_service_id"],
                                      emission["far_side_payload_hash"])[-1]
    terminal=row.get("receipt_terminal")
    if not isinstance(terminal,str) or not terminal.strip():
        findings.append("RESPONSE_CARRIES_NO_FAR_SIDE_TERMINAL_RECEIPT")
    elif terminal!=recomputed:
        findings.append("FAR_SIDE_TERMINAL_RECEIPT_DOES_NOT_RECOMPUTE:"+terminal)
    return {"receipt_terminal_recomputes":not findings,
            "far_side_terminal_receipt_recomputed":recomputed,"findings":findings}

def publish_ecosystem_from_directory(repo_root:Path, *, standing:dict[str,Any], message_class:str, subject:str, body:dict[str,Any],
                                     requested_action:str|None=None, authority_effect:str="NONE",
                                     communication_id:str|None=None, mesh_root:Path|None=None,
                                     now_ns:int|None=None)->dict[str,Any]:
    registry=load_registry(repo_root)
    directory=load_federation_directory(repo_root)
    organizations=[row["organization"] for row in directory["organizations"]]
    origin=registry["organization"]
    return publish_ecosystem_message(
      origin_org=origin,
      origin_service=organization_slug(origin)+".org-control",
      organizations=organizations,
      standing=standing,
      message_class=message_class,
      subject=subject,
      body=body,
      requested_action=requested_action,
      authority_effect=authority_effect,
      communication_id=communication_id,
      root=mesh_root,
      now_ns=now_ns,
      repo_root=repo_root
    )


# --- Federation replay/dedup v1.3.1 additions ---
def federation_seen_frame_names(repo_root:Path)->set[str]:
    seen_dir=repo_root/"resident-runtime/federation/seen.d"
    if not seen_dir.exists():
        return set()
    names=set()
    for path in seen_dir.glob("*.json"):
        try:
            value=json.loads(path.read_text())
            if isinstance(value.get("frame_name"),str):
                names.add(value["frame_name"])
        except Exception:
            continue
    return names

def mark_federation_frame_seen(repo_root:Path, frame_path:str, frame:dict[str,Any], result:dict[str,Any])->Path:
    seen_dir=repo_root/"resident-runtime/federation/seen.d"
    seen_dir.mkdir(parents=True,exist_ok=True)
    frame_name=Path(frame_path).name
    marker={
      "schema_version":"stegverse.federation-frame-consumption.v1",
      "frame_name":frame_name,
      "frame_sha256":frame.get("frame_sha256"),
      "packet_id":frame.get("packet_id"),
      "destination_org":frame.get("destination_org"),
      "status":result.get("status"),
      "authority_effect":"NONE_CARRIER_ONLY"
    }
    refusal=result.get("refusal")
    if result.get("status")=="REFUSED" and isinstance(refusal,dict):
        # Terminal: the refused frame is quarantined under its own name, so it
        # is never re-processed and never stalls a later cycle (B-P36j). The
        # marker reads no clock and carries no clock stamp.
        marker.update({
          "disposition":"FAIL_CLOSED","failure_code":FRAME_REFUSED_QUARANTINED,"failed_predicate":FRAME_PREDICATE,
          "detail":refusal["failure_code"]+": "+refusal["detail"],"refused_failure_code":refusal["failure_code"],
          "required_evidence_or_repair":refusal["required_evidence_or_repair"],
          "retry_entrypoint":refusal["retry_entrypoint"],"owning_existing_goal":refusal["owning_existing_goal"],
          "next_attempt":"terminal here: the frame is quarantined and not re-processed; the sender re-emits a new frame",
          "derived_from_clock":False,"consequence_committed":False})
    marker_path=seen_dir/(hashlib.sha256(frame_name.encode()).hexdigest()+".json")
    if marker_path.exists():
        if json.loads(marker_path.read_text())!=marker:
            raise ValueError("federation_seen_marker_collision")
    else:
        marker_path.write_text(json.dumps(marker,indent=2,sort_keys=True)+"\n")
    return marker_path
