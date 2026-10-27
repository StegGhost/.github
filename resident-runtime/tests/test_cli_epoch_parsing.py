#!/usr/bin/env python3
"""Prove every receipt-writing CLI hands --hb-epoch to the shared rule as typed.

An argparse `type=int` (or any int() ahead of the rule) reads "+33", "３３" and
" 33" as 33 and writes a receipt the shared rule would have refused. Each CLI
here must take the raw string, refuse every coerced, absent or malformed epoch
six-field FAIL_CLOSED with nothing written, and accept a supplied one.

Driven against scratch ledgers, so a run never touches the operator's chain.
"""
import json, os, subprocess, sys, tempfile
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
DIGEST = "sha256:" + "0" * 64
SIX_FIELDS = ("disposition", "failed_predicate", "retry_entrypoint",
              "owning_existing_goal", "next_attempt", "failure_code")
REFUSED = ["+33", "３３", " 33", "True", "abc", "33.7", "", None]
ACCEPTED = "4096"


def scratch():
    base = Path(tempfile.mkdtemp())
    (base / "inputs").mkdir()
    (base / "inputs/payload.json").write_text(json.dumps({"message_class": "probe"}))
    (base / "inputs/standing.json").write_text(json.dumps(
        {"mode": "ESTABLISH_GENESIS", "node_ref": "cli-epoch-test", "predecessor": None}))
    (base / "ledger-home").mkdir()
    # A real repository receipt for the aggregator to consume, written by a
    # supplied epoch; its ledger files are the baseline each run compares to.
    made = run(".stegverse/transition-ledger/emit.py",
               ["--transition-id", "cli-epoch-source", "--transition-class", "CLI_EPOCH_SOURCE",
                "--predecessor-state-sha256", DIGEST, "--successor-state-sha256", DIGEST],
               "64", base)
    assert made.returncode == 0, (made.stdout, made.stderr)
    (base / "inputs/receipt.json").write_text(made.stdout)
    return base


def written(base):
    """Every file under the scratch ledgers; the inputs are not ledger state."""
    return sorted(str(p.relative_to(base)) for p in base.rglob("*")
                  if p.is_file() and "inputs" not in p.relative_to(base).parts)


def run(script, args, epoch, base):
    env = dict(os.environ,
               # the designated subtree of the organization ledger (emit.py lr(), B-P40)
               STEGVERSE_REPO_LEDGER_ROOT=str(base / "org-ledger" / "repository-ledger/StegGhost/.github"),
               STEGVERSE_ORG_LEDGER_ROOT=str(base / "org-ledger"),
               STEGVERSE_REPO_LEDGER_HOME=str(base / "ledger-home"))
    argv = [sys.executable, str(TREE / script)] + [
        a.replace("{in}", str(base / "inputs")) for a in args]
    if epoch is not None:
        argv.append("--hb-epoch=" + epoch)
    return subprocess.run(argv, cwd=TREE, env=env, capture_output=True, text=True,
                          timeout=120)


def refusal_of(stdout):
    try:
        result = json.loads(stdout)
    except ValueError:
        return None
    if isinstance(result, dict) and str(result.get("failure_code", "")).startswith("HB_EPOCH_"):
        return result
    return None


CLIS = [
    (".stegverse/transition-ledger/emit.py",
     ["--transition-id", "cli-epoch", "--transition-class", "CLI_EPOCH_PROBE",
      "--predecessor-state-sha256", DIGEST, "--successor-state-sha256", DIGEST]),
    ("resident-runtime/aggregate_repo_transition.py",
     ["--transition-receipt", "{in}/receipt.json",
      "--predecessor-org-state-sha256", DIGEST, "--successor-org-state-sha256", DIGEST]),
    ("resident-runtime/intr_destination_ingress.py",
     ["--payload", "{in}/payload.json", "--packet-id", "cli-epoch"]),
    ("resident-runtime/organization_egress_boundary.py",
     ["--destination-organization", "StegVerse-Labs",
      "--payload", "{in}/payload.json", "--standing", "{in}/standing.json"]),
    ("resident-runtime/propagate_repository_receipts.py", []),
    ("resident-runtime/release_organization_batch.py", ["--release-only"]),
]

for script, args in CLIS:
    for epoch in REFUSED:
        base = scratch()
        before = written(base)
        proc = run(script, args, epoch, base)
        label = script + " --hb-epoch " + repr(epoch)
        assert proc.returncode != 0, (label, proc.stdout, proc.stderr)
        refusal = refusal_of(proc.stdout)
        assert refusal is not None, (label, proc.stdout, proc.stderr)
        for field in SIX_FIELDS:
            assert refusal.get(field), (label, field, refusal)
        assert refusal["disposition"] == "FAIL_CLOSED", (label, refusal)
        assert refusal["failure_code"] == ("HB_EPOCH_NOT_SUPPLIED" if epoch is None
                                           else "HB_EPOCH_INVALID"), (label, refusal)
        assert refusal["derived_from_clock"] is False, (label, refusal)
        assert refusal["consequence_committed"] is False, (label, refusal)
        assert written(base) == before, (label, before, written(base))

    base = scratch()
    proc = run(script, args, ACCEPTED, base)
    label = script + " --hb-epoch " + ACCEPTED
    assert refusal_of(proc.stdout) is None, (label, proc.stdout, proc.stderr)
    assert "HB_EPOCH_" not in proc.stderr, (label, proc.stderr)
    print("ok", script)

# The plain writer goes the whole way: 4096 is accepted and becomes the receipt's epoch.
base = scratch()
before = written(base)
proc = run(CLIS[0][0], CLIS[0][1], ACCEPTED, base)
assert proc.returncode == 0, (proc.stdout, proc.stderr)
receipt = json.loads(proc.stdout)
assert receipt["hb_reference"]["epoch"] == 4096, receipt
assert written(base) != before, "the accepted epoch wrote no receipt"
print("ok accepted 4096 writes a receipt at epoch 4096")
