"""Durable, single-host SQLite store for native banking SFC projections.

The source financial register remains authoritative. This store persists a
reproducible projection snapshot and an immutable checkpoint atomically; it is
not a ledger, distributed consensus service, or substitute for source replay.
"""
from __future__ import annotations

from contextlib import closing
from dataclasses import asdict, is_dataclass
from decimal import Decimal
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Mapping


SCHEMA_VERSION = 2
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
        with closing(self._connect()) as con:
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
                    source_chain_hash TEXT NOT NULL,
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
                    source_chain_hash TEXT NOT NULL,
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

    def append(self, projection, *, source_register_id, source_sequence, source_chain_hash,
               instrument_registry_digest, sector_registry_digest,
               opening_snapshot_digest, fault_at=None):
        """Persist a complete deterministic projection and cursor in one transaction.

        fault_at is a test-only failpoint: after_snapshot or after_checkpoint.
        """
        if fault_at not in (None, "after_snapshot", "after_checkpoint"):
            raise BankingSFCStoreError("unsupported persistence failpoint")
        source_register_id = self._required(source_register_id, "source_register_id")
        for value, name in ((source_chain_hash, "source_chain_hash"),
                            (instrument_registry_digest, "instrument_registry_digest"),
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
        snapshot_id = _digest([source_register_id, source_sequence, source_chain_hash, source_digest, mapping_version])
        checkpoint_body = {
            "store_id": STORE_ID, "schema_version": SCHEMA_VERSION,
            "snapshot_id": snapshot_id, "source_register_id": source_register_id,
            "applied_through_sequence": source_sequence,
            "source_chain_hash": source_chain_hash,
            "source_digest": source_digest, "mapping_version": mapping_version,
            "instrument_registry_digest": instrument_registry_digest,
            "sector_registry_digest": sector_registry_digest,
            "opening_snapshot_digest": opening_snapshot_digest,
            "projection_digest": projection_digest,
        }
        checkpoint_digest = _digest(checkpoint_body)
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                latest = con.execute(
                    "SELECT s.snapshot_id,s.source_sequence,s.source_digest,s.mapping_version,"
                    "s.projection_digest,s.instrument_registry_digest,s.sector_registry_digest,"
                    "s.opening_snapshot_digest,s.projection_json,s.source_chain_hash,"
                    "c.source_register_id AS checkpoint_source_register_id,c.source_chain_hash AS checkpoint_source_chain_hash,"
                    "c.applied_through_sequence,c.projection_digest AS checkpoint_projection_digest,"
                    "c.checkpoint_digest FROM banking_sfc_snapshots s "
                    "LEFT JOIN banking_sfc_checkpoints c USING(snapshot_id) "
                    "WHERE s.source_register_id=? ORDER BY s.source_sequence DESC LIMIT 1",
                    (source_register_id,)
                ).fetchone()
                if latest:
                    # Never treat a duplicate source cursor as successful until the
                    # previously committed snapshot and its checkpoint have been
                    # independently revalidated. SQLite triggers protect normal
                    # writes, but offline/file-level corruption must fail closed too.
                    if (latest["checkpoint_source_register_id"] != source_register_id
                            or latest["checkpoint_source_chain_hash"] != latest["source_chain_hash"]
                            or latest["applied_through_sequence"] != latest["source_sequence"]
                            or latest["checkpoint_projection_digest"] != latest["projection_digest"]
                            or latest["checkpoint_digest"] is None):
                        raise BankingSFCStoreError("latest projection snapshot has no valid matching checkpoint")
                    stored_checkpoint_body = {
                        "store_id": STORE_ID, "schema_version": SCHEMA_VERSION,
                        "snapshot_id": latest["snapshot_id"],
                        "source_register_id": source_register_id,
                        "applied_through_sequence": latest["source_sequence"],
                        "source_chain_hash": latest["source_chain_hash"],
                        "source_digest": latest["source_digest"],
                        "mapping_version": latest["mapping_version"],
                        "instrument_registry_digest": latest["instrument_registry_digest"],
                        "sector_registry_digest": latest["sector_registry_digest"],
                        "opening_snapshot_digest": latest["opening_snapshot_digest"],
                        "projection_digest": latest["projection_digest"],
                    }
                    stored_projection_digest = hashlib.sha256(
                        latest["projection_json"].encode("utf-8")
                    ).hexdigest()
                    if (_digest(stored_checkpoint_body) != latest["checkpoint_digest"]
                            or stored_projection_digest != latest["projection_digest"]):
                        raise BankingSFCStoreError("latest projection snapshot/checkpoint integrity verification failed")
                    if source_sequence < latest["source_sequence"]:
                        raise BankingSFCStoreError("stale source cursor")
                    if source_sequence == latest["source_sequence"]:
                        if (snapshot_id, source_chain_hash, source_digest, mapping_version, projection_digest,
                            instrument_registry_digest, sector_registry_digest, opening_snapshot_digest,
                            projection_json) == (
                            latest["snapshot_id"], latest["source_chain_hash"], latest["source_digest"], latest["mapping_version"],
                            latest["projection_digest"], latest["instrument_registry_digest"],
                            latest["sector_registry_digest"], latest["opening_snapshot_digest"],
                            latest["projection_json"]
                        ):
                            if checkpoint_digest != latest["checkpoint_digest"]:
                                raise BankingSFCStoreError("replayed checkpoint digest differs from stored checkpoint")
                            con.execute("COMMIT")
                            return {"snapshot_id": snapshot_id, "checkpoint_digest": checkpoint_digest,
                                    "projection_digest": projection_digest, "replayed": True}
                        raise BankingSFCStoreError("source cursor reused with changed projection content")
                    if source_sequence <= latest["source_sequence"]:
                        raise BankingSFCStoreError("source cursor must advance monotonically")
                    if mapping_version != latest["mapping_version"]:
                        raise BankingSFCStoreError("mapping version changed; explicit rebuild required")
                    if (source_chain_hash != latest["source_chain_hash"]):
                        raise BankingSFCStoreError("source chain checkpoint changed; explicit rebuild required")
                    if (instrument_registry_digest != latest["instrument_registry_digest"]
                            or sector_registry_digest != latest["sector_registry_digest"]
                            or opening_snapshot_digest != latest["opening_snapshot_digest"]):
                        raise BankingSFCStoreError("pinned registry/opening digest changed; explicit rebuild required")
                con.execute(
                    "INSERT INTO banking_sfc_snapshots(snapshot_id,source_register_id,source_sequence,source_chain_hash,"
                    "source_digest,mapping_version,instrument_registry_digest,sector_registry_digest,"
                    "opening_snapshot_digest,projection_digest,projection_json) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                    (snapshot_id, source_register_id, source_sequence, source_chain_hash, source_digest, mapping_version,
                     instrument_registry_digest, sector_registry_digest, opening_snapshot_digest,
                     projection_digest, projection_json)
                )
                if fault_at == "after_snapshot":
                    raise RuntimeError("injected crash after snapshot write")
                con.execute(
                    "INSERT INTO banking_sfc_checkpoints(snapshot_id,source_register_id,"
                    "applied_through_sequence,source_chain_hash,projection_digest,checkpoint_digest) VALUES(?,?,?,?,?,?)",
                    (snapshot_id, source_register_id, source_sequence, source_chain_hash, projection_digest, checkpoint_digest)
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

    def recover(self, expected_projection, *, source_register_id, source_sequence, source_chain_hash,
                instrument_registry_digest, sector_registry_digest,
                opening_snapshot_digest):
        """Compare a freshly re-derived projection to the immutable stored checkpoint."""
        source_register_id = self._required(source_register_id, "source_register_id")
        if not isinstance(source_sequence, int) or isinstance(source_sequence, bool) or source_sequence < 0:
            raise BankingSFCStoreError("source_sequence must be a non-negative integer")
        for value, name in ((source_chain_hash, "source_chain_hash"),
                            (instrument_registry_digest, "instrument_registry_digest"),
                            (sector_registry_digest, "sector_registry_digest"),
                            (opening_snapshot_digest, "opening_snapshot_digest")):
            self._required(value, name)
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
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT s.*,c.applied_through_sequence,c.checkpoint_digest "
                "FROM banking_sfc_snapshots s JOIN banking_sfc_checkpoints c USING(snapshot_id) "
                "WHERE s.source_register_id=? AND s.source_sequence=?",
                (source_register_id, source_sequence)
            ).fetchone()
            if row is None:
                raise BankingSFCStoreError("sealed projection checkpoint is missing")
            expected_meta = (
                source_digest, mapping_version, source_chain_hash, instrument_registry_digest,
                sector_registry_digest, opening_snapshot_digest, digest
            )
            stored_meta = (
                row["source_digest"], row["mapping_version"], row["source_chain_hash"], row["instrument_registry_digest"],
                row["sector_registry_digest"], row["opening_snapshot_digest"], row["projection_digest"]
            )
            if stored_meta != expected_meta or row["applied_through_sequence"] != source_sequence:
                raise BankingSFCStoreError("persisted projection/checkpoint differs from independently rebuilt source")
            if row["projection_json"] != encoded:
                raise BankingSFCStoreError("persisted projection rows differ from deterministic replay")
            checkpoint_body = {
                "store_id": STORE_ID, "schema_version": SCHEMA_VERSION,
                "snapshot_id": row["snapshot_id"], "source_register_id": source_register_id,
                "applied_through_sequence": source_sequence, "source_chain_hash": source_chain_hash,
                "source_digest": source_digest, "mapping_version": mapping_version,
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
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT c.*,s.source_digest,s.mapping_version FROM banking_sfc_checkpoints c "
                "JOIN banking_sfc_snapshots s USING(snapshot_id) WHERE c.source_register_id=? "
                "ORDER BY c.applied_through_sequence DESC LIMIT 1", (source_register_id,)
            ).fetchone()
        return dict(row) if row else None


__all__ = ["BankingSFCStoreError", "BankingSFCProjectionStore", "SCHEMA_VERSION"]
