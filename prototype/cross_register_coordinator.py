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
            """)

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
                "SELECT * FROM coordinator_operations WHERE transaction_id=? ORDER BY participant",
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
