import os
import tempfile
import unittest
from datetime import datetime, timezone

from sqlite_event_repository import SQLiteEventRepository
from economic_registry import EconomicMarketplaceRegistry
from lead_radar_adapter import LeadRadarError, ingest_lead_signal, normalize_lead_signal


NOW = datetime(2026, 11, 14, 12, 0, tzinfo=timezone.utc)
SIGNAL = {
    "category": "equipment", "requirements": ["delivery", "installation"],
    "quantity": 2, "budget": {"amount_minor": 100000, "currency": "KZT", "scale": 2},
}


class LeadRadarAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.registry = EconomicMarketplaceRegistry(
            SQLiteEventRepository(os.path.join(self.tmp.name, "lead.sqlite3")))
        self.kwargs = dict(
            tenant_id="tenant-a", buyer_id="buyer-a", jurisdiction="KZ",
            consent_ref="consent:1", source_system="lead-radar",
            source_ref="source:123", demand_id="d-1",
            expires_at="2026-12-01T00:00:00Z",
            command_id="cmd-1", idempotency_key="key-1",
            actor_id="lead-radar-adapter", authority_ref="service:lead-radar",
            correlation_id="corr:1", occurred_at=NOW,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def test_consent_is_checked_before_registry_write(self):
        with self.assertRaises(LeadRadarError):
            ingest_lead_signal(self.registry, SIGNAL, consent_verifier=lambda *args: False,
                               **self.kwargs)
        self.assertEqual(self.registry.tenant_version("tenant-a"), 0)

    def test_consent_granted_lead_is_registered(self):
        receipt = ingest_lead_signal(
            self.registry, SIGNAL,
            consent_verifier=lambda ref, tenant, purpose: (
                ref == "consent:1" and tenant == "tenant-a" and purpose == "marketplace_matching"
            ),
            **self.kwargs,
        )
        self.assertEqual(receipt.result["status"], "registered")
        demand = self.registry.get_demand("tenant-a", "d-1")
        self.assertEqual(demand["source_system"], "lead-radar")
        self.assertNotIn("email", demand)

    def test_same_intent_fingerprint_is_deduplicated(self):
        verifier = lambda *args: True
        first = ingest_lead_signal(self.registry, SIGNAL, consent_verifier=verifier, **self.kwargs)
        second_kwargs = dict(self.kwargs, demand_id="d-2", command_id="cmd-2",
                             idempotency_key="key-2", correlation_id="corr:2")
        second = ingest_lead_signal(self.registry, SIGNAL, consent_verifier=verifier,
                                    **second_kwargs)
        self.assertEqual(first.result["status"], "registered")
        self.assertEqual(second.result["status"], "duplicate")
        self.assertEqual(second.result["existing_id"], "d-1")
        self.assertIsNone(self.registry.get_demand("tenant-a", "d-2"))

    def test_raw_personal_data_is_rejected_not_persisted(self):
        unsafe = dict(SIGNAL, email="person@example.test")
        with self.assertRaises(LeadRadarError):
            ingest_lead_signal(self.registry, unsafe, consent_verifier=lambda *args: True,
                               **self.kwargs)
        self.assertEqual(self.registry.tenant_version("tenant-a"), 0)

    def test_fingerprint_is_stable_under_requirement_order(self):
        left = normalize_lead_signal(SIGNAL, **{k:v for k,v in self.kwargs.items()
            if k in {"tenant_id","buyer_id","jurisdiction","consent_ref","source_system","source_ref","demand_id","expires_at"}})
        right_signal = dict(SIGNAL, requirements=["installation", "delivery", "delivery"])
        right = normalize_lead_signal(right_signal, **{k:v for k,v in self.kwargs.items()
            if k in {"tenant_id","buyer_id","jurisdiction","consent_ref","source_system","source_ref","demand_id","expires_at"}})
        self.assertEqual(left["source_fingerprint"], right["source_fingerprint"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
