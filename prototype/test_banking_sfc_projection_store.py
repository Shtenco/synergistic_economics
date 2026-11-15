"""Adversarial tests for durable native banking SFC projection persistence."""
from dataclasses import dataclass
from decimal import Decimal
import sqlite3
import tempfile
import unittest
from pathlib import Path

from banking_sfc_projection_store import (
    BankingSFCProjectionStore,
    BankingSFCStoreError,
)


@dataclass(frozen=True)
class Projection:
    mapping_version: str
    source_digest: str
    events: tuple
    projection: dict
    openings: dict
    roll_forward: dict
    sector_financial_net_lending: dict
    source_event_count: int = 1
    mapped_source_event_count: int = 1
    excluded_opening_event_count: int = 0


def sample_projection(source_digest="source-1", amount="10.00"):
    return Projection(
        mapping_version="banking-sfc-v1:test",
        source_digest=source_digest,
        events=({"event_id": "evt-1", "deltas": ({"amount": Decimal(amount)},)},),
        projection={"mapping_version": "banking-sfc-v1:test"},
        openings={("position-a", 1): Decimal("100")},
        roll_forward={("position-a", 1): {"opening": Decimal("100"),
                                           "transaction": Decimal(amount),
                                           "closing": Decimal("110")}},
        sector_financial_net_lending={(1, "CB", "KZT"): Decimal("-10")},
    )


class BankingSFCProjectionStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = str(Path(self.tmp.name) / "projection.sqlite")
        self.store = BankingSFCProjectionStore(self.path)
        self.pins = dict(
            source_register_id="operating-financial:principal-1",
            source_sequence=4,
            source_chain_hash="a" * 64,
            instrument_registry_digest="instrument-digest-v1",
            sector_registry_digest="sector-digest-v1",
            opening_snapshot_digest="opening-digest-v1",
        )

    def append(self, projection=None, **overrides):
        args = dict(self.pins)
        args.update(overrides)
        return self.store.append(
            projection or sample_projection(),
            instrument_registry_digest=args["instrument_registry_digest"],
            sector_registry_digest=args["sector_registry_digest"],
            opening_snapshot_digest=args["opening_snapshot_digest"],
            source_register_id=args["source_register_id"],
            source_sequence=args["source_sequence"],
            source_chain_hash=args["source_chain_hash"],
            **({"fault_at": args["fault_at"]} if "fault_at" in args else {}),
        )

    def recover(self, projection=None):
        return self.store.recover(
            projection or sample_projection(),
            source_register_id=self.pins["source_register_id"],
            source_sequence=self.pins["source_sequence"],
            source_chain_hash=self.pins["source_chain_hash"],
            instrument_registry_digest=self.pins["instrument_registry_digest"],
            sector_registry_digest=self.pins["sector_registry_digest"],
            opening_snapshot_digest=self.pins["opening_snapshot_digest"],
        )

    def test_append_is_idempotent_and_recovery_rederives_exact_projection(self):
        first = self.append()
        replay = self.append()
        self.assertFalse(first["replayed"])
        self.assertTrue(replay["replayed"])
        self.assertEqual(first["projection_digest"], replay["projection_digest"])
        recovered = self.recover()
        self.assertEqual(recovered["applied_through_sequence"], 4)
        self.assertEqual(self.store.latest_checkpoint(self.pins["source_register_id"])["checkpoint_digest"],
                         first["checkpoint_digest"])

    def test_changed_event_content_at_same_cursor_is_rejected(self):
        self.append()
        with self.assertRaisesRegex(BankingSFCStoreError, "reused with changed"):
            self.append(sample_projection(amount="11"))

    def test_stale_cursor_is_rejected_but_global_sequence_gaps_are_allowed(self):
        self.append()
        with self.assertRaisesRegex(BankingSFCStoreError, "stale"):
            self.append(source_sequence=3)
        # The register sequence is global; unrelated aggregate events may occupy
        # intervening sequence numbers, so the financial projection cursor may skip.
        advanced = self.append(source_sequence=6)
        self.assertFalse(advanced["replayed"])
        self.assertEqual(self.store.latest_checkpoint(self.pins["source_register_id"])
                         ["applied_through_sequence"], 6)

    def test_source_chain_tail_change_at_same_cursor_is_rejected(self):
        self.append()
        with self.assertRaisesRegex(BankingSFCStoreError, "reused with changed"):
            self.append(source_chain_hash="b" * 64)

    def test_registry_or_opening_drift_is_rejected(self):
        self.append()
        with self.assertRaisesRegex(BankingSFCStoreError, "pinned registry/opening"):
            self.append(source_sequence=5, sector_registry_digest="changed")

    def test_recovery_rejects_changed_replay_without_advancing_checkpoint(self):
        self.append()
        with self.assertRaisesRegex(BankingSFCStoreError, "differs"):
            self.recover(sample_projection(amount="12"))
        self.assertEqual(self.store.latest_checkpoint(self.pins["source_register_id"])
                         ["applied_through_sequence"], 4)

    def test_failure_after_snapshot_write_rolls_back_snapshot_and_checkpoint(self):
        with self.assertRaisesRegex(RuntimeError, "injected crash"):
            self.append(fault_at="after_snapshot")
        self.assertIsNone(self.store.latest_checkpoint(self.pins["source_register_id"]))
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM banking_sfc_snapshots").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM banking_sfc_checkpoints").fetchone()[0], 0)

    def test_failure_after_checkpoint_write_rolls_back_both_rows(self):
        with self.assertRaisesRegex(RuntimeError, "injected crash"):
            self.append(fault_at="after_checkpoint")
        self.assertIsNone(self.store.latest_checkpoint(self.pins["source_register_id"]))
        with sqlite3.connect(self.path) as con:
            self.assertEqual(con.execute("SELECT COUNT(*) FROM banking_sfc_snapshots").fetchone()[0], 0)
            self.assertEqual(con.execute("SELECT COUNT(*) FROM banking_sfc_checkpoints").fetchone()[0], 0)


    def test_unknown_failpoint_is_rejected_before_any_database_write(self):
        with self.assertRaisesRegex(BankingSFCStoreError, "unsupported persistence failpoint"):
            self.append(fault_at="after_snapshop")
        self.assertIsNone(self.store.latest_checkpoint(self.pins["source_register_id"]))

    def test_recovery_rejects_invalid_cursor_and_unpinned_metadata(self):
        self.append()
        with self.assertRaisesRegex(BankingSFCStoreError, "source_sequence"):
            self.store.recover(
                sample_projection(),
                source_register_id=self.pins["source_register_id"],
                source_sequence=True,
                source_chain_hash=self.pins["source_chain_hash"],
                instrument_registry_digest=self.pins["instrument_registry_digest"],
                sector_registry_digest=self.pins["sector_registry_digest"],
                opening_snapshot_digest=self.pins["opening_snapshot_digest"],
            )
        with self.assertRaisesRegex(BankingSFCStoreError, "sector_registry_digest"):
            self.store.recover(
                sample_projection(),
                source_register_id=self.pins["source_register_id"],
                source_sequence=4,
                source_chain_hash=self.pins["source_chain_hash"],
                instrument_registry_digest=self.pins["instrument_registry_digest"],
                sector_registry_digest=" ",
                opening_snapshot_digest=self.pins["opening_snapshot_digest"],
            )

    def test_idempotent_append_rejects_offline_checkpoint_corruption(self):
        self.append()
        # Simulate an offline/file-level edit that bypasses the normal immutable-row trigger.
        with sqlite3.connect(self.path) as con:
            con.execute("DROP TRIGGER banking_sfc_checkpoints_no_update")
            con.execute("UPDATE banking_sfc_checkpoints SET checkpoint_digest='tampered'")
        with self.assertRaisesRegex(BankingSFCStoreError, "integrity verification failed"):
            self.append()

    def test_idempotent_append_rejects_missing_checkpoint(self):
        self.append()
        with sqlite3.connect(self.path) as con:
            con.execute("DROP TRIGGER banking_sfc_checkpoints_no_delete")
            con.execute("DELETE FROM banking_sfc_checkpoints")
        with self.assertRaisesRegex(BankingSFCStoreError, "no valid matching checkpoint"):
            self.append()

    def test_persisted_rows_are_immutable(self):
        self.append()
        with sqlite3.connect(self.path) as con:
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("UPDATE banking_sfc_snapshots SET source_digest='tampered'")
            with self.assertRaises(sqlite3.IntegrityError):
                con.execute("DELETE FROM banking_sfc_checkpoints")


if __name__ == "__main__":
    unittest.main()
