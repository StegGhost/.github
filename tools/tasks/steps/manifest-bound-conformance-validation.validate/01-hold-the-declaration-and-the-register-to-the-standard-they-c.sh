set -eu
python3 org-boundary/tests/test_manifest_bound_conformance.py
python3 -m py_compile \
  org-boundary/runtime/manifest_selection.py \
  org-boundary/runtime/process_boundary.py \
  org-kernel/kernel.py
