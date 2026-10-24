"""No workflow in ``.github/workflows`` is triggered by hand or by a clock.

B-P40 (ruling R-DISPATCH). No invariant names workflow_dispatch, schedule or
cron verbatim; the rule is derived from StegVerse-Labs/.github@149f16e
data/task-registry-global-invariants.json:54 (actions_by_manifest_required),
:58 (external_machine_awaiting_allowed false), :60 (always_on_receiver_required
false), :120 and :160-161, and data/sv-work-items/invariants.json:133 ("Nothing
reads a clock and nothing mints an epoch"). A run is a state transition bound
to what was committed: triggers are pull_request, push or workflow_run; a
writer takes its epoch from a committed request (COMMITTED_REQUEST), never
from a dispatch input or a schedule.

The YAML is read as text (stdlib only). ALLOWLIST holds the workflows whose
trigger another author wrote; each is listed on the owning Goal issue for its
owner to replace and leaves this list when it is.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: path -> trigger keys another author added, not edited here (B-P40).
ALLOWLIST = {
    ".github/workflows/bilateral-match-validation.yml": {"workflow_dispatch"},
    ".github/workflows/intr-destination-capability-validation.yml": {"workflow_dispatch"},
    ".github/workflows/node-standing-ingress-validation.yml": {"workflow_dispatch"},
    ".github/workflows/org-boundary-execution.yml": {"workflow_dispatch"},
    ".github/workflows/org-runtime-boundary.yml": {"workflow_dispatch"},
    ".github/workflows/organization-egress-boundary-validation.yml": {"workflow_dispatch"},
    ".github/workflows/organization-ledger-transition.yml": {"workflow_dispatch"},
}

FORBIDDEN = {"workflow_dispatch", "schedule", "repository_dispatch"}


def workflow_triggers():
    for path in sorted(WORKFLOWS.rglob("*")):
        if path.suffix not in (".yml", ".yaml") or not path.is_file():
            continue
        text = path.read_text()
        # The trigger keys sit two spaces in under the top-level `on:`.
        block = re.search(r"^(?:on|\"on\"|'on'):[ \t]*\n((?:[ \t]+.*\n|[ \t]*#.*\n|\n)*)", text, re.M)
        keys = set(re.findall(r"^  (\w+):", block.group(1), re.M)) if block else set()
        inline = re.search(r"^(?:on|\"on\"|'on'):[ \t]*(\S.*)$", text, re.M)
        if inline:
            keys |= set(re.findall(r"\w+", inline.group(1)))
        if re.search(r"^\s*-?\s*cron:", text, re.M):
            keys.add("schedule")
        yield path.relative_to(ROOT).as_posix(), keys


class WorkflowTriggersTest(unittest.TestCase):
    def test_no_manual_or_clock_trigger(self):
        found = list(workflow_triggers())
        self.assertTrue(found, "no workflows found under .github/workflows")
        bad = [
            f"{path}: {', '.join(sorted(keys & FORBIDDEN - ALLOWLIST.get(path, set())))}"
            for path, keys in found
            if keys & FORBIDDEN - ALLOWLIST.get(path, set())
        ]
        self.assertFalse(
            bad,
            "\n".join(
                [
                    "failure_code: WORKFLOW_MANUAL_DISPATCH_PRESENT",
                    "failed_predicate: ACTION_IS_STATE_TRANSITION_DEPENDENT; "
                    "found: " + "; ".join(bad),
                    "required_evidence_or_repair: validation workflows keep only "
                    "pull_request/push/workflow_run; a writer is triggered by a push "
                    "to main that commits its request and reads its epoch from it "
                    "(COMMITTED_REQUEST); a schedule job becomes a push/workflow_run "
                    "step or is deleted",
                    "retry_entrypoint: python -m unittest tests.test_workflow_triggers -v",
                    "owning_existing_goal: SVORG-LLM-ORG-FOUNDATION-001",
                    "next_attempt: remove the listed triggers and rerun the retry_entrypoint",
                ]
            ),
        )

    def test_allowlist_names_only_present_triggers(self):
        # An entry whose trigger is gone has been fixed and leaves the list.
        found = dict(workflow_triggers())
        for path, keys in ALLOWLIST.items():
            with self.subTest(path=path):
                self.assertIn(path, found)
                self.assertTrue(keys <= found[path], f"{path} no longer has {keys - found[path]}")


if __name__ == "__main__":
    unittest.main()
