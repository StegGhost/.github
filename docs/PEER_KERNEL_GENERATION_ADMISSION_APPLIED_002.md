# Applied 002 — this organization now runs the gate it declared

    document_id:        PEER-KERNEL-GENERATION-ADMISSION-APPLIED-002
    status:             APPLIED_AT_THIS_ORGANIZATION
    authority_effect:   NONE_RECORD_ONLY
    answers:            PEER-KERNEL-GENERATION-ADMISSION-FINDING-002
                        PEER-KERNEL-GENERATION-ADMISSION-MIGRATION-002
    owner_of_the_fix:   StegGhost
    raised_from:        StegVerse-org/.github
    canonical_source:   StegVerse-org/.github

## What was found here

Finding 002 named `StegVerse-Labs` and `Admissible-Existence`. This organization
is a third instance, and the declaration is stronger: `org-kernel/kernel.py` was
byte-identical to the StegVerse-Labs kernel the finding reported, while
`org-kernel/kernel-manifest.json` was byte-identical to the canonical **1.3.1**
manifest. Every row of `org-boundary/registry/federation.json` declares
`kernel_required: 1.3.0`. Both declarations name this gate.

Probed against this organization's own kernel and its own tree, before this
change, with the finding's own origin string:

    origin "Anyone-At-All", no standing field at all
      -> CONSUMED, 5 receipts, terminal receipt minted, response published

`build_packet` took no `standing` argument, so a standing-less packet was the
only kind this organization could construct.

A second ingress surface was open in its own right.
`org-boundary/runtime/process_boundary.py` is run directly as a subprocess by
`resident-runtime/run_once.py`, never through `kernel.dispatch`, and the same
standing-less envelope exited 0 there with a full five-receipt chain. A
kernel-only gate would have left that lane ungated.

## What this change does

    1. org-boundary/runtime/node_standing.py and
       docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json are copied verbatim from
       the canonical source, so this organization carries the canonical module
       rather than a fork of it:

         node_standing.py
           sha256 a24b7d2cc546fa57e4467e55d075e717249e20c2624b4299b36dca08f307ac8e
         CANONICAL_NODE_INGRESS_CONTRACT_001.json
           sha256 398c794b3d1c617787a5cf1edd59d3420584800aec01f718b9e9611f5f9b7bab

       Both match the digests Migration 002 recorded.

    2. org-kernel/kernel.py takes the kernel hunks of
       docs/migrations/stegverse-labs.node-standing-gate.patch unchanged. They
       apply cleanly because the kernel was the same file. Standing resolves
       before the boundary-role branch, `build_packet` takes `standing` as a
       required keyword with no default, the ecosystem publish path threads it
       through, and a response carries the request's standing forward rather
       than declaring its own.

    3. org-boundary/runtime/process_boundary.py resolves standing itself,
       before any receipt is minted, so a refused crossing leaves no chain
       implying it was consumed.

    4. org-boundary/runtime/intr_transport.py requires standing at
       construction, carries it forward on the egress side, and
       validate_org_crossing refuses an envelope that declares none.

    5. resident-runtime/ecosystem_control.py takes --standing as a required
       argument. The operator declares it; this runtime never mints one for
       itself, which would be the gate answering its own question.

## Dispositions, before and after

Each probed against this organization's own kernel and its own tree:

    packet                     before                  after
    no standing at all         CONSUMED, 5 receipts    build refused
    hand-forged, no standing   CONSUMED, 5 receipts    fail-closed refusal
    standing declared empty    cannot be built         fail-closed refusal
    absent predecessor key     cannot be built         fail-closed refusal
    valid genesis standing     cannot be built         CONSUMED, 5 receipts

Parity with the organization that raised the finding is the target, and parity
is what this reaches. The gate does not make this organization stricter than
StegVerse-org.

## The crossing still completes

A real crossing from `StegVerse-org`, run with that organization's egress
boundary on one side and this organization's own kernel against its own tree on
the other, completes all four steps after this change, with the same packet id
and the same terminal receipt as before it:

    resolve -> ALLOW, addressed at stegghost.org-control
    emit    -> ALLOW, pkt-9792afb8f0c567dc487d1520
    peer    -> CONSUMED, 5 receipts, terminal egress_emitted-ac0cbcae007f12bea4968d5f
    close   -> ALLOW, closed=True, far-side terminal recomputed and matching

The gate costs the organization nothing it had. What it removes is the
indistinguishability: before this change, that completing crossing and the
`Anyone-At-All` probe were the same event at this boundary.

## What the gate does not do

A crossing whose origin string is `Anyone-At-All` and whose standing is a valid
genesis declaration is admitted, here as at the canonical source. The gate makes
a crossing provable by node chain; it does not validate a caller-written origin.
The admitted result says so in its own fields rather than leaving a reader of
the chain to assume otherwise, and the regression asserts these values:

    caller_editable_origin_established_identity      false
    structural_standing_only                         true
    structural_standing_is_authenticated_standing    false
    standing_authority_effect                        NONE_STANDING_ONLY

So Finding 002's narrowing holds after this change: the receipt chain becomes
one whose standing was checked, not one whose origin was authenticated.

## What remains open at this organization's egress

Two gaps found alongside this one are **not** closed in this change, and this
document does not imply they are. Both are answered separately by
`docs/EGRESS_CLOSABILITY_AND_RECEIPT_RECOMPUTATION_003.md`, which depends on
this change and does not replace it:

* There is no `resolve`/`emit`/`close` egress boundary. A payload declaring a
  `message_class` the transport profile does not answer is published, consumed
  and receipted by the far side and never answered. StegVerse-org refuses the
  same payload at emission with
  `PAYLOAD_DECLARES_A_REQUEST_CLASS_THE_BOUNDARY_ANSWERS`; this organization
  publishes it and then collects zero responses, with nothing distinguishing an
  unclosable crossing from one still in flight.

* `kernel.collect_ecosystem_responses` carries the far side's
  `receipt_terminal` as the response asserts it, and never recomputes it. A
  response carrying a forged terminal receipt was accepted and counted.

Both are egress-side and recorded here so the gap is observable rather than
silent. Neither is touched by this change.

## Boundary

    Standing admitted is not origin authenticated.
    A gate on ingress is not a gate on egress.
    Standing grants no execution, route, credential, governance or transition
      authority.
    kernel_required was a declaration at this organization until this change;
      it is now enforced on every ingress surface this organization exposes.
