"""Drive an Interlock/InTr crossing from StegVerse-org all the way into StegGhost.

The federation directory declares StegGhost a peer on
`stegverse.intr.org-boundary.v1`, and this boundary has carried a registry, a
kernel, a node-standing gate and a manifest selector for some time. What it had
never carried is a crossing: nothing drove a packet addressed to a StegGhost
service through `dispatch`, so whether this organization could be *addressed*
was unproven in exactly the way a declared transport with no exercised endpoint
always is.

These tests address `stegghost.boundary-diagnostic` -- the registry's
`BOUNDARY_LOCAL_DIAGNOSTIC` row, which needs no endpoint adapter and writes
nothing -- from a StegVerse-org origin, and hold the whole disposition: the
five-receipt chain, its chaining, the standing ALLOW, and the refusals that
must stay refusals.

The origin side builds with this checkout's own kernel. That is the same packet
StegVerse-org's kernel builds: both are `kernel_version` 1.3.1 and their
`build_packet` bodies differ only in the literal order of two keys, which
`canon()` sorts. A test here must not depend on another organization's
checkout being present, so the agreement is asserted rather than imported.

Nothing here claims runtime observation, InTr delivery over a live carrier, or
any authority effect. Standing is structural and grants nothing.
"""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORGANIZATION = "StegGhost"
DIAGNOSTIC = "stegghost.boundary-diagnostic"
ORIGIN_ORG = "StegVerse-org"
ORIGIN_SERVICE = "stegverse-org.org-control"

RECEIPT_KINDS = ["INGRESS_ACCEPTED", "DISPATCHED", "CONSUMED", "RESULT_BOUND", "EGRESS_EMITTED"]

# `predecessor` is present and null: explicit genesis. An absent key is an
# unstated chain position, and the contract refuses it rather than defaulting.
GENESIS = {"mode": "ESTABLISH_GENESIS", "node_ref": "stegverse-org-boundary", "predecessor": None}

spec = importlib.util.spec_from_file_location("stegghost_kernel", ROOT / "org-kernel/kernel.py")
kernel = importlib.util.module_from_spec(spec)
spec.loader.exec_module(kernel)


def crossing_packet(*, service=DIAGNOSTIC, standing=GENESIS, packet_id="intr-stegghost-001",
                    payload=None):
    packet = kernel.build_packet(
        origin_org=ORIGIN_ORG, origin_service=ORIGIN_SERVICE,
        destination_org=ORGANIZATION, destination_service=service,
        payload=payload if payload is not None else {"probe": "stegghost-crossing"},
        standing=GENESIS, packet_id=packet_id)
    if standing is None:
        packet.pop("standing")
    else:
        packet["standing"] = standing
    return packet


class AddressedServiceTests(unittest.TestCase):
    """The address a peer would resolve has to exist in this organization's registry."""

    def setUp(self):
        self.registry = kernel.load_registry(ROOT)

    def test_this_registry_is_stegghosts(self):
        self.assertEqual(self.registry["organization"], ORGANIZATION)

    def test_the_diagnostic_address_is_declared_and_active(self):
        rows = [s for s in self.registry["services"] if s["service_id"] == DIAGNOSTIC]
        self.assertEqual(len(rows), 1, DIAGNOSTIC + " is not declared exactly once")
        self.assertEqual(rows[0]["boundary_role"], "BOUNDARY_LOCAL_DIAGNOSTIC")
        self.assertEqual(rows[0]["profile_status"], "ACTIVE")
        # A boundary-local diagnostic is the processor, so it needs no runtime
        # standing up elsewhere before it can be addressed.
        self.assertFalse(rows[0]["runtime_required_for_consumption"])

    def test_the_boundary_runtimes_dispatch_requires_are_present(self):
        """`dispatch` fails closed without either; a peer crossing would stop here."""
        for relative in ("org-boundary/runtime/node_standing.py",
                         "org-boundary/runtime/manifest_selection.py",
                         "docs/CANONICAL_NODE_INGRESS_CONTRACT_001.json"):
            with self.subTest(relative):
                self.assertTrue((ROOT / relative).is_file(), relative + " missing")


class CrossingLandsTests(unittest.TestCase):
    """A packet addressed from StegVerse-org to StegGhost is consumed here."""

    @classmethod
    def setUpClass(cls):
        cls.packet = crossing_packet()
        cls.result = kernel.dispatch(ROOT, cls.packet)

    def test_the_crossing_is_consumed_by_the_addressed_service(self):
        self.assertTrue(self.result["consumed"])
        self.assertEqual(self.result["organization"], ORGANIZATION)
        self.assertEqual(self.result["service_id"], DIAGNOSTIC)
        self.assertEqual(self.result["packet_id"], self.packet["packet_id"])

    def test_the_origin_is_another_organization(self):
        self.assertEqual(self.packet["origin"]["org"], ORIGIN_ORG)
        self.assertEqual(self.packet["destination"]["org"], ORGANIZATION)
        self.assertEqual(self.packet["intr_profile"], "stegverse.intr.org-boundary.v1")

    def test_five_receipts_are_minted_in_order_and_chained(self):
        receipts = self.result["receipts"]
        self.assertEqual([r["kind"] for r in receipts], RECEIPT_KINDS)
        previous = None
        for r in receipts:
            self.assertEqual(r["previous_receipt_id"], previous,
                             r["kind"] + " does not chain to its predecessor")
            self.assertEqual(r["packet_id"], self.packet["packet_id"])
            self.assertEqual(r["subject"], DIAGNOSTIC)
            previous = r["receipt_id"]
        self.assertEqual(self.result["reconstruction"]["terminal_receipt_id"], previous)
        self.assertEqual(self.result["reconstruction"]["status"], "RECONSTRUCTED")

    def test_standing_is_allowed_and_says_what_it_is_not(self):
        self.assertEqual(self.result["node_standing_disposition"], "ALLOW")
        self.assertEqual(self.result["standing_mode"], "ESTABLISH_GENESIS")
        self.assertEqual(self.result["standing_generation"], 1)
        self.assertIsNone(self.result["standing_predecessor"])
        self.assertTrue(self.result["boundary_carried_predecessor"])
        self.assertTrue(self.result["boundary_validated_predecessor"])
        # The narrowness is part of the result, not a caveat kept elsewhere.
        self.assertTrue(self.result["structural_standing_only"])
        self.assertFalse(self.result["structural_standing_is_authenticated_standing"])
        self.assertEqual(self.result["standing_authority_effect"], "NONE_STANDING_ONLY")

    def test_a_boundary_local_surface_selects_no_processor(self):
        self.assertEqual(self.result["processing_selection"],
                         "BOUNDARY_LOCAL_NO_PROCESSOR_SELECTED")
        self.assertFalse(self.result["declared_capability_processed"])

    def test_the_crossing_carries_no_authority_effect(self):
        self.assertEqual(self.result["authority_effect"], "NONE")
        self.assertEqual(self.result["application_result"], {"echo": self.packet["payload"]})


class RefusalTests(unittest.TestCase):
    """What must stay refused, so an admitted crossing means something."""

    def test_a_standing_less_dispatch_is_refused(self):
        packet = crossing_packet(standing=None, packet_id="intr-stegghost-no-standing")
        self.assertNotIn("standing", packet)
        with self.assertRaises(ValueError) as refused:
            kernel.dispatch(ROOT, packet)
        self.assertIn("node_standing_refused:", str(refused.exception))
        self.assertIn("no-standing-declared", str(refused.exception))

    def test_an_absent_predecessor_key_is_not_read_as_genesis(self):
        """`predecessor_key: REQUIRED`. Omitting it is an unstated chain
        position, not a default, so it is refused rather than admitted."""
        packet = crossing_packet(
            standing={"mode": "ESTABLISH_GENESIS", "node_ref": "stegverse-org-boundary"},
            packet_id="intr-stegghost-absent-predecessor")
        with self.assertRaises(ValueError) as refused:
            kernel.dispatch(ROOT, packet)
        self.assertIn("node_standing_refused:", str(refused.exception))
        self.assertIn("predecessor-key-absent", str(refused.exception))

    def test_explicit_genesis_may_not_also_declare_a_predecessor(self):
        packet = crossing_packet(
            standing={"mode": "ESTABLISH_GENESIS", "node_ref": "stegverse-org-boundary",
                      "predecessor": {"generation": 1}},
            packet_id="intr-stegghost-contradictory-genesis")
        with self.assertRaises(ValueError) as refused:
            kernel.dispatch(ROOT, packet)
        self.assertIn("explicit-genesis-declares-no-predecessor", str(refused.exception))

    def test_an_unregistered_destination_service_is_refused(self):
        packet = crossing_packet(service="stegghost.not-registered",
                                 packet_id="intr-stegghost-unknown-service")
        with self.assertRaises(ValueError) as refused:
            kernel.dispatch(ROOT, packet)
        self.assertIn("unknown_service", str(refused.exception))

    def test_a_packet_addressed_to_another_organization_is_refused(self):
        packet = crossing_packet(packet_id="intr-stegghost-wrong-org")
        packet["destination"]["org"] = "StegVerse-org"
        with self.assertRaises(ValueError) as refused:
            kernel.dispatch(ROOT, packet)
        self.assertIn("wrong_destination_org", str(refused.exception))

    def test_an_internal_endpoint_without_an_adapter_is_refused(self):
        """The registry's other StegGhost rows are reconciliation-pending, and
        addressing one must not quietly behave like the diagnostic."""
        packet = crossing_packet(service="stegghost.entity-sandbox-runner",
                                 packet_id="intr-stegghost-no-adapter")
        with self.assertRaises(ValueError) as refused:
            kernel.dispatch(ROOT, packet)
        self.assertIn("endpoint_adapter_not_installed", str(refused.exception))


class PacketOriginAgreementTests(unittest.TestCase):
    """The packet this checkout builds is the packet StegVerse-org's kernel builds.

    Asserted on the shape rather than by importing another organization's
    kernel, which a test here must not require to be present.
    """

    def test_the_packet_is_the_transport_profile_the_directory_declares(self):
        packet = crossing_packet(packet_id="intr-stegghost-shape")
        self.assertEqual(packet["schema_version"], "stegverse.intr.org-boundary.v1")
        self.assertEqual(packet["direction"], "INGRESS")
        self.assertEqual(packet["carrier"], {"kind": "HB_DERIVED", "reference": "org-federation"})
        self.assertEqual(sorted(packet), [
            "carrier", "destination", "direction", "evidence", "intr_profile", "origin",
            "packet_id", "payload", "schema_version", "standing", "transition"])

    def test_build_packet_requires_standing_with_no_default(self):
        with self.assertRaises(TypeError):
            kernel.build_packet(
                origin_org=ORIGIN_ORG, origin_service=ORIGIN_SERVICE,
                destination_org=ORGANIZATION, destination_service=DIAGNOSTIC,
                payload={"probe": "no-standing"})


if __name__ == "__main__":
    unittest.main()
