import unittest
import json
from hashlib import sha256
from datetime import datetime, timezone

from synergy_kernel import EventStore
from real_economy_event_bridge import InMemoryAtomicCoordinator
from real_economy_event_replay import EventReplayError, audit_canonical_event_log


NOW = datetime(2026, 11, 11, 14, 0, tzinfo=timezone.utc)


def raw_event(event_id, key, version, ordinal_payload="5"):
    return {
        "event_id": event_id,
        "event_type": "inventory.quantity_reserved",
        "aggregate_id": "lot-1",
        "aggregate_version": version,
        "idempotency_key": key,
        "payload": {"quantity": ordinal_payload},
    }


def rewrite_envelope(event, **changes):
    event.payload.update(changes)
    raw = json.dumps(event.payload, sort_keys=True, separators=(",", ":"), default=str)
    object.__setattr__(event, "digest", sha256((event.event_type + "|" + raw).encode()).hexdigest())
    if "idempotency_key" in changes:
        object.__setattr__(event, "idempotency_key", changes["idempotency_key"])


def run_command(coordinator, command_id, key, version, events):
    return coordinator.execute(
        command_id=command_id, idempotency_key=key,
        request={"command": command_id}, aggregate_type="inventory_lot",
        aggregate_id="lot-1", expected_version=version - 1,
        actor_id="operator", authority_ref="mandate",
        correlation_id="correlation", occurred_at=NOW, recorded_at=NOW,
        transition=lambda state: (state, "ok", events),
    )


class CanonicalReplayAuditTests(unittest.TestCase):
    def setUp(self):
        self.store = EventStore()
        self.coordinator = InMemoryAtomicCoordinator({}, self.store)

    def test_empty_log(self):
        report = audit_canonical_event_log(self.store)
        self.assertEqual(report.canonical_events, 0)
        self.assertEqual(report.legacy_events, 0)

    def test_global_event_sequence_gap_is_rejected(self):
        self.store.append("legacy-1", "old.event", {"x": 1}, "legacy-key-1")
        self.store.append("legacy-2", "old.event", {"x": 2}, "legacy-key-2")
        object.__setattr__(self.store.events[1], "sequence", 3)
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_legacy_events_are_counted_but_not_decoded(self):
        self.store.append("legacy-1", "old.event", {"x": 1}, "legacy-key")
        report = audit_canonical_event_log(self.store)
        self.assertEqual(report.legacy_events, 1)
        self.assertEqual(report.canonical_events, 0)

    def test_valid_single_event_command(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        report = audit_canonical_event_log(self.store)
        self.assertEqual((report.canonical_events, report.aggregates, report.commands), (1, 1, 1))

    def test_valid_multi_event_command_has_contiguous_ordinals(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1, [
            raw_event("evt-1", "event-key-1", 1),
            raw_event("evt-2", "event-key-2", 1, "6"),
        ])
        report = audit_canonical_event_log(self.store)
        self.assertEqual(report.canonical_events, 2)
        self.assertEqual(report.commands, 1)

    def test_sequential_aggregate_versions(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        run_command(self.coordinator, "cmd-2", "request-2", 2,
                    [raw_event("evt-2", "event-key-2", 2)])
        report = audit_canonical_event_log(self.store)
        self.assertEqual(report.commands, 2)

    def test_payload_tampering_is_detected(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        self.store.events[0].payload["payload"]["quantity"] = "999"
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_envelope_tampering_is_detected_by_store_digest(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        self.store.events[0].payload["actor_id"] = "intruder"
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_identity_mismatch_is_detected(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        self.store.events[0].payload["event_id"] = "different"
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_aggregate_version_gap_is_rejected(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        # Create a well-formed second envelope but with aggregate version 3.
        run_command(self.coordinator, "cmd-2", "request-2", 2,
                    [raw_event("evt-2", "event-key-2", 2)])
        event = self.store.events[1]
        event.payload["aggregate_version"] = 3
        raw = json.dumps(event.payload, sort_keys=True, separators=(",", ":"), default=str)
        object.__setattr__(event, "digest", sha256((event.event_type + "|" + raw).encode()).hexdigest())
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_ordinal_gap_is_rejected(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1, [
            raw_event("evt-1", "event-key-1", 1),
            raw_event("evt-2", "event-key-2", 1),
        ])
        self.store.events[1].payload["event_ordinal"] = 2
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_missing_actor_metadata_is_rejected_even_with_recomputed_store_digest(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        rewrite_envelope(self.store.events[0], actor_id=" ")
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_non_utc_timestamp_is_rejected(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        rewrite_envelope(self.store.events[0], occurred_at="2026-11-11T17:00:00+03:00")
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_duplicate_idempotency_key_across_events_is_rejected(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1, [
            raw_event("evt-1", "event-key-1", 1),
            raw_event("evt-2", "event-key-2", 1, "6"),
        ])
        rewrite_envelope(self.store.events[1], idempotency_key="event-key-1")
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_command_id_cannot_be_reused_for_another_aggregate_version(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        run_command(self.coordinator, "cmd-2", "request-2", 2,
                    [raw_event("evt-2", "event-key-2", 2)])
        rewrite_envelope(self.store.events[1], command_id="cmd-1")
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_duplicate_evidence_refs_are_rejected(self):
        run_command(self.coordinator, "cmd-1", "request-1", 1,
                    [raw_event("evt-1", "event-key-1", 1)])
        rewrite_envelope(self.store.events[0], evidence_refs=["evidence-1", "evidence-1"])
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)

    def test_unknown_declared_schema_fails_closed(self):
        self.store.append("bad-1", "future.event", {"schema_version": "synergy.event.v99"}, "bad-key")
        with self.assertRaises(EventReplayError):
            audit_canonical_event_log(self.store)


if __name__ == "__main__":
    unittest.main(verbosity=2)
