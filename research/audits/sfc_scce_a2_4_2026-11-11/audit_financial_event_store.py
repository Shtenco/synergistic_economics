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
        connection.commit()
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
        # Deliberately reverse lexical event-ID order to prove that migration
        # preserves insertion order rather than sorting by identifier.
        legacy_events = (transfer, loan)
        for legacy_version, filename in (
                (1, "legacy-v1.sqlite3"),
                (0, "legacy-v1-unstamped.sqlite3")):
            legacy_db = Path(directory) / filename
            legacy_group = _create_legacy_v1_database(
                legacy_db, legacy_events, legacy_version)
            migrated = FinancialEventStore(legacy_db)
            assert migrated.integrity_check()
            assert migrated.get_group("legacy-group") == legacy_group
            assert migrated.iter_groups() == [{
                "commit_sequence": 1, "group": legacy_group,
            }]
            with closing(sqlite3.connect(legacy_db)) as connection:
                assert connection.execute("PRAGMA user_version").fetchone()[0] == 3
                assert connection.execute(
                    "SELECT event_id, event_index FROM events "
                    "WHERE group_id = ? ORDER BY event_index",
                    ("legacy-group",),
                ).fetchall() == [("transfer-1", 0), ("loan-1", 1)]

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

        # Global commit order is independent of economic effective_period.
        order_db = Path(directory) / "commit-order.sqlite3"
        order_store = FinancialEventStore(order_db)
        first_event = _event("ordered-1", "first-committed", (
            _posting("cash", "D", "1", "entity-a"),
            _posting("equity", "C", "1", "entity-a"),
        ))
        second_event = _event("ordered-2", "late-arriving-backdated", (
            _posting("cash", "D", "2", "entity-b"),
            _posting("equity", "C", "2", "entity-b"),
        ))
        second_event["effective_period"] = 2018
        assert order_store.append_group("ordered-group-1", (first_event,))
        assert order_store.append_group("ordered-group-2", (second_event,))
        assert order_store.append_group("ordered-group-1", (first_event,)) is False
        ordered = order_store.iter_groups()
        assert [item["commit_sequence"] for item in ordered] == [1, 2]
        assert [item["group"]["group_id"] for item in ordered] == [
            "ordered-group-1", "ordered-group-2",
        ]
        assert [item["group"]["events"][0]["effective_period"]
                for item in ordered] == [2021, 2018]
        assert order_store.integrity_check()

        # Concurrent independent writers allocate one gap-free sequence under
        # BEGIN IMMEDIATE, regardless of which writer wins the lock first.
        concurrent_order_db = Path(directory) / "concurrent-commit-order.sqlite3"
        concurrent_order_store = FinancialEventStore(concurrent_order_db)
        order_barrier = Barrier(4)
        def ordered_writer(index):
            event = _event(f"concurrent-order-{index}", "concurrent-append", (
                _posting("cash", "D", str(index + 1), f"entity-{index}"),
                _posting("equity", "C", str(index + 1), f"entity-{index}"),
            ))
            order_barrier.wait()
            return concurrent_order_store.append_group(
                f"concurrent-group-{index}", (event,))
        with ThreadPoolExecutor(max_workers=4) as pool:
            assert all(pool.map(ordered_writer, range(4)))
        concurrent_sequences = [
            item["commit_sequence"] for item in concurrent_order_store.iter_groups()
        ]
        assert concurrent_sequences == [1, 2, 3, 4]
        assert concurrent_order_store.integrity_check()

        # A populated v2 database with multiple groups has no recoverable
        # cross-group chronology. Migration must fail closed and leave it v2.
        legacy_v2_db = Path(directory) / "legacy-v2-multi-group.sqlite3"
        with closing(sqlite3.connect(legacy_v2_db)) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
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
                    event_index INTEGER NOT NULL CHECK (event_index >= 0),
                    payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL
                );
                CREATE TABLE journal_lines (
                    event_id TEXT NOT NULL REFERENCES events(event_id),
                    line_no INTEGER NOT NULL CHECK (line_no >= 0),
                    posting_json TEXT NOT NULL,
                    PRIMARY KEY (event_id, line_no)
                );
                PRAGMA user_version = 2;
            """)
            for index in range(2):
                event = _event(f"v2-event-{index}", "legacy-v2", (
                    _posting("cash", "D", "1", f"entity-{index}"),
                    _posting("equity", "C", "1", f"entity-{index}"),
                ))
                envelope = {"group_id": f"v2-group-{index}",
                            "causation_id": None, "events": [event]}
                group_json = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                                         ensure_ascii=False, allow_nan=False)
                event_json = json.dumps(event, sort_keys=True, separators=(",", ":"),
                                        ensure_ascii=False, allow_nan=False)
                connection.execute(
                    "INSERT INTO event_groups VALUES (?, ?, ?, ?)",
                    (envelope["group_id"], None,
                     hashlib.sha256(group_json.encode("utf-8")).hexdigest(), group_json),
                )
                connection.execute(
                    "INSERT INTO events VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (event["event_id"], envelope["group_id"], event["event_type"],
                     event["effective_period"], 0,
                     hashlib.sha256(event_json.encode("utf-8")).hexdigest(), event_json),
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
            connection.commit()
        _must_reject(
            lambda: FinancialEventStore(legacy_v2_db),
            "populated schema-v2 store with ambiguous group order was migrated",
        )
        with closing(sqlite3.connect(legacy_v2_db)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 2
            assert connection.execute("SELECT COUNT(*) FROM event_groups").fetchone()[0] == 2

        # A crash after the v2 DDL but before user_version stamping must
        # be recognized as v2 from its event_index column, then fail closed.
        legacy_v2_unstamped_db = Path(directory) / "legacy-v2-unstamped.sqlite3"
        with closing(sqlite3.connect(legacy_v2_db)) as source_connection:
            with closing(sqlite3.connect(legacy_v2_unstamped_db)) as target_connection:
                source_connection.backup(target_connection)
                target_connection.execute("PRAGMA user_version = 0")
                target_connection.commit()
        _must_reject(
            lambda: FinancialEventStore(legacy_v2_unstamped_db),
            "unstamped populated schema-v2 store with ambiguous group order was migrated",
        )
        with closing(sqlite3.connect(legacy_v2_unstamped_db)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 0
            assert connection.execute("SELECT COUNT(*) FROM event_groups").fetchone()[0] == 2

        # A populated v2 store with one group has an unambiguous global order.
        legacy_v2_single_db = Path(directory) / "legacy-v2-single-group.sqlite3"
        with closing(sqlite3.connect(legacy_v2_db)) as source_connection:
            with closing(sqlite3.connect(legacy_v2_single_db)) as target_connection:
                source_connection.backup(target_connection)
                target_connection.execute(
                    "DELETE FROM journal_lines WHERE event_id = ?", ("v2-event-1",))
                target_connection.execute(
                    "DELETE FROM events WHERE event_id = ?", ("v2-event-1",))
                target_connection.execute(
                    "DELETE FROM event_groups WHERE group_id = ?", ("v2-group-1",))
                target_connection.commit()
        migrated_v2_single = FinancialEventStore(legacy_v2_single_db)
        assert migrated_v2_single.iter_groups()[0]["commit_sequence"] == 1
        assert migrated_v2_single.integrity_check()
        with closing(sqlite3.connect(legacy_v2_single_db)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 4

        # A v3 initializer may have committed commit_sequence but crashed
        # before stamping user_version. Reconstruct a populated single-group
        # v3 store, clear the version marker, and require v3 -> v4 recovery.
        legacy_v3_unstamped_db = Path(directory) / "legacy-v3-unstamped.sqlite3"
        with closing(sqlite3.connect(legacy_v2_db)) as source_connection:
            with closing(sqlite3.connect(legacy_v3_unstamped_db)) as target_connection:
                source_connection.backup(target_connection)
                target_connection.execute(
                    "DELETE FROM journal_lines WHERE event_id = ?", ("v2-event-1",))
                target_connection.execute(
                    "DELETE FROM events WHERE event_id = ?", ("v2-event-1",))
                target_connection.execute(
                    "DELETE FROM event_groups WHERE group_id = ?", ("v2-group-1",))
                target_connection.execute(
                    "ALTER TABLE event_groups ADD COLUMN commit_sequence "
                    "INTEGER NOT NULL DEFAULT 1 CHECK (commit_sequence > 0)")
                target_connection.execute(
                    "CREATE UNIQUE INDEX event_groups_commit_sequence "
                    "ON event_groups(commit_sequence)")
                target_connection.execute("PRAGMA user_version = 0")
                target_connection.commit()
        migrated_v3_unstamped = FinancialEventStore(legacy_v3_unstamped_db)
        assert migrated_v3_unstamped.iter_groups()[0]["commit_sequence"] == 1
        assert migrated_v3_unstamped.integrity_check()
        with closing(sqlite3.connect(legacy_v3_unstamped_db)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 4
            columns = {row[1] for row in connection.execute(
                "PRAGMA table_info(event_groups)").fetchall()}
            assert {"commit_sequence", "previous_group_hash", "group_chain_hash"} <= columns

        # A v4 initializer may have committed its chain columns but crashed
        # before stamping user_version. It must be recognized as v4 without
        # trying to add its columns a second time.
        legacy_v4_unstamped_db = Path(directory) / "legacy-v4-unstamped.sqlite3"
        with closing(sqlite3.connect(legacy_v2_single_db)) as source_connection:
            with closing(sqlite3.connect(legacy_v4_unstamped_db)) as target_connection:
                source_connection.backup(target_connection)
                target_connection.execute("PRAGMA user_version = 0")
                target_connection.commit()
        migrated_v4_unstamped = FinancialEventStore(legacy_v4_unstamped_db)
        assert migrated_v4_unstamped.iter_groups()[0]["commit_sequence"] == 1
        assert migrated_v4_unstamped.integrity_check()
        with closing(sqlite3.connect(legacy_v4_unstamped_db)) as connection:
            assert connection.execute("PRAGMA user_version").fetchone()[0] == 4

        # Out-of-band sequence corruption is caught even if an operator
        # disables the immutability trigger.
        tamper_db = Path(directory) / "commit-sequence-tamper.sqlite3"
        tamper_store = FinancialEventStore(tamper_db)
        tamper_store.append_group("tamper-group-1", (first_event,))
        tamper_store.append_group("tamper-group-2", (second_event,))
        with closing(sqlite3.connect(tamper_db)) as connection:
            connection.execute("DROP TRIGGER event_groups_no_update")
            connection.execute(
                "UPDATE event_groups SET commit_sequence = 9 WHERE group_id = ?",
                ("tamper-group-2",),
            )
            connection.commit()
        assert not tamper_store.integrity_check()

        # A permutation preserves the contiguous sequence set {1, 2}; the
        # hash chain must still detect that historical group order was changed.
        reorder_db = Path(directory) / "commit-sequence-reorder.sqlite3"
        reorder_store = FinancialEventStore(reorder_db)
        reorder_store.append_group("order-group-1", (first_event,))
        reorder_store.append_group("order-group-2", (second_event,))
        with closing(sqlite3.connect(reorder_db)) as connection:
            connection.execute("DROP TRIGGER event_groups_no_update")
            connection.execute(
                "UPDATE event_groups SET commit_sequence = 3 WHERE group_id = ?",
                ("order-group-1",),
            )
            connection.execute(
                "UPDATE event_groups SET commit_sequence = 1 WHERE group_id = ?",
                ("order-group-2",),
            )
            connection.execute(
                "UPDATE event_groups SET commit_sequence = 2 WHERE group_id = ?",
                ("order-group-1",),
            )
            connection.commit()
            assert [row[0] for row in connection.execute(
                "SELECT commit_sequence FROM event_groups ORDER BY commit_sequence"
            )] == [1, 2]
        assert not reorder_store.integrity_check()

        # An out-of-band extra posting is detectable even if SQLite itself
        # remains structurally valid and foreign keys still hold.
        with closing(sqlite3.connect(database)) as connection:
            connection.execute(
                "INSERT INTO journal_lines(event_id, line_no, posting_json) "
                "VALUES (?, ?, ?)",
                ("loan-1", 99, '{"account":"tampered","side":"D","amount":"1","entity_id":"x"}'),
            )
            connection.commit()
        assert not reopened.integrity_check()

    print("A2.4.4 durable financial event store: PASS")
    print("event and posting rows commit atomically as one transaction group")
    print("group/event uniqueness survives store reconstruction")
    print("same-content replay is idempotent; changed-content replay is rejected")
    print("cross-group event-ID reuse and binary floating-point amounts are rejected")
    print("injected mid-write failure rolls back group, events and postings together")
    print("concurrent identical group delivery serializes to one durable insert")
    print("concurrent cross-group event-ID collision admits exactly one winner")
    print("schema-v1 migration preserves the sole historical group and stamps commit sequence 1")
    print("global commit_sequence is gap-free and hash-chain sealed independently of effective_period")
    print("concurrent distinct groups receive a unique serialized commit order")
    print("ambiguous populated v2 and unstamped-v2 migrations fail closed without fabricating chronology")
    print("single-group populated v2 migration safely assigns sequence 1")
    print("tampered global commit sequence and order permutation are detected by integrity_check")


if __name__ == "__main__":
    main()
