# StegGhost Organizational Boundary

`StegGhost/.github` is the canonical specification and bootstrap home for the StegGhost organizational ingress/egress boundary.

## Processing path

```
HB or HB-derived carrier
  -> governed InTr envelope
  -> organizational ingress validation
  -> normalization / provenance binding
  -> service + endpoint-profile resolution
  -> internal dispatch
  -> endpoint consumption
  -> result/evidence binding
  -> organizational egress
  -> governed InTr envelope
  -> carrier
```

## Authority boundary

HB and HB-derived carriers provide synchronization and carrier capability only. They do not grant admission, execution, credential, routing, transition, receiving, publication, custody, or release authority.

The organizational boundary may validate, normalize, resolve, route, and bind evidence. Applicable transition elements determine authority effects. GitHub Actions may validate artifacts but are not runtime authority.

## Evidence lifecycle

The following remain separate evidence states:

```
source-present
validated
merged
deployed
activated
ingress-observed
dispatched
consumed
result-bound
egress-observed
same-execution-reconstructed
released
```

## Internal service registry

See `registry/services.json`. Repository-specific semantics belong in endpoint profiles; organization-wide transport semantics belong here.
