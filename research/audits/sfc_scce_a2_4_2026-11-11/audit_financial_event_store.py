"""Adversarial controls for the durable A2.4.4 financial event store."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile

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


def main():
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "financial-events.sqlite3"
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


if __name__ == "__main__":
    main()
