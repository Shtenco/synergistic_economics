import unittest
from datetime import datetime, timezone

from economic_router import RouterValidationError, route_demand, score_offer


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
DEMAND = {
    "demand_id": "dem-1", "buyer_id": "buyer-1", "category": "ai_automation",
    "jurisdiction": "KZ", "status": "open", "requirements": ["crm", "russian"],
    "quantity": 1, "budget": {"amount_minor": 50000000, "currency": "RUB", "scale": 2},
    "expires_at": "2026-12-01T00:00:00Z",
}
OFFER = {
    "offer_id": "off-1", "seller_id": "seller-1", "category": "ai_automation",
    "jurisdiction": "KZ", "status": "active", "seller_verification": "verified",
    "capabilities": ["crm", "russian", "integration"], "capacity": 2,
    "price": {"amount_minor": 25000000, "currency": "RUB", "scale": 2},
    "expires_at": "2026-12-01T00:00:00Z", "evidence_refs": ["evidence:1"],
}


class EconomicRouterTests(unittest.TestCase):
    def test_compatible_offer_is_matched(self):
        match = score_offer(DEMAND, OFFER, now=NOW)
        self.assertIsNotNone(match)
        self.assertEqual(match["decision"], "candidate")
        self.assertEqual(match["authority"], "routing_only")
        self.assertEqual(match["seller_id"], "seller-1")

    def test_incompatible_jurisdiction_is_not_matched(self):
        offer = dict(OFFER, jurisdiction="RU")
        self.assertIsNone(score_offer(DEMAND, offer, now=NOW))

    def test_unverified_seller_fails_closed(self):
        offer = dict(OFFER, seller_verification="unknown")
        with self.assertRaises(RouterValidationError):
            score_offer(DEMAND, offer, now=NOW)

    def test_float_money_is_rejected(self):
        offer = dict(OFFER, price={"amount_minor": 12.5, "currency": "RUB", "scale": 2})
        with self.assertRaises(RouterValidationError):
            score_offer(DEMAND, offer, now=NOW)

    def test_expired_offer_is_not_matched(self):
        offer = dict(OFFER, expires_at="2026-11-14T11:59:59Z")
        self.assertIsNone(score_offer(DEMAND, offer, now=NOW))

    def test_over_budget_offer_is_not_matched(self):
        offer = dict(OFFER, price={"amount_minor": 50000001, "currency": "RUB", "scale": 2})
        self.assertIsNone(score_offer(DEMAND, offer, now=NOW))

    def test_missing_capability_is_not_matched(self):
        offer = dict(OFFER, capabilities=["crm"])
        self.assertIsNone(score_offer(DEMAND, offer, now=NOW))

    def test_rank_is_deterministic_and_duplicate_offer_is_removed(self):
        expensive = dict(OFFER, offer_id="off-2", seller_id="seller-2",
                         price={"amount_minor": 30000000, "currency": "RUB", "scale": 2})
        ranked = route_demand(DEMAND, [expensive, OFFER, OFFER], now=NOW)
        self.assertEqual([x["offer_id"] for x in ranked], ["off-1", "off-2"])

    def test_invalid_limit_is_rejected(self):
        with self.assertRaises(RouterValidationError):
            route_demand(DEMAND, [OFFER], now=NOW, limit=0)


if __name__ == "__main__":
    unittest.main()
