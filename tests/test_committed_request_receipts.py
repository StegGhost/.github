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
        env.update(STEGVERSE_REPO_LEDGER_ROOT=str(self.tmp / "repo-ledger"),
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

    def files_under(self, *names):
        return [p for name in names for p in (self.tmp / name).rglob("*") if p.is_file()]


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
    """V-P11 @722b416 new row: aggregate retained a rehashed off-ledger source
    receipt carrying a forged committed_request. The claim is verified against
    the request this run carries or, with none, the file at its path; anything
    else is COMMITTED_REQUEST_DIGEST_UNVERIFIED and nothing is copied."""

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

    def aggregate(self, source, **extra):
        return self.run_cli("resident-runtime/aggregate_repo_transition.py", "--repo-receipt", str(source),
                            "--predecessor-org-state-sha256", "sha256:" + "3" * 64,
                            "--successor-org-state-sha256", "sha256:" + "4" * 64, "--hb-epoch", "4096", **extra)

    def claim(self, path, digest):
        return {"path": path, "sha256": digest, "hb_epoch_source": "COMMITTED_REQUEST"}

    def assert_refused_nothing_copied(self, result):
        refusal = self.assert_six_field(result, "COMMITTED_REQUEST_DIGEST_UNVERIFIED", 2)
        self.assertIs(refusal["terminal"], True)
        self.assertEqual(self.files_under("org-ledger"), [])

    def test_a_forged_digest_against_this_runs_request_is_refused(self):
        forged = self.forged(self.claim(PAIR["STEGVERSE_COMMITTED_REQUEST_PATH"], "sha256:" + "f" * 64))
        self.assert_refused_nothing_copied(self.aggregate(forged, **PAIR))

    def test_a_forged_digest_with_no_run_request_is_checked_against_the_committed_file(self):
        readme = "sha256:" + hashlib.sha256((ROOT / "README.md").read_bytes()).hexdigest()
        self.assert_refused_nothing_copied(self.aggregate(self.forged(self.claim("README.md", "sha256:" + "f" * 64))))
        self.assert_refused_nothing_copied(self.aggregate(self.forged(self.claim("no/such/request.json", readme))))
        # Row 7: even the committed file's real digest is refused on a receipt
        # that was never on the repository ledger (rehashed, off-ledger).
        self.assert_refused_nothing_copied(self.aggregate(self.forged(self.claim("README.md", readme))))

    def test_an_on_ledger_receipt_tampered_after_the_append_is_refused(self):
        result = self.run_cli(".stegverse/transition-ledger/emit.py", "--transition-id", "t-on", "--transition-class",
                              "T", "--predecessor-state-sha256", "sha256:" + "1" * 64,
                              "--successor-state-sha256", "sha256:" + "2" * 64, "--hb-epoch", "4096", **PAIR)
        self.assertEqual(result.returncode, 0, result.stderr)
        on_ledger = json.loads(result.stdout)
        # Positive control: the receipt as appended, under the same run's pair.
        source = self.tmp / "on-ledger.json"
        source.write_text(json.dumps(on_ledger))
        accepted = self.aggregate(source, **PAIR)
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        # Its claim rewritten and the receipt rehashed: no longer the stored one.
        emit = load("b_p40_tamper_emit", ".stegverse/transition-ledger/emit.py")
        body = {k: v for k, v in on_ledger.items() if k != "receipt_sha256"}
        body["committed_request"] = {**body["committed_request"], "sha256": "sha256:" + "e" * 64}
        source.write_text(json.dumps({**body, "receipt_sha256": emit.sha(body)}))
        before = sorted(str(p) for p in self.files_under("org-ledger"))
        tampered = self.aggregate(source, **{**PAIR, "STEGVERSE_COMMITTED_REQUEST_SHA256": "sha256:" + "e" * 64})
        self.assert_six_field(tampered, "COMMITTED_REQUEST_DIGEST_UNVERIFIED", 2)
        self.assertEqual(sorted(str(p) for p in self.files_under("org-ledger")), before)

    def test_a_malformed_claim_is_refused(self):
        for claim in ("x", {"path": "README.md"}, {**self.claim("README.md", "sha256:" + "a" * 64), "extra": 1},
                      {**self.claim("README.md", "sha256:" + "a" * 64), "hb_epoch_source": "CLOCK"},
                      self.claim("../README.md", "sha256:" + "a" * 64)):
            with self.subTest(claim=claim):
                self.assert_refused_nothing_copied(self.aggregate(self.forged(claim)))


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
                    shutil.rmtree(self.tmp / "repo-ledger")

    def test_in_process_append_refuses_forged_evidence(self):
        saved = {k: os.environ.get(k) for k in ("STEGVERSE_REPO_LEDGER_ROOT", "STEGVERSE_ORG_LEDGER_ROOT")}
        os.environ.update(STEGVERSE_REPO_LEDGER_ROOT=str(self.tmp / "repo-ledger"),
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
