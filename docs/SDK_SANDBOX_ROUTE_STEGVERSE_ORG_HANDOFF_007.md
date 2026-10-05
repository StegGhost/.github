# Sandbox Route 007 — what StegVerse-org must declare, and why StegGhost cannot

    document_id:        ORGANIZATION-SDK-SANDBOX-ROUTE-HANDOFF-007
    status:             HANDOFF_OPEN_AWAITING_STEGVERSE_ORG_DECLARATION
    authority_effect:   NONE_RECORD_ONLY
    depends_on:         ORGANIZATION-EGRESS-BOUNDARY-004
                        ORGANIZATION-BILATERAL-MATCH-005
                        ORGANIZATION-ORIGIN-ATTESTATION-SEAM-006
                        ORGANIZATION-ROLE-RUNTIME-REALITY-DEPLOYMENT-001
    owner_of_each_item: named per item below — none of them is StegGhost
    canonical_route:    StegGhost/entity-sandbox-runner
                        docs/SDK_CUSTOMER_INGRESS_REPOSITORY_DETERMINATION.md

## Why this document exists

StegGhost has been assigned a role in the canonical formal testing route. The
assignment is architecture of record and it is not in dispute. What this
document records is that **no leg of that route is addressable today**, that
every repair but one belongs to another organization, and exactly what each of
those repairs is — stated concretely enough to be acted on rather than
negotiated.

This is a handoff, not a request for infrastructure. Nothing described here is
a machine for StegGhost to await. Every item below is a **declaration** —
something written into a registry, a contract, or a repository — and each one
takes effect as a state transition the moment it is declared.

## The route, and who owns each leg

From the determination cited above, resolving Issue #11 as a split
existing-role determination:

    intake authority .................. StegVerse-org/StegVerse-SDK
    routing plane ..................... StegVerse-org ingestion surface
    bounded execution and return ...... StegGhost/entity-sandbox-runner
    receipt custody ................... master-records
    strict external target ............ StegVerse-Labs/entity-sandbox
                                        (separate mutation authority required)

StegGhost's assigned legs, from `FORMAL_TESTING_ROUTE.md` by way of the
determination:

    1. sandbox intake and CGE admission
    2. the ephemeral sandbox batch
    3. return validation before return

## What is true at StegGhost today

    legs addressable .......................... 0 of 3
    inbound leg disposition ................... REFUSED endpoint_adapter_not_installed
    outbound leg disposition .................. NOT_REACHED — inbound refuses first
    registered as ............................. SGHOST-EXEMPTION-001

`org-boundary/registry/services.json` declares `stegghost.entity-sandbox-runner`
with `boundary_role: INTERNAL_ENDPOINT`, `profile_status:
NEEDS_REPOSITORY_HANDOFF_RECONCILIATION`, and no `endpoint_adapter`. Dispatch
refuses `endpoint_adapter_not_installed` before any leg is entered, so no leg
emits an organization receipt and the return leg is never reached.

This is registered rather than left silent, per
`data/organization-role-exemption-register.json`. The refusal is immediate and
local: an envelope addressed here today earns a named refusal, not a wait.

## The invariant this route must satisfy

    THE_PATH_TO_AND_FROM_THE_SANDBOX_IS_STATE_TRANSITION_DEPENDENT_IN_BOTH_DIRECTIONS

Both directions, and the return is the half that is easy to get wrong. A
sandbox result that comes back as a function return — a value handed to whoever
called in — is not a state transition and leaves no receipt. The return leg
must be a manifest-bound crossing in its own right, emitting its own
organization receipt, exactly as the inbound leg does. StegGhost's declaration
states this as `return_is_a_state_transition_not_a_function_return: true` and
`each_leg_emits_an_organization_receipt: true`.

Nothing in the route may be gated on a receiver being up. Per the conformance
standard StegGhost now declares: an existing destination is sufficient for
ingress and egress, destination liveness is **not** a transition predicate, an
unavailable receiver gets
`DURABLE_QUEUE_OR_EVENT_EPHEMERAL_MATERIALIZATION`, and no always-on receiver
is required anywhere.

---

# Item 1 — StegVerse-org declares the route to StegGhost's sandbox

    owner:      StegVerse-org
    surface:    StegVerse-org/.github org-boundary/registry/federation.json
    blocking:   yes — this is the item that makes every other one reachable

**There is no SDK→StegGhost sandbox route declared anywhere today.**
StegVerse-org's federation directory carries exactly one row for this
organization:

```json
{
  "organization": "StegGhost",
  "repository": "StegGhost/.github",
  "org_control_service": "stegghost.org-control",
  "kernel_required": "1.3.0",
  "transport_profile": "stegverse.intr.org-boundary.v1"
}
```

`org_control_service` is the control plane. It is not a sandbox route and
cannot carry one: a manifest addressed to `stegghost.org-control` reaches the
organization's control surface, which is `BOUNDARY_LOCAL_CONTROL` — it is its
own processor and selects no sandbox.

StegGhost cannot add this row. The directory is StegVerse-org's, its generation
is counted against StegVerse-org's own denominator, and a row written here
would be StegGhost declaring routing on another organization's behalf — which
is the defect `deployment_scope:
THIS_ORGANIZATION_ONLY_EACH_ORGANIZATION_DEPLOYS_IN_ITS_OWN_DOT_GITHUB` exists
to prevent.

The shape already exists in that same directory. The `SV-011` row shows how a
non-control addressed service is declared:

```json
{
  "organization": "SV-011",
  "repository": "SV-011/entity",
  "addressed_service": "sv-011.boundary-diagnostic",
  "addressed_service_role": "BOUNDARY_LOCAL_DIAGNOSTIC",
  "serves_an_organization_control_service": false,
  "peer_declares_this_in_its_own_registry":
      "SV-011/entity:org-boundary/registry/services.json",
  "peer_class": "PREPARED_EXTERNAL_DEPENDENCY",
  "kernel_required": "1.3.0",
  "transport_profile": "stegverse.intr.org-boundary.v1"
}
```

The StegGhost sandbox row takes that shape with
`addressed_service: stegghost.entity-sandbox-runner` and
`addressed_service_role: INTERNAL_ENDPOINT`. Note what the existing row models
correctly and must be preserved: `peer_declares_this_in_its_own_registry`
points at the peer's **own** registry, so the directory records where the
declaration lives rather than making it. StegGhost's row in
`org-boundary/registry/services.json` is the declaration; the directory row is
the route to it.

Remember the denominator. Adding a row without bumping `denominator` fails
StegVerse-org's own directory validation with
`federation_directory_denominator_mismatch`.

---

# Item 2 — StegVerse-org declares the capability and its route_id

    owner:      StegVerse-org/StegVerse-SDK
    surface:    PUBLISHED_ROUTES and the capability-to-processor binding
    blocking:   yes — a route with no capability admits nothing

`SDK-GENERIC-MANIFEST-ECOSYSTEM-INVARIANT-005` is now enforced at both of
StegGhost's dispatch surfaces: processing is selected only by an admitted
manifest's `processing.capability` bound to its `processing.route_id`, resolved
before any receipt is minted. A manifest arriving with no `processing` block is
recorded `IDENTITY_SELECTED_NO_MANIFEST_DECLARATION` and the declared
capability is explicitly **not** processed; a capability with no `route_id` is
refused outright with `manifest-declares-capability-without-route`.

This means an SDK manifest bound for StegGhost's sandbox must declare:

```json
{
  "processing": {
    "capability": "<the sandbox capability the SDK publishes>",
    "route_id": "<the route the SDK binds that capability to>"
  }
}
```

**StegGhost must not invent either value.** The capability-to-processor table
belongs to `StegVerse-org/StegVerse-SDK`, which owns `PUBLISHED_ROUTES`. This
boundary holds no copy and must not grow one; a second copy would make StegGhost
a second source of truth for route installation. StegGhost's selection surface
records `route_admissibility: NOT_RESOLVED_AT_BOUNDARY_ROUTE_OWNER_IS_SDK` on
every passing selection, precisely so a PASS cannot be read as StegGhost having
proven an installed route.

Once the SDK publishes the capability and its `route_id`, StegGhost admits the
pair in its own registry row's `admits_processing`:

```json
"admits_processing": [
  {"capability": "<published capability>", "route_id": "<published route_id>"}
]
```

A bare capability string is refused rather than treated as a wildcard route
(`service-admitted-processing-binding-incomplete`), and an admitted capability
paired with an unadmitted route is refused
(`declared-capability-route-binding-not-admitted`). Both halves must be
published before either can be admitted.

---

# Item 3 — the endpoint repository declares its receiving operation

    owner:      StegGhost/entity-sandbox-runner
    surface:    that repository's own manifest-bound receiving operation
                and the endpoint_adapter path that resolves it
    blocking:   yes, for the sandbox legs specifically

This is the one item inside StegGhost's organization, and it is still not
StegGhost/.github's to perform. `ENTITY_SANDBOX_RUNNER_MIRROR_HANDOFF.md`
withholds authority for external-repository mutation, and the determination
cited above closes with the same boundary: it "does not authorize
cross-repository mutation, deployment, release, tagging, publication,
production activation, or merge into `main`."

So the declaration is that repository's act. What it must declare:

    a manifest-bound receiving operation for each of the three assigned legs
    the endpoint_adapter path that resolves it
    reconciliation of its NEEDS_REPOSITORY_HANDOFF_RECONCILIATION status

Once declared, `org-boundary/registry/services.json` here gains the
`endpoint_adapter` for `stegghost.entity-sandbox-runner`, both legs emit
organization receipts, and `SGHOST-EXEMPTION-001` is retired. The conformance
suite forces that retirement rather than leaving it to be noticed:
`test_registered_surfaces_still_exist` fails on an exemption whose row now
carries an adapter, and `test_sandbox_leg_count_is_recomputed` recomputes
`legs_addressable_today` from the registry rather than trusting the declared
number.

The same pattern applies to the other five refusing endpoints
(`stegghost.telemetry`, `stegghost.automated-buildout`,
`stegghost.stegverse-sandbox`, `stegghost.stegcge`,
`stegghost.ghost-pat-lab`), registered together as `SGHOST-EXEMPTION-002`. Each
is its own repository's declaration to make.

---

# Item 4 — master-records receipt custody at every ingestion boundary

    owner:      StegGhost/.github for the submitter; master-records for custody
    surface:    .stegverse/transition-ledger/org-contract.json
    blocking:   no — propagation does not gate runtime reality

The determination assigns `master-records` receipt custody "at every ingestion
boundary." StegGhost's organization ledger contract currently declares
`propagation_target: null` with
`organization_batch_propagation_implemented: false`, and says why: naming a
target with no submitter behind it would be a declared capability with nothing
enforcing it — the exact defect
`PEER_KERNEL_GENERATION_ADMISSION_APPLIED_002` records at this organization's
kernel.

The conformant shape is settled and does not need a decision from anyone.
StegVerse-org's own `org-contract.json` carries it:

    propagation_target .................................. master-records/.github
    propagation_role .................. RELEASED_ORGANIZATION_BATCH_RECEIPT_RECORDER
    propagation_gates_organization_runtime_reality ...... false
    propagation_receiver_unavailable_disposition ........ DURABLE_QUEUE_OR_
                                                          EVENT_EPHEMERAL_
                                                          MATERIALIZATION
    always_on_receiver_required ......................... false

Read those last three together: propagation does **not** gate this
organization's runtime reality, an unavailable receiver yields a durable queue
or an ephemeral materialization rather than a wait, and no always-on receiver is
required. That is why this item is not blocking and why it is not an exemption
either — the gap is honestly declared null rather than silently claimed.

Two canonical modules perform it, both organization-neutral in the way the
ledger modules already ported here are:

    resident-runtime/propagate_repository_receipts.py ..... repo chain → org ledger,
                                                           in order, exactly once
    resident-runtime/submit_org_transition_to_master_records.py .... org → master-records

Porting them is StegGhost/.github's own work and needs nothing from
StegVerse-org. It was deliberately not in that change, which was scoped to the
conformance declaration and the register. It landed in
`ORGANIZATION_BATCH_RELEASE_008`: the repository-receipt propagator is ported
verbatim and the release is implemented, so `propagation_target` is now
declared. What is still open is below — the custody service itself.

What **is** master-records' to settle, and now the only thing blocking custody:
the custody service itself. This has been answered at the semantic level —
organization receipts are recorded at the organization level and then batched to
master-records, which is the `RELEASED_ORGANIZATION_BATCH_RECEIPT_RECORDER` role
— so `propagation_target` is declared and the release is implemented. The
addressing is not answered. The directory row for master-records declares
`org_control_service: master-records.org-control` and no `addressed_service`,
and the control plane is not a custody ledger, so the submission refuses rather
than reaching for the service that happens to exist (`SGHOST-EXEMPTION-006`).

`master-records` declares its custody service in its own
`org-boundary/registry/services.json`. This organization then records *where*
that declaration lives, the way the `SV-011` row does, and bumps the
denominator. StegGhost will not name the service itself, because that would be a
declaration about master-records' own surface — the same reason item 1 above is
StegVerse-org's to make.

---

# Item 5 — the credential authority makes attestation manifest-bound

    owner:      StegVerse-Labs/tvc
    surface:    the TV/TVC signing operation
    registered: SGHOST-EXEMPTION-005
    blocking:   no — an unattested crossing completes and records itself unattested

`org-boundary/runtime/origin_attestation.py` reaches `PROVEN` only by calling
`TV_EXPORT_HMAC_SIGN` and `TV_EXPORT_HMAC_VERIFY` on a TV/TVC resident host
whose key is loaded from a systemd credential directory. The attestation action
is therefore performable only where that host answers — which is the prohibited
justification `AN_EXTERNAL_MACHINE_MUST_BE_RUNNING`.

**The repair is to make attestation manifest-bound, not to stand up a machine
for StegGhost to await.** Standing one up would satisfy the call and still fail
the standard. The credential authority exposes attestation as a signing request
that crosses as a governed manifest and returns a receipt. This is
`StegVerse-Labs/tvc`'s declaration to make: `AUTHORITY_SOURCE` in
`org-boundary/runtime/origin_attestation.py` names
`StegVerse-Labs/tvc:scripts/tv_credential_verify_export_resident.py` as the
operation this seam calls.

Until then the crossing itself conforms: an emission with no authority supplied
completes and records `origin_attestation_state: NOT_PROVEN` with
`signer_supplied: false`. Nothing is awaited and no absence becomes a
transition. An *offered* attestation that fails refuses the emission.

---

# Item 6 — a peer serves the other half of the bilateral match

    owner:      any peer organization
    surface:    that organization's emission chain disclosure
    blocking:   no — a peer serving no disclosure is a refusal, never a pass

StegGhost serves its half: it answers, from its own chain, whether it records
emitting a packet a peer names, and to whom. It also asks that question of a
claimed origin and records the answer. **No peer in this ecosystem served this
half before StegGhost did**, so a match completes only where a peer serves the
other side.

A satisfied match corroborates a claimed origin against that organization's own
ledger, which a forged origin cannot write. It does not make standing
authenticated and does not make origin attested by the credential authority.
An unreachable or silent peer yields `PEER_SERVED_NO_DISCLOSURE` or
`PEER_COULD_NOT_CONSULT_ITS_CHAIN` — distinct findings, neither of them a pass.

---

# Item 7 — StegVerse-Labs runs the ungated kernel

    owner:      StegVerse-Labs
    surface:    StegVerse-Labs/.github org-kernel/kernel.py
    blocking:   no, for this route
    status:     PATCH_PREPARED_PERMISSION_NOT_GRANTED

`PEER_KERNEL_GENERATION_ADMISSION_APPLIED_002` named this. StegVerse-Labs is
the canonical kernel source StegGhost vendors from, and its own kernel does not
carry the standing gate. The patch applies cleanly at that repository's head
and introduces zero `node_standing` references that are not the gate itself.

This session has no write access to `StegVerse-Labs/.github` — the repository
add was denied by policy, and that denial has been respected rather than routed
around. The patch is not applied and no attempt was made to apply it.

---

# What StegGhost has already done, so it is not asked for again

    standing gated on both ingress surfaces ................ #8
    far-side receipt recomputation, closability refusal .... #9
    organization egress boundary, both ledger levels ....... #10
    bilateral match — StegGhost serves its half ........... #11
    origin attestation seam, ceiling declared ............. #12
    manifest-bound processing selection at both gates ...... this change
    conformance declaration and exemption register ......... this change

The conformance suite (`org-boundary/tests/test_manifest_bound_conformance.py`)
holds the register against the repository rather than against itself: a seventh
refusing endpoint added without an exemption fails, an exemption that outlives
its defect fails, an exemption that awaits a machine fails, an invented owning
goal or a minted COSV fails, and an emptied register fails. CI additionally
mutates a copy of the register and requires the check to catch it, so a
conformance test that cannot fail does not pass as one that can.

# What this document does not do

It does not authorize anything. It is a record of what each owner must declare,
written from this organization because this organization is the one whose
assigned legs are unaddressable. It confers no authority on StegGhost over any
surface named in it, and it does not imply the route runs.

    authority_effect: NONE_RECORD_ONLY
