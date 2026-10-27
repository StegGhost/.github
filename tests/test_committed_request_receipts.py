"""B-P40 VALIDATOR rows on #28 (grade @c5ac403, comment 6388879437).

Row 1  a committed request.json that is deeply nested, or carries NaN or
       Infinity, is refused six-field by both workflow gates, never a traceback.
Row 2  every receipt our writers produce under a committed request names it
       (path, sha256, hb_epoch_source COMMITTED_REQUEST); half a pair or a
       malformed one is COMMITTED_REQUEST_INVALID, terminal, nothing written.
       Receipts written by InTr code are the optional Grok Lane B hand-off.
Row 3  a non-finite number in CLI JSON is refused before any write.
Row 4  the organization runtime refuses a non-object authority and a
       non-finite envelope six-field.
Row 5  ecosystem_control send-* takes its epoch from --hb-epoch or HB_EPOCH
       and refuses when absent; nothing it publishes reads a clock.

Stores live in temporary roots; nothing is written into this tree.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEEP = '{"a":' + "[" * 200000
REQUEST_ENV = ("STEGVERSE_COMMITTED_REQUEST_PATH", "STEGVERSE_COMMITTED_REQUEST_SHA256")
PAIR = {"STEGVERSE_COMMITTED_REQUEST_PATH": ".stegverse/organization-ledger-transition/request.json",
        "STEGVERSE_COMMITTED_REQUEST_SHA256": "sha256:" + "a" * 64}
#: The repository ledger's namespace in the organization ledger (B-P40: emit.py lr()).
REPOSITORY_NAMESPACE = json.loads((ROOT / ".stegverse/transition-ledger/contract.json").read_text())[
    "repository_ledger_location"]["namespace"]
SIX_FIELDS = ("failure_code", "failed_predicate", "required_evidence_or_repair",
              "retry_entrypoint", "owning_existing_goal", "next_attempt")


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


KERNEL = load("b_p40_kernel", "org-kernel/kernel.py")
HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                      text=True, check=True).stdout.strip()


def gate_script(workflow, step):
    lines = (ROOT / ".github/workflows" / workflow).read_text(encoding="utf-8").splitlines(keepends=True)
    start = lines.index("      - name: " + step + "\n")
    run = next(i for i in range(start, len(lines)) if lines[i] == "        run: |\n")
    body = []
    for line in lines[run + 1:]:
        if line.strip() and not line.startswith("          "):
            break
        body.append(line[10:] if line.strip() else "\n")
    return "".join(body)


class Scratch(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.tmp = Path(work.name)

    def env(self, **extra):
        env = {k: v for k, v in os.environ.items()
               if k not in REQUEST_ENV + ("HB_EPOCH", "GITHUB_ENV", "GITHUB_SHA")}
        env.update(STEGVERSE_REPO_LEDGER_ROOT=str(self.repo_ledger()),
                   STEGVERSE_ORG_LEDGER_ROOT=str(self.tmp / "org-ledger"),
                   STEGVERSE_ORG_FEDERATION_ROOT=str(self.tmp / "mesh"),
                   XDG_STATE_HOME=str(self.tmp / "state"))
        env.update(extra)
        return env

    def run_cli(self, relative, *args, **extra):
        return subprocess.run([sys.executable, str(ROOT / relative), *args], cwd=ROOT,
                              env=self.env(**extra), capture_output=True, text=True, check=False)

    def assert_six_field(self, result, code, rc):
        self.assertEqual(result.returncode, rc, (result.stdout, result.stderr))
        self.assertNotIn("Traceback", result.stderr + result.stdout)
        refusal = json.loads(result.stdout)
        self.assertEqual(refusal["disposition"], "FAIL_CLOSED")
        self.assertEqual(refusal["failure_code"], code, refusal)
        for field in SIX_FIELDS:
            self.assertTrue(refusal.get(field), (field, refusal))
        self.assertIs(refusal["consequence_committed"], False)
        return refusal

    def repo_ledger(self):
        """This repository's ledger: the designated subtree of the organization
        ledger (contract.json repository_ledger_location; emit.py lr(), B-P40)."""
        return self.tmp / "org-ledger" / REPOSITORY_NAMESPACE

    def files_under(self, *names):
        # "repo-ledger" is the repository subtree of the organization ledger;
        # "org-ledger" is the organization ledger's own files, without it.
        found = []
        for name in names:
            root = self.repo_ledger() if name == "repo-ledger" else self.tmp / name
            found += [p for p in root.rglob("*") if p.is_file()
                      and not (name == "org-ledger" and "repository-ledger" in p.relative_to(root).parts)]
        return found


class CommittedRequestGateRow1(Scratch):
    GATES = (("organization-ledger-transition.yml",
              "Refuse an absent, invalid or stale committed request before any append",
              "LEDGER_TRANSITION_REQUEST_INVALID"),
             ("resident-federation-cycle.yml",
              "Refuse an absent, invalid or stale committed request before the cycle",
              "FEDERATION_CYCLE_REQUEST_INVALID"))

    def run_gate(self, workflow, step, raw):
        request = self.tmp / "request.json"
        request.write_text(raw)
        env = self.env(REQUEST=str(request), LEDGER_REF="HEAD", LEDGER_HEAD=HEAD,
                       RUNNER_TEMP=str(self.tmp), GITHUB_ENV=str(self.tmp / "env"), GITHUB_SHA="0" * 40)
        return subprocess.run(["bash", "-e", "-c", gate_script(workflow, step)], cwd=ROOT, env=env,
                              capture_output=True, text=True, check=False)

    def test_deep_and_non_finite_requests_are_refused_six_field(self):
        for workflow, step, code in self.GATES:
            for raw in (DEEP, '{"hb_epoch": NaN, "ledger_head": "%s"}' % HEAD,
                        '{"hb_epoch": "4096", "ledger_head": "%s", "x": Infinity}' % HEAD,
                        '{"hb_epoch": "4096", "ledger_head": "%s", "x": 1e999}' % HEAD):
                with self.subTest(workflow=workflow, raw=raw[:40]):
                    self.assert_six_field(self.run_gate(workflow, step, raw), code, 1)
                    self.assertFalse((self.tmp / "env").exists())

    def test_an_accepted_request_exports_the_pair_to_the_writers(self):
        for workflow, step, _ in self.GATES:
            with self.subTest(workflow=workflow):
                (self.tmp / "env").unlink(missing_ok=True)
                raw = json.dumps({"hb_epoch": "4096", "ledger_head": HEAD, "communication_id": "c-1"})
                result = self.run_gate(workflow, step, raw)
                self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
                exported = dict(line.split("=", 1) for line in (self.tmp / "env").read_text().splitlines())
                self.assertEqual(exported["HB_EPOCH"], "4096")
                self.assertEqual(exported["STEGVERSE_COMMITTED_REQUEST_PATH"], str(self.tmp / "request.json"))
                self.assertEqual(exported["STEGVERSE_COMMITTED_REQUEST_SHA256"],
                                 "sha256:" + hashlib.sha256(raw.encode()).hexdigest())


class ReceiptsNameTheCommittedRequestRow2(Scratch):
    def emit(self, *extra_args, **extra):
        return self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "t-1",
                            "--transition-class", "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                            "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096",
                            *extra_args, **extra)

    def test_emit_and_aggregate_receipts_carry_the_committed_request(self):
        result = self.emit(**PAIR)
        self.assertEqual(result.returncode, 0, result.stderr)
        repo = json.loads(result.stdout)
        expected = {"path": PAIR["STEGVERSE_COMMITTED_REQUEST_PATH"],
                    "sha256": PAIR["STEGVERSE_COMMITTED_REQUEST_SHA256"], "hb_epoch_source": "COMMITTED_REQUEST"}
        self.assertEqual(repo["committed_request"], expected)
        source = self.tmp / "repo-receipt.json"
        source.write_text(json.dumps(repo))
        result = self.run_cli("resident-runtime/aggregate_repo_transition.py", "--repo-receipt", str(source),
                              "--predecessor-org-state-sha256", "sha256:" + "3" * 64,
                              "--successor-org-state-sha256", "sha256:" + "4" * 64, "--hb-epoch", "4096", **PAIR)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["committed_request"], expected)

    def test_no_pair_means_no_field(self):
        result = self.emit()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("committed_request", json.loads(result.stdout))

    def test_a_half_set_or_malformed_pair_is_refused_before_any_write(self):
        cases = ({"STEGVERSE_COMMITTED_REQUEST_PATH": PAIR["STEGVERSE_COMMITTED_REQUEST_PATH"]},
                 {"STEGVERSE_COMMITTED_REQUEST_SHA256": PAIR["STEGVERSE_COMMITTED_REQUEST_SHA256"]},
                 {**PAIR, "STEGVERSE_COMMITTED_REQUEST_SHA256": "sha256:" + "A" * 64},
                 {**PAIR, "STEGVERSE_COMMITTED_REQUEST_SHA256": "a" * 64},
                 {**PAIR, "STEGVERSE_COMMITTED_REQUEST_PATH": "../escape/request.json"},
                 {**PAIR, "STEGVERSE_COMMITTED_REQUEST_PATH": "/abs/request.json"})
        for env in cases:
            with self.subTest(env=env):
                refusal = self.assert_six_field(self.emit(**env), "COMMITTED_REQUEST_INVALID", 2)
                self.assertIs(refusal["terminal"], True)
                self.assertEqual(self.files_under("repo-ledger"), [])

    def test_the_cycle_record_carries_the_committed_request(self):
        root = self.tmp / "tree"
        (root / "org-kernel").mkdir(parents=True)
        shutil.copy2(ROOT / "org-kernel/kernel.py", root / "org-kernel/kernel.py")
        (root / "org-boundary/registry").mkdir(parents=True)
        (root / "org-boundary/registry/services.json").write_text(json.dumps(
            {"organization": "Org-C", "services": [{"service_id": "org-c.org-control",
                                                    "repository": "Org-C/.github",
                                                    "boundary_role": "BOUNDARY_LOCAL_CONTROL"}]}))
        cycle = load("b_p40_cycle", "resident-runtime/federation_cycle.py")
        cycle.ROOT = root
        saved = {k: os.environ.get(k) for k in (*REQUEST_ENV, "STEGVERSE_ORG_FEDERATION_ROOT")}
        os.environ.update(PAIR, STEGVERSE_ORG_FEDERATION_ROOT=str(self.tmp / "mesh"))
        try:
            import contextlib
            import io
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cycle.main(["--hb-epoch", "4096"]), 0)
        finally:
            for key, value in saved.items():
                os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)
        record = json.loads((root / "resident-runtime/federation/latest-cycle.json").read_text())
        self.assertEqual(record["committed_request"]["sha256"], PAIR["STEGVERSE_COMMITTED_REQUEST_SHA256"])
        self.assertEqual(record["committed_request"]["hb_epoch_source"], "COMMITTED_REQUEST")


class ForgedCommittedRequestIsRefused(Scratch):
    """V-P11 @722b416/@aa1a30f row 7 and the lead's 20:34Z ruling. A source
    receipt not on its repository ledger is SOURCE_RECEIPT_NOT_ON_LEDGER,
    committed_request or not. An on-ledger receipt whose claim is not the
    committed request is COMMITTED_REQUEST_DIGEST_UNVERIFIED. Nothing is copied."""

    def forged(self, claim):
        emit = load("b_p40_forge_emit", ".stegverse/transition-ledger/emit.py")
        body = {"schema": "stegverse.repo-transition-receipt/v1", "repository": emit.C["repository"],
                "transition_id": "forged", "transition_class": "T", "predecessor_state_sha256": "sha256:" + "1" * 64,
                "successor_state_sha256": "sha256:" + "2" * 64, "evidence": {}, "authority_effect": "NONE",
                "hb_reference": KERNEL.hb_reference(epoch=4096), "previous_receipt_sha256": None,
                "committed_request": claim}
        path = self.tmp / "forged.json"
        path.write_text(json.dumps({**body, "receipt_sha256": emit.sha(body)}))
        return path

    def on_ledger(self, **extra):
        result = self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "t-on", "--transition-class",
                              "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                              "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096", **extra)
        self.assertEqual(result.returncode, 0, result.stderr)
        path = self.tmp / "on-ledger.json"
        path.write_text(result.stdout)
        return path, json.loads(result.stdout)

    def aggregate(self, source, **extra):
        return self.run_cli("resident-runtime/aggregate_repo_transition.py", "--repo-receipt", str(source),
                            "--predecessor-org-state-sha256", "sha256:" + "3" * 64,
                            "--successor-org-state-sha256", "sha256:" + "4" * 64, "--hb-epoch", "4096", **extra)

    def claim(self, path, digest):
        return {"path": path, "sha256": digest, "hb_epoch_source": "COMMITTED_REQUEST"}

    def assert_refused_nothing_copied(self, result, code):
        refusal = self.assert_six_field(result, code, 2)
        self.assertIs(refusal["terminal"], True)
        self.assertEqual(self.files_under("org-ledger"), [])

    def test_an_off_ledger_receipt_carrying_committed_request_is_not_on_ledger(self):
        readme = "sha256:" + hashlib.sha256((ROOT / "README.md").read_bytes()).hexdigest()
        for claim, extra in ((self.claim(PAIR["STEGVERSE_COMMITTED_REQUEST_PATH"], "sha256:" + "f" * 64), PAIR),
                             (self.claim("README.md", "sha256:" + "f" * 64), {}),
                             # even the committed file's real digest, off the ledger
                             (self.claim("README.md", readme), {})):
            with self.subTest(claim=claim):
                self.assert_refused_nothing_copied(self.aggregate(self.forged(claim), **extra),
                                                   "SOURCE_RECEIPT_NOT_ON_LEDGER")

    def test_an_on_ledger_receipt_whose_claim_is_not_this_runs_request_is_unverified(self):
        source, _ = self.on_ledger(**PAIR)
        other = {**PAIR, "STEGVERSE_COMMITTED_REQUEST_SHA256": "sha256:" + "e" * 64}
        self.assert_refused_nothing_copied(self.aggregate(source, **other), "COMMITTED_REQUEST_DIGEST_UNVERIFIED")
        # With no run pair, the claim is checked against the committed file,
        # which this request path does not name in the tree.
        self.assert_refused_nothing_copied(self.aggregate(source), "COMMITTED_REQUEST_DIGEST_UNVERIFIED")
        # Positive control: the same run's pair.
        accepted = self.aggregate(source, **PAIR)
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)

    def test_an_on_ledger_receipt_tampered_after_the_append_is_not_on_ledger(self):
        source, on_ledger = self.on_ledger(**PAIR)
        emit = load("b_p40_tamper_emit", ".stegverse/transition-ledger/emit.py")
        body = {k: v for k, v in on_ledger.items() if k != "receipt_sha256"}
        body["committed_request"] = {**body["committed_request"], "sha256": "sha256:" + "e" * 64}
        source.write_text(json.dumps({**body, "receipt_sha256": emit.sha(body)}))
        self.assert_refused_nothing_copied(
            self.aggregate(source, **{**PAIR, "STEGVERSE_COMMITTED_REQUEST_SHA256": "sha256:" + "e" * 64}),
            "SOURCE_RECEIPT_NOT_ON_LEDGER")

    def test_a_malformed_claim_is_unverified(self):
        for claim in ("x", {"path": "README.md"}, {**self.claim("README.md", "sha256:" + "a" * 64), "extra": 1},
                      {**self.claim("README.md", "sha256:" + "a" * 64), "hb_epoch_source": "CLOCK"},
                      self.claim("../README.md", "sha256:" + "a" * 64)):
            with self.subTest(claim=claim):
                with self.assertRaises(KERNEL.CommittedRequestUnverified) as refused:
                    KERNEL.verify_carried_committed_request({"committed_request": claim}, ROOT, env={})
                self.assertEqual(refused.exception.refusal["failure_code"], "COMMITTED_REQUEST_DIGEST_UNVERIFIED")


class OffLedgerSourceWithoutBindingIsRefused(Scratch):
    """V-P11 @58e8177 OFF_LEDGER_SOURCE_RECEIPT_WITHOUT_BINDING_ACCEPTED: every
    source ingest is checked against its repository ledger, binding or not."""

    def receipt(self, transition_id):
        emit = load("b_p40_offledger_emit", ".stegverse/transition-ledger/emit.py")
        body = {"schema": "stegverse.repo-transition-receipt/v1", "repository": emit.C["repository"],
                "transition_id": transition_id, "transition_class": "T", "predecessor_state_sha256": "sha256:" + "1" * 64,
                "successor_state_sha256": "sha256:" + "2" * 64, "evidence": {}, "authority_effect": "NONE",
                "hb_reference": KERNEL.hb_reference(epoch=4096), "previous_receipt_sha256": None}
        return {**body, "receipt_sha256": emit.sha(body)}

    def aggregate(self, receipt, *extra_args):
        path = self.tmp / "source.json"
        path.write_text(json.dumps(receipt))
        return self.run_cli("resident-runtime/aggregate_repo_transition.py", "--repo-receipt", str(path),
                            "--predecessor-org-state-sha256", "sha256:" + "3" * 64,
                            "--successor-org-state-sha256", "sha256:" + "4" * 64, "--hb-epoch", "4096", *extra_args)

    def test_a_fabricated_receipt_with_a_consistent_hash_and_no_binding_is_refused(self):
        refusal = self.assert_six_field(self.aggregate(self.receipt("fabricated")),
                                        "SOURCE_RECEIPT_NOT_ON_LEDGER", 2)
        self.assertIs(refusal["terminal"], True)
        self.assertEqual(self.files_under("org-ledger"), [])

    def test_a_receipt_of_another_repository_off_its_ledger_is_refused(self):
        emit = load("b_p40_offledger_emit2", ".stegverse/transition-ledger/emit.py")
        body = {k: v for k, v in self.receipt("other-repo").items() if k != "receipt_sha256"}
        body["repository"] = "StegGhost/elsewhere"
        other = {**body, "receipt_sha256": emit.sha(body)}
        self.assert_six_field(self.aggregate(other), "SOURCE_RECEIPT_NOT_ON_LEDGER", 2)
        self.assertEqual(self.files_under("org-ledger"), [])


    def test_an_appended_receipt_is_accepted(self):
        result = self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "real", "--transition-class",
                              "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                              "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096")
        self.assertEqual(result.returncode, 0, result.stderr)
        accepted = self.aggregate(json.loads(result.stdout))
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        self.assertTrue(self.files_under("org-ledger"))

class SourceLedgerIsNotTheCallersChoiceRow8(Scratch):
    """V-P11 rows 8 and SOURCE_LEDGER_REDIRECTED_BY_ENV_VIA_EMIT_LR, lead rulings
    20:57Z/20:59Z. The repository ledger is the designated subtree
    (repository-ledger/<repository>) of the organization ledger; nothing a
    caller names, and no STEGVERSE_REPO_LEDGER_ROOT that differs from it,
    redirects aggregate or emit. A receipt minted with the real emit.py into an
    attacker's ledger is never laundered into the organization ledger."""

    def setUp(self):
        super().setUp()
        self.saved = {k: os.environ.get(k) for k in ("STEGVERSE_REPO_LEDGER_ROOT", "STEGVERSE_ORG_LEDGER_ROOT",
                                                    "STEGVERSE_REPO_LEDGER_HOME")}
        self.addCleanup(self.restore)
        self.use_real_ledger()
        os.environ["STEGVERSE_REPO_LEDGER_HOME"] = str(self.tmp / "ledger-home")
        self.aggregate = load("b_p40_row8_aggregate", "resident-runtime/aggregate_repo_transition.py")

    def restore(self):
        for key, value in self.saved.items():
            os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)

    def use_real_ledger(self):
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(self.tmp / "org-ledger")
        os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(self.repo_ledger())

    def minted_into(self, organization):
        """The attacker runs the real writer against an organization ledger of their own."""
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(organization)
        os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(organization / REPOSITORY_NAMESPACE)
        emit = load("b_p40_row8_emit_" + organization.name, ".stegverse/transition-ledger/emit.py")
        receipt = emit.append("fabricated", "T", "sha256:" + "1" * 64, "sha256:" + "2" * 64, {}, hb_epoch=4096)
        self.use_real_ledger()
        return receipt, organization / REPOSITORY_NAMESPACE

    def append(self, receipt, source_ledger=None):
        return self.aggregate.append(receipt, "REPO_STATE_PROPAGATION", "sha256:" + "3" * 64, "sha256:" + "4" * 64,
                                     {}, "NONE", hb_epoch=4096, source_ledger=source_ledger)

    def assert_refused(self, receipt, source_ledger, code="LEDGER_ROOT_NOT_CONTRACT_DESIGNATED"):
        # aggregate loads its own kernel copy: recognise the refusal by its record.
        with self.assertRaises(Exception) as refused:
            self.append(receipt, source_ledger)
        self.assertEqual(getattr(refused.exception, "refusal", {}).get("failure_code"), code, refused.exception)
        for field in SIX_FIELDS:
            self.assertTrue(refused.exception.refusal.get(field), field)
        self.assertEqual(self.files_under("org-ledger"), [])

    def test_an_attacker_ledger_is_refused(self):
        receipt, attacker = self.minted_into(self.tmp / "attacker")
        self.assert_refused(receipt, attacker)
        self.assert_refused(receipt, str(attacker))
        self.assert_refused(receipt, "git+" + str(attacker) + "#refs/stegverse/organization-ledger")
        # Read from the designated ledger, where it was never appended.
        self.assert_refused(receipt, None, code="SOURCE_RECEIPT_NOT_ON_LEDGER")

    def test_an_attacker_env_kept_set_redirects_neither_aggregate_nor_emit(self):
        # V-P11 final @a9893aa row 1: the attacker's STEGVERSE_REPO_LEDGER_ROOT
        # stays set while aggregate runs; aggregate still reads the designated
        # ledger, and emit refuses the diverging root.
        receipt, attacker = self.minted_into(self.tmp / "attacker")
        os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(attacker)
        self.assert_refused(receipt, None, code="SOURCE_RECEIPT_NOT_ON_LEDGER")
        emit = load("b_p40_row1_emit", ".stegverse/transition-ledger/emit.py")
        with self.assertRaises(Exception) as refused:
            emit.append("redirected", "T", "sha256:" + "1" * 64, "sha256:" + "2" * 64, {}, hb_epoch=4096)
        self.assertEqual(refused.exception.refusal["failure_code"], "LEDGER_ROOT_NOT_CONTRACT_DESIGNATED")
        self.assertEqual(self.files_under("repo-ledger", "org-ledger"), [])

    def test_a_symlink_to_an_attacker_ledger_is_refused(self):
        receipt, attacker = self.minted_into(self.tmp / "attacker")
        link = self.tmp / "looks-designated"
        link.symlink_to(attacker, target_is_directory=True)
        self.assert_refused(receipt, link)

    def test_another_repositorys_ledger_is_refused_for_this_repositorys_receipt(self):
        receipt, _ = self.minted_into(self.tmp / "attacker")
        self.assert_refused(receipt, self.tmp / "org-ledger" / "repository-ledger" / "StegGhost" / "elsewhere")

    def test_this_repositorys_ledger_is_accepted_by_its_real_path(self):
        emit = load("b_p40_row8_real_emit", ".stegverse/transition-ledger/emit.py")
        receipt = emit.append("real", "T", "sha256:" + "1" * 64, "sha256:" + "2" * 64, {}, hb_epoch=4096)
        link = self.tmp / "store-link"
        link.symlink_to(self.repo_ledger(), target_is_directory=True)
        self.assertEqual(self.append(receipt, link)["repo_receipt_sha256"], receipt["receipt_sha256"])

    def test_the_repository_ledger_home_is_not_ledger_evidence(self):
        # REPO_LEDGER_HOME_DEFAULT_INSIDE_CHECKOUT (lead 20:57Z): an attacker's
        # directory named by STEGVERSE_REPO_LEDGER_HOME holds another
        # repository's "ledger"; it is scratch, never evidence.
        attacker = self.tmp / "attacker-home"
        os.environ["STEGVERSE_REPO_LEDGER_HOME"] = str(attacker)
        emit = load("b_p40_home_emit", ".stegverse/transition-ledger/emit.py")
        body = {"schema": "stegverse.repo-transition-receipt/v1", "repository": "StegGhost/other",
                "transition_id": "fab", "transition_class": "T", "predecessor_state_sha256": "sha256:" + "1" * 64,
                "successor_state_sha256": "sha256:" + "2" * 64, "evidence": {}, "authority_effect": "NONE",
                "hb_reference": KERNEL.hb_reference(epoch=4096), "previous_receipt_sha256": None}
        receipt = {**body, "receipt_sha256": emit.sha(body)}
        store_module = load("b_p40_home_store", "resident-runtime/ledger_store.py")
        root = attacker / "StegGhost" / "other"
        store = store_module.open_store(root)
        store.initialize()
        store.append_transaction(store_module.receipt_key(receipt["receipt_sha256"]), receipt, None,
                                 {"receipt_sha256": receipt["receipt_sha256"]})
        self.assert_refused(receipt, root)
        self.assert_refused(receipt, None, code="SOURCE_RECEIPT_NOT_ON_LEDGER")

    def checkout(self):
        """A scratch git checkout standing in for this repository's tree."""
        tree = self.tmp / "checkout"
        for relative in (".stegverse/transition-ledger/contract.json", ".stegverse/transition-ledger/org-contract.json",
                         ".stegverse/transition-ledger/emit.py", "org-kernel/kernel.py",
                         "resident-runtime/ledger_store.py"):
            (tree / relative).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, tree / relative)
        for args in (["init", "-q"], ["config", "user.email", "probe@example.invalid"], ["config", "user.name", "probe"]):
            subprocess.run(["git", "-C", str(tree), *args], check=True)
        self.aggregate.ROOT = tree
        return tree

    def test_a_ledger_committed_into_the_checkout_is_refused(self):
        tree = self.checkout()
        organization = tree / ".stegverse-run/state/stegverse/org-ledgers/StegGhost"
        receipt, _ = self.minted_into(organization)
        subprocess.run(["git", "-C", str(tree), "add", "-f", "."], check=True)
        subprocess.run(["git", "-C", str(tree), "commit", "-q", "-m", "fake ledger"], check=True)
        # The organization ledger this run would use is inside the checkout and
        # its files are tracked: not evidence.
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(organization)
        os.environ.pop("STEGVERSE_REPO_LEDGER_ROOT", None)
        with self.assertRaises(Exception) as refused:
            self.append(receipt)
        self.assertEqual(refused.exception.refusal["failure_code"], "LEDGER_ROOT_NOT_CONTRACT_DESIGNATED")

    def test_the_designated_ledger_is_accepted(self):
        tree = self.checkout()
        location = json.loads((ROOT / ".stegverse/transition-ledger/contract.json").read_text())["repository_ledger_location"]
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = "git+" + str(tree) + "#" + location["ref"]
        os.environ.pop("STEGVERSE_REPO_LEDGER_ROOT", None)
        emit = load("b_p40_designated_emit", ".stegverse/transition-ledger/emit.py")
        emit.C = {**emit.C, "repository": "StegGhost/other"}
        receipt = emit.append("designated", "T", "sha256:" + "1" * 64, "sha256:" + "2" * 64, {}, hb_epoch=4096)
        organization = self.append(receipt)
        self.assertEqual(organization["repo_receipt_sha256"], receipt["receipt_sha256"])

    def test_the_cli_has_no_source_ledger_flag(self):
        self.assertNotIn("--source-ledger", (ROOT / "resident-runtime/aggregate_repo_transition.py").read_text())


class CrossRepositoryPropagationRow2(Scratch):
    """V-P11 final @a9893aa CROSS_REPO_PROPAGATE_BROKEN: propagate reads another
    repository's receipts from its contract-designated ledger, on a git
    organization ledger and a POSIX one alike."""

    def setUp(self):
        super().setUp()
        saved = {k: os.environ.get(k) for k in ("STEGVERSE_REPO_LEDGER_ROOT", "STEGVERSE_ORG_LEDGER_ROOT")}
        self.addCleanup(lambda: [os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
                                 for k, v in saved.items()])
        os.environ.pop("STEGVERSE_REPO_LEDGER_ROOT", None)

    def propagate_other(self, organization):
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = organization
        emit = load("b_p40_row2_emit_" + str(abs(hash(organization))), ".stegverse/transition-ledger/emit.py")
        emit.C = {**emit.C, "repository": "StegGhost/other"}
        first = emit.append("other-1", "T", "sha256:" + "1" * 64, "sha256:" + "2" * 64, {}, hb_epoch=4096)
        second = emit.append("other-2", "T", "sha256:" + "2" * 64, "sha256:" + "3" * 64, {}, hb_epoch=4096)
        propagation = load("b_p40_row2_propagate_" + str(abs(hash(organization))),
                           "resident-runtime/propagate_repository_receipts.py")
        result = propagation.propagate("StegGhost/other", hb_epoch=4096)
        self.assertEqual([p["repository_receipt_sha256"] for p in result["propagated"]],
                         [first["receipt_sha256"], second["receipt_sha256"]])
        again = propagation.propagate("StegGhost/other", hb_epoch=4096)
        self.assertEqual((again["propagated"], len(again["skipped"])), ([], 2))

    def test_a_git_organization_ledger(self):
        repository = self.tmp / "ledger.git"
        subprocess.run(["git", "init", "-q", "--bare", str(repository)], check=True)
        self.propagate_other("git+" + str(repository) + "#refs/stegverse/organization-ledger")

    def test_a_posix_organization_ledger(self):
        self.propagate_other(str(self.tmp / "org-ledger"))


class CorruptPredecessorIsRefusedRow3(Scratch):
    """V-P11 final @a9893aa: a source receipt on a chain whose predecessor is
    corrupt or missing is refused six-field; nothing is aggregated."""

    def chain(self):
        receipts = []
        for index in (1, 2):
            result = self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "t-" + str(index),
                                  "--transition-class", "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                                  "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096")
            self.assertEqual(result.returncode, 0, result.stderr)
            receipts.append(json.loads(result.stdout))
        self.assertEqual(receipts[1]["previous_receipt_sha256"], receipts[0]["receipt_sha256"])
        return receipts

    def stored(self, receipt):
        return self.repo_ledger() / ("receipts/" + receipt["receipt_sha256"].split(":", 1)[1] + ".json")

    def aggregate(self, receipt):
        source = self.tmp / "source.json"
        source.write_text(json.dumps(receipt))
        return self.run_cli("resident-runtime/aggregate_repo_transition.py", "--repo-receipt", str(source),
                            "--predecessor-org-state-sha256", "sha256:" + "3" * 64,
                            "--successor-org-state-sha256", "sha256:" + "4" * 64, "--hb-epoch", "4096")

    def test_a_tampered_predecessor_is_refused(self):
        first, second = self.chain()
        tampered = dict(json.loads(self.stored(first).read_text()), transition_class="FORGED")
        self.stored(first).write_text(json.dumps(tampered))
        for receipt in (second, first):
            with self.subTest(receipt=receipt["transition_id"]):
                self.assert_six_field(self.aggregate(receipt), "SOURCE_RECEIPT_NOT_ON_LEDGER", 2)
        self.assertEqual(self.files_under("org-ledger"), [])

    def test_a_missing_predecessor_is_refused(self):
        first, second = self.chain()
        self.stored(first).unlink()
        self.assert_six_field(self.aggregate(second), "SOURCE_RECEIPT_NOT_ON_LEDGER", 2)
        self.assertEqual(self.files_under("org-ledger"), [])

    def test_an_intact_chain_is_accepted(self):
        _, second = self.chain()
        result = self.aggregate(second)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


class CorruptSourceLedgerIsRefusedRow9(Scratch):
    """V-P11 @b28cb64 row 9 SOURCE_LEDGER_WALK_TRACEBACK_ON_CORRUPT_RECEIPT: a
    corrupt stored receipt is refused six-field, an OSError is non-terminal;
    never a traceback, nothing copied."""

    def corrupted(self, damage):
        result = self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "t", "--transition-class",
                              "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                              "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096")
        self.assertEqual(result.returncode, 0, result.stderr)
        receipt = json.loads(result.stdout)
        stored = self.repo_ledger() / ("receipts/" + receipt["receipt_sha256"].split(":", 1)[1] + ".json")
        self.assertTrue(stored.is_file())
        damage(stored)
        source = self.tmp / "source.json"
        source.write_text(json.dumps(receipt))
        return self.run_cli("resident-runtime/aggregate_repo_transition.py", "--repo-receipt", str(source),
                            "--predecessor-org-state-sha256", "sha256:" + "3" * 64,
                            "--successor-org-state-sha256", "sha256:" + "4" * 64, "--hb-epoch", "4096")

    def test_a_truncated_or_garbage_receipt_is_refused_six_field(self):
        for name, damage in (("truncated", lambda p: p.write_text(p.read_text()[:20])),
                             ("garbage", lambda p: p.write_bytes(b"\xff\x00 not json")),
                             ("directory", lambda p: (p.unlink(), p.mkdir()))):
            with self.subTest(damage=name):
                refusal = self.assert_six_field(self.corrupted(damage), "SOURCE_RECEIPT_NOT_ON_LEDGER", 2)
                self.assertIs(refusal["terminal"], True)
                self.assertEqual(self.files_under("org-ledger"), [])
                shutil.rmtree(self.repo_ledger())

    def test_an_unreadable_receipt_is_a_non_terminal_retry(self):
        saved = {k: os.environ.get(k) for k in ("STEGVERSE_REPO_LEDGER_ROOT", "STEGVERSE_ORG_LEDGER_ROOT")}
        os.environ.update(STEGVERSE_REPO_LEDGER_ROOT=str(self.repo_ledger()),
                          STEGVERSE_ORG_LEDGER_ROOT=str(self.tmp / "org-ledger"))
        try:
            emit = load("b_p40_row9_emit", ".stegverse/transition-ledger/emit.py")
            receipt = emit.append("t", "T", "sha256:" + "1" * 64, "sha256:" + "2" * 64, {}, hb_epoch=4096)
            aggregate = load("b_p40_row9_aggregate", "resident-runtime/aggregate_repo_transition.py")
            real_open = aggregate.open_store

            class Unreadable:
                def __init__(self, store):
                    self.store = store

                def get(self, key):
                    if key.startswith("receipts/"):
                        raise PermissionError(13, "Permission denied", key)
                    return self.store.get(key)
            aggregate.open_store = lambda location: Unreadable(real_open(location))
            with self.assertRaises(aggregate.kernel.LedgerWriteFailed) as failed:
                aggregate.append(receipt, "REPO_STATE_PROPAGATION", "sha256:" + "3" * 64, "sha256:" + "4" * 64,
                                 {}, "NONE", hb_epoch=4096)
            self.assertIs(failed.exception.refusal["terminal"], False)
            self.assertEqual(self.files_under("org-ledger"), [])
        finally:
            for key, value in saved.items():
                os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)


class CallerEvidenceCannotSetCommittedRequestRow5(Scratch):
    """V-P11 @aa1a30f row 5: committed_request inside caller evidence, at any
    depth, CLI or in-process, pair set or unset, is COMMITTED_REQUEST_FORGED
    before any write."""

    FORGED = {"committed_request": {"path": "forged", "sha256": "sha256:" + "f" * 64,
                                    "hb_epoch_source": "COMMITTED_REQUEST"}}

    def test_the_cli_refuses_forged_evidence_with_or_without_the_pair(self):
        for evidence in (self.FORGED, {"a": [{"b": self.FORGED}]}):
            for extra in ({}, PAIR):
                with self.subTest(evidence=evidence, pair=bool(extra)):
                    result = self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "t", "--transition-class",
                                          "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                                          "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096",
                                          "--evidence-json", json.dumps(evidence), **extra)
                    self.assert_six_field(result, "COMMITTED_REQUEST_FORGED", 2)
                    self.assertEqual(self.files_under("repo-ledger"), [])
                    # A genuine on-ledger source, so only the evidence is at fault.
                    ok = self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "t-src",
                                      "--transition-class", "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                                      "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096", **extra)
                    self.assertEqual(ok.returncode, 0, ok.stderr)
                    receipt = self.tmp / "r.json"
                    receipt.write_text(ok.stdout)
                    result = self.run_cli("resident-runtime/aggregate_repo_transition.py", "--repo-receipt", str(receipt),
                                          "--predecessor-org-state-sha256", "sha256:" + "3" * 64,
                                          "--successor-org-state-sha256", "sha256:" + "4" * 64, "--hb-epoch", "4096",
                                          "--boundary-evidence-json", json.dumps(evidence), **extra)
                    self.assert_six_field(result, "COMMITTED_REQUEST_FORGED", 2)
                    self.assertEqual(self.files_under("org-ledger"), [])
                    shutil.rmtree(self.repo_ledger())

    def test_in_process_append_refuses_forged_evidence(self):
        saved = {k: os.environ.get(k) for k in ("STEGVERSE_REPO_LEDGER_ROOT", "STEGVERSE_ORG_LEDGER_ROOT")}
        os.environ.update(STEGVERSE_REPO_LEDGER_ROOT=str(self.repo_ledger()),
                          STEGVERSE_ORG_LEDGER_ROOT=str(self.tmp / "org-ledger"))
        try:
            emit = load("b_p40_row5_emit", ".stegverse/transition-ledger/emit.py")
            aggregate = load("b_p40_row5_aggregate", "resident-runtime/aggregate_repo_transition.py")
            with self.assertRaises(Exception) as caught:
                emit.append("t", "T", "sha256:" + "1" * 64, "sha256:" + "2" * 64, {"x": [self.FORGED]}, hb_epoch=4096)
            self.assertEqual(caught.exception.refusal["failure_code"], "COMMITTED_REQUEST_FORGED")
            receipt = emit.append("t-ok", "T", "sha256:" + "1" * 64, "sha256:" + "2" * 64, {}, hb_epoch=4096)
            with self.assertRaises(Exception) as caught:
                aggregate.append(receipt, "REPO_STATE_PROPAGATION", "sha256:" + "3" * 64, "sha256:" + "4" * 64,
                                 self.FORGED, "NONE", hb_epoch=4096)
            self.assertEqual(caught.exception.refusal["failure_code"], "COMMITTED_REQUEST_FORGED")
            self.assertEqual(self.files_under("org-ledger"), [])
        finally:
            for key, value in saved.items():
                os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)

    def test_a_cyclic_evidence_value_terminates(self):
        cyclic = {"a": []}
        cyclic["a"].append(cyclic)
        KERNEL.refuse_caller_committed_request(cyclic, argument="evidence")
        cyclic["a"].append(self.FORGED)
        with self.assertRaises(KERNEL.CommittedRequestForged):
            KERNEL.refuse_caller_committed_request(cyclic, argument="evidence")

    def test_a_deep_evidence_value_is_scanned_not_a_recursion_error(self):
        deep = self.FORGED
        for _ in range(5000):
            deep = {"n": [deep]}
        with self.assertRaises(KERNEL.CommittedRequestForged):
            KERNEL.refuse_caller_committed_request(deep, argument="evidence")


class EgressRefusesABadPairBeforePublishRow6(Scratch):
    """V-P11 @aa1a30f row 6: a half-set or malformed pair is refused six-field
    at the top of egress emit and request_bilateral_match; nothing is published."""

    def test_emit_and_bilateral_match_publish_nothing_on_a_bad_pair(self):
        egress = load("b_p40_row6_egress", "resident-runtime/organization_egress_boundary.py")
        standing = {"mode": "ESTABLISH_GENESIS", "node_ref": "b-p40-node", "predecessor": None}
        for bad in ({"STEGVERSE_COMMITTED_REQUEST_PATH": "x/r.json"},
                    {**PAIR, "STEGVERSE_COMMITTED_REQUEST_SHA256": "sha256:XYZ"}):
            saved = {k: os.environ.get(k) for k in REQUEST_ENV}
            for key in REQUEST_ENV:
                os.environ.pop(key, None)
            os.environ.update(bad)
            try:
                for call in (lambda: egress.emit("Org-B", {"message_class": "ecosystem.communication"},
                                                 standing=standing, mesh_root=self.tmp / "mesh", hb_epoch=4096),
                             lambda: egress.request_bilateral_match("Org-B", "p-1", standing=standing,
                                                                    mesh_root=self.tmp / "mesh", hb_epoch=4096)):
                    with self.subTest(bad=bad):
                        result = call()
                        self.assertEqual((result["disposition"], result["failure_code"], result["emitted"]),
                                         ("FAIL_CLOSED", "COMMITTED_REQUEST_INVALID", False))
                        for field in SIX_FIELDS:
                            self.assertTrue(result.get(field), field)
                        self.assertEqual(self.files_under("mesh"), [])
            finally:
                for key, value in saved.items():
                    os.environ.pop(key, None) if value is None else os.environ.__setitem__(key, value)


class NonFiniteCliInputRow3(Scratch):
    def test_emit_and_aggregate_refuse_non_finite_json_before_any_write(self):
        for value in ('{"a":NaN}', '{"a":-Infinity}', '{"a":1e999}'):
            with self.subTest(value=value):
                result = self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "t", "--transition-class",
                                      "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                                      "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096",
                                      "--evidence-json", value)
                self.assert_six_field(result, "CLI_INPUT_UNREADABLE", 2)
                receipt = self.tmp / "r.json"
                receipt.write_text("{}")
                result = self.run_cli("resident-runtime/aggregate_repo_transition.py", "--repo-receipt", str(receipt),
                                      "--predecessor-org-state-sha256", "sha256:" + "3" * 64,
                                      "--successor-org-state-sha256", "sha256:" + "4" * 64, "--hb-epoch", "4096",
                                      "--boundary-evidence-json", value)
                self.assert_six_field(result, "CLI_INPUT_UNREADABLE", 2)
                self.assertEqual(self.files_under("repo-ledger", "org-ledger"), [])

    def test_the_writers_never_serialize_a_non_finite_number(self):
        emit = load("b_p40_emit", ".stegverse/transition-ledger/emit.py")
        aggregate = load("b_p40_aggregate", "resident-runtime/aggregate_repo_transition.py")
        for canon in (emit.canon, aggregate.canon):
            with self.assertRaises(ValueError):
                canon({"a": float("nan")})


class RuntimeIngressRow4(Scratch):
    def envelope(self, authority=None, extra=None):
        payload = b"payload"
        intent = {"schema": "stegverse.universal-intr-transport/v1", "protocol": "InTr", "packet_id": "p-1",
                  "payload_hash": "sha256:" + hashlib.sha256(payload).hexdigest(),
                  "authority": authority if authority is not None else {"transport_grants_execution_authority": False}}
        env = {"schema": "stegverse.organization-interlock-envelope/v1", "intr_intent": intent,
               "payload_base64": base64.b64encode(payload).decode(), **(extra or {})}
        return {**env, "envelope_hash": KERNEL.sha(env)}

    def test_a_non_object_authority_is_a_six_field_refusal(self):
        for authority in ("x", [1]):
            with self.subTest(authority=authority):
                path = self.tmp / "env.json"
                path.write_text(json.dumps(self.envelope(authority)))
                result = self.run_cli("runtime/organization_runtime.py", "ingress", "--file", str(path), "--hb-epoch", "4096")
                refusal = self.assert_six_field(result, "RUNTIME_BOUNDARY_REFUSED", 2)
                self.assertIn("authority", refusal["detail"])

    def test_a_non_finite_envelope_is_refused(self):
        path = self.tmp / "env.json"
        path.write_text(json.dumps(self.envelope()).replace('"p-1"', 'NaN', 1))
        result = self.run_cli("runtime/organization_runtime.py", "ingress", "--file", str(path), "--hb-epoch", "4096")
        self.assert_six_field(result, "CLI_INPUT_UNREADABLE", 2)
        runtime = load("b_p40_runtime", "runtime/organization_runtime.py")
        with self.assertRaises(runtime.RuntimeBoundaryError):
            runtime.ingress({**self.envelope(), "x": float("inf")}, hb_epoch=4096)


class EcosystemControlEpochRow5(Scratch):
    def test_send_refuses_an_absent_epoch_before_anything_is_published(self):
        standing = self.tmp / "standing.json"
        standing.write_text("{}")
        for value in (None, "", "abc", "31"):
            with self.subTest(value=value):
                args = ["send-message", "--subject", "s", "--body-json", "{}", "--standing", str(standing)]
                if value is not None:
                    args += ["--hb-epoch", value]
                result = self.run_cli("resident-runtime/ecosystem_control.py", *args)
                # A CLI "" is INVALID, as for every writer CLI; only absent is NOT_SUPPLIED.
                code = "HB_EPOCH_NOT_SUPPLIED" if value is None else "HB_EPOCH_INVALID"
                self.assert_six_field(result, code, 1)
                self.assertEqual(self.files_under("mesh"), [])

    def test_send_reads_no_clock(self):
        source = (ROOT / "resident-runtime/ecosystem_control.py").read_text()
        self.assertNotIn("datetime", source)
        self.assertNotIn("time.time", source)
        self.assertIn("epoch=int(raw)", source)

    def test_an_ecosystem_publication_at_a_supplied_epoch_is_not_clock_derived(self):
        standing = {"mode": "ESTABLISH_GENESIS", "node_ref": "b-p40-node", "predecessor": None}
        out = KERNEL.publish_ecosystem_message(
            origin_org="Org-A", origin_service="org-a.org-control", organizations=["Org-B"],
            standing=standing, message_class="ecosystem.communication", subject="s", body={},
            root=self.tmp / "mesh", epoch=4096)
        self.assertEqual(out["published_count"], 1)
        for publication in out["publications"]:
            reference = publication["frame"]["heartbeat_reference"]
            self.assertEqual((reference["epoch"], reference["derived_from_clock"]), (4096, False))


class InTrFilesAreUntouchedRowRuling(unittest.TestCase):
    """INTR_PATH_FILE_BYTE_IDENTICAL_TO_MAIN_MODULO_GRADED_EXCEPTION_FIXES
    (lead ruling 20:08Z, amended 20:16Z). Each InTr file may differ from
    main@79a0ea8 only by exception-fix commits that V-P11 graded ALLOW and the
    PR body lists with their sha and row. No such fix is carried here, so the
    list is explicitly empty and each file is pinned at main's sha256. The
    committed request reaches the self-closure's receipts only through
    emit.append and aggregate_repo_transition.append, this repository's own."""

    #: (commit sha, V-P11 row) of each graded exception fix to an InTr file.
    GRADED_EXCEPTION_FIXES: tuple[tuple[str, str], ...] = ()

    MAIN_SHA256 = {
        "resident-runtime/intr_destination_ingress.py":
            "35c212e029a65033cb5ac5b1acbd8379d8fd63721ab8ea66dede1a1648c1042c",
        "resident-runtime/intr_path_ingress.py":
            "2607a18a9c55beaab1dd5cdfa6fc22815e030547b869eecab1e9d4f35a301f4b",
        "resident-runtime/intr_path_transfer.py":
            "2909ec9480467ad8622726686b1808b87e3f794bc477566806cd86376db7592d",
        "resident-runtime/intr_path_tvc_read.py":
            "a3f14f99fe50b598d90173709efa186608acb50921a2bb564ef616fccf8e3afe",
    }

    def test_no_exception_fix_is_claimed(self):
        # A non-empty list would need each file re-pinned at its head sha.
        self.assertEqual(self.GRADED_EXCEPTION_FIXES, ())

    def test_each_intr_file_is_byte_identical_to_main(self):
        for relative, expected in self.MAIN_SHA256.items():
            with self.subTest(file=relative):
                self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), expected)


if __name__ == "__main__":
    unittest.main()
