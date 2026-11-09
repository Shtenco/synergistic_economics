import json
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "synergy-economy.schema.json"
EXAMPLES_PATH = ROOT / "examples" / "canonical_records.json"


class CanonicalSchemaTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
        cls.examples = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(cls.schema)
        cls.validator = Draft202012Validator(
            cls.schema, format_checker=FormatChecker()
        )

    def test_schema_is_valid_draft_2020_12(self):
        self.assertEqual(
            self.schema["$schema"],
            "https://json-schema.org/draft/2020-12/schema",
        )

    def test_all_canonical_examples_validate(self):
        self.assertGreater(len(self.examples["records"]), 0)
        for record in self.examples["records"]:
            with self.subTest(record_id=record["id"]):
                self.validator.validate(record)

    def test_unknown_fields_are_rejected(self):
        person = dict(self.examples["records"][0])
        person["unregisteredEconomicPower"] = True
        self.assertFalse(self.validator.is_valid(person))

    def test_invalid_sci_value_is_rejected(self):
        contribution = next(
            item for item in self.examples["records"]
            if item["recordType"] == "contribution"
        )
        invalid = dict(contribution)
        invalid["sciScore"] = -1
        self.assertFalse(self.validator.is_valid(invalid))

    def test_unknown_record_type_is_rejected(self):
        record = dict(self.examples["records"][0])
        record["recordType"] = "universal_human_value_score"
        self.assertFalse(self.validator.is_valid(record))


if __name__ == "__main__":
    unittest.main()
