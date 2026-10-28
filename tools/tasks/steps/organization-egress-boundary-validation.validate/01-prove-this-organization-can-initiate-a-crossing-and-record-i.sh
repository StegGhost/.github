set -eu
python3 resident-runtime/tests/test_organization_egress_boundary.py
python3 resident-runtime/tests/test_origin_attestation_seam.py
python3 resident-runtime/tests/test_cli_epoch_parsing.py
python3 -m py_compile \
  org-boundary/runtime/origin_attestation.py \
  resident-runtime/organization_egress_boundary.py \
  resident-runtime/aggregate_repo_transition.py \
  resident-runtime/ledger_store.py \
  .stegverse/transition-ledger/emit.py \
  org-kernel/kernel.py
