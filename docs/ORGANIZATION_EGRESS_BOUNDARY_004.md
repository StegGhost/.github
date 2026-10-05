# Egress Boundary 004 — this organization can now initiate a crossing

    document_id:        ORGANIZATION-EGRESS-BOUNDARY-004
    status:             APPLIED_AT_THIS_ORGANIZATION
    authority_effect:   NONE_RECORD_ONLY
    depends_on:         PEER-KERNEL-GENERATION-ADMISSION-APPLIED-002
                        EGRESS_CLOSABILITY_AND_RECEIPT_RECOMPUTATION_003
    owner_of_the_fix:   StegGhost
    canonical_source:   StegVerse-org/.github resident-runtime/organization_egress_boundary.py

## What was missing, stated precisely

A crossing involving this organization completed all four reference steps before
this change:

    resolve -> ALLOW, addressed at stegghost.org-control
    emit    -> ALLOW
    peer    -> CONSUMED, five receipts, terminal receipt minted
    close   -> ALLOW, closed=True, far-side terminal recomputed and matching

That was read as "this organization is wired", and it was wired -- as a
**responder**. Three of those four steps were `StegVerse-org`'s operations,
performed by that organization's `organization_egress_boundary.py` against its
own tree. This organization performed step 3.

Probed directly, before this change:

    resolve_destination()   ABSENT
    emit()                  ABSENT
    close()                 ABSENT

So leaving the organization -- the most consequential transition it makes --
emitted no receipt at either ledger level, while the organization ledger
contract's `organization_scope_rule` is that *every* state transition occurring
within the organization emits an organization receipt. The outbound boundary was
the one that was never built.

## What this adds

    resident-runtime/ledger_store.py              copied verbatim from the canonical source
    .stegverse/transition-ledger/emit.py          copied verbatim; identity from contract.json
    resident-runtime/aggregate_repo_transition.py copied verbatim; identity from org-contract.json
    .stegverse/transition-ledger/contract.json    new, this organization's repository ledger
    .stegverse/transition-ledger/org-contract.json new, this organization's organization ledger
    resident-runtime/organization_egress_boundary.py  adapted, see below
    org-kernel/kernel.py                          hb_reference(epoch=...), validate_hb_reference

The three ported modules needed no edits: each reads its organization identity
from a contract JSON, so only the two contracts are specific to here.

`hb_reference` gained a reproducible path. A ledger receipt must be replayable,
and an epoch read from a host clock is not: an NTP step moves or reverses it, and
two nodes with skewed clocks assign different epochs to one event. Supplying the
tick makes the receipt reproducible; deriving one now says `derived_from_clock`
rather than reading as though a tick had been observed.

## Where this is stricter than the canonical source

`kernel.build_packet` requires `standing` but does not check its shape, so an
empty or incoherent declaration is buildable and publishable, and then refused
fail-closed at the far side's ingress. That is a crossing emitted that can never
close -- the same defect `closability_refusal` exists to prevent, arriving by a
different route. The reference boundary passes `standing` straight through.

This boundary resolves it first, through this organization's **own** ingress
contract and the same `node_standing` module that gates arrivals, so it cannot
emit outbound what it would refuse inbound:

    standing {}                              DENY at emission, nothing published
      node-standing-fail_closed:claimed-standing-not-provable:no-mode-declared
    standing with no predecessor key         DENY at emission
    standing declaring an unknown mode       DENY at emission

The refusal was found by this change's own regression, not reasoned about: the
first run of the suite emitted `standing={}` with disposition ALLOW.

## Where this is narrower than the canonical source, and why

* **No capability addressing.** The reference resolves a peer's address for a
  declared capability from its own overlay. This organization's
  `org-runtime/interlock-intr.json` declares no `capability_endpoint_bindings`,
  so a `--capability` argument here would address a capability nothing declares.
  The directory's `addressed_service` field is honoured; capability addressing
  is added when an overlay declares one.
* **No attestation path at all.** The reference reaches
  `origin_attestation_state: PROVEN` when a credential authority signs a
  statement naming the origin for the packet. This organization carries no
  `origin_attestation` module and no wired credential authority, so rather than
  port an unusable signing path, the record states
  `attestation_is_unavailable_at_this_organization: true` alongside
  `NOT_PROVEN`. A reader of the chain cannot take that `NOT_PROVEN` for an
  attestation that was attempted and failed.

  **Superseded.** `ORGANIZATION-ORIGIN-ATTESTATION-SEAM-006` built the seam:
  `emit` takes a credential authority and reaches `PROVEN` on that authority's
  verification receipt, so the claim above that no code path here could reach
  it no longer holds. What remains true is the ceiling, and it is now declared
  in the overlay and enforced by the boundary validator rather than stated in
  a record field: the authority's key is on a TV/TVC resident host this
  organization cannot reach, so every crossing emitted here today is still
  unattested. The field named above was replaced by `signer_supplied`, which
  distinguishes no authority offered from one offered that failed.
* **No propagation to `master-records`.** The reference declares
  `propagation_target: master-records/.github` and carries a submitter to
  perform it. This organization carries no submitter, so the field is `null` and
  `organization_batch_propagation_implemented` is `false`. Naming a target with
  nothing propagating to it is the defect Applied 002 recorded at this
  organization's kernel, and CI asserts the field stays null until a submitter
  exists.
* **A narrower `consumes` list.** The reference also admits
  `stegverse.canonical-state-transition-receipt/v1`. Nothing here emits that
  schema, so admitting it would declare an intake with no producer.

## Dispositions

Each recorded at both ledger levels, under its own transition class, so no
reader can mistake a refusal for a crossing that left:

    resolve  declared peer                    ALLOW
             peer absent from the directory    DENY   DESTINATION_IS_A_DECLARED_PEER...
             peer on another transport profile DENY   DESTINATION_SPEAKS_THIS_BOUNDARY...

    emit     declared peer, closable, standing ALLOW  ORGANIZATION_EGRESS_EMITTED
             unanswerable message_class        DENY   ORGANIZATION_EGRESS_REFUSED
             blank communication_id            DENY   ORGANIZATION_EGRESS_REFUSED
             standing this ingress would refuse DENY  ORGANIZATION_EGRESS_REFUSED
             undeclared peer                   DENY   ORGANIZATION_EGRESS_REFUSED

    close    no response in the mesh yet       PENDING  nothing recorded
             response, terminal recomputes     ALLOW    ORGANIZATION_EGRESS_CLOSED
             forged terminal receipt           DENY     ORGANIZATION_EGRESS_CLOSURE_REFUSED
             no emission record here           DENY     ORGANIZATION_EGRESS_CLOSURE_REFUSED

`PENDING` records nothing deliberately. An absence is not an arrival: nothing
crossed the boundary, so there is no disposition to record, and appending a
refusal per poll would record the polling rather than the crossing.

## The crossing, driven from here

Run against the real `StegVerse-Labs` head, with this organization's boundary
driving all four steps and that organization's own kernel serving step 3:

    1. resolve  ALLOW, addressed at stegverse-labs.org-control
                kernel_required 1.3.0, proven here: false
    2. emit     ALLOW, pkt-85982afac89c139511c4011a
                repository and organization receipts both appended
                attestation NOT_PROVEN, unavailable here
    3. peer     CONSUMED, 5 receipts, terminal egress_emitted-2f354cb0415a3122cff9cd5b
    4. close    ALLOW, closed=true, findings []
                recomputed here egress_emitted-2f354cb0415a3122cff9cd5b -- matching
                repository and organization receipts both appended

This is the reference shape, produced by this organization rather than for it.

## What the recomputation proves, and what it does not

    reconstruction_proves_the_boundary_ran_this_packet       true
    reconstruction_proves_who_the_far_side_is                false
    reconstruction_proves_the_far_side_persisted_its_chain   false
    bilateral_match_requires_the_far_side_chain_to_be_readable true

A terminal receipt is derived from the packet id, the service id and the payload
digest, all of which this organization already holds. So the id that comes back
is recomputed and compared rather than trusted. That it recomputes proves a
boundary ran this packet and minted the chain this packet determines. It does
not establish whose boundary that was.

## Boundary

    Origin is asserted, not attested, and no path here attests it.
    Standing admitted is not origin authenticated.
    A recomputed far-side chain is not a bilateral match.
    There is no capability addressing and no propagation to master-records.
    Nothing here grants execution, route, credential, governance or transition
      authority.

The propagation half of the fourth line is superseded by
`ORGANIZATION_BATCH_RELEASE_008`, which declares `propagation_target:
master-records/.github` and implements the release. The line stood as written
until then. What remains true of it: no batch has reached the real recorder,
because the federation directory declares no custody service for it, and
capability addressing is still absent.
