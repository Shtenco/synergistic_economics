import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]


class CanonicalEconomicEntitySnapshotSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(
            (ROOT / "canonical-economic-entity-snapshot-v1.schema.json").read_text(encoding="utf-8")
        )
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def sample(self):
        return {
            "schema_id": "synergy.economic.canonical-entity-snapshot",
            "schema_version": 1,
            "tenant_id": "tenant-kz",
            "entity_id": "economic-entity-001",
            "entity_kind": "company",
            "jurisdiction": "KZ",
            "institutional_sector": "NFC",
            "version": 7,
            "status": "ACTIVE",
            "authority_system": "synergistic_economics",
            "authority_event_ref": "entity-event:registered:v1",
            "source_digest": "a" * 64,
            "verified": True,
            "effective_as_of": "2026-11-15T09:00:00Z",
            "display_name": "Example enterprise",
            "external_refs": [{
                "namespace": "business-registry",
                "value": "BIN-001",
                "issuer": "KZ-MINISTRY",
                "evidence_ref": "evidence:registry-extract-1",
            }],
        }

    def test_valid_snapshot_matches_metaverse_resolver_contract(self):
        self.validator.validate(self.sample())

    def test_digest_must_be_sha256_hex(self):
        sample = self.sample()
        sample["source_digest"] = "not-a-digest"
        self.assertFalse(self.validator.is_valid(sample))

    def test_unverified_or_wrong_authority_snapshot_is_rejected(self):
        for change in ({"verified": False}, {"authority_system": "spatial_registry"}):
            with self.subTest(change=change):
                self.assertFalse(self.validator.is_valid(self.sample() | change))

    def test_unknown_fields_and_sector_inference_are_rejected(self):
        sample = self.sample()
        sample["owner_id"] = "must-not-be-in-this-contract"
        self.assertFalse(self.validator.is_valid(sample))
        sample = self.sample()
        sample["institutional_sector"] = "INFERRED"
        self.assertFalse(self.validator.is_valid(sample))

    def test_status_and_version_are_constrained(self):
        self.assertFalse(self.validator.is_valid(self.sample() | {"status": "UNKNOWN"}))
        self.assertFalse(self.validator.is_valid(self.sample() | {"version": 0}))


if __name__ == "__main__":
    unittest.main(verbosity=2)
