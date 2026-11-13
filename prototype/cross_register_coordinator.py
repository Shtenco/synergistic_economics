"""Durable cross-register prepare/commit coordinator.

This module is a protocol implementation and conformance harness. SQLiteParticipant
is an independent durable participant store; domain-specific adapters must bind its
prepare/commit contract to the authoritative physical, capital, labour, product,
legal/rights and financial stores before production use.
"""
from __future__ import annotations

from contextlib import closing, contextmanager
import hashlib
import json
import os
from pathlib import Path
import sqlite3
from typing import Mapping

PARTICIPANTS = ("physical", "capital", "labour", "product", "legal_rights", "financial")
STATES = {
    "NEW", "PREPARING", "PREPARED", "ABORT_DECIDED", "ABORTED",
    "COMMIT_DECIDED", "COMMITTING", "COMMITTED",
}
CRASH_EXIT = 87


class CoordinatorError(ValueError):
    """Invalid, conflicting, or unrecoverable coordinator operation."""


def _canonical(value) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CoordinatorError("value is not canonical JSON data") from exc


def _digest(value) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()



_EVENT_GROUP_ZERO_HASH = "0" * 64


def _verify_event_group_chain(con) -> bool:
    """Verify the immutable canonical six-register event-group hash chain."""
    try:
        rows=con.execute(
            "SELECT commit_sequence,transaction_id,common_event_id,payload_json,payload_digest,previous_hash,group_hash "
            "FROM coordinator_event_groups ORDER BY commit_sequence"
        ).fetchall()
        previous=_EVENT_GROUP_ZERO_HASH
        expected_sequence=1
        for row in rows:
            if row["commit_sequence"]!=expected_sequence or row["previous_hash"]!=previous:
                return False
            raw=row["payload_json"]
            if not isinstance(raw,str): return False
            payload=json.loads(raw)
            if _canonical(payload)!=raw: return False
            digest=hashlib.sha256(raw.encode("utf-8")).hexdigest()
            if digest!=row["payload_digest"]: return False
            expected_hash=hashlib.sha256((previous+digest).encode("ascii")).hexdigest()
            if expected_hash!=row["group_hash"]: return False
            if payload.get("transaction_id")!=row["transaction_id"] or payload.get("common_event_id")!=row["common_event_id"]:
                return False
            events=payload.get("events")
            if not isinstance(events,list) or len(events)!=len(PARTICIPANTS):
                return False
            if [event.get("register_id") for event in events if isinstance(event,dict)]!=list(PARTICIPANTS):
                return False
            if any(not isinstance(event,dict) or event.get("common_event_id")!=row["transaction_id"] for event in events):
                return False
            if con.execute("SELECT 1 FROM coordinator_transactions WHERE transaction_id=?",(row["transaction_id"],)).fetchone() is None:
                return False
            previous=expected_hash
            expected_sequence+=1
        return True
    except (sqlite3.Error,TypeError,ValueError,KeyError,json.JSONDecodeError):
        return False

def _required(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise CoordinatorError(f"{field} must be trimmed non-empty text")
    return value


def _fault(point: str) -> None:
    if os.environ.get("SYNERGY_COORDINATOR_CRASH_AT") == point:
        os._exit(CRASH_EXIT)


def _connect(path):
    con = sqlite3.connect(str(path), timeout=10, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    con.execute("PRAGMA busy_timeout=10000")
    con.execute("PRAGMA synchronous=FULL")
    con.execute("PRAGMA journal_mode=WAL")
    return con


@contextmanager
def _exclusive_process_lock(path):
    """Crash-released cross-process lock shared by coordinator instances.

    The lock is a separate SQLite database so participant/coordinator writes
    can proceed while this transaction remains open. A process death releases
    the OS file lock and rolls back the empty transaction. This deliberately
    serializes execution globally; it is a local/shared-filesystem conformance
    mechanism, not a distributed lease for hosts without reliable SQLite locks.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    try:
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA journal_mode=DELETE")
        con.execute("BEGIN EXCLUSIVE")
        yield
        con.execute("COMMIT")
    except Exception:
        if con.in_transaction:
            con.execute("ROLLBACK")
        raise
    finally:
        con.close()


class SQLiteParticipant:
    """Independent durable inbox/event store for one participant role.

    This is a real SQLite participant implementation for protocol testing, not
    a substitute for a domain adapter to an existing register's authoritative DB.
    """

    def __init__(self, name: str, database_path):
        if name not in PARTICIPANTS:
            raise CoordinatorError(f"unknown participant role: {name}")
        self.name = name
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        with closing(_connect(self.database_path)) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS participant_heads(
                    stream_id TEXT PRIMARY KEY,
                    revision INTEGER NOT NULL CHECK(revision >= 0)
                );
                CREATE TABLE IF NOT EXISTS participant_inbox(
                    transaction_id TEXT PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    native_event_id TEXT NOT NULL UNIQUE,
                    payload_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL CHECK(expected_revision >= 0),
                    prepare_token TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('PREPARED','COMMITTED','ABORTED')),
                    receipt_json TEXT
                );
                CREATE TABLE IF NOT EXISTS participant_transitions(
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL REFERENCES participant_inbox(transaction_id),
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS participant_transitions_no_update
                    BEFORE UPDATE ON participant_transitions
                    BEGIN SELECT RAISE(ABORT,'participant transition history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS participant_transitions_no_delete
                    BEFORE DELETE ON participant_transitions
                    BEGIN SELECT RAISE(ABORT,'participant transition history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS participant_inbox_payload_no_update
                    BEFORE UPDATE OF transaction_id,stream_id,native_event_id,payload_digest,payload_json,expected_revision,prepare_token
                    ON participant_inbox
                    BEGIN SELECT RAISE(ABORT,'participant prepared payload is immutable'); END;
                CREATE TABLE IF NOT EXISTS participant_events(
                    native_event_id TEXT PRIMARY KEY,
                    transaction_id TEXT NOT NULL UNIQUE,
                    stream_id TEXT NOT NULL,
                    revision INTEGER NOT NULL,
                    payload_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS participant_one_prepared_per_stream
                    ON participant_inbox(stream_id) WHERE state='PREPARED';
                CREATE TRIGGER IF NOT EXISTS participant_events_no_update
                    BEFORE UPDATE ON participant_events
                    BEGIN SELECT RAISE(ABORT,'participant events are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS participant_events_no_delete
                    BEFORE DELETE ON participant_events
                    BEGIN SELECT RAISE(ABORT,'participant events are immutable'); END;
            """)

    def _token(self, txid, stream_id, native_event_id, digest, expected_revision):
        return _digest({
            "protocol": "synergy-participant-prepare-v1", "participant": self.name,
            "transaction_id": txid, "stream_id": stream_id,
            "native_event_id": native_event_id, "payload_digest": digest,
            "expected_revision": expected_revision,
        })

    def prepare(self, txid, operation):
        txid = _required(txid, "transaction_id")
        stream = _required(operation.get("stream_id"), "stream_id")
        native_id = _required(operation.get("native_event_id"), "native_event_id")
        payload = operation.get("payload")
        if not isinstance(payload, Mapping):
            raise CoordinatorError("participant payload must be a JSON object")
        payload_json = _canonical(payload)
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        revision = operation.get("expected_revision")
        if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
            raise CoordinatorError("expected_revision must be a non-negative integer")
        token = self._token(txid, stream, native_id, digest, revision)
        with closing(_connect(self.database_path)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute(
                    "SELECT * FROM participant_inbox WHERE transaction_id=?", (txid,)
                ).fetchone()
                if old:
                    if (old["stream_id"], old["native_event_id"], old["payload_digest"],
                        old["expected_revision"], old["prepare_token"]) != (
                        stream, native_id, digest, revision, token):
                        raise CoordinatorError("participant transaction ID reused with changed content")
                    if old["state"] == "ABORTED":
                        raise CoordinatorError("aborted participant transaction cannot be prepared again")
                    con.execute("COMMIT")
                    return token
                head = con.execute(
                    "SELECT revision FROM participant_heads WHERE stream_id=?", (stream,)
                ).fetchone()
                current = head["revision"] if head else 0
                if current != revision:
                    raise CoordinatorError(
                        f"{self.name} stale revision: expected {revision}, current {current}"
                    )
                con.execute("""INSERT INTO participant_inbox(
                    transaction_id,stream_id,native_event_id,payload_digest,payload_json,
                    expected_revision,prepare_token,state)
                    VALUES(?,?,?,?,?,?,?,'PREPARED')""",
                    (txid, stream, native_id, digest, payload_json, revision, token))
                con.execute("""INSERT INTO participant_transitions(
                    transaction_id,from_state,to_state,reason) VALUES(?,NULL,'PREPARED','prepare')""",
                    (txid,))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        _fault(f"after_prepare:{self.name}")
        return token

    def commit(self, txid, token):
        with closing(_connect(self.database_path)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row = con.execute(
                    "SELECT * FROM participant_inbox WHERE transaction_id=?", (txid,)
                ).fetchone()
                if row is None or row["prepare_token"] != token:
                    raise CoordinatorError("missing or mismatched durable prepare token")
                if row["state"] == "COMMITTED":
                    receipt = json.loads(row["receipt_json"])
                    con.execute("COMMIT")
                    return receipt
                if row["state"] != "PREPARED":
                    raise CoordinatorError("participant is not in PREPARED state")
                head = con.execute(
                    "SELECT revision FROM participant_heads WHERE stream_id=?",
                    (row["stream_id"],)
                ).fetchone()
                current = head["revision"] if head else 0
                if current != row["expected_revision"]:
                    raise CoordinatorError("participant revision changed after prepare")
                next_revision = current + 1
                con.execute("""INSERT INTO participant_events(
                    native_event_id,transaction_id,stream_id,revision,payload_digest,payload_json)
                    VALUES(?,?,?,?,?,?)""",
                    (row["native_event_id"], txid, row["stream_id"], next_revision,
                     row["payload_digest"], row["payload_json"]))
                con.execute("""INSERT INTO participant_heads(stream_id,revision) VALUES(?,?)
                    ON CONFLICT(stream_id) DO UPDATE SET revision=excluded.revision""",
                    (row["stream_id"], next_revision))
                receipt = {
                    "participant": self.name, "transaction_id": txid,
                    "native_event_id": row["native_event_id"],
                    "payload_digest": row["payload_digest"],
                    "prepare_token": token, "revision": next_revision,
                }
                con.execute("""UPDATE participant_inbox SET state='COMMITTED',receipt_json=?
                    WHERE transaction_id=?""", (_canonical(receipt), txid))
                con.execute("""INSERT INTO participant_transitions(
                    transaction_id,from_state,to_state,reason)
                    VALUES(?,'PREPARED','COMMITTED','commit')""", (txid,))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        _fault(f"after_commit:{self.name}")
        return receipt

    def abort(self, txid):
        with closing(_connect(self.database_path)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row = con.execute(
                    "SELECT state FROM participant_inbox WHERE transaction_id=?", (txid,)
                ).fetchone()
                if row is not None:
                    if row["state"] == "COMMITTED":
                        raise CoordinatorError("cannot abort a committed participant effect")
                    if row["state"] == "PREPARED":
                        con.execute(
                            "UPDATE participant_inbox SET state='ABORTED' WHERE transaction_id=?",
                            (txid,)
                        )
                        con.execute("""INSERT INTO participant_transitions(
                            transaction_id,from_state,to_state,reason)
                            VALUES(?,'PREPARED','ABORTED','abort-before-commit-decision')""", (txid,))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def status(self, txid):
        with closing(_connect(self.database_path)) as con:
            row = con.execute(
                "SELECT state,prepare_token,receipt_json,native_event_id,payload_digest "
                "FROM participant_inbox WHERE transaction_id=?", (txid,)
            ).fetchone()
            return dict(row) if row else None

    def event_count(self, txid):
        with closing(_connect(self.database_path)) as con:
            return con.execute(
                "SELECT COUNT(*) FROM participant_events WHERE transaction_id=?", (txid,)
            ).fetchone()[0]

    def committed_event(self, txid):
        """Return the persisted native event, not merely its inbox receipt."""
        with closing(_connect(self.database_path)) as con:
            row = con.execute(
                "SELECT native_event_id,stream_id,revision,payload_digest,payload_json "
                "FROM participant_events WHERE transaction_id=?", (txid,)
            ).fetchone()
            return dict(row) if row else None


class CrossRegisterCoordinator:
    """Durable coordinator with an irreversible commit decision and read barrier."""

    def __init__(self, database_path, participants: Mapping[str, SQLiteParticipant]):
        if set(participants) != set(PARTICIPANTS):
            raise CoordinatorError("exactly six named participants are required")
        if any(participants[name].name != name for name in PARTICIPANTS):
            raise CoordinatorError("participant mapping/name mismatch")
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.execution_lock_path = self.database_path.with_name(
            self.database_path.name + ".execution-lock.sqlite3"
        )
        self.participants = dict(participants)
        with closing(_connect(self.database_path)) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS coordinator_transactions(
                    transaction_id TEXT PRIMARY KEY,
                    envelope_json TEXT NOT NULL,
                    envelope_digest TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN
                      ('NEW','PREPARING','PREPARED','ABORT_DECIDED','ABORTED',
                       'COMMIT_DECIDED','COMMITTING','COMMITTED'))
                );
                CREATE TABLE IF NOT EXISTS coordinator_transitions(
                    transition_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    transaction_id TEXT NOT NULL REFERENCES coordinator_transactions(transaction_id),
                    from_state TEXT,
                    to_state TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS coordinator_transitions_no_update
                    BEFORE UPDATE ON coordinator_transitions
                    BEGIN SELECT RAISE(ABORT,'coordinator transition history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS coordinator_transitions_no_delete
                    BEFORE DELETE ON coordinator_transitions
                    BEGIN SELECT RAISE(ABORT,'coordinator transition history is immutable'); END;
                CREATE TABLE IF NOT EXISTS coordinator_operations(
                    transaction_id TEXT NOT NULL REFERENCES coordinator_transactions(transaction_id),
                    participant TEXT NOT NULL,
                    stream_id TEXT NOT NULL,
                    native_event_id TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('PENDING','PREPARED','COMMITTED','ABORTED')),
                    prepare_token TEXT,
                    receipt_json TEXT,
                    PRIMARY KEY(transaction_id,participant),
                    UNIQUE(participant,native_event_id)
                );
                CREATE TRIGGER IF NOT EXISTS coordinator_transactions_payload_no_update
                    BEFORE UPDATE OF transaction_id,envelope_json,envelope_digest ON coordinator_transactions
                    BEGIN SELECT RAISE(ABORT,'coordinator transaction envelope is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS coordinator_transactions_no_delete
                    BEFORE DELETE ON coordinator_transactions
                    BEGIN SELECT RAISE(ABORT,'coordinator history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS coordinator_operations_payload_no_update
                    BEFORE UPDATE OF transaction_id,participant,stream_id,native_event_id,payload_json,payload_digest,expected_revision ON coordinator_operations
                    BEGIN SELECT RAISE(ABORT,'coordinator operation payload is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS coordinator_operations_no_delete
                    BEFORE DELETE ON coordinator_operations
                    BEGIN SELECT RAISE(ABORT,'coordinator operations are immutable'); END;
                CREATE TABLE IF NOT EXISTS coordinator_event_groups(
                    commit_sequence INTEGER PRIMARY KEY CHECK(commit_sequence>0),
                    transaction_id TEXT NOT NULL UNIQUE REFERENCES coordinator_transactions(transaction_id),
                    common_event_id TEXT NOT NULL UNIQUE,
                    payload_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    group_hash TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS coordinator_event_groups_no_update
                    BEFORE UPDATE ON coordinator_event_groups
                    BEGIN SELECT RAISE(ABORT,'canonical event groups are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS coordinator_event_groups_no_delete
                    BEFORE DELETE ON coordinator_event_groups
                    BEGIN SELECT RAISE(ABORT,'canonical event-group history is immutable'); END;
            """)
        self._backfill_event_groups()

    def _set_state(self, txid, state):
        if state not in STATES:
            raise CoordinatorError("invalid coordinator state")
        with closing(_connect(self.database_path)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute(
                    "SELECT state FROM coordinator_transactions WHERE transaction_id=?", (txid,)
                ).fetchone()
                if old is None:
                    raise CoordinatorError("unknown coordinator transaction")
                current = old["state"]
                allowed = {
                    "NEW": {"PREPARING", "ABORT_DECIDED"},
                    "PREPARING": {"PREPARED", "ABORT_DECIDED"},
                    "PREPARED": {"COMMIT_DECIDED", "ABORT_DECIDED"},
                    "ABORT_DECIDED": {"ABORTED"},
                    "ABORTED": set(),
                    "COMMIT_DECIDED": {"COMMITTING"},
                    "COMMITTING": {"COMMITTED"},
                    "COMMITTED": set(),
                }
                if current == state:
                    con.execute("COMMIT")
                    return
                if state not in allowed.get(current, set()):
                    raise CoordinatorError(f"illegal coordinator transition: {current} -> {state}")
                con.execute(
                    "UPDATE coordinator_transactions SET state=? WHERE transaction_id=?",
                    (state, txid)
                )
                con.execute("""INSERT INTO coordinator_transitions(
                    transaction_id,from_state,to_state,reason) VALUES(?,?,?,?)""",
                    (txid, current, state, "protocol"))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def submit(self, transaction_id, scenario_id, causation_id, operations):
        txid = _required(transaction_id, "transaction_id")
        envelope = {
            "transaction_id": txid,
            "scenario_id": _required(scenario_id, "scenario_id"),
            "causation_id": _required(causation_id, "causation_id"),
            "schema_version": 1,
            "participants": [],
        }
        if not isinstance(operations, Mapping) or set(operations) != set(PARTICIPANTS):
            raise CoordinatorError("transaction must contain one operation for each of six participants")
        rows = []
        for name in PARTICIPANTS:
            op = operations[name]
            if not isinstance(op, Mapping):
                raise CoordinatorError(f"{name} operation must be a mapping")
            stream = _required(op.get("stream_id"), f"{name}.stream_id")
            native_id = _required(op.get("native_event_id"), f"{name}.native_event_id")
            payload = op.get("payload")
            if not isinstance(payload, Mapping):
                raise CoordinatorError(f"{name}.payload must be a JSON object")
            from register_event_contract import normalize_event_envelope
            try:
                payload = normalize_event_envelope(name, payload)
            except ValueError as exc:
                raise CoordinatorError(f"{name} native event contract rejected: {exc}") from exc
            payload_json = _canonical(payload)
            digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
            revision = op.get("expected_revision")
            if not isinstance(revision, int) or isinstance(revision, bool) or revision < 0:
                raise CoordinatorError(f"{name}.expected_revision must be a non-negative integer")
            envelope["participants"].append({
                "name": name, "stream_id": stream, "native_event_id": native_id,
                "expected_revision": revision, "payload_digest": digest,
            })
            rows.append((name, stream, native_id, payload_json, digest, revision))
        envelope_json = _canonical(envelope)
        envelope_digest = hashlib.sha256(envelope_json.encode("utf-8")).hexdigest()
        with closing(_connect(self.database_path)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute(
                    "SELECT envelope_digest FROM coordinator_transactions WHERE transaction_id=?",
                    (txid,)
                ).fetchone()
                if old:
                    if old["envelope_digest"] != envelope_digest:
                        raise CoordinatorError("coordinator transaction ID reused with changed envelope")
                    con.execute("COMMIT")
                    return False
                con.execute("""INSERT INTO coordinator_transactions(
                    transaction_id,envelope_json,envelope_digest,state) VALUES(?,?,?,'NEW')""",
                    (txid, envelope_json, envelope_digest))
                con.execute("""INSERT INTO coordinator_transitions(
                    transaction_id,from_state,to_state,reason) VALUES(?,NULL,'NEW','submit')""",
                    (txid,))
                for name, stream, native_id, payload_json, digest, revision in rows:
                    con.execute("""INSERT INTO coordinator_operations(
                        transaction_id,participant,stream_id,native_event_id,payload_json,
                        payload_digest,expected_revision,state)
                        VALUES(?,?,?,?,?,?,?,'PENDING')""",
                        (txid, name, stream, native_id, payload_json, digest, revision))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def _operations(self, txid):
        with closing(_connect(self.database_path)) as con:
            return con.execute(
                """SELECT * FROM coordinator_operations WHERE transaction_id=?
                   ORDER BY CASE participant
                     WHEN 'physical' THEN 1 WHEN 'capital' THEN 2 WHEN 'labour' THEN 3
                     WHEN 'product' THEN 4 WHEN 'legal_rights' THEN 5 WHEN 'financial' THEN 6
                     ELSE 99 END""",
                (txid,)
            ).fetchall()

    def _record_prepared(self, txid, name, token):
        with closing(_connect(self.database_path)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row = con.execute("SELECT state,prepare_token FROM coordinator_operations WHERE transaction_id=? AND participant=?",
                                  (txid, name)).fetchone()
                if row is None:
                    raise CoordinatorError("coordinator operation is missing")
                if row["state"] == "PREPARED":
                    if row["prepare_token"] != token:
                        raise CoordinatorError("prepare receipt changed on retry")
                    con.execute("COMMIT")
                    return
                if row["state"] != "PENDING":
                    raise CoordinatorError("coordinator operation cannot accept a prepare receipt")
                con.execute("""UPDATE coordinator_operations SET state='PREPARED',prepare_token=?
                    WHERE transaction_id=? AND participant=? AND state='PENDING'""",
                    (token, txid, name))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        _fault(f"after_prepare_receipt:{name}")

    def _record_committed(self, txid, name, receipt):
        with closing(_connect(self.database_path)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row = con.execute("SELECT * FROM coordinator_operations WHERE transaction_id=? AND participant=?",
                                  (txid, name)).fetchone()
                if row is None:
                    raise CoordinatorError("coordinator operation is missing")
                expected = {
                    "participant": name, "transaction_id": txid,
                    "native_event_id": row["native_event_id"],
                    "payload_digest": row["payload_digest"],
                    "prepare_token": row["prepare_token"],
                    "revision": row["expected_revision"] + 1,
                }
                if receipt != expected:
                    raise CoordinatorError("participant commit receipt does not match prepared operation")
                receipt_json = _canonical(receipt)
                if row["state"] == "COMMITTED":
                    if row["receipt_json"] != receipt_json:
                        raise CoordinatorError("commit receipt changed on retry")
                    con.execute("COMMIT")
                    return
                if row["state"] != "PREPARED":
                    raise CoordinatorError("coordinator operation was not durably prepared")
                con.execute("""UPDATE coordinator_operations SET state='COMMITTED',receipt_json=?
                    WHERE transaction_id=? AND participant=? AND state='PREPARED'""",
                    (receipt_json, txid, name))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        _fault(f"after_commit_receipt:{name}")

    def _abort_predecision(self, txid):
        self._set_state(txid, "ABORT_DECIDED")
        for name in PARTICIPANTS:
            self.participants[name].abort(txid)
            with closing(_connect(self.database_path)) as con:
                con.execute("""UPDATE coordinator_operations SET state='ABORTED'
                    WHERE transaction_id=? AND participant=? AND state!='COMMITTED'""",
                    (txid, name))
        self._set_state(txid, "ABORTED")

    def _commit_after_decision(self, txid):
        self._set_state(txid, "COMMITTING")
        operations = self._operations(txid)
        if len(operations) != len(PARTICIPANTS) or {row["participant"] for row in operations} != set(PARTICIPANTS):
            raise CoordinatorError("commit decision has incomplete participant operation coverage")
        for row in operations:
            name = row["participant"]
            status = self.participants[name].status(txid)
            if status is None or status["state"] == "ABORTED":
                raise CoordinatorError(f"{name} has no recoverable prepared record")
            token = row["prepare_token"]
            if not token or token != status["prepare_token"]:
                raise CoordinatorError(f"{name} durable prepare receipt is missing or mismatched")
            receipt = self.participants[name].commit(txid, token)
            self._record_committed(txid, name, receipt)
        self._persist_event_group(txid)
        _fault("after_event_group_persist")
        self._set_state(txid, "COMMITTED")
        _fault("after_commit_barrier")

    def execute(self, txid):
        # One shared SQLite exclusive lock serializes independent coordinator
        # processes; the kernel releases it automatically on process death.
        with _exclusive_process_lock(self.execution_lock_path):
            return self._execute_locked(txid)

    def _execute_locked(self, txid):
        # A client may retry after losing the response to a successful commit.
        # Never attempt to move a terminal transaction back into PREPARING.
        state = self.state(txid)
        if state is None:
            raise CoordinatorError("unknown coordinator transaction")
        if state == "COMMITTED":
            if not self.is_visible(txid):
                raise CoordinatorError("committed transaction failed native-event visibility verification")
            return "COMMITTED"
        if state == "ABORTED":
            return "ABORTED"
        if state in {"ABORT_DECIDED", "COMMIT_DECIDED", "COMMITTING"}:
            return self._recover_locked(txid)
        if state not in {"NEW", "PREPARING", "PREPARED"}:
            raise CoordinatorError(f"unsupported execute state: {state}")

        self._set_state(txid, "PREPARING")
        try:
            for row in self._operations(txid):
                name = row["participant"]
                operation = {
                    "stream_id": row["stream_id"],
                    "native_event_id": row["native_event_id"],
                    "payload": json.loads(row["payload_json"]),
                    "expected_revision": row["expected_revision"],
                }
                token = self.participants[name].prepare(txid, operation)
                self._record_prepared(txid, name, token)
            self._set_state(txid, "PREPARED")
            _fault("after_prepared_barrier")
        except Exception:
            self._abort_predecision(txid)
            raise
        # This durable decision is the point after which recovery MUST commit.
        self._set_state(txid, "COMMIT_DECIDED")
        _fault("after_commit_decision")
        self._commit_after_decision(txid)
        return self.state(txid)

    def recover(self, txid):
        with _exclusive_process_lock(self.execution_lock_path):
            return self._recover_locked(txid)

    def _recover_locked(self, txid):
        with closing(_connect(self.database_path)) as con:
            row = con.execute(
                "SELECT state FROM coordinator_transactions WHERE transaction_id=?", (txid,)
            ).fetchone()
        if row is None:
            raise CoordinatorError("unknown coordinator transaction")
        state = row["state"]
        if state in {"NEW","PREPARING","PREPARED"}:
            self._abort_predecision(txid)
        elif state == "ABORT_DECIDED":
            self._abort_predecision(txid)
        elif state in {"COMMIT_DECIDED","COMMITTING"}:
            self._commit_after_decision(txid)
        elif state in {"ABORTED","COMMITTED"}:
            return state
        else:
            raise CoordinatorError(f"unsupported recovery state: {state}")
        return self.state(txid)

    def state(self, txid):
        with closing(_connect(self.database_path)) as con:
            row = con.execute(
                "SELECT state FROM coordinator_transactions WHERE transaction_id=?", (txid,)
            ).fetchone()
            return row["state"] if row else None

    def is_visible(self, txid):
        """Read barrier: all six receipts AND native persisted events must match."""
        if self.state(txid) != "COMMITTED":
            return False
        with closing(_connect(self.database_path)) as con:
            if not _verify_event_group_chain(con):
                return False
            group_row=con.execute("SELECT commit_sequence FROM coordinator_event_groups WHERE transaction_id=?",(txid,)).fetchone()
            if group_row is None:
                return False
            pending_prior=con.execute(
                """SELECT 1 FROM coordinator_event_groups g
                   JOIN coordinator_transactions t ON t.transaction_id=g.transaction_id
                   WHERE g.commit_sequence<=? AND t.state!='COMMITTED' LIMIT 1""",
                (group_row["commit_sequence"],)
            ).fetchone()
            if pending_prior:
                return False
        operations = self._operations(txid)
        if len(operations) != len(PARTICIPANTS) or {r["participant"] for r in operations} != set(PARTICIPANTS):
            return False
        for row in operations:
            name = row["participant"]
            participant = self.participants[name]
            status = participant.status(txid)
            if not status or status["state"] != "COMMITTED":
                return False
            if not row["receipt_json"] or not status["receipt_json"]:
                return False
            try:
                receipt = json.loads(row["receipt_json"])
                participant_receipt = json.loads(status["receipt_json"])
            except (TypeError, json.JSONDecodeError):
                return False
            if not receipt or receipt != participant_receipt:
                return False
            if (receipt.get("participant") != name
                    or receipt.get("transaction_id") != txid
                    or receipt.get("native_event_id") != row["native_event_id"]
                    or receipt.get("payload_digest") != row["payload_digest"]
                    or receipt.get("prepare_token") != row["prepare_token"]
                    or receipt.get("revision") != row["expected_revision"] + 1):
                return False

            # A receipt is not proof that the native event row still exists.
            # Verify the authoritative participant-side persisted effect too.
            event = participant.committed_event(txid)
            if participant.event_count(txid) != 1 or event is None:
                return False
            if (event["native_event_id"] != row["native_event_id"]
                    or event["stream_id"] != row["stream_id"]
                    or event["revision"] != row["expected_revision"] + 1
                    or event["payload_digest"] != row["payload_digest"]
                    or event["payload_json"] != row["payload_json"]):
                return False
            actual_digest = hashlib.sha256(event["payload_json"].encode("utf-8")).hexdigest()
            if actual_digest != row["payload_digest"]:
                return False
        return True
    def _assemble_event_group(self, txid):
        """Assemble a candidate only after all six participant native receipts exist."""
        if self.state(txid) not in {"COMMITTING","COMMITTED"}:
            raise CoordinatorError("event group assembly requires an irreversible commit decision")
        with closing(_connect(self.database_path)) as con:
            row = con.execute(
                "SELECT envelope_json FROM coordinator_transactions WHERE transaction_id=?",
                (txid,)
            ).fetchone()
        if row is None:
            raise CoordinatorError("unknown coordinator transaction")
        envelope = json.loads(row["envelope_json"])
        events = []
        for operation in self._operations(txid):
            name = operation["participant"]
            native = self.participants[name].committed_event(txid)
            if native is None or native.get("common_event_id", txid) != txid:
                raise CoordinatorError("participant event is not bound to the common transaction ID")
            try:
                participant_payload = json.loads(native["payload_json"])
            except (TypeError, json.JSONDecodeError) as exc:
                raise CoordinatorError("participant event payload is not valid JSON") from exc
            if not isinstance(participant_payload, dict):
                raise CoordinatorError("participant event payload must be a JSON object")
            if isinstance(participant_payload.get("payload"), dict) and isinstance(participant_payload.get("event_type"), str):
                event_type = participant_payload["event_type"]
                domain_payload = dict(participant_payload["payload"])
                for metadata_field in ("stock_flow_movements", "no_stock_flow_effect"):
                    if metadata_field in participant_payload:
                        domain_payload[metadata_field] = participant_payload[metadata_field]
            else:
                event_type = participant_payload.get("event_type", "participant.command")
                domain_payload = participant_payload
            events.append({
                "register_id": name,
                "common_event_id": txid,
                "native_event_id": operation["native_event_id"],
                "aggregate_id": operation["stream_id"],
                "aggregate_version": operation["expected_revision"] + 1,
                "payload_digest": operation["payload_digest"],
                "event_type": event_type,
                "event_schema_id": participant_payload.get("schema_id"),
                "event_schema_version": participant_payload.get("schema_version"),
                "payload": domain_payload,
            })
        if {event["register_id"] for event in events} != set(PARTICIPANTS) or len(events) != len(PARTICIPANTS):
            raise CoordinatorError("committed event group does not contain exactly six registers")
        return {
            "schema_version": 1,
            "transaction_id": txid,
            "common_event_id": txid,
            "scenario_id": envelope["scenario_id"],
            "causation_id": envelope["causation_id"],
            "events": tuple(events),
        }


    def _persist_event_group(self,txid):
        group=self._assemble_event_group(txid)
        payload_json=_canonical(group)
        payload_digest=hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        with closing(_connect(self.database_path)) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                if not _verify_event_group_chain(con):
                    raise CoordinatorError("canonical event-group hash chain is corrupt")
                existing=con.execute(
                    "SELECT * FROM coordinator_event_groups WHERE transaction_id=?",(txid,)
                ).fetchone()
                if existing:
                    if existing["payload_json"]!=payload_json or existing["payload_digest"]!=payload_digest:
                        raise CoordinatorError("canonical event group retry changed immutable content")
                    con.execute("COMMIT")
                    return
                pending_group=con.execute(
                    """SELECT g.transaction_id FROM coordinator_event_groups g
                       JOIN coordinator_transactions t ON t.transaction_id=g.transaction_id
                       WHERE t.state!='COMMITTED' ORDER BY g.commit_sequence LIMIT 1"""
                ).fetchone()
                if pending_group:
                    raise CoordinatorError("an earlier canonical event group has not crossed the commit barrier")
                current_decision=con.execute(
                    "SELECT MIN(transition_id) FROM coordinator_transitions WHERE transaction_id=? AND to_state='COMMIT_DECIDED'",
                    (txid,)
                ).fetchone()[0]
                earlier_decision=con.execute(
                    """SELECT t.transaction_id FROM coordinator_transactions t
                       JOIN coordinator_transitions d ON d.transaction_id=t.transaction_id AND d.to_state='COMMIT_DECIDED'
                       WHERE t.transaction_id<>? AND t.state IN ('COMMIT_DECIDED','COMMITTING')
                         AND d.transition_id<? AND NOT EXISTS(
                           SELECT 1 FROM coordinator_event_groups g WHERE g.transaction_id=t.transaction_id)
                       ORDER BY d.transition_id LIMIT 1""",
                    (txid,current_decision)
                ).fetchone()
                if earlier_decision:
                    raise CoordinatorError("an earlier commit decision must recover before publishing this event group")
                latest=con.execute(
                    "SELECT commit_sequence,group_hash FROM coordinator_event_groups ORDER BY commit_sequence DESC LIMIT 1"
                ).fetchone()
                sequence=1 if latest is None else latest["commit_sequence"]+1
                previous_hash=_EVENT_GROUP_ZERO_HASH if latest is None else latest["group_hash"]
                group_hash=hashlib.sha256((previous_hash+payload_digest).encode("ascii")).hexdigest()
                con.execute(
                    """INSERT INTO coordinator_event_groups(
                       commit_sequence,transaction_id,common_event_id,payload_json,payload_digest,previous_hash,group_hash
                       ) VALUES(?,?,?,?,?,?,?)""",
                    (sequence,txid,txid,payload_json,payload_digest,previous_hash,group_hash)
                )
                if not _verify_event_group_chain(con):
                    raise CoordinatorError("new canonical event group failed hash-chain verification")
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise

    def _backfill_event_groups(self):
        """Migrate the contiguous committed prefix into the canonical stream."""
        with closing(_connect(self.database_path)) as con:
            if not _verify_event_group_chain(con):
                raise CoordinatorError("canonical event-group hash chain is corrupt at startup")
            rows=con.execute(
                """SELECT t.transaction_id,t.state,MIN(d.transition_id) AS decision_transition
                   FROM coordinator_transactions t
                   JOIN coordinator_transitions d ON d.transaction_id=t.transaction_id AND d.to_state='COMMIT_DECIDED'
                   WHERE t.state IN ('COMMITTED','COMMIT_DECIDED','COMMITTING')
                   GROUP BY t.transaction_id ORDER BY decision_transition"""
            ).fetchall()
        for row in rows:
            if row["state"]!="COMMITTED":
                break
            with closing(_connect(self.database_path)) as con:
                exists=con.execute("SELECT 1 FROM coordinator_event_groups WHERE transaction_id=?",
                    (row["transaction_id"],)).fetchone()
            if exists is None:
                self._persist_event_group(row["transaction_id"])

    def committed_event_group(self,txid):
        """Read the immutable canonical six-register group after the global visibility barrier."""
        if not self.is_visible(txid):
            raise CoordinatorError("transaction is not globally visible")
        with closing(_connect(self.database_path)) as con:
            if not _verify_event_group_chain(con):
                raise CoordinatorError("canonical event-group hash chain is corrupt")
            row=con.execute("SELECT payload_json FROM coordinator_event_groups WHERE transaction_id=?",
                (txid,)).fetchone()
        if row is None:
            raise CoordinatorError("committed transaction has no canonical event group")
        return json.loads(row["payload_json"])

    def iter_committed_event_groups(self):
        """Return the append-only committed prefix of the common economic event stream."""
        with closing(_connect(self.database_path)) as con:
            if not _verify_event_group_chain(con):
                raise CoordinatorError("canonical event-group hash chain is corrupt")
            rows=con.execute(
                """SELECT g.transaction_id,g.payload_json,t.state FROM coordinator_event_groups g
                   JOIN coordinator_transactions t ON t.transaction_id=g.transaction_id
                   ORDER BY g.commit_sequence"""
            ).fetchall()
        result=[]
        for row in rows:
            if row["state"]!="COMMITTED": break
            result.append(json.loads(row["payload_json"]))
        return result

    def latest_event_group_checkpoint(self):
        """Return the latest committed event-stream sequence/hash for external anchoring."""
        groups=self.iter_committed_event_groups()
        if not groups: return {"sequence":0,"group_hash":_EVENT_GROUP_ZERO_HASH}
        txid=groups[-1]["transaction_id"]
        with closing(_connect(self.database_path)) as con:
            row=con.execute("SELECT commit_sequence,group_hash FROM coordinator_event_groups WHERE transaction_id=?",
                (txid,)).fetchone()
        return {"sequence":row["commit_sequence"],"group_hash":row["group_hash"]}


    def publish_event_stream_checkpoint(self,anchor,service_id):
        """Anchor every missing event-stream sequence, including genesis, in an immutable external store."""
        if not isinstance(service_id,str) or not service_id or service_id!=service_id.strip():
            raise CoordinatorError("checkpoint service_id must be trimmed non-empty text")
        groups=self.iter_committed_event_groups()
        with closing(_connect(self.database_path)) as con:
            rows=con.execute(
                """SELECT g.commit_sequence,g.transaction_id,g.previous_hash,g.group_hash
                   FROM coordinator_event_groups g JOIN coordinator_transactions t
                     ON t.transaction_id=g.transaction_id
                   WHERE t.state='COMMITTED' ORDER BY g.commit_sequence"""
            ).fetchall()
        if len(rows)!=len(groups):
            raise CoordinatorError("committed event-group prefix differs from checkpoint source rows")
        manifests=[{
            "schema_version":"synergy.event-stream-checkpoint.v1",
            "service_id":service_id,"sequence":0,"transaction_id":None,
            "previous_group_hash":_EVENT_GROUP_ZERO_HASH,"group_hash":_EVENT_GROUP_ZERO_HASH,
        }]
        for row in rows:
            manifests.append({
                "schema_version":"synergy.event-stream-checkpoint.v1",
                "service_id":service_id,"sequence":row["commit_sequence"],
                "transaction_id":row["transaction_id"],
                "previous_group_hash":row["previous_hash"],"group_hash":row["group_hash"],
            })
        current=anchor.latest(service_id)
        current_sequence=-1 if current is None else current["checkpoint_sequence"]
        if current_sequence>len(rows):
            raise CoordinatorError("external checkpoint is ahead of the committed coordinator event stream")
        service_key=hashlib.sha256(service_id.encode("utf-8")).hexdigest()
        for manifest in manifests:
            sequence=manifest["sequence"]
            object_key=f"event-stream/{service_key}/{sequence:020d}-{manifest['group_hash']}.json"
            body=_canonical(manifest).encode("utf-8")
            digest=hashlib.sha256(body).hexdigest()
            if sequence<=current_sequence:
                if not anchor.is_anchored(service_id,sequence,object_key,digest):
                    raise CoordinatorError("external checkpoint history conflicts with canonical event stream")
                continue
            if sequence!=current_sequence+1:
                raise CoordinatorError("external checkpoint sequence would contain a gap")
            anchor.put_immutable(object_key,body)
            anchor.advance_latest(service_id,sequence,object_key,digest)
            current_sequence=sequence
        latest=anchor.latest(service_id)
        expected=manifests[-1]
        expected_key=f"event-stream/{service_key}/{expected['sequence']:020d}-{expected['group_hash']}.json"
        expected_digest=hashlib.sha256(_canonical(expected).encode("utf-8")).hexdigest()
        if latest is None or (latest["checkpoint_sequence"],latest["object_key"],latest["object_digest"])!=(
            expected["sequence"],expected_key,expected_digest
        ):
            raise CoordinatorError("external anchor latest pointer does not match the canonical event stream")
        if not anchor.is_anchored(service_id,expected["sequence"],expected_key,expected_digest):
            raise CoordinatorError("external anchor cannot verify the latest event-stream checkpoint")
        return expected

    def reconcile_event_stream(self,opening_positions,closing_positions):
        """Reconcile T/V/O movements from the verified committed event-stream prefix."""
        from economic_stock_flow_reconciliation import movements_from_event_groups,reconcile_periods
        groups=tuple(self.iter_committed_event_groups())
        movements=movements_from_event_groups(groups)
        return reconcile_periods(opening_positions,movements,closing_positions)
