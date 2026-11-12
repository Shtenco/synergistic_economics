"""Adversarial controls for the validated journal-to-store adapter."""
from contextlib import closing
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))
AUDIT_DIR = ROOT / "research" / "audits" / "sfc_scce_a2_4_2026-11-11"
sys.path.insert(0, str(AUDIT_DIR))

from financial_event_store import FinancialEventStore
from financial_journal_adapter import (
    JournalStoreAdapterError,
    _posting_payload,
    append_validated_group,
)
from audit_entity_sector_journal import (
    EntityJournal,
    EntityRegistry,
    IdentityError,
    JournalEvent,
    SectorMembership,
    make_line,
)


def _fixture():
    registry = EntityRegistry((
        SectorMembership("bank-1", "CB", 0),
        SectorMembership("household-1", "H", 0),
        SectorMembership("company-2", "NFC", 0),
    ))
    period = 1
    # Non-instrument lines retain absent dimensions as absent. Explicit
    # dimensions, including an explicitly selected local currency, survive.
    expense = make_line(registry, period, "ordinary_expense", "D", 1, "household-1")
    expense_payload = _posting_payload(expense)
    assert expense.counterparty_entity_id is None
    assert expense.issuer_entity_id is None
    assert expense.currency is None
    assert "currency" not in expense_payload
    assert "instrument_id" not in expense_payload
    explicit_currency = make_line(
        registry, period, "ordinary_expense", "D", 1, "household-1",
        currency="LCU")
    assert _posting_payload(explicit_currency)["currency"] == "LCU"
    loan = JournalEvent("loan-1", "nonbank_loan_origination", period, (
        make_line(registry, period, "loan_asset", "D", 19, "household-1",
                  issuer="company-2", instrument_id="loan-hc",
                  instrument_class="loan", maturity="2029"),
        make_line(registry, period, "loan_liability", "C", 19, "company-2",
                  counterparty="household-1", issuer="company-2",
                  instrument_id="loan-hc", instrument_class="loan",
                  maturity="2029"),
    ))
    transfer = JournalEvent("transfer-1", "nonbank_deposit_transfer", period, (
        make_line(registry, period, "deposit_asset", "C", 19, "household-1",
                  issuer="bank-1", instrument_id="deposit-h",
                  instrument_class="deposit"),
        make_line(registry, period, "deposit_liability", "D", 19, "bank-1",
                  counterparty="household-1", issuer="bank-1",
                  instrument_id="deposit-h", instrument_class="deposit"),
        make_line(registry, period, "deposit_asset", "D", 19, "company-2",
                  issuer="bank-1", instrument_id="deposit-c",
                  instrument_class="deposit"),
        make_line(registry, period, "deposit_liability", "C", 19, "bank-1",
                  counterparty="company-2", issuer="bank-1",
                  instrument_id="deposit-c", instrument_class="deposit"),
    ))
    return registry, loan, transfer


def _must_reject(call, expected, message):
    try:
        call()
    except expected:
        return
    raise AssertionError(message)


def main():
    registry, loan, transfer = _fixture()
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "adapter.sqlite3"
        store = FinancialEventStore(database)
        journal = EntityJournal(registry)

        assert append_validated_group(
            journal, store, "credit-tx-1", (loan, transfer),
            causation_id="credit-agreement-1") is True
        assert set(journal.events) == {"loan-1", "transfer-1"}
        assert store.counts() == {
            "groups": 1, "events": 2, "journal_lines": 6,
        }
        saved = store.get_group("credit-tx-1")
        assert saved["causation_id"] == "credit-agreement-1"
        saved_loan = saved["events"][0]
        assert saved_loan["event_type"] == "nonbank_loan_origination"
        first_line = saved_loan["postings"][0]
        assert first_line["amount"] == "19"
        assert first_line["entity_id"] == "household-1"
        assert first_line["issuer_entity_id"] == "company-2"
        assert first_line["institutional_sector"] == "H"
        assert first_line["issuer_sector"] == "NFC"
        assert first_line["instrument_id"] == "loan-hc"
        assert store.integrity_check()

        # Reopen both sides. A fresh EntityJournal validates the events again;
        # the durable store recognizes the exact group replay without writing.
        reopened_store = FinancialEventStore(database)
        replay_journal = EntityJournal(registry)
        assert append_validated_group(
            replay_journal, reopened_store, "credit-tx-1", (loan, transfer),
            causation_id="credit-agreement-1") is False
        assert set(replay_journal.events) == {"loan-1", "transfer-1"}
        assert reopened_store.counts() == {
            "groups": 1, "events": 2, "journal_lines": 6,
        }

        # If a later event fails accounting validation, earlier events from
        # this call are removed from the in-memory journal and nothing reaches
        # the durable store.
        bad = JournalEvent("bad-loan", "nonbank_loan_origination", 1, (
            make_line(registry, 1, "loan_asset", "D", 19, "household-1",
                      issuer="company-2", instrument_id="bad-loan",
                      instrument_class="loan"),
            make_line(registry, 1, "loan_liability", "C", 18, "company-2",
                      counterparty="household-1", issuer="company-2",
                      instrument_id="bad-loan", instrument_class="loan"),
        ))
        rollback_journal = EntityJournal(registry)
        before = reopened_store.counts()
        _must_reject(
            lambda: append_validated_group(
                rollback_journal, reopened_store, "bad-group", (loan, bad)),
            IdentityError,
            "unbalanced second event was accepted",
        )
        assert rollback_journal.events == {}
        assert reopened_store.get_group("bad-group") is None
        assert reopened_store.counts() == before

        # A durable write failure after successful journal validation must
        # also undo the in-memory journal mutations.
        failure_db = Path(directory) / "adapter-failure.sqlite3"
        failure_store = FinancialEventStore(failure_db)
        with closing(sqlite3.connect(failure_db)) as connection:
            connection.execute("""
                CREATE TRIGGER fail_adapter_posting
                BEFORE INSERT ON journal_lines
                BEGIN SELECT RAISE(ABORT, 'injected adapter write failure'); END
            """)
        failure_journal = EntityJournal(registry)
        _must_reject(
            lambda: append_validated_group(
                failure_journal, failure_store, "failure-group", (loan,)),
            sqlite3.IntegrityError,
            "injected durable-store failure was not surfaced",
        )
        assert failure_journal.events == {}
        assert failure_store.counts() == {
            "groups": 0, "events": 0, "journal_lines": 0,
        }
        assert failure_store.integrity_check()

        # Arbitrary mappings cannot masquerade as validated JournalEvent data.
        _must_reject(
            lambda: append_validated_group(
                EntityJournal(registry), reopened_store, "raw-dict-group",
                ({"event_id": "fake"},)),
            (IdentityError, JournalStoreAdapterError, AttributeError),
            "untyped event mapping bypassed the journal validator",
        )

    print("A2.4.4 validated journal adapter: PASS")
    print("EntityJournal validation precedes serialization and durable append")
    print("entity/sector/issuer/instrument dimensions survive the adapter")
    print("replay after restart is idempotent")
    print("validation and storage failures roll back adapter-owned in-memory entries")


if __name__ == "__main__":
    main()
