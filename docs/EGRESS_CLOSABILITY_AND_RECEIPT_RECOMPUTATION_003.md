# Finding 003 — the two egress gaps, and the change that closes them

    document_id:        EGRESS_CLOSABILITY_AND_RECEIPT_RECOMPUTATION_003
    status:             APPLIED_AT_THIS_ORGANIZATION
    authority_effect:   NONE_RECORD_ONLY
    depends_on:         PEER-KERNEL-GENERATION-ADMISSION-APPLIED-002
    owner_of_the_fix:   StegGhost
    reference_boundary: StegVerse-org/.github resident-runtime/organization_egress_boundary.py

## The two gaps

Recorded as open by Applied 002, which gated ingress and said plainly that it
did not touch egress. Both were probed at this organization's own emission path
before this change.

### 1. A crossing could be emitted that could never close

The responder answers only the request classes the transport profile names, and
closure correlates a response by `communication_id`. A payload declaring
anything else was published, consumed and receipted by the far side, and never
answered:

    message_class "ecosystem.status.query"
      StegVerse-org: DENY at emission,
                     PAYLOAD_DECLARES_A_REQUEST_CLASS_THE_BOUNDARY_ANSWERS
      StegGhost:     published; far side CONSUMED with 5 receipts, answered: False
                     then 0 responses collected

The distinction that was missing is not between success and failure. It is
between a crossing still in flight, whose closure is **pending**, and one that
can never be answered, whose closure is **unreachable**. A response count of
zero expresses the first and cannot express the second, so an unclosable
crossing was indistinguishable from a slow one.

### 2. The far side's terminal receipt was carried, never recomputed

`collect_ecosystem_responses` copied `receipt_terminal` out of the response
body and checked nothing. A response carrying a forged terminal was accepted
and counted complete:

    forged terminal egress_emitted-000000000000000000000000
      -> accepted, response_count 1, reported complete

## What this change does

    1. RESPONDED_REQUEST_CLASSES becomes a named constant. The map was already
       inline in `response_message_class`; emission now reads the same
       declaration instead of a second copy of it, so the set a crossing must
       declare to be closable is the set the responder actually answers.

    2. closability_refusal(payload) names why a payload's crossing could never
       close. build_ecosystem_packets refuses it before any frame is published:
       an unclosable crossing is not emitted at all, rather than left for a
       caller to discover as a response that never arrives.

    3. far_side_receipt_chain(packet_id, service_id, payload_hash) recomputes
       the chain the far side must have minted. Not a claim about the far side's
       honesty -- a recomputation. Every input is something the emitting
       organization already holds: the packet id it minted, the service it
       addressed from its own directory, and the digest of its own payload.

    4. Publishing records each emission to the write-once outbox that
       `persist_outbox` already implemented and nothing called. Written after
       the frame is published, because the record is of an emission; recording
       it first would claim a crossing that had not happened yet.

    5. collect_ecosystem_responses recomputes each response's terminal against
       this organization's own emission record and refuses one that does not
       recompute, rather than counting it. Both emission lanes record, so the
       Service Gateway lane is verified the same way as the local spool lane.

## Dispositions, before and after

    case                                      before              after
    unanswerable message_class                published           refused at emission
    blank communication_id                    published           refused at emission
    an answered class                         published           published
    honest response                           counted             counted, terminal recomputes
    forged terminal receipt                   counted complete    refused, not counted
    response to a crossing we never emitted   counted             refused, not counted

## The absence is stated, not silent

`collect_ecosystem_responses` can be called without an emission record to
recompute against. It then reports

    far_side_receipts_recomputed_here: false
    receipt_terminal_recomputes:       null

rather than returning a carried terminal that reads like a checked one. This is
the same move Applied 002's `destination_kernel_generation_is_proven_here` makes
on the resolution side: a field that says what was not established, so a reader
of the record is not left to assume it was.

## Where the refusal sits, and where it does not

The closability refusal is at `build_ecosystem_packets`, the governed emission
path. It is deliberately **not** in `build_packet`, the low-level constructor,
because `build_control_response` builds responses through it and a response's
class is an acknowledgement rather than a request -- a check there would refuse
every response. This matches the reference boundary, where `emit` refuses and
`kernel.build_packet` does not. A caller reaching past the governed path can
still construct an unclosable packet, here as there.

## What this does not do

This is not the reference organization's full `resolve`/`emit`/`close` boundary.
That boundary records every emission and closure on a transition ledger, carries
credential-authority attestation, and returns an explicit `PENDING` disposition
for a crossing still in flight. This organization carries none of that
infrastructure, and porting it was not attempted here: what is closed is the two
gaps that were probed, with the machinery this repository already has.

So:

    An unclosable crossing is refused at emission.
    A far-side terminal receipt is recomputed rather than trusted.
    There is still no ledger-backed emission and closure record,
      and no explicit PENDING disposition.
    Standing admitted is still not origin authenticated.
