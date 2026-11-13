import json
from pathlib import Path
import unittest

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8"))


class EconomicRouterSchemaTests(unittest.TestCase):
    def setUp(self):
        self.demand_schema = load("economic-router-demand-v1.schema.json")
        self.offer_schema = load("economic-router-offer-v1.schema.json")
        Draft202012Validator.check_schema(self.demand_schema)
        Draft202012Validator.check_schema(self.offer_schema)
        self.demand_validator = Draft202012Validator(self.demand_schema, format_checker=FormatChecker())
        self.offer_validator = Draft202012Validator(self.offer_schema, format_checker=FormatChecker())

    def test_valid_demand_and_offer(self):
        demand = {
            "schema_id": "synergy.economic-router.demand", "schema_version": 1,
            "demand_id": "d-1", "buyer_id": "b-1", "tenant_id": "t-1",
            "consent_ref": "consent:1", "category": "equipment", "jurisdiction": "KZ",
            "status": "open", "requirements": ["delivery"], "quantity": 1,
            "budget": {"amount_minor": 100000, "currency": "KZT", "scale": 2},
            "expires_at": "2026-12-01T00:00:00Z"
        }
        offer = {
            "schema_id": "synergy.economic-router.offer", "schema_version": 1,
            "offer_id": "o-1", "seller_id": "s-1", "tenant_id": "t-1",
            "category": "equipment", "jurisdiction": "KZ", "status": "active",
            "seller_verification": "verified", "capabilities": ["delivery"],
            "capacity": 1, "price": {"amount_minor": 90000, "currency": "KZT", "scale": 2},
            "expires_at": "2026-12-01T00:00:00Z"
        }
        self.demand_validator.validate(demand)
        self.offer_validator.validate(offer)

    def test_demand_requires_tenant_and_consent_references(self):
        demand = {
            "schema_id": "synergy.economic-router.demand", "schema_version": 1,
            "demand_id": "d-1", "buyer_id": "b-1", "category": "equipment",
            "jurisdiction": "KZ", "status": "open", "requirements": [],
            "quantity": 1, "budget": {"amount_minor": 100, "currency": "KZT", "scale": 2},
            "expires_at": "2026-12-01T00:00:00Z"
        }
        self.assertTrue(list(self.demand_validator.iter_errors(demand)))

    def test_money_rejects_float_minor_units(self):
        offer = {
            "schema_id": "synergy.economic-router.offer", "schema_version": 1,
            "offer_id": "o-1", "seller_id": "s-1", "tenant_id": "t-1",
            "category": "equipment", "jurisdiction": "KZ", "status": "active",
            "seller_verification": "verified", "capabilities": ["delivery"],
            "capacity": 1, "price": {"amount_minor": 1.25, "currency": "KZT", "scale": 2},
            "expires_at": "2026-12-01T00:00:00Z"
        }
        self.assertTrue(list(self.offer_validator.iter_errors(offer)))


if __name__ == "__main__":
    unittest.main()
