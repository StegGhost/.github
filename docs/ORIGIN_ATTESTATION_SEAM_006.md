# Origin Attestation 006 — the seam exists, and its ceiling is declared

    document_id:        ORGANIZATION-ORIGIN-ATTESTATION-SEAM-006
    status:             APPLIED_AT_THIS_ORGANIZATION
    authority_effect:   NONE_RECORD_ONLY
    depends_on:         ORGANIZATION-EGRESS-BOUNDARY-004
                        ORGANIZATION-BILATERAL-MATCH-005
    owner_of_the_fix:   StegGhost
    canonical_source:   StegVerse-org/.github org-boundary/runtime/origin_attestation.py

## What was open

`ORGANIZATION_EGRESS_BOUNDARY_004` recorded that origin was asserted and not
attested, and that this organization carried no `origin_attestation` module and
no credential authority, so no code path here could reach `PROVEN`. That was
accurate and it was a ceiling, not a gap in the design: the reference reaches
`PROVEN` by asking TV/TVC to sign a statement binding the origin to the packet.

## What this adds, and what it deliberately does not

`org-boundary/runtime/origin_attestation.py` is copied verbatim from the
canonical source, `sha256 d736f108...4533647`. It is organization-neutral --
zero occurrences of the source organization's name -- so no fork of the
statement shape exists.

`emit` now takes a `credential_authority` and, given one:

    asks it to sign the statement, then asks it to confirm its own signature
    records PROVEN only on the authority's verification receipt
    attaches the signature inside the packet, where packet_sha256 binds it

Two calls, deliberately. Recording `PROVEN` on the strength of having asked for
a signature would be this boundary asserting its own origin again, one level up
-- trusting its own request rather than the authority's answer.

**No signing or verification algorithm is in this repository.** The module asks;
it does not compute. A second implementation here would make this organization a
second credential authority, which the `credential_authority: TV/TVC` split
exists to prevent. `origin_attestation_is_bound` in the boundary validator reads
the module's source and refuses if `import hmac`, `hmac.new`, `hashlib.sha256`
or `compare_digest` appears in it, so a future edit cannot quietly cross that
line. The suite asserts the same across the boundary and the kernel.

## The ceiling, declared rather than left to be inferred

The key lives on a TV/TVC resident host, loaded from a systemd credential
directory, with no development fallback. This organization has no access to it.
So the overlay declares, and the validator enforces:

    credential_authority_resident_host_available_to_this_organization  false
    signer_is_supplied_by_the_operator_not_held_here                   true
    every_crossing_emitted_here_today_is_unattested                    true

The seam exists; the authority does not answer here. Declaring the binding
without declaring that would be the defect this repository has now corrected
four times -- a declaration with nothing behind it.

`signer_supplied` is on every emission record, so the two unattested cases stay
apart: no authority was offered, versus one was offered and the emission was
refused. An unattested record can no longer be read as an attempt that failed.

## An offered attestation that fails refuses the emission

    no credential authority supplied   ALLOW, NOT_PROVEN, signer_supplied false
    authority supplied and confirms    ALLOW, PROVEN, signer_supplied true
    authority unreachable              DENY  CREDENTIAL_AUTHORITY_IS_REACHABLE
    authority says signature invalid   DENY, nothing published
    receipt not from TV/TVC            DENY  RECEIPT_COMES_FROM_THE_DECLARED_...

An unreachable authority is a hold, never a pass. Emitting anyway would record
an attempted attestation as an ordinary unattested crossing, which is the same
defect class with the record now claiming the opposite of the truth.

The last row was found by this change's own test: the stub authority's receipt
omitted `credential_authority`, and the module refused it as a receipt from
somewhere else rather than accepting a verification it could not attribute.

## Inbound is unchanged, and that is the canonical shape

Nothing verifies an arriving attestation. Checked rather than assumed:
`origin_attestation` is referenced nowhere in the canonical source's kernel or
process boundary, and `grep attestation` over both returns nothing. Attestation
is an outbound act -- an organization attests its own origin -- and a receiver
verifying one would need to reach TV/TVC itself. This port keeps that shape. A
receiver-side verification is a separate change at the canonical source, not a
local divergence.

## What attestation proves, and what it does not

    proves_the_authority_signed_this_statement                true
    proves_the_authority_authenticated_the_asker              false
    initiator_identification_also_requires_the_bilateral_match true

It proves TV/TVC signed this statement and that whoever assembled the frame
could not have produced the signature. It does **not** prove TV/TVC
authenticated the asker as the organization the statement names: TV/TVC signs
what it is handed, and binding the asker to the claimed origin is TV/TVC's to
do. The overlay declares that refusal of the overclaim and the validator
enforces it.

What closes the asker question is the bilateral match, which
`ORGANIZATION_BILATERAL_MATCH_005` built and this organization serves: an
attested statement names a packet id, and a forged origin would need the claimed
organization's own ledger to hold an emission receipt for it.

## The three layers, at this organization, after this change

    node standing     the crossing is provable by node chain    ENFORCED
    TV/TVC signature  a credential authority attested origin    SEAM BUILT,
                                                                AUTHORITY NOT
                                                                REACHABLE HERE
    bilateral match   the claimed origin's chain records it      SERVED

Each remains necessary and none substitutes for another.

## Boundary

    A seam is not an attestation. Every crossing emitted here today is
      unattested, and the overlay says so.
    Attestation is outbound only; an arriving attestation is not verified here,
      as at the canonical source.
    An attested origin is an identified sender, not an authorized one.
    No credential algorithm lives in this repository and the validator refuses
      one that appears.
