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


class FixedDatetime(real_datetime.datetime):
    @classmethod
    def now(cls, tz=None):
        CLOCK_CALLS.append(tz)
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
        served = KERNEL.consume_and_respond(b, mesh_root=mesh)
        self.assertIsNotNone(served[0]["response_publication"])
        self.assertIs(served[0]["response_publication"]["frame"]["heartbeat_reference"]["derived_from_clock"], True)
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

    def test_federation_cycle_marks_latest_cycle(self):
        # Row 2: takes no epoch; its frames and latest-cycle.json are clock-marked.
        root = self.tmp / "c"
        provision(root, "Org-C", "BOUNDARY_LOCAL_CONTROL", "org-c.org-control")
        cycle = load("probe_federation_cycle", "resident-runtime/federation_cycle.py")
        cycle.ROOT = root
        cycle.K = KERNEL
        import os
        previous = os.environ.pop("STEGVERSE_ORG_FEDERATION_GATEWAY_URL", None)
        os.environ["STEGVERSE_ORG_FEDERATION_ROOT"] = str(self.tmp / "mesh")
        try:
            cycle.main()
        finally:
            os.environ.pop("STEGVERSE_ORG_FEDERATION_ROOT", None)
            if previous is not None:
                os.environ["STEGVERSE_ORG_FEDERATION_GATEWAY_URL"] = previous
        latest = json.loads((root / "resident-runtime/federation/latest-cycle.json").read_text())
        self.assertIs(latest["heartbeat_reference"]["derived_from_clock"], True)
        self.assertEqual(latest["heartbeat_reference"]["sampled_unix_ns"], FIXED_NS)
        self.assertMarked(latest)

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


if __name__ == "__main__":
    unittest.main()
