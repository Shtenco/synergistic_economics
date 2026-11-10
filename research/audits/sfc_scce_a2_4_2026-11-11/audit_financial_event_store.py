"""Adversarial controls for the durable A2.4.4 financial event store."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile
from threading import Barrier

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from financial_event_store import FinancialEventStore, FinancialEventStoreError


def _posting(account, side, amount, entity_id):
    return {
        "account": account,
        "side": side,
        "amount": str(amount),
        "entity_id": entity_id,
    }


def _event(event_id, event_type, postings):
    return {
        "event_id": event_id,
        "event_type": event_type,
        "effective_period": 2021,
        "postings": postings,
    }


def _must_reject(call, message):
    try:
        call()
    except (FinancialEventStoreError, sqlite3.IntegrityError):
        return
    raise AssertionError(message)


def _create_legacy_v1_database(path, events, user_version):
    group = {
        "group_id": "legacy-group",
        "causation_id": "legacy-cause",
        "events": list(events),
    }
    group_json = json.dumps(
        group, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    )
    with closing(sqlite3.connect(path)) as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        connection.executescript("""
            CREATE TABLE event_groups (
                group_id TEXT PRIMARY KEY, causation_id TEXT,
                payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE events (
                event_id TEXT PRIMARY KEY,
                group_id TEXT NOT NULL REFERENCES event_groups(group_id),
                event_type TEXT NOT NULL,
                effective_period INTEGER NOT NULL CHECK (effective_period >= 0),
                payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL
            );
            CREATE TABLE journal_lines (
                event_id TEXT NOT NULL REFERENCES events(event_id),
                line_no INTEGER NOT NULL CHECK (line_no >= 0),
                posting_json TEXT NOT NULL,
                PRIMARY KEY (event_id, line_no)
            );
            CREATE INDEX events_by_group ON events(group_id, event_id);
            CREATE TRIGGER events_no_update BEFORE UPDATE ON events
            BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
        """)
        connection.execute(
            "INSERT INTO event_groups VALUES (?, ?, ?, ?)",
            ("legacy-group", "legacy-cause",
             hashlib.sha256(group_json.encode("utf-8")).hexdigest(),
             group_json),
        )
        for event in events:
            event_json = json.dumps(
                event, sort_keys=True, separators=(",", ":"),
                ensure_ascii=False, allow_nan=False,
            )
            connection.execute(
                "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?)",
                (event["event_id"], "legacy-group", event["event_type"],
                 event["effective_period"],
                 hashlib.sha256(event_json.encode("utf-8")).hexdigest(),
                 event_json),
            )
            for line_no, posting in enumerate(event["postings"]):
                posting_json = json.dumps(
                    posting, sort_keys=True, separators=(",", ":"),
                    ensure_ascii=False, allow_nan=False,
                )
                connection.execute(
                    "INSERT INTO journal_lines VALUES (?, ?, ?)",
                    (event["event_id"], line_no, posting_json),
                )
        connection.execute(f"PRAGMA user_version = {int(user_version)}")
    return group


def main():
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "financial-events.sqlite3"
        _must_reject(
            lambda: FinancialEventStore(":memory:"),
            "non-persistent in-memory database was accepted",
        )
        _must_reject(
            lambda: FinancialEventStore(database, timeout=float("nan")),
            "non-finite SQLite timeout was accepted",
        )
        loan = _event("loan-1", "nonbank_loan_origination", (
            _posting("loan_asset", "D", "19", "lender-1"),
            _posting("loan_liability", "C", "19", "borrower-1"),
        ))
        transfer = _event("transfer-1", "nonbank_deposit_transfer", (
            _posting("deposit_asset", "C", "19", "lender-1"),
            _posting("deposit_liability", "D", "19", "lender-1"),
            _posting("deposit_asset", "D", "19", "borrower-1"),
            _posting("deposit_liability", "C", "19", "borrower-1"),
        ))
        group = (loan, transfer)

        store = FinancialEventStore(database)
        assert store.append_group(
            "credit-transaction-1", group,
            causation_id="credit-agreement-1")
        assert store.counts() == {
            "groups": 1, "events": 2, "journal_lines": 6,
        }
        assert store.integrity_check()

        # Restart boundary: uniqueness and the complete group survive process
        # reconstruction because they are in SQLite, not an in-memory dict.
        reopened = FinancialEventStore(database)
        assert reopened.append_group(
            "credit-transaction-1", group,
            causation_id="credit-agreement-1") is False
        recovered = reopened.get_group("credit-transaction-1")
        assert recovered["causation_id"] == "credit-agreement-1"
        assert [row["event_id"] for row in recovered["events"]] == [
            "loan-1", "transfer-1",
        ]
        assert reopened.counts() == {
            "groups": 1, "events": 2, "journal_lines": 6,
        }

        # Same group ID with modified economics is not an idempotent replay.
        changed = _event("loan-1", "nonbank_loan_origination", (
            _posting("loan_asset", "D", "20", "lender-1"),
            _posting("loan_liability", "C", "20", "borrower-1"),
        ))
        _must_reject(
            lambda: reopened.append_group(
                "credit-transaction-1", (changed, transfer),
                causation_id="credit-agreement-1"),
            "changed content under an existing group ID was accepted",
        )

        # Event IDs are globally unique across groups, not just within one call.
        _must_reject(
            lambda: reopened.append_group(
                "credit-transaction-2", (loan,),
                causation_id="credit-agreement-2"),
            "event ID reused by a second group was accepted",
        )
        assert reopened.get_group("credit-transaction-2") is None
        assert reopened.counts() == {
            "groups": 1, "events": 2, "journal_lines": 6,
        }

        # The database itself rejects mutation of committed event/posting rows.
        with closing(sqlite3.connect(database)) as connection:
            _must_reject(
                lambda: connection.execute(
                    "UPDATE events SET payload_json = '{}' WHERE event_id = 'loan-1'"),
                "committed event row was mutable",
            )
            _must_reject(
                lambda: connection.execute(
                    "DELETE FROM journal_lines WHERE event_id = 'loan-1'"),
                "committed posting rows were deletable",
            )
        assert reopened.integrity_check()

        # Decimal strings are required: binary floats and non-finite values
        # must not enter the canonical financial event payload.
        malformed = _event("bad-amount", "supplier_settlement", (
            _posting("expense", "D", "1", "payer"),
            _posting("deposit_asset", "C", "1", "payer"),
        ))
        malformed["postings"][0]["amount"] = 1.25
        _must_reject(
            lambda: reopened.append_group("bad-amount-group", (malformed,)),
            "binary floating-point amount was accepted",
        )

        # Force a failure after the group and event rows have begun inserting.
        # The SQLite transaction must roll back the entire group and all lines.
        rollback_db = Path(directory) / "rollback.sqlite3"
        rollback_store = FinancialEventStore(rollback_db)
        with closing(sqlite3.connect(rollback_db)) as connection:
            connection.execute("""
                CREATE TRIGGER reject_second_posting
                BEFORE INSERT ON journal_lines
                WHEN NEW.line_no = 1
                BEGIN
                    SELECT RAISE(ABORT, 'injected posting failure');
                END
            """)
        _must_reject(
            lambda: rollback_store.append_group(
                "atomic-group", (loan,), causation_id="atomic-cause"),
            "injected mid-transaction posting failure was not surfaced",
        )
        assert rollback_store.get_group("atomic-group") is None
        assert rollback_store.counts() == {
            "groups": 0, "events": 0, "journal_lines": 0,
        }
        assert rollback_store.integrity_check()

        # Upgrade explicit v1 and crash-interrupted v1-layout databases.
        legacy_events = (loan, transfer)
        for legacy_version, filename in (
                (1, "legacy-v1.sqlite3"),
                (0, "legacy-v1-unstamped.sqlite3")):
            legacy_db = Path(directory) / filename
            legacy_group = _create_legacy_v1_database(
                legacy_db, legacy_events, legacy_version)
            migrated = FinancialEventStore(legacy_db)
            assert migrated.integrity_check()
            assert migrated.get_group("legacy-group") == legacy_group
            with closing(sqlite3.connect(legacy_db)) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
                assert connection.execute(
                    "SELECT event_id, event_index FROM events "
                    "WHERE group_id = ? ORDER BY event_index",
                    ("legacy-group",),
                ).fetchall() == [("loan-1", 0), ("transfer-1", 1)]

        # Concurrent duplicate delivery of one group must serialize to
        # one insert and one idempotent replay, never duplicate postings.
        race_db = Path(directory) / "same-group-race.sqlite3"
        race_store = FinancialEventStore(race_db)
        same_group_barrier = Barrier(2)

        def same_group_writer():
            same_group_barrier.wait()
            return race_store.append_group(
                "raced-group", (loan,), causation_id="raced-cause")

        with ThreadPoolExecutor(max_workers=2) as pool:
            same_group_results = list(pool.map(
                lambda _: same_group_writer(), range(2)))
        assert sorted(same_group_results) == [False, True]
        assert race_store.counts() == {
            "groups": 1, "events": 1, "journal_lines": 2,
        }
        assert race_store.integrity_check()

        # Different transaction groups racing with the same event ID must
        # not both win the uniqueness check.
        cross_group_db = Path(directory) / "cross-group-race.sqlite3"
        cross_group_store = FinancialEventStore(cross_group_db)
        cross_group_barrier = Barrier(2)

        def cross_group_writer(group_id):
            cross_group_barrier.wait()
            try:
                return cross_group_store.append_group(
                    group_id, (loan,), causation_id=group_id)
            except FinancialEventStoreError:
                return "event-id-conflict"

        with ThreadPoolExecutor(max_workers=2) as pool:
            cross_group_results = list(pool.map(
                cross_group_writer, ("race-A", "race-B")))
        assert cross_group_results.count(True) == 1
        assert cross_group_results.count("event-id-conflict") == 1
        assert cross_group_store.counts() == {
            "groups": 1, "events": 1, "journal_lines": 2,
        }
        assert cross_group_store.integrity_check()

        # An out-of-band extra posting is detectable even if SQLite itself
        # remains structurally valid and foreign keys still hold.
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "INSERT INTO journal_lines(event_id, line_no, posting_json) "
                "VALUES (?, ?, ?)",
                ("loan-1", 99, '{"account":"tampered","side":"D","amount":"1","entity_id":"x"}'),
            )
        assert not reopened.integrity_check()

    print("A2.4.4 durable financial event store: PASS")
    print("event and posting rows commit atomically as one transaction group")
    print("group/event uniqueness survives store reconstruction")
    print("same-content replay is idempotent; changed-content replay is rejected")
    print("cross-group event-ID reuse and binary floating-point amounts are rejected")
    print("injected mid-write failure rolls back group, events and postings together")
    print("concurrent identical group delivery serializes to one durable insert")
    print("concurrent cross-group event-ID collision admits exactly one winner")
    print("schema-v1 migration preserves explicit transaction event order")


if __name__ == "__main__":
    main()
