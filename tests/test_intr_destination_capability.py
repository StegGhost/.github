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
        self.assertEqual(pending["disposition"], "PENDING")
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

    def test_the_dispatch_workflow_appends_pushes_and_reads_the_ref_back(self):
        text = (ROOT / ".github/workflows/organization-ledger-transition.yml").read_text(
            encoding="utf-8")
        self.assertIn("workflow_dispatch", text)
        self.assertIn("refs/stegverse/organization-ledger", text)
        self.assertIn("--self-close", text)
        self.assertIn("communication_id", text)
        self.assertIn('git push origin "$LEDGER_REF:$LEDGER_REF"', text)
        self.assertIn("organization_ledger_readback.py", text)
        self.assertIn("SGHOST-EXEMPTION-006", text)
        self.assertNotIn("federation.json", text)


class DispatchEpochGateTests(unittest.TestCase):
    """The workflow's own inline epoch gate emits the kernel's six-field refusal.

    The step's run block is read from the workflow and executed as-is; only
    DISPATCH_INPUTS (the toJSON of the dispatch inputs) varies per case.
    """

    STEP = "      - name: Refuse an absent or invalid dispatch epoch before any append\n"
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

    def run_gate(self, inputs):
        env = {k: v for k, v in os.environ.items() if k != "DISPATCH_INPUTS"}
        if inputs is not None:
            env["DISPATCH_INPUTS"] = json.dumps(inputs)
        return subprocess.run(["bash", "-e", "-c", self.script], cwd=ROOT, env=env,
                              capture_output=True, text=True, check=False)

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
        # A dispatch string input cannot tell "" from absent; both are NOT_SUPPLIED here.
        self.assert_refused({"communication_id": "c-1"}, "HB_EPOCH_NOT_SUPPLIED")
        self.assert_refused({"hb_epoch": ""}, "HB_EPOCH_NOT_SUPPLIED")
        self.assert_refused(None, "HB_EPOCH_NOT_SUPPLIED")

    def test_an_invalid_epoch_is_refused(self):
        for value in ("\u0663\u0663", "\uff13\uff13", "+33", " 33", "33.0", "31", "abc"):
            with self.subTest(value=value):
                self.assert_refused({"hb_epoch": value}, "HB_EPOCH_INVALID")

    def test_a_supplied_epoch_passes(self):
        result = self.run_gate({"hb_epoch": "4096", "communication_id": "c-1"})
        self.assertEqual(result.returncode, 0, (result.stdout, result.stderr))
        self.assertEqual(result.stdout, "")
        self.assertNotIn("Traceback", result.stderr)

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


def subprocess_git(args):
    import subprocess
    completed = subprocess.run(["git", *args], capture_output=True, text=True)
    if completed.returncode != 0:
        raise AssertionError(completed.stderr)


if __name__ == "__main__":
    unittest.main()
