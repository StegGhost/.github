set -eu
python3 - <<'PY'
import json, subprocess, sys
from pathlib import Path

# The register only means something if removing an entry fails the
# build. Mutate a copy of the tree and require the check to catch it.
# A conformance test that cannot fail is the silent non-conformance
# it was written to prevent, wearing a green check.
TEST = 'org-boundary/tests/test_manifest_bound_conformance.py'
REGISTER = Path('data/organization-role-exemption-register.json')
original = REGISTER.read_text(encoding='utf-8')

def run():
    return subprocess.run([sys.executable, TEST],
                          capture_output=True, text=True).returncode

assert run() == 0, 'the conformance check does not pass at head'

try:
    # Drop the entry registering the five refusing endpoints.
    document = json.loads(original)
    document['exemptions'] = [
        entry for entry in document['exemptions']
        if entry['exemption_id'] != 'SGHOST-EXEMPTION-002']
    REGISTER.write_text(json.dumps(document, indent=2), encoding='utf-8')
    assert run() != 0, \
        'an unregistered refusing endpoint passed; the register is decorative'

    # Let an exemption await a machine, which the standard forbids.
    document = json.loads(original)
    document['exemptions'][0]['awaits_an_external_machine'] = True
    REGISTER.write_text(json.dumps(document, indent=2), encoding='utf-8')
    assert run() != 0, 'an exemption awaiting a machine passed'

    # Empty the register entirely.
    document = json.loads(original)
    document['exemptions'] = []
    REGISTER.write_text(json.dumps(document, indent=2), encoding='utf-8')
    assert run() != 0, 'an empty register passed'
finally:
    REGISTER.write_text(original, encoding='utf-8')

assert run() == 0, 'the tree was not restored'
print('REGISTER_IS_LOAD_BEARING=PASS')
PY
