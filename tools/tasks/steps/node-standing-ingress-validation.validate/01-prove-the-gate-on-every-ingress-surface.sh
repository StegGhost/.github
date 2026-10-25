set -eu
python3 org-kernel/tests/test_kernel.py
python3 org-boundary/tests/test_process_boundary.py
python3 -m py_compile org-boundary/runtime/node_standing.py \
  org-boundary/runtime/process_boundary.py \
  org-boundary/runtime/intr_transport.py \
  org-kernel/kernel.py \
  resident-runtime/ecosystem_control.py \
  resident-runtime/federation_gateway_transport.py
