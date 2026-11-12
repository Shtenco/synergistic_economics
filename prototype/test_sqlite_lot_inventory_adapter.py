import hashlib
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from real_economy_protocol import RealEconomyError
from sqlite_lot_inventory_adapter import SQLiteLotInventory, SQLiteLotInventoryError


NOW = datetime(2026, 11, 12, 16, 0, tzinfo=timezone.utc)
LATER = NOW + timedelta(days=2)


class SQLiteLotInventoryAdapterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = os.path.join(self.tmp.name, "inventory.sqlite3")
        self.inventory = SQLiteLotInventory(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def meta(self, command, key, *, fail_at=None):
        return {
            "command_id": command, "idempotency_key": key,
            "authority_ref": "inventory-mandate-1",
            "correlation_id": "corr-inventory-1",
            "occurred_at": NOW, "recorded_at": NOW, "fail_at": fail_at,
        }

    def register(self):
        return self.inventory.register_lot(
            lot_id="lot-1", product_id="grain", owner_id="owner-1",
            custodian_id="warehouse-1", location_id="depot-a",
            quantity="100", unit="kg", authorized_actors=("operator-1",),
            actor_id="operator-1",
            **self.meta("cmd-register", "request-register"),
        )

    def test_actual_lot_inventory_rules_are_durable_across_full_lifecycle(self):
        first = self.register()
        self.assertEqual(first.result["lot_id"], "lot-1")
        reserve = self.inventory.reserve(
            lot_id="lot-1", reservation_id="reservation-1", quantity="40",
            actor_id="operator-1", counterparty_id="buyer-1", purpose="delivery",
            expires_at=LATER, expected_lot_version=1, now=NOW,
            **self.meta("cmd-reserve", "request-reserve"),
        )
        self.assertEqual(reserve.result["remaining_quantity"], "40")
        commit = self.inventory.commit(
            reservation_id="reservation-1", actor_id="operator-1",
            authorization_ref="contract-1", expected_reservation_version=1,
            now=NOW, **self.meta("cmd-commit", "request-commit"),
        )
        self.assertEqual(commit.result["status"], "COMMITTED")
        consume = self.inventory.consume(
            reservation_id="reservation-1", actor_id="operator-1",
            quantity="15", moved_lot_id="lot-2",
            destination_location="depot-b", new_custodian_id="carrier-1",
            expected_reservation_version=2,
            **self.meta("cmd-consume", "request-consume"),
        )
        self.assertEqual(consume.result["moved_lot"]["quantity"], "15")
        release = self.inventory.release(
            reservation_id="reservation-1", actor_id="operator-1",
            expected_reservation_version=3,
            **self.meta("cmd-release", "request-release"),
        )
        self.assertEqual(release.result["status"], "RELEASED")
        quarantine = self.inventory.quarantine(
            lot_id="lot-1", actor_id="operator-1", expected_lot_version=4,
            reason="quality inspection",
            **self.meta("cmd-quarantine", "request-quarantine"),
        )
        self.assertEqual(quarantine.result["quality_status"], "QUARANTINED")

        source = self.inventory.get_lot("lot-1")
        moved = self.inventory.get_lot("lot-2")
        reservation = self.inventory.get_reservation("reservation-1")
        self.assertEqual(source.quantity, Decimal("85"))
        self.assertEqual(source.reserved_quantity, Decimal("0"))
        self.assertEqual(source.quality_status, "QUARANTINED")
        self.assertEqual(moved.quantity, Decimal("15"))
        self.assertEqual(moved.source_lot_id, "lot-1")
        self.assertEqual(reservation.remaining_quantity, Decimal("0"))
        self.assertEqual(reservation.status, "RELEASED")

        # A retry of the first command after five later commands must use its
        # original expected aggregate version and return the original receipt.
        version_before = self.inventory.repository.load_aggregate(
            "inventory_book", "inventory-book"
        )[0]
        replayed = self.register()
        self.assertEqual(replayed, first)
        self.assertEqual(self.inventory.repository.load_aggregate(
            "inventory_book", "inventory-book"
        )[0], version_before)

        reopened = SQLiteLotInventory(self.db)
        recovered = reopened.recover()
        self.assertEqual(recovered["version"], 6)
        self.assertEqual(len(recovered["lots"]), 2)
        self.assertEqual(len(recovered["reservations"]), 1)
        report = reopened.audit()
        self.assertEqual(report, {
            "events": 6, "commands": 6, "outbox": 6,
            "lots": 2, "reservations": 1,
        })

    def test_projection_failure_rolls_back_inventory_and_receipt_then_retry_succeeds(self):
        self.register()
        with self.assertRaisesRegex(RuntimeError, "projection write"):
            self.inventory.reserve(
                lot_id="lot-1", reservation_id="reservation-1", quantity="30",
                actor_id="operator-1", counterparty_id="buyer-1", purpose="delivery",
                expires_at=LATER, expected_lot_version=1, now=NOW,
                **self.meta("cmd-reserve", "request-reserve", fail_at="after_projection_write"),
            )
        self.assertEqual(self.inventory.get_lot("lot-1").reserved_quantity, Decimal("0"))
        with self.assertRaises(RealEconomyError):
            self.inventory.get_reservation("reservation-1")
        self.assertIsNone(self.inventory.repository.lookup_receipt("request-reserve"))
        self.assertEqual(self.inventory.audit()["events"], 1)

        receipt = self.inventory.reserve(
            lot_id="lot-1", reservation_id="reservation-1", quantity="30",
            actor_id="operator-1", counterparty_id="buyer-1", purpose="delivery",
            expires_at=LATER, expected_lot_version=1, now=NOW,
            **self.meta("cmd-reserve", "request-reserve"),
        )
        self.assertEqual(receipt.result["remaining_quantity"], "30")
        self.assertEqual(self.inventory.get_lot("lot-1").reserved_quantity, Decimal("30"))
        self.assertEqual(self.inventory.audit()["events"], 2)

    def test_replay_rejects_projection_tampering_even_when_projection_digest_is_rewritten(self):
        self.register()
        self.inventory.reserve(
            lot_id="lot-1", reservation_id="reservation-1", quantity="10",
            actor_id="operator-1", counterparty_id="buyer-1", purpose="delivery",
            expires_at=LATER, expected_lot_version=1, now=NOW,
            **self.meta("cmd-reserve", "request-reserve"),
        )
        forged = json.dumps(
            {"schema": "synergy.inventory-book.v1", "lots": [], "reservations": []},
            sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False,
        )
        digest = hashlib.sha256(forged.encode("utf-8")).hexdigest()
        import sqlite3
        con = sqlite3.connect(self.db)
        con.execute(
            "UPDATE aggregates SET state_json=?,state_digest=?",
            (forged, digest),
        )
        con.commit()
        con.close()
        with self.assertRaises(SQLiteLotInventoryError):
            self.inventory.audit()
        with self.assertRaises(SQLiteLotInventoryError):
            self.inventory.recover()

    def test_unauthorized_custodian_cannot_reserve_owned_stock(self):
        self.inventory.register_lot(
            lot_id="lot-1", product_id="grain", owner_id="owner-1",
            custodian_id="warehouse-1", location_id="depot-a",
            quantity="100", unit="kg",
            actor_id="operator-1",
            **self.meta("cmd-register", "request-register"),
        )
        with self.assertRaisesRegex(RealEconomyError, "not authorized"):
            self.inventory.reserve(
                lot_id="lot-1", reservation_id="reservation-1", quantity="10",
                actor_id="warehouse-1", counterparty_id="buyer-1", purpose="delivery",
                expires_at=LATER, expected_lot_version=1, now=NOW,
                **self.meta("cmd-reserve", "request-reserve"),
            )
        self.assertEqual(self.inventory.get_lot("lot-1").reserved_quantity, Decimal("0"))
        self.assertEqual(self.inventory.audit()["events"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
