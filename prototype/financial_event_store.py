"""Crash-persistent, atomic append-only store for validated financial event groups.

This prototype persists immutable event envelopes and their journal postings in
one SQLite transaction. Economic validation remains the responsibility of the
EntityJournal before append_group() is called.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, InvalidOperation
import hashlib
import json
import math
import os
import sqlite3
from typing import Any, Mapping, Sequence


class FinancialEventStoreError(ValueError):
    """Raised when an event group is invalid, conflicting or not appendable."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(
            value, sort_keys=True, separators=(",", ":"),
            ensure_ascii=False, allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise FinancialEventStoreError("event payload is not canonical JSON data") from exc


def _nonempty_string(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise FinancialEventStoreError(f"{field} must be a non-empty string")
    return value


def _validate_group(group_id: Any, causation_id: Any,
                    events: Sequence[Mapping[str, Any]]) -> tuple[str, str | None, list[dict]]:
    group_id = _nonempty_string(group_id, "group_id")
    if causation_id is not None:
        causation_id = _nonempty_string(causation_id, "causation_id")
    if not isinstance(events, (tuple, list)) or not events:
        raise FinancialEventStoreError("events must be a non-empty list or tuple")

    normalized: list[dict] = []
    seen_ids: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, Mapping):
            raise FinancialEventStoreError(f"event {index} must be a mapping")
        event_id = _nonempty_string(event.get("event_id"), "event_id")
        event_type = _nonempty_string(event.get("event_type"), "event_type")
        period = event.get("effective_period")
        if not isinstance(period, int) or isinstance(period, bool) or period < 0:
            raise FinancialEventStoreError("effective_period must be a non-negative integer")
        postings = event.get("postings")
        if not isinstance(postings, (tuple, list)) or not postings:
            raise FinancialEventStoreError("each event requires non-empty postings")
        if event_id in seen_ids:
            raise FinancialEventStoreError(f"duplicate event ID inside group: {event_id}")
        seen_ids.add(event_id)

        clean_postings = []
        for line_no, posting in enumerate(postings):
            if not isinstance(posting, Mapping):
                raise FinancialEventStoreError("each posting must be a mapping")
            for field in ("account", "side", "amount", "entity_id"):
                _nonempty_string(posting.get(field), f"posting.{field}")
            if posting["side"] not in ("D", "C"):
                raise FinancialEventStoreError("posting.side must be D or C")
            try:
                amount = Decimal(posting["amount"])
            except (InvalidOperation, TypeError, ValueError) as exc:
                raise FinancialEventStoreError("posting.amount must be a decimal string") from exc
            if not amount.is_finite() or amount <= 0:
                raise FinancialEventStoreError("posting.amount must be finite and positive")
            # Validate the complete posting is serializable before opening a DB transaction.
            clean = dict(posting)
            _canonical_json(clean)
            clean_postings.append(clean)

        clean_event = dict(event)
        clean_event["event_id"] = event_id
        clean_event["event_type"] = event_type
        clean_event["effective_period"] = period
        clean_event["postings"] = clean_postings
        _canonical_json(clean_event)
        normalized.append(clean_event)
    return group_id, causation_id, normalized


class FinancialEventStore:
    """SQLite append-only event store with durable uniqueness and atomic groups.

    The database must live on a filesystem with reliable SQLite locking and
    fsync semantics. This is a single-database/single-host prototype, not a
    distributed consensus or multi-region event store.
    """

    SCHEMA_VERSION = 2

    def __init__(self, database_path: str | os.PathLike, timeout: float = 10.0):
        if (not isinstance(timeout, (int, float)) or isinstance(timeout, bool)
                or not math.isfinite(timeout) or timeout <= 0):
            raise FinancialEventStoreError("timeout must be finite and positive")
        self.database_path = os.fspath(database_path)
        if not self.database_path or self.database_path == ":memory:":
            raise FinancialEventStoreError(
                "a persistent file-backed database_path is required")
        self.timeout = float(timeout)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=self.timeout, isolation_level=None,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self.timeout * 1000)}")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        with closing(self._connect()) as connection:
            journal_mode = connection.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            synchronous = connection.execute("PRAGMA synchronous = FULL").fetchone()[0]
            if str(journal_mode).lower() != "wal" or synchronous != 2:
                raise FinancialEventStoreError(
                    "SQLite WAL mode and FULL synchronous durability are required")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version == 0:
                # Recover safely if an older initializer created the v1 events
                # table but crashed before stamping PRAGMA user_version.
                table = connection.execute(
                    "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'events'"
                ).fetchone()
                if table is not None:
                    columns = {
                        row["name"] for row in connection.execute(
                            "PRAGMA table_info(events)").fetchall()
                    }
                    if "event_index" not in columns:
                        version = 1
            if version not in (0, 1, self.SCHEMA_VERSION):
                raise FinancialEventStoreError(
                    f"unsupported event-store schema version: {version}")

            # Version 2 makes event order explicit rather than relying on
            # SQLite rowid, which is not a durable ordering contract.
            if version == 1:
                connection.execute("BEGIN IMMEDIATE")
                try:
                    connection.execute(
                        "ALTER TABLE events ADD COLUMN event_index INTEGER "
                        "NOT NULL DEFAULT 0 CHECK (event_index >= 0)")
                    connection.execute("DROP TRIGGER IF EXISTS events_no_update")
                    groups = connection.execute(
                        "SELECT group_id FROM event_groups ORDER BY group_id"
                    ).fetchall()
                    for group in groups:
                        rows = connection.execute(
                            "SELECT event_id FROM events WHERE group_id = ? ORDER BY rowid",
                            (group["group_id"],),
                        ).fetchall()
                        for event_index, row in enumerate(rows):
                            connection.execute(
                                "UPDATE events SET event_index = ? WHERE event_id = ?",
                                (event_index, row["event_id"]),
                            )
                    connection.execute(
                        "CREATE UNIQUE INDEX IF NOT EXISTS events_group_order "
                        "ON events(group_id, event_index)")
                    connection.execute("""
                        CREATE TRIGGER IF NOT EXISTS events_no_update
                        BEFORE UPDATE ON events
                        BEGIN SELECT RAISE(ABORT, 'events are append-only'); END
                    """)
                    connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")
                    connection.execute("COMMIT")
                except Exception:
                    if connection.in_transaction:
                        connection.execute("ROLLBACK")
                    raise

            connection.executescript("""
                CREATE TABLE IF NOT EXISTS event_groups (
                    group_id TEXT PRIMARY KEY,
                    causation_id TEXT,
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id TEXT PRIMARY KEY,
                    group_id TEXT NOT NULL REFERENCES event_groups(group_id),
                    event_type TEXT NOT NULL,
                    effective_period INTEGER NOT NULL CHECK (effective_period >= 0),
                    event_index INTEGER NOT NULL CHECK (event_index >= 0),
                    payload_sha256 TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS journal_lines (
                    event_id TEXT NOT NULL REFERENCES events(event_id),
                    line_no INTEGER NOT NULL CHECK (line_no >= 0),
                    posting_json TEXT NOT NULL,
                    PRIMARY KEY (event_id, line_no)
                );
                CREATE INDEX IF NOT EXISTS events_by_group
                    ON events(group_id, event_id);
                CREATE UNIQUE INDEX IF NOT EXISTS events_group_order
                    ON events(group_id, event_index);
                CREATE TRIGGER IF NOT EXISTS event_groups_no_update
                    BEFORE UPDATE ON event_groups
                    BEGIN SELECT RAISE(ABORT, 'event groups are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS event_groups_no_delete
                    BEFORE DELETE ON event_groups
                    BEGIN SELECT RAISE(ABORT, 'event groups are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_update
                    BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete
                    BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS journal_lines_no_update
                    BEFORE UPDATE ON journal_lines
                    BEGIN SELECT RAISE(ABORT, 'journal lines are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS journal_lines_no_delete
                    BEFORE DELETE ON journal_lines
                    BEGIN SELECT RAISE(ABORT, 'journal lines are append-only'); END;
            """)
            connection.execute(f"PRAGMA user_version = {self.SCHEMA_VERSION}")

    def append_group(self, group_id: str, events: Sequence[Mapping[str, Any]],
                     causation_id: str | None = None) -> bool:
        """Atomically append a group; return False for an identical replay.

        A reused group ID with changed content, or any event ID already owned
        by another group, is rejected. The full envelope and postings are
        committed together under BEGIN IMMEDIATE.
        """
        group_id, causation_id, normalized = _validate_group(
            group_id, causation_id, events)
        envelope = {
            "group_id": group_id,
            "causation_id": causation_id,
            "events": normalized,
        }
        payload_json = _canonical_json(envelope)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        event_rows = []
        for event in normalized:
            event_json = _canonical_json(event)
            event_rows.append((
                event["event_id"], event["event_type"], event["effective_period"],
                len(event_rows),
                hashlib.sha256(event_json.encode("utf-8")).hexdigest(),
                event_json, event["postings"],
            ))

        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                existing = connection.execute(
                    "SELECT payload_sha256 FROM event_groups WHERE group_id = ?",
                    (group_id,),
                ).fetchone()
                if existing is not None:
                    if existing["payload_sha256"] == payload_hash:
                        connection.execute("ROLLBACK")
                        return False
                    raise FinancialEventStoreError(
                        "group ID replayed with different immutable content")

                for event_id, *_ in event_rows:
                    row = connection.execute(
                        "SELECT group_id FROM events WHERE event_id = ?",
                        (event_id,),
                    ).fetchone()
                    if row is not None:
                        raise FinancialEventStoreError(
                            f"event ID already belongs to group {row['group_id']}: {event_id}")

                connection.execute(
                    "INSERT INTO event_groups(group_id, causation_id, payload_sha256, payload_json) "
                    "VALUES (?, ?, ?, ?)",
                    (group_id, causation_id, payload_hash, payload_json),
                )
                for event_id, event_type, period, event_index, event_hash, event_json, postings in event_rows:
                    connection.execute(
                        "INSERT INTO events(event_id, group_id, event_type, effective_period, "
                        "event_index, payload_sha256, payload_json) VALUES (?, ?, ?, ?, ?, ?, ?)",
                        (event_id, group_id, event_type, period, event_index, event_hash, event_json),
                    )
                    for line_no, posting in enumerate(postings):
                        connection.execute(
                            "INSERT INTO journal_lines(event_id, line_no, posting_json) "
                            "VALUES (?, ?, ?)",
                            (event_id, line_no, _canonical_json(posting)),
                        )
                connection.execute("COMMIT")
                return True
            except Exception:
                if connection.in_transaction:
                    connection.execute("ROLLBACK")
                raise

    def get_group(self, group_id: str) -> dict | None:
        _nonempty_string(group_id, "group_id")
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload_json FROM event_groups WHERE group_id = ?",
                (group_id,),
            ).fetchone()
        return json.loads(row["payload_json"]) if row else None

    def counts(self) -> dict[str, int]:
        with closing(self._connect()) as connection:
            return {
                "groups": connection.execute(
                    "SELECT COUNT(*) FROM event_groups").fetchone()[0],
                "events": connection.execute(
                    "SELECT COUNT(*) FROM events").fetchone()[0],
                "journal_lines": connection.execute(
                    "SELECT COUNT(*) FROM journal_lines").fetchone()[0],
            }

    def integrity_check(self) -> bool:
        """Check SQLite structure, foreign keys, payload hashes and line mirrors."""
        try:
            with closing(self._connect()) as connection:
                result = connection.execute("PRAGMA integrity_check").fetchone()[0]
                foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
                if result != "ok" or foreign_keys:
                    return False

                groups = connection.execute(
                    "SELECT group_id, causation_id, payload_sha256, payload_json "
                    "FROM event_groups ORDER BY group_id"
                ).fetchall()
                for group in groups:
                    if hashlib.sha256(group["payload_json"].encode("utf-8")).hexdigest() != group["payload_sha256"]:
                        return False
                    envelope = json.loads(group["payload_json"])
                    if (envelope.get("group_id") != group["group_id"]
                            or envelope.get("causation_id") != group["causation_id"]):
                        return False
                    payload_events = envelope.get("events")
                    if not isinstance(payload_events, list) or not payload_events:
                        return False
                    stored_events = connection.execute(
                        "SELECT event_id, event_type, effective_period, event_index, payload_sha256, payload_json "
                        "FROM events WHERE group_id = ? ORDER BY event_index",
                        (group["group_id"],),
                    ).fetchall()
                    if len(stored_events) != len(payload_events):
                        return False
                    for event_index, (payload_event, stored) in enumerate(zip(payload_events, stored_events)):
                        if stored["event_index"] != event_index:
                            return False
                        event_json = _canonical_json(payload_event)
                        if (payload_event.get("event_id") != stored["event_id"]
                                or payload_event.get("event_type") != stored["event_type"]
                                or payload_event.get("effective_period") != stored["effective_period"]
                                or hashlib.sha256(event_json.encode("utf-8")).hexdigest() != stored["payload_sha256"]
                                or event_json != stored["payload_json"]):
                            return False
                        stored_lines = connection.execute(
                            "SELECT line_no, posting_json FROM journal_lines "
                            "WHERE event_id = ? ORDER BY line_no",
                            (stored["event_id"],),
                        ).fetchall()
                        payload_lines = payload_event.get("postings")
                        if not isinstance(payload_lines, list) or len(stored_lines) != len(payload_lines):
                            return False
                        if ([row["line_no"] for row in stored_lines] != list(range(len(payload_lines)))
                                or [row["posting_json"] for row in stored_lines] != [
                                    _canonical_json(line) for line in payload_lines]):
                            return False
        except (sqlite3.DatabaseError, ValueError, TypeError, KeyError, AttributeError):
            return False
        return True
