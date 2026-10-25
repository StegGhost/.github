set -eu
python3 - <<'PY'
from pathlib import Path

source = Path('resident-runtime/release_organization_batch.py').read_text(
    encoding='utf-8')

# Recording is real at the organization ledger; batching hands a
# verified segment over. Fusing them is how the recorder becomes a
# gate, so `release` must not consult the destination at all.
body = source.split('def release(', 1)[1].split('\ndef ', 1)[0]
for reach in ('organization_record_destination', 'egress.emit', 'submit('):
    assert reach not in body, (
        'release() reaches for ' + reach + '; a release that consults '
        'the recorder is a release the recorder can gate')

# Verified means re-digested, not asserted.
assert 'if receipt.get("receipt_sha256") != sha(body):' in source
assert 'ORGANIZATION_LEDGER_RECEIPT_HASH_MISMATCH' in source

# Exactly-once is read off the chain, not remembered in a file.
assert 'def already_released(' in source
assert 'def prior_releases(' in source

# The refusal path says all four things, so a refused submission is
# neither a lost batch nor a pending one.
for statement in ('"release_stands": True',
                  '"awaits_an_external_machine": False',
                  '"queued_against_a_future_declaration": False',
                  '"unrecorded_batch_is_proof_of_non_occurrence": False'):
    assert statement in source, 'the refusal record omits ' + statement

# The control service is named only to refuse it, never to address it.
assert 'ORGANIZATION_RECORD_SERVICE_NOT_DECLARED_FOR_' in source
emit_call = source.split('result = egress.emit(', 1)[1][:400]
assert 'record_organization' in emit_call
assert 'org_control_service' not in emit_call, (
    'the batch must not be addressed at the control service')

# The kernel's closability map may be *explained* here -- the module
# says why it was deliberately not extended -- but never defined or
# mutated. Extending it would make this organization answer inbound
# record requests, claiming to be a recorder it is not. So the check
# is on an assignment, not on the name appearing in prose.
for mutation in ('RESPONDED_REQUEST_CLASSES =',
                  'RESPONDED_REQUEST_CLASSES=',
                  'RESPONDED_REQUEST_CLASSES[',
                  'RESPONDED_REQUEST_CLASSES.update',
                  'ACK_CLASSES =', 'ACK_CLASSES='):
    assert mutation not in source, (
        'this module alters the closability map (' + mutation + '); '
        'the kernel owns it, and extending it would make this '
        'organization answer inbound record requests')
# And the batch rides a class the kernel already answers, rather than
# a record-handover class that would have to be added to that map.
assert '"message_class": "ecosystem.communication"' in source
print('RELEASE_AND_SUBMISSION_STAY_TWO_ACTS=PASS')
PY
