# Bilateral Match 005 — this organization serves the half nobody served

    document_id:        ORGANIZATION-BILATERAL-MATCH-005
    status:             APPLIED_AT_THIS_ORGANIZATION
    authority_effect:   NONE_RECORD_ONLY
    depends_on:         ORGANIZATION-EGRESS-BOUNDARY-004
    owner_of_the_fix:   StegGhost
    first_in_ecosystem: true

## The gap, in the ecosystem's own words

Every closure record this organization writes has carried, since the outbound
boundary was built:

    reconstruction_proves_the_boundary_ran_this_packet          true
    reconstruction_proves_who_the_far_side_is                   false
    reconstruction_proves_the_far_side_persisted_its_chain      false
    bilateral_match_requires_the_far_side_chain_to_be_readable  true

Recomputing a far-side receipt chain proves a boundary ran the packet. It does
not say *whose* boundary, because every input to the recomputation is held by
the recomputing side. What would say whose is the other half: the claimed
origin's own ledger holding an emission receipt for that packet id, addressed
to the asker. A forged origin cannot produce that, because it cannot write the
claimed organization's chain.

`StegVerse-org`'s `origin_attestation.py` names this as what closes the asker
gap, and says it "is already here". Checked rather than taken: the phrase names
the *local* half -- walking one's own chain for one's own emission, which
`recorded_emission` does. Searched across the canonical source, `bilateral` is
mentioned in six places and implemented in none, and no surface anywhere in the
ecosystem makes an organization's chain readable to a peer. So the half that
needs the far side existed nowhere, and the field above was true everywhere
because nothing could make it false.

## What this adds

    org-boundary/runtime/emission_chain_disclosure.py   the serving half, and the matcher
    org-kernel/kernel.py                               a fourth answered request class
    resident-runtime/organization_egress_boundary.py    request_bilateral_match, observe_bilateral_match

### Served, not invented transport

The disclosure is a fourth entry in `RESPONDED_REQUEST_CLASSES`:

    ecosystem.emission.disclosure.request -> ecosystem.emission.disclosure.response

Declaring it there rather than giving it a transport of its own means the
crossing is closable by construction: `closability_refusal` admits it with no
special case and `close` correlates it like any other. The alternative
considered was the reference's capability-ingress machinery
(`capability_ingress.py` plus `manifest_selection.py`, about 450 lines) which
exists to route SDK manifests to a dedicated address. This organization has no
such capability, and porting that machinery to address one that does not exist
would be a road to nowhere.

### What a disclosure carries, and what it refuses to carry

One packet id the asker already holds, answered yes or no, with the digests and
the destination organization the chain recorded. Never a payload, never the
chain, never another packet. An asker learns whether its own crossing is
corroborated and nothing else about this organization's traffic. CI asserts the
absence of payload and frame bodies in the module.

### Silence is never a pass

Three distinct answers, none of which is a match:

    peer serves no disclosure          PEER_SERVED_NO_DISCLOSURE
    peer cannot consult its chain      PEER_COULD_NOT_CONSULT_ITS_CHAIN
    peer's chain holds no such receipt PEER_CHAIN_HOLDS_NO_EMISSION_RECEIPT_FOR_THIS_PACKET

A peer that cannot read its own ledger has not declined to hold the receipt, so
`NOT_AVAILABLE` is kept apart from `NO_RECORD`. Unsatisfied is the default and
every failure path keeps it.

## Dispositions

    ask      an ordinary recorded crossing, emitted through `emit`
    observe  no answer yet                  PENDING  nothing recorded
             answer corroborates            ALLOW    ORGANIZATION_BILATERAL_MATCH_SATISFIED
             answer refuses or is silent    DENY     ORGANIZATION_BILATERAL_MATCH_REFUSED

The ask crosses an organization boundary outbound, so it is that transition and
is recorded as one. Giving the match a private path would be the outbound
boundary exempting its own traffic from the record it exists to keep.

## Proven, including the case that matters

    a peer really emitted the packet      match SATISFIED, peer chain readable
    a forged frame claimed that origin    match REFUSED, peer chain readable and said no
    a peer serving no disclosure          match REFUSED, peer chain not readable
    disclosure answers a different packet REFUSED
    disclosure from a different org       REFUSED
    peer recorded emitting elsewhere      REFUSED

The forged case is the point. A frame claiming any origin can be published by
any writer of a shared mesh, is admitted on valid standing, and is consumed and
receipted -- consumption was never the question. What was missing was any way
to ask the claimed origin. Now there is one, and the forged origin is caught by
the claimed organization's own chain saying it never emitted that packet.

## A latent bug this work surfaced

`consume_and_respond` answered from a literal set of three message classes
rather than from `RESPONDED_REQUEST_CLASSES`. The moment the map gained a
fourth class, the map declared four answered and the responder answered three
-- so a crossing the closability gate admitted was consumed and never answered.
That is the unclosable crossing of `EGRESS_CLOSABILITY_AND_RECEIPT_RECOMPUTATION_003`,
arriving through the one surface that decides what is closable.

`federation_gateway_transport.py` carried the same literal set, so the Service
Gateway lane had it too. Both now read the map, and CI asserts no surface
restates either the request set or the acknowledgement set.

## What a satisfied match does not do

    makes_standing_authenticated                        false
    makes_origin_attested_by_the_credential_authority   false

A match corroborates one crossing against one chain. It does not make standing
authenticated: standing stays structural, as
`PEER_KERNEL_GENERATION_ADMISSION_APPLIED_002` records. It does not attest
origin: that needs the credential authority, which this organization has no
path to, as `ORGANIZATION_EGRESS_BOUNDARY_004` records.

The three layers remain separate and each remains necessary:

    node standing       the crossing is provable by node chain   enforced here
    TV/TVC signature    a credential authority attested origin   no path here
    bilateral match     the claimed origin's chain records it    served here, first

## Boundary

    A satisfied match is not an authenticated origin.
    A disclosure is a yes or no about one packet, not a readable chain.
    No peer served this half before now, so a match completes only where a peer
      serves the other side. Refusals against peers that serve none are correct
      refusals, not failures of this organization.
    Nothing here grants execution, route, credential, governance or transition
      authority.
