#!/usr/bin/env python3
"""Fixed-clock probe of every route that reads a host clock (B-P36g).

The clock is pinned and each route is run. Every value it writes that came from
that clock must be marked as clock-derived (`derived_from_clock` true or a
`sampled_unix_ns` beside it), and every receipt writer must refuse an absent
epoch before writing, or stamp the epoch its caller supplied. No clock value may
appear under `derived_from_clock` false.
"""
from __future__ import annotations

import base64
import datetime as real_datetime
import importlib.util
import json
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path

TREE = Path(__file__).resolve().parents[1]
CONTRACT = "docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json"
STANDING = {"mode": "ESTABLISH_GENESIS", "node_ref": "clock-probe-node", "predecessor": None}
FIXED = real_datetime.datetime(2030, 1, 1, tzinfo=real_datetime.timezone.utc)
FIXED_NS = int(FIXED.timestamp() * 1_000_000_000)
FIXED_ISO = "2030-01-01T00:00:00"
CLOCK_CALLS = []
RAISING = []


class FixedDatetime(real_datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        CLOCK_CALLS.append(tz)
        if RAISING:
            raise AssertionError("a clock was read on a route that carries a supplied epoch")
        return FIXED if tz is not None else FIXED.replace(tzinfo=None)


def load(name: str, relative: str):
    """Load a module with the pinned clock in place of `datetime`."""
    fake = types.ModuleType("datetime")
    fake.__dict__.update(real_datetime.__dict__)
    fake.datetime = FixedDatetime
    previous = sys.modules["datetime"]
    sys.modules["datetime"] = fake
    try:
        spec = importlib.util.spec_from_file_location(name, TREE / relative)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.modules["datetime"] = previous
    return module


def provision(root: Path, organization: str, role: str, service: str) -> None:
    (root / "org-boundary/runtime").mkdir(parents=True, exist_ok=True)
    for name in ("node_standing.py", "manifest_selection.py"):
        shutil.copy2(TREE / "org-boundary/runtime" / name, root / "org-boundary/runtime" / name)
    (root / "docs").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TREE / CONTRACT, root / CONTRACT)
    (root / "org-kernel").mkdir(parents=True, exist_ok=True)
    shutil.copy2(TREE / "org-kernel/kernel.py", root / "org-kernel/kernel.py")
    (root / "org-boundary/registry").mkdir(parents=True, exist_ok=True)
    row = {"service_id": service, "repository": organization + "/.github", "boundary_role": role}
    (root / "org-boundary/registry/services.json").write_text(
        json.dumps({"organization": organization, "services": [row]}))


def unmarked_clock_values(value, path="$", parent=None):
    """Paths of pinned-clock values not marked as clock-derived."""
    found = []
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "packet_base64" and isinstance(item, str):
                found += unmarked_clock_values(json.loads(base64.b64decode(item)), path + ".packet", None)
            else:
                found += unmarked_clock_values(item, path + "." + key, value)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += unmarked_clock_values(item, path + "[" + str(index) + "]", parent)
    else:
        from_clock = (isinstance(value, str) and FIXED_ISO in value) or \
            (isinstance(value, int) and not isinstance(value, bool) and value in CLOCK_INTS)
        if from_clock:
            marked = isinstance(parent, dict) and (parent.get("derived_from_clock") is True
                                                   or "sampled_unix_ns" in parent)
            if not marked:
                found.append(path)
    return found


KERNEL = load("probe_kernel", "org-kernel/kernel.py")
CLOCK_EPOCH = KERNEL.HB_ANCHOR_EPOCH + (FIXED_NS - KERNEL.HB_ANCHOR_UNIX_NS) // KERNEL.HB_PERIOD_NS
CLOCK_INTS = {FIXED_NS, CLOCK_EPOCH}


def written(root: Path) -> list:
    return [json.loads(p.read_text()) for p in sorted(root.rglob("*.json"))
            if "registry" not in p.parts and p.name != Path(CONTRACT).name]


class ClockMarkerProbe(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        CLOCK_CALLS.clear()

    def assertMarked(self, *values):
        for value in values:
            self.assertEqual(unmarked_clock_values(value), [], value)

    def test_kernel_frame_routes_mark_every_clock_value(self):
        # Rows 1, 5, 6: publish_packet(None), publish_ecosystem_*, and the
        # response consume_and_respond publishes are frames only, clock-marked.
        a, b, mesh = self.tmp / "a", self.tmp / "b", self.tmp / "mesh"
        provision(a, "Org-A", "BOUNDARY_LOCAL_CONTROL", "org-a.org-control")
        provision(b, "Org-B", "BOUNDARY_LOCAL_CONTROL", "org-b.org-control")
        out = KERNEL.publish_ecosystem_message(
            origin_org="Org-A", origin_service="org-a.org-control", organizations=["Org-B"],
            standing=STANDING, message_class="ecosystem.communication", subject="probe",
            body={"probe": "clock"}, communication_id="clock-probe-001", root=mesh, repo_root=a)
        ref = out["publications"][0]["frame"]["heartbeat_reference"]
        self.assertIs(ref["derived_from_clock"], True)
        self.assertEqual(ref["sampled_unix_ns"], FIXED_NS)
        # The clock-flagged request is consumed but lends no epoch, and none was
        # supplied: the response is refused six-field, never clock-stamped.
        clock_reads = len(CLOCK_CALLS)
        served = KERNEL.consume_and_respond(b, mesh_root=mesh)
        self.assertEqual(served[0]["result"]["status"], "CONSUMED")
        self.assertIsNone(served[0]["response_publication"])
        self.assertEqual(served[0]["response_refusal"]["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        self.assertEqual(len(CLOCK_CALLS), clock_reads)
        self.assertGreater(len(CLOCK_CALLS), 0)
        self.assertMarked(out, served, KERNEL.resident_status(a), *written(self.tmp))

    def test_supplied_epoch_frame_reads_no_clock(self):
        packet = KERNEL.build_packet(
            origin_org="Org-A", origin_service="org-a.org-control", destination_org="Org-B",
            destination_service="org-b.org-control", payload={"probe": "supplied"}, standing=STANDING)
        published = KERNEL.publish_packet(packet, root=self.tmp / "mesh", epoch=4096)
        self.assertEqual(CLOCK_CALLS, [])
        ref = published["frame"]["heartbeat_reference"]
        self.assertEqual((ref["epoch"], ref["derived_from_clock"]), (4096, False))
        self.assertNotIn("sampled_unix_ns", ref)

    def test_ingest_frame_consumed_route_reads_no_clock_and_writes_nothing(self):
        # Row 4: ingest_frame returns CONSUMED, writes nothing, reads no clock.
        root = self.tmp / "d"
        provision(root, "Diag", "BOUNDARY_LOCAL_DIAGNOSTIC", "diag.boundary-diagnostic")
        packet = KERNEL.build_packet(
            origin_org="Peer", origin_service="peer.org-control", destination_org="Diag",
            destination_service="diag.boundary-diagnostic", payload={"probe": "ping"}, standing=STANDING)
        frame = KERNEL.carrier_frame(packet, epoch=4096)
        before = sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        result = KERNEL.ingest_frame(root, frame)
        self.assertEqual(result["status"], "CONSUMED")
        self.assertEqual(CLOCK_CALLS, [])
        self.assertEqual(sorted(p for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts), before)

    def test_git_carrier_emission_marks_its_clock_frame(self):
        # Row 5: an off-workflow frame-only helper with no epoch parameter.
        root = self.tmp / "g"
        provision(root, "Org-G", "BOUNDARY_LOCAL_CONTROL", "org-g.org-control")
        carrier = load("probe_git_carrier", "org-boundary/runtime/git_carrier.py")
        sys.modules["datetime"], previous = types.ModuleType("datetime"), sys.modules["datetime"]
        sys.modules["datetime"].__dict__.update(real_datetime.__dict__)
        sys.modules["datetime"].datetime = FixedDatetime
        try:
            emitted = carrier.emit(destination_org="Org-B", destination_service="org-b.org-control",
                                   payload={"probe": "git"}, standing=STANDING, root=root)
        finally:
            sys.modules["datetime"] = previous
        frame = json.loads(Path(emitted["persisted"]).read_text())
        self.assertIs(frame["heartbeat_reference"]["derived_from_clock"], True)
        self.assertMarked(frame)

    def test_intr_transport_marks_the_carrier_clock_reading(self):
        # Row 6: `observed_at` is a clock reading; the carrier says so.
        transport = load("probe_intr_transport", "org-boundary/runtime/intr_transport.py")
        ingress = transport.build_ingress({"org": "peer", "service": "peer.x"}, {"org": "Org-A", "service": "a.x"},
                                          {"probe": "ping"}, "HB-test", "test", standing=STANDING)
        result = {"receipts": [{"receipt_id": "r" + str(i)} for i in range(5)],
                  "reconstruction": {"terminal_receipt_id": "r4"}}
        egress = transport.build_egress(ingress, result)
        for envelope in (ingress, egress):
            self.assertTrue(envelope["carrier"]["observed_at"].startswith(FIXED_ISO))
            self.assertIs(envelope["carrier"]["derived_from_clock"], True)
        self.assertMarked(ingress, egress)

    def test_gateway_acknowledgement_marks_its_clock_reading(self):
        # Row 6 on the federation_cycle gateway branch.
        gateway = load("probe_gateway", "resident-runtime/federation_gateway_transport.py")
        sent = []
        gateway._json_request = lambda method, path, *, body=None, headers=None: sent.append(body) or {"state": "OK"}
        gateway.acknowledge_frame("Org-A", {"packet_id": "p", "frame_sha256": "sha256:" + "0" * 64}, "CONSUMED")
        self.assertIs(sent[0]["derived_from_clock"], True)
        self.assertMarked(sent[0])

    def test_federation_cycle_refuses_an_absent_epoch(self):
        # S2: with no --hb-epoch and no HB_EPOCH the cycle is refused six-field
        # NOT_SUPPLIED and writes nothing; no clock is read.
        root = self.tmp / "c"
        provision(root, "Org-C", "BOUNDARY_LOCAL_CONTROL", "org-c.org-control")
        cycle = load("probe_federation_cycle", "resident-runtime/federation_cycle.py")
        cycle.ROOT = root
        cycle.K = KERNEL
        import os
        previous = os.environ.pop("STEGVERSE_ORG_FEDERATION_GATEWAY_URL", None)
        previous_epoch = os.environ.pop("HB_EPOCH", None)
        os.environ["STEGVERSE_ORG_FEDERATION_ROOT"] = str(self.tmp / "mesh")
        import contextlib, io
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(cycle.main([]), 1)
        finally:
            os.environ.pop("STEGVERSE_ORG_FEDERATION_ROOT", None)
            if previous is not None:
                os.environ["STEGVERSE_ORG_FEDERATION_GATEWAY_URL"] = previous
            if previous_epoch is not None:
                os.environ["HB_EPOCH"] = previous_epoch
        refusal = json.loads(out.getvalue())
        self.assertEqual((refusal["disposition"], refusal["failure_code"]), ("FAIL_CLOSED", "HB_EPOCH_NOT_SUPPLIED"))
        self.assertFalse((root / "resident-runtime/federation/latest-cycle.json").exists())
        self.assertEqual(CLOCK_CALLS, [])

    def test_organization_runtime_receipts_take_the_supplied_epoch(self):
        # Row 3: activation and ingress receipts refuse an absent epoch before
        # writing, and stamp the supplied one rather than the clock.
        runtime = load("probe_organization_runtime", "runtime/organization_runtime.py")
        runtime.ACTIVATIONS, runtime.INGRESS, runtime.EGRESS = (self.tmp / "act", self.tmp / "in", self.tmp / "eg")
        for hb_epoch in (None, "+33", "31", True):
            with self.assertRaises(runtime.kernel.SuppliedEpochRefused) as refused:
                runtime.activate("probe-activation", "node", hb_epoch)
            self.assertEqual(refused.exception.disposition, "FAIL_CLOSED")
            for field in ("failure_code", "failed_predicate", "required_evidence_or_repair",
                          "retry_entrypoint", "owning_existing_goal", "next_attempt"):
                self.assertIn(field, refused.exception.refusal)
        self.assertEqual(refused.exception.refusal["retry_entrypoint"], runtime.EPOCH_RETRY_ENTRYPOINT)
        envelope = runtime.egress("probe-msg", "op", {"boundary": "X", "subsystem": "Y"}, b"payload")
        with self.assertRaises(runtime.kernel.SuppliedEpochRefused) as absent:
            runtime.ingress(envelope)
        self.assertEqual(absent.exception.refusal["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        self.assertFalse((self.tmp / "act").exists())
        self.assertFalse((self.tmp / "in").exists())

        activation = runtime.activate("probe-activation", "node", "4096")
        receipt = runtime.ingress(envelope, "4096")
        for record in (activation, receipt):
            self.assertEqual(record["hb_reference"]["epoch"], 4096)
            self.assertIs(record["hb_reference"]["derived_from_clock"], False)
            self.assertNotIn("requested_at", record)
            self.assertNotIn("validated_at", record)
        self.assertEqual(CLOCK_CALLS, [])
        self.assertMarked(activation, receipt, *written(self.tmp))


class SharedRuleAndSourceProvenance(unittest.TestCase):
    """B-P36h: an unmarked reference is refused, and a clock-provenance
    repository receipt is not consumed as an organization source."""

    def setUp(self):
        import os
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        self.ledger = self.tmp / "org-ledger"
        previous = os.environ.get("STEGVERSE_ORG_LEDGER_ROOT")
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(self.ledger)
        self.addCleanup(lambda: os.environ.__setitem__("STEGVERSE_ORG_LEDGER_ROOT", previous)
                        if previous is not None else os.environ.pop("STEGVERSE_ORG_LEDGER_ROOT", None))
        spec = importlib.util.spec_from_file_location("probe_aggregate", TREE / "resident-runtime/aggregate_repo_transition.py")
        self.org = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.org)

    def test_reference_without_derived_from_clock_is_refused(self):
        k = self.org.kernel
        self.assertEqual(k.supplied_epoch_failure(4096, {"epoch": 4096})[0], "HB_EPOCH_PROVENANCE_UNMARKED")
        refusal = k.writer_epoch_refusal(4096, retry_entrypoint="probe", reference={"epoch": 4096})
        self.assertEqual(refusal["failure_code"], "HB_EPOCH_PROVENANCE_UNMARKED")
        for field in ("disposition", "failed_predicate", "required_evidence_or_repair",
                      "retry_entrypoint", "owning_existing_goal", "next_attempt"):
            self.assertIn(field, refusal)
        self.assertEqual(k.supplied_epoch_failure(4096, {"derived_from_clock": True})[0], "HB_EPOCH_INVALID")
        self.assertIsNone(k.supplied_epoch_failure(4096, {"derived_from_clock": False}))
        # Marker vocabulary: CARRIED states false too; a bare sample is legacy CLOCK.
        self.assertEqual(k.supplied_epoch_failure(4096, {"provenance": "CARRIED:LEGACY_CLOCK_RECEIPT"})[0],
                         "HB_EPOCH_PROVENANCE_UNMARKED")
        self.assertEqual(k.supplied_epoch_failure(4096, {"sampled_unix_ns": 1})[0], "HB_EPOCH_INVALID")
        self.assertEqual(k.supplied_epoch_failure(4096, {"source": "ORGANIZATION_LEDGER_HEAD",
                                                         "head_receipt_sha": "sha256:" + "f" * 64})[0],
                         "HB_EPOCH_PROVENANCE_UNMARKED")
        # The rule passes a false+source reference; the writer or ingest verifies it.
        self.assertIsNone(k.supplied_epoch_failure(4096, {"derived_from_clock": False, "source": "X"}))
        self.assertEqual(k.supplied_epoch_failure(4096, {"derived_from_clock": False, "sampled_unix_ns": 1})[0],
                         "HB_EPOCH_INVALID")
        self.assertIsNone(k.supplied_epoch_failure(4096, k.hb_reference(epoch=4096)))
        self.assertIsNone(k.supplied_epoch_failure(4096))

    def test_the_shared_rule_is_the_pinned_final_text(self):
        import hashlib, inspect
        k = self.org.kernel
        digest = hashlib.sha256(inspect.getsource(k.supplied_epoch_failure).encode()).hexdigest()
        self.assertEqual(digest, k.SHARED_VALIDATOR_SHA256)
        self.assertEqual(k.SHARED_VALIDATOR_SHA256,
                         "ad8ff52936d5bcd9a2ad6caceb2d9a637a099518989b34bbb3370301c7a4cce2")

    def repo_receipt(self, transition_id, hb):
        body = {"schema": "stegverse.repo-transition-receipt/v1", "repository": self.org.C["organization"] + "/probe",
                "transition_id": transition_id, "transition_class": "PROBE",
                "predecessor_state_sha256": "sha256:" + "1" * 64, "successor_state_sha256": "sha256:" + "2" * 64,
                "evidence": {}, "authority_effect": "NONE", "hb_reference": hb, "previous_receipt_sha256": None}
        return {**body, "receipt_sha256": self.org.sha(body)}

    def append(self, receipt, **kw):
        return self.org.append(receipt, "REPO_STATE_PROPAGATION", "sha256:" + "1" * 64, "sha256:" + "2" * 64,
                               {}, "NONE", hb_epoch="4096", **kw)

    def files(self):
        return sorted(p for p in self.ledger.rglob("*") if p.is_file()) if self.ledger.exists() else []

    def test_clock_provenance_source_is_refused_and_writes_nothing(self):
        k = self.org.kernel
        clock = self.repo_receipt("clock-source", k.hb_reference(k.HB_ANCHOR_UNIX_NS + 1_000_000_000))
        for idempotent in (False, True):
            with self.assertRaises(k.SuppliedEpochRefused) as refused:
                self.append(clock, idempotent=idempotent)
            refusal = refused.exception.refusal
            self.assertEqual(refusal["failure_code"], "SOURCE_RECEIPT_IS_CLOCK_PROVENANCE")
            self.assertEqual(refusal["disposition"], "FAIL_CLOSED")
            self.assertIn("CARRIED:LEGACY_CLOCK_RECEIPT", refusal["required_evidence_or_repair"])
            self.assertIn("never mutated", refusal["required_evidence_or_repair"])
            for field in ("failed_predicate", "retry_entrypoint", "owning_existing_goal", "next_attempt"):
                self.assertIn(field, refusal)
            self.assertEqual(self.files(), [])
        supplied = self.repo_receipt("supplied-source", k.hb_reference(epoch=4096))
        self.assertEqual(self.append(supplied)["hb_reference"]["epoch"], 4096)

    def test_already_recorded_clock_source_still_replays(self):
        # A ledger written before the guard holds an organization receipt over a
        # clock-provenance source. Replay returns it; nothing is rewritten.
        k = self.org.kernel
        clock = self.repo_receipt("legacy-clock-source", k.hb_reference(k.HB_ANCHOR_UNIX_NS + 1_000_000_000))
        guard = self.org.source_clock_refusal
        self.org.source_clock_refusal = lambda receipt: None
        try:
            recorded = self.append(clock)
        finally:
            self.org.source_clock_refusal = guard
        before = {p: p.read_bytes() for p in self.files()}
        self.assertEqual(self.append(clock, idempotent=True), recorded)
        self.assertEqual({p: p.read_bytes() for p in self.files()}, before)


class InboundEpochIsSupplied(unittest.TestCase):
    """B-P36g (1)/(2): a response to a frame carrying a validated epoch is
    published at that epoch; no clock default is reached on the route."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp)
        CLOCK_CALLS.clear()
        RAISING.append(True)
        self.addCleanup(RAISING.clear)
        self.a, self.b, self.mesh = self.tmp / "a", self.tmp / "b", self.tmp / "mesh"
        provision(self.a, "Org-A", "BOUNDARY_LOCAL_CONTROL", "org-a.org-control")
        provision(self.b, "Org-B", "BOUNDARY_LOCAL_CONTROL", "org-b.org-control")
        built = KERNEL.build_ecosystem_packets(
            origin_org="Org-A", origin_service="org-a.org-control", organizations=["Org-B"],
            standing=STANDING, message_class="ecosystem.communication", subject="inbound",
            body={"probe": "inbound"}, communication_id="inbound-epoch-001")
        self.request = built["packets"][0]
        self.frame = KERNEL.carrier_frame(self.request, epoch=4096)

    def assertSupplied(self, frame):
        ref = frame["heartbeat_reference"]
        self.assertEqual((ref["epoch"], ref["derived_from_clock"]), (4096, False))
        self.assertNotIn("sampled_unix_ns", ref)

    def test_consume_and_respond_publishes_at_the_inbound_epoch(self):
        KERNEL.publish_frame(self.frame, root=self.mesh)
        served = KERNEL.consume_and_respond(self.b, mesh_root=self.mesh)
        self.assertEqual(served[0]["result"]["status"], "CONSUMED")
        self.assertSupplied(served[0]["response_publication"]["frame"])
        self.assertEqual(CLOCK_CALLS, [])

    def test_gateway_cycle_responds_at_the_inbound_epoch(self):
        gateway = load("probe_gateway_cycle", "resident-runtime/federation_gateway_transport.py")
        gateway.K = KERNEL
        submitted = []
        gateway.fetch_frame = lambda organization: {"state": "FRAME_AVAILABLE", "frame": self.frame}
        gateway.submit_frame = lambda frame: submitted.append(frame) or {}
        gateway.acknowledge_frame = lambda organization, frame, state: {"state": state}
        out = gateway.resident_gateway_cycle(self.b)
        self.assertEqual(out["responses_emitted"], 1)
        self.assertSupplied(submitted[0])
        self.assertEqual(CLOCK_CALLS, [])

    def test_a_refused_frame_is_quarantined_and_never_retried(self):
        # B-P36j: a mixed batch. The refused frame gets a terminal six-field
        # quarantine marker, the valid one is answered, and a second cycle
        # proceeds without retrying the refused frame. No clock is read.
        KERNEL.publish_frame(self.frame, root=self.mesh)
        unmarked_packet = dict(self.request, packet_id=self.request["packet_id"] + ":unmarked")
        frame = KERNEL.carrier_frame(unmarked_packet, epoch=4096)
        body = {k: v for k, v in frame.items() if k != "frame_sha256"}
        body["heartbeat_reference"] = {k: v for k, v in frame["heartbeat_reference"].items()
                                       if k != "derived_from_clock"}
        KERNEL.publish_frame({**body, "frame_sha256": KERNEL.sha(body)}, root=self.mesh)
        # A CLOCK-flagged frame, built before the clock is forbidden: consumed
        # (pending WU-B13), lending no epoch, its response refused NOT_SUPPLIED.
        RAISING.clear()
        clock_packet = dict(self.request, packet_id=self.request["packet_id"] + ":clock")
        clock_frame = KERNEL.carrier_frame(clock_packet)
        KERNEL.publish_frame(clock_frame, root=self.mesh)
        CLOCK_CALLS.clear()
        RAISING.append(True)
        first = KERNEL.consume_and_respond(self.b, mesh_root=self.mesh)
        statuses = sorted(item["result"]["status"] for item in first)
        self.assertEqual(statuses, ["CONSUMED", "CONSUMED", "REFUSED"])
        clock = next(item for item in first if item["result"].get("packet", {}).get("packet_id") == clock_packet["packet_id"])
        self.assertIsNone(clock["response_publication"])
        self.assertEqual(clock["response_refusal"]["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        supplied = next(item for item in first if item["result"].get("packet", {}).get("packet_id") == self.request["packet_id"])
        self.assertSupplied(supplied["response_publication"]["frame"])
        refused = next(item for item in first if item["result"]["status"] == "REFUSED")
        self.assertIsNone(refused["response_publication"])
        marker = json.loads(Path(refused["seen_marker"]).read_text())
        self.assertEqual((marker["status"], marker["disposition"], marker["failure_code"]),
                         ("REFUSED", "FAIL_CLOSED", "FRAME_REFUSED_QUARANTINED"))
        self.assertEqual(marker["refused_failure_code"], "HB_EPOCH_PROVENANCE_UNMARKED")
        for field in ("failed_predicate", "required_evidence_or_repair", "retry_entrypoint",
                      "owning_existing_goal", "next_attempt"):
            self.assertIn(field, marker)
        self.assertMarked(marker)
        self.assertEqual(list((self.b / "resident-runtime/control").glob("inbox/*")), [])
        second = KERNEL.consume_and_respond(self.b, mesh_root=self.mesh)
        self.assertNotIn(refused["path"], [item["path"] for item in second])
        self.assertEqual(CLOCK_CALLS, [])

    def assertMarked(self, *values):
        for value in values:
            self.assertEqual(unmarked_clock_values(value), [], value)

    def test_a_clock_flagged_frame_is_answered_at_a_supplied_epoch_or_refused(self):
        # S1 narrow: a clock-flagged request is consumed but lends no epoch.
        # Every route that would answer it refuses six-field NOT_SUPPLIED and
        # never reaches the clock default.
        RAISING.clear()
        monitor = KERNEL.build_ecosystem_packets(
            origin_org="Org-A", origin_service="org-a.org-control", organizations=["Org-B"],
            standing=STANDING, message_class="ecosystem.monitor.request", subject="monitor",
            body={}, communication_id="clock-monitor-001")["packets"][0]
        clock_monitor = KERNEL.carrier_frame(monitor)
        clock_request = KERNEL.carrier_frame(self.request)
        CLOCK_CALLS.clear()
        RAISING.append(True)
        status = KERNEL.ingest_frame(self.b, clock_monitor)["execution_result"]["application_result"]
        self.assertNotIn("monitor_status", status)
        self.assertEqual(status["monitor_status_refusal"]["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        gateway = load("probe_gateway_clock", "resident-runtime/federation_gateway_transport.py")
        gateway.K = KERNEL
        submitted = []
        gateway.fetch_frame = lambda organization: {"state": "FRAME_AVAILABLE", "frame": clock_request}
        gateway.submit_frame = lambda frame: submitted.append(frame) or {}
        gateway.acknowledge_frame = lambda organization, frame, state: {"state": state}
        out = gateway.resident_gateway_cycle(self.b)
        self.assertEqual((out["responses_emitted"], submitted), (0, []))
        self.assertEqual(out["response_refusal"]["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        self.assertEqual(gateway.resident_gateway_cycle(self.b, hb_epoch=4096)["responses_emitted"], 1)
        self.assertSupplied(submitted[0])
        self.assertEqual(CLOCK_CALLS, [])

    def test_git_carrier_refuses_a_clock_flagged_egress(self):
        RAISING.clear()
        root = self.tmp / "g"
        provision(root, "Diag", "BOUNDARY_LOCAL_DIAGNOSTIC", "diag.boundary-diagnostic")
        (root / "org-boundary/runtime").mkdir(parents=True, exist_ok=True)
        shutil.copy2(TREE / "org-boundary/runtime/intr_transport.py", root / "org-boundary/runtime/intr_transport.py")
        packet = KERNEL.build_packet(
            origin_org="Peer", origin_service="peer.org-control", destination_org="Diag",
            destination_service="diag.boundary-diagnostic", payload={"probe": "git"}, standing=STANDING)
        carrier = load("probe_git_carrier_consume", "org-boundary/runtime/git_carrier.py")
        out = carrier.consume(KERNEL.carrier_frame(packet), root=root)
        self.assertEqual(out["status"], "CONSUMED")
        self.assertIsNone(out["egress_persisted"])
        self.assertEqual(out["egress_refusal"]["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        supplied = carrier.consume(KERNEL.carrier_frame(dict(packet, packet_id=packet["packet_id"] + ":s"), epoch=4096),
                                   root=root)
        self.assertSupplied(json.loads(Path(supplied["egress_persisted"]).read_text()))

    def test_an_explicit_and_a_frame_epoch_must_agree(self):
        # B-P36l: an invalid explicit epoch is refused whatever the frame says;
        # two supplied epochs that disagree are refused HB_EPOCH_CONFLICT; one
        # alone is the supplied epoch. A refusal writes nothing, not even a
        # quarantine marker, so the frame is processed once a valid epoch comes.
        for hb_epoch in ("+33", "31", True):
            result = KERNEL.ingest_frame(self.b, self.frame, hb_epoch=hb_epoch)
            self.assertEqual(result["status"], "REFUSED")
            self.assertEqual(result["refusal"]["failure_code"], "HB_EPOCH_INVALID")
        conflict = KERNEL.ingest_frame(self.b, self.frame, hb_epoch=5000)
        self.assertEqual(conflict["refusal"]["failure_code"], "HB_EPOCH_CONFLICT")
        for field in ("disposition", "failed_predicate", "required_evidence_or_repair",
                      "retry_entrypoint", "owning_existing_goal", "next_attempt"):
            self.assertIn(field, conflict["refusal"])
        KERNEL.publish_frame(self.frame, root=self.mesh)
        before = sorted(p for p in self.b.rglob("*") if p.is_file() and "__pycache__" not in p.parts)
        served = KERNEL.consume_and_respond(self.b, mesh_root=self.mesh, hb_epoch="5000")
        self.assertEqual(served[0]["result"]["refusal"]["failure_code"], "HB_EPOCH_CONFLICT")
        self.assertIsNone(served[0]["seen_marker"])
        self.assertIsNone(served[0]["response_publication"])
        self.assertEqual(sorted(p for p in self.b.rglob("*") if p.is_file() and "__pycache__" not in p.parts), before)
        agreed = KERNEL.consume_and_respond(self.b, mesh_root=self.mesh, hb_epoch="4096")
        self.assertSupplied(agreed[0]["response_publication"]["frame"])
        self.assertEqual(CLOCK_CALLS, [])

    def test_an_explicit_epoch_alone_answers_a_clock_flagged_frame(self):
        RAISING.clear()
        monitor = KERNEL.build_ecosystem_packets(
            origin_org="Org-A", origin_service="org-a.org-control", organizations=["Org-B"],
            standing=STANDING, message_class="ecosystem.monitor.request", subject="monitor",
            body={}, communication_id="explicit-monitor-001")["packets"][0]
        clock_monitor = KERNEL.carrier_frame(monitor)
        CLOCK_CALLS.clear()
        RAISING.append(True)
        status = KERNEL.ingest_frame(self.b, clock_monitor, hb_epoch="4096")[
            "execution_result"]["application_result"]["monitor_status"]
        self.assertSupplied(status)
        self.assertEqual(CLOCK_CALLS, [])

    def test_monitor_request_status_takes_the_inbound_epoch(self):
        # R2: resident_status is stamped from the request frame's epoch.
        built = KERNEL.build_ecosystem_packets(
            origin_org="Org-A", origin_service="org-a.org-control", organizations=["Org-B"],
            standing=STANDING, message_class="ecosystem.monitor.request", subject="monitor",
            body={}, communication_id="monitor-epoch-001")
        frame = KERNEL.carrier_frame(built["packets"][0], epoch=4096)
        result = KERNEL.ingest_frame(self.b, frame)
        status = result["execution_result"]["application_result"]["monitor_status"]
        self.assertSupplied(status)
        self.assertEqual(CLOCK_CALLS, [])

    def test_federation_cycle_stamps_the_supplied_epoch(self):
        # R4: --hb-epoch / HB_EPOCH is checked by the shared rule and stamps the
        # cycle record and the responses it publishes, even to a clock request.
        import contextlib, io, os
        RAISING.clear()
        KERNEL.publish_frame(KERNEL.carrier_frame(self.request), root=self.mesh)
        cycle = load("probe_federation_cycle_epoch", "resident-runtime/federation_cycle.py")
        cycle.ROOT, cycle.K = self.b, KERNEL
        latest = self.b / "resident-runtime/federation/latest-cycle.json"
        saved = {key: os.environ.pop(key, None) for key in
                 ("STEGVERSE_ORG_FEDERATION_GATEWAY_URL", "HB_EPOCH", "STEGVERSE_ORG_FEDERATION_ROOT")}
        os.environ["STEGVERSE_ORG_FEDERATION_ROOT"] = str(self.mesh)

        def restore():
            for key, value in saved.items():
                os.environ.pop(key, None)
                if value is not None:
                    os.environ[key] = value
        self.addCleanup(restore)
        for argv, env in ((["--hb-epoch", "+33"], None), ([], "+33"), ([], "")):
            if env is not None:
                os.environ["HB_EPOCH"] = env
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(cycle.main(argv), 1)
            os.environ.pop("HB_EPOCH", None)
            refusal = json.loads(out.getvalue())
            self.assertEqual((refusal["disposition"], refusal["failure_code"]), ("FAIL_CLOSED", "HB_EPOCH_INVALID"))
            self.assertEqual(refusal["retry_entrypoint"], cycle.EPOCH_RETRY_ENTRYPOINT)
            self.assertFalse(latest.exists())
        CLOCK_CALLS.clear()
        RAISING.append(True)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cycle.main(["--hb-epoch", "4096"]), 0)
        self.assertSupplied(json.loads(latest.read_text()))
        responses = [json.loads(path.read_text()) for path in (self.mesh / "frames.d").glob("*.json")]
        responses = [frame for frame in responses if frame["destination_org"] == "Org-A"]
        self.assertEqual(len(responses), 1)
        self.assertSupplied(responses[0])
        os.environ["HB_EPOCH"] = "4096"
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(cycle.main([]), 0)
        self.assertSupplied(json.loads(latest.read_text()))
        self.assertEqual(CLOCK_CALLS, [])

    def test_a_clock_or_unmarked_inbound_frame_lends_no_epoch(self):
        RAISING.clear()
        self.assertEqual(KERNEL.frame_supplied_epoch(self.frame), 4096)
        clock = KERNEL.carrier_frame(self.request)
        self.assertIsNone(KERNEL.frame_supplied_epoch(clock))
        unmarked = dict(self.frame, heartbeat_reference={
            k: v for k, v in self.frame["heartbeat_reference"].items() if k != "derived_from_clock"})
        self.assertIsNone(KERNEL.frame_supplied_epoch(unmarked))
        # B-P36i: a CARRIED provenance naming an invented head is not a
        # supplied epoch; no route accepts it in place of one.
        carried = dict(self.frame, heartbeat_reference={
            **unmarked["heartbeat_reference"], "provenance": "CARRIED:ORGANIZATION_LEDGER_HEAD",
            "head_receipt_sha": "sha256:" + "e" * 64})
        self.assertIsNone(KERNEL.frame_supplied_epoch(carried))


class NoWriterAcceptsAProvenanceArgument(unittest.TestCase):
    """B-P36i: no receipt writer takes a caller-supplied provenance; each
    takes only hb_epoch, so an invented CARRIED source cannot be passed in."""

    def test_writers_refuse_a_provenance_argument(self):
        import inspect
        writers = [
            load("probe_emit", ".stegverse/transition-ledger/emit.py").append,
            load("probe_aggregate_writer", "resident-runtime/aggregate_repo_transition.py").append,
        ]
        for writer in writers:
            parameters = inspect.signature(writer).parameters
            self.assertIn("hb_epoch", parameters)
            for name in parameters:
                self.assertNotIn("provenance", name)
                self.assertNotIn("head_receipt", name)


if __name__ == "__main__":
    unittest.main()
