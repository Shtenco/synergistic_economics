import os
import tempfile
import unittest
from datetime import datetime, timezone

from real_economy_event_bridge import EventBridgeConflict
from sqlite_event_repository import SQLiteEventRepository
from economic_registry import EconomicMarketplaceRegistry, RegistryError


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


class EconomicRegistryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "economic.sqlite3")
        self.repo = SQLiteEventRepository(self.path)
        self.registry = EconomicMarketplaceRegistry(self.repo)

    def tearDown(self):
        self.tmp.cleanup()

    def register_demand(self, demand=None, key="key-1", command="cmd-1"):
        return self.registry.register_demand(
            demand or DEMAND, command_id=command, idempotency_key=key,
            actor_id="actor-1", authority_ref="mandate:1",
            correlation_id="corr:1", occurred_at=NOW,
        )

    def register_offer(self, offer=None, key="key-2", command="cmd-2"):
        return self.registry.register_offer(
            offer or OFFER, command_id=command, idempotency_key=key,
            actor_id="actor-1", authority_ref="mandate:1",
            correlation_id="corr:2", occurred_at=NOW,
        )

    def test_demand_and_offer_survive_repository_restart(self):
        self.register_demand()
        self.register_offer()
        restarted = EconomicMarketplaceRegistry(SQLiteEventRepository(self.path))
        self.assertEqual(restarted.get_demand("tenant-a", "d-1"), DEMAND)
        self.assertEqual(restarted.get_offer("tenant-a", "o-1"), OFFER)
        self.assertEqual(restarted.tenant_version("tenant-a"), 2)

    def test_tenant_isolation(self):
        self.register_demand()
        self.assertIsNone(self.registry.get_demand("tenant-b", "d-1"))
        self.assertEqual(self.registry.list_open_demands("tenant-b"), ())

    def test_same_idempotency_key_returns_original_receipt(self):
        first = self.register_demand()
        second = self.register_demand()
        self.assertEqual(first, second)
        self.assertEqual(self.registry.tenant_version("tenant-a"), 1)

    def test_reused_idempotency_key_with_changed_request_conflicts(self):
        self.register_demand()
        changed = dict(DEMAND, category="different")
        with self.assertRaises(EventBridgeConflict):
            self.register_demand(changed)

    def test_duplicate_demand_id_is_rejected_without_mutation(self):
        self.register_demand()
        duplicate = dict(DEMAND, buyer_id="b-2")
        with self.assertRaises(RegistryError):
            self.register_demand(duplicate, key="key-duplicate", command="cmd-duplicate")
        self.assertEqual(self.registry.tenant_version("tenant-a"), 1)

    def test_duplicate_source_fingerprint_is_audited_not_reinserted(self):
        first = dict(DEMAND, source_fingerprint="fingerprint-1")
        self.registry.register_demand(first, command_id="cmd-1", idempotency_key="key-1",
                                      actor_id="actor-1", authority_ref="mandate:1",
                                      correlation_id="corr:1", occurred_at=NOW)
        second = dict(DEMAND, demand_id="d-2", source_fingerprint="fingerprint-1")
        receipt = self.registry.register_demand(second, command_id="cmd-2", idempotency_key="key-2",
                                                actor_id="actor-1", authority_ref="mandate:1",
                                                correlation_id="corr:2", occurred_at=NOW)
        self.assertEqual(receipt.result["status"], "duplicate")
        self.assertIsNone(self.registry.get_demand("tenant-a", "d-2"))
        self.assertEqual(len(self.registry.list_open_demands("tenant-a")), 1)

    def test_offer_registration_and_list(self):
        self.register_offer()
        self.assertEqual(self.registry.list_active_offers("tenant-a"), (OFFER,))

    def test_float_money_is_rejected_before_persistence(self):
        invalid = dict(OFFER, price={"amount_minor": 1.5, "currency": "KZT", "scale": 2})
        with self.assertRaises(RegistryError):
            self.register_offer(invalid)
        self.assertEqual(self.registry.tenant_version("tenant-a"), 0)

    def test_event_and_outbox_are_committed_atomically(self):
        self.register_demand()
        self.assertEqual(self.repo.audit(), {"events": 1, "commands": 1, "outbox": 1})
        pending = self.repo.pending_outbox()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["envelope"]["event_type"], "marketplace.demand.registered")

    def test_tenant_scoped_idempotency_keys_do_not_collide(self):
        demand_b = dict(DEMAND, tenant_id="tenant-b")
        self.register_demand()
        self.registry.register_demand(demand_b, command_id="cmd-1", idempotency_key="key-1",
                                      actor_id="actor-1", authority_ref="mandate:1",
                                      correlation_id="corr-b", occurred_at=NOW)
        self.assertEqual(self.registry.tenant_version("tenant-a"), 1)
        self.assertEqual(self.registry.tenant_version("tenant-b"), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
