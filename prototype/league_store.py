"""Tenant-scoped durable store for SYNERGY LEAGUES work orders.

Research prototype: SQLite persistence and replay safety only. Authentication,
authorization, payment execution, and production multi-host coordination remain
responsibilities of separate services.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Any

from synergy_leagues import PayoutShare, WorkOrder, WorkStatus


class LeagueStoreError(RuntimeError):
    pass


class LeagueOrderNotFound(LeagueStoreError):
    pass


class LeagueVersionConflict(LeagueStoreError):
    pass


class LeagueCommandConflict(LeagueStoreError):
    pass


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field} is required")
    return value.strip()


def _order_document(order: WorkOrder) -> dict[str, Any]:
    return {
        "order_id": order.order_id,
        "buyer_id": order.buyer_id,
        "title": order.title,
        "description": order.description,
        "required_skills": list(order.required_skills),
        "budget": str(order.budget),
        "currency": order.currency,
        "created_at": order.created_at,
        "deadline": order.deadline,
        "status": order.status.value,
        "applications": list(order.applications),
        "assignee_id": order.assignee_id,
        "payout_shares": [
            {"recipient_id": item.recipient_id, "basis_points": item.basis_points}
            for item in order.payout_shares
        ],
        "delivery_evidence_refs": list(order.delivery_evidence_refs),
        "reviewer_id": order.reviewer_id,
        "version": order.version,
    }


def _order_from_document(document: dict[str, Any]) -> WorkOrder:
    data = dict(document)
    data["required_skills"] = tuple(data["required_skills"])
    data["applications"] = tuple(data["applications"])
    data["status"] = WorkStatus(data["status"])
    data["payout_shares"] = tuple(PayoutShare(**item) for item in data["payout_shares"])
    data["delivery_evidence_refs"] = tuple(data["delivery_evidence_refs"])
    return WorkOrder(**data)


def _canonical(document: dict[str, Any]) -> tuple[str, str]:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return payload, hashlib.sha256(payload.encode("utf-8")).hexdigest()


class SQLiteLeagueStore:
    """File-backed, append-only event history with optimistic order versions."""

    def __init__(self, path: str | Path, *, timeout_seconds: float = 5.0):
        self.path = str(path)
        if not self.path or self.path == ":memory:":
            raise ValueError("a file-backed database path is required")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.timeout_seconds = float(timeout_seconds)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.path, timeout=self.timeout_seconds, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(f"PRAGMA busy_timeout = {int(self.timeout_seconds * 1000)}")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS league_work_orders (
                    security_domain TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    version INTEGER NOT NULL CHECK (version >= 1),
                    status TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    PRIMARY KEY (security_domain, order_id)
                );

                CREATE TABLE IF NOT EXISTS league_work_order_events (
                    security_domain TEXT NOT NULL,
                    sequence INTEGER NOT NULL CHECK (sequence >= 1),
                    event_id TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL,
                    order_id TEXT NOT NULL,
                    aggregate_version INTEGER NOT NULL CHECK (aggregate_version >= 1),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    recorded_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now')),
                    PRIMARY KEY (security_domain, sequence),
                    UNIQUE (security_domain, event_id),
                    UNIQUE (security_domain, idempotency_key),
                    FOREIGN KEY (security_domain, order_id)
                        REFERENCES league_work_orders(security_domain, order_id)
                );

                CREATE INDEX IF NOT EXISTS idx_league_order_events_order
                    ON league_work_order_events(security_domain, order_id, sequence);

                CREATE TRIGGER IF NOT EXISTS league_order_events_no_update
                BEFORE UPDATE ON league_work_order_events
                BEGIN
                    SELECT RAISE(ABORT, 'league work-order events are append-only');
                END;

                CREATE TRIGGER IF NOT EXISTS league_order_events_no_delete
                BEFORE DELETE ON league_work_order_events
                BEGIN
                    SELECT RAISE(ABORT, 'league work-order events are append-only');
                END;
                """
            )
        finally:
            connection.close()

    @staticmethod
    def _existing_command(
        connection: sqlite3.Connection,
        domain: str,
        idempotency_key: str,
        *,
        order_id: str,
        version: int,
        event_type: str,
        digest: str,
    ) -> bool | None:
        row = connection.execute(
            """
            SELECT order_id, aggregate_version, event_type, payload_sha256
            FROM league_work_order_events
            WHERE security_domain = ? AND idempotency_key = ?
            """,
            (domain, idempotency_key),
        ).fetchone()
        if row is None:
            return None
        if (
            row["order_id"] == order_id
            and row["aggregate_version"] == version
            and row["event_type"] == event_type
            and row["payload_sha256"] == digest
        ):
            return True
        raise LeagueCommandConflict("idempotency key was reused with different content")

    @staticmethod
    def _append_event(
        connection: sqlite3.Connection,
        domain: str,
        order: WorkOrder,
        event_id: str,
        idempotency_key: str,
        event_type: str,
        payload: str,
        digest: str,
    ) -> None:
        sequence = connection.execute(
            """
            SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence
            FROM league_work_order_events WHERE security_domain = ?
            """,
            (domain,),
        ).fetchone()["next_sequence"]
        connection.execute(
            """
            INSERT INTO league_work_order_events
                (security_domain, sequence, event_id, idempotency_key, order_id,
                 aggregate_version, event_type, payload_json, payload_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                domain, sequence, event_id, idempotency_key, order.order_id,
                order.version, event_type, payload, digest,
            ),
        )

    def create(
        self,
        security_domain: str,
        order: WorkOrder,
        *,
        event_id: str,
        idempotency_key: str,
    ) -> bool:
        domain = _required(security_domain, "security_domain")
        event_id = _required(event_id, "event_id")
        idempotency_key = _required(idempotency_key, "idempotency_key")
        if order.version != 1 or order.status != WorkStatus.OPEN:
            raise LeagueStoreError("new work orders must begin at version 1 in OPEN state")
        document = _order_document(order)
        payload, digest = _canonical(document)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._existing_command(
                connection, domain, idempotency_key,
                order_id=order.order_id, version=order.version,
                event_type="WORK_ORDER_CREATED", digest=digest,
            )
            if replay:
                connection.rollback()
                return False
            connection.execute(
                """
                INSERT INTO league_work_orders
                    (security_domain, order_id, version, status, payload_json, payload_sha256)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (domain, order.order_id, order.version, order.status.value, payload, digest),
            )
            self._append_event(
                connection, domain, order, event_id, idempotency_key,
                "WORK_ORDER_CREATED", payload, digest,
            )
            connection.commit()
            return True
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise LeagueCommandConflict(str(exc)) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def save(
        self,
        security_domain: str,
        order: WorkOrder,
        *,
        expected_version: int,
        event_id: str,
        idempotency_key: str,
        event_type: str,
    ) -> bool:
        domain = _required(security_domain, "security_domain")
        event_id = _required(event_id, "event_id")
        idempotency_key = _required(idempotency_key, "idempotency_key")
        event_type = _required(event_type, "event_type")
        if isinstance(expected_version, bool) or not isinstance(expected_version, int) or expected_version < 1:
            raise ValueError("expected_version must be a positive integer")
        if order.version != expected_version + 1:
            raise LeagueStoreError("new order version must equal expected_version + 1")
        document = _order_document(order)
        payload, digest = _canonical(document)
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            replay = self._existing_command(
                connection, domain, idempotency_key,
                order_id=order.order_id, version=order.version,
                event_type=event_type, digest=digest,
            )
            if replay:
                connection.rollback()
                return False
            current = connection.execute(
                """
                SELECT version FROM league_work_orders
                WHERE security_domain = ? AND order_id = ?
                """,
                (domain, order.order_id),
            ).fetchone()
            if current is None:
                raise LeagueOrderNotFound(order.order_id)
            if current["version"] != expected_version:
                raise LeagueVersionConflict(
                    f"expected version {expected_version}, current version {current['version']}"
                )
            changed = connection.execute(
                """
                UPDATE league_work_orders
                SET version = ?, status = ?, payload_json = ?, payload_sha256 = ?
                WHERE security_domain = ? AND order_id = ? AND version = ?
                """,
                (
                    order.version, order.status.value, payload, digest,
                    domain, order.order_id, expected_version,
                ),
            ).rowcount
            if changed != 1:
                raise LeagueVersionConflict("concurrent work-order update detected")
            self._append_event(
                connection, domain, order, event_id, idempotency_key,
                event_type, payload, digest,
            )
            connection.commit()
            return True
        except sqlite3.IntegrityError as exc:
            connection.rollback()
            raise LeagueCommandConflict(str(exc)) from exc
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, security_domain: str, order_id: str) -> WorkOrder:
        domain = _required(security_domain, "security_domain")
        order_id = _required(order_id, "order_id")
        connection = self._connect()
        try:
            row = connection.execute(
                """
                SELECT payload_json, payload_sha256
                FROM league_work_orders
                WHERE security_domain = ? AND order_id = ?
                """,
                (domain, order_id),
            ).fetchone()
            if row is None:
                raise LeagueOrderNotFound(order_id)
            payload = row["payload_json"]
            if hashlib.sha256(payload.encode("utf-8")).hexdigest() != row["payload_sha256"]:
                raise LeagueStoreError("stored work-order digest mismatch")
            return _order_from_document(json.loads(payload))
        finally:
            connection.close()

    def events(self, security_domain: str, order_id: str | None = None) -> tuple[dict[str, Any], ...]:
        domain = _required(security_domain, "security_domain")
        connection = self._connect()
        try:
            if order_id is None:
                rows = connection.execute(
                    """
                    SELECT sequence, event_id, idempotency_key, order_id,
                           aggregate_version, event_type, payload_json, payload_sha256
                    FROM league_work_order_events
                    WHERE security_domain = ? ORDER BY sequence
                    """,
                    (domain,),
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT sequence, event_id, idempotency_key, order_id,
                           aggregate_version, event_type, payload_json, payload_sha256
                    FROM league_work_order_events
                    WHERE security_domain = ? AND order_id = ? ORDER BY sequence
                    """,
                    (domain, _required(order_id, "order_id")),
                ).fetchall()
            result = []
            for row in rows:
                payload = row["payload_json"]
                if hashlib.sha256(payload.encode("utf-8")).hexdigest() != row["payload_sha256"]:
                    raise LeagueStoreError("stored work-order event digest mismatch")
                result.append({
                    "sequence": row["sequence"],
                    "event_id": row["event_id"],
                    "idempotency_key": row["idempotency_key"],
                    "order_id": row["order_id"],
                    "aggregate_version": row["aggregate_version"],
                    "event_type": row["event_type"],
                    "order": _order_from_document(json.loads(payload)),
                })
            return tuple(result)
        finally:
            connection.close()

    def integrity_check(self) -> bool:
        connection = self._connect()
        try:
            integrity = connection.execute("PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                raise LeagueStoreError(f"SQLite integrity check failed: {integrity}")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise LeagueStoreError("league store foreign-key check failed")
            orders = connection.execute(
                "SELECT payload_json, payload_sha256 FROM league_work_orders"
            ).fetchall()
            for row in orders:
                if hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() != row["payload_sha256"]:
                    raise LeagueStoreError("stored work-order digest mismatch")
                _order_from_document(json.loads(row["payload_json"]))
            events = connection.execute(
                """
                SELECT security_domain, sequence, payload_json, payload_sha256
                FROM league_work_order_events ORDER BY security_domain, sequence
                """
            ).fetchall()
            last: dict[str, int] = {}
            for row in events:
                if row["sequence"] != last.get(row["security_domain"], 0) + 1:
                    raise LeagueStoreError("league event sequence gap")
                last[row["security_domain"]] = row["sequence"]
                if hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest() != row["payload_sha256"]:
                    raise LeagueStoreError("stored event digest mismatch")
                _order_from_document(json.loads(row["payload_json"]))
            return True
        finally:
            connection.close()
