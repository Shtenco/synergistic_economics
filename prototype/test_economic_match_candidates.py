import os
import tempfile
import unittest
from datetime import datetime, timezone

from sqlite_event_repository import SQLiteEventRepository
from real_economy_event_bridge import EventBridgeConflict
from economic_registry import EconomicMarketplaceRegistry, RegistryError
from economic_match_candidates import MatchCandidateStore


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


class MatchCandidateStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "marketplace.sqlite3")
        self.repo = SQLiteEventRepository(self.path)
        self.registry = EconomicMarketplaceRegistry(self.repo)
        self.store = MatchCandidateStore(self.registry)
        self.registry.register_demand(
            DEMAND, command_id="cmd-demand", idempotency_key="key-demand",
            actor_id="test", authority_ref="test:mandate", correlation_id="corr-demand",
            occurred_at=NOW,
        )
        self.registry.register_offer(
            OFFER, command_id="cmd-offer", idempotency_key="key-offer",
            actor_id="test", authority_ref="test:mandate", correlation_id="corr-offer",
            occurred_at=NOW,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def persist(self, **overrides):
        args = {
            "command_id": "cmd-candidate", "idempotency_key": "key-candidate",
            "actor_id": "test", "authority_ref": "test:mandate",
            "correlation_id": "corr-candidate", "occurred_at": NOW,
        }
        args.update(overrides)
        return self.store.persist_candidate("tenant-a", "d-1", "o-1", **args)

    def test_candidate_is_durable_and_tenant_scoped(self):
        receipt = self.persist()
        candidate_id = receipt.result["candidate_id"]
        restarted = MatchCandidateStore(
            EconomicMarketplaceRegistry(SQLiteEventRepository(self.path))
        )
        candidate = restarted.get_candidate("tenant-a", candidate_id)
        self.assertEqual(candidate["status"], "active")
        self.assertEqual(candidate["freshness"], "current")
        self.assertIsNone(restarted.get_candidate("tenant-b", candidate_id))
        self.assertEqual(restarted.repository.audit(),
                         {"events": 3, "commands": 3, "outbox": 3})

    def test_same_command_retry_returns_original_receipt(self):
        first = self.persist()
        second = self.persist()
        self.assertEqual(first, second)
        self.assertEqual(self.registry.tenant_version("tenant-a"), 3)

    def test_changed_request_with_same_idempotency_key_conflicts(self):
        self.persist()
        with self.assertRaises(EventBridgeConflict):
            self.store.persist_candidate(
                "tenant-a", "d-1", "o-1", command_id="cmd-candidate",
                idempotency_key="key-candidate", actor_id="other",
                authority_ref="test:mandate", correlation_id="corr-candidate",
                occurred_at=NOW,
            )

    def test_withdrawal_is_persisted_and_not_reversible_by_listing(self):
        receipt = self.persist()
        candidate_id = receipt.result["candidate_id"]
        self.store.withdraw_candidate(
            "tenant-a", candidate_id, command_id="cmd-withdraw",
            idempotency_key="key-withdraw", actor_id="test",
            authority_ref="test:mandate", correlation_id="corr-withdraw",
            occurred_at=NOW,
        )
        candidate = self.store.get_candidate("tenant-a", candidate_id)
        self.assertEqual(candidate["status"], "withdrawn")
        self.assertEqual(candidate["effective_status"], "withdrawn")

    def test_stale_transition_is_explicit_and_durable(self):
        receipt = self.persist()
        candidate_id = receipt.result["candidate_id"]
        self.store.mark_stale(
            "tenant-a", candidate_id, command_id="cmd-stale",
            idempotency_key="key-stale", actor_id="test",
            authority_ref="test:mandate", correlation_id="corr-stale",
            occurred_at=NOW,
        )
        self.assertEqual(self.store.get_candidate("tenant-a", candidate_id)["status"], "stale")


    def test_withdrawn_candidate_cannot_be_silently_reactivated(self):
        receipt = self.persist()
        candidate_id = receipt.result["candidate_id"]
        self.store.withdraw_candidate(
            "tenant-a", candidate_id, command_id="cmd-withdraw",
            idempotency_key="key-withdraw", actor_id="test",
            authority_ref="test:mandate", correlation_id="corr-withdraw",
            occurred_at=NOW,
        )
        with self.assertRaises(RegistryError):
            self.store.persist_candidate(
                "tenant-a", "d-1", "o-1", command_id="cmd-reactivate",
                idempotency_key="key-reactivate", actor_id="test",
                authority_ref="test:mandate", correlation_id="corr-reactivate",
                occurred_at=NOW,
            )

    def test_incompatible_pair_cannot_be_persisted(self):
        self.registry.register_offer(
            dict(OFFER, offer_id="o-2", price={"amount_minor": 200000, "currency": "KZT", "scale": 2}),
            command_id="cmd-offer-2", idempotency_key="key-offer-2",
            actor_id="test", authority_ref="test:mandate", correlation_id="corr-offer-2",
            occurred_at=NOW,
        )
        with self.assertRaises(RegistryError):
            self.store.persist_candidate(
                "tenant-a", "d-1", "o-2", command_id="cmd-bad",
                idempotency_key="key-bad", actor_id="test",
                authority_ref="test:mandate", correlation_id="corr-bad",
                occurred_at=NOW,
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
