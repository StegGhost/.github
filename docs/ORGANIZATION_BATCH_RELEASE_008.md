# Organization Batch Release 008 — recorded here, then batched there

    document_id:        ORGANIZATION-BATCH-RELEASE-008
    status:             APPLIED_AT_THIS_ORGANIZATION
    authority_effect:   NONE_RECORD_ONLY
    depends_on:         ORGANIZATION-EGRESS-BOUNDARY-004
                        ORGANIZATION-ROLE-RUNTIME-REALITY-DEPLOYMENT-001
                        ORGANIZATION-SDK-SANDBOX-ROUTE-HANDOFF-007
    owner_of_the_fix:   StegGhost
    canonical_source:   StegVerse-org/.github
                        resident-runtime/propagate_repository_receipts.py

## What was open

`ORGANIZATION_EGRESS_BOUNDARY_004` recorded it in one line: *there is no
capability addressing and no propagation to master-records.* The organization
ledger contract carried `propagation_target: null`, and said why — naming a
target with no submitter behind it would be a declared capability with nothing
enforcing it, which is the defect
`PEER_KERNEL_GENERATION_ADMISSION_APPLIED_002` found in this organization's own
kernel.

That was honest and it was also a gap. The ledger root was already this
organization's runtime-reality locus; nothing carried a verified segment of it
anywhere.

## The two acts

    recorded at the organization level .... real under ORGANIZATION_LEDGER_LOCK
                                            the moment it is appended
    batched to master-records ............. a segment this organization has
                                            independently verified and released,
                                            handed over for durable custody

Keeping these apart is the whole design. `master-records` is the
`RELEASED_ORGANIZATION_BATCH_RECEIPT_RECORDER`: it holds custody,
reconstruction and cross-organization history, and it holds no transition
authority. It is not this organization's runtime-reality authority and it may
not gate it.

**An organization transition is real when it is appended under the organization
ledger lock — not when a batch carrying it is recorded downstream.**

Which is why `release` and `submit` are separate functions rather than one
call, and why CI reads `release`'s body to prove it never reaches for
`custody_destination`, `egress.emit` or `submit`. A release that consults the
recorder is a release the recorder can gate.

## What this adds

### The repository half, ported

`resident-runtime/propagate_repository_receipts.py` is copied verbatim from the
canonical source, `sha256 02206765...abb27396`. It walks a declared
repository's chain and carries its receipts onto the organization chain in
repository chain order, each verified against its own body, each exactly once.
It is organization-neutral — it reads this organization's name and its seven
declared repositories off `org-boundary/registry/services.json` — so no fork of
it exists.

### The release, built here

`resident-runtime/release_organization_batch.py` verifies the contiguous,
not-yet-released tail of the organization chain and releases it.

**Verified means re-digested.** Each receipt's claimed `receipt_sha256` is
recomputed from its own body. One receipt whose digest does not match stops the
walk and refuses the whole segment: the receipts before it are not made
trustworthy by it, and releasing them under a batch digest would put this
organization's signature on a chain it had not actually checked.

**Exactly-once is read, not remembered.** Prior releases are walked off the
chain itself, so a second run is a no-op rather than a duplicate batch — and it
survives a lost file, a fresh process, and a second node holding the same
ledger.

**The release predecessor is the prior batch**, found in chain order. An
earlier draft of this module took the lexicographically largest released
receipt digest, which is meaningless: a digest sorts by its bytes, not by when
it was written. The suite asserts the second release chains onto the first
batch's digest.

**The release is itself a transition here**, so it emits receipts at both
ledger levels like any other. A batch release that left no organization receipt
would be the one transition in this organization the ledger could not replay.

**An empty chain releases nothing** rather than minting an empty batch. An
empty batch receipt would assert a handover that did not happen.

### The submission, and the refusal it earns today

The contract now declares the target and the three fields that keep it
non-gating:

    propagation_target .................................. master-records/.github
    propagation_role .................. RELEASED_ORGANIZATION_BATCH_RECEIPT_RECORDER
    propagation_gates_organization_runtime_reality ...... false
    propagation_receiver_unavailable_disposition ........ DURABLE_QUEUE_OR_EVENT_
                                                          EPHEMERAL_MATERIALIZATION
    always_on_receiver_required ......................... false

The submission goes through the recorded egress boundary — the same standing
gate, closability refusal and receipt chain as every other crossing this
organization makes — rather than a private path.

**It refuses today, and the refusal is the point.**
`org-boundary/registry/federation.json` declares `master-records` with
`org_control_service: master-records.org-control` and no `addressed_service`. A
control service is the control plane, not a custody ledger. Addressing a batch
to it *because it is the service that happens to exist* is the identity-addressing
substitution `SDK-GENERIC-MANIFEST-ECOSYSTEM-INVARIANT-005` forbids — and the
same defect this organization documented in another organization's directory in
`SDK_SANDBOX_ROUTE_STEGVERSE_ORG_HANDOFF_007`. Having named it
there, reaching for it here would be worse than the original gap.

So the submission refuses with `A_CUSTODY_SERVICE_IS_DECLARED_FOR_THE_PROPAGATION_TARGET`
and the refusal names what the row *does* declare, so a reader can see a control
service was available and deliberately not used. Registered as
`SGHOST-EXEMPTION-006`.

The refusal is immediate and local. Nothing is queued against the day the
service is declared, nothing polls for it, and no machine is awaited. And the
refusal is *recorded* at both ledger levels, so a batch that was never handed
over is distinguishable from one never attempted.

**The release stands regardless.** A batch that has not been released or
recorded is a value in the attempted transition's evidence state — not a
blocker, and not proof of non-occurrence.

## Why the kernel's closability map was not extended

A custody handover rides `ecosystem.communication`, which the kernel already
answers, and carries its specificity in `operation:
CUSTODY_RELEASED_ORGANIZATION_BATCH`.

The obvious move was to add `ecosystem.transition.custody.request` to
`RESPONDED_REQUEST_CLASSES`. That map does double duty: it is the set a
crossing may declare to be closable, *and* the set `consume_and_respond`
answers. Adding a custody class would therefore make **this** organization
acknowledge an inbound custody request — claiming to be a recorder it is not.
Under `SDK-GENERIC-MANIFEST-ECOSYSTEM-INVARIANT-005` it is the declared
capability that selects processing anyway, never the message class, so the
class carries nothing the `operation` does not.

Closable is not awaited. `emit` returns as soon as the frame is published;
closure is a separate transition that may never occur.

The closability gate caught this during development — the first version of the
payload declared no `message_class` at all and was refused as an unclosable
crossing. The gate from `EGRESS_CLOSABILITY_AND_RECEIPT_RECOMPUTATION_003` was
working exactly as built, against its own author.

## What is proven, and what is not

Ten cases in `resident-runtime/tests/test_organization_batch_release.py`, driven
against a scratch ledger. Both directions are exercised: the submission refuses
against the directory as it actually stands, **and** crosses against a scratch
directory carrying a declared custody row — addressed at the custody service,
with the control service still on the row and still not what carried the batch.

A `submit` proven only able to refuse would be indistinguishable from one that
is broken.

Ten mutations were probed against the module and all ten were caught: skipped
verification, re-releasing, a genesis-faking predecessor, an empty batch, a
fallback to the control service, a recorder claimed to hold authority, a
refused submission reported as dropping the release, an unrecorded refusal, an
unchecked resolver disagreement, and a release gated on its submission. Ten
more were probed against the conformance declaration and all ten were caught.

**No batch has reached the real recorder.** The crossing is proven against a
scratch directory, which proves the path and proves nothing about what
`master-records` received. The custody service is `master-records`' to declare
in its own registry; this organization then records *where* that declaration
lives, the way the `SV-011` row does, and does not declare it on the peer's
behalf.

That declaration is also the one thing this organization cannot read. The
recorder's repository is named `.github`, which cannot be attached to a session
of this kind, so its registry was not consulted and no custody service name was
assumed from the canonical submitter's.

    authority_effect: NONE_RECORD_ONLY
