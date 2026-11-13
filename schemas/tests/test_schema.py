import json
import sys
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from validate_records import validate_records


class CanonicalSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads((ROOT / "synergy-economy.schema.json").read_text(encoding="utf-8"))
        cls.examples = json.loads((ROOT / "examples" / "canonical_records.json").read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(cls.schema, format_checker=FormatChecker())

    def test_native_register_event_envelope_schema_is_valid(self):
        schema_path = ROOT / "native-register-event-envelope-v1.schema.json"
        contract = json.loads(schema_path.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(contract)
        sample = {
            "schema_id": "synergy.native-register-event", "schema_version": 1,
            "register_id": "labour", "event_type": "engagement.offered",
            "effective_at": "2026-11-13T07:00:00Z", "recorded_at": "2026-11-13T07:00:00Z",
            "actor_id": "coordinator", "authority_ref": "AUTH:CONTRACT-1",
            "idempotency_key": "LABOUR-EVENT-1", "payload": {"planned_hours": "2"}
        }
        Draft202012Validator(contract, format_checker=FormatChecker()).validate(sample)
        validator = Draft202012Validator(contract, format_checker=FormatChecker())
        with self.assertRaises(Exception):
            validator.validate(dict(sample, schema_version=2))
        with self.assertRaises(Exception):
            validator.validate(dict(sample, effective_at="2026-11-13T10:00:00+03:00"))
        with self.assertRaises(Exception):
            validator.validate(dict(sample, stock_flow_movements=[], no_stock_flow_effect="invalid dual declaration"))
    def test_schema_is_valid_draft_2020_12(self):
        self.assertEqual(self.schema["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_all_canonical_examples_validate(self):
        self.assertGreater(len(self.examples["records"]), 0)
        for record in self.examples["records"]:
            with self.subTest(record_id=record["id"]):
                self.validator.validate(record)

    def test_examples_pass_cross_record_validation(self):
        self.assertEqual(validate_records(self.examples["records"], self.schema), [])

    def test_unknown_fields_are_rejected(self):
        person = dict(self.examples["records"][0])
        person["unregisteredEconomicPower"] = True
        self.assertFalse(self.validator.is_valid(person))

    def test_invalid_sci_value_is_rejected(self):
        contribution = next(x for x in self.examples["records"] if x["recordType"] == "contribution")
        invalid = dict(contribution)
        invalid["sciScore"] = -1
        self.assertFalse(self.validator.is_valid(invalid))

    def test_unknown_record_type_is_rejected(self):
        person = dict(self.examples["records"][0])
        person["recordType"] = "universal_human_value_score"
        self.assertFalse(self.validator.is_valid(person))

    def test_title_claim_requires_explicit_share(self):
        claim = {
            "id": "claim:test-1", "schemaVersion": "1.0.0", "recordType": "ownership_claim",
            "createdAt": "2026-11-09T12:00:00Z", "provenance": {"sourceType": "unknown"},
            "assetId": "asset:tractor-001", "claimantEntityId": "person:member-001",
            "rightType": "legal_title", "legalBasisRef": "document:test",
            "verificationStatus": "document_checked"
        }
        self.assertFalse(self.validator.is_valid(claim))

    def test_non_object_record_is_reported_without_crashing(self):
        issues = validate_records([None, "not-a-record"], self.schema)
        self.assertTrue(any("expected an object" in issue for issue in issues))

    def test_non_string_reference_is_reported_without_crashing(self):
        records = [dict(x) for x in self.examples["records"]]
        contribution = next(x for x in records if x["recordType"] == "contribution")
        contribution["projectId"] = {"bad": "reference"}
        issues = validate_records(records, self.schema)
        self.assertTrue(any("reference must be a string" in issue for issue in issues))

    def test_malformed_ownership_interval_is_reported_without_crashing(self):
        records = [dict(x) for x in self.examples["records"]]
        records.append({
            "id": "claim:malformed-time", "schemaVersion": "1.0.0",
            "recordType": "ownership_claim", "createdAt": "2026-11-09T12:00:00Z",
            "provenance": {"sourceType": "public_registry"},
            "assetId": "asset:tractor-001", "claimantEntityId": "person:member-001",
            "rightType": "legal_title", "share": 0.5,
            "legalBasisRef": "registry:claim",
            "verificationStatus": "registry_confirmed", "validFrom": "not-a-date"
        })
        issues = validate_records(records, self.schema)
        self.assertTrue(any("invalid ownership-claim time interval" in issue for issue in issues))

    def test_missing_reference_is_reported(self):
        records = [dict(x) for x in self.examples["records"]]
        contribution = next(x for x in records if x["recordType"] == "contribution")
        contribution["projectId"] = "project:does-not-exist"
        issues = validate_records(records, self.schema)
        self.assertTrue(any("unresolved reference" in issue for issue in issues))

    def test_overlapping_verified_title_shares_cannot_exceed_one(self):
        records = [dict(x) for x in self.examples["records"]]
        base = {
            "schemaVersion": "1.0.0", "recordType": "ownership_claim",
            "createdAt": "2026-11-09T12:00:00Z", "provenance": {"sourceType": "public_registry"},
            "assetId": "asset:tractor-001", "claimantEntityId": "person:member-001",
            "rightType": "legal_title", "legalBasisRef": "registry:claim",
            "verificationStatus": "registry_confirmed", "share": 0.6
        }
        records.extend([dict(base, id="claim:test-a"), dict(base, id="claim:test-b", share=0.5)])
        issues = validate_records(records, self.schema)
        self.assertTrue(any("sum to" in issue and "> 1" in issue for issue in issues))

    def test_event_subject_reference_type_is_checked(self):
        records = [dict(x) for x in self.examples["records"]]
        event = next(x for x in records if x["recordType"] == "economic_event")
        event["subjectEntityIds"] = ["asset:tractor-001"]
        issues = validate_records(records, self.schema)
        self.assertTrue(any("expected" in issue and "subjectEntityIds" in issue for issue in issues))

    def test_duplicate_event_idempotency_key_is_reported(self):
        records = [dict(x) for x in self.examples["records"]]
        event = next(x for x in records if x["recordType"] == "economic_event")
        duplicate = dict(event, id="event:shipment-duplicate")
        records.append(duplicate)
        issues = validate_records(records, self.schema)
        self.assertTrue(any("duplicate key" in issue for issue in issues))


if __name__ == "__main__":
    unittest.main()
