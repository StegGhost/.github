# Organization Resident Runtime

This directory is the only canonical home for organization resident-runtime activation metadata and entrypoints.

Application repositories expose capabilities to this runtime. They do not independently activate an organization resident runtime.

All organization-crossing communications are generated through the adjacent `org-boundary` Interlock/InTr ingress/egress implementation.
