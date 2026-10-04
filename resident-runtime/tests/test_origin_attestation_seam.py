#!/usr/bin/env python3
"""Prove the attestation seam, and prove its ceiling honestly.

Before this, `origin_attestation_state` read NOT_PROVEN on every record this
organization wrote, with no code path that could reach anything else. The seam
now exists: `emit` takes a credential authority, asks it to sign a statement
binding this origin to this packet, asks it to confirm its own signature, and
records PROVEN only on the authority's verification receipt.

What this organization still cannot do is supply the authority. The key lives
on a TV/TVC resident host it has no access to by design. So these cases pass a
stub authority that reproduces the authority's *receipt contract* -- never its
algorithm -- and the suite asserts no credential algorithm lives in this
repository. A second implementation here would make this organization a second
credential authority, which the TV/TVC split exists to prevent.
"""
import hashlib
import hmac
import importlib.util, json, os, tempfile
from pathlib import Path

TREE = Path(__file__).resolve().parents[2]
_T = tempfile.mkdtemp()
os.environ["STEGVERSE_REPO_LEDGER_ROOT"] = str(Path(_T) / "repo-ledger")
os.environ["STEGVERSE_ORG_LEDGER_ROOT"] = str(Path(_T) / "org-ledger")


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, TREE / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


E = load("egress", "resident-runtime/organization_egress_boundary.py")
A = load("attestation", "org-boundary/runtime/origin_attestation.py")
K = load("kernel", "org-kernel/kernel.py")

STANDING = {"mode": "ESTABLISH_GENESIS", "node_ref": "attestation-test", "predecessor": None}
PEER = "StegVerse-Labs"


class StubAuthority:
    """The credential authority's receipt contract, not its algorithm.

    The algorithm lives on a TV/TVC resident host and must not live in this
    repository. What a test needs is a surface that answers the way the
    authority answers, so the boundary's two-call protocol can be exercised:
    ask to sign, then ask to verify, and only the verification receipt moves
    the state. The HMAC below is this test file's own, is never imported by
    any module under test, and the final case asserts the modules carry none.
    """

    def __init__(self, key=b"test-only-not-an-authority"):
        self.key = key
        self.signed = 0
        self.verified = 0

    def _hmac(self, payload):
        digest = hashlib.sha256(payload).hexdigest()
        return digest, hmac.new(self.key, digest.encode("ascii"), hashlib.sha256).hexdigest()

    def sign(self, payload):
        self.signed += 1
        digest, value = self._hmac(payload)
        return {"algo": "hmac-sha256", "value": value, "sha256": digest}

    def verify(self, payload, signature_bytes=None, **_):
        self.verified += 1
        digest, value = self._hmac(payload)
        carried = json.loads(signature_bytes.decode()) if signature_bytes else {}
        # The receipt must name the declared authority and the verify
        # operation, or the module refuses it as a receipt from somewhere else.
        return {"credential_authority": "TV/TVC",
                "operation": A.VERIFY_OPERATION,
                "signature_valid": carried.get("value") == value and carried.get("sha256") == digest,
                "signature_algorithm": "hmac-sha256"}

    def mapping(self):
        return {A.SIGN: self.sign, A.VERIFY: self.verify}


def payload(communication_id):
    return {"message_class": "ecosystem.communication", "communication_id": communication_id,
            "subject": "attestation", "body": {"probe": True}, "requested_action": None,
            "audience": "ORIGIN", "target_organization": PEER, "target_count": 1}


# ------------------------------------------ unattested is the default, and says so
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    plain = E.emit(PEER, payload("attest-none-001"), standing=STANDING, root=TREE,
                   mesh_root=mesh, hb_epoch=7000)
    assert plain["disposition"] == E.ALLOW, plain
    assert plain["origin_attestation_state"] == "NOT_PROVEN"
    assert plain["origin_is_attested_by_the_credential_authority"] is False
    # Which case this is: no signer was supplied, as opposed to one that failed.
    assert plain["signer_supplied"] is False
    record = plain["emission_record"]
    assert record["no_attestation_was_offered"] is True
    assert record["origin_is_asserted_by_the_sender"] is True
    assert record["origin_is_verified_by_this_boundary"] is False
print("UNATTESTED_DEFAULT_PASS")


# ------------------------------------------------- a supplied authority reaches PROVEN
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"
    authority = StubAuthority()
    attested = E.emit(PEER, payload("attest-proven-001"), standing=STANDING,
                      credential_authority=authority.mapping(), root=TREE,
                      mesh_root=mesh, hb_epoch=7001)
    assert attested["disposition"] == E.ALLOW, attested
    assert attested["origin_attestation_state"] == A.PROVEN, attested
    assert attested["origin_is_attested_by_the_credential_authority"] is True
    assert attested["signer_supplied"] is True
    # Two calls, deliberately: asked to sign, then asked to confirm. Recording
    # PROVEN on the strength of having asked would be trusting its own request.
    assert authority.signed == 1 and authority.verified == 1, (authority.signed, authority.verified)
    record = attested["emission_record"]
    assert record["proves_the_authority_signed_this_statement"] is True
    # The overclaim the record refuses: signing is not authenticating the asker.
    assert record["proves_the_authority_authenticated_the_asker"] is False
    assert record["initiator_identification_also_requires_the_bilateral_match"] is True
    # The signature travels inside the packet, bound by packet_sha256.
    frames = sorted((mesh / "frames.d").glob("*.json"))
    carried = [K.recover_packet(json.loads(f.read_text())) for f in frames]
    signed_packets = [p for p in carried if "attestation" in p]
    assert signed_packets, "the signature must travel inside the packet"
    assert signed_packets[0]["attestation"]["algo"] == "hmac-sha256"
    # The statement is reconstructible by the receiver from the packet alone,
    # so nothing travels but the signature.
    rebuilt = A.statement_from_packet(signed_packets[0],
                                      K.sha(payload("attest-proven-001")))
    assert rebuilt == record["attested_statement"], (rebuilt, record["attested_statement"])
print("ATTESTED_PROVEN_PASS")


# --------------------------------- an offered attestation that fails refuses the emission
with tempfile.TemporaryDirectory() as td:
    mesh = Path(td) / "mesh"

    class Unreachable:
        def mapping(self):
            return {}

    refused = E.emit(PEER, payload("attest-unreachable-001"), standing=STANDING,
                     credential_authority=Unreachable().mapping(), root=TREE,
                     mesh_root=mesh, hb_epoch=7002)
    assert refused["disposition"] == E.DENY, refused
    assert refused["emitted"] is False
    # An unreachable authority is a hold, never a pass: emitting anyway would
    # record an attempted attestation as an ordinary unattested crossing.
    assert refused["failed_predicate"] == "CREDENTIAL_AUTHORITY_IS_REACHABLE", refused
    assert refused["refusal_recorded"] is True
    assert not (mesh / "frames.d").exists(), "a refused attestation published a frame"

    # An authority whose own verifier says the signature is not valid is also a
    # refusal, not a downgrade to unattested.
    class LyingSigner(StubAuthority):
        def sign(self, payload):
            return {"algo": "hmac-sha256", "value": "0" * 64, "sha256": "0" * 64}

    lied = E.emit(PEER, payload("attest-invalid-001"), standing=STANDING,
                  credential_authority=LyingSigner().mapping(), root=TREE,
                  mesh_root=mesh, hb_epoch=7003)
    assert lied["disposition"] == E.DENY, lied
    assert lied["emitted"] is False
    assert not (mesh / "frames.d").exists(), "a refused attestation published a frame"
print("OFFERED_AND_FAILED_REFUSES_PASS")


# ------------------------------- no credential algorithm lives in this repository
for relative in ("org-boundary/runtime/origin_attestation.py",
                 "resident-runtime/organization_egress_boundary.py",
                 "org-boundary/runtime/emission_chain_disclosure.py",
                 "org-kernel/kernel.py"):
    source = (TREE / relative).read_text(encoding="utf-8")
    for token in ("import hmac", "hmac.new", "compare_digest"):
        assert token not in source, (relative, token)
# The boundary validator enforces the same thing, so a future edit cannot
# quietly make this organization a second credential authority.
RB = load("runtime_boundary", "org-runtime/runtime_boundary.py")
overlay = json.loads((TREE / "org-runtime/interlock-intr.json").read_text())
assert RB.origin_attestation_is_bound(overlay) is True
assert RB.validate()["checks"]["origin_attestation_is_bound"] is True
# And the ceiling is declared, not inferred.
declared = overlay["egress"]["origin_attestation"]
assert declared["credential_authority_resident_host_available_to_this_organization"] is False
assert declared["signer_is_supplied_by_the_operator_not_held_here"] is True
assert declared["every_crossing_emitted_here_today_is_unattested"] is True
assert declared["verification_algorithm_implemented_here"] is False
assert declared["boundary_holds_key_material"] is False
print("NO_SECOND_CREDENTIAL_AUTHORITY_PASS")
print("ORIGIN_ATTESTATION_SEAM_PASS")
