#!/usr/bin/env python3
"""Hold this organization's conformance declaration and exemption register to
the standard they cite, and hold the repository to the register.

The standard is
`EVERY_ACTION_IS_A_MANIFEST_BOUND_STATE_TRANSITION_AND_NO_EXTERNAL_MACHINE_IS_AWAITED`,
and the part of it that makes a register necessary rather than optional is
`silent_non_conformance_allowed: false`. A surface that cannot yet be bound is
not a defect by itself; a surface that cannot be bound and is *not written down*
is. So the failing condition this file exists to catch is not "a declaration is
missing a key" -- it is "this repository grew a non-conforming surface and the
register did not notice".

Four kinds of check, in rising order of how much they actually prove:

1. The declaration and register are shaped as the standard requires, and the
   two agree on the required-field list. Cheap, and only shape.

2. Every exemption carries all nine required fields non-empty, an actionable
   disposition, and `awaits_an_external_machine: false`. An exemption that
   awaited a machine would be the thing the standard forbids, dressed as a
   registration of it.

3. No entry leans on a prohibited justification, and no COSV is invented. The
   contract's own rule for an unresolvable COSV is to record
   `ABSENT_FROM_CURRENT_TASK_REGISTRY_SCHEMA`, not to mint one, and the same
   discipline applies to `owning_existing_goal` while no task registry exists
   here.

4. The register is checked against the repository, not just against itself.
   Every `INTERNAL_ENDPOINT` row in `services.json` with no installed adapter
   is a non-conforming surface, and every one of them must appear in some
   exemption's `surface`. Adding a seventh refusing endpoint without
   registering it fails here. The declared count of addressable sandbox legs is
   recomputed from the registry rather than trusted.

And one check that is about the code rather than the paperwork: processing
selection must be resolved from the admitted manifest at both dispatch
surfaces, and resolved *before* the first receipt is minted. A selection that
ran after the chain started would leave receipts for a crossing that is then
refused.

Nothing here grants authority. A passing run means the register is honest and
complete as of this commit; it does not mean any registered surface works.
"""
from __future__ import annotations

import json
import re
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

DECLARATION = ROOT / "data/organization-role-runtime-reality-deployment.json"
REGISTER = ROOT / "data/organization-role-exemption-register.json"
SERVICES = ROOT / "org-boundary/registry/services.json"

STANDARD = (
    "EVERY_ACTION_IS_A_MANIFEST_BOUND_STATE_TRANSITION_"
    "AND_NO_EXTERNAL_MACHINE_IS_AWAITED"
)
COSV_ABSENT = "ABSENT_FROM_CURRENT_TASK_REGISTRY_SCHEMA"

REQUIRED_FIELDS = (
    "surface",
    "owning_existing_goal",
    "failure_code",
    "failed_predicate",
    "why_manifest_bound_state_transition_is_not_yet_possible",
    "required_evidence_or_repair",
    "retry_entrypoint",
    "next_attempt",
    "expires_or_review_on",
)

# The ten keys the canonical declaration's conformance_standard carries. A
# declaration that dropped one would be declaring a weaker standard under the
# same name.
CONFORMANCE_KEYS = (
    "actions_by_manifest_required",
    "state_transition_dependent",
    "external_machine_awaiting_allowed",
    "destination_sufficiency_rule",
    "destination_liveness_is_transition_predicate",
    "receiver_unavailable_disposition",
    "always_on_receiver_required",
    "post_closure_authentic_observer_gate_allowed",
    "non_conforming_surface_disposition",
    "non_conforming_surface_failure_code",
)

checks: list[str] = []


def ok(label: str) -> None:
    checks.append(label)


def load(path: Path) -> dict:
    assert path.is_file(), f"{path.relative_to(ROOT)} is absent"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------- 1. shape

def test_declaration_shape(declaration: dict) -> None:
    assert declaration["schema"] == (
        "stegverse.organization-role-runtime-reality-deployment/v1")
    assert declaration["organization"] == "StegGhost", (
        "this declaration is this organization's own; deployment_scope is "
        "THIS_ORGANIZATION_ONLY and a declaration naming another organization "
        "would be declaring on its behalf")
    assert declaration["deployment_scope"] == (
        "THIS_ORGANIZATION_ONLY_EACH_ORGANIZATION_DEPLOYS_IN_ITS_OWN_DOT_GITHUB")
    assert declaration["authority_effect"] == "NONE_DECLARATION_ONLY"

    standard = declaration["conformance_standard"]
    missing = [k for k in CONFORMANCE_KEYS if k not in standard]
    assert not missing, f"conformance_standard dropped {missing}"

    # The three that carry the user's constraint rather than describing it.
    assert standard["actions_by_manifest_required"] is True
    assert standard["state_transition_dependent"] is True
    assert standard["external_machine_awaiting_allowed"] is False
    assert standard["always_on_receiver_required"] is False
    assert standard["destination_liveness_is_transition_predicate"] is False
    assert standard["post_closure_authentic_observer_gate_allowed"] is False
    assert standard["non_conforming_surface_disposition"] == (
        "DECLARED_EXEMPTION_REQUIRED")
    ok("DECLARATION_DECLARES_THE_FULL_STANDARD")


def test_register_shape(register: dict) -> None:
    assert register["schema"] == (
        "stegverse.organization-role-exemption-register/v1")
    assert register["standard"] == STANDARD
    assert register["silent_non_conformance_allowed"] is False
    assert register["exemption_grants_authority"] is False
    assert register["exemption_may_satisfy_a_terminal_predicate"] is False
    assert register["authority_effect"] == "NONE_REGISTER_ONLY"
    assert tuple(register["required_fields"]) == REQUIRED_FIELDS
    ok("REGISTER_DECLARES_ITS_OWN_LIMITS")


def test_declaration_and_register_agree(declaration: dict,
                                        register: dict) -> None:
    path = declaration["exemption_path"]
    assert path["register"] == "data/organization-role-exemption-register.json"
    assert (ROOT / path["register"]) == REGISTER
    assert tuple(path["required_fields"]) == tuple(register["required_fields"]), (
        "the declaration and the register must require the same fields; a "
        "shorter list on either side is a field nobody checks")
    assert path["exemption_grants_authority"] is False
    assert register["declaration"] == declaration["declaration_id"]

    # This register must not open empty, and must say why -- the canonical one
    # opens empty because that organization had nothing to register.
    assert path["register_opens_empty"] is False
    assert register["exemptions"], (
        "this organization carries non-conforming surfaces; an empty register "
        "here is the silent non-conformance the rule forbids")
    ok("DECLARATION_AND_REGISTER_AGREE")


# ------------------------------------------------- 2. every entry is complete

def test_every_exemption_is_complete(register: dict) -> None:
    seen: set[str] = set()
    declared_on = date.fromisoformat(
        load(DECLARATION)["declared_on"])

    for entry in register["exemptions"]:
        eid = entry.get("exemption_id")
        assert eid, "an exemption with no id cannot be cited or retired"
        assert eid not in seen, f"duplicate exemption id {eid}"
        seen.add(eid)

        for field in REQUIRED_FIELDS:
            assert field in entry, f"{eid} is missing {field}"
            value = entry[field]
            assert isinstance(value, str) and value.strip(), (
                f"{eid}.{field} is empty; a required field filled with nothing "
                f"is the absence it was added to prevent")

        assert entry["failure_code"] == "ORGANIZATION_ROLE_CONFORMANCE_NOT_DECLARED"

        review = date.fromisoformat(entry["expires_or_review_on"])
        assert review > declared_on, (
            f"{eid} reviews on or before the day it was declared, so it never "
            f"comes back for review")
        ok(f"{eid}_CARRIES_ALL_NINE_REQUIRED_FIELDS")


def test_no_exemption_awaits_a_machine(register: dict) -> None:
    for entry in register["exemptions"]:
        eid = entry["exemption_id"]
        assert entry.get("awaits_an_external_machine") is False, (
            f"{eid} awaits an external machine; registering that is not "
            f"conforming to the standard, it is recording a violation of it")
        assert entry.get("disposition_is_actionable") is True, (
            f"{eid} has no actionable disposition; a surface that neither "
            f"works nor refuses is the silent case")

        disposition = entry.get("disposition")
        assert isinstance(disposition, str) and disposition, (
            f"{eid} declares no disposition")

        if disposition.startswith("ALLOW"):
            # An ALLOW disposition is the dangerous shape: it means a crossing
            # completes. It is only admissible where the completion itself
            # conforms and the entry says why, in its own key.
            why = [k for k in entry if k.startswith("_why_the_disposition_is_ALLOW")]
            assert why, (
                f"{eid} allows a crossing to complete under an exemption and "
                f"does not say why that completion conforms")
        else:
            assert disposition.startswith("DENY"), (
                f"{eid} disposition {disposition!r} is neither an explained "
                f"ALLOW nor a DENY")
        ok(f"{eid}_DISPOSITION_IS_ACTIONABLE_AND_AWAITS_NOTHING")


# ------------------------------------- 3. no prohibited reason, no minted COSV

def test_no_prohibited_justification(register: dict) -> None:
    prohibited = register["prohibited_justifications"]
    assert prohibited, "the register must carry the prohibited list it checks"
    # Every prohibited justification the canonical standard names.
    for required in ("AN_EXTERNAL_MACHINE_MUST_BE_RUNNING",
                     "A_RECEIVER_IS_NOT_ALWAYS_ON",
                     "AN_AUTHENTIC_OBSERVER_HAS_NOT_YET_LOOKED"):
        assert required in prohibited, f"{required} must be prohibited"

    # A prohibited justification may be *named* -- 005 names the one it would
    # otherwise have leaned on, which is the honest move -- but may not be the
    # value of a field that justifies the exemption.
    justifying = (
        "failed_predicate",
        "next_attempt",
        "disposition",
    )
    for entry in register["exemptions"]:
        eid = entry["exemption_id"]
        for field in justifying:
            value = entry.get(field, "")
            for banned in prohibited:
                assert banned not in value, (
                    f"{eid}.{field} uses the prohibited justification {banned}")
    ok("NO_ENTRY_RESTS_ON_A_PROHIBITED_JUSTIFICATION")


def test_no_cosv_is_invented(register: dict) -> None:
    assert register["cosv"] == COSV_ABSENT, (
        "the ingress contract records COSV_UNRESOLVABLE_BY_CONSTRUCTION with "
        "the solution 'Record ABSENT_FROM_CURRENT_TASK_REGISTRY_SCHEMA; do not "
        "invent COSV.'")

    # No bare COSV identifier anywhere in the register. The one legitimate
    # central reference lives in prose that explains why none is minted, so
    # check the structured fields rather than the whole file.
    minted = re.compile(r"\bCOSV[\s:_-]*\d{6,}")
    for entry in register["exemptions"]:
        eid = entry["exemption_id"]
        for field, value in entry.items():
            if field.startswith("_") or not isinstance(value, str):
                continue
            found = minted.search(value)
            assert not found, f"{eid}.{field} mints a COSV: {found.group(0)!r}"

        assert entry["owning_existing_goal"] == COSV_ABSENT, (
            f"{eid} names an owning goal while this organization carries no "
            f"task registry; a goal invented to fill the field is the defect "
            f"the COSV rule forbids in the adjacent case")
    ok("NO_COSV_AND_NO_OWNING_GOAL_IS_INVENTED")


def test_the_absent_task_registry_is_itself_registered(register: dict) -> None:
    # 003 is load-bearing: it is why every other entry may record its owning
    # goal absent. If this repository ever grows a task registry, 003 fails and
    # the register is forced to re-point the other entries at real goals.
    predecessors = [e for e in register["exemptions"]
                    if e.get("_is_the_predecessor_repair")]
    assert len(predecessors) == 1, (
        "exactly one entry is the predecessor repair for the absent owning "
        "goal; found " + str(len(predecessors)))

    registry = ROOT / "orchestration/task-registry.json"
    assert not registry.exists(), (
        "orchestration/task-registry.json now exists, so owning_existing_goal "
        "is no longer unsatisfiable: every entry must name its owning goal and "
        f"{predecessors[0]['exemption_id']} must be retired")
    ok("ABSENT_TASK_REGISTRY_IS_REGISTERED_NOT_ASSUMED")


# ----------------------------------- 4. the register is checked against reality

def nonconforming_endpoints() -> list[str]:
    """Every service row that is declared and cannot receive a crossing.

    An INTERNAL_ENDPOINT selects a processor, so it needs an installed adapter
    to be entered at all. A BOUNDARY_LOCAL_* row *is* its own processor and
    needs none, so it is not a non-conforming surface.
    """
    services = load(SERVICES)["services"]
    return sorted(
        row["service_id"] for row in services
        if row.get("boundary_role") == "INTERNAL_ENDPOINT"
        and not row.get("endpoint_adapter")
    )


def test_every_nonconforming_endpoint_is_registered(register: dict) -> None:
    surfaces = " \n".join(e["surface"] for e in register["exemptions"])
    unregistered = [sid for sid in nonconforming_endpoints()
                    if sid not in surfaces]
    assert not unregistered, (
        "these endpoints are declared, refuse every crossing, and appear in no "
        "exemption, which is exactly the silent non-conformance the register "
        "exists to prevent: " + ", ".join(unregistered))
    ok("EVERY_REFUSING_ENDPOINT_IS_REGISTERED")


def test_registered_surfaces_still_exist(register: dict) -> None:
    # The mirror of the check above: an exemption for a row that has since been
    # fixed or removed is stale paperwork claiming a defect that is gone.
    declared = {row["service_id"] for row in load(SERVICES)["services"]}
    cited = set()
    for entry in register["exemptions"]:
        cited.update(re.findall(r"\bstegghost\.[a-z0-9-]+", entry["surface"]))
    missing = sorted(cited - declared)
    assert not missing, (
        "the register cites service rows that no longer exist: " +
        ", ".join(missing))

    still_refusing = set(nonconforming_endpoints())
    fixed = sorted(cited - still_refusing)
    assert not fixed, (
        "these rows now carry an adapter and no longer need an exemption; "
        "retire their entries: " + ", ".join(fixed))
    ok("NO_STALE_EXEMPTION_CLAIMS_A_DEFECT_THAT_IS_GONE")


def test_sandbox_leg_count_is_recomputed(declaration: dict) -> None:
    invariant = declaration["sandbox_path_invariant"]
    assert invariant["rule"] == (
        "THE_PATH_TO_AND_FROM_THE_SANDBOX_IS_STATE_TRANSITION_DEPENDENT_"
        "IN_BOTH_DIRECTIONS")
    assert invariant["return_is_a_state_transition_not_a_function_return"] is True
    assert invariant["each_leg_emits_an_organization_receipt"] is True

    # The declared count is not taken on faith. The sandbox legs are addressable
    # only if the row that receives them can be entered.
    rows = {r["service_id"]: r for r in load(SERVICES)["services"]}
    sandbox = rows.get("stegghost.entity-sandbox-runner")
    assert sandbox is not None, (
        "the declaration assigns this organization sandbox legs and the row "
        "that would receive them is absent")
    addressable = 3 if sandbox.get("endpoint_adapter") else 0
    assert invariant["legs_addressable_today"] == addressable, (
        f"legs_addressable_today declares {invariant['legs_addressable_today']}"
        f" and the registry supports {addressable}")

    if addressable == 0:
        assert invariant["inbound_leg_disposition"].startswith("REFUSED"), (
            "an inbound leg that is not addressable must refuse, not wait")
        assert invariant["exemption_registered"], (
            "an unaddressable assigned leg must cite its exemption")
        register = load(REGISTER)
        ids = {e["exemption_id"] for e in register["exemptions"]}
        assert invariant["exemption_registered"] in ids, (
            "the cited exemption is not in the register")
    ok("SANDBOX_LEG_COUNT_IS_RECOMPUTED_FROM_THE_REGISTRY")


def test_observer_gated_state_is_registered(register: dict) -> None:
    # The declaration forbids an observer gate. This repository holds two such
    # states today. They must be registered, and the register must still match
    # what the files say -- if a state is retired, its entry goes with it.
    gated = {
        "resident-runtime/activation-manifest.json":
            "UNIVERSAL_KERNEL_NETWORK_FEDERATION_SOURCE_INSTALLED_OBSERVATION_PENDING",
        "control/organization-runtime.json":
            "SOURCE_CONFIGURED_RUNTIME_NOT_CLAIMED",
    }
    live = {}
    for relative, expected in gated.items():
        document = load(ROOT / relative)
        live[relative] = document.get("state")
        assert live[relative] == expected, (
            f"{relative} state is now {live[relative]!r}; the register's "
            f"account of it is stale")

    cited = " \n".join(
        entry["surface"] + entry["why_manifest_bound_state_transition_is_not_yet_possible"]
        for entry in register["exemptions"])
    for relative, expected in gated.items():
        assert expected in cited, (
            f"{relative} holds {expected}, whose advance condition is that an "
            f"observation occurred, and no exemption registers it")
    ok("OBSERVER_GATED_STATES_ARE_REGISTERED_AND_CURRENT")


# ------------------------------------- 5. the code, not the paperwork

def test_processing_is_selected_from_the_manifest() -> None:
    module = ROOT / "org-boundary/runtime/manifest_selection.py"
    assert module.is_file(), (
        "the selection surface the declaration names is absent")
    source = module.read_text(encoding="utf-8")
    assert "SDK-GENERIC-MANIFEST-ECOSYSTEM-INVARIANT-005" in source
    # Selection is not admission, and the route table is not copied here.
    assert "NOT_RESOLVED_AT_BOUNDARY_ROUTE_OWNER_IS_SDK" in source, (
        "a passing selection must record that route installation was not "
        "resolved here, or a PASS reads as a proven installed route")
    assert "PUBLISHED_ROUTES" not in source.split('"""', 2)[-1], (
        "the capability-to-processor table belongs to the SDK; a copy here "
        "would make this boundary a second source of truth")

    # Anchored on the statement that actually mints, not on the list of receipt
    # kinds -- `KINDS` is a module constant declared above the dispatch body,
    # so its position says nothing about ordering.
    for relative, selects, mints in (
        ("org-kernel/kernel.py",
         "manifest_selection(root).select_processing",
         "r=receipt(kind,packet["),
        ("org-boundary/runtime/process_boundary.py",
         "selection.select_processing",
         "receipts.append("),
    ):
        text = (ROOT / relative).read_text(encoding="utf-8")
        assert selects in text, f"{relative} does not select from the manifest"
        assert mints in text, (
            f"{relative} no longer mints receipts the way this check reads it; "
            f"re-anchor rather than dropping the ordering check")
        # Selection must precede the first mint: a refused crossing must leave
        # no receipt behind.
        assert text.index(selects) < text.index(mints), (
            f"{relative} mints a receipt before selecting processing, so a "
            f"refused crossing leaves a chain for a crossing that did not "
            f"happen")
    ok("PROCESSING_IS_SELECTED_BY_THE_MANIFEST_BEFORE_ANY_RECEIPT")


def test_the_kernel_gates_reach_is_declared(declaration: dict) -> None:
    """The kernel gate runs, and it cannot enforce the binding. Hold both.

    `dispatch` refuses every role but the two boundary-local ones *before*
    selection runs, so selection there only ever resolves
    `BOUNDARY_LOCAL_NO_PROCESSOR_SELECTED` and the capability/route binding is
    never tested by the kernel today. Saying "gated at the kernel" without
    saying that would let a passing kernel dispatch read as an enforced
    binding. If the kernel ever grows an `INTERNAL_ENDPOINT` arm, this check
    fails and the declaration has to be corrected rather than quietly
    outgrown.
    """
    selection = declaration["processing_selection"]
    assert "org-kernel/kernel.py::dispatch" in selection["gated_at"]

    kernel = (ROOT / "org-kernel/kernel.py").read_text(encoding="utf-8")
    role_check = kernel.index('role not in {"BOUNDARY_LOCAL_DIAGNOSTIC"')
    selects_at = kernel.index("manifest_selection(root).select_processing")
    reaches_internal = role_check > selects_at or "INTERNAL_ENDPOINT" in kernel[
        role_check:selects_at]

    assert selection["kernel_gate_can_reach_an_internal_endpoint"] is \
        reaches_internal, (
            "the declaration's account of what the kernel gate can reach no "
            "longer matches the kernel: it declares "
            f"{selection['kernel_gate_can_reach_an_internal_endpoint']} and "
            f"the source says {reaches_internal}")

    if not reaches_internal:
        assert "BOUNDARY_LOCAL_NO_PROCESSOR_SELECTED" in (
            ROOT / "org-boundary/runtime/manifest_selection.py"
        ).read_text(encoding="utf-8"), (
            "the kernel can only resolve the boundary-local outcome, and the "
            "selection surface no longer has one to resolve")
    ok("KERNEL_GATE_REACH_IS_DECLARED_NOT_IMPLIED")


def main() -> int:
    declaration = load(DECLARATION)
    register = load(REGISTER)

    test_declaration_shape(declaration)
    test_register_shape(register)
    test_declaration_and_register_agree(declaration, register)
    test_every_exemption_is_complete(register)
    test_no_exemption_awaits_a_machine(register)
    test_no_prohibited_justification(register)
    test_no_cosv_is_invented(register)
    test_the_absent_task_registry_is_itself_registered(register)
    test_every_nonconforming_endpoint_is_registered(register)
    test_registered_surfaces_still_exist(register)
    test_sandbox_leg_count_is_recomputed(declaration)
    test_observer_gated_state_is_registered(register)
    test_processing_is_selected_from_the_manifest()
    test_the_kernel_gates_reach_is_declared(declaration)

    for label in checks:
        print(label + "=PASS")
    print(f"MANIFEST_BOUND_CONFORMANCE_CHECKS={len(checks)}")
    print("MANIFEST_BOUND_CONFORMANCE=PASS")
    print("AUTHORITY_EFFECT=NONE_VALIDATION_ONLY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
