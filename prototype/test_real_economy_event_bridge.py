import unittest
from threading import Thread
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


    def test_multi_event_failure_after_second_append_rolls_back_everything(self):
        def multi(state):
            candidate = dict(state)
            candidate["reserved"] = 10
            return candidate, "ok", [
                domain_event("evt-a", "key-a", 1, "5"),
                domain_event("evt-b", "key-b", 1, "5"),
            ]
        with self.assertRaises(RuntimeError):
            self.execute(transition_fn=multi, fail_after_event_append=2)
        self.assertEqual(self.coordinator.state, {"reserved": 0})
        self.assertEqual(self.coordinator.aggregate_version("inventory_lot", "lot-1"), 0)
        self.assertEqual(self.store.replay(), ())

        # Failed attempts do not leave an idempotency receipt: the same command
        # can be retried after the transient append failure has been removed.
        receipt = self.execute(transition_fn=multi)
        self.assertEqual(self.coordinator.state, {"reserved": 10})
        self.assertEqual(len(receipt.events), 2)
        self.assertEqual(len(self.store.replay()), 2)

    def test_transition_exception_leaves_state_log_and_version_unchanged(self):
        def broken(state):
            state["reserved"] = 999
            raise RuntimeError("transition failed")
        with self.assertRaises(RuntimeError):
            self.execute(transition_fn=broken)
        self.assertEqual(self.coordinator.state, {"reserved": 0})
        self.assertEqual(self.coordinator.aggregate_version("inventory_lot", "lot-1"), 0)
        self.assertEqual(self.store.replay(), ())
        self.assertEqual(self.execute().result, 5)

    def test_expected_version_rejects_bool_negative_and_float(self):
        for invalid in (True, False, -1, 0.0, 1.5):
            with self.subTest(value=invalid):
                with self.assertRaises(EventBridgeError):
                    self.execute(expected_version=invalid)
        self.assertEqual(self.store.replay(), ())
        self.assertEqual(self.coordinator.state, {"reserved": 0})

    def test_fault_injection_index_must_be_positive_integer(self):
        for invalid in (True, False, 0, -1, 1.0):
            with self.subTest(value=invalid):
                with self.assertRaises(EventBridgeError):
                    self.execute(fail_after_event_append=invalid)
        self.assertEqual(self.store.replay(), ())

    def test_concurrent_commands_at_same_version_allow_exactly_one_winner(self):
        outcomes = []
        def worker(command_id):
            def concurrent_transition(state):
                candidate = dict(state)
                candidate["reserved"] = candidate.get("reserved", 0) + 5
                event = domain_event(
                    event_id="evt-" + command_id,
                    key="event-" + command_id,
                    version=1,
                )
                return candidate, command_id, [event]
            try:
                receipt = self.coordinator.execute(
                    command_id=command_id,
                    idempotency_key="request-" + command_id,
                    request={"command": command_id},
                    aggregate_type="inventory_lot",
                    aggregate_id="lot-1",
                    expected_version=0,
                    actor_id="operator-1",
                    authority_ref="mandate-1",
                    correlation_id="corr-" + command_id,
                    occurred_at=NOW,
                    recorded_at=NOW,
                    transition=concurrent_transition,
                )
                outcomes.append(("committed", receipt.command_id))
            except EventBridgeConflict:
                outcomes.append(("conflict", command_id))

        threads = [Thread(target=worker, args=(f"cmd-{i}",)) for i in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sum(kind == "committed" for kind, _ in outcomes), 1)
        self.assertEqual(sum(kind == "conflict" for kind, _ in outcomes), 1)
        self.assertEqual(self.coordinator.state["reserved"], 5)
        self.assertEqual(self.coordinator.aggregate_version("inventory_lot", "lot-1"), 1)
        self.assertEqual(len(self.store.replay()), 1)



if __name__ == "__main__":
    unittest.main(verbosity=2)
