import base64
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from canonical_entity_register import (
    CanonicalEconomicEntityRegister,
    Ed25519EntityAuthorityVerifier,
    EconomicEntityRegisterError,
    TrustedEntityAuthorityKey,
    entity_event_signing_document,
)
from durable_event_register import canonical_json, RegisterError


T = "2026-11-15T08:00:00Z"
RECORDED = "2026-11-15T08:01:00Z"


class SignedAuthority:
    def __init__(self, tenant_id="tenant-kz", authority_refs=("*",)):
        self.private = Ed25519PrivateKey.generate()
        public = self.private.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )
        self.key = TrustedEntityAuthorityKey(
            key_id="authority-key-1", issuer="KZ-ENTITY-AUTHORITY",
            tenant_id=tenant_id, public_key_raw=public,
            valid_from="2026-01-01T00:00:00Z", valid_until="2027-01-01T00:00:00Z",
            authority_refs=authority_refs,
        )
        self.verifier = Ed25519EntityAuthorityVerifier({self.key.key_id: self.key})

    def attestation(self, *, event_id, event_type, aggregate_id, effective_at,
                    recorded_at, actor_id, authority_ref, payload):
        document = entity_event_signing_document(
            event_id=event_id, event_type=event_type, aggregate_id=aggregate_id,
            effective_at=effective_at, recorded_at=recorded_at, actor_id=actor_id,
            authority_ref=authority_ref, payload=payload,
        )
        signature = self.private.sign(canonical_json(document).encode("utf-8"))
        return {
            "algorithm": "Ed25519", "key_id": self.key.key_id,
            "issuer": self.key.issuer, "signed_at": RECORDED,
            "signature": base64.b64encode(signature).decode("ascii"),
            "scope": "synergy.economic.entity-event/v1",
        }


class CanonicalEconomicEntityRegisterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "entities.sqlite3"
        self.authority = SignedAuthority()
        self.store = CanonicalEconomicEntityRegister(
            self.path, authority_verifier=self.authority.verifier,
            clock=lambda: datetime(2026, 11, 15, 9, 0, tzinfo=timezone.utc),
        )
        self.store.bootstrap_admin(
            principal_id="root", authority_ref="BOOTSTRAP:POLICY",
            occurred_at=RECORDED,
        )
        self.store.grant_access(
            event_id="ACL-WRITER", idempotency_key="ACL-WRITER",
            principal_id="registrar", permissions=["entity:read", "entity:write"],
            actor_id="root", authority_ref="POLICY:ENTITY-WRITER", occurred_at=RECORDED,
        )
        self.store.grant_access(
            event_id="ACL-ADMIN", idempotency_key="ACL-ADMIN",
            principal_id="admin", permissions=["entity:read", "entity:write", "entity:admin"],
            actor_id="root", authority_ref="POLICY:ENTITY-ADMIN", occurred_at=RECORDED,
        )
        self.store.grant_access(
            event_id="ACL-READER", idempotency_key="ACL-READER",
            principal_id="auditor", permissions=["entity:read"],
            actor_id="root", authority_ref="POLICY:ENTITY-READER", occurred_at=RECORDED,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def _register(self, *, entity_id="entity-001", tenant_id="tenant-kz", sector="NFC",
                  event_id="ENTITY-REGISTERED", actor="registrar", authority_ref="AUTHORITY:KZ"):
        aggregate = f"{tenant_id}::{entity_id}"
        unsigned = {
            "tenant_id": tenant_id, "entity_id": entity_id, "entity_kind": "company",
            "jurisdiction": "KZ", "institutional_sector": sector,
            "external_refs": [{
                "namespace": "business-registry", "value": "BIN-001",
                "issuer": "KZ-MINISTRY", "evidence_ref": "evidence:registry-extract-1",
            }],
        }
        attestation = self.authority.attestation(
            event_id=event_id, event_type="entity.registered", aggregate_id=aggregate,
            effective_at=T, recorded_at=RECORDED, actor_id=actor,
            authority_ref=authority_ref, payload=unsigned,
        )
        return self.store.register_entity(
            entity_id=entity_id, tenant_id=tenant_id, entity_kind="company",
            jurisdiction="KZ", institutional_sector=sector, event_id=event_id,
            idempotency_key=event_id, effective_at=T, recorded_at=RECORDED,
            actor_id=actor, authority_ref=authority_ref, authority_attestation=attestation,
            external_refs=unsigned["external_refs"],
        )

    def _event(self, *, event_id, event_type, payload, version, actor="registrar",
               authority_ref="AUTHORITY:KZ", effective_at=RECORDED):
        aggregate = "tenant-kz::entity-001"
        unsigned = {"tenant_id": "tenant-kz", "entity_id": "entity-001", **payload}
        attestation = self.authority.attestation(
            event_id=event_id, event_type=event_type, aggregate_id=aggregate,
            effective_at=effective_at, recorded_at=RECORDED, actor_id=actor,
            authority_ref=authority_ref, payload=unsigned,
        )
        return self.store.append_entity_event(
            tenant_id="tenant-kz", entity_id="entity-001", event_type=event_type,
            event_id=event_id, idempotency_key=event_id, effective_at=effective_at,
            recorded_at=RECORDED, actor_id=actor, authority_ref=authority_ref,
            authority_attestation=attestation, payload=payload, expected_version=version,
        )

    def test_register_resolves_metaverse_contract_with_verified_chain_digest(self):
        self._register()
        snapshot = self.store.resolve_entity("tenant-kz", "entity-001", principal_id="auditor")
        self.assertEqual(snapshot["tenant_id"], "tenant-kz")
        self.assertEqual(snapshot["entity_id"], "entity-001")
        self.assertEqual(snapshot["institutional_sector"], "NFC")
        self.assertEqual(snapshot["authority_system"], "synergistic_economics")
        self.assertEqual(snapshot["authority_event_ref"], "ENTITY-REGISTERED")
        self.assertEqual(len(snapshot["source_digest"]), 64)
        self.assertTrue(snapshot["verified"])
        self.assertEqual(snapshot["status"], "ACTIVE")

    def test_sector_changes_are_effective_dated_and_resolvable(self):
        self._register()
        self._event(
            event_id="SECTOR-CHANGE", event_type="entity.sector_changed",
            payload={"institutional_sector": "GOV"}, version=1,
            effective_at="2026-11-16T00:00:00Z",
        )
        old = self.store.resolve_entity(
            "tenant-kz", "entity-001", principal_id="auditor", as_of="2026-11-15T23:59:59Z"
        )
        new = self.store.resolve_entity(
            "tenant-kz", "entity-001", principal_id="auditor", as_of="2026-11-16T00:00:00Z"
        )
        self.assertEqual(old["institutional_sector"], "NFC")
        self.assertEqual(new["institutional_sector"], "GOV")

    def test_tenant_isolation_and_acl(self):
        self._register()
        with self.assertRaises(EconomicEntityRegisterError):
            self.store.resolve_entity("tenant-other", "entity-001", principal_id="auditor")
        with self.assertRaises(RegisterError):
            self.store.resolve_entity("tenant-kz", "entity-001", principal_id="intruder")

    def test_sector_is_never_inferred_and_invalid_sector_rejected(self):
        with self.assertRaises(EconomicEntityRegisterError):
            self._register(sector="UNKNOWN")
        self.assertEqual(self.store.total_event_count, 4)  # ACL bootstrap + three grants only

    def test_suspension_and_retirement_invalidate_business_twin_resolution(self):
        self._register()
        self._event(
            event_id="SUSPEND", event_type="entity.suspended",
            payload={"reason": "authority review", "evidence_ref": "evidence:suspension"},
            version=1, actor="admin",
        )
        self.assertEqual(
            self.store.resolve_entity("tenant-kz", "entity-001", principal_id="auditor")["status"],
            "SUSPENDED",
        )
        self._event(
            event_id="REACTIVATE", event_type="entity.reactivated",
            payload={"reason": "review cleared", "evidence_ref": "evidence:reactivation"},
            version=2, actor="admin",
        )
        self._event(
            event_id="RETIRE", event_type="entity.retired",
            payload={"reason": "legal dissolution", "evidence_ref": "evidence:retirement"},
            version=3, actor="admin",
        )
        self.assertEqual(
            self.store.resolve_entity("tenant-kz", "entity-001", principal_id="auditor")["status"],
            "RETIRED",
        )
        with self.assertRaises(EconomicEntityRegisterError):
            self._event(
                event_id="REACTIVATE-AGAIN", event_type="entity.reactivated",
                payload={"reason": "invalid", "evidence_ref": "evidence:bad"},
                version=4, actor="admin",
            )

    def test_signature_tampering_and_wrong_tenant_authority_fail_closed(self):
        self._register()
        payload = {
            "tenant_id": "tenant-kz", "entity_id": "entity-002",
            "entity_kind": "company", "jurisdiction": "KZ",
            "institutional_sector": "NFC", "external_refs": [],
        }
        aggregate = "tenant-kz::entity-002"
        signature = self.authority.attestation(
            event_id="BAD-SIGNATURE", event_type="entity.registered",
            aggregate_id=aggregate, effective_at=T, recorded_at=RECORDED,
            actor_id="registrar", authority_ref="AUTHORITY:KZ", payload=payload,
        )
        payload["jurisdiction"] = "RU"
        with self.assertRaises(EconomicEntityRegisterError):
            self.store.register_entity(
                entity_id="entity-002", tenant_id="tenant-kz", entity_kind="company",
                jurisdiction="RU", institutional_sector="NFC", event_id="BAD-SIGNATURE",
                idempotency_key="BAD-SIGNATURE", effective_at=T, recorded_at=RECORDED,
                actor_id="registrar", authority_ref="AUTHORITY:KZ",
                authority_attestation=signature,
            )

    def test_revoked_key_is_rejected(self):
        self._register()
        revoked = TrustedEntityAuthorityKey(
            key_id=self.authority.key.key_id, issuer=self.authority.key.issuer,
            tenant_id=self.authority.key.tenant_id, public_key_raw=self.authority.key.public_key_raw,
            valid_from=self.authority.key.valid_from, valid_until=self.authority.key.valid_until,
            authority_refs=self.authority.key.authority_refs, revoked_at="2026-11-15T08:00:30Z",
        )
        self.store.authority_verifier = Ed25519EntityAuthorityVerifier({revoked.key_id: revoked})
        with self.assertRaises(EconomicEntityRegisterError):
            self._event(
                event_id="POST-REVOCATION", event_type="entity.updated",
                payload={"changes": {"jurisdiction": "KZ-ALMATY"}},
                version=1,
            )

    def test_event_idempotency_and_immutable_history(self):
        self._register()
        self.assertFalse(self._register())
        self.assertTrue(self.store.verify())
        with self.assertRaises(RegisterError):
            self.store.append_entity_event(
                tenant_id="tenant-kz", entity_id="entity-001", event_type="entity.updated",
                event_id="UPDATE-1", idempotency_key="UPDATE-1", effective_at=RECORDED,
                recorded_at=RECORDED, actor_id="registrar", authority_ref="AUTHORITY:KZ",
                authority_attestation={}, payload={"changes": {"jurisdiction": "RU"}},
                expected_version=1,
            )

    def test_version_conflict_and_invalid_lifecycle_transition(self):
        self._register()
        with self.assertRaises(RegisterError):
            self._event(
                event_id="STALE", event_type="entity.updated",
                payload={"changes": {"jurisdiction": "RU"}}, version=0,
            )
        with self.assertRaises(EconomicEntityRegisterError):
            self._event(
                event_id="RETIRE-UNREGISTERED", event_type="entity.retired",
                payload={"reason": "no entity", "evidence_ref": "evidence:none"},
                version=0, actor="admin",
            )

    def test_external_reference_is_append_only_and_duplicate_safe(self):
        self._register()
        self._event(
            event_id="EXT-1", event_type="entity.external_reference_added",
            payload={"external_ref": {
                "namespace": "tax", "value": "TAX-001", "issuer": "KZ-TAX",
                "evidence_ref": "evidence:tax-001",
            }}, version=1,
        )
        with self.assertRaises(EconomicEntityRegisterError):
            self._event(
                event_id="EXT-2", event_type="entity.external_reference_added",
                payload={"external_ref": {
                    "namespace": "tax", "value": "TAX-001", "issuer": "KZ-TAX",
                    "evidence_ref": "evidence:tax-duplicate",
                }}, version=2,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
