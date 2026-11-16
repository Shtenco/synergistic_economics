"""Durable Ed25519 trust-key registry shared by SYNERGY service boundaries.

Key material is public-only. Private keys belong in a KMS/HSM. The database
must be writable only by the independently governed trust-control plane.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import base64
import json
import sqlite3
from pathlib import Path
from typing import Iterable


class TrustRegistryError(ValueError):
    """Invalid key registration, authorization or trust-state transition."""


@dataclass(frozen=True)
class TrustedKeyRecord:
    key_id: str
    issuer: str
    tenant_id: str
    public_key: bytes
    valid_from: str
    valid_until: str
    scopes: tuple[str, ...]
    audiences: tuple[str, ...]
    fingerprint_sha256: str


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise TrustRegistryError(f"{field} must be trimmed non-empty text")
    return value


def _utc(value, field):
    value = _text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise TrustRegistryError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise TrustRegistryError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _now():
    return datetime.now(timezone.utc)


def _json_strings(values: Iterable[str], field: str) -> str:
    if isinstance(values, (str, bytes)):
        raise TrustRegistryError(f"{field} must be a sequence of strings")
    items = tuple(values)
    if not items or len(set(items)) != len(items):
        raise TrustRegistryError(f"{field} must be non-empty and unique")
    for item in items:
        _text(item, field)
    return json.dumps(sorted(items), separators=(",", ":"), ensure_ascii=False)


class TrustedKeyRegistry:
    """SQLite-backed append-only key registry with immediate revocation.

    Rotation is register-new-key followed by revoke-old-key. Key records and
    revocation records cannot be updated or deleted. Revoked keys are never
    returned by resolve_key, including for historical signatures.
    """

    SCHEMA_VERSION = 1

    def __init__(self, database_path: str | Path, *, timeout: float = 10.0):
        if str(database_path) == ":memory:":
            raise TrustRegistryError("durable file-backed trust registry is required")
        self.database_path = str(database_path)
        if timeout <= 0:
            raise TrustRegistryError("timeout must be positive")
        self.timeout = float(timeout)
        self._initialize()

    def _connect(self):
        con = sqlite3.connect(self.database_path, timeout=self.timeout, isolation_level=None)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA synchronous=FULL")
        con.execute(f"PRAGMA busy_timeout={int(self.timeout * 1000)}")
        return con

    def _initialize(self):
        with self._connect() as con:
            mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal" or con.execute("PRAGMA synchronous").fetchone()[0] != 2:
                raise TrustRegistryError("WAL and FULL synchronous mode are required")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS trust_meta(
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    schema_version INTEGER NOT NULL
                );
                INSERT OR IGNORE INTO trust_meta(singleton,schema_version) VALUES(1,1);
                CREATE TABLE IF NOT EXISTS trusted_keys(
                    key_id TEXT PRIMARY KEY,
                    issuer TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    public_key BLOB NOT NULL CHECK(length(public_key)=32),
                    fingerprint_sha256 TEXT NOT NULL,
                    valid_from TEXT NOT NULL,
                    valid_until TEXT NOT NULL,
                    scopes_json TEXT NOT NULL,
                    audiences_json TEXT NOT NULL,
                    registered_at TEXT NOT NULL,
                    registered_by TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS key_revocations(
                    key_id TEXT PRIMARY KEY REFERENCES trusted_keys(key_id),
                    revoked_at TEXT NOT NULL,
                    revoked_by TEXT NOT NULL,
                    reason TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS trust_events(
                    event_id TEXT PRIMARY KEY,
                    event_type TEXT NOT NULL,
                    key_id TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    payload_digest TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS trusted_keys_no_update
                    BEFORE UPDATE ON trusted_keys BEGIN SELECT RAISE(ABORT,'trusted keys are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS trusted_keys_no_delete
                    BEFORE DELETE ON trusted_keys BEGIN SELECT RAISE(ABORT,'trusted keys are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS key_revocations_no_update
                    BEFORE UPDATE ON key_revocations BEGIN SELECT RAISE(ABORT,'revocations are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS key_revocations_no_delete
                    BEFORE DELETE ON key_revocations BEGIN SELECT RAISE(ABORT,'revocations are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS trust_events_no_update
                    BEFORE UPDATE ON trust_events BEGIN SELECT RAISE(ABORT,'trust events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS trust_events_no_delete
                    BEFORE DELETE ON trust_events BEGIN SELECT RAISE(ABORT,'trust events are append-only'); END;
            """)
            version = con.execute("SELECT schema_version FROM trust_meta WHERE singleton=1").fetchone()[0]
            if version != self.SCHEMA_VERSION:
                raise TrustRegistryError("unsupported trust registry schema version")

    def register_key(self, *, key_id, issuer, tenant_id, public_key, valid_from,
                     valid_until, scopes, audiences, registered_by, registered_at=None):
        key_id, issuer, tenant_id, registered_by = (
            _text(key_id, "key_id"), _text(issuer, "issuer"),
            _text(tenant_id, "tenant_id"), _text(registered_by, "registered_by")
        )
        if not isinstance(public_key, bytes) or len(public_key) != 32:
            raise TrustRegistryError("Ed25519 public key must be exactly 32 raw bytes")
        start, end = _utc(valid_from, "valid_from"), _utc(valid_until, "valid_until")
        if end <= start:
            raise TrustRegistryError("key validity interval must be positive")
        scope_json = _json_strings(scopes, "scopes")
        audience_json = _json_strings(audiences, "audiences")
        instant = _utc(registered_at or _now().isoformat().replace("+00:00", "Z"), "registered_at")
        if instant < start:
            raise TrustRegistryError("key cannot be registered before its validity begins")
        fingerprint = sha256(public_key).hexdigest()
        payload = json.dumps({
            "key_id": key_id, "issuer": issuer, "tenant_id": tenant_id,
            "fingerprint_sha256": fingerprint, "valid_from": valid_from,
            "valid_until": valid_until, "scopes": json.loads(scope_json),
            "audiences": json.loads(audience_json),
        }, sort_keys=True, separators=(",", ":"))
        event_id = sha256(("REGISTER\0" + payload).encode()).hexdigest()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute(
                    """INSERT INTO trusted_keys VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                    (key_id, issuer, tenant_id, public_key, fingerprint, valid_from,
                     valid_until, scope_json, audience_json, instant.isoformat(), registered_by),
                )
                con.execute(
                    "INSERT INTO trust_events VALUES(?,?,?,?,?,?)",
                    (event_id, "KEY_REGISTERED", key_id, instant.isoformat(),
                     registered_by, sha256(payload.encode()).hexdigest()),
                )
                con.commit()
            except Exception:
                con.rollback()
                raise
        return fingerprint

    def revoke_key(self, *, key_id, revoked_by, reason, revoked_at=None):
        key_id, revoked_by, reason = (
            _text(key_id, "key_id"), _text(revoked_by, "revoked_by"),
            _text(reason, "reason")
        )
        instant = _utc(revoked_at or _now().isoformat().replace("+00:00", "Z"), "revoked_at")
        payload = json.dumps({"key_id": key_id, "revoked_at": instant.isoformat(),
                              "revoked_by": revoked_by, "reason": reason},
                             sort_keys=True, separators=(",", ":"))
        event_id = sha256(("REVOKE\0" + payload).encode()).hexdigest()
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                exists = con.execute("SELECT 1 FROM trusted_keys WHERE key_id=?", (key_id,)).fetchone()
                if not exists:
                    raise TrustRegistryError("cannot revoke an unknown key")
                con.execute("INSERT INTO key_revocations VALUES(?,?,?,?)",
                            (key_id, instant.isoformat(), revoked_by, reason))
                con.execute("INSERT INTO trust_events VALUES(?,?,?,?,?,?)",
                            (event_id, "KEY_REVOKED", key_id, instant.isoformat(),
                             revoked_by, sha256(payload.encode()).hexdigest()))
                con.commit()
            except Exception:
                con.rollback()
                raise

    def resolve_key(self, key_id, *, tenant_id=None, issuer=None,
                    required_scope=None, audience=None, now=None):
        key_id = _text(key_id, "key_id")
        instant = _utc((now or _now()).isoformat().replace("+00:00", "Z"), "now")
        with self._connect() as con:
            row = con.execute(
                """SELECT k.key_id,k.issuer,k.tenant_id,k.public_key,k.valid_from,
                          k.valid_until,k.scopes_json,k.audiences_json,k.fingerprint_sha256
                   FROM trusted_keys k LEFT JOIN key_revocations r ON r.key_id=k.key_id
                   WHERE k.key_id=? AND r.key_id IS NULL""", (key_id,)
            ).fetchone()
        if row is None:
            return None
        record = TrustedKeyRecord(
            key_id=row[0], issuer=row[1], tenant_id=row[2], public_key=bytes(row[3]),
            valid_from=row[4], valid_until=row[5], scopes=tuple(json.loads(row[6])),
            audiences=tuple(json.loads(row[7])), fingerprint_sha256=row[8],
        )
        if instant < _utc(record.valid_from, "valid_from") or instant >= _utc(record.valid_until, "valid_until"):
            return None
        if tenant_id is not None and record.tenant_id != tenant_id:
            return None
        if issuer is not None and record.issuer != issuer:
            return None
        if required_scope is not None and required_scope not in record.scopes:
            return None
        if audience is not None and audience not in record.audiences:
            return None
        return record

    def list_active_key_ids(self, *, tenant_id=None, now=None):
        with self._connect() as con:
            ids = [row[0] for row in con.execute(
                """SELECT k.key_id FROM trusted_keys k
                   LEFT JOIN key_revocations r ON r.key_id=k.key_id
                   WHERE r.key_id IS NULL ORDER BY k.key_id"""
            )]
        return [key_id for key_id in ids
                if self.resolve_key(key_id, tenant_id=tenant_id, now=now) is not None]


ECONOMIC_EVENT_DOMAIN = b"SYNERGY-ECONOMIC-MARKETPLACE-EVENT-V1\\x00"


def sign_economic_event_envelope(envelope, *, private_key, key_id, issuer,
                                 audience, issued_at, expires_at):
    """Attach an Ed25519 signature for the canonical marketplace event envelope."""
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if not isinstance(private_key, Ed25519PrivateKey):
        raise TrustRegistryError("private_key must be an Ed25519PrivateKey")
    if not isinstance(envelope, dict) or "attestation" in envelope:
        raise TrustRegistryError("unsigned event envelope must be an object without attestation")
    _text(key_id, "key_id")
    _text(issuer, "issuer")
    _text(audience, "audience")
    start, end = _utc(issued_at, "issued_at"), _utc(expires_at, "expires_at")
    if end <= start:
        raise TrustRegistryError("event attestation expiry must follow issue time")
    canonical = json.dumps(
        envelope, sort_keys=True, separators=(",", ":"),
        ensure_ascii=False, allow_nan=False,
    ).encode("utf-8")
    signature = private_key.sign(ECONOMIC_EVENT_DOMAIN + sha256(canonical).digest())
    return {
        **envelope,
        "attestation": {
            "algorithm": "Ed25519", "key_id": key_id, "issuer": issuer,
            "audience": audience, "issued_at": issued_at, "expires_at": expires_at,
            "signature": base64.b64encode(signature).decode("ascii"),
        },
    }
