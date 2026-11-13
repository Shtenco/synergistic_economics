import sqlite3
import tempfile
from pathlib import Path
import unittest
from decimal import Decimal

from synergy_leagues import (
    LeagueError, ParticipantProfile, SkillEvidence, WorkOrder, WorkStatus,
)
from league_store import (
    LeagueCommandConflict, LeagueOrderNotFound, LeagueVersionConflict,
    SQLiteLeagueStore,
)


def profile():
    return ParticipantProfile(
        "worker-1", "Worker",
        (SkillEvidence("python", "evidence:python", "issuer:test", "2026-11-13T10:00:00Z"),),
    )


def order():
    return WorkOrder(
        "order-1", "buyer-1", "Build automation", "Create an invoice workflow.",
        ("python",), Decimal("1250.00"), "KZT",
        "2026-11-13T09:00:00Z", "2026-11-20T09:00:00Z",
    )


class SQLiteLeagueStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "league.sqlite3"
        self.store = SQLiteLeagueStore(self.db)

    def tearDown(self):
        self.temp.cleanup()

    def test_create_restart_and_read_append_only_history(self):
        initial = order()
        self.assertTrue(self.store.create(
            "tenant-a", initial, event_id="event-1", idempotency_key="create-1",
        ))
        restarted = SQLiteLeagueStore(self.db)
        loaded = restarted.get("tenant-a", "order-1")
        self.assertEqual(loaded, initial)
        self.assertEqual([e["event_type"] for e in restarted.events("tenant-a")], ["WORK_ORDER_CREATED"])
        self.assertTrue(restarted.integrity_check())

    def test_save_transition_and_exact_idempotent_replay(self):
        initial = order()
        self.store.create("tenant-a", initial, event_id="event-1", idempotency_key="create-1")
        applied = initial.apply(profile(), expected_version=1)
        self.assertTrue(self.store.save(
            "tenant-a", applied, expected_version=1,
            event_id="event-2", idempotency_key="apply-1", event_type="WORK_ORDER_APPLIED",
        ))
        self.assertFalse(self.store.save(
            "tenant-a", applied, expected_version=1,
            event_id="event-2", idempotency_key="apply-1", event_type="WORK_ORDER_APPLIED",
        ))
        self.assertEqual(self.store.get("tenant-a", "order-1"), applied)
        self.assertEqual(len(self.store.events("tenant-a", "order-1")), 2)

    def test_stale_version_and_unseen_order_rejected(self):
        initial = order()
        self.store.create("tenant-a", initial, event_id="event-1", idempotency_key="create-1")
        applied = initial.apply(profile(), expected_version=1)
        self.store.save(
            "tenant-a", applied, expected_version=1,
            event_id="event-2", idempotency_key="apply-1", event_type="WORK_ORDER_APPLIED",
        )
        with self.assertRaises(LeagueVersionConflict):
            self.store.save(
                "tenant-a", applied, expected_version=1,
                event_id="event-3", idempotency_key="stale-write", event_type="WORK_ORDER_APPLIED",
            )
        with self.assertRaises(LeagueOrderNotFound):
            self.store.get("tenant-b", "order-1")

    def test_idempotency_key_cannot_be_reused_for_different_payload(self):
        initial = order()
        self.store.create("tenant-a", initial, event_id="event-1", idempotency_key="create-1")
        applied = initial.apply(profile(), expected_version=1)
        self.store.save(
            "tenant-a", applied, expected_version=1,
            event_id="event-2", idempotency_key="apply-1", event_type="WORK_ORDER_APPLIED",
        )
        altered = applied.assign("worker-1", expected_version=2)
        with self.assertRaises(LeagueCommandConflict):
            self.store.save(
                "tenant-a", altered, expected_version=2,
                event_id="event-3", idempotency_key="apply-1", event_type="WORK_ORDER_ASSIGNED",
            )

    def test_tenant_scoping_allows_same_order_id_without_cross_read(self):
        self.store.create("tenant-a", order(), event_id="event-1", idempotency_key="create-1")
        other = order()
        other = WorkOrder(
            other.order_id, "buyer-b", other.title, other.description,
            other.required_skills, other.budget, other.currency,
            other.created_at, other.deadline,
        )
        self.store.create("tenant-b", other, event_id="event-1", idempotency_key="create-1")
        self.assertEqual(self.store.get("tenant-a", "order-1").buyer_id, "buyer-1")
        self.assertEqual(self.store.get("tenant-b", "order-1").buyer_id, "buyer-b")
        self.assertEqual(len(self.store.events("tenant-a")), 1)
        self.assertEqual(len(self.store.events("tenant-b")), 1)

    def test_event_rows_are_append_only(self):
        self.store.create("tenant-a", order(), event_id="event-1", idempotency_key="create-1")
        connection = sqlite3.connect(self.db)
        try:
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE league_work_order_events SET event_type='TAMPERED' "
                    "WHERE security_domain='tenant-a'"
                )
            connection.rollback()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "DELETE FROM league_work_order_events WHERE security_domain='tenant-a'"
                )
            connection.rollback()
        finally:
            connection.close()

    def test_new_orders_must_start_open_at_version_one(self):
        invalid = WorkOrder(
            "order-2", "buyer-1", "Title", "Description", (), Decimal("1.00"), "KZT",
            "2026-11-13T09:00:00Z", "2026-11-20T09:00:00Z",
            status=WorkStatus.CANCELLED,
        )
        with self.assertRaisesRegex(Exception, "must begin at version 1 in OPEN"):
            self.store.create("tenant-a", invalid, event_id="event-2", idempotency_key="create-2")

    def test_file_backed_database_is_required(self):
        with self.assertRaises(ValueError):
            SQLiteLeagueStore(":memory:")


if __name__ == "__main__":
    unittest.main()
