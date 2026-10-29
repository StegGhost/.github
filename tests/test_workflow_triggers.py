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

Since #34 the validators run as groups of tools/tasks/task_catalog.json under
.github/workflows/validation-dispatcher.yml, so the catalog is held to the same
rule: every group runs only on committed events, and the group that runs these
suites is the one that does.

The YAML is read as text (stdlib only). ALLOWLIST holds only workflows on a
declared other-lane surface (TVC, InTr-path, KV), handed off to that lane; an
entry leaves the list when its trigger is replaced.
"""
from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

#: path -> trigger keys handed off to another lane's surface, not edited here
#: (B-P40, R-SCOPE). None is a workflow trigger: every workflow here conforms.
ALLOWLIST: dict[str, set[str]] = {}

FORBIDDEN = {"workflow_dispatch", "schedule", "repository_dispatch"}
COMMITTED = {"pull_request", "push", "workflow_run"}
DISPATCHER = ".github/workflows/validation-dispatcher.yml"
CATALOG = ROOT / "tools" / "tasks" / "task_catalog.json"


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



class DispatcherCatalogTriggersTest(unittest.TestCase):
    """The folded validators keep the rule: no hand or clock trigger anywhere."""

    def test_dispatcher_runs_only_on_committed_events(self):
        found = dict(workflow_triggers())
        self.assertIn(DISPATCHER, found)
        self.assertTrue(found[DISPATCHER], "the dispatcher declares no trigger")
        self.assertLessEqual(found[DISPATCHER], COMMITTED, found[DISPATCHER])

    def test_every_catalog_group_runs_only_on_committed_events(self):
        groups = json.loads(CATALOG.read_text())["groups"]
        self.assertTrue(groups)
        for group in groups:
            with self.subTest(group=group["id"]):
                self.assertTrue(group["events"])
                self.assertLessEqual(set(group["events"]), COMMITTED)
                for step in group["steps"]:
                    self.assertNotRegex((ROOT / step["run_file"]).read_text(), r"^\s*-?\s*cron:")

    def test_these_suites_run_under_the_dispatcher(self):
        # The group runs tests.test_clock_marker_probe by name; its load_tests
        # pulls in this suite and the committed-request receipts suite.
        groups = {g["id"]: g for g in json.loads(CATALOG.read_text())["groups"]}
        group = groups["clock-marker-probe-validation.validate"]
        self.assertEqual(set(group["events"]), {"pull_request", "push"})
        bodies = "".join((ROOT / step["run_file"]).read_text() for step in group["steps"])
        self.assertIn("python -m unittest tests.test_clock_marker_probe", bodies)
        loaded = unittest.defaultTestLoader.loadTestsFromName("tests.test_clock_marker_probe")
        ids = set()
        stack = [loaded]
        while stack:
            item = stack.pop()
            if isinstance(item, unittest.TestSuite):
                stack.extend(item)
            else:
                ids.add(item.id().split(".")[1])
        self.assertTrue({"test_workflow_triggers", "test_committed_request_receipts"} <= ids, ids)


if __name__ == "__main__":
    unittest.main()
