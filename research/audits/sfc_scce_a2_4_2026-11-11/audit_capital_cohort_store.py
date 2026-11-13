"""Durable B8.1 capital cohort register: atomic periods, replay and tamper rejection."""
from contextlib import closing
from dataclasses import replace
from pathlib import Path
import sqlite3, sys, tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"prototype"))
from capital_cohort_bridge import CapitalCohort,CohortEvent
from capital_cohort_store import CapitalCohortStore,CapitalCohortStoreError


def main():
    opening=(CapitalCohort("machine-1","cell-1","machine",2020,6,10,10,
        "operating",0.9,0.8,0.95),)
    loss=(CohortEvent("loss-1","machine-1","physical_loss",2,"operating",None,"accident"),)
    addition=(CapitalCohort("machine-2","cell-1","machine",2026,0,3,10,
        "operating",0.9,0.8,0.95),)
    with tempfile.TemporaryDirectory() as tmp:
        db=Path(tmp)/"capital.sqlite3"
        store=CapitalCohortStore(db)
        assert store.initialize(opening) is True
        assert store.append_period(2026,loss,addition) is True
        state=store.current_state()
        assert state.last_processed_period==2026
        assert sum(x.quantity for x in state.cohorts if x.operating_status!="retired")==11
        assert store.verify()
        assert store.append_period(2026,loss,addition) is False
        assert store.current_state()==state
        try:
            store.append_period(2026,loss,())
        except CapitalCohortStoreError:
            pass
        else:
            raise AssertionError("changed period batch was accepted")
        # State transition splits a cohort while preserving identity and stock.
        transition=(CohortEvent("repair-1","machine-1","state_transition",1,
            "operating","repair",""),)
        assert store.append_period(2027,transition,()) is True
        assert store.verify()
        restarted=CapitalCohortStore(db)
        assert restarted.verify() and restarted.current_state().last_processed_period==2027
        try:
            restarted.append_period(2028,loss,())
        except CapitalCohortStoreError:
            pass
        else:
            raise AssertionError("reused processed event ID was accepted")
        with closing(sqlite3.connect(db)) as con:
            con.execute("DROP TRIGGER capital_cohort_periods_no_update")
            con.execute("UPDATE capital_cohort_periods SET closing_state_json='{}' WHERE period=2026")
            con.commit()
        assert restarted.verify() is False
    print("A2.4 durable B8.1 capital cohort register: PASS")
    print("opening seal, immutable period batches, stock-flow replay and same-period idempotency verified")
    print("physical loss, additions, lifecycle split, restart and tamper rejection verified")


if __name__=="__main__":
    main()
