set -eu
python3 - <<'PY'
from pathlib import Path
source = Path('org-boundary/runtime/emission_chain_disclosure.py').read_text(encoding='utf-8')

# A disclosure answers one packet id the asker already holds. It must
# not carry a payload, a chain, or another packet.
assert '"discloses_payloads": False' in source
assert '"discloses_other_packets": False' in source
for leak in ('payload_base64', '"payload"', 'packet_base64'):
    assert leak not in source, 'a disclosure must not carry ' + leak

# An unreachable or silent peer is never a pass. Three distinct
# answers, none of them a match.
assert 'NOT_AVAILABLE = ' in source
assert 'PEER_SERVED_NO_DISCLOSURE' in source
assert 'PEER_COULD_NOT_CONSULT_ITS_CHAIN' in source
assert 'PEER_CHAIN_HOLDS_NO_EMISSION_RECEIPT_FOR_THIS_PACKET' in source
# A receipt recording a crossing addressed elsewhere is not this one.
assert 'PEER_RECORDED_EMITTING_TO_A_DIFFERENT_ORGANIZATION' in source

# Unsatisfied is the default: the match result is built from findings,
# never defaulted to true.
assert 'bilateral_match_satisfied": satisfied' in source
assert '"makes_standing_authenticated": False' in source
assert '"makes_origin_attested_by_the_credential_authority": False' in source

boundary = Path('resident-runtime/organization_egress_boundary.py').read_text(encoding='utf-8')
# The ask is an ordinary recorded crossing, not a private path.
assert 'result = emit(claimed_origin, payload' in boundary, \
    'the ask must be emitted through the recorded boundary'
# An absence is not a transition, here as at closure.
assert boundary.count('absence_is_not_a_transition') >= 2
# The match has its own two disposition classes.
assert 'MATCH_SATISFIED_CLASS' in boundary and 'MATCH_REFUSED_CLASS' in boundary
# Closure still does not claim identity; it names where the match is.
assert 'bilateral_match_is_a_separate_transition' in boundary
assert '"reconstruction_proves_who_the_far_side_is": False' in boundary
print('DISCLOSURE_STAYS_NARROW=PASS')
print('SILENCE_IS_NEVER_A_PASS=PASS')
PY
