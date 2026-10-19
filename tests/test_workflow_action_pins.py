"""Every ``uses:`` in ``.github/workflows`` is pinned to a full commit sha.

A tag such as ``@v4`` can be moved to other code after review. A 40-hex sha
cannot. Local ``./`` actions are part of this repository and are excepted.
The tag a pin was taken from stays as a trailing comment.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

USES = re.compile(r"^\s*(?:-\s+)?uses:\s*['\"]?([^\s'\"#]+)")
PINNED = re.compile(r"^[^@\s]+@[0-9a-f]{40}$")


def workflow_uses():
    for path in sorted(WORKFLOWS.rglob("*")):
        if path.suffix not in (".yml", ".yaml") or not path.is_file():
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            match = USES.match(line)
            if match:
                yield path.relative_to(ROOT), number, match.group(1)


class WorkflowActionPinsTest(unittest.TestCase):
    def test_every_uses_is_pinned_to_a_full_sha(self):
        found = list(workflow_uses())
        self.assertTrue(found, "no uses: found under .github/workflows")
        unpinned = [
            f"{path}:{number}: {ref}"
            for path, number, ref in found
            if not ref.startswith("./") and not PINNED.match(ref)
        ]
        self.assertFalse(
            unpinned,
            "\n".join(
                [
                    "failure_code: WORKFLOW_ACTION_NOT_PINNED",
                    "failed_predicate: every non-local uses: in .github/workflows "
                    "matches <owner>/<action>@<40-hex sha>; unpinned: "
                    + "; ".join(unpinned),
                    "required_evidence_or_repair: resolve each tag with "
                    "`git ls-remote https://github.com/<owner>/<action> "
                    "refs/tags/<tag>` (peel annotated tags with ^{}), replace "
                    "the tag with the sha, and keep the tag as a trailing comment",
                    "retry_entrypoint: python -m unittest "
                    "tests.test_workflow_action_pins -v",
                    "owning_existing_goal: SVORG-LLM-ORG-FOUNDATION-001",
                    "next_attempt: pin the listed uses: and rerun the "
                    "retry_entrypoint",
                ]
            ),
        )


if __name__ == "__main__":
    unittest.main()
