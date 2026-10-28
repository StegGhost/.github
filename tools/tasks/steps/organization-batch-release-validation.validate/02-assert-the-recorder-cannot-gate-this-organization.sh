set -eu
python3 - <<'PY'
import json, subprocess, sys
from pathlib import Path

# The failure worth catching is not a missing batch. It is a batch
# that gates: a release that only counts once the recorder
# acknowledges it. Mutate the contract three ways and require the
# conformance check to catch each.
CHECK = 'org-boundary/tests/test_manifest_bound_conformance.py'
CONTRACT = Path('.stegverse/transition-ledger/org-contract.json')
original = CONTRACT.read_text(encoding='utf-8')

def run():
    return subprocess.run([sys.executable, CHECK],
                          capture_output=True, text=True).returncode

assert run() == 0, 'the conformance check does not pass at head'
try:
    for field, value, label in (
        ('propagation_gates_organization_runtime_reality', True,
         'propagation gating runtime reality'),
        ('always_on_receiver_required', True,
         'an always-on recorder being required'),
        ('runtime_reality_authority',
         'RELEASED_ORGANIZATION_BATCH_RECEIPT_RECORDER',
         'runtime reality moving off the Organization'),
    ):
        document = json.loads(original)
        document[field] = value
        CONTRACT.write_text(json.dumps(document, indent=2), encoding='utf-8')
        assert run() != 0, label + ' passed the conformance check'
finally:
    CONTRACT.write_text(original, encoding='utf-8')
assert run() == 0, 'the contract was not restored'
print('THE_RECORDER_CANNOT_GATE_THIS_ORGANIZATION=PASS')
PY
