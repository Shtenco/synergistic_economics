"""Durable event-sourced capital cohort register.

Period batches are immutable. State is rebuilt through the canonical B8.1
transition function; persisted closing state is a checkpoint, not an authority.
"""
from __future__ import annotations
from contextlib import closing
from dataclasses import asdict
import hashlib, json, sqlite3
from pathlib import Path

from capital_cohort_bridge import (
    CapitalBridgeError, CapitalCohort, CohortEvent, CohortLedgerState,
    advance_cohort_period, initial_cohort_state,
)

GENESIS = "0" * 64
DOMAIN = b"SYNERGY_CAPITAL_COHORT_CHAIN_V1\\0"


class CapitalCohortStoreError(ValueError):
    pass


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _cohort_dict(row):
    return asdict(row)


def _state_dict(state):
    return {"last_processed_period":state.last_processed_period,
            "cohorts":[_cohort_dict(x) for x in state.cohorts],
            "processed_event_ids":sorted(state.processed_event_ids)}


def _state_from(value):
    return CohortLedgerState(
        value["last_processed_period"],
        tuple(CapitalCohort(**x) for x in value["cohorts"]),
        frozenset(value["processed_event_ids"]),
    )


def _event_dict(row):
    return asdict(row)


def _event_from(value):
    return CohortEvent(**value)


def _hash(sequence, period, payload_hash, state_hash, previous):
    value={"sequence":sequence,"period":period,"payload_sha256":payload_hash,
           "state_sha256":state_hash,"previous_hash":previous}
    return hashlib.sha256(DOMAIN + _canonical(value).encode()).hexdigest()


class CapitalCohortStore:
    SCHEMA_VERSION = 1

    def __init__(self, database_path):
        self.path=str(database_path)
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        with closing(self._connect()) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS capital_cohort_meta(
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                    schema_version INTEGER NOT NULL CHECK(schema_version=1),
                    opening_state_json TEXT NOT NULL,
                    opening_state_sha256 TEXT NOT NULL,
                    period_count INTEGER NOT NULL CHECK(period_count>=0),
                    tail_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS capital_cohort_periods(
                    commit_sequence INTEGER PRIMARY KEY CHECK(commit_sequence>0),
                    period INTEGER NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    closing_state_json TEXT NOT NULL,
                    state_sha256 TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    chain_hash TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS capital_cohort_periods_no_update
                    BEFORE UPDATE ON capital_cohort_periods
                    BEGIN SELECT RAISE(ABORT,'capital cohort periods are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS capital_cohort_periods_no_delete
                    BEFORE DELETE ON capital_cohort_periods
                    BEGIN SELECT RAISE(ABORT,'capital cohort periods are immutable'); END;
            """)

    def _connect(self):
        con=sqlite3.connect(self.path,timeout=30,isolation_level=None)
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA synchronous=FULL")
        return con

    def initialize(self, cohorts):
        if not isinstance(cohorts,tuple):
            raise CapitalCohortStoreError("opening cohorts must be an immutable tuple")
        try:
            state=initial_cohort_state(cohorts)
        except CapitalBridgeError as exc:
            raise CapitalCohortStoreError(str(exc)) from exc
        encoded=_canonical(_state_dict(state))
        digest=hashlib.sha256(encoded.encode()).hexdigest()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                existing=con.execute("SELECT opening_state_sha256 FROM capital_cohort_meta WHERE singleton_id=1").fetchone()
                if existing:
                    if existing["opening_state_sha256"] != digest:
                        raise CapitalCohortStoreError("capital cohort opening snapshot already sealed with different content")
                    con.execute("COMMIT")
                    return False
                con.execute("INSERT INTO capital_cohort_meta VALUES(1,1,?,?,0,?)",(encoded,digest,GENESIS))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise

    def append_period(self, period, events=(), additions=()):
        if not isinstance(events,tuple) or not isinstance(additions,tuple):
            raise CapitalCohortStoreError("events and additions must be immutable tuples")
        payload={"period":period,"events":[_event_dict(x) for x in events],
                 "additions":[_cohort_dict(x) for x in additions]}
        payload_json=_canonical(payload)
        payload_hash=hashlib.sha256(payload_json.encode()).hexdigest()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                meta=con.execute("SELECT * FROM capital_cohort_meta WHERE singleton_id=1").fetchone()
                if meta is None:
                    raise CapitalCohortStoreError("capital cohort opening snapshot is not initialized")
                old=con.execute("SELECT payload_sha256 FROM capital_cohort_periods WHERE period=?",(period,)).fetchone()
                if old:
                    if old["payload_sha256"] != payload_hash:
                        raise CapitalCohortStoreError("period replay conflicts with immutable event batch")
                    con.execute("ROLLBACK")
                    if not self.verify():
                        raise CapitalCohortStoreError("idempotent retry refused: cohort replay failed")
                    return False
                if meta["period_count"]:
                    last=con.execute("SELECT period,closing_state_json FROM capital_cohort_periods ORDER BY commit_sequence DESC LIMIT 1").fetchone()
                    if period != last["period"]+1:
                        raise CapitalCohortStoreError("capital periods must advance exactly once in sequence")
                    opening=_state_from(json.loads(last["closing_state_json"]))
                else:
                    if not isinstance(period,int) or isinstance(period,bool) or period < 0:
                        raise CapitalCohortStoreError("period must be a non-negative integer")
                    opening=_state_from(json.loads(meta["opening_state_json"]))
                try:
                    result=advance_cohort_period(opening,events,additions,period)
                except CapitalBridgeError as exc:
                    raise CapitalCohortStoreError(str(exc)) from exc
                closing_json=_canonical(_state_dict(result.state))
                state_hash=hashlib.sha256(closing_json.encode()).hexdigest()
                seq=meta["period_count"]+1
                chain=_hash(seq,period,payload_hash,state_hash,meta["tail_hash"])
                con.execute("INSERT INTO capital_cohort_periods VALUES(?,?,?,?,?,?,?,?)",
                    (seq,period,payload_json,payload_hash,closing_json,state_hash,meta["tail_hash"],chain))
                con.execute("UPDATE capital_cohort_meta SET period_count=?,tail_hash=? WHERE singleton_id=1",
                    (seq,chain))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise

    def current_state(self):
        with closing(self._connect()) as con:
            meta=con.execute("SELECT * FROM capital_cohort_meta WHERE singleton_id=1").fetchone()
            if meta is None: raise CapitalCohortStoreError("capital cohort store is not initialized")
            row=con.execute("SELECT closing_state_json FROM capital_cohort_periods ORDER BY commit_sequence DESC LIMIT 1").fetchone()
            return _state_from(json.loads(row["closing_state_json"] if row else meta["opening_state_json"]))

    def verify(self):
        try:
            with closing(self._connect()) as con:
                meta=con.execute("SELECT * FROM capital_cohort_meta WHERE singleton_id=1").fetchone()
                if meta is None or meta["schema_version"] != self.SCHEMA_VERSION: return False
                opening=json.loads(meta["opening_state_json"])
                if _canonical(opening) != meta["opening_state_json"]: return False
                if hashlib.sha256(meta["opening_state_json"].encode()).hexdigest() != meta["opening_state_sha256"]: return False
                state=_state_from(opening)
                rows=con.execute("SELECT * FROM capital_cohort_periods ORDER BY commit_sequence").fetchall()
                previous,seen_period=GENESIS,None
                for seq,row in enumerate(rows,1):
                    payload=json.loads(row["payload_json"])
                    if _canonical(payload) != row["payload_json"]: return False
                    if row["commit_sequence"] != seq or row["previous_hash"] != previous: return False
                    if payload["period"] != row["period"]: return False
                    if seen_period is not None and row["period"] != seen_period+1: return False
                    payload_hash=hashlib.sha256(row["payload_json"].encode()).hexdigest()
                    if payload_hash != row["payload_sha256"]: return False
                    events=tuple(_event_from(x) for x in payload["events"])
                    additions=tuple(CapitalCohort(**x) for x in payload["additions"])
                    result=advance_cohort_period(state,events,additions,row["period"])
                    state_json=_canonical(_state_dict(result.state))
                    state_hash=hashlib.sha256(state_json.encode()).hexdigest()
                    if state_json != row["closing_state_json"] or state_hash != row["state_sha256"]: return False
                    chain=_hash(seq,row["period"],payload_hash,state_hash,previous)
                    if chain != row["chain_hash"]: return False
                    state=result.state
                    previous,seen_period=chain,row["period"]
                return meta["period_count"] == len(rows) and meta["tail_hash"] == previous
        except (sqlite3.DatabaseError,ValueError,TypeError,KeyError,AttributeError,CapitalBridgeError):
            return False
