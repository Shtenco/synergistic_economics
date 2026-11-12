"""End-to-end atomic P2, period carry-forward and recovery controls for GOLD-2A."""
from contextlib import closing
from decimal import Decimal
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))
AUDIT_DIR = ROOT / "research" / "audits" / "sfc_scce_a2_4_2026-11-11"

from audit_financial_journal_adapter import _corpus_events
from entity_journal import EntityJournal
from financial_event_store import FinancialEventStore
from sfc_projection_registry import activate_sfc_projection
from sfc_projection_store import (
    SFCProjectionStoreError, activate_control_openings,
    append_projected_group, verify_projection_replay,
)


def _activate(store):
    import json
    corpus = json.loads((AUDIT_DIR / "SFC_GOLD_2A_CORPUS.json").read_text(encoding="utf-8"))
    opening = corpus["opening_snapshot"]
    assert activate_sfc_projection(
        store, opening["rows"], mapper_version=opening["mapper_version"],
        evidence_ref=opening["evidence_ref"]) is True
    controls = (
        {"control_id":"impairment_allowance","entity_id":"bank-1","sector":"CB",
         "currency":"LCU","valuation_basis":"NOMINAL","period":0,"amount":"0",
         "evidence_ref":"GOLD2A:synthetic-opening-v1"},
        {"control_id":"writeoff_memorandum","entity_id":"bank-1","sector":"CB",
         "currency":"LCU","valuation_basis":"NOMINAL","period":0,"amount":"0",
         "evidence_ref":"GOLD2A:synthetic-opening-v1"},
    )
    assert activate_control_openings(
        store, controls, mapper_version="gold2a-controls@1",
        evidence_ref="GOLD2A:synthetic-opening-v1") is True


def main():
    registry, events = _corpus_events()
    with tempfile.TemporaryDirectory() as directory:
        database = Path(directory) / "p2.sqlite3"
        store = FinancialEventStore(database)
        _activate(store)
        journal = EntityJournal(registry)
        assert append_projected_group(
            journal, store, "gold2a-p2", events,
            causation_id="gold2a-atomic-control") is True
        assert store.counts() == {
            "groups":1, "events":7,
            "journal_lines":sum(len(event.lines) for event in events),
        }
        assert verify_projection_replay(store)

        with closing(store._connect()) as con:
            runtime = con.execute("SELECT * FROM sfc_projection_runtime WHERE singleton_id=1").fetchone()
            assert runtime["applied_commit_sequence"] == 1
            assert runtime["current_period"] == 4
            positions = {r["instrument_id"]:Decimal(r["closing_balance"]) for r in con.execute(
                "SELECT instrument_id,closing_balance FROM sfc_projection_positions WHERE period=4")}
            controls = {r["control_id"]:Decimal(r["closing_balance"]) for r in con.execute(
                "SELECT control_id,closing_balance FROM sfc_control_positions WHERE period=4")}
            assert positions == {"LOAN-001":Decimal("60"),"DEP-001":Decimal("76"),"INT-001":Decimal("6")}
            assert controls == {"impairment_allowance":Decimal("5"),"writeoff_memorandum":Decimal("15")}
            allowance_position = con.execute("""SELECT currency,valuation_basis,closing_balance
                FROM sfc_control_positions WHERE control_id='impairment_allowance' AND period=4""").fetchone()
            assert tuple(allowance_position) == ("LCU","NOMINAL","5")
            assert con.execute("SELECT COUNT(*) FROM sfc_event_coverage").fetchone()[0] == 7
            assert con.execute("SELECT COUNT(*) FROM sfc_projection_event_checkpoints").fetchone()[0] == 7
            assert con.execute("SELECT COUNT(*) FROM sfc_projection_group_checkpoints").fetchone()[0] == 1
            # The same period-0 opening is carried forward automatically.
            assert con.execute("SELECT COUNT(*) FROM sfc_projection_positions").fetchone()[0] == 15
            assert con.execute("SELECT COUNT(*) FROM sfc_control_positions").fetchone()[0] == 10

        # An identical retry after restart does not append or reapply deltas.
        reopened = FinancialEventStore(database)
        replay_journal = EntityJournal(registry)
        assert append_projected_group(
            replay_journal, reopened, "gold2a-p2", events,
            causation_id="gold2a-atomic-control") is False
        assert reopened.counts()["events"] == 7
        assert verify_projection_replay(reopened)

        # A late-arriving backdated event must be rejected, not inserted into
        # an already-applied historical prefix.
        late = replace_event_period(events[4], 3)
        late_journal = EntityJournal(registry)
        try:
            append_projected_group(late_journal, reopened, "late-period", (late,))
        except SFCProjectionStoreError:
            pass
        else:
            raise AssertionError("backdated event was accepted without period reopen")
        assert late_journal.events == {}
        assert reopened.get_group("late-period") is None
        assert verify_projection_replay(reopened)

        # Inject failure at the first control-delta write. Event rows, instrument
        # deltas, controls, checkpoints and cursor must all roll back together.
        failure_db = Path(directory) / "p2-failure.sqlite3"
        failure_store = FinancialEventStore(failure_db)
        _activate(failure_store)
        from sfc_projection_store import _schema
        with closing(failure_store._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            _schema(con)
            con.execute("COMMIT")
            con.execute("""CREATE TRIGGER fail_projection_control
                BEFORE INSERT ON sfc_control_deltas
                BEGIN SELECT RAISE(ABORT,'injected projection failure'); END""")
        failure_journal = EntityJournal(registry)
        try:
            append_projected_group(failure_journal,failure_store,"atomic-failure",events)
        except sqlite3.IntegrityError:
            pass
        else:
            raise AssertionError("injected projection failure was not surfaced")
        assert failure_journal.events == {}
        assert failure_store.counts() == {"groups":0,"events":0,"journal_lines":0}
        with closing(failure_store._connect()) as con:
            runtime=con.execute("SELECT applied_commit_sequence,current_period FROM sfc_projection_runtime").fetchone()
            assert runtime is None or tuple(runtime)==(0,0)
            assert con.execute("SELECT COUNT(*) FROM sfc_projection_event_checkpoints").fetchone()[0] == 0
            assert con.execute("SELECT COUNT(*) FROM sfc_projection_positions WHERE period=1").fetchone()[0] == 0
            con.execute("DROP TRIGGER fail_projection_control")
        assert append_projected_group(
            EntityJournal(registry),failure_store,"atomic-failure",events) is True
        assert verify_projection_replay(failure_store)

        # A changed materialized balance is detected by independent replay.
        with closing(reopened._connect()) as con:
            con.execute("""UPDATE sfc_projection_positions SET closing_balance='61'
                WHERE instrument_id='LOAN-001' AND period=4""")
        assert verify_projection_replay(reopened) is False
        corrupted_retry_journal = EntityJournal(registry)
        try:
            append_projected_group(
                corrupted_retry_journal,reopened,"gold2a-p2",events,
                causation_id="gold2a-atomic-control")
        except SFCProjectionStoreError:
            pass
        else:
            raise AssertionError("idempotent retry accepted a corrupted materialized projection")
        assert corrupted_retry_journal.events == {}

    print("A2.4.4 P2 projection-aware atomic append: PASS")
    print("event journal, instrument/control positions, per-event coverage and cursor committed atomically")
    print("closing-to-opening carry-forward and GOLD-2A final balances verified")
    print("restart idempotency, backdated-event rejection and injected rollback verified")
    print("independent replay detects materialized-position tampering")


def replace_event_period(event, period):
    from dataclasses import replace
    return replace(event, event_id="late-arriving-backdated-event", effective_period=period)


if __name__ == "__main__":
    main()
