"""Cryptographic integration tests for signed first-administrator bootstrap."""
import base64
import tempfile
import unittest
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from durable_event_register import RegisterError
from labour_register import LabourRegister
from signed_approval_assertions import (
    ApprovalAssertionError,
    SignedApprovalVerifier,
    SignedBootstrapAuthorizer,
    encode_assertion_payload,
)

ISSUER = "https://identity.example.test"
AUDIENCE = "synergy-native-register-bootstrap"
KID = "bootstrap-ed25519-test-1"
NOW = 1_800_000_000
OCCURRED = "2026-11-13T05:00:00Z"


def canonical(value):
    import json
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def sign_assertion(payload, private_key):
    header = {"alg": "EdDSA", "kid": KID, "typ": "JWT"}
    header_segment = base64.urlsafe_b64encode(canonical(header)).decode("ascii").rstrip("=")
    payload_segment = encode_assertion_payload(payload)
    signing_input = header_segment + "." + payload_segment
    signature = private_key.sign(signing_input.encode("ascii"))
    signature_segment = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return signing_input + "." + signature_segment


class SignedBootstrapAuthorizerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.private = Ed25519PrivateKey.generate()
        self.public = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.revoked = set()
        self.assertions = {}
        self.verifier = self.make_verifier()
        self.authorizer = SignedBootstrapAuthorizer(self.verifier, self.assertions.__getitem__)

    def tearDown(self):
        self.tmp.cleanup()

    def make_verifier(self):
        return SignedApprovalVerifier(
            self.root / "assertion-replays.sqlite3",
            issuer=ISSUER,
            audience=AUDIENCE,
            key_resolver=lambda issuer, kid: (
                self.public if issuer == ISSUER and kid == KID else None
            ),
            is_revoked=lambda issuer, kid, jti: (
                (issuer, kid) in self.revoked or (issuer, jti) in self.revoked
            ),
            clock=lambda: NOW,
            clock_skew_seconds=5,
            max_lifetime_seconds=300,
        )

    def token(self, principal="root", register="labour", *, jti="bootstrap-1",
              role="bootstrap_admin", iat=NOW - 5, exp=NOW + 120):
        payload = {"principal_id": principal, "permissions": ["*"]}
        evidence_ref = "authority://bootstrap/" + jti
        context = SignedBootstrapAuthorizer.request_context(
            principal, register, payload, evidence_ref
        )
        claims = {
            "iss": ISSUER,
            "sub": principal,
            "aud": AUDIENCE,
            "service_id": context["service_id"],
            "request_id": context["request_id"],
            "request_digest": context["request_digest"],
            "role": role,
            "evidence_ref": evidence_ref,
            "jti": jti,
            "iat": iat,
            "exp": exp,
        }
        self.assertions[evidence_ref] = sign_assertion(claims, self.private)
        return evidence_ref

    def test_signed_assertion_bootstraps_first_admin_and_survives_reopen(self):
        token = self.token()
        store = LabourRegister(
            self.root / "labour.sqlite3", bootstrap_authorizer=self.authorizer
        )
        self.assertTrue(store.bootstrap_admin(
            principal_id="root", authority_ref=token, occurred_at=OCCURRED
        ))
        self.assertEqual(store.total_event_count, 1)
        self.assertTrue(store.verify())

        # Exact assertion retry is safe and idempotent across verifier instances.
        reopened_verifier = self.make_verifier()
        reopened_authorizer = SignedBootstrapAuthorizer(
            reopened_verifier, self.assertions.__getitem__
        )
        reopened = LabourRegister(
            self.root / "labour.sqlite3", bootstrap_authorizer=reopened_authorizer
        )
        self.assertFalse(reopened.bootstrap_admin(
            principal_id="root", authority_ref=token, occurred_at=OCCURRED
        ))
        self.assertEqual(reopened.total_event_count, 1)
        self.assertTrue(reopened.verify())

    def test_subject_register_role_and_payload_are_bound_to_signature(self):
        cases = [
            ("attacker", "labour", self.token(principal="root")),
            ("root", "legal_rights", self.token(register="labour")),
            ("root", "labour", self.token(role="period_owner")),
        ]
        for index, (principal, register, token) in enumerate(cases):
            with self.subTest(index=index):
                store = LabourRegister(
                    self.root / f"denied-{index}.sqlite3",
                    bootstrap_authorizer=self.authorizer,
                )
                with self.assertRaises(RegisterError):
                    store.bootstrap_admin(
                        principal_id=principal, authority_ref=token, occurred_at=OCCURRED
                    )
                self.assertEqual(store.total_event_count, 0)
                self.assertTrue(store.verify())

    def test_tampered_expired_and_revoked_assertions_fail_closed(self):
        valid = self.token(jti="tamper")
        head, payload, signature = valid.split(".")
        raw = bytearray(base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4)))
        raw[0] ^= 1
        tampered = head + "." + payload + "." + base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")
        expired = self.token(jti="expired", iat=NOW - 500, exp=NOW - 400)
        revoked = self.token(jti="revoked")
        self.revoked.add((ISSUER, KID))
        for index, token in enumerate((tampered, expired, revoked)):
            with self.subTest(index=index):
                store = LabourRegister(
                    self.root / f"denied-crypto-{index}.sqlite3",
                    bootstrap_authorizer=self.authorizer,
                )
                with self.assertRaises(RegisterError):
                    store.bootstrap_admin(
                        principal_id="root", authority_ref=token, occurred_at=OCCURRED
                    )
                self.assertEqual(store.total_event_count, 0)
                self.assertTrue(store.verify())

    def test_missing_signed_verifier_never_falls_back_to_allow(self):
        with tempfile.TemporaryDirectory() as directory:
            store = LabourRegister(Path(directory) / "labour.sqlite3")
            with self.assertRaises(RegisterError):
                store.bootstrap_admin(
                    principal_id="root",
                    authority_ref=self.token(),
                    occurred_at=OCCURRED,
                )
            self.assertEqual(store.total_event_count, 0)


if __name__ == "__main__":
    unittest.main()
