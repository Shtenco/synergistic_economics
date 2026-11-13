"""Explicit, immutable opening-snapshot activation for the SFC projection.

This is P1 only. It deliberately blocks legacy event appends after activation
until a projection-aware atomic append path is implemented.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal
import hashlib
import json
import sqlite3
from typing import Any, Mapping, Sequence

from financial_event_store import FinancialEventStore, FinancialEventStoreError
from sfc_projection_kernel import SFCIdentity, SFCProjectionError, canonical_decimal


class SFCProjectionRegistryError(ValueError):
    """Raised when opening activation or its immutable snapshot is invalid."""


def _canonical_json(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise SFCProjectionRegistryError("opening snapshot is not canonical JSON") from exc


def _identity_payload(identity: SFCIdentity) -> dict[str, str]:
    return {field: getattr(identity, field) for field in SFCIdentity.__dataclass_fields__}


def _normalize_openings(openings: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(openings, (tuple, list)) or not openings:
        raise SFCProjectionRegistryError("at least one explicit opening row is required")
    normalized: list[dict[str, Any]] = []
    seen: set[tuple[SFCIdentity, int]] = set()
    for index, row in enumerate(openings):
        if not isinstance(row, Mapping):
            raise SFCProjectionRegistryError(f"opening row {index} must be a mapping")
        raw_identity = row.get("identity")
        if not isinstance(raw_identity, Mapping):
            raise SFCProjectionRegistryError("opening.identity must be a mapping")
        try:
            expected_fields = set(SFCIdentity.__dataclass_fields__)
            if set(raw_identity) != expected_fields:
                raise SFCProjectionRegistryError(
                    "opening.identity must contain exactly the ten canonical identity fields")
            identity = SFCIdentity(**{
                field: raw_identity.get(field)
                for field in SFCIdentity.__dataclass_fields__
            })
            period = row.get("period")
            if not isinstance(period, int) or isinstance(period, bool) or period < 0:
                raise SFCProjectionRegistryError("opening.period must be a non-negative integer")
            amount_text = canonical_decimal(row.get("amount"))
            amount = Decimal(amount_text)
        except (TypeError, SFCProjectionError) as exc:
            raise SFCProjectionRegistryError(f"invalid opening row {index}: {exc}") from exc
        evidence_ref = row.get("evidence_ref")
        if (not isinstance(evidence_ref, str) or not evidence_ref.strip()
                or evidence_ref != evidence_ref.strip()):
            raise SFCProjectionRegistryError("opening.evidence_ref must be trimmed non-empty text")
        key = (identity, period)
        if key in seen:
            raise SFCProjectionRegistryError("duplicate opening identity and period")
        seen.add(key)
        normalized.append({
            "identity": _identity_payload(identity),
            "period": period,
            "amount": amount_text,
            "evidence_ref": evidence_ref,
        })
    normalized.sort(key=lambda item: (
        tuple(item["identity"][field] for field in SFCIdentity.__dataclass_fields__),
        item["period"],
    ))
    return normalized


def _snapshot_hash(openings: list[dict[str, Any]]) -> str:
    return hashlib.sha256(_canonical_json(openings).encode("utf-8")).hexdigest()


def _create_schema(connection: sqlite3.Connection) -> None:
    # Do not use executescript() here: sqlite3 implicitly commits an open
    # transaction before running it, which would break the activation lock.
    statements = (
        """CREATE TABLE IF NOT EXISTS sfc_projection_meta (
            singleton_id INTEGER PRIMARY KEY CHECK (singleton_id = 1),
            projection_schema_version INTEGER NOT NULL CHECK (projection_schema_version = 1),
            state TEXT NOT NULL CHECK (state = 'prepared'),
            snapshot_sha256 TEXT NOT NULL,
            mapper_version TEXT NOT NULL,
            evidence_ref TEXT NOT NULL,
            opening_count INTEGER NOT NULL CHECK (opening_count > 0)
        )""",
        """CREATE TABLE IF NOT EXISTS sfc_openings (
            instrument_id TEXT NOT NULL,
            instrument_class TEXT NOT NULL,
            holder_entity_id TEXT NOT NULL,
            holder_sector TEXT NOT NULL,
            issuer_entity_id TEXT NOT NULL,
            issuer_sector TEXT NOT NULL,
            currency TEXT NOT NULL,
            maturity TEXT NOT NULL,
            denomination TEXT NOT NULL,
            valuation_basis TEXT NOT NULL,
            period INTEGER NOT NULL CHECK (period >= 0),
            amount TEXT NOT NULL,
            evidence_ref TEXT NOT NULL,
            PRIMARY KEY (
                instrument_id, instrument_class, holder_entity_id, holder_sector,
                issuer_entity_id, issuer_sector, currency, maturity,
                denomination, valuation_basis, period
            )
        )""",
        """CREATE TRIGGER IF NOT EXISTS sfc_openings_no_insert_after_activation
            BEFORE INSERT ON sfc_openings
            WHEN EXISTS (SELECT 1 FROM sfc_projection_meta WHERE singleton_id = 1)
            BEGIN SELECT RAISE(ABORT, 'SFC opening snapshot is sealed'); END""",
        """CREATE TRIGGER IF NOT EXISTS sfc_openings_no_update
            BEFORE UPDATE ON sfc_openings
            BEGIN SELECT RAISE(ABORT, 'SFC openings are immutable'); END""",
        """CREATE TRIGGER IF NOT EXISTS sfc_openings_no_delete
            BEFORE DELETE ON sfc_openings
            BEGIN SELECT RAISE(ABORT, 'SFC openings are immutable'); END""",
        """CREATE TRIGGER IF NOT EXISTS sfc_projection_meta_no_update
            BEFORE UPDATE ON sfc_projection_meta
            BEGIN SELECT RAISE(ABORT, 'SFC projection metadata is immutable'); END""",
        """CREATE TRIGGER IF NOT EXISTS sfc_projection_meta_no_delete
            BEFORE DELETE ON sfc_projection_meta
            BEGIN SELECT RAISE(ABORT, 'SFC projection metadata is immutable'); END""",
    )
    for statement in statements:
        connection.execute(statement)


def activate_sfc_projection(
    store: FinancialEventStore,
    openings: Sequence[Mapping[str, Any]],
    *,
    mapper_version: str,
    evidence_ref: str,
) -> bool:
    """Activate P1 on an empty event store; identical retry is idempotent.

    Returns True for first activation and False for an identical retry.
    Populated legacy histories are never assigned inferred openings.
    """
    if not isinstance(store, FinancialEventStore):
        raise SFCProjectionRegistryError("a FinancialEventStore is required")
    if (not isinstance(mapper_version, str) or not mapper_version.strip()
            or mapper_version != mapper_version.strip()):
        raise SFCProjectionRegistryError("mapper_version must be trimmed non-empty text")
    if (not isinstance(evidence_ref, str) or not evidence_ref.strip()
            or evidence_ref != evidence_ref.strip()):
        raise SFCProjectionRegistryError("snapshot evidence_ref must be trimmed non-empty text")
    normalized = _normalize_openings(openings)
    snapshot_hash = _snapshot_hash(normalized)

    with closing(store._connect()) as connection:
        connection.execute("BEGIN IMMEDIATE")
        try:
            _create_schema(connection)
            existing = connection.execute(
                "SELECT projection_schema_version, state, snapshot_sha256, "
                "mapper_version, evidence_ref, opening_count "
                "FROM sfc_projection_meta WHERE singleton_id = 1"
            ).fetchone()
            if existing is not None:
                same = (
                    existing["projection_schema_version"] == 1
                    and existing["state"] == "prepared"
                    and existing["snapshot_sha256"] == snapshot_hash
                    and existing["mapper_version"] == mapper_version
                    and existing["evidence_ref"] == evidence_ref
                    and existing["opening_count"] == len(normalized)
                )
                if not same or not verify_sfc_projection_openings(connection):
                    raise SFCProjectionRegistryError(
                        "SFC projection is already activated with different or corrupt data")
                connection.execute("COMMIT")
                return False

            table_counts = {}
            for table_name in ("event_groups", "events", "journal_lines"):
                table_counts[table_name] = connection.execute(
                    f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            if any(table_counts.values()):
                raise SFCProjectionRegistryError(
                    "opening activation requires an empty event store including "
                    "all normalized event and posting tables; legacy history "
                    "requires an attested rebuild procedure")
            if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise SFCProjectionRegistryError(
                    "opening activation requires a structurally healthy empty store")
            if connection.execute("PRAGMA foreign_key_check").fetchall():
                raise SFCProjectionRegistryError(
                    "opening activation refuses event-store foreign-key violations")
            # Insert opening rows before the metadata seal. The insert trigger
            # prevents any later extension of the frozen opening snapshot.
            for item in normalized:
                identity = item["identity"]
                connection.execute(
                    "INSERT INTO sfc_openings("
                    "instrument_id, instrument_class, holder_entity_id, holder_sector, "
                    "issuer_entity_id, issuer_sector, currency, maturity, denomination, "
                    "valuation_basis, period, amount, evidence_ref) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    tuple(identity[field] for field in SFCIdentity.__dataclass_fields__)
                    + (item["period"], item["amount"], item["evidence_ref"]),
                )
            connection.execute(
                "INSERT INTO sfc_projection_meta(singleton_id, projection_schema_version, "
                "state, snapshot_sha256, mapper_version, evidence_ref, opening_count) "
                "VALUES (1, 1, 'prepared', ?, ?, ?, ?)",
                (snapshot_hash, mapper_version, evidence_ref, len(normalized)),
            )
            if not verify_sfc_projection_openings(connection):
                raise SFCProjectionRegistryError("opening snapshot failed post-write verification")
            connection.execute("COMMIT")
            return True
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise


def verify_sfc_projection_openings(connection: sqlite3.Connection) -> bool:
    """Verify persisted openings against the frozen snapshot hash.

    Accept both sqlite3.Row and the default tuple row factory. The verifier
    must not require callers to mutate their connection configuration.
    """
    try:
        meta_cursor = connection.execute(
            "SELECT projection_schema_version, state, snapshot_sha256, opening_count "
            "FROM sfc_projection_meta WHERE singleton_id = 1"
        )
        meta_values = meta_cursor.fetchone()
        if meta_values is None:
            return False
        meta = dict(zip((column[0] for column in meta_cursor.description), meta_values))
        if meta["projection_schema_version"] != 1 or meta["state"] != "prepared":
            return False
        rows_cursor = connection.execute(
            "SELECT instrument_id, instrument_class, holder_entity_id, holder_sector, "
            "issuer_entity_id, issuer_sector, currency, maturity, denomination, "
            "valuation_basis, period, amount, evidence_ref FROM sfc_openings"
        )
        columns = tuple(column[0] for column in rows_cursor.description)
        rows = [dict(zip(columns, row)) for row in rows_cursor.fetchall()]
        if len(rows) != meta["opening_count"]:
            return False
        normalized = []
        for row in rows:
            amount = canonical_decimal(row["amount"])
            if amount != row["amount"]:
                return False
            identity = {field: row[field] for field in SFCIdentity.__dataclass_fields__}
            SFCIdentity(**identity)
            normalized.append({
                "identity": identity,
                "period": row["period"],
                "amount": amount,
                "evidence_ref": row["evidence_ref"],
            })
        normalized.sort(key=lambda item: (
            tuple(item["identity"][field] for field in SFCIdentity.__dataclass_fields__),
            item["period"],
        ))
        return _snapshot_hash(normalized) == meta["snapshot_sha256"]
    except (sqlite3.DatabaseError, KeyError, TypeError, ValueError, SFCProjectionError):
        return False
