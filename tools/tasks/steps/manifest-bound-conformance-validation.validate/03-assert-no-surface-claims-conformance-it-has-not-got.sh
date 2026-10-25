set -eu
python3 - <<'PY'
import json
from pathlib import Path

declaration = json.loads(Path(
    'data/organization-role-runtime-reality-deployment.json'
).read_text(encoding='utf-8'))
register = json.loads(Path(
    'data/organization-role-exemption-register.json'
).read_text(encoding='utf-8'))

# A declaration is not authority and an exemption is not a pass.
# Three claims nothing in this organization may make.
assert declaration['authority_effect'] == 'NONE_DECLARATION_ONLY'
assert register['authority_effect'] == 'NONE_REGISTER_ONLY'
assert register['exemption_grants_authority'] is False
assert register['exemption_may_satisfy_a_terminal_predicate'] is False

# The declaration is this organization's own. deployment_scope is
# THIS_ORGANIZATION_ONLY, so a declaration naming another
# organization's surfaces would be declaring on its behalf.
scope = declaration['deployment_scope']
assert scope.startswith('THIS_ORGANIZATION_ONLY'), scope
assert declaration['organization'] == 'StegGhost'
assert register['organization'] == 'StegGhost'

# The sandbox route is architecture of record, not a running path.
invariant = declaration['sandbox_path_invariant']
assert invariant['legs_addressable_today'] == 0, \
    'if a leg became addressable, say so and retire its exemption'
assert invariant['exemption_registered'] in {
    entry['exemption_id'] for entry in register['exemptions']}, \
    'the unaddressable sandbox leg must cite an exemption that exists'

assert declaration['processing_selection']['route_owner'] == \
    'StegVerse-org/StegVerse-SDK', \
    'route installation is the SDK\'s; this boundary must not own it'
assert declaration['processing_selection'][
    'route_installation_resolved_here'] is False
print('NO_SURFACE_CLAIMS_CONFORMANCE_IT_HAS_NOT_GOT=PASS')
PY
