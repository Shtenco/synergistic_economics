import unittest
from datetime import datetime, timezone

from economic_router import RouterValidationError, route_demand, score_offer


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
DEMAND = {
    "schema_id": "synergy.economic-router.demand", "schema_version": 1,
    "demand_id": "dem-1", "buyer_id": "buyer-1", "tenant_id": "tenant-1",
    "consent_ref": "consent:1", "category": "ai_automation", "jurisdiction": "KZ",
    "status": "open", "requirements": ["crm", "russian"],
    "quantity": 1, "budget": {"amount_minor": 50000000, "currency": "RUB", "scale": 2},
    "expires_at": "2026-12-01T00:00:00Z",
}
OFFER = {
    "schema_id": "synergy.economic-router.offer", "schema_version": 1,
    "offer_id": "off-1", "seller_id": "seller-1", "tenant_id": "tenant-1",
    "category": "ai_automation", "jurisdiction": "KZ", "status": "active",
    "seller_verification": "verified", "capabilities": ["crm", "russian", "integration"],
    "capacity": 2, "price": {"amount_minor": 25000000, "currency": "RUB", "scale": 2},
    "expires_at": "2026-12-01T00:00:00Z", "evidence_refs": ["evidence:1"],
}


class EconomicRouterTests(unittest.TestCase):
    def test_compatible_offer_is_matched_and_explained(self):
        match = score_offer(DEMAND, OFFER, now=NOW)
        self.assertIsNotNone(match)
        self.assertEqual(match["decision"], "candidate")
        self.assertEqual(match["authority"], "routing_only")
        self.assertEqual(match["seller_id"], "seller-1")
        self.assertEqual(match["tenant_id"], "tenant-1")

    def test_incompatible_jurisdiction_is_not_matched(self):
        self.assertIsNone(score_offer(DEMAND, dict(OFFER, jurisdiction="RU"), now=NOW))

    def test_cross_tenant_offer_is_not_matched(self):
        self.assertIsNone(score_offer(DEMAND, dict(OFFER, tenant_id="other"), now=NOW))

    def test_unverified_seller_fails_closed(self):
        with self.assertRaises(RouterValidationError):
            score_offer(DEMAND, dict(OFFER, seller_verification="unknown"), now=NOW)

    def test_float_money_is_rejected(self):
        offer = dict(OFFER, price={"amount_minor": 12.5, "currency": "RUB", "scale": 2})
        with self.assertRaises(RouterValidationError):
            score_offer(DEMAND, offer, now=NOW)

    def test_expired_offer_is_not_matched(self):
        self.assertIsNone(score_offer(DEMAND, dict(OFFER, expires_at="2026-11-14T11:59:59Z"), now=NOW))

    def test_over_budget_offer_is_not_matched(self):
        offer = dict(OFFER, price={"amount_minor": 50000001, "currency": "RUB", "scale": 2})
        self.assertIsNone(score_offer(DEMAND, offer, now=NOW))

    def test_missing_capability_is_not_matched(self):
        self.assertIsNone(score_offer(DEMAND, dict(OFFER, capabilities=["crm"]), now=NOW))

    def test_duplicate_requirements_and_unknown_fields_are_rejected(self):
        with self.assertRaises(RouterValidationError):
            score_offer(dict(DEMAND, requirements=["crm", "crm"]), OFFER, now=NOW)
        with self.assertRaises(RouterValidationError):
            score_offer(dict(DEMAND, email="private@example.test"), OFFER, now=NOW)

    def test_rank_is_deterministic_and_duplicate_offer_is_removed(self):
        expensive = dict(OFFER, offer_id="off-2", seller_id="seller-2",
                         price={"amount_minor": 30000000, "currency": "RUB", "scale": 2})
        ranked = route_demand(DEMAND, [expensive, OFFER, OFFER], now=NOW)
        self.assertEqual([x["offer_id"] for x in ranked], ["off-1", "off-2"])

    def test_offer_deduplication_is_tenant_scoped(self):
        foreign = dict(OFFER, tenant_id="tenant-2")
        ranked = route_demand(DEMAND, [foreign, OFFER], now=NOW)
        self.assertEqual([item["offer_id"] for item in ranked], ["off-1"])

    def test_match_ids_are_tenant_scoped(self):
        other_demand = dict(DEMAND, tenant_id="tenant-2")
        other_offer = dict(OFFER, tenant_id="tenant-2")
        self.assertNotEqual(score_offer(DEMAND, OFFER, now=NOW)["match_id"],
                            score_offer(other_demand, other_offer, now=NOW)["match_id"])

    def test_invalid_limit_and_naive_clock_are_rejected(self):
        with self.assertRaises(RouterValidationError):
            route_demand(DEMAND, [OFFER], now=NOW, limit=0)
        with self.assertRaises(RouterValidationError):
            score_offer(DEMAND, OFFER, now=datetime(2026, 11, 14, 12, 0))


if __name__ == "__main__":
    unittest.main(verbosity=2)
