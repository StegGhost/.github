"""``intr-destination`` is a universal ingress capability, not a purpose route.

StegGhost advertises it. A peer address is derived as
``organization_slug + "." + "intr-destination"``. A purpose-neutral diagnostic
can be emitted and closed. Peer installation is not proven at resolution.
Closure, when a fabricated far side answers, shows that a boundary ran this
packet. It does not show which organization that boundary belongs to. No
answer stays ``PENDING`` and writes nothing.

Authority and time are constraint variables. A disposition is transition
evidence only. Both ledger roots and the mesh are redirected. Nothing here is
an authentic production receipt or a live peer installation.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PROFILE_ID = "intr-destination"
PROFILE_NAME = "InTr:Destination"
OPERATION = "DIAGNOSTIC_CROSSING"
OPERATION_ID = "ORGANIZATION_INTR_DESTINATION_INGRESS"
ADDRESS = "stegghost." + PROFILE_ID
PAYLOAD_SCHEMA = "stegverse.org-intr-destination-diagnostic/v1"
THIS = "StegGhost"
PEER = "StegVerse-org"
CONSTRAINT = "CONSTRAINT_VARIABLE"
DISPOSITION_ROLE = "TRANSITION_EVIDENCE_ONLY"
CONSTRAINT_FIELDS = (
    "routing_authority_constraint",
    "admission_authority_constraint",
    "execution_authority_constraint",
    "time_constraint",
)
STANDING = {"mode": "ESTABLISH_GENESIS", "node_ref": "intr-destination-test", "predecessor": None}


def _module(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


kernel = _module("kernel", "org-kernel/kernel.py")
capability = _module("capability_ingress", "org-boundary/runtime/capability_ingress.py")
egress = _module("organization_egress_boundary",
                 "resident-runtime/organization_egress_boundary.py")
ingress = _module("intr_destination_ingress", "resident-runtime/intr_destination_ingress.py")
runtime_boundary = _module("runtime_boundary", "org-runtime/runtime_boundary.py")

REGISTRY = json.loads((ROOT / "org-boundary/registry/services.json").read_text(encoding="utf-8"))
BOUNDARY = json.loads((ROOT / "org-runtime/interlock-intr.json").read_text(encoding="utf-8"))
FEDERATION = json.loads((ROOT / "org-boundary/registry/federation.json").read_text(encoding="utf-8"))


def binding(profile_id, document=None):
    matches = [entry for entry in (document or BOUNDARY)["ingress"]["capability_endpoint_bindings"]
               if entry.get("profile_id") == profile_id]
    if len(matches) != 1:
        raise AssertionError(profile_id)
    return matches[0]


def row(service_id):
    return next(item for item in REGISTRY["services"] if item["service_id"] == service_id)


def diagnostic(communication_id="intr-destination-diagnostic-001", schema=PAYLOAD_SCHEMA):
    return {
        "message_class": "ecosystem.communication",
        "communication_id": communication_id,
        "subject": "purpose-neutral mesh diagnostic",
        "body": {"schema": schema, "probe": "diagnostic-crossing"},
    }


def assert_constraints(test, record):
    for name in CONSTRAINT_FIELDS:
        test.assertEqual(record[name], CONSTRAINT, name)
    test.assertEqual(record["disposition_role"], DISPOSITION_ROLE)


class DeclarationTests(unittest.TestCase):
    def test_the_overlay_advertises_the_capability_and_sets_no_constraint(self):
        declared = binding(PROFILE_ID)
        self.assertEqual(declared["profile_name"], PROFILE_NAME)
        self.assertEqual(declared["operation"], OPERATION)
        self.assertEqual(declared["payload_schema"], PAYLOAD_SCHEMA)
        self.assertEqual(declared["submission_reader"], capability.COMMUNICATION_READER)
        self.assertEqual(declared["authority_effect"], "NONE_BINDING_ONLY")
        self.assertIs(declared["environment_selected_ingress"], False)
        assert_constraints(self, declared)
        receiving = declared["receiving_operation"]
        self.assertEqual(receiving["operation_id"], OPERATION_ID)
        self.assertEqual(receiving["addressed_service"], ADDRESS)
        self.assertEqual(receiving["addressed_service_boundary_role"], capability.ROLE)
        self.assertIs(receiving["selects_processing_at_the_capability_address"], False)
        self.assertIs(receiving["host_required"], False)
        self.assertIs(receiving["environment_url_required"], False)
        assert_constraints(self, receiving)
        self.assertTrue((ROOT / receiving["operation"]).is_file())

    def test_the_registry_row_is_an_address_and_not_an_admission(self):
        served = row(ADDRESS)
        self.assertEqual(served["boundary_role"], "BOUNDARY_LOCAL_CAPABILITY_INGRESS")
        self.assertEqual(served["capability_profile_id"], PROFILE_ID)
        self.assertEqual(served["admission_authority_constraint"], CONSTRAINT)
        self.assertEqual(served["time_constraint"], CONSTRAINT)
        self.assertEqual(served["disposition_role"], DISPOSITION_ROLE)
        self.assertIs(served["selects_processing_at_this_address"], False)
        self.assertNotIn("endpoint_adapter", served)
        self.assertNotIn("admits_processing", served)
        self.assertIn("ecosystem.communication", served["accepts"])
        self.assertIn(PAYLOAD_SCHEMA, served["accepts"])

    def test_the_served_address_is_named_and_no_peer_address_is(self):
        proven = BOUNDARY["egress"]["peer_capability_resolution"]["proven_on_this_organization"]
        served = {entry["receiving_operation"]["addressed_service"]
                  for entry in BOUNDARY["ingress"]["capability_endpoint_bindings"]}
        self.assertEqual(served, {ADDRESS})
        self.assertEqual(proven, ADDRESS)
        self.assertNotIn("stegverse-org.intr-destination", (proven,))
        report = runtime_boundary.validate()
        self.assertIs(report["valid"], True, report["checks"])
        self.assertIs(report["checks"]["capability_addresses_resolve"], True)
        self.assertIs(report["checks"]["peer_capability_addresses_derive"], True)

    def test_naming_a_proper_subset_of_served_addresses_is_refused(self):
        document = json.loads(json.dumps(BOUNDARY))
        extra = json.loads(json.dumps(binding(PROFILE_ID)))
        extra["profile_id"] = "sdk-manifest-ingress"
        extra["receiving_operation"] = dict(extra["receiving_operation"])
        extra["receiving_operation"]["addressed_service"] = "stegghost.sdk-manifest-ingress"
        document["ingress"]["capability_endpoint_bindings"].append(extra)
        document["egress"]["peer_capability_resolution"]["proven_on_this_organization"] = ADDRESS
        self.assertIs(runtime_boundary.peer_capability_addresses_derive(document), False)

    def test_a_peer_address_in_the_proven_field_is_refused(self):
        document = json.loads(json.dumps(BOUNDARY))
        document["egress"]["peer_capability_resolution"]["proven_on_this_organization"] = [
            ADDRESS, "stegverse-org.intr-destination"]
        self.assertIs(runtime_boundary.peer_capability_addresses_derive(document), False)

    def test_a_single_served_address_may_still_be_named_as_a_string(self):
        self.assertIsInstance(
            BOUNDARY["egress"]["peer_capability_resolution"]["proven_on_this_organization"], str)
        self.assertIs(runtime_boundary.peer_capability_addresses_derive(BOUNDARY), True)

    def test_peer_services_are_not_written_into_the_federation_directory(self):
        for entry in FEDERATION["organizations"]:
            for key in ("org_control_service", "addressed_service"):
                self.assertNotIn(PROFILE_ID, str(entry.get(key) or ""))

    def test_no_governance_or_remediation_destination_binding_was_added(self):
        self.assertNotIn("capability_destination_bindings", BOUNDARY["egress"])
        emitting = BOUNDARY["egress"]["emitting_operation"]
        self.assertEqual(emitting["operation"], "resident-runtime/organization_egress_boundary.py")
        self.assertEqual(emitting["emission"], "resident-runtime/organization_egress_boundary.py::emit")
        self.assertEqual(emitting["closure"], "resident-runtime/organization_egress_boundary.py::close")
        self.assertNotIn("governance", json.dumps(BOUNDARY["egress"]["emitting_operation"]))
        self.assertNotIn("remediation", json.dumps(BOUNDARY["egress"]["emitting_operation"]))


class OverlayAuthorityTests(unittest.TestCase):
    def test_resolution_names_the_overlay_and_the_bound_operation(self):
        resolved = capability.resolve(ROOT, row(ADDRESS))
        self.assertEqual(resolved["resolution_source"], "ORGANIZATION_CAPABILITY_OVERLAY")
        self.assertIs(resolved["resolved_from_the_addressed_row_alone"], False)
        self.assertEqual(resolved["receiving_operation_id"], OPERATION_ID)
        self.assertEqual(resolved["capability_operation"], OPERATION)
        self.assertEqual(ingress.OPERATION_ID, OPERATION_ID)

    def test_a_row_the_overlay_does_not_name_resolves_nothing(self):
        with self.assertRaises(SystemExit) as refused:
            capability.resolve(ROOT, {"service_id": "stegghost.not-bound-anywhere"})
        self.assertIn("ADDRESS_SERVES_A_CAPABILITY_THE_OVERLAY_BINDS_HERE",
                      str(refused.exception))

    def test_a_module_that_is_not_the_bound_operation_is_refused(self):
        resolved = dict(capability.resolve(ROOT, row(ADDRESS)))
        resolved["receiving_operation_path"] = ROOT / "resident-runtime/organization_egress_boundary.py"
        with self.assertRaises(SystemExit) as refused:
            capability.load_operation(resolved)
        self.assertIn("MODULE_IDENTIFIES_ITSELF_AS_THE_BOUND_OPERATION",
                      str(refused.exception))

    def test_an_operation_outside_this_organization_is_refused(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, True)
        (root / "org-runtime").mkdir(parents=True)
        document = json.loads(json.dumps(BOUNDARY))
        receiving = binding(PROFILE_ID, document)["receiving_operation"]
        receiving["operation"] = "../outside.py"
        (root / "org-runtime/interlock-intr.json").write_text(json.dumps(document), encoding="utf-8")
        with self.assertRaises(SystemExit) as refused:
            capability.resolve(root, row(ADDRESS))
        self.assertIn("RECEIVING_OPERATION_IS_OWNED_INSIDE_THIS_ORGANIZATION",
                      str(refused.exception))

    def test_the_readers_do_not_cross(self):
        manifest_binding = {"operation": "SUBMIT_MANIFEST"}
        with self.assertRaises(SystemExit) as manifest_refused:
            capability.submission_for(manifest_binding, diagnostic())
        self.assertIn("SUBMISSION_CARRIES_A_MANIFEST", str(manifest_refused.exception))
        with self.assertRaises(SystemExit) as diagnostic_refused:
            capability.submission_for(binding(PROFILE_ID), {"manifest": {"probe": True}})
        self.assertIn("SUBMISSION_DECLARES_A_RESPONDED_REQUEST_CLASS",
                      str(diagnostic_refused.exception))

    def test_a_diagnostic_body_under_another_schema_is_refused(self):
        with self.assertRaises(SystemExit) as refused:
            capability.submission_for(
                binding(PROFILE_ID), diagnostic(schema="stegverse.org-governance-decision/v1"))
        self.assertIn("SUBMISSION_BODY_DECLARES_THE_BOUND_PAYLOAD_SCHEMA", str(refused.exception))


class RedirectedLedgers(unittest.TestCase):
    LEDGER_ROOTS = ("STEGVERSE_REPO_LEDGER_ROOT", "STEGVERSE_ORG_LEDGER_ROOT")

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.addCleanup(self._work.cleanup)
        previous = {name: os.environ.get(name) for name in self.LEDGER_ROOTS}
        for name in self.LEDGER_ROOTS:
            os.environ[name] = str(Path(self._work.name) / name.lower())
        self.mesh = Path(self._work.name) / "mesh"

        def restore():
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.addCleanup(restore)

    def receipts(self, variable, schema, transition_class=None):
        found = []
        root = Path(os.environ[variable])
        if not root.exists():
            return found
        for path in root.rglob("*.json"):
            record = json.loads(path.read_text(encoding="utf-8"))
            if record.get("schema") != schema:
                continue
            if transition_class is not None and record.get("transition_class") != transition_class:
                continue
            found.append(record)
        return found


class OperationReceiptTests(RedirectedLedgers):
    def test_a_diagnostic_is_acknowledged_at_both_ledger_levels(self):
        result = ingress.receive(diagnostic(), registry=REGISTRY, packet_id="direct-diagnostic",
                                 hb_epoch=32)
        self.assertEqual(result["disposition"], "ALLOW", result.get("detail"))
        self.assertIs(result["received"], True)
        self.assertIs(result["communication_acknowledged"], True)
        self.assertIs(result["repository_receipt_observed"], True)
        self.assertIs(result["organization_receipt_observed"], True)
        self.assertIs(result["organization_receipt_preserves_repository_receipt"], True)
        self.assertEqual(result["authority_effect"], "NONE_DIAGNOSTIC_ACK_ONLY")
        assert_constraints(self, result)
        for flag in ("selects_processing", "purpose_specific_route", "standing_rechecked_here"):
            self.assertIs(result[flag], False, flag)
        repository, = self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                    "stegverse.repo-transition-receipt/v1", OPERATION_ID)
        self.assertEqual(repository["evidence"]["profile_id"], PROFILE_ID)
        self.assertEqual(repository["evidence"]["receiving_operation"], OPERATION_ID)
        assert_constraints(self, repository["evidence"])
        organization, = self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                      "stegverse.organization-transition-receipt/v1")
        self.assertEqual(organization["repo_receipt_sha256"], repository["receipt_sha256"])

    def test_a_replay_of_the_same_diagnostic_does_not_mint_a_second_pair(self):
        first = ingress.receive(diagnostic(), registry=REGISTRY, packet_id="replayed-diagnostic",
                                hb_epoch=32)
        second = ingress.receive(diagnostic(), registry=REGISTRY, packet_id="replayed-diagnostic",
                                 hb_epoch=32)
        self.assertIs(second["transition_replayed"], True)
        self.assertEqual(first["repository_receipt_sha256"], second["repository_receipt_sha256"])
        self.assertEqual(len(self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                           "stegverse.repo-transition-receipt/v1", OPERATION_ID)), 1)

    def test_a_payload_that_is_not_the_diagnostic_is_refused_and_recorded(self):
        result = ingress.receive(
            {"message_class": "ecosystem.work.request", "communication_id": "not-a-diagnostic",
             "body": {"schema": "stegverse.org-governance-decision-request/v1"}},
            registry=REGISTRY, packet_id="refused-diagnostic", hb_epoch=32)
        self.assertEqual(result["disposition"], "DENY")
        self.assertIs(result["communication_acknowledged"], False)
        self.assertIs(result["refusal_recorded"], True)
        self.assertEqual(result["failed_predicate"], "SUBMISSION_DECLARES_A_RESPONDED_REQUEST_CLASS")
        self.assertEqual(result["authority_effect"], "NONE_REFUSAL_ONLY")
        assert_constraints(self, result)
        self.assertEqual(len(self.receipts(
            "STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1",
            ingress.REFUSED_CLASS)), 1)
        self.assertEqual(self.receipts(
            "STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1", OPERATION_ID), [])


class RepositoryReceiptNeverReadsAClockTests(RedirectedLedgers):
    """B-P29: a repository receipt carried `derived_from_clock: true` while the
    organization receipt for the same transition carried `false`.

    The repository writer took the host clock when no epoch was supplied and the
    organization writer was handed that epoch as if supplied. The repository
    writer now takes the supplied epoch or refuses, and no clock is read.
    """

    def setUp(self):
        super().setUp()
        self.emit = _module("repo_transition_emit_b_p29", ".stegverse/transition-ledger/emit.py")

        def clock(*_args, **_kwargs):
            raise AssertionError("a clock was read")

        class NoClock:
            @staticmethod
            def now(*_args, **_kwargs):
                clock()

        for module in (self.emit.kernel, ingress.repository_ledger.kernel,
                       ingress.organization_ledger.kernel):
            previous = module.datetime
            module.datetime = NoClock
            self.addCleanup(setattr, module, "datetime", previous)

    def all_receipts(self):
        return (self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")
                + self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                "stegverse.organization-transition-receipt/v1"))

    def test_an_absent_epoch_is_refused_with_the_six_fields_and_writes_nothing(self):
        with self.assertRaises(self.emit.RepoLedgerEpochRefused) as refused:
            self.emit.append("t:absent", "T", "sha256:" + "0" * 64, "sha256:" + "1" * 64)
        refusal = refused.exception.refusal
        self.assertEqual(refusal["disposition"], "FAIL_CLOSED")
        self.assertEqual(refusal["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        for field in ("failure_code", "failed_predicate", "required_evidence_or_repair",
                      "retry_entrypoint", "owning_existing_goal", "next_attempt"):
            self.assertTrue(refusal[field], field)
        self.assertIs(refusal["derived_from_clock"], False)
        self.assertEqual(self.all_receipts(), [])

    def test_an_invalid_epoch_is_refused_and_writes_nothing(self):
        for epoch in (31, 0, -1, True, 33.0, "33.0", "+33", " 33", "3_3", "x"):
            with self.subTest(epoch=epoch):
                with self.assertRaises(self.emit.RepoLedgerEpochRefused) as refused:
                    self.emit.append("t:invalid", "T", "sha256:" + "0" * 64,
                                     "sha256:" + "1" * 64, hb_epoch=epoch)
                self.assertEqual(refused.exception.refusal["failure_code"], "HB_EPOCH_INVALID")
        self.assertEqual(self.all_receipts(), [])

    def test_the_ingress_refuses_an_absent_or_invalid_epoch_before_opening_a_store(self):
        cases = ((None, "HB_EPOCH_NOT_SUPPLIED"), ("33.0", "HB_EPOCH_INVALID"),
                 (True, "HB_EPOCH_INVALID"), (31, "HB_EPOCH_INVALID"),
                 ("+33", "HB_EPOCH_INVALID"))
        for epoch, code in cases:
            with self.subTest(epoch=epoch):
                result = ingress.receive(diagnostic(), registry=REGISTRY,
                                         packet_id="refused-epoch", hb_epoch=epoch)
                self.assertEqual(result["failure_code"], code)
                self.assertEqual(result["failed_predicate"],
                                 "SUBMISSION_CARRIES_THE_SUPPLIED_HB_EPOCH")
                for variable in self.LEDGER_ROOTS:
                    self.assertFalse(Path(os.environ[variable]).exists(), variable)

    def test_a_supplied_epoch_is_carried_and_derived_from_clock_is_false(self):
        receipt = self.emit.append("t:supplied", "T", "sha256:" + "0" * 64,
                                   "sha256:" + "1" * 64, hb_epoch=469436465)
        self.assertEqual(receipt["hb_reference"]["epoch"], 469436465)
        self.assertIs(receipt["hb_reference"]["derived_from_clock"], False)
        self.assertNotIn("sampled_unix_ns", receipt["hb_reference"])

    def test_derived_from_clock_is_never_true_at_either_ledger_level(self):
        ingress.receive(diagnostic(), registry=REGISTRY, packet_id="clock-free", hb_epoch=32)
        ingress.receive(diagnostic(), registry=REGISTRY, packet_id="clock-free", hb_epoch=40)
        ingress.receive(diagnostic(), registry=REGISTRY, packet_id="no-epoch")
        ingress.self_close("clock-free-closure", registry=REGISTRY, hb_epoch=33)
        ingress.self_close("no-epoch-closure", registry=REGISTRY, packet_id="no-epoch-closure")
        found = self.all_receipts()
        self.assertTrue(found)
        for record in found:
            reference = record["hb_reference"]
            self.assertIs(reference["derived_from_clock"], False, record["receipt_sha256"])
            self.assertNotIn("sampled_unix_ns", reference)
        repository = {record["receipt_sha256"]: record for record in self.receipts(
            "STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")}
        for record in self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                    "stegverse.organization-transition-receipt/v1"):
            source = repository[record["repo_receipt_sha256"]]
            self.assertEqual(record["hb_reference"], source["hb_reference"])

    def test_the_cli_refuses_an_absent_epoch_with_the_six_fields(self):
        import subprocess
        import sys
        run = subprocess.run(
            [sys.executable, str(ROOT / ".stegverse/transition-ledger/emit.py"),
             "--transition-id", "t:cli", "--transition-class", "T",
             "--predecessor-state-sha256", "sha256:" + "0" * 64,
             "--successor-state-sha256", "sha256:" + "1" * 64],
            capture_output=True, text=True, env=dict(os.environ))
        self.assertEqual(run.returncode, 1, run.stderr)
        refusal = json.loads(run.stdout)
        self.assertEqual(refusal["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        self.assertEqual(refusal["retry_entrypoint"], self.emit.EPOCH_RETRY_ENTRYPOINT)
        self.assertEqual(self.all_receipts(), [])


REFUSED_EPOCHS = ((None, "HB_EPOCH_NOT_SUPPLIED"), ("33.0", "HB_EPOCH_INVALID"),
                  (True, "HB_EPOCH_INVALID"), (31, "HB_EPOCH_INVALID"),
                  ("+33", "HB_EPOCH_INVALID"))
SIX_FIELDS = ("failure_code", "failed_predicate", "required_evidence_or_repair",
              "retry_entrypoint", "owning_existing_goal", "next_attempt")


class RefusalPrecedesAnyWriteTests(RedirectedLedgers):
    """B-P36b: the organization ledger and the egress refuse an epoch first.

    `aggregate_repo_transition.append` fell back to the clock when no epoch was
    supplied, and `egress.emit` published its mesh frame before the epoch was
    refused, with a clock-derived frame epoch. Both now refuse an absent or
    invalid epoch before a store is opened or a frame is published.
    """

    def setUp(self):
        super().setUp()
        self.aggregate = ingress.organization_ledger
        self.repository = _module("repo_transition_emit_b_p36b",
                                  ".stegverse/transition-ledger/emit.py")

        class NoClock:
            @staticmethod
            def now(*_args, **_kwargs):
                raise AssertionError("a clock was read")

        for module in (kernel, egress.kernel, egress.organization_ledger.kernel,
                       self.aggregate.kernel, self.repository.kernel):
            previous = module.datetime
            module.datetime = NoClock
            self.addCleanup(setattr, module, "datetime", previous)

    def source_receipt(self):
        return self.repository.append("t:b-p36b", "T", "sha256:" + "0" * 64,
                                      "sha256:" + "1" * 64, hb_epoch=32)

    def org_ledger_files(self):
        root = Path(os.environ["STEGVERSE_ORG_LEDGER_ROOT"])
        return sorted(str(path) for path in root.rglob("*")) if root.exists() else None

    def test_the_organization_ledger_refuses_before_opening_its_store(self):
        source = self.source_receipt()

        def opened(*_args, **_kwargs):
            raise AssertionError("the store was opened")

        for epoch, code in REFUSED_EPOCHS:
            with self.subTest(epoch=epoch):
                previous = self.aggregate.open_store
                self.aggregate.open_store = opened
                try:
                    with self.assertRaises(self.aggregate.OrgLedgerEpochRefused) as refused:
                        self.aggregate.append(source, "REPO_STATE_PROPAGATION",
                                              "sha256:" + "0" * 64, "sha256:" + "1" * 64,
                                              {}, "NONE", hb_epoch=epoch)
                finally:
                    self.aggregate.open_store = previous
                refusal = refused.exception.refusal
                self.assertEqual(refusal["disposition"], "FAIL_CLOSED")
                self.assertEqual(refusal["failure_code"], code)
                self.assertEqual(refusal["failed_predicate"],
                                 "SUBMISSION_CARRIES_THE_SUPPLIED_HB_EPOCH")
                self.assertEqual(refusal["retry_entrypoint"], self.aggregate.EPOCH_RETRY_ENTRYPOINT)
                for field in SIX_FIELDS:
                    self.assertTrue(refusal[field], field)
                self.assertIsNone(self.org_ledger_files())

    def test_a_refusal_leaves_an_existing_organization_ledger_untouched(self):
        source = self.source_receipt()
        self.aggregate.append(source, "REPO_STATE_PROPAGATION", "sha256:" + "0" * 64,
                              "sha256:" + "1" * 64, {}, "NONE", hb_epoch=32)
        before = {path: Path(path).read_bytes() for path in self.org_ledger_files()
                  if Path(path).is_file()}
        for epoch, _code in REFUSED_EPOCHS:
            with self.subTest(epoch=epoch):
                with self.assertRaises(self.aggregate.OrgLedgerEpochRefused):
                    self.aggregate.append(source, "REPO_STATE_PROPAGATION",
                                          "sha256:" + "0" * 64, "sha256:" + "1" * 64,
                                          {}, "NONE", hb_epoch=epoch)
                after = {path: Path(path).read_bytes() for path in self.org_ledger_files()
                         if Path(path).is_file()}
                self.assertEqual(after, before)

    def test_the_organization_ledger_cli_refuses_an_absent_epoch(self):
        import subprocess
        import sys
        source = Path(self._work.name) / "source.json"
        source.write_text(json.dumps(self.source_receipt()), encoding="utf-8")
        for extra, code in (([], "HB_EPOCH_NOT_SUPPLIED"), (["--hb-epoch", "+33"], "HB_EPOCH_INVALID")):
            with self.subTest(extra=extra):
                run = subprocess.run(
                    [sys.executable, str(ROOT / "resident-runtime/aggregate_repo_transition.py"),
                     "--repo-receipt", str(source),
                     "--predecessor-org-state-sha256", "sha256:" + "0" * 64,
                     "--successor-org-state-sha256", "sha256:" + "1" * 64, *extra],
                    capture_output=True, text=True, env=dict(os.environ))
                self.assertEqual(run.returncode, 1, run.stderr)
                self.assertEqual(json.loads(run.stdout)["failure_code"], code)
                self.assertIsNone(self.org_ledger_files())

    def test_the_egress_refuses_before_publishing_a_frame(self):
        published = []
        previous = egress.kernel.publish_packet

        def publish(*args, **kwargs):
            published.append((args, kwargs))
            return previous(*args, **kwargs)

        egress.kernel.publish_packet = publish
        self.addCleanup(setattr, egress.kernel, "publish_packet", previous)
        for epoch, code in REFUSED_EPOCHS:
            with self.subTest(epoch=epoch):
                result = egress.emit(PEER, diagnostic("refused-epoch-egress"), standing=STANDING,
                                     capability=PROFILE_ID, mesh_root=self.mesh, hb_epoch=epoch)
                self.assertEqual(result["disposition"], "FAIL_CLOSED")
                self.assertEqual(result["failure_code"], code)
                self.assertEqual(result["failed_predicate"],
                                 "SUBMISSION_CARRIES_THE_SUPPLIED_HB_EPOCH")
                for field in SIX_FIELDS:
                    self.assertTrue(result[field], field)
                self.assertIs(result["emitted"], False)
                self.assertIs(result["refusal_recorded"], False)
                self.assertEqual(published, [])
                self.assertEqual(list(self.mesh.glob("frames.d/*.json")), [])
                for variable in self.LEDGER_ROOTS:
                    self.assertFalse(Path(os.environ[variable]).exists(), variable)

    def test_the_egress_frame_carries_the_supplied_epoch(self):
        result = egress.emit(PEER, diagnostic("supplied-epoch-egress"), standing=STANDING,
                             capability=PROFILE_ID, mesh_root=self.mesh, hb_epoch="469436465")
        self.assertEqual(result["disposition"], "ALLOW", result.get("detail"))
        frame, = self.mesh.glob("frames.d/*.json")
        reference = json.loads(frame.read_text(encoding="utf-8"))["heartbeat_reference"]
        self.assertEqual(reference["epoch"], 469436465)
        self.assertIs(reference["derived_from_clock"], False)
        self.assertNotIn("sampled_unix_ns", reference)


class AddressedAndClosedTests(RedirectedLedgers):
    def publish(self, payload, service, packet_id, origin=PEER):
        packet = kernel.build_packet(
            origin_org=origin,
            origin_service=kernel.organization_slug(origin) + "." + PROFILE_ID,
            destination_org=THIS, destination_service=service,
            payload=payload, standing=STANDING,
            transition_reference="intr:transition:" + packet_id,
            authority_effect="NONE", packet_id=packet_id)
        kernel.publish_packet(packet, root=self.mesh)
        return packet

    def consume(self):
        return kernel.consume_addressed_frames(ROOT, mesh_root=self.mesh)

    def frames_to(self, organization):
        directory = self.mesh / "frames.d"
        if not directory.is_dir():
            return []
        frames = []
        for path in directory.glob("*.json"):
            frame = json.loads(path.read_text(encoding="utf-8"))
            if frame.get("destination_org") == organization:
                frames.append(frame)
        return frames

    def test_a_peer_frame_at_the_address_without_a_supplied_epoch_fails_closed(self):
        # The capability ingress hands the operation no hb_epoch, and the
        # carrier's reference is derived from a clock. The repository receipt
        # used to be stamped from that clock; it is now refused, and neither
        # ledger level is written.
        self.publish(diagnostic("addressed-diagnostic"), ADDRESS, "addressed-diagnostic")
        results = self.consume()
        self.assertEqual(len(results), 1)
        execution = results[0]["result"]["execution_result"]
        self.assertEqual(results[0]["result"]["status"], "CONSUMED")
        self.assertEqual(results[0]["result"]["packet"]["origin"]["org"], PEER)
        self.assertEqual(execution["service_id"], ADDRESS)
        self.assertEqual(execution["processing_selection"], "BOUNDARY_LOCAL_NO_PROCESSOR_SELECTED")
        application = execution["application_result"]
        self.assertIs(application["capability_received"], True)
        self.assertEqual(application["capability_profile_id"], PROFILE_ID)
        self.assertEqual(application["receiving_operation_id"], OPERATION_ID)
        self.assertIs(application["declared_capability_processed_at_this_address"], False)
        operation = application["receiving_operation_result"]
        self.assertEqual(operation["disposition"], "FAIL_CLOSED")
        self.assertEqual(operation["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        self.assertEqual(operation["failed_predicate"], "SUBMISSION_CARRIES_THE_SUPPLIED_HB_EPOCH")
        for field in ("required_evidence_or_repair", "retry_entrypoint",
                      "owning_existing_goal", "next_attempt"):
            self.assertTrue(operation[field], field)
        self.assertIs(operation["communication_acknowledged"], False)
        self.assertIs(operation["repository_receipt_observed"], False)
        self.assertIs(operation["organization_receipt_observed"], False)
        self.assertEqual(self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                       "stegverse.repo-transition-receipt/v1"), [])
        self.assertEqual(self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                       "stegverse.organization-transition-receipt/v1"), [])

    def test_a_manifest_addressed_to_this_capability_is_not_a_diagnostic(self):
        self.publish({"manifest": {"probe": True}}, ADDRESS, "not-a-diagnostic")
        with self.assertRaises(ValueError) as refused:
            self.consume()
        self.assertIn("SUBMISSION_DECLARES_A_RESPONDED_REQUEST_CLASS", str(refused.exception))
        self.assertEqual(self.receipts(
            "STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1", OPERATION_ID), [])

    def test_outbound_resolution_derives_the_peer_address_and_does_not_prove_it_serves(self):
        resolved = egress.resolve_destination(PEER, capability=PROFILE_ID)
        self.assertEqual(resolved["destination_service"],
                         kernel.organization_slug(PEER) + "." + PROFILE_ID)
        self.assertEqual(resolved["destination_service"], "stegverse-org.intr-destination")
        self.assertNotEqual(resolved["destination_service"],
                            resolved["destination_org_control_service"])
        self.assertIs(resolved["peer_serves_this_capability_is_proven_here"], False)
        self.assertIs(resolved["destination_capability_declared_by_the_peer_directory"], False)
        self.assertEqual(egress.peer_capability_service(THIS, PROFILE_ID), ADDRESS)

    def test_an_undeclared_capability_is_still_refused(self):
        with self.assertRaises(egress.EgressRefused) as refused:
            egress.resolve_destination(PEER, capability="not-a-declared-capability")
        self.assertEqual(refused.exception.failed_predicate,
                         "CAPABILITY_IS_DECLARED_IN_THIS_ORGANIZATIONS_OVERLAY")

    def test_an_undeclared_peer_is_still_refused(self):
        with self.assertRaises(egress.EgressRefused) as refused:
            egress.resolve_destination("Not-A-Declared-Peer", capability=PROFILE_ID)
        self.assertEqual(refused.exception.failed_predicate,
                         "DESTINATION_IS_A_DECLARED_PEER_OF_THIS_ORGANIZATION")

    def answer(self, packet):
        """Answer as a boundary does: the kernel's own receipt chain and control response.

        The chain is fabricated in this temporary mesh. It is not an authentic
        receipt and not a live peer installation.
        """
        chain, previous = [], None
        for kind in egress.FAR_SIDE_RECEIPT_KINDS:
            receipt = kernel.receipt(kind, packet["packet_id"], packet["destination"]["service"],
                                     previous, {"payload_hash": kernel.sha(packet["payload"])})
            chain.append(receipt["receipt_id"])
            previous = receipt["receipt_id"]
        response = kernel.build_control_response(
            packet, {"application_result": {
                "schema": ingress.RESULT_SCHEMA, "disposition": "ALLOW",
                "authority_effect": "NONE_DIAGNOSTIC_ACK_ONLY"},
                "reconstruction": {"terminal_receipt_id": chain[-1]}})
        kernel.publish_packet(response, root=self.mesh)
        return chain[-1]

    def test_a_diagnostic_crossing_closes_only_when_the_far_side_answers(self):
        emitted = egress.emit(PEER, diagnostic("closable-diagnostic"), standing=STANDING,
                              capability=PROFILE_ID, mesh_root=self.mesh, hb_epoch=32)
        self.assertEqual(emitted["disposition"], "ALLOW", emitted.get("detail"))
        self.assertIs(emitted["emitted"], True)
        self.assertEqual(emitted["destination_service"], "stegverse-org.intr-destination")
        self.assertIs(emitted["peer_serves_this_capability_is_proven_here"], False)
        self.assertEqual(emitted["emission_record"]["far_side_service_id"],
                         emitted["destination_service"])
        pending = egress.close(PEER, emitted["packet_id"], "closable-diagnostic",
                               mesh_root=self.mesh, hb_epoch=33)
        self.assertEqual(pending["disposition"], "FAIL_CLOSED")
        self.assertEqual(pending["failure_code"],
                         "DURABLE_QUEUE_OR_EVENT_EPHEMERAL_MATERIALIZATION")
        self.assertIs(pending["closed"], False)
        self.assertIs(pending["closure_recorded"], False)
        self.assertIs(pending["absence_is_not_a_transition"], True)
        self.assertEqual(self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                       "stegverse.repo-transition-receipt/v1",
                                       egress.CLOSED_CLASS), [])

        frame, = self.frames_to(PEER)
        packet = kernel.recover_packet(frame)
        self.assertEqual(packet["destination"]["service"], "stegverse-org.intr-destination")
        self.assertEqual(packet["payload"]["message_class"], "ecosystem.communication")
        self.assertEqual(packet["payload"]["communication_id"], "closable-diagnostic")
        terminal = self.answer(packet)
        closed = egress.close(PEER, emitted["packet_id"], "closable-diagnostic",
                              mesh_root=self.mesh, hb_epoch=34)
        self.assertEqual(closed["disposition"], "ALLOW", closed.get("closure_findings"))
        self.assertIs(closed["closed"], True)
        self.assertEqual(closed["far_side_terminal_receipt"], terminal)
        self.assertEqual(closed["communication_id"], "closable-diagnostic")
        self.assertEqual(closed["closure_record"]["response_message_class"],
                         "ecosystem.communication.ack")
        # Closure shows a boundary ran this packet. It does not show which
        # organization that boundary belongs to, and resolution did not claim
        # the peer serves the capability.
        self.assertIs(closed["closure_record"]["reconstruction_proves_the_boundary_ran_this_packet"], True)
        self.assertIs(closed["closure_record"]["reconstruction_proves_who_the_far_side_is"], False)
        self.assertIs(emitted["peer_serves_this_capability_is_proven_here"], False)
        self.assertEqual(len(self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                           "stegverse.repo-transition-receipt/v1",
                                           egress.CLOSED_CLASS)), 1)
        self.assertTrue(self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                      "stegverse.organization-transition-receipt/v1"))


class DesignatedLedgerRefTests(unittest.TestCase):
    """The organization ledger ref is designated. The recorder exemption stands.

    These checks read the contract. They do not mint a receipt.
    """

    def test_the_ref_is_designated_and_the_recorder_exemption_stands(self):
        org = json.loads((ROOT / ".stegverse/transition-ledger/org-contract.json").read_text())
        repo = json.loads((ROOT / ".stegverse/transition-ledger/contract.json").read_text())
        self.assertEqual(org["organization_ledger_ref"], "refs/stegverse/organization-ledger")
        self.assertEqual(org["organization_ledger_repository"], "StegGhost/.github")
        self.assertIs(org["organization_record_service_declared"], False)
        self.assertTrue(org["organization_record_submission_disposition"].startswith("DENY_"))
        self.assertIn("SGHOST-EXEMPTION-006", org["_why_the_submission_refuses_today"])
        location = repo["repository_ledger_location"]
        self.assertEqual(location["repository"], "StegGhost/.github")
        self.assertEqual(location["ref"], org["organization_ledger_ref"])
        self.assertIs(location["new_ledger_root"], False)
        self.assertTrue(location["namespace"])

    def test_the_committed_request_workflow_appends_pushes_and_reads_the_ref_back(self):
        text = (ROOT / ".github/workflows/organization-ledger-transition.yml").read_text(
            encoding="utf-8")
        # B-P40 COMMITTED_REQUEST: a push committing the request, no dispatch, no inputs.
        self.assertNotIn("workflow_dispatch:", text)
        self.assertNotIn("github.event.inputs", text)
        self.assertIn("on:\n  push:\n    branches: [main]\n    paths:\n"
                      "      - .stegverse/organization-ledger-transition/request.json\n", text)
        self.assertIn("refs/stegverse/organization-ledger", text)
        self.assertIn("--self-close", text)
        self.assertIn("communication_id", text)
        self.assertIn('git push origin "$LEDGER_REF:$LEDGER_REF"', text)
        self.assertIn("organization_ledger_readback.py", text)
        self.assertIn("SGHOST-EXEMPTION-006", text)
        self.assertNotIn("federation.json", text)


class CommittedRequestGateTests(unittest.TestCase):
    """The workflow's own inline request gate emits six-field refusals.

    The step's run block is read from the workflow and executed as-is; only
    the committed request file (REQUEST) varies per case. LEDGER_REF is this
    checkout's HEAD, so a request naming HEAD or an ancestor is on the ledger.
    """

    STEP = "      - name: Refuse an absent, invalid or stale committed request before any append\n"
    SIX_FIELDS = ("failure_code", "failed_predicate", "required_evidence_or_repair",
                  "retry_entrypoint", "owning_existing_goal", "next_attempt")

    @classmethod
    def setUpClass(cls):
        lines = (ROOT / ".github/workflows/organization-ledger-transition.yml").read_text(
            encoding="utf-8").splitlines(keepends=True)
        start = lines.index(cls.STEP)
        run = next(i for i in range(start, len(lines)) if lines[i] == "        run: |\n")
        body = []
        for line in lines[run + 1:]:
            if line.strip() and not line.startswith("          "):
                break
            body.append(line[10:] if line.strip() else "\n")
        cls.script = "".join(body)

    HEAD = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                          text=True, check=True).stdout.strip()

    def run_gate(self, inputs, raw=None):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        request = Path(work.name) / "request.json"
        if raw is not None:
            request.write_text(raw)
        elif inputs is not None:
            request.write_text(json.dumps(inputs))
        env = {k: v for k, v in os.environ.items() if k not in ("GITHUB_ENV", "GITHUB_SHA")}
        env.update(REQUEST=str(request), LEDGER_REF="HEAD", RUNNER_TEMP=work.name,
                   GITHUB_ENV=str(Path(work.name) / "env"))
        result = subprocess.run(["bash", "-e", "-c", self.script], cwd=ROOT, env=env,
                                capture_output=True, text=True, check=False)
        result.work = Path(work.name)
        return result

    def assert_refused(self, inputs, code):
        result = self.run_gate(inputs)
        self.assertEqual(result.returncode, 1, (inputs, result.stdout, result.stderr))
        self.assertNotIn("Traceback", result.stderr)
        self.assertNotIn("Traceback", result.stdout)
        refusal = json.loads(result.stdout)
        self.assertEqual(refusal["disposition"], "FAIL_CLOSED")
        for field in self.SIX_FIELDS:
            self.assertTrue(refusal.get(field), (field, refusal))
        self.assertEqual(refusal["failure_code"], code, refusal)
        self.assertEqual(refusal["retry_entrypoint"],
                         ".github/workflows/organization-ledger-transition.yml")
        self.assertIs(refusal["consequence_committed"], False)

    def test_an_absent_or_empty_epoch_is_not_supplied(self):
        # A missing hb_epoch key and "" are both NOT_SUPPLIED.
        self.assert_refused({"communication_id": "c-1"}, "HB_EPOCH_NOT_SUPPLIED")
        self.assert_refused({"hb_epoch": ""}, "HB_EPOCH_NOT_SUPPLIED")
        self.assert_refused({}, "HB_EPOCH_NOT_SUPPLIED")

    def test_an_absent_or_malformed_request_is_refused(self):
        self.assert_refused(None, "LEDGER_TRANSITION_REQUEST_NOT_SUPPLIED")
        result = self.run_gate(None, raw="[1]")
        self.assertEqual(json.loads(result.stdout)["failure_code"], "LEDGER_TRANSITION_REQUEST_INVALID")
        result = self.run_gate(None, raw="{")
        self.assertEqual(json.loads(result.stdout)["failure_code"], "LEDGER_TRANSITION_REQUEST_INVALID")

    def test_identifiers_and_ledger_head_are_checked(self):
        base = {"hb_epoch": "4096", "communication_id": "c-1", "ledger_head": self.HEAD}
        self.assert_refused({**base, "communication_id": ""}, "COMMUNICATION_ID_NOT_SUPPLIED")
        self.assert_refused({**base, "communication_id": "a/../b"}, "REQUEST_IDENTIFIER_INVALID")
        self.assert_refused({**base, "packet_id": "p\u00e9"}, "REQUEST_IDENTIFIER_INVALID")
        self.assert_refused({k: v for k, v in base.items() if k != "ledger_head"}, "LEDGER_HEAD_NOT_SUPPLIED")
        self.assert_refused({**base, "ledger_head": "f" * 40}, "LEDGER_HEAD_INVALID")
        self.assert_refused({**base, "ledger_head": "GENESIS"}, "LEDGER_HEAD_INVALID")

    def test_an_invalid_epoch_is_refused(self):
        for value in ("\u0663\u0663", "\uff13\uff13", "+33", " 33", "33.0", "31", "abc"):
            with self.subTest(value=value):
                self.assert_refused({"hb_epoch": value}, "HB_EPOCH_INVALID")

    def test_a_committed_request_on_the_ledger_passes(self):
        result = self.run_gate({"hb_epoch": "4096", "communication_id": "c-1", "ledger_head": self.HEAD})
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertNotIn("Traceback", result.stderr)
        receipt = json.loads(result.stdout)
        self.assertEqual(receipt["hb_epoch"], "4096")
        self.assertTrue(receipt["request_sha256"].startswith("sha256:"))
        self.assertIs(receipt["derived_from_clock"], False)
        self.assertEqual((result.work / "env").read_text(), "HB_EPOCH=4096\n")
        self.assertEqual((result.work / "closure-id.txt").read_text(),
                         "c-1\norganization-intr-destination-self-closure\n")

    def test_the_legacy_inline_refusal_is_gone(self):
        text = (ROOT / ".github/workflows/organization-ledger-transition.yml").read_text(
            encoding="utf-8")
        self.assertNotIn("DISPATCH_HB_EPOCH_INVALID", text)
        self.assertIn("kernel.writer_epoch_refusal(hb_epoch", text)


class DiagnosticSelfClosureOnAGitRefTests(unittest.TestCase):
    """A scratch git ref receives a diagnostic self-closure and reads it back.

    The repository is temporary. The receipts minted here are test fixtures.
    They are not authentic production receipts, and this test does not publish
    refs/stegverse/organization-ledger.
    """

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.addCleanup(self._work.cleanup)
        self.repo = Path(self._work.name) / "ledger"
        subprocess_git(["init", "-q", str(self.repo)])
        ref = "refs/stegverse/organization-ledger"
        namespace = json.loads(
            (ROOT / ".stegverse/transition-ledger/contract.json").read_text()
        )["repository_ledger_location"]["namespace"]
        self.org_root = "git+" + str(self.repo) + "#" + ref
        self.repo_root = self.org_root + ":" + namespace
        self.namespace = namespace
        previous = {name: os.environ.get(name) for name in
                    ("STEGVERSE_REPO_LEDGER_ROOT", "STEGVERSE_ORG_LEDGER_ROOT")}

        def restore():
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.addCleanup(restore)
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = self.org_root
        os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = self.repo_root

    def test_a_self_closure_appends_both_receipts_and_reads_them_back(self):
        readback = _module("organization_ledger_readback",
                           "resident-runtime/organization_ledger_readback.py")
        closed = ingress.self_close(
            "diagnostic-self-closure-001", registry=REGISTRY,
            packet_id="self-closure-packet", hb_epoch=32)
        self.assertEqual(closed["disposition"], "ALLOW", closed.get("detail"))
        self.assertIs(closed["self_closure"], True)
        self.assertIs(closed["closure_recorded"], True)
        self.assertEqual(closed["communication_id"], "diagnostic-self-closure-001")
        self.assertIs(closed["repository_receipt_observed"], True)
        self.assertIs(closed["organization_receipt_observed"], True)
        assert_constraints(self, closed)
        replayed = ingress.self_close(
            "diagnostic-self-closure-001", registry=REGISTRY,
            packet_id="self-closure-packet", hb_epoch=32)
        self.assertIs(replayed["transition_replayed"], True)
        self.assertEqual(replayed["organization_receipt_sha256"],
                         closed["organization_receipt_sha256"])
        fresh = Path(self._work.name) / "fresh.git"
        subprocess_git(["init", "-q", "--bare", str(fresh)])
        subprocess_git(["--git-dir", str(fresh), "fetch", "-q", str(self.repo),
                        "+refs/stegverse/organization-ledger:refs/stegverse/organization-ledger"])
        verified = readback.readback("git+" + str(fresh) + "#refs/stegverse/organization-ledger",
                                     closed)
        verified["repository_ledger"] = readback.repository_readback(
            "git+" + str(fresh) + "#refs/stegverse/organization-ledger",
            self.namespace, verified, closed)
        self.assertEqual(verified["disposition"], "ALLOW")
        self.assertEqual(verified["closure_communication_id"], "diagnostic-self-closure-001")
        self.assertIs(verified["closure_receipt_carries_communication_id"], True)
        self.assertIs(verified["master_records_awaited"], False)
        repository_ledger = verified["repository_ledger"]
        self.assertIs(repository_ledger["closure_repository_receipt_in_chain"], True)
        self.assertIs(repository_ledger["closure_repository_receipt_carries_communication_id"], True)
        self.assertIs(repository_ledger["replay_read_organization_receipts"], False)
        self.assertEqual(repository_ledger["consumed_by_organization_receipt_sha256"],
                         closed["organization_receipt_sha256"])


class ReadBackEpochIsNeverForwardedTests(AddressedAndClosedTests):
    """B-P36f: an ingress forwarded an epoch read back from its own receipt.

    `intr_destination_ingress._append` handed the organization writer the
    epoch on the repository receipt it had just appended. On a replay that
    receipt is the recorded one, which an earlier writer may have stamped from
    a clock, so the organization receipt claimed a clock epoch with
    `derived_from_clock: false`. Each ingress now forwards only the epoch
    supplied to it, or refuses before the first write. Here the clock is not
    forbidden but fixed, so a laundered clock epoch would be recognisable.
    """

    SUPPLIED = 4096

    def setUp(self):
        super().setUp()
        import datetime as datetime_module
        real = datetime_module.datetime
        self.fixed_ns = kernel.HB_ANCHOR_UNIX_NS + 1_000_000 * kernel.HB_PERIOD_NS
        fixed_ns = self.fixed_ns

        class FixedClock(real):
            @classmethod
            def now(cls, tz=None):
                return real.fromtimestamp(fixed_ns / 1_000_000_000, tz)

        self.clock_epoch = kernel.hb_reference(now_ns=fixed_ns)["epoch"]
        self.assertNotEqual(self.clock_epoch, self.SUPPLIED)
        # Modules loaded during the test (the capability resolver loads the
        # operation afresh) read the fixed clock too.
        datetime_module.datetime = FixedClock
        self.addCleanup(setattr, datetime_module, "datetime", real)
        self.release = _module("release_organization_batch_b_p36f",
                               "resident-runtime/release_organization_batch.py")
        self.propagation = _module("propagate_repository_receipts_b_p36f",
                                   "resident-runtime/propagate_repository_receipts.py")
        for module in (kernel, ingress.repository_ledger.kernel, ingress.organization_ledger.kernel,
                       egress.kernel, egress.repository_ledger.kernel,
                       egress.organization_ledger.kernel):
            previous = module.datetime
            module.datetime = FixedClock
            self.addCleanup(setattr, module, "datetime", previous)

    def all_receipts(self):
        return (self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")
                + self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                "stegverse.organization-transition-receipt/v1"))

    def assert_nothing_laundered(self, supplied=()):
        for record in self.all_receipts():
            reference = record["hb_reference"]
            if reference["derived_from_clock"] is False:
                self.assertIn(reference["epoch"], supplied, record["receipt_sha256"])
                self.assertNotIn("sampled_unix_ns", reference)

    def assert_supplied_pair(self, repository, organization):
        for record in (repository, organization):
            self.assertEqual(record["hb_reference"]["epoch"], self.SUPPLIED)
            self.assertIs(record["hb_reference"]["derived_from_clock"], False)
        self.assertEqual(organization["repo_receipt_sha256"], repository["receipt_sha256"])

    def clock_stamped(self, writer):
        """Have `writer` stamp its receipts from the clock, as writers did before B-P29."""
        original = writer.kernel.supplied_hb_reference
        writer.kernel.supplied_hb_reference = lambda *_args, **_kwargs: writer.kernel.hb_reference()
        self.addCleanup(setattr, writer.kernel, "supplied_hb_reference", original)
        return lambda: setattr(writer.kernel, "supplied_hb_reference", original)

    def test_a_replayed_clock_stamped_repository_receipt_does_not_lend_its_epoch(self):
        # A repository receipt stamped from the clock, whose organization
        # receipt was never written (an earlier writer, or a crash between the
        # two appends).
        restore = self.clock_stamped(ingress.repository_ledger)
        original_append = ingress.organization_ledger.append

        def crash(*_args, **_kwargs):
            raise RuntimeError("stopped between the two appends")
        ingress.organization_ledger.append = crash
        try:
            with self.assertRaises(RuntimeError):
                ingress.receive(diagnostic("read-back"), registry=REGISTRY,
                                packet_id="read-back", hb_epoch=self.SUPPLIED)
        finally:
            ingress.organization_ledger.append = original_append
            restore()
        stamped, = self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                 "stegverse.repo-transition-receipt/v1")
        self.assertIs(stamped["hb_reference"]["derived_from_clock"], True)
        self.assertEqual(stamped["hb_reference"]["epoch"], self.clock_epoch)

        absent = ingress.receive(diagnostic("read-back"), registry=REGISTRY, packet_id="read-back")
        self.assertEqual(absent["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        self.assertEqual(self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                       "stegverse.organization-transition-receipt/v1"), [])

        # B-P36h (O-1): the clock-provenance repository receipt is not consumed
        # as a source, even under a supplied epoch. Refused six-field; nothing
        # is written and the repository receipt is left as it was.
        replayed = ingress.receive(diagnostic("read-back"), registry=REGISTRY,
                                   packet_id="read-back", hb_epoch=self.SUPPLIED)
        self.assertEqual(replayed["failure_code"], "SOURCE_RECEIPT_IS_CLOCK_PROVENANCE")
        self.assertIn("CARRIED:LEGACY_CLOCK_RECEIPT", replayed["required_evidence_or_repair"])
        self.assertEqual(self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                       "stegverse.organization-transition-receipt/v1"), [])
        self.assertEqual(self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                       "stegverse.repo-transition-receipt/v1"), [stamped])
        self.assert_nothing_laundered(supplied=(self.SUPPLIED,))

    def test_the_intr_destination_ingress_with_no_epoch_writes_nothing(self):
        for call in (lambda: ingress.receive(diagnostic("no-epoch"), registry=REGISTRY,
                                             packet_id="no-epoch"),
                     lambda: ingress.self_close("no-epoch-closure", registry=REGISTRY)):
            self.assertEqual(call()["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        self.assertEqual(self.all_receipts(), [])

    def test_the_intr_destination_ingress_carries_the_supplied_epoch_to_both_levels(self):
        ingress.receive(diagnostic("supplied"), registry=REGISTRY, packet_id="supplied",
                        hb_epoch=str(self.SUPPLIED))
        ingress.receive(diagnostic("supplied"), registry=REGISTRY, packet_id="supplied",
                        hb_epoch=self.SUPPLIED + 1)
        repository, = self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                    "stegverse.repo-transition-receipt/v1")
        organization, = self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                      "stegverse.organization-transition-receipt/v1")
        self.assert_supplied_pair(repository, organization)

    def test_the_capability_ingress_with_a_clock_carrier_writes_nothing(self):
        self.publish(diagnostic("addressed-no-epoch"), ADDRESS, "addressed-no-epoch")
        result, = self.consume()
        operation = result["result"]["execution_result"]["application_result"][
            "receiving_operation_result"]
        self.assertEqual(operation["failure_code"], "HB_EPOCH_NOT_SUPPLIED")
        self.assertEqual(self.all_receipts(), [])

    def test_the_capability_ingress_records_at_the_inbound_frames_validated_epoch(self):
        # B-P36g (1): a validated epoch on the inbound frame is the supplied one
        # for the crossing, so the bound operation records at it.
        packet = kernel.build_packet(
            origin_org=PEER, origin_service=kernel.organization_slug(PEER) + "." + PROFILE_ID,
            destination_org=THIS, destination_service=ADDRESS, payload=diagnostic("addressed-supplied"),
            standing=STANDING, transition_reference="intr:transition:addressed-supplied",
            authority_effect="NONE", packet_id="addressed-supplied")
        kernel.publish_packet(packet, root=self.mesh, epoch=self.SUPPLIED)
        result, = self.consume()
        operation = result["result"]["execution_result"]["application_result"][
            "receiving_operation_result"]
        self.assertEqual(operation["disposition"], "ALLOW", operation)
        repository, = self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")
        organization, = self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                      "stegverse.organization-transition-receipt/v1")
        self.assert_supplied_pair(repository, organization)
        self.assert_nothing_laundered(supplied=(self.SUPPLIED,))

    def test_the_egress_and_release_records_refuse_or_carry_the_supplied_epoch(self):
        record = {"intended_action": "PROBE", "disposition": "ALLOW",
                  "crossed_an_organization_boundary": False}
        for name, writer in (("egress", egress), ("release", self.release)):
            with self.subTest(writer=name):
                with self.assertRaises(writer.repository_ledger.RepoLedgerEpochRefused):
                    writer._record("t:" + name, "T", "sha256:" + "0" * 64,
                                   "sha256:" + "1" * 64, record, None)
                self.assertEqual(self.all_receipts(), [])
        appended = egress._record("t:egress", "T", "sha256:" + "0" * 64, "sha256:" + "1" * 64,
                                  record, self.SUPPLIED)
        self.assert_supplied_pair(appended["repository_receipt"], appended["organization_receipt"])
        self.assert_nothing_laundered(supplied=(self.SUPPLIED,))

    def test_propagation_stamps_only_the_epoch_supplied_to_it(self):
        writer = _module("repo_transition_emit_b_p36f", ".stegverse/transition-ledger/emit.py")
        self.clock_stamped(writer)
        stamped = writer.append("t:propagated", "T", "sha256:" + "0" * 64, "sha256:" + "1" * 64,
                                hb_epoch=self.SUPPLIED)
        self.assertIs(stamped["hb_reference"]["derived_from_clock"], True)
        repository_root = Path(os.environ["STEGVERSE_REPO_LEDGER_ROOT"])
        with self.assertRaises(self.propagation.organization_ledger.OrgLedgerEpochRefused):
            self.propagation.propagate(THIS + "/.github", repository_root=repository_root)
        self.assertEqual(self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                       "stegverse.organization-transition-receipt/v1"), [])
        # B-P36h (O-1): a supplied epoch does not make a clock-provenance
        # repository receipt consumable; it is refused and nothing is written.
        with self.assertRaises(self.propagation.organization_ledger.OrgLedgerEpochRefused) as refused:
            self.propagation.propagate(THIS + "/.github", repository_root=repository_root,
                                       hb_epoch=self.SUPPLIED)
        self.assertEqual(refused.exception.refusal["failure_code"], "SOURCE_RECEIPT_IS_CLOCK_PROVENANCE")
        self.assertEqual(self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                       "stegverse.organization-transition-receipt/v1"), [])
        self.assert_nothing_laundered(supplied=(self.SUPPLIED,))


class CarriedClaimIsVerifiedTests(AddressedAndClosedTests):
    """B-P36k: a carrier cannot self-assert CARRIED. A claim naming a head
    that is not this organization's current verified ledger head is refused
    six-field before dispatch, on every role, and nothing is written."""

    SUPPLIED = 4096
    CONTROL = "stegghost.org-control"
    DIAGNOSTIC = "stegghost.boundary-diagnostic"

    def carried(self, service, packet_id, head_sha, payload=None):
        packet = kernel.build_packet(
            origin_org=PEER, origin_service=kernel.organization_slug(PEER) + "." + PROFILE_ID,
            destination_org=THIS, destination_service=service,
            payload=payload or diagnostic(packet_id), standing=STANDING,
            transition_reference="intr:transition:" + packet_id, authority_effect="NONE", packet_id=packet_id)
        frame = kernel.carrier_frame(packet, epoch=self.SUPPLIED)
        body = {key: value for key, value in frame.items() if key != "frame_sha256"}
        body["heartbeat_reference"] = {**frame["heartbeat_reference"], "source": kernel.CARRIED_SOURCE,
                                       "head_receipt_sha": head_sha}
        frame = {**body, "frame_sha256": kernel.sha(body)}
        kernel.publish_frame(frame, root=self.mesh)
        return frame

    def written(self):
        found = set()
        for variable in self.LEDGER_ROOTS:
            root = Path(os.environ[variable])
            if root.exists():
                found |= {path for path in root.rglob("*") if path.is_file()}
        inbox = ROOT / "resident-runtime/control/inbox"
        if inbox.exists():
            found |= {path for path in inbox.rglob("*") if path.is_file()}
        return found

    def test_a_forged_head_is_refused_on_every_route_and_writes_nothing(self):
        forged = "sha256:" + "f" * 64
        before = self.written()
        for service in (ADDRESS, self.CONTROL, self.DIAGNOSTIC):
            self.carried(service, "forged-" + service.split(".")[1], forged,
                         payload={"message_class": "ecosystem.work.request", "communication_id": "forged-work"}
                         if service == self.CONTROL else None)
        results = self.consume()
        self.assertEqual(len(results), 3)
        for item in results:
            result = item["result"]
            self.assertEqual(result["status"], "REFUSED", result)
            refusal = result["refusal"]
            self.assertEqual(refusal["failure_code"], "CARRIED_PROVENANCE_UNVERIFIED")
            for field in ("disposition", "failed_predicate", "required_evidence_or_repair",
                          "retry_entrypoint", "owning_existing_goal", "next_attempt"):
                self.assertIn(field, refusal)
        self.assertEqual(self.written(), before)
        self.assertEqual(self.frames_to(PEER), [])

    def test_a_claim_naming_the_current_verified_head_is_admitted(self):
        ingress.receive(diagnostic("seed-head"), registry=REGISTRY, packet_id="seed-head",
                        hb_epoch=self.SUPPLIED)
        head = json.loads((Path(os.environ["STEGVERSE_ORG_LEDGER_ROOT"]) / "HEAD.json").read_text())
        self.carried(ADDRESS, "carried-verified", head["receipt_sha256"])
        result, = self.consume()
        self.assertEqual(result["result"]["status"], "CONSUMED", result["result"])
        operation = result["result"]["execution_result"]["application_result"]["receiving_operation_result"]
        self.assertEqual(operation["disposition"], "ALLOW", operation)
        # B-P36m: both receipts for the crossing read CARRIED, never a bare
        # supplied stamp: source and head_receipt_sha travel with the epoch.
        repository = [r for r in self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")
                      if r["transition_id"].endswith(":carried-verified")]
        organization = [r for r in self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                                 "stegverse.organization-transition-receipt/v1")
                        if r["source_transition_id"].endswith(":carried-verified")]
        self.assertEqual((len(repository), len(organization)), (1, 1))
        for record in repository + organization:
            reference = record["hb_reference"]
            self.assertEqual(reference["epoch"], self.SUPPLIED)
            self.assertIs(reference["derived_from_clock"], False)
            self.assertEqual(reference["source"], "ORGANIZATION_LEDGER_HEAD")
            self.assertEqual(reference["head_receipt_sha"], head["receipt_sha256"])
            self.assertNotIn("sampled_unix_ns", reference)


class LedgerWriteFaultIsNonTerminalTests(AddressedAndClosedTests):
    """F-TRANSIENT-RT: a lost compare-and-swap (or any store fault) on either
    append is this repository's fault, not the frame's. It surfaces as the
    dedicated writer exception with a six-field, terminal-false refusal; nothing
    partial is published at that level, and a retry records the transition once."""

    SUPPLIED = 4096

    def inject(self, store_class, method):
        original = getattr(store_class, method)
        calls = []

        def lost(*args, **kwargs):
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError("ledger_append_lost_comparison")
            return original(*args, **kwargs)
        setattr(store_class, method, lost)
        self.addCleanup(setattr, store_class, method, original)

    def assert_pair(self, repo_count, org_count):
        self.assertEqual(len(self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")),
                         repo_count)
        self.assertEqual(len(self.receipts("STEGVERSE_ORG_LEDGER_ROOT",
                                           "stegverse.organization-transition-receipt/v1")), org_count)

    def test_a_lost_comparison_on_either_append_is_non_terminal_and_retried_once(self):
        import sys
        org_store = sys.modules[ingress.organization_ledger.open_store.__module__].PosixLedgerStore
        repo_store = ingress.repository_ledger.ledger_store.PosixLedgerStore
        for name, (store_class, method), after_fault in (
                ("repository", (repo_store, "put"), (0, 0)),
                ("organization", (org_store, "append_transaction"), (1, 0))):
            with self.subTest(append=name):
                packet_id = "lost-comparison-" + name
                self.inject(store_class, method)
                with self.assertRaises(RuntimeError) as raised:
                    ingress.receive(diagnostic(packet_id), registry=REGISTRY, packet_id=packet_id,
                                    hb_epoch=self.SUPPLIED)
                fault = kernel.write_failure(raised.exception)
                self.assertIsNotNone(fault)
                self.assertIs(fault.refusal["terminal"], False)
                self.assertEqual(fault.refusal["failed_predicate"], "RuntimeError")
                for field in ("disposition", "failure_code", "required_evidence_or_repair",
                              "retry_entrypoint", "owning_existing_goal", "next_attempt"):
                    self.assertIn(field, fault.refusal)
                before = (len(self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")),
                          len(self.receipts("STEGVERSE_ORG_LEDGER_ROOT", "stegverse.organization-transition-receipt/v1")))
                retried = ingress.receive(diagnostic(packet_id), registry=REGISTRY, packet_id=packet_id,
                                          hb_epoch=self.SUPPLIED)
                self.assertEqual(retried["disposition"], "ALLOW", retried)
                again = ingress.receive(diagnostic(packet_id), registry=REGISTRY, packet_id=packet_id,
                                        hb_epoch=self.SUPPLIED)
                self.assertIs(again["transition_replayed"], True)
                after = (len(self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")),
                         len(self.receipts("STEGVERSE_ORG_LEDGER_ROOT", "stegverse.organization-transition-receipt/v1")))
                self.assertEqual((after[0] - before[0] + after_fault[0], after[1] - before[1] + after_fault[1]), (1, 1))


class FailedHeadPublishDoesNotWedgeTests(AddressedAndClosedTests):
    """VALIDATOR @7a12ee6 row 1: an OSError at the org HEAD publish (os.replace
    call #5 of one intr-destination append) must not wedge the ledger. The
    transaction rolls back what it wrote; if residue survives, the next append
    adopts a complete, recomputing receipt that chains to HEAD."""

    SUPPLIED = 4096

    def fail_replace_call(self, number):
        original = os.replace
        calls = []

        def replace(*args, **kwargs):
            calls.append(1)
            if len(calls) == number:
                raise OSError(5, "Input/output error")
            return original(*args, **kwargs)
        os.replace = replace
        return lambda: setattr(os, "replace", original)

    def org_receipts(self):
        return self.receipts("STEGVERSE_ORG_LEDGER_ROOT", "stegverse.organization-transition-receipt/v1")

    def test_a_packet_id_collision_is_refused_six_field_and_writes_nothing(self):
        ingress.receive(diagnostic("collision-a"), registry=REGISTRY, packet_id="collision", hb_epoch=self.SUPPLIED)
        before = (self.org_receipts(), self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1"))
        collided = ingress.receive(diagnostic("collision-b"), registry=REGISTRY, packet_id="collision",
                                   hb_epoch=self.SUPPLIED)
        self.assertEqual((collided["disposition"], collided["failure_code"]), ("FAIL_CLOSED", "LEDGER_RECEIPT_COLLISION"))
        for field in ("failed_predicate", "required_evidence_or_repair", "retry_entrypoint",
                      "owning_existing_goal", "next_attempt"):
            self.assertIn(field, collided)
        self.assertEqual((self.org_receipts(),
                          self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")), before)

    def run_case(self, packet_id, keep_residue):
        import sys
        store_class = sys.modules[ingress.organization_ledger.open_store.__module__].PosixLedgerStore
        if keep_residue:
            original_discard = store_class.discard_unpublished
            store_class.discard_unpublished = lambda self, key: None
        restore = self.fail_replace_call(5)
        try:
            with self.assertRaises(RuntimeError) as raised:
                ingress.receive(diagnostic(packet_id), registry=REGISTRY, packet_id=packet_id,
                                hb_epoch=self.SUPPLIED)
        finally:
            restore()
            if keep_residue:
                store_class.discard_unpublished = original_discard
        self.assertIsNotNone(kernel.write_failure(raised.exception))
        for _cycle in range(2):
            result = ingress.receive(diagnostic(packet_id), registry=REGISTRY, packet_id=packet_id,
                                     hb_epoch=self.SUPPLIED)
            self.assertEqual(result["disposition"], "ALLOW", result)
        organization = [r for r in self.org_receipts() if r["source_transition_id"].endswith(":" + packet_id)]
        self.assertEqual(len(organization), 1)
        head = json.loads((Path(os.environ["STEGVERSE_ORG_LEDGER_ROOT"]) / "HEAD.json").read_text())
        self.assertEqual(head["receipt_sha256"], organization[0]["receipt_sha256"])

    def test_an_io_fault_at_every_write_step_completes_exactly_once(self):
        # B-P36q / torn writes: an OSError at each os.replace (5) and fsync (10)
        # of one intr-destination append, repository and organization levels.
        # The attempt is a non-terminal writer fault; the next cycle records
        # exactly one receipt per level with both HEADs consistent; a later
        # frame is unaffected.
        for function, count in (("replace", 5), ("fsync", 10)):
            for number in range(1, count + 1):
                with self.subTest(fault=function + "#" + str(number)):
                    work = Path(tempfile.mkdtemp(dir=self._work.name))
                    os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(work / "repo")
                    os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(work / "org")
                    original = getattr(os, function)
                    calls = []

                    def faulty(*args, _original=original, _calls=calls, _number=number, **kwargs):
                        _calls.append(1)
                        if len(_calls) == _number:
                            raise OSError(5, "Input/output error")
                        return _original(*args, **kwargs)
                    setattr(os, function, faulty)
                    try:
                        try:
                            ingress.receive(diagnostic("torn"), registry=REGISTRY, packet_id="torn",
                                            hb_epoch=self.SUPPLIED)
                        except RuntimeError as error:
                            self.assertIsNotNone(kernel.write_failure(error))
                    finally:
                        setattr(os, function, original)
                    for _cycle in range(2):
                        result = ingress.receive(diagnostic("torn"), registry=REGISTRY, packet_id="torn",
                                                 hb_epoch=self.SUPPLIED)
                        self.assertEqual(result["disposition"], "ALLOW", result)
                    later = ingress.receive(diagnostic("later"), registry=REGISTRY, packet_id="later",
                                            hb_epoch=self.SUPPLIED)
                    self.assertEqual(later["disposition"], "ALLOW", later)
                    repository = self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")
                    organization = self.org_receipts()
                    for packet in ("torn", "later"):
                        self.assertEqual(len([r for r in repository if r["transition_id"].endswith(":" + packet)]), 1)
                        self.assertEqual(len([r for r in organization
                                              if r["source_transition_id"].endswith(":" + packet)]), 1)
                    org_head = json.loads((work / "org" / "HEAD.json").read_text())["receipt_sha256"]
                    repo_head = json.loads((work / "repo" / "HEAD.json").read_text())["receipt_sha256"]
                    later_org, = [r for r in organization if r["source_transition_id"].endswith(":later")]
                    later_repo, = [r for r in repository if r["transition_id"].endswith(":later")]
                    self.assertEqual((org_head, repo_head), (later_org["receipt_sha256"], later_repo["receipt_sha256"]))

    def test_the_egress_and_release_records_resume_after_a_torn_write(self):
        # B-P36q: egress._record and release._record append repository then
        # organization. A fault at the org HEAD publish (os.replace #5) leaves
        # the repository receipt; the retry returns it and completes the pair
        # once, with no second repository receipt.
        release = _module("release_organization_batch_b_p36q", "resident-runtime/release_organization_batch.py")
        record = {"intended_action": "PROBE", "disposition": "ALLOW", "crossed_an_organization_boundary": False}
        for name, writer in (("egress", egress), ("release", release)):
            with self.subTest(writer=name):
                transition = "t:torn-" + name
                restore = self.fail_replace_call(5)
                try:
                    with self.assertRaises(RuntimeError) as raised:
                        writer._record(transition, "T", "sha256:" + "0" * 64, "sha256:" + "1" * 64,
                                       record, self.SUPPLIED)
                finally:
                    restore()
                self.assertIsNotNone(kernel.write_failure(raised.exception))
                first = writer._record(transition, "T", "sha256:" + "0" * 64, "sha256:" + "1" * 64,
                                       record, self.SUPPLIED)
                again = writer._record(transition, "T", "sha256:" + "0" * 64, "sha256:" + "1" * 64,
                                       record, self.SUPPLIED)
                self.assertEqual(first, again)
                repository = [r for r in self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                                       "stegverse.repo-transition-receipt/v1")
                              if r["transition_id"] == transition]
                organization = [r for r in self.org_receipts() if r["source_transition_id"] == transition]
                self.assertEqual((len(repository), len(organization)), (1, 1))

    def test_egress_emit_returns_its_own_write_fault_six_field(self):
        # F-WRITER-TRACE: egress.emit faulting on its own write (each of its
        # five os.replace points) returns the non-terminal six-field record, not
        # a raised OSError; the next call emits once.
        for number in range(1, 6):
            with self.subTest(replace=number):
                work = Path(tempfile.mkdtemp(dir=self._work.name))
                os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(work / "repo")
                os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(work / "org")
                mesh = work / "mesh"
                restore = self.fail_replace_call(number)
                try:
                    faulted = egress.emit(PEER, diagnostic("writer-trace"), standing=STANDING,
                                          capability=PROFILE_ID, mesh_root=mesh, hb_epoch=self.SUPPLIED)
                finally:
                    restore()
                self.assertEqual(faulted["disposition"], "FAIL_CLOSED", faulted)
                self.assertIs(faulted["terminal"], False)
                for field in ("failure_code", "failed_predicate", "required_evidence_or_repair",
                              "retry_entrypoint", "owning_existing_goal", "next_attempt"):
                    self.assertIn(field, faulted)
                done = egress.emit(PEER, diagnostic("writer-trace"), standing=STANDING,
                                   capability=PROFILE_ID, mesh_root=mesh, hb_epoch=self.SUPPLIED)
                self.assertEqual(done["disposition"], "ALLOW", done)

    def test_re_emitting_a_recorded_packet_is_a_no_op_or_a_six_field_collision(self):
        # V-P11 @bbd81b6: a re-emit is checked against this chain before
        # anything is published, and never publishes then raises.
        mesh = Path(tempfile.mkdtemp(dir=self._work.name))
        first = egress.emit(PEER, diagnostic("re-emit"), standing=STANDING, capability=PROFILE_ID,
                            mesh_root=mesh, hb_epoch=self.SUPPLIED)
        # A byte-identical re-emit (the recorded epoch) is an idempotent no-op.
        same = egress.emit(PEER, diagnostic("re-emit"), standing=STANDING, capability=PROFILE_ID,
                           mesh_root=mesh, hb_epoch=self.SUPPLIED)
        self.assertEqual((first["disposition"], same["disposition"]), ("ALLOW", "ALLOW"), same)
        self.assertIs(same["emission_replayed"], True)
        self.assertEqual(same["emission_repository_receipt_sha256"], first["emission_repository_receipt_sha256"])
        self.assertEqual(same["emission_organization_receipt_sha256"], first["emission_organization_receipt_sha256"])
        # A different-content re-emit (4096 then 5000) is refused six-field;
        # nothing is published.
        again = egress.emit(PEER, diagnostic("re-emit"), standing=STANDING, capability=PROFILE_ID,
                            mesh_root=mesh, hb_epoch=5000)
        self.assertEqual((again["disposition"], again["failure_code"]), ("FAIL_CLOSED", "EMISSION_REPLAY_COLLISION"))
        for field in ("failed_predicate", "required_evidence_or_repair", "retry_entrypoint",
                      "owning_existing_goal", "next_attempt"):
            self.assertIn(field, again)
        self.assertIs(again["emitted"], False)
        self.assertEqual(len(list((mesh / "frames.d").glob("*.json"))), 1)
        repository = [r for r in self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")
                      if r["transition_id"] == egress.EMITTED_CLASS + ":" + first["packet_id"]]
        self.assertEqual(len(repository), 1)
        match = egress.request_bilateral_match(PEER, "some-packet", standing=STANDING, mesh_root=mesh,
                                               hb_epoch=self.SUPPLIED)
        rematch = egress.request_bilateral_match(PEER, "some-packet", standing=STANDING, mesh_root=mesh,
                                                 hb_epoch=5000)
        self.assertEqual((match["disposition"], rematch["failure_code"]), ("ALLOW", "EMISSION_REPLAY_COLLISION"))
        self.assertEqual(len(list((mesh / "frames.d").glob("*.json"))), 2)

    def faulting(self, function, number):
        original = getattr(os, function)
        calls = []

        def faulty(*args, **kwargs):
            calls.append(1)
            if len(calls) == number:
                raise OSError(5, "Input/output error")
            return original(*args, **kwargs)
        setattr(os, function, faulty)
        return lambda: setattr(os, function, original)

    def fresh_ledgers(self):
        work = Path(tempfile.mkdtemp(dir=self._work.name))
        os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(work / "repo")
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(work / "org")
        return work

    def test_release_and_submit_completes_exactly_once_across_faults_and_repeats(self):
        # V-P11 @5bc61ff: a fault at any os.replace (10) or fsync (20) of
        # release --standing, then a retry and a repeated call, leaves exactly
        # one release and one submission outcome. A repeated call releases
        # nothing: the release's own receipts are not a new segment.
        import io, contextlib
        release = _module("release_organization_batch_v_p11", "resident-runtime/release_organization_batch.py")
        emitter = _module("emit_v_p11", ".stegverse/transition-ledger/emit.py")
        zero, one = "sha256:" + "0" * 64, "sha256:" + "1" * 64
        for function, count in (("replace", 10), ("fsync", 20)):
            for number in range(1, count + 1):
                with self.subTest(fault=function + "#" + str(number)):
                    self.fresh_ledgers()
                    seed = emitter.append("seed:1", "T", zero, one, hb_epoch=self.SUPPLIED)
                    release.organization_ledger.append(seed, "REPO_STATE_PROPAGATION", zero, one, {}, "NONE",
                                                       hb_epoch=self.SUPPLIED)
                    restore = self.faulting(function, number)
                    try:
                        release.release_and_submit(standing=STANDING, hb_epoch=self.SUPPLIED)
                    except RuntimeError as error:
                        self.assertIsNotNone(kernel.write_failure(error))
                    finally:
                        restore()
                    release.release_and_submit(standing=STANDING, hb_epoch=self.SUPPLIED)
                    repeated = release.release_and_submit(standing=STANDING, hb_epoch=self.SUPPLIED)
                    self.assertIs(repeated["release"]["released"], False)
                    self.assertIsNone(repeated["submission"])
                    classes = [r["transition_class"] for r in self.receipts(
                        "STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")]
                    self.assertEqual(classes.count(release.RELEASE_CLASS), 1, classes)
                    self.assertEqual(classes.count(release.SUBMIT_REFUSED_CLASS), 1, classes)

    def test_a_writer_cli_fault_after_head_is_replaced_does_not_duplicate_on_retry(self):
        # V-P11 @5bc61ff: emit.py and aggregate_repo_transition.py faulting at
        # each fsync/replace print one record per run, and a retry of a failed
        # run leaves exactly one receipt (a fault after HEAD's replace is
        # committed, not reported as a failure to retry).
        import io, contextlib, sys
        emitter = _module("emit_cli_v_p11", ".stegverse/transition-ledger/emit.py")
        aggregate = _module("aggregate_cli_v_p11", "resident-runtime/aggregate_repo_transition.py")
        zero, one = "sha256:" + "0" * 64, "sha256:" + "1" * 64
        for name, module in (("emit", emitter), ("aggregate", aggregate)):
            for function in ("replace", "fsync"):
                for number in range(1, 9):
                    with self.subTest(cli=name, fault=function + "#" + str(number)):
                        work = self.fresh_ledgers()
                        if name == "emit":
                            argv = ["emit", "--transition-id", "x:1", "--transition-class", "T",
                                    "--predecessor-state-sha256", zero, "--successor-state-sha256", one,
                                    "--hb-epoch", str(self.SUPPLIED)]
                            ledger = work / "repo"
                        else:
                            seed = emitter.append("seed:1", "T", zero, one, hb_epoch=self.SUPPLIED)
                            (work / "seed.json").write_text(json.dumps(seed))
                            argv = ["aggregate", "--repo-receipt", str(work / "seed.json"),
                                    "--predecessor-org-state-sha256", zero, "--successor-org-state-sha256", one,
                                    "--hb-epoch", str(self.SUPPLIED)]
                            ledger = work / "org"

                        def run():
                            saved, sys.argv = sys.argv, argv
                            out = io.StringIO()
                            try:
                                with contextlib.redirect_stdout(out):
                                    try:
                                        code = module.main()
                                    except SystemExit as exited:
                                        code = exited.code
                            finally:
                                sys.argv = saved
                            return code, out.getvalue()
                        restore = self.faulting(function, number)
                        try:
                            code, printed = run()
                        finally:
                            restore()
                        self.assertLessEqual(printed.count('"failure_code"'), 1, printed)
                        if code not in (0, None):
                            code, _ = run()
                            self.assertIn(code, (0, None))
                        self.assertEqual(len(list((ledger / "receipts").glob("*.json"))), 1)

    def test_a_re_emit_after_a_faulted_record_publishes_no_second_frame(self):
        # V-P11 @7f3012b row 2: the frame is published, then the emission
        # record faults (each replace and fsync of emit and of
        # request_bilateral_match). A re-emit at another epoch finds the frame
        # on the mesh: exactly 1 frame and 1 EMITTED receipt, and the re-emit is
        # the six-field EMISSION_REPLAY_COLLISION. A byte-identical re-emit
        # completes the record instead.
        calls = {
            "emit": lambda epoch, mesh: egress.emit(PEER, diagnostic("faulted-record"), standing=STANDING,
                                                    capability=PROFILE_ID, mesh_root=mesh, hb_epoch=epoch),
            "bilateral": lambda epoch, mesh: egress.request_bilateral_match(PEER, "faulted-packet", standing=STANDING,
                                                                            mesh_root=mesh, hb_epoch=epoch),
        }
        for name, call in calls.items():
            for function, count in (("replace", 6), ("fsync", 12)):
                for number in range(1, count + 1):
                    for second in (5000, self.SUPPLIED):
                        with self.subTest(call=name, fault=function + "#" + str(number), re_emit=second):
                            work = self.fresh_ledgers()
                            mesh = work / "mesh"
                            restore = self.faulting(function, number)
                            try:
                                first = call(self.SUPPLIED, mesh)
                            finally:
                                restore()
                            frames_d = mesh / "frames.d"
                            published = frames_d.exists() and any(frames_d.glob("*.json"))
                            again = call(second, mesh)
                            frames = list((mesh / "frames.d").glob("*.json")) if (mesh / "frames.d").exists() else []
                            emitted = [r for r in self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                                                "stegverse.repo-transition-receipt/v1")
                                       if r["transition_class"] == egress.EMITTED_CLASS]
                            self.assertEqual(len(frames), 1, (first, again))
                            self.assertEqual(len(emitted), 1, (first, again))
                            if second == self.SUPPLIED or not published:
                                # Byte-identical: the record is completed. Or the
                                # fault came before the frame: a fresh emit.
                                self.assertEqual(again["disposition"], "ALLOW", again)
                            else:
                                self.assertEqual(again.get("failure_code"), "EMISSION_REPLAY_COLLISION", again)
                                self.assertIs(again["emitted"], False)

    def test_an_unverified_frame_claiming_our_packet_id_is_refused_and_binds_nothing(self):
        # V-P11 @be39f2f EGRESS_ON_MESH_FRAME_UNVERIFIED: a frames.d frame that
        # claims our packet id binds only if it is this packet's own frame.
        # Malformed, tampered (claimed digest kept) and re-hashed forgeries are
        # each refused six-field, with nothing published or recorded and no
        # traceback.
        import base64, hashlib
        probe_work = self.fresh_ledgers()
        genuine = egress.emit(PEER, diagnostic("on-mesh-forgery"), standing=STANDING, capability=PROFILE_ID,
                              mesh_root=probe_work / "mesh", hb_epoch=self.SUPPLIED)
        self.assertEqual(genuine["disposition"], "ALLOW", genuine)
        own = json.loads(next((probe_work / "mesh" / "frames.d").glob("*.json")).read_text())
        packet_id = genuine["packet_id"]
        tampered = {**own, "origin_org": "Mallory-org",
                    "packet_base64": base64.b64encode(b'{"packet_id": "x"}').decode("ascii")}
        rehashed = {k: v for k, v in tampered.items() if k != "frame_sha256"}
        rehashed["frame_sha256"] = kernel.sha(rehashed)
        # A digest-correct forgery: our packet re-encoded with another origin and
        # payload, packet_sha256, packet_base64 and frame_sha256 all recomputed.
        forged_packet = {**json.loads(base64.b64decode(own["packet_base64"])),
                         "payload": {"forged": True}}
        forged_packet["origin"] = {**forged_packet["origin"], "org": "Mallory-org"}
        consistent = kernel.carrier_frame(forged_packet, epoch=self.SUPPLIED)
        self.assertEqual(consistent["packet_id"], packet_id)
        kernel.recover_packet(consistent)
        forgeries = {
            "digest_correct_content_swapped": consistent,
            "malformed": {"packet_id": packet_id, "origin_org": "Mallory-org", "frame_sha256": "sha256:" + "f" * 64,
                          "packet_base64": "AAAA", "heartbeat_reference": {"epoch": 99}},
            "tampered_claimed_digest_kept": tampered,
            "rehashed": rehashed,
        }
        for name, forged in forgeries.items():
            with self.subTest(forgery=name):
                work = self.fresh_ledgers()
                frames = work / "mesh" / "frames.d"
                frames.mkdir(parents=True)
                (frames / (hashlib.sha256(name.encode()).hexdigest() + ".json")).write_text(json.dumps(forged))
                refused = egress.emit(PEER, diagnostic("on-mesh-forgery"), standing=STANDING, capability=PROFILE_ID,
                                      mesh_root=work / "mesh", hb_epoch=self.SUPPLIED)
                self.assertEqual((refused["disposition"], refused["failure_code"]),
                                 ("FAIL_CLOSED", "EMISSION_FRAME_UNVERIFIED"), refused)
                self.assertIs(refused["emitted"], False)
                for field in ("failed_predicate", "required_evidence_or_repair", "retry_entrypoint",
                              "owning_existing_goal", "next_attempt"):
                    self.assertIn(field, refused)
                self.assertEqual(len(list(frames.glob("*.json"))), 1)
                self.assertEqual(self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1"), [])

    def test_a_deeply_nested_frames_d_entry_is_skipped_and_emit_proceeds(self):
        # F-SCAN-RECURSION: one deep frames.d file (RecursionError on decode)
        # claims nothing; emit and request_bilateral_match proceed normally.
        work = self.fresh_ledgers()
        frames = work / "mesh" / "frames.d"
        frames.mkdir(parents=True)
        (frames / "0000-deep.json").write_text('{"a":' + "[" * 200000)
        emitted = egress.emit(PEER, diagnostic("deep-neighbour"), standing=STANDING, capability=PROFILE_ID,
                              mesh_root=work / "mesh", hb_epoch=self.SUPPLIED)
        self.assertEqual(emitted["disposition"], "ALLOW", emitted)
        match = egress.request_bilateral_match(PEER, "deep-neighbour-packet", standing=STANDING,
                                               mesh_root=work / "mesh", hb_epoch=self.SUPPLIED)
        self.assertEqual(match["disposition"], "ALLOW", match)
        self.assertEqual(len(list(frames.glob("*.json"))), 3)

    # ------------------------------------------- lead ruling 09:44Z on the batch chain

    def release_modules(self, tag):
        release = _module("release_organization_batch_" + tag, "resident-runtime/release_organization_batch.py")
        emitter = _module("emit_" + tag, ".stegverse/transition-ledger/emit.py")
        return release, emitter

    def seed_transition(self, release, emitter, name):
        zero, one = "sha256:" + "0" * 64, "sha256:" + "1" * 64
        seed = emitter.append(name, "T", zero, one, hb_epoch=self.SUPPLIED)
        release.organization_ledger.append(seed, "REPO_STATE_PROPAGATION", zero, one, {}, "NONE",
                                           hb_epoch=self.SUPPLIED)

    def release_classes(self, release):
        return [r["transition_class"] for r in self.receipts("STEGVERSE_REPO_LEDGER_ROOT",
                                                             "stegverse.repo-transition-receipt/v1")
                ].count(release.RELEASE_CLASS)

    def test_release_predecessor_carries_the_prior_release_receipt_digest(self):
        # Condition 2: the next batch names the prior release's own receipt
        # digest; it resolves in the ledger and recomputes. Condition 1: the
        # prior release receipt stays on the chain, excluded from the payload.
        release, emitter = self.release_modules("ruling_c2")
        self.fresh_ledgers()
        self.seed_transition(release, emitter, "c2:1")
        first = release.release(hb_epoch=self.SUPPLIED)
        self.assertIsNone(first["release_record"]["release_predecessor_receipt_sha256"])
        self.seed_transition(release, emitter, "c2:2")
        second = release.release(hb_epoch=self.SUPPLIED)
        record = second["release_record"]
        self.assertEqual(record["release_predecessor_receipt_sha256"], first["release_organization_receipt_sha256"])
        self.assertEqual(record["release_predecessor"], first["batch_sha256"])
        self.assertNotIn(first["release_organization_receipt_sha256"], record["released_organization_receipts"])
        self.assertIn(first["release_organization_receipt_sha256"],
                      [r["receipt_sha256"] for r in release.organization_chain()])
        self.assertIsNone(release.release_predecessor_refusal(record))

    def refused_release(self, release, segment):
        genuine = release.verified_segment
        release.verified_segment = lambda: segment
        try:
            return release.release(hb_epoch=self.SUPPLIED)
        finally:
            release.verified_segment = genuine

    def assert_predecessor_refusal(self, refused, code):
        self.assertEqual((refused["disposition"], refused["failure_code"]), ("FAIL_CLOSED", code), refused)
        self.assertIs(refused["terminal"], False)
        self.assertIs(refused["released"], False)
        self.assertIn("after ledger repair", refused["retry_entrypoint"])
        for field in ("failed_predicate", "required_evidence_or_repair", "retry_entrypoint",
                      "owning_existing_goal", "next_attempt"):
            self.assertIn(field, refused)

    def test_a_release_whose_predecessor_does_not_resolve_is_refused_six_field(self):
        # Condition 3: RELEASE_PREDECESSOR_UNRESOLVED, non-terminal, nothing written.
        release, emitter = self.release_modules("ruling_c3_unresolved")
        self.fresh_ledgers()
        self.seed_transition(release, emitter, "c3u:1")
        release.release(hb_epoch=self.SUPPLIED)
        self.seed_transition(release, emitter, "c3u:2")
        segment = dict(release.verified_segment(), release_predecessor_receipt_sha256="sha256:" + "f" * 64)
        refused = self.refused_release(release, segment)
        self.assert_predecessor_refusal(refused, "RELEASE_PREDECESSOR_UNRESOLVED")
        self.assertEqual(self.release_classes(release), 1)

    def test_a_release_whose_predecessor_does_not_recompute_is_refused_six_field(self):
        # Condition 3: RELEASE_PREDECESSOR_DIGEST_MISMATCH, non-terminal, nothing written.
        release, emitter = self.release_modules("ruling_c3_mismatch")
        work = self.fresh_ledgers()
        self.seed_transition(release, emitter, "c3m:1")
        first = release.release(hb_epoch=self.SUPPLIED)
        self.seed_transition(release, emitter, "c3m:2")
        segment = release.verified_segment()
        digest = first["release_organization_receipt_sha256"]
        path = work / "org" / "receipts" / (digest.split(":", 1)[1] + ".json")
        tampered = {**json.loads(path.read_text()), "authority_effect": "TAMPERED"}
        path.write_text(json.dumps(tampered))
        refused = self.refused_release(release, segment)
        self.assert_predecessor_refusal(refused, "RELEASE_PREDECESSOR_DIGEST_MISMATCH")
        self.assertEqual(self.release_classes(release), 1)

    def test_a_deleted_or_tampered_prior_release_receipt_is_refused_six_field(self):
        # C3: a chain that does not verify -- the prior release receipt really
        # deleted, or tampered with -- is RELEASE_PREDECESSOR_RECEIPT_UNVERIFIED,
        # six-field and non-terminal, with nothing written; never a bare DENY.
        for damage in ("deleted", "tampered"):
            with self.subTest(damage=damage):
                release, emitter = self.release_modules("c3_chain_" + damage)
                work = self.fresh_ledgers()
                self.seed_transition(release, emitter, "c3c:1")
                first = release.release(hb_epoch=self.SUPPLIED)
                self.seed_transition(release, emitter, "c3c:2")
                path = work / "org" / "receipts" / (first["release_organization_receipt_sha256"].split(":", 1)[1] + ".json")
                if damage == "deleted":
                    path.unlink()
                else:
                    path.write_text(json.dumps({**json.loads(path.read_text()), "authority_effect": "TAMPERED"}))
                refused = release.release(hb_epoch=self.SUPPLIED)
                self.assert_predecessor_refusal(refused, "RELEASE_PREDECESSOR_RECEIPT_UNVERIFIED")
                self.assertEqual(self.release_classes(release), 1)

    def test_a_callers_custody_prefixed_communication_is_still_released(self):
        # V-P11 @35c7cec deferral CUSTODY_PREFIX_USER_COMMUNICATION_NEVER_RELEASED:
        # only the exact custody id of a recorded release is bookkeeping.
        release, emitter = self.release_modules("custody_prefix")
        work = self.fresh_ledgers()
        emitted = egress.emit(PEER, diagnostic("custody-a-callers-own-thread"), standing=STANDING,
                              capability=PROFILE_ID, mesh_root=work / "mesh", hb_epoch=self.SUPPLIED)
        self.assertEqual(emitted["disposition"], "ALLOW", emitted)
        segment = release.verified_segment()
        self.assertEqual(segment["segment_length"], 1, segment)
        self.assertEqual(segment["release_bookkeeping_receipts"], 0)

    def test_a_failed_directory_fsync_is_recorded_as_evidence_not_a_failure(self):
        # Lead ruling: the replace is the commit; a failed directory fsync after
        # it is one non-terminal evidence line, the append returns once.
        import contextlib, io
        release, emitter = self.release_modules("dir_fsync")
        self.fresh_ledgers()
        store_class = emitter.ledger_store.PosixLedgerStore
        original = store_class.__dict__["_sync_directory"]

        def failing(directory):
            raise OSError(5, "Input/output error")
        store_class._sync_directory = staticmethod(failing)
        err = io.StringIO()
        try:
            with contextlib.redirect_stderr(err):
                receipt = emitter.append("fsync:1", "T", "sha256:" + "0" * 64, "sha256:" + "1" * 64,
                                         hb_epoch=self.SUPPLIED)
        finally:
            store_class._sync_directory = original
        lines = [json.loads(line) for line in err.getvalue().splitlines() if line.strip()]
        self.assertTrue(lines)
        for line in lines:
            self.assertEqual(line["failed_step"], "DIRECTORY_FSYNC_AFTER_REPLACE")
            self.assertIs(line["write_committed"], True)
            self.assertIs(line["terminal"], False)
        repository = self.receipts("STEGVERSE_REPO_LEDGER_ROOT", "stegverse.repo-transition-receipt/v1")
        self.assertEqual([r["receipt_sha256"] for r in repository], [receipt["receipt_sha256"]])

    def test_a_failed_org_head_publish_rolls_back_and_the_next_cycle_appends_once(self):
        self.run_case("head-publish-rollback", keep_residue=False)

    def test_residue_of_a_failed_publish_is_adopted_by_the_next_append(self):
        self.run_case("head-publish-adopted", keep_residue=True)


def subprocess_git(args):
    import subprocess
    completed = subprocess.run(["git", *args], capture_output=True, text=True)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)


class CloseResponseAbsentFailsClosed(unittest.TestCase):
    """`close` with no response in the mesh fails closed with the six fields.

    Function-level port of StegVerse-org/.github#186's
    tests/test_egress_close_response_absent_fail_closed.py onto this
    organization's module. An absent response is the protocol's
    receiver-unavailable disposition, DURABLE_QUEUE_OR_EVENT_EPHEMERAL_MATERIALIZATION,
    returned FAIL_CLOSED with the six fields; nothing is written at either
    ledger level. The supplied epoch is checked first. Both ledger roots and the
    mesh are temporary; a passing test is not an authentic receipt.
    """
    SIX_FIELDS = ("failure_code", "failed_predicate", "required_evidence_or_repair",
                  "retry_entrypoint", "owning_existing_goal", "next_attempt")
    ENTRYPOINT = "resident-runtime/organization_egress_boundary.py::close"
    LEDGER_ENV = ("STEGVERSE_REPO_LEDGER_ROOT", "STEGVERSE_ORG_LEDGER_ROOT")

    def setUp(self):
        self._work = tempfile.TemporaryDirectory()
        self.addCleanup(self._work.cleanup)
        work = Path(self._work.name)
        self.mesh = work / "mesh"
        self.mesh.mkdir()
        self.repo_ledger = work / "repo-ledger"
        self.org_ledger = work / "org-ledger"
        previous = {name: os.environ.get(name) for name in self.LEDGER_ENV}
        os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(self.repo_ledger)
        os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(self.org_ledger)

        def restore():
            for name, value in previous.items():
                if value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = value
        self.addCleanup(restore)

    @staticmethod
    def _files(root):
        if not root.exists():
            return []
        return sorted(str(p.relative_to(root)) for p in root.rglob("*") if p.is_file())

    def close(self, hb_epoch="40"):
        return egress.close(PEER, "packet-response-absent", "comm-response-absent",
                            mesh_root=self.mesh, hb_epoch=hb_epoch)

    def assert_six_fields(self, result):
        self.assertEqual(result["disposition"], "FAIL_CLOSED")
        for field in self.SIX_FIELDS:
            self.assertIsInstance(result.get(field), str, field)
            self.assertTrue(result[field].strip(), field)
        self.assertEqual(result["retry_entrypoint"], self.ENTRYPOINT)
        self.assertEqual(result["owning_existing_goal"],
                         "INTERLOCK-INTR-RUNTIME-INDEPENDENT-PROTOCOL-001")
        self.assertEqual(result["owning_existing_goal"], egress.INTR_PROTOCOL_GOAL)
        self.assertIs(result["closed"], False)
        self.assertIs(result["closure_recorded"], False)
        self.assertIs(result["refusal_recorded"], False)
        self.assertEqual(result["authority_effect"], "NONE_REFUSAL_ONLY")
        self.assertEqual(result["request_packet_id"], "packet-response-absent")
        self.assertEqual(result["communication_id"], "comm-response-absent")

    def assert_response_absent_refusal(self, result):
        self.assert_six_fields(result)
        self.assertNotEqual(result["disposition"], "PENDING")
        self.assertEqual(result["failure_code"], egress.RESPONSE_ABSENT_FAILURE_CODE)
        self.assertEqual(result["failure_code"],
                         "DURABLE_QUEUE_OR_EVENT_EPHEMERAL_MATERIALIZATION")
        self.assertEqual(result["failed_predicate"],
                         "EGRESS_RESPONSE_DURABLY_MATERIALIZED_BEFORE_CLOSE")
        self.assertIn("comm-response-absent", result["required_evidence_or_repair"])
        self.assertIn(self.ENTRYPOINT, result["next_attempt"])
        self.assertIs(result["absence_is_not_a_transition"], True)
        self.assertEqual(result["destination_organization"], PEER)
        self.assertNotIn("closure_repository_receipt_sha256", result)
        self.assertNotIn("closure_organization_receipt_sha256", result)

    def assert_epoch_refusal(self, result, failure_code):
        self.assert_six_fields(result)
        self.assertEqual(result["failure_code"], failure_code)
        self.assertEqual(result["failed_predicate"], "SUBMISSION_CARRIES_THE_SUPPLIED_HB_EPOCH")

    def assert_nothing_appended(self):
        self.assertEqual(self._files(self.repo_ledger), [])
        self.assertEqual(self._files(self.org_ledger), [])

    def test_no_response_fails_closed_with_the_six_fields(self):
        self.assert_response_absent_refusal(self.close())
        self.assert_nothing_appended()

    def test_the_refusal_is_the_same_on_every_attempt_and_records_nothing(self):
        first, second = self.close("40"), self.close("41")
        self.assertEqual(first, second)
        self.assert_response_absent_refusal(second)
        self.assert_nothing_appended()

    def test_no_epoch_and_no_response_is_hb_epoch_not_supplied(self):
        self.assert_epoch_refusal(self.close(None), "HB_EPOCH_NOT_SUPPLIED")
        self.assert_nothing_appended()

    def test_an_invalid_epoch_and_no_response_is_hb_epoch_invalid(self):
        for invalid in ("31", "+33", " 33", "3_3", "33.0", True, 31):
            with self.subTest(hb_epoch=invalid):
                self.assert_epoch_refusal(self.close(invalid), "HB_EPOCH_INVALID")
        self.assert_nothing_appended()

    def test_a_supplied_epoch_and_no_response_is_the_response_absence(self):
        for supplied in ("32", "0033", 40):
            with self.subTest(hb_epoch=supplied):
                self.assert_response_absent_refusal(self.close(supplied))
        self.assert_nothing_appended()

    def test_the_epoch_is_checked_before_the_destination_or_the_mesh_is_read(self):
        from unittest import mock
        with mock.patch.object(egress, "resolve_destination",
                               side_effect=AssertionError("destination read")), \
                mock.patch.object(egress.kernel, "collect_ecosystem_responses",
                                  side_effect=AssertionError("mesh read")):
            self.assert_epoch_refusal(self.close(None), "HB_EPOCH_NOT_SUPPLIED")
        self.assert_nothing_appended()

    def test_the_declared_precedence_puts_inputs_before_state_and_the_epoch_first(self):
        order = egress.CLOSE_REFUSAL_PRECEDENCE
        self.assertEqual(order[0], ("SUBMISSION_CARRIES_THE_SUPPLIED_HB_EPOCH", "INPUT"))
        kinds = [kind for _, kind in order]
        self.assertEqual(kinds, sorted(kinds, key=lambda kind: kind != "INPUT"))
        self.assertIn(("EGRESS_RESPONSE_DURABLY_MATERIALIZED_BEFORE_CLOSE", "STATE"), order)

    def test_the_owning_organization_is_unchanged(self):
        self.assertEqual(egress.OWNER_REPOSITORY, "StegGhost/.github")

    def test_an_unattested_emission_reports_no_recorded_attestation(self):
        self.assertIsNone(egress._recorded_attestation(None))
        self.assertIsNone(egress._recorded_attestation({"origin_attestation_state": "NOT_PROVEN"}))

    def test_a_proven_emission_reports_only_the_attestation_it_recorded(self):
        emission = {"origin_attestation_state": egress.attestation_module.PROVEN,
                    "signature_sha256": "s" * 64, "far_side_service_id": "not-carried"}
        recorded = egress._recorded_attestation(emission)
        self.assertEqual(recorded["signature_sha256"], "s" * 64)
        self.assertNotIn("far_side_service_id", recorded)
        self.assertIs(recorded["attestation_read_from_this_organizations_own_emission_record"], True)

    def test_reconstruct_far_side_chain_is_this_kernels_recomputation(self):
        self.assertEqual(egress.reconstruct_far_side_chain("pkt-1", "svc", "h" * 64),
                         kernel.far_side_receipt_chain("pkt-1", "svc", "h" * 64))

    def test_the_cli_exits_nonzero_on_the_refusal(self):
        import contextlib
        import io
        import sys
        from unittest import mock
        work = Path(self._work.name)
        payload, standing = work / "payload.json", work / "standing.json"
        payload.write_text("{}", encoding="utf-8")
        standing.write_text(json.dumps({"predecessor": None}), encoding="utf-8")
        real_close = egress.close

        def on_this_mesh(*args, **kwargs):
            kwargs["mesh_root"] = self.mesh
            return real_close(*args, **kwargs)
        argv = ["organization_egress_boundary.py", "--destination-organization", PEER,
                "--payload", str(payload), "--standing", str(standing), "--close",
                "--packet-id", "packet-response-absent",
                "--communication-id", "comm-response-absent", "--hb-epoch", "40"]
        out = io.StringIO()
        with mock.patch.object(sys, "argv", argv), \
                mock.patch.object(egress, "close", on_this_mesh), \
                contextlib.redirect_stdout(out):
            code = egress.main()
        self.assertEqual(code, 1)
        self.assert_response_absent_refusal(json.loads(out.getvalue()))
        self.assert_nothing_appended()


if __name__ == "__main__":
    unittest.main()
