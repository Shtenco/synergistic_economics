"""Adversarial controls for the canonical GOLD-2A journal-to-store adapter."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))
AUDIT_DIR = ROOT / "research" / "audits" / "sfc_scce_a2_4_2026-11-11"

from entity_journal import EntityJournal, EntityJournalError, EntityRegistry, JournalEvent, LegalEvidence, SectorMembership, make_line
from financial_event_store import FinancialEventStore
from financial_journal_adapter import JournalStoreAdapterError, _posting_payload, append_validated_group
from sfc_projection_store import _map_event


def _corpus_events():
    corpus = json.loads((AUDIT_DIR / "SFC_GOLD_2A_CORPUS.json").read_text(encoding="utf-8"))
    registry = EntityRegistry(tuple(SectorMembership(r["entity_id"], r["sector"], 0) for r in corpus["entities"]))
    events = []
    for raw in corpus["events"]:
        period = raw["effective_period"]
        lines = tuple(make_line(
            registry, period, p["account"], p["side"], Decimal(p["amount"]), p["entity_id"],
            counterparty=p.get("counterparty_entity_id"), issuer=p.get("issuer_entity_id"),
            instrument_id=p.get("instrument_id"), instrument_class=p.get("instrument_class"),
            currency=p.get("currency"), maturity=p.get("maturity"),
            denomination=p.get("denomination"), valuation_basis=p.get("valuation_basis"),
        ) for p in raw["postings"])
        if raw["event_type"] == "impairment_allowance_recognition":
            # Explicit synthetic reporting basis for this frozen test corpus.
            lines = tuple(replace(line, currency="LCU", valuation_basis="NOMINAL")
                          if line.account == "impairment_allowance" else line
                          for line in lines)
        evidence = None
        if raw["event_type"] == "legal_debt_forgiveness":
            # Evidence is supplied by the integration fixture; the frozen corpus stays immutable.
            evidence = LegalEvidence(
                "GOLD-2A-TEST-LEGAL-AUTHORITY", "fixture-authorized-creditor-resolution",
                "period:4", "principal:5", ("bank-1", "borrower-1"))
        events.append(JournalEvent(
            raw["event_id"], raw["event_type"], period, lines, raw["component"],
            raw["legal_effect"],
            Decimal(raw["writeoff_claim_delta"]) if raw.get("writeoff_claim_delta") is not None else None,
            Decimal(raw["forgiven_principal"]) if raw.get("forgiven_principal") is not None else None,
            evidence,
        ))
    return registry, tuple(events)


def _must_reject(call, expected, message):
    try:
        call()
    except expected:
        return
    raise AssertionError(message)


def main():
    registry, events = _corpus_events()
    assert len(events) == 7
    _must_reject(lambda: EntityJournal(registry).post(replace(events[5], event_type="creditor_writeoff")),
                 EntityJournalError, "legacy creditor_writeoff alias was accepted")
    _must_reject(lambda: EntityJournal(registry).post(replace(events[2], component="V")),
                 EntityJournalError, "interest_payment with wrong T/V/O component was accepted")
    _must_reject(lambda: EntityJournal(registry).post(replace(events[6], legal_evidence=None)),
                 EntityJournalError, "legal forgiveness without legal evidence was accepted")
    bad_allowance = replace(events[3], lines=tuple(
        replace(line, currency=None, valuation_basis=None)
        if line.account == "impairment_allowance" else line
        for line in events[3].lines))
    _must_reject(lambda: EntityJournal(registry).post(bad_allowance),
                 EntityJournalError, "impairment control without explicit valuation dimensions was accepted")
    _must_reject(lambda: _posting_payload(replace(events[1].lines[1], currency="")),
                 JournalStoreAdapterError, "empty optional field was silently discarded")
    usd_allowance = replace(events[3], lines=tuple(
        replace(line, currency="USD") if line.account == "impairment_allowance" else line
        for line in events[3].lines))
    assert _map_event(usd_allowance)[1][0][3:5] == ("USD", "NOMINAL")

    # A non-instrument journal line retains absent dimensions as absent.
    payload = _posting_payload(events[1].lines[1])
    assert "issuer_entity_id" not in payload and "currency" not in payload

    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "gold2a.sqlite3"
        store = FinancialEventStore(database)
        journal = EntityJournal(registry)
        assert append_validated_group(journal, store, "gold2a-complete", events,
                                      causation_id="gold2a-control-run") is True
        assert store.counts() == {
            "groups": 1, "events": 7,
            "journal_lines": sum(len(event.lines) for event in events),
        }
        saved = store.get_group("gold2a-complete")
        assert [e["event_type"] for e in saved["events"]] == [e.event_type for e in events]
        allowance_posting = next(p for p in saved["events"][3]["postings"]
                                 if p["account"] == "impairment_allowance")
        assert allowance_posting["currency"] == "LCU"
        assert allowance_posting["valuation_basis"] == "NOMINAL"
        writeoff = saved["events"][5]
        assert (writeoff["component"], writeoff["legal_effect"], writeoff["writeoff_claim_delta"]) == (
            "O", "accounting_derecognition_no_legal_extinguishment", "15")
        forgiveness = saved["events"][6]
        assert forgiveness["forgiven_principal"] == "5"
        assert forgiveness["legal_evidence"]["evidence_ref"] == "GOLD-2A-TEST-LEGAL-AUTHORITY"
        assert forgiveness["legal_evidence"]["parties"] == ["bank-1", "borrower-1"]
        assert store.integrity_check()

        reopened = FinancialEventStore(database)
        replay_journal = EntityJournal(registry)
        assert append_validated_group(replay_journal, reopened, "gold2a-complete", events,
                                      causation_id="gold2a-control-run") is False
        assert reopened.counts()["events"] == 7

        bad_events = events[:6] + (replace(events[6], forgiven_principal=Decimal("6")),)
        bad_journal = EntityJournal(registry)
        before = reopened.counts()
        _must_reject(lambda: append_validated_group(bad_journal, reopened, "bad-gold2a", bad_events),
                     EntityJournalError, "incorrect forgiveness amount was accepted")
        assert bad_journal.events == {} and reopened.get_group("bad-gold2a") is None
        assert reopened.counts() == before

        failure_db = Path(directory) / "gold2a-failure.sqlite3"
        failure_store = FinancialEventStore(failure_db)
        with closing(sqlite3.connect(failure_db)) as connection:
            connection.execute("""
                CREATE TRIGGER fail_adapter_posting
                BEFORE INSERT ON journal_lines
                BEGIN SELECT RAISE(ABORT, 'injected adapter write failure'); END
            """)
        failure_journal = EntityJournal(registry)
        _must_reject(lambda: append_validated_group(failure_journal, failure_store, "failure", events[:1]),
                     sqlite3.IntegrityError, "injected SQLite failure was not surfaced")
        assert failure_journal.events == {}
        assert failure_store.counts() == {"groups": 0, "events": 0, "journal_lines": 0}
        assert failure_store.integrity_check()

        class FakeJournal:
            def __init__(self): self.events = {}
            def post(self, event):
                self.events[event.event_id] = event
                return Decimal(1), Decimal(1)
        _must_reject(lambda: append_validated_group(FakeJournal(), reopened, "fake", events[:1]),
                     JournalStoreAdapterError, "duck-typed journal bypassed canonical validation")
        _must_reject(lambda: append_validated_group(EntityJournal(registry), reopened, "raw", ({"event_id":"fake"},)),
                     JournalStoreAdapterError, "raw mapping bypassed canonical validation")

    print("A2.4.4 canonical GOLD-2A journal adapter: PASS")
    print("seven canonical event types, T/V/O and legal-effect semantics validated")
    print("legal evidence and write-off/forgiveness metadata survive durable serialization")
    print("legacy aliases, fake journals, empty optional fields and malformed events rejected")
    print("replay idempotency and validation/SQLite rollback controls passed")


if __name__ == "__main__":
    main()
