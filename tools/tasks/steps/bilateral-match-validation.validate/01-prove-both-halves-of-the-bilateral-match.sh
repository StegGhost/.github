set -eu
python3 resident-runtime/tests/test_bilateral_match.py
python3 -m py_compile \
  org-boundary/runtime/emission_chain_disclosure.py \
  resident-runtime/organization_egress_boundary.py \
  org-kernel/kernel.py
