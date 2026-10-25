set -eu
python3 resident-runtime/tests/test_organization_batch_release.py
python3 org-boundary/tests/test_manifest_bound_conformance.py
python3 -m py_compile \
  resident-runtime/release_organization_batch.py \
  resident-runtime/propagate_repository_receipts.py \
  resident-runtime/organization_egress_boundary.py
