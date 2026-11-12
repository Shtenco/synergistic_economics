import os
import tempfile
import unittest
from datetime import datetime, timezone

from real_economy_event_bridge import EventBridgeConflict
from real_economy_event_replay import EventReplayError, audit_canonical_event_log
from synergy_kernel import EventStore
from sqlite_event_repository import SQLiteEventRepository, SQLiteRepositoryError


NOW = datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)


def event(event_id="event-1", key="event-key-1", version=1, quantity="4"):
    return {
        "event_id": event_id,
        "event_type": "inventory.quantity_reserved",
        "aggregate_id": "lot-1",
        "aggregate_version": version,
        "idempotency_key": key,
        "payload": {"quantity": quantity, "unit": "kg"},
    }


class SQLiteRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "p6.sqlite3")
        self.repo = SQLiteEventRepository(self.db)
        self.repo.register_aggregate("inventory_lot", "lot-1", {"reserved": 0})

    def tearDown(self):
        self.tmp.cleanup()

    def execute(self, *, key="request-1", command="cmd-1", fail_at=None, quantity=4):
        def transition(state):
            candidate = dict(state)
            candidate["reserved"] += quantity
            return candidate, {"reserved": candidate["reserved"]}, [
                event(quantity=str(quantity))
            ]
        return self.repo.execute(
            command_id=command, idempotency_key=key,
            request={"lot_id": "lot-1", "quantity": quantity},
            aggregate_type="inventory_lot", aggregate_id="lot-1",
            expected_version=0, actor_id="operator-1",
            authority_ref="mandate-1", correlation_id="corr-1",
            occurred_at=NOW, recorded_at=NOW, transition=transition,
            fail_at=fail_at,
        )

    def test_atomic_success_persists_event_projection_receipt_and_outbox(self):
        receipt = self.execute()
        self.assertEqual(receipt.event_ids, ("event-1",))
        self.assertEqual(self.repo.load_aggregate("inventory_lot", "lot-1"),
                         (1, {"reserved": 4}))
        self.assertEqual(self.repo.audit(), {"events": 1, "commands": 1, "outbox": 1})
        self.assertEqual(len(self.repo.pending_outbox()), 1)

    def test_crash_before_commit_rolls_back_every_durable_record(self):
        for fail_at in ("after_event_insert", "after_projection_write",
                        "after_receipt_write", "before_commit"):
            with self.subTest(fail_at=fail_at):
                with self.assertRaises(RuntimeError):
                    self.execute(key="request-" + fail_at,
                                 command="cmd-" + fail_at, fail_at=fail_at)
                self.assertEqual(self.repo.load_aggregate("inventory_lot", "lot-1"),
                                 (0, {"reserved": 0}))
                self.assertEqual(self.repo.audit(),
                                 {"events": 0, "commands": 0, "outbox": 0})

    def test_lost_response_after_commit_is_resolved_by_same_idempotency_key(self):
        with self.assertRaisesRegex(RuntimeError, "lost response"):
            self.execute(fail_at="after_commit_before_response")
        receipt = self.repo.lookup_receipt("request-1")
        self.assertIsNotNone(receipt)
        retry = self.execute()
        self.assertEqual(retry, receipt)
        self.assertEqual(self.repo.load_aggregate("inventory_lot", "lot-1"),
                         (1, {"reserved": 4}))
        self.assertEqual(self.repo.audit()["events"], 1)

    def test_same_key_different_request_is_hard_conflict(self):
        self.execute()
        with self.assertRaises(EventBridgeConflict):
            self.repo.execute(
                command_id="cmd-2", idempotency_key="request-1",
                request={"lot_id": "lot-1", "quantity": 99},
                aggregate_type="inventory_lot", aggregate_id="lot-1",
                expected_version=1, actor_id="operator-1",
                authority_ref="mandate-1", correlation_id="corr-1",
                occurred_at=NOW, recorded_at=NOW,
                transition=lambda state: (state, None, [event("event-2", "event-key-2", 2)]),
            )

    def test_stale_version_does_not_mutate_anything(self):
        with self.assertRaises(EventBridgeConflict):
            self.repo.execute(
                command_id="cmd-stale", idempotency_key="stale",
                request={"x": 1}, aggregate_type="inventory_lot",
                aggregate_id="lot-1", expected_version=1,
                actor_id="operator-1", authority_ref="mandate-1",
                correlation_id="corr-1", occurred_at=NOW, recorded_at=NOW,
                transition=lambda state: (state, None, [event()]),
            )
        self.assertEqual(self.repo.audit()["events"], 0)

    def test_outbox_publication_is_separate_and_idempotent(self):
        self.execute()
        self.assertTrue(self.repo.mark_published("event-1", NOW))
        self.assertFalse(self.repo.mark_published("event-1", NOW))
        self.assertEqual(self.repo.pending_outbox(), ())

    def test_restart_reopens_same_database_and_recovers_durable_heads(self):
        self.execute()
        reopened = SQLiteEventRepository(self.db)
        self.assertEqual(reopened.recover()[("inventory_lot", "lot-1")],
                         {"version": 1, "state": {"reserved": 4}})

    def test_projection_tampering_fails_closed(self):
        self.execute()
        import sqlite3
        con = sqlite3.connect(self.db)
        con.execute("UPDATE aggregates SET state_json=?", ('{"reserved":999}',))
        con.commit()
        con.close()
        with self.assertRaises(SQLiteRepositoryError):
            self.repo.recover()

    def test_aggregate_version_divergence_from_event_log_fails_closed(self):
        self.execute()
        import sqlite3
        con = sqlite3.connect(self.db)
        con.execute("UPDATE aggregates SET version=2")
        con.commit()
        con.close()
        with self.assertRaises(SQLiteRepositoryError):
            self.repo.recover()

    def test_event_tampering_fails_closed(self):
        self.execute()
        import sqlite3
        con = sqlite3.connect(self.db)
        con.execute("UPDATE events SET envelope_json=?", ('{"tampered":true}',))
        con.commit()
        con.close()
        with self.assertRaises(SQLiteRepositoryError):
            self.repo.audit()


if __name__ == "__main__":
    unittest.main(verbosity=2)
