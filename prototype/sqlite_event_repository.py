"""P6.3b SQLite transactional repository for canonical single-aggregate commands.

SQLite is a single-host durable commit authority. Events, aggregate projection,
command receipt and outbox rows commit in one BEGIN IMMEDIATE transaction.
This adapter deliberately does not retrofit the mutating P6.1 LotInventory API
or claim P6.3a multi-aggregate v2 support.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
import sqlite3
from contextlib import closing
from typing import Callable, Mapping

from real_economy_event_bridge import (
    EventBridgeConflict, EventBridgeError, canonical_json, map_domain_event,
)


class SQLiteRepositoryError(RuntimeError):
    """Durable repository or integrity failure."""


@dataclass(frozen=True)
class DurableReceipt:
    command_id: str
    request_fingerprint: str
    result: object
    event_ids: tuple[str, ...]
    commit_sequence: int


def _text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise EventBridgeError(f"{field} must be non-empty text")
    return value


def _json_value(value, field):
    try:
        return canonical_json(value)
    except EventBridgeError as exc:
        raise EventBridgeError(f"{field} must be canonical JSON data") from exc


class SQLiteEventRepository:
    """Atomic durable event/projection/receipt/outbox repository.

    SQLite WAL + BEGIN IMMEDIATE serializes writers on one host. Do not put the
    database on a network filesystem or treat this as a distributed lock.
    The supplied transition must be pure: it receives a detached state copy
    and returns (new_state, result, raw_events). No external side effects.
    """

    SCHEMA_VERSION = 1

    def __init__(self, path, *, timeout=10.0):
        if not isinstance(path, str) or not path:
            raise ValueError("database path is required")
        self.path = path
        self.timeout = timeout
        self._initialize()

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=self.timeout, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA synchronous=FULL")
        con.execute(f"PRAGMA busy_timeout={int(self.timeout * 1000)}")
        return con

    def _initialize(self):
        with closing(self._connect()) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS repository_meta(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    schema_version INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO repository_meta(singleton,schema_version) VALUES(1,1);
                CREATE TABLE IF NOT EXISTS aggregates(
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK(version>=0),
                    state_json TEXT NOT NULL,
                    state_digest TEXT NOT NULL,
                    PRIMARY KEY(aggregate_type,aggregate_id)
                );
                CREATE TABLE IF NOT EXISTS commands(
                    idempotency_key TEXT PRIMARY KEY,
                    command_id TEXT NOT NULL UNIQUE,
                    request_fingerprint TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    aggregate_version INTEGER NOT NULL,
                    result_json TEXT NOT NULL,
                    event_ids_json TEXT NOT NULL,
                    commit_sequence INTEGER NOT NULL,
                    recorded_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_id TEXT NOT NULL UNIQUE,
                    event_type TEXT NOT NULL,
                    aggregate_type TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    aggregate_version INTEGER NOT NULL,
                    event_ordinal INTEGER NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    command_id TEXT NOT NULL,
                    envelope_json TEXT NOT NULL,
                    payload_digest TEXT NOT NULL,
                    envelope_digest TEXT NOT NULL
                );
                CREATE UNIQUE INDEX IF NOT EXISTS events_aggregate_order
                    ON events(aggregate_type,aggregate_id,aggregate_version,event_ordinal);
                CREATE TABLE IF NOT EXISTS outbox(
                    event_id TEXT PRIMARY KEY REFERENCES events(event_id),
                    sequence INTEGER NOT NULL,
                    published_at TEXT,
                    attempts INTEGER NOT NULL DEFAULT 0
                );
            """)
            version = con.execute(
                "SELECT schema_version FROM repository_meta WHERE singleton=1"
            ).fetchone()[0]
            if version != self.SCHEMA_VERSION:
                raise SQLiteRepositoryError("unsupported repository schema version")

    def register_aggregate(self, aggregate_type, aggregate_id, initial_state):
        aggregate_type = _text(aggregate_type, "aggregate_type")
        aggregate_id = _text(aggregate_id, "aggregate_id")
        state_json = _json_value(initial_state, "initial_state")
        digest = sha256(state_json.encode("utf-8")).hexdigest()
        con = self._connect()
        try:
            con.execute("BEGIN IMMEDIATE")
            con.execute(
                "INSERT INTO aggregates VALUES(?,?,?,?,?)",
                (aggregate_type, aggregate_id, 0, state_json, digest),
            )
            con.commit()
        except sqlite3.IntegrityError as exc:
            con.rollback()
            raise EventBridgeConflict("aggregate already exists") from exc
        except Exception:
            con.rollback()
            raise
        finally:
            con.close()

    def load_aggregate(self, aggregate_type, aggregate_id):
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT version,state_json,state_digest FROM aggregates "
                "WHERE aggregate_type=? AND aggregate_id=?",
                (aggregate_type, aggregate_id),
            ).fetchone()
        if row is None:
            raise SQLiteRepositoryError("aggregate not found")
        if sha256(row["state_json"].encode("utf-8")).hexdigest() != row["state_digest"]:
            raise SQLiteRepositoryError("aggregate projection digest mismatch")
        return row["version"], json.loads(row["state_json"])

    def execute(self, *, command_id, idempotency_key, request,
                aggregate_type, aggregate_id, expected_version, actor_id,
                authority_ref, correlation_id, occurred_at, recorded_at,
                transition: Callable, evidence_refs=(), causation_id=None,
                fail_at=None):
        """Commit one aggregate command; fail_at is a deterministic crash hook.

        Hooks: after_event_insert, after_projection_write, after_receipt_write,
        before_commit, after_commit_before_response. The last hook simulates
        lost acknowledgement: retry with the same key returns the receipt.
        """
        for name, value in (("command_id",command_id),("idempotency_key",idempotency_key),
                            ("aggregate_type",aggregate_type),("aggregate_id",aggregate_id),
                            ("actor_id",actor_id),("authority_ref",authority_ref),
                            ("correlation_id",correlation_id)):
            _text(value, name)
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 0:
            raise EventBridgeError("expected_version must be a non-negative integer")
        allowed = {None, "after_event_insert", "after_projection_write",
                   "after_receipt_write", "before_commit", "after_commit_before_response"}
        if fail_at not in allowed:
            raise EventBridgeError("unknown crash injection point")
        fingerprint_data = {
            "command_id": command_id, "request": request,
            "aggregate_type": aggregate_type, "aggregate_id": aggregate_id,
            "expected_version": expected_version, "actor_id": actor_id,
            "authority_ref": authority_ref, "correlation_id": correlation_id,
            "occurred_at": occurred_at.isoformat(),
            "evidence_refs": list(evidence_refs), "causation_id": causation_id,
        }
        fingerprint = sha256(_json_value(fingerprint_data, "request").encode()).hexdigest()
        con = self._connect()
        committed = False
        try:
            con.execute("BEGIN IMMEDIATE")
            prior = con.execute(
                "SELECT * FROM commands WHERE idempotency_key=?", (idempotency_key,)
            ).fetchone()
            if prior is not None:
                if prior["request_fingerprint"] != fingerprint:
                    raise EventBridgeConflict("idempotency key reused with different request")
                con.commit()
                return DurableReceipt(
                    prior["command_id"], prior["request_fingerprint"],
                    json.loads(prior["result_json"]), tuple(json.loads(prior["event_ids_json"])),
                    prior["commit_sequence"],
                )
            row = con.execute(
                "SELECT version,state_json FROM aggregates WHERE aggregate_type=? AND aggregate_id=?",
                (aggregate_type, aggregate_id),
            ).fetchone()
            if row is None:
                raise SQLiteRepositoryError("aggregate not found")
            if row["version"] != expected_version:
                raise EventBridgeConflict(
                    f"stale aggregate version: expected {expected_version}, current {row['version']}"
                )
            old_state = json.loads(row["state_json"])
            candidate, result, raw_events = transition(old_state)
            if not isinstance(raw_events, (list, tuple)) or not raw_events:
                raise EventBridgeError("successful transition must emit at least one event")
            next_version = expected_version + 1
            mapped = tuple(map_domain_event(
                raw, aggregate_type=aggregate_type, actor_id=actor_id,
                authority_ref=authority_ref, command_id=command_id,
                correlation_id=correlation_id, occurred_at=occurred_at,
                recorded_at=recorded_at, evidence_refs=evidence_refs,
                causation_id=causation_id, event_ordinal=i,
            ) for i, raw in enumerate(raw_events))
            if any(e.aggregate_id != aggregate_id or e.aggregate_version != next_version for e in mapped):
                raise EventBridgeError("all events must target the command aggregate and next version")
            if len({e.event_id for e in mapped}) != len(mapped) or len({e.idempotency_key for e in mapped}) != len(mapped):
                raise EventBridgeError("duplicate event identity inside command")
            candidate_json = _json_value(candidate, "candidate state")
            result_json = _json_value(result, "command result")
            event_ids = [e.event_id for e in mapped]
            for event in mapped:
                envelope = event.as_dict()
                envelope_json = canonical_json(envelope)
                envelope_digest = sha256(envelope_json.encode("utf-8")).hexdigest()
                cur = con.execute(
                    "INSERT INTO events(event_id,event_type,aggregate_type,aggregate_id,"
                    "aggregate_version,event_ordinal,idempotency_key,command_id,envelope_json,"
                    "payload_digest,envelope_digest) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (event.event_id,event.event_type,aggregate_type,aggregate_id,next_version,
                     event.event_ordinal,event.idempotency_key,command_id,envelope_json,
                     event.payload_digest,envelope_digest),
                )
                sequence = cur.lastrowid
                con.execute("INSERT INTO outbox(event_id,sequence) VALUES(?,?)",
                            (event.event_id, sequence))
                if fail_at == "after_event_insert":
                    raise RuntimeError("injected crash after event/outbox insert")
            state_digest = sha256(candidate_json.encode("utf-8")).hexdigest()
            con.execute(
                "UPDATE aggregates SET version=?,state_json=?,state_digest=? "
                "WHERE aggregate_type=? AND aggregate_id=? AND version=?",
                (next_version,candidate_json,state_digest,aggregate_type,aggregate_id,expected_version),
            )
            if con.execute("SELECT changes()").fetchone()[0] != 1:
                raise EventBridgeConflict("aggregate compare-and-swap failed")
            if fail_at == "after_projection_write":
                raise RuntimeError("injected crash after projection write")
            last_sequence = con.execute("SELECT MAX(sequence) FROM events").fetchone()[0]
            con.execute(
                "INSERT INTO commands VALUES(?,?,?,?,?,?,?,?,?,?)",
                (idempotency_key,command_id,fingerprint,aggregate_type,aggregate_id,
                 next_version,result_json,canonical_json(event_ids),last_sequence,
                 recorded_at.isoformat()),
            )
            if fail_at == "after_receipt_write":
                raise RuntimeError("injected crash after receipt write")
            if fail_at == "before_commit":
                raise RuntimeError("injected crash before commit")
            con.commit()
            committed = True
            receipt = DurableReceipt(command_id, fingerprint, json.loads(result_json),
                                     tuple(event_ids), last_sequence)
            if fail_at == "after_commit_before_response":
                raise RuntimeError("injected lost response after durable commit")
            return receipt
        except Exception:
            if not committed:
                con.rollback()
            raise
        finally:
            con.close()

    def lookup_receipt(self, idempotency_key):
        with closing(self._connect()) as con:
            row = con.execute("SELECT * FROM commands WHERE idempotency_key=?",
                              (idempotency_key,)).fetchone()
        if row is None:
            return None
        return DurableReceipt(row["command_id"], row["request_fingerprint"],
                              json.loads(row["result_json"]),
                              tuple(json.loads(row["event_ids_json"])),
                              row["commit_sequence"])

    def pending_outbox(self, limit=100):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("limit must be positive")
        with closing(self._connect()) as con:
            rows = con.execute(
                "SELECT e.sequence,e.event_id,e.envelope_json FROM outbox o "
                "JOIN events e ON e.event_id=o.event_id "
                "WHERE o.published_at IS NULL ORDER BY e.sequence LIMIT ?", (limit,)
            ).fetchall()
        return tuple({"sequence":r["sequence"],"event_id":r["event_id"],
                      "envelope":json.loads(r["envelope_json"])} for r in rows)

    def mark_published(self, event_id, published_at):
        _text(event_id, "event_id")
        if not isinstance(published_at, datetime) or published_at.tzinfo is None or published_at.utcoffset() is None:
            raise ValueError("published_at must be timezone-aware")
        with closing(self._connect()) as con:
            cur = con.execute(
                "UPDATE outbox SET published_at=?,attempts=attempts+1 "
                "WHERE event_id=? AND published_at IS NULL",
                (published_at.isoformat(),event_id),
            )
            if cur.rowcount not in (0,1):
                raise SQLiteRepositoryError("unexpected outbox update count")
            exists = con.execute("SELECT 1 FROM outbox WHERE event_id=?", (event_id,)).fetchone()
            if exists is None:
                raise SQLiteRepositoryError("outbox event not found")
            return cur.rowcount == 1

    def _audit_connection(self, con):
        """Audit all durable tables inside the caller's SQLite read snapshot."""
        events = con.execute("SELECT * FROM events ORDER BY sequence").fetchall()
        commands = con.execute("SELECT * FROM commands").fetchall()
        outbox = con.execute("SELECT * FROM outbox").fetchall()
        meta = con.execute("SELECT schema_version FROM repository_meta WHERE singleton=1").fetchone()
        if meta is None or meta[0] != self.SCHEMA_VERSION:
            raise SQLiteRepositoryError("repository schema metadata mismatch")
        if len(outbox) != len(events):
            raise SQLiteRepositoryError("outbox/event cardinality mismatch")
        if [r["sequence"] for r in events] != list(range(1, len(events)+1)):
            raise SQLiteRepositoryError("global event sequence is not contiguous")
        by_command = {}
        aggregate_versions = {}
        for row in events:
            try:
                envelope = json.loads(row["envelope_json"])
                if canonical_json(envelope) != row["envelope_json"]:
                    raise SQLiteRepositoryError("event envelope is not canonical")
                if sha256(row["envelope_json"].encode()).hexdigest() != row["envelope_digest"]:
                    raise SQLiteRepositoryError("event envelope digest mismatch")
                if (envelope.get("event_id") != row["event_id"]
                        or envelope.get("event_type") != row["event_type"]
                        or envelope.get("aggregate_type") != row["aggregate_type"]
                        or envelope.get("aggregate_id") != row["aggregate_id"]
                        or envelope.get("aggregate_version") != row["aggregate_version"]
                        or envelope.get("event_ordinal") != row["event_ordinal"]
                        or envelope.get("idempotency_key") != row["idempotency_key"]
                        or envelope.get("command_id") != row["command_id"]):
                    raise SQLiteRepositoryError("event identity or aggregate metadata mismatch")
                if envelope.get("payload_digest") != row["payload_digest"]:
                    raise SQLiteRepositoryError("payload digest metadata mismatch")
                if sha256(canonical_json(envelope["payload"]).encode()).hexdigest() != row["payload_digest"]:
                    raise SQLiteRepositoryError("domain payload digest mismatch")
            except (KeyError, TypeError, ValueError) as exc:
                raise SQLiteRepositoryError("malformed durable event envelope") from exc
            key = row["command_id"]
            by_command.setdefault(key, []).append(row)
            aggregate_key = (row["aggregate_type"], row["aggregate_id"])
            aggregate_versions.setdefault(aggregate_key, set()).add(row["aggregate_version"])
        receipt_by_command = {r["command_id"]: r for r in commands}
        if set(by_command) != set(receipt_by_command):
            raise SQLiteRepositoryError("event groups and command receipts differ")
        for command_id, rows in by_command.items():
            receipt = receipt_by_command[command_id]
            ids = [r["event_id"] for r in rows]
            if ids != json.loads(receipt["event_ids_json"]):
                raise SQLiteRepositoryError("receipt event IDs/order mismatch")
            if [r["event_ordinal"] for r in rows] != list(range(len(rows))):
                raise SQLiteRepositoryError("command event ordinals are not contiguous")
            if any(r["aggregate_version"] != receipt["aggregate_version"]
                   or r["aggregate_type"] != receipt["aggregate_type"]
                   or r["aggregate_id"] != receipt["aggregate_id"] for r in rows):
                raise SQLiteRepositoryError("command aggregate version/identity mismatch")
            if rows[-1]["sequence"] != receipt["commit_sequence"]:
                raise SQLiteRepositoryError("receipt commit sequence differs from command tail")
        for key, versions in aggregate_versions.items():
            if versions != set(range(1, max(versions) + 1)):
                raise SQLiteRepositoryError("aggregate event version history has a gap")
        heads = con.execute(
            "SELECT aggregate_type,aggregate_id,version FROM aggregates"
        ).fetchall()
        for head in heads:
            key = (head["aggregate_type"], head["aggregate_id"])
            expected_head = max(aggregate_versions.get(key, {0}))
            if head["version"] != expected_head:
                raise SQLiteRepositoryError("aggregate head version differs from canonical event history")
        if set(aggregate_versions) - {(h["aggregate_type"], h["aggregate_id"]) for h in heads}:
            raise SQLiteRepositoryError("event history references an unregistered aggregate")
        event_by_id = {e["event_id"]: e for e in events}
        for row in outbox:
            linked = event_by_id.get(row["event_id"])
            if linked is None:
                raise SQLiteRepositoryError("orphan outbox row")
            if row["sequence"] != linked["sequence"]:
                raise SQLiteRepositoryError("outbox sequence differs from event sequence")
        return {"events": len(events), "commands": len(commands), "outbox": len(outbox)}

    def audit(self):
        """Fail-closed integrity audit in one consistent SQLite read snapshot."""
        with closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                report = self._audit_connection(con)
                con.commit()
                return report
            except Exception:
                con.rollback()
                raise

    def recover(self):
        """Audit and read aggregate heads from the same consistent snapshot."""
        with closing(self._connect()) as con:
            con.execute("BEGIN")
            try:
                self._audit_connection(con)
                rows = con.execute(
                    "SELECT aggregate_type,aggregate_id,version,state_json,state_digest "
                    "FROM aggregates ORDER BY aggregate_type,aggregate_id"
                ).fetchall()
                recovered = {}
                for row in rows:
                    if sha256(row["state_json"].encode()).hexdigest() != row["state_digest"]:
                        raise SQLiteRepositoryError("aggregate state digest mismatch")
                    recovered[(row["aggregate_type"], row["aggregate_id"])] = {
                        "version": row["version"], "state": json.loads(row["state_json"])
                    }
                con.commit()
                return recovered
            except Exception:
                con.rollback()
                raise
