import os
import tempfile
import unittest
from datetime import datetime, timezone

from sqlite_event_repository import SQLiteEventRepository
from economic_registry import EconomicMarketplaceRegistry
from economic_marketplace_service import EconomicMarketplaceService, MarketplaceQueryError


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
DEMAND = {
    "schema_id": "synergy.economic-router.demand", "schema_version": 1,
    "demand_id": "d-1", "buyer_id": "b-1", "tenant_id": "tenant-a",
    "consent_ref": "consent:1", "category": "equipment", "jurisdiction": "KZ",
    "status": "open", "requirements": ["delivery"], "quantity": 1,
    "budget": {"amount_minor": 100000, "currency": "KZT", "scale": 2},
    "expires_at": "2026-12-01T00:00:00Z",
}
OFFER = {
    "schema_id": "synergy.economic-router.offer", "schema_version": 1,
    "offer_id": "o-1", "seller_id": "s-1", "tenant_id": "tenant-a",
    "category": "equipment", "jurisdiction": "KZ", "status": "active",
    "seller_verification": "verified", "capabilities": ["delivery"],
    "capacity": 1, "price": {"amount_minor": 90000, "currency": "KZT", "scale": 2},
    "expires_at": "2026-12-01T00:00:00Z",
}


class MarketplaceServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.repo = SQLiteEventRepository(os.path.join(self.tmp.name, "marketplace.sqlite3"))
        self.registry = EconomicMarketplaceRegistry(self.repo)
        self.service = EconomicMarketplaceService(self.registry)
        self.registry.register_demand(
            DEMAND, command_id="cmd-demand", idempotency_key="key-demand",
            actor_id="test", authority_ref="test:mandate", correlation_id="corr-demand",
            occurred_at=NOW,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def register_offer(self, offer, index):
        return self.registry.register_offer(
            offer, command_id=f"cmd-offer-{index}", idempotency_key=f"key-offer-{index}",
            actor_id="test", authority_ref="test:mandate", correlation_id=f"corr-offer-{index}",
            occurred_at=NOW,
        )

    def test_discovers_and_ranks_tenant_offers(self):
        self.register_offer(OFFER, 1)
        cheaper = dict(OFFER, offer_id="o-2", seller_id="s-2",
                       price={"amount_minor": 70000, "currency": "KZT", "scale": 2})
        self.register_offer(cheaper, 2)
        result = self.service.discover_matches("tenant-a", "d-1", now=NOW)
        self.assertEqual(result["candidate_count"], 2)
        self.assertEqual(result["matches"][0]["offer_id"], "o-2")
        self.assertEqual(result["side_effects"], "none")
        self.assertEqual(result["authority"], "routing_only")

    def test_search_is_read_only(self):
        self.register_offer(OFFER, 1)
        before = self.registry.tenant_version("tenant-a")
        self.service.discover_matches("tenant-a", "d-1", now=NOW)
        self.assertEqual(self.registry.tenant_version("tenant-a"), before)
        self.assertEqual(self.repo.audit()["events"], 2)

    def test_foreign_tenant_demand_is_not_discoverable(self):
        with self.assertRaises(MarketplaceQueryError):
            self.service.discover_matches("tenant-b", "d-1", now=NOW)

    def test_expired_offer_is_not_returned(self):
        expired = dict(OFFER, expires_at="2026-11-14T11:59:59Z")
        self.register_offer(expired, 1)
        result = self.service.discover_matches("tenant-a", "d-1", now=NOW)
        self.assertEqual(result["matches"], [])

    def test_limit_is_bounded(self):
        with self.assertRaises(MarketplaceQueryError):
            self.service.discover_matches("tenant-a", "d-1", now=NOW, limit=101)


if __name__ == "__main__":
    unittest.main(verbosity=2)
