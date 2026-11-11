import unittest
from datetime import datetime, timezone, timedelta

from synergy_kernel import EventStore
from real_economy_event_bridge import (
    EventBridgeConflict, EventBridgeError, InMemoryAtomicCoordinator,
    map_domain_event,
)


NOW = datetime(2026, 11, 11, 14, 0, tzinfo=timezone.utc)


def domain_event(event_id="evt-1", key="key-1", version=1, quantity="5"):
    return {
        "event_id": event_id,
        "event_type": "inventory.quantity_reserved",
        "aggregate_id": "lot-1",
        "aggregate_version": version,
        "idempotency_key": key,
        "payload": {"quantity": quantity, "unit": "kg"},
    }


def transition(state):
    candidate = dict(state)
    candidate["reserved"] = candidate.get("reserved", 0) + 5
    return candidate, candidate["reserved"], [domain_event()]


class CanonicalMappingTests(unittest.TestCase):
    def map(self, event=None, **kwargs):
        defaults = dict(
            aggregate_type="inventory_lot", actor_id="operator-1",
            authority_ref="mandate-1", command_id="cmd-1",
            correlation_id="corr-1", occurred_at=NOW, recorded_at=NOW,
        )
        defaults.update(kwargs)
        return map_domain_event(event or domain_event(), **defaults)

    def test_mapping_preserves_identity_and_adds_canonical_metadata(self):
        mapped = self.map()
        self.assertEqual(mapped.event_id, "evt-1")
        self.assertEqual(mapped.aggregate_id, "lot-1")
        self.assertEqual(mapped.aggregate_version, 1)
        self.assertEqual(mapped.actor_id, "operator-1")
        self.assertEqual(mapped.authority_ref, "mandate-1")
        self.assertEqual(mapped.schema_version, "synergy.event.v1")
        self.assertEqual(len(mapped.payload_digest), 64)

    def test_payload_digest_changes_when_domain_fact_changes(self):
        a = self.map(domain_event(quantity="5"))
        b = self.map(domain_event(quantity="6"))
        self.assertNotEqual(a.payload_digest, b.payload_digest)

    def test_naive_timestamps_are_rejected(self):
        with self.assertRaises(EventBridgeError):
            self.map(occurred_at=datetime(2026, 11, 11, 14, 0))

    def test_non_utc_timestamp_is_rejected(self):
        with self.assertRaises(EventBridgeError):
            self.map(recorded_at=NOW.astimezone(timezone(timedelta(hours=5))))

    def test_missing_actor_or_authority_is_rejected(self):
        with self.assertRaises(EventBridgeError):
            self.map(actor_id="")
        with self.assertRaises(EventBridgeError):
            self.map(authority_ref="")

    def test_non_json_payload_is_rejected(self):
        bad = domain_event()
        bad["payload"] = {"quantity": object()}
        with self.assertRaises(EventBridgeError):
            self.map(bad)


class AtomicCoordinatorTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore()
        self.coordinator = InMemoryAtomicCoordinator({"reserved": 0}, self.store)

    def execute(self, *, transition_fn=transition, **overrides):
        args = dict(
            command_id="cmd-1", idempotency_key="request-key-1",
            request={"lot_id": "lot-1", "quantity": "5"},
            aggregate_type="inventory_lot", aggregate_id="lot-1",
            expected_version=0, actor_id="operator-1",
            authority_ref="mandate-1", correlation_id="corr-1",
            occurred_at=NOW, recorded_at=NOW, transition=transition_fn,
        )
        args.update(overrides)
        return self.coordinator.execute(**args)

    def test_success_commits_state_and_one_canonical_event(self):
        receipt = self.execute()
        self.assertEqual(self.coordinator.state["reserved"], 5)
        self.assertEqual(self.coordinator.aggregate_version("inventory_lot", "lot-1"), 1)
        self.assertEqual(len(self.store.replay()), 1)
        self.assertEqual(receipt.events[0].aggregate_version, 1)
        self.assertEqual(self.store.replay()[0].sequence, 1)

    def test_same_command_retry_returns_original_receipt_without_second_event(self):
        first = self.execute()
        second = self.execute()
        self.assertEqual(first, second)
        self.assertEqual(len(self.store.replay()), 1)
        self.assertEqual(self.coordinator.state["reserved"], 5)

    def test_same_key_with_different_request_is_rejected(self):
        self.execute()
        with self.assertRaises(EventBridgeConflict):
            self.execute(request={"lot_id": "lot-1", "quantity": "9"})

    def test_stale_aggregate_version_is_rejected(self):
        self.execute()
        with self.assertRaises(EventBridgeConflict):
            self.execute(command_id="cmd-2", idempotency_key="key-2",
                         expected_version=0)

    def test_idempotency_key_is_global_across_command_ids(self):
        self.execute()
        with self.assertRaises(EventBridgeConflict):
            self.execute(command_id="cmd-2")

    def test_failure_after_event_append_rolls_back_store_and_state(self):
        with self.assertRaises(RuntimeError):
            self.execute(fail_after_event_append=1)
        self.assertEqual(self.coordinator.state, {"reserved": 0})
        self.assertEqual(len(self.store.replay()), 0)
        self.assertEqual(self.coordinator.aggregate_version("inventory_lot", "lot-1"), 0)

    def test_duplicate_event_id_failure_rolls_back_state(self):
        self.store.append("evt-1", "already.exists", {}, "existing-key")
        with self.assertRaises(Exception):
            self.execute()
        self.assertEqual(self.coordinator.state, {"reserved": 0})
        self.assertEqual(len(self.store.replay()), 1)

    def test_multi_event_command_uses_ordinals_and_single_aggregate_version(self):
        def multi(state):
            candidate = dict(state)
            candidate["reserved"] = 5
            second = domain_event("evt-2", "key-2", 1, "5")
            return candidate, "ok", [domain_event(), second]
        receipt = self.execute(transition_fn=multi)
        self.assertEqual([e.event_ordinal for e in receipt.events], [0, 1])
        self.assertEqual([e.aggregate_version for e in receipt.events], [1, 1])
        self.assertEqual(len(self.store.replay()), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
