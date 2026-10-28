set -eu
python3 - <<'PY'
from pathlib import Path
source = Path('org-boundary/runtime/node_standing.py').read_text(encoding='utf-8')
# local_second_predecessor_semantics_permitted is false, so the owner's
# field set is read off the contract rather than restated here.
assert 'predecessor_fields' in source
assert '"generation", "manifest_sha256", "result_sha256", "heartbeat_epoch"' not in source
assert 'CANONICAL_NODE_INGRESS_CONTRACT_001.json' in source
for marker in ('predecessor-key-absent', 'attestation_owner_state',
               'caller_editable_origin_established_identity'):
    assert marker in source, marker

kernel = Path('org-kernel/kernel.py').read_text(encoding='utf-8')
# Standing must resolve above the role branch, or only one dispatch
# arm is gated and the other is the bypass.
assert kernel.index('standing_module=node_standing(root)') \
     < kernel.index('role=service.get("boundary_role")'), \
    'standing must resolve before the role branch'
# No default standing anywhere: a silent default is the defaulting the
# contract exists to prevent.
assert 'standing:dict[str,Any]' in kernel
assert 'standing=None' not in kernel and 'standing={}' not in kernel

# process_boundary.py is run directly as a subprocess by
# resident-runtime/run_once.py, so a kernel-only gate leaves that lane
# open. It resolves standing itself, before any receipt is minted.
boundary = Path('org-boundary/runtime/process_boundary.py').read_text(encoding='utf-8')
assert 'node_standing.require(' in boundary, 'the crossing surface must resolve standing'
assert boundary.index('node_standing.require(') < boundary.index('receipts=[]'), \
    'standing must resolve before any receipt is minted'

transport = Path('org-boundary/runtime/intr_transport.py').read_text(encoding='utf-8')
assert '*,standing,' in transport, 'build_ingress must require standing'
assert '"standing","evidence"' in transport, 'standing must be in the required key set'
assert 'standing_carried_forward_from_request' in transport, \
    'an egress carries the request standing rather than declaring its own'

# Outbound: the operator declares standing, the runtime never mints one.
control = Path('resident-runtime/ecosystem_control.py').read_text(encoding='utf-8')
assert '"--standing",required=True' in control

# Egress: the answered-class set is one declaration, the closability
# refusal happens before anything is published, and the far side's
# terminal receipt is recomputed rather than carried.
assert 'RESPONDED_REQUEST_CLASSES={' in kernel
assert kernel.count('"ecosystem.monitor.request":"ecosystem.monitor.response"') == 1, \
    'the answered-class map must not be restated'
# A literal set of the answered classes is the bug this caught: the
# map declared four and the responder answered three, so a crossing
# the closability gate admitted was consumed and never answered. Every
# surface that decides what is answered reads the map.
gateway = Path('resident-runtime/federation_gateway_transport.py').read_text(encoding='utf-8')
for name, source in (('kernel', kernel), ('gateway', gateway)):
    literal = '"ecosystem.monitor.request", "ecosystem.work.request"'
    compact = '"ecosystem.monitor.request","ecosystem.work.request"'
    assert literal not in source and compact not in source, \
        name + ' restates the answered-class set instead of reading the map'
assert 'message_class in RESPONDED_REQUEST_CLASSES' in kernel, \
    'the responder must read the map'
assert 'K.RESPONDED_REQUEST_CLASSES' in gateway, \
    'the gateway lane must read the map'
# Likewise the acknowledgement set.
for name, source in (('kernel', kernel), ('gateway', gateway)):
    assert '"ecosystem.monitor.response","ecosystem.work.ack"' not in source, name
    assert '"ecosystem.monitor.response", "ecosystem.work.ack"' not in source, name
assert kernel.index('unclosable=closability_refusal(payload)') \
     < kernel.index('packets.append(packet)'), \
    'an unclosable crossing must be refused before it is collected for publishing'
assert 'def far_side_receipt_chain(' in kernel
assert 'FAR_SIDE_TERMINAL_RECEIPT_DOES_NOT_RECOMPUTE' in kernel
assert 'far_side_receipts_recomputed_here' in kernel, \
    'a collection that recomputed nothing must say so'
gateway = Path('resident-runtime/federation_gateway_transport.py').read_text(encoding='utf-8')
assert 'K.persist_outbox(repo_root, frame)' in gateway, \
    'the gateway lane must record its emissions or it cannot recompute'
assert 'K.far_side_receipt_chain(' in gateway

print('NODE_STANDING_CONTRACT_IS_THE_AUTHORITY=PASS')
print('EVERY_INGRESS_SURFACE_GATED=PASS')
print('EGRESS_CLOSABILITY_AND_RECOMPUTATION_ENFORCED=PASS')
PY
