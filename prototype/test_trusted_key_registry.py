import base64
import hashlib
import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from trusted_key_registry import TrustedKeyRegistry, TrustRegistryError, sign_economic_event_envelope, ECONOMIC_EVENT_DOMAIN
from canonical_entity_register import entity_authority_key_resolver


class TrustedKeyRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "trust.sqlite3"
        self.registry = TrustedKeyRegistry(self.path)
        self.public = Ed25519PrivateKey.generate().public_key().public_bytes(encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw)

    def tearDown(self):
        self.tmp.cleanup()

    def register(self, key_id="key-1", tenant="tenant-a", issuer="SYNERGY-ECONOMICS"):
        return self.registry.register_key(
            key_id=key_id, issuer=issuer, tenant_id=tenant,
            public_key=self.public,
            valid_from="2026-01-01T00:00:00Z",
            valid_until="2027-01-01T00:00:00Z",
            scopes=("synergy.economic.entity-event/v1", "synergy.spatial.registry-proof/v1"),
            audiences=("synergy.metaverse.economic-projection.v1", "synergy.maps.spatial-registry.v1"),
            registered_by="trust-admin", registered_at="2026-11-16T00:00:00Z",
        )

    def test_key_is_durable_tenant_scoped_and_scope_limited(self):
        fingerprint = self.register()
        reopened = TrustedKeyRegistry(self.path)
        key = reopened.resolve_key(
            "key-1", tenant_id="tenant-a",
            required_scope="synergy.economic.entity-event/v1",
            audience="synergy.metaverse.economic-projection.v1",
            now=datetime(2026, 11, 16, tzinfo=timezone.utc),
        )
        self.assertIsNotNone(key)
        self.assertEqual(key.fingerprint_sha256, fingerprint)
        self.assertIsNone(reopened.resolve_key("key-1", tenant_id="tenant-b"))
        self.assertIsNone(reopened.resolve_key("key-1", required_scope="admin"))
        self.assertIsNone(reopened.resolve_key("key-1", audience="wrong-audience"))

    def test_revocation_is_immediate_and_append_only(self):
        self.register()
        self.registry.revoke_key(
            key_id="key-1", revoked_by="security-admin",
            reason="scheduled key rotation", revoked_at="2026-11-16T00:10:00Z",
        )
        self.assertIsNone(self.registry.resolve_key(
            "key-1", now=datetime(2026, 11, 16, 1, tzinfo=timezone.utc)
        ))
        with sqlite3.connect(self.path) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("DELETE FROM trusted_keys WHERE key_id='key-1'")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE key_revocations SET reason='rewritten' WHERE key_id='key-1'")

    def test_rotation_uses_new_key_id_and_revokes_old_key(self):
        self.register("key-old")
        new_public = Ed25519PrivateKey.generate().public_key().public_bytes_raw()
        self.registry.register_key(
            key_id="key-new", issuer="SYNERGY-ECONOMICS", tenant_id="tenant-a",
            public_key=new_public, valid_from="2026-11-16T00:00:00Z",
            valid_until="2027-11-16T00:00:00Z",
            scopes=("synergy.economic.entity-event/v1",),
            audiences=("synergy.metaverse.economic-projection.v1",),
            registered_by="trust-admin", registered_at="2026-11-16T00:00:00Z",
        )
        self.registry.revoke_key(
            key_id="key-old", revoked_by="trust-admin",
            reason="rotated", revoked_at="2026-11-16T00:01:00Z",
        )
        self.assertIsNone(self.registry.resolve_key("key-old"))
        self.assertIsNotNone(self.registry.resolve_key("key-new"))


    def test_economic_verifier_resolver_observes_live_revocation(self):
        self.registry.register_key(
            key_id="entity-key", issuer="KZ-ENTITY-AUTHORITY", tenant_id="tenant-a",
            public_key=self.public, valid_from="2026-01-01T00:00:00Z",
            valid_until="2027-01-01T00:00:00Z",
            scopes=("synergy.economic.entity-event/v1",), audiences=("synergy.economic.entity-register.v1",),
            registered_by="trust-admin", registered_at="2026-11-16T00:00:00Z",
        )
        resolver = entity_authority_key_resolver(self.registry)
        self.assertIsNotNone(resolver("entity-key"))
        self.registry.revoke_key(
            key_id="entity-key", revoked_by="security-admin",
            reason="rotation", revoked_at="2026-11-16T00:01:00Z",
        )
        self.assertIsNone(resolver("entity-key"))


    def test_economic_marketplace_event_signer_uses_domain_separated_ed25519(self):
        private = Ed25519PrivateKey.generate()
        envelope = {
            "schema_version": "synergy.event.v1", "event_id": "evt-1",
            "event_type": "marketplace.offer.registered",
            "aggregate_type": "economic_marketplace_tenant", "aggregate_id": "tenant-a",
            "aggregate_version": 1, "event_ordinal": 0,
            "occurred_at": "2026-11-16T00:00:00Z", "recorded_at": "2026-11-16T00:00:01Z",
            "actor_id": "economics-service", "authority_ref": "mandate:1",
            "idempotency_key": "evt-1", "command_id": "cmd-1",
            "correlation_id": "corr-1", "causation_id": None,
            "payload": {"tenant_id": "tenant-a", "entity": {"offer_id": "offer-1"}},
            "evidence_refs": [], "payload_digest": "0" * 64,
        }
        signed = sign_economic_event_envelope(
            envelope, private_key=private, key_id="economics-event-key",
            issuer="SYNERGY-ECONOMICS",
            audience="synergy.metaverse.economic-projection.v1",
            issued_at="2026-11-16T00:00:00Z", expires_at="2026-11-16T00:05:00Z",
        )
        unsigned = {key: value for key, value in signed.items() if key != "attestation"}
        canonical = json.dumps(
            unsigned, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        ).encode("utf-8")
        signature = base64.b64decode(signed["attestation"]["signature"], validate=True)
        private.public_key().verify(
            signature, ECONOMIC_EVENT_DOMAIN + hashlib.sha256(canonical).digest()
        )
        self.assertEqual(signed["attestation"]["algorithm"], "Ed25519")

    def test_duplicate_key_id_and_invalid_key_material_are_rejected(self):
        self.register()
        with self.assertRaises(sqlite3.IntegrityError):
            self.register()
        with self.assertRaises(TrustRegistryError):
            self.registry.register_key(
                key_id="bad", issuer="issuer", tenant_id="tenant-a",
                public_key=b"short", valid_from="2026-01-01T00:00:00Z",
                valid_until="2027-01-01T00:00:00Z", scopes=("scope",),
                audiences=("audience",), registered_by="admin",
            )


if __name__ == "__main__":
    unittest.main()
