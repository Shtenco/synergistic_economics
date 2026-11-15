"""Durable, single-host SQLite store for native banking SFC projections.

The source financial register remains authoritative. This store persists a
reproducible projection snapshot and an immutable checkpoint atomically; it is
not a ledger, distributed consensus service, or substitute for source replay.
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Mapping


SCHEMA_VERSION = 1
STORE_ID = "native-banking-sfc-projection"


class BankingSFCStoreError(ValueError):
    """Projection persistence, cursor, or recovery validation failed."""


def _normal(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise BankingSFCStoreError("non-finite Decimal in projection")
        return format(value, "f")
    if is_dataclass(value):
        return _normal(asdict(value))
    if isinstance(value, Mapping):
        # Keys in SFC projections can be tuples and identity dataclasses.
        pairs = [(_normal(k), _normal(v)) for k, v in value.items()]
        pairs.sort(key=lambda pair: _json(pair[0]))
        return {"$map": pairs}
    if isinstance(value, (tuple, list)):
        return [_normal(item) for item in value]
    if isinstance(value, (str, int, bool)) or value is None:
        return value
    raise BankingSFCStoreError(f"unsupported projection value: {type(value).__name__}")


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


def _digest(value):
    return hashlib.sha256(_json(value).encode("utf-8")).hexdigest()


class BankingSFCProjectionStore:
    """Atomic projection snapshot/checkpoint persistence with fail-closed replay."""

    def __init__(self, database_path):
        self.path = str(database_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS banking_sfc_store_meta(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    store_id TEXT NOT NULL,
                    schema_version INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS banking_sfc_snapshots(
                    snapshot_id TEXT PRIMARY KEY,
                    source_register_id TEXT NOT NULL,
                    source_sequence INTEGER NOT NULL CHECK(source_sequence>=0),
                    source_digest TEXT NOT NULL,
                    mapping_version TEXT NOT NULL,
                    instrument_registry_digest TEXT NOT NULL,
                    sector_registry_digest TEXT NOT NULL,
                    opening_snapshot_digest TEXT NOT NULL,
                    projection_digest TEXT NOT NULL,
                    projection_json TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS banking_sfc_checkpoints(
                    checkpoint_sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id TEXT NOT NULL UNIQUE REFERENCES banking_sfc_snapshots(snapshot_id),
                    source_register_id TEXT NOT NULL,
                    applied_through_sequence INTEGER NOT NULL CHECK(applied_through_sequence>=0),
                    projection_digest TEXT NOT NULL,
                    checkpoint_digest TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS banking_sfc_snapshots_no_update
                    BEFORE UPDATE ON banking_sfc_snapshots
                    BEGIN SELECT RAISE(ABORT,'banking SFC snapshots are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS banking_sfc_snapshots_no_delete
                    BEFORE DELETE ON banking_sfc_snapshots
                    BEGIN SELECT RAISE(ABORT,'banking SFC snapshots are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS banking_sfc_checkpoints_no_update
                    BEFORE UPDATE ON banking_sfc_checkpoints
                    BEGIN SELECT RAISE(ABORT,'banking SFC checkpoints are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS banking_sfc_checkpoints_no_delete
                    BEFORE DELETE ON banking_sfc_checkpoints
                    BEGIN SELECT RAISE(ABORT,'banking SFC checkpoints are immutable'); END;
            """)
            row = con.execute("SELECT store_id,schema_version FROM banking_sfc_store_meta WHERE singleton=1").fetchone()
            if row is None:
                con.execute("INSERT INTO banking_sfc_store_meta VALUES(1,?,?)",
                            (STORE_ID, SCHEMA_VERSION))
            elif tuple(row) != (STORE_ID, SCHEMA_VERSION):
                raise BankingSFCStoreError("projection store identity/schema mismatch; explicit migration required")

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA synchronous=FULL")
        return con

    @staticmethod
    def _required(value, field):
        if not isinstance(value, str) or not value or value != value.strip():
            raise BankingSFCStoreError(f"{field} must be trimmed non-empty text")
        return value

    def append(self, projection, *, source_register_id, source_sequence,
               instrument_registry_digest, sector_registry_digest,
               opening_snapshot_digest, fault_at=None):
        """Persist a complete deterministic projection and cursor in one transaction.

        fault_at is a test-only failpoint: after_snapshot or after_checkpoint.
        """
        source_register_id = self._required(source_register_id, "source_register_id")
        for value, name in ((instrument_registry_digest, "instrument_registry_digest"),
                            (sector_registry_digest, "sector_registry_digest"),
                            (opening_snapshot_digest, "opening_snapshot_digest")):
            self._required(value, name)
        if not isinstance(source_sequence, int) or isinstance(source_sequence, bool) or source_sequence < 0:
            raise BankingSFCStoreError("source_sequence must be a non-negative integer")
        mapping_version = self._required(getattr(projection, "mapping_version", None), "mapping_version")
        source_digest = self._required(getattr(projection, "source_digest", None), "source_digest")
        body = _normal({
            "mapping_version": mapping_version,
            "source_digest": source_digest,
            "events": getattr(projection, "events", None),
            "projection": getattr(projection, "projection", None),
            "openings": getattr(projection, "openings", None),
            "roll_forward": getattr(projection, "roll_forward", None),
            "sector_financial_net_lending": getattr(projection, "sector_financial_net_lending", None),
            "source_event_count": getattr(projection, "source_event_count", None),
            "mapped_source_event_count": getattr(projection, "mapped_source_event_count", None),
            "excluded_opening_event_count": getattr(projection, "excluded_opening_event_count", None),
        })
        projection_json = _json(body)
        projection_digest = hashlib.sha256(projection_json.encode("utf-8")).hexdigest()
        snapshot_id = _digest([source_register_id, source_sequence, source_digest, mapping_version])
        checkpoint_body = {
            "store_id": STORE_ID, "schema_version": SCHEMA_VERSION,
            "snapshot_id": snapshot_id, "source_register_id": source_register_id,
            "applied_through_sequence": source_sequence,
            "source_digest": source_digest, "mapping_version": mapping_version,
            "instrument_registry_digest": instrument_registry_digest,
            "sector_registry_digest": sector_registry_digest,
            "opening_snapshot_digest": opening_snapshot_digest,
            "projection_digest": projection_digest,
        }
        checkpoint_digest = _digest(checkpoint_body)
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                latest = con.execute(
                    "SELECT source_sequence,source_digest,mapping_version,projection_digest "
                    "FROM banking_sfc_snapshots WHERE source_register_id=? "
                    "ORDER BY source_sequence DESC LIMIT 1", (source_register_id,)
                ).fetchone()
                if latest:
                    if source_sequence < latest["source_sequence"]:
                        raise BankingSFCStoreError("stale source cursor")
                    if source_sequence == latest["source_sequence"]:
                        if (source_digest, mapping_version, projection_digest) == (
                            latest["source_digest"], latest["mapping_version"], latest["projection_digest"]
                        ):
                            con.execute("COMMIT")
                            return {"snapshot_id": snapshot_id, "checkpoint_digest": checkpoint_digest,
                                    "projection_digest": projection_digest, "replayed": True}
                        raise BankingSFCStoreError("source cursor reused with changed projection content")
                    if mapping_version != latest["mapping_version"]:
                        raise BankingSFCStoreError("mapping version changed; explicit rebuild required")
                con.execute(
                    "INSERT INTO banking_sfc_snapshots(snapshot_id,source_register_id,source_sequence,"
                    "source_digest,mapping_version,instrument_registry_digest,sector_registry_digest,"
                    "opening_snapshot_digest,projection_digest,projection_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    (snapshot_id, source_register_id, source_sequence, source_digest, mapping_version,
                     instrument_registry_digest, sector_registry_digest, opening_snapshot_digest,
                     projection_digest, projection_json)
                )
                if fault_at == "after_snapshot":
                    raise RuntimeError("injected crash after snapshot write")
                con.execute(
                    "INSERT INTO banking_sfc_checkpoints(snapshot_id,source_register_id,"
                    "applied_through_sequence,projection_digest,checkpoint_digest) VALUES(?,?,?,?,?)",
                    (snapshot_id, source_register_id, source_sequence, projection_digest, checkpoint_digest)
                )
                if fault_at == "after_checkpoint":
                    raise RuntimeError("injected crash after checkpoint write")
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        return {"snapshot_id": snapshot_id, "checkpoint_digest": checkpoint_digest,
                "projection_digest": projection_digest, "replayed": False}

    def recover(self, expected_projection, *, source_register_id, source_sequence,
                instrument_registry_digest, sector_registry_digest,
                opening_snapshot_digest):
        """Compare a freshly re-derived projection to the immutable stored checkpoint."""
        mapping_version = self._required(getattr(expected_projection, "mapping_version", None), "mapping_version")
        source_digest = self._required(getattr(expected_projection, "source_digest", None), "source_digest")
        body = _normal({
            "mapping_version": mapping_version, "source_digest": source_digest,
            "events": getattr(expected_projection, "events", None),
            "projection": getattr(expected_projection, "projection", None),
            "openings": getattr(expected_projection, "openings", None),
            "roll_forward": getattr(expected_projection, "roll_forward", None),
            "sector_financial_net_lending": getattr(expected_projection, "sector_financial_net_lending", None),
            "source_event_count": getattr(expected_projection, "source_event_count", None),
            "mapped_source_event_count": getattr(expected_projection, "mapped_source_event_count", None),
            "excluded_opening_event_count": getattr(expected_projection, "excluded_opening_event_count", None),
        })
        encoded = _json(body)
        digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
        with self._connect() as con:
            row = con.execute(
                "SELECT s.*,c.applied_through_sequence,c.checkpoint_digest "
                "FROM banking_sfc_snapshots s JOIN banking_sfc_checkpoints c USING(snapshot_id) "
                "WHERE s.source_register_id=? AND s.source_sequence=?",
                (source_register_id, source_sequence)
            ).fetchone()
            if row is None:
                raise BankingSFCStoreError("sealed projection checkpoint is missing")
            expected_meta = (
                source_digest, mapping_version, instrument_registry_digest,
                sector_registry_digest, opening_snapshot_digest, digest
            )
            stored_meta = (
                row["source_digest"], row["mapping_version"], row["instrument_registry_digest"],
                row["sector_registry_digest"], row["opening_snapshot_digest"], row["projection_digest"]
            )
            if stored_meta != expected_meta or row["applied_through_sequence"] != source_sequence:
                raise BankingSFCStoreError("persisted projection/checkpoint differs from independently rebuilt source")
            if row["projection_json"] != encoded:
                raise BankingSFCStoreError("persisted projection rows differ from deterministic replay")
            checkpoint_body = {
                "store_id": STORE_ID, "schema_version": SCHEMA_VERSION,
                "snapshot_id": row["snapshot_id"], "source_register_id": source_register_id,
                "applied_through_sequence": source_sequence, "source_digest": source_digest,
                "mapping_version": mapping_version,
                "instrument_registry_digest": instrument_registry_digest,
                "sector_registry_digest": sector_registry_digest,
                "opening_snapshot_digest": opening_snapshot_digest,
                "projection_digest": digest,
            }
            if _digest(checkpoint_body) != row["checkpoint_digest"]:
                raise BankingSFCStoreError("checkpoint digest verification failed")
        return {"snapshot_id": row["snapshot_id"], "checkpoint_digest": row["checkpoint_digest"],
                "projection_digest": digest, "applied_through_sequence": source_sequence}

    def latest_checkpoint(self, source_register_id):
        with self._connect() as con:
            row = con.execute(
                "SELECT c.*,s.source_digest,s.mapping_version FROM banking_sfc_checkpoints c "
                "JOIN banking_sfc_snapshots s USING(snapshot_id) WHERE c.source_register_id=? "
                "ORDER BY c.applied_through_sequence DESC LIMIT 1", (source_register_id,)
            ).fetchone()
        return dict(row) if row else None


__all__ = ["BankingSFCStoreError", "BankingSFCProjectionStore", "SCHEMA_VERSION"]
