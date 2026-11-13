import os
import subprocess
import sys
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

    def test_outbox_publish_attempt_survives_crash_before_ack_and_retries(self):
        self.execute()
        self.assertTrue(self.repo.record_publish_attempt("event-1"))
        self.assertEqual(self.repo.pending_outbox()[0]["attempts"], 1)
        # Simulates publisher death after external send but before local ack.
        self.assertEqual(self.repo.pending_outbox()[0]["event_id"], "event-1")
        self.assertTrue(self.repo.record_publish_attempt("event-1"))
        self.assertEqual(self.repo.pending_outbox()[0]["attempts"], 2)
        self.assertTrue(self.repo.mark_published("event-1", NOW))
        self.assertFalse(self.repo.mark_published("event-1", NOW))
        self.assertEqual(self.repo.pending_outbox(), ())

    def test_real_process_termination_crash_matrix(self):
        script = r"""
import os, sys
sys.path.insert(0, sys.argv[3])
from datetime import datetime, timezone
from sqlite_event_repository import SQLiteEventRepository
db, target = sys.argv[1], sys.argv[2]
repo = SQLiteEventRepository(db)
now = datetime(2026, 11, 12, 14, 0, tzinfo=timezone.utc)
def transition(state):
    candidate = dict(state)
    candidate["reserved"] += 4
    event = {"event_id":"event-1","event_type":"inventory.quantity_reserved",
             "aggregate_id":"lot-1","aggregate_version":1,
             "idempotency_key":"event-key-1",
             "payload":{"quantity":"4","unit":"kg"}}
    return candidate, {"reserved":4}, [event]
def kill(stage):
    if stage == target:
        os._exit(73)
repo.execute(command_id="cmd-1", idempotency_key="request-1",
    request={"quantity":4}, aggregate_type="inventory_lot", aggregate_id="lot-1",
    expected_version=0, actor_id="operator-1", authority_ref="mandate-1",
    correlation_id="corr-1", occurred_at=now, recorded_at=now,
    transition=transition, crash_hook=kill)
"""
        stages = ("after_event_insert", "after_projection_write",
                  "after_receipt_write", "before_commit",
                  "after_commit_before_response")
        for stage in stages:
            with self.subTest(stage=stage):
                db = os.path.join(self.tmp.name, stage + ".sqlite3")
                repo = SQLiteEventRepository(db)
                repo.register_aggregate("inventory_lot", "lot-1", {"reserved": 0})
                child = subprocess.run(
                    [sys.executable, "-c", script, db, stage, os.path.dirname(__file__)],
                    check=False, capture_output=True, text=True,
                )
                self.assertEqual(child.returncode, 73, child.stderr)
                recovered = SQLiteEventRepository(db)
                if stage == "after_commit_before_response":
                    self.assertEqual(recovered.audit()["events"], 1)
                    self.assertIsNotNone(recovered.lookup_receipt("request-1"))
                    self.assertEqual(recovered.load_aggregate("inventory_lot", "lot-1"),
                                     (1, {"reserved": 4}))
                else:
                    self.assertEqual(recovered.audit(),
                                     {"events": 0, "commands": 0, "outbox": 0})
                    self.assertIsNone(recovered.lookup_receipt("request-1"))
                    self.assertEqual(recovered.load_aggregate("inventory_lot", "lot-1"),
                                     (0, {"reserved": 0}))

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

    def test_canonical_events_and_receipts_are_immutable(self):
        self.execute()
        import sqlite3
        con = sqlite3.connect(self.db)
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("UPDATE events SET event_type='forged'")
        con.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("UPDATE commands SET result_json='{}'")
        con.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            con.execute("DELETE FROM outbox")
        con.rollback()
        con.close()

    def test_event_tampering_fails_closed(self):
        self.execute()
        import sqlite3
        con = sqlite3.connect(self.db)
        con.execute("DROP TRIGGER events_no_update")
        con.execute("UPDATE events SET envelope_json=?", ('{"tampered":true}',))
        con.commit()
        con.close()
        with self.assertRaises(SQLiteRepositoryError):
            self.repo.audit()


if __name__ == "__main__":
    unittest.main(verbosity=2)
