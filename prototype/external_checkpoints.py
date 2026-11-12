"""Ed25519-signed checkpoint manifests and monotonic external anchor contract.

LocalImmutableAnchor is a test/conformance store only. Production must supply an
independently administered WORM/object-lock implementation and externally held
trust-root/key-revocation state.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
from typing import Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey


MANIFEST_FIELDS = (
    "service_id", "manifest_schema_version", "database_schema_version", "mapper_version",
    "projection_generation", "commit_sequence", "event_count", "event_log_root",
    "instrument_opening_hash", "control_opening_hash", "projection_state_hash",
    "coverage_count", "applied_through_cursor", "period", "period_closed",
    "backup_sha256", "checkpoint_sequence", "created_at_utc", "signer_key_id",
)


class CheckpointError(ValueError):
    """Invalid, untrusted, rolled-back or conflicting checkpoint."""


def canonical_json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise CheckpointError("checkpoint data is not canonical JSON") from exc


def sha256_bytes(value):
    return hashlib.sha256(value).hexdigest()


def _hash(value, field):
    if not isinstance(value, str) or len(value) != 64:
        raise CheckpointError(f"{field} must be a SHA-256 hex digest")
    if any(c not in "0123456789abcdef" for c in value):
        raise CheckpointError(f"{field} must be lowercase SHA-256 hex")
    return value


def validate_manifest(manifest):
    if not isinstance(manifest, dict) or set(manifest) != set(MANIFEST_FIELDS):
        raise CheckpointError("checkpoint manifest fields do not match the canonical schema")
    for field in ("service_id", "mapper_version", "signer_key_id"):
        if not isinstance(manifest[field], str) or not manifest[field] or manifest[field] != manifest[field].strip():
            raise CheckpointError(f"{field} must be trimmed non-empty text")
    for field in ("event_log_root", "instrument_opening_hash", "control_opening_hash",
                  "projection_state_hash", "backup_sha256"):
        _hash(manifest[field], field)
    for field in ("manifest_schema_version", "database_schema_version", "projection_generation", "commit_sequence",
                  "event_count", "coverage_count", "applied_through_cursor",
                  "period", "checkpoint_sequence"):
        value = manifest[field]
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            raise CheckpointError(f"{field} must be a non-negative integer")
    if not isinstance(manifest["period_closed"], bool):
        raise CheckpointError("period_closed must be boolean")
    if manifest["manifest_schema_version"] != 1:
        raise CheckpointError("unsupported checkpoint manifest schema version")
    if manifest["applied_through_cursor"] != manifest["commit_sequence"]:
        raise CheckpointError("applied-through cursor must match the checkpoint commit sequence")
    if manifest["coverage_count"] != manifest["event_count"]:
        raise CheckpointError("every committed event must have an explicit projection coverage row")
    timestamp = manifest["created_at_utc"]
    if not isinstance(timestamp, str):
        raise CheckpointError("created_at_utc must be an ISO-8601 UTC timestamp")
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError as exc:
        raise CheckpointError("created_at_utc is invalid") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise CheckpointError("created_at_utc must explicitly use UTC")
    canonical_json(manifest)
    return manifest


class Ed25519Signer:
    def __init__(self, key_id, private_key):
        if not isinstance(key_id, str) or not key_id or key_id != key_id.strip():
            raise CheckpointError("signer key ID must be trimmed non-empty text")
        if not isinstance(private_key, Ed25519PrivateKey):
            raise CheckpointError("Ed25519 private key required")
        self.key_id = key_id
        self._private_key = private_key

    @classmethod
    def generate(cls, key_id):
        return cls(key_id, Ed25519PrivateKey.generate())

    @classmethod
    def from_private_bytes(cls, key_id, raw_private_key):
        try:
            return cls(key_id, Ed25519PrivateKey.from_private_bytes(raw_private_key))
        except (TypeError, ValueError) as exc:
            raise CheckpointError("invalid raw Ed25519 private key") from exc

    def private_bytes(self):
        return self._private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_bytes(self):
        return self._private_key.public_key().public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def sign(self, message):
        return self._private_key.sign(message)


class TrustedKeyRegistry:
    """Trust-root object loaded from outside the protected ledger database."""

    def __init__(self, keys, revoked=()):
        self.keys = dict(keys)
        self.revoked = set(revoked)

    def public_key(self, key_id):
        if key_id in self.revoked:
            raise CheckpointError("checkpoint signing key is revoked")
        raw = self.keys.get(key_id)
        if raw is None:
            raise CheckpointError("checkpoint signing key is not trusted")
        try:
            return Ed25519PublicKey.from_public_bytes(raw)
        except (TypeError, ValueError) as exc:
            raise CheckpointError("trusted key registry contains an invalid public key") from exc


class CheckpointAnchor(Protocol):
    """External immutable-object and monotonic-sequence storage contract."""

    def put_immutable(self, object_key: str, object_bytes: bytes): ...
    def get(self, object_key: str) -> bytes: ...
    def advance_latest(self, service_id: str, sequence: int, object_key: str, object_digest: str): ...
    def latest(self, service_id: str): ...
    def is_anchored(self, service_id: str, sequence: int, object_key: str, object_digest: str) -> bool: ...


class LocalImmutableAnchor:
    """SQLite-backed test anchor; not a production WORM or independent trust domain."""

    def __init__(self, database_path):
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS checkpoint_objects(
                    object_key TEXT PRIMARY KEY,
                    object_digest TEXT NOT NULL,
                    object_bytes BLOB NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoint_latest(
                    service_id TEXT PRIMARY KEY,
                    checkpoint_sequence INTEGER NOT NULL,
                    object_key TEXT NOT NULL,
                    object_digest TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checkpoint_history(
                    service_id TEXT NOT NULL,
                    checkpoint_sequence INTEGER NOT NULL,
                    object_key TEXT NOT NULL,
                    object_digest TEXT NOT NULL,
                    PRIMARY KEY(service_id,checkpoint_sequence),
                    UNIQUE(object_key)
                );
                CREATE TRIGGER IF NOT EXISTS checkpoint_history_no_update
                    BEFORE UPDATE ON checkpoint_history
                    BEGIN SELECT RAISE(ABORT,'checkpoint anchor history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS checkpoint_history_no_delete
                    BEFORE DELETE ON checkpoint_history
                    BEGIN SELECT RAISE(ABORT,'checkpoint anchor history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS checkpoint_objects_no_update
                    BEFORE UPDATE ON checkpoint_objects
                    BEGIN SELECT RAISE(ABORT,'checkpoint objects are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS checkpoint_objects_no_delete
                    BEFORE DELETE ON checkpoint_objects
                    BEGIN SELECT RAISE(ABORT,'checkpoint objects are immutable'); END;
            """)

    def _connect(self):
        con = sqlite3.connect(str(self.path), timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=10000")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def put_immutable(self, object_key, object_bytes):
        digest = sha256_bytes(object_bytes)
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute(
                    "SELECT object_digest,object_bytes FROM checkpoint_objects WHERE object_key=?",
                    (object_key,)
                ).fetchone()
                if old:
                    if old["object_digest"] != digest or bytes(old["object_bytes"]) != object_bytes:
                        raise CheckpointError("immutable checkpoint object key already contains different bytes")
                    con.execute("COMMIT")
                    return False
                con.execute("INSERT INTO checkpoint_objects VALUES(?,?,?)",
                            (object_key, digest, object_bytes))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def get(self, object_key):
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT object_digest,object_bytes FROM checkpoint_objects WHERE object_key=?",
                (object_key,)
            ).fetchone()
            if row is None:
                raise CheckpointError("checkpoint object not found")
            payload = bytes(row["object_bytes"])
            if sha256_bytes(payload) != row["object_digest"]:
                raise CheckpointError("anchored checkpoint object digest mismatch")
            return payload

    def advance_latest(self, service_id, sequence, object_key, object_digest):
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute(
                    "SELECT checkpoint_sequence,object_key,object_digest FROM checkpoint_latest WHERE service_id=?",
                    (service_id,)
                ).fetchone()
                current = old["checkpoint_sequence"] if old else -1
                if sequence == current:
                    if (old["object_key"], old["object_digest"]) != (object_key, object_digest):
                        raise CheckpointError("checkpoint sequence already anchored to different content")
                    con.execute("COMMIT")
                    return False
                if sequence < current:
                    raise CheckpointError("checkpoint sequence rollback is forbidden")
                con.execute("INSERT INTO checkpoint_history VALUES(?,?,?,?)",
                            (service_id, sequence, object_key, object_digest))
                if old:
                    con.execute("""UPDATE checkpoint_latest SET checkpoint_sequence=?,
                        object_key=?,object_digest=? WHERE service_id=?""",
                        (sequence, object_key, object_digest, service_id))
                else:
                    con.execute("INSERT INTO checkpoint_latest VALUES(?,?,?,?)",
                                (service_id, sequence, object_key, object_digest))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def latest(self, service_id):
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT checkpoint_sequence,object_key,object_digest FROM checkpoint_latest WHERE service_id=?",
                (service_id,)
            ).fetchone()
            return dict(row) if row else None

    def is_anchored(self, service_id, sequence, object_key, object_digest):
        with closing(self._connect()) as con:
            row = con.execute(
                "SELECT object_key,object_digest FROM checkpoint_history WHERE service_id=? AND checkpoint_sequence=?",
                (service_id, sequence),
            ).fetchone()
            return bool(row and (row["object_key"], row["object_digest"]) == (object_key, object_digest))


def publish_checkpoint(manifest, signer: Ed25519Signer, anchor: CheckpointAnchor):
    manifest = validate_manifest(dict(manifest))
    if manifest["signer_key_id"] != signer.key_id:
        raise CheckpointError("manifest signer key ID does not match signing key")
    body = canonical_json(manifest).encode("utf-8")
    signature = signer.sign(body)
    envelope = {
        "algorithm": "Ed25519",
        "manifest": manifest,
        "signature_hex": signature.hex(),
    }
    object_bytes = canonical_json(envelope).encode("utf-8")
    object_digest = sha256_bytes(object_bytes)
    key = f"checkpoints/{manifest['service_id']}/{manifest['checkpoint_sequence']}.json"
    anchor.put_immutable(key, object_bytes)
    anchor.advance_latest(manifest["service_id"], manifest["checkpoint_sequence"], key, object_digest)
    return key, object_digest


def verify_checkpoint(object_key, expected_object_digest, trust: TrustedKeyRegistry,
                      anchor: CheckpointAnchor, *, require_latest=True):
    expected = _hash(expected_object_digest, "expected_object_digest")
    object_bytes = anchor.get(object_key)
    if sha256_bytes(object_bytes) != expected:
        raise CheckpointError("checkpoint object digest does not match requested digest")
    try:
        envelope = json.loads(object_bytes)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CheckpointError("checkpoint envelope is not valid JSON") from exc
    if not isinstance(envelope, dict):
        raise CheckpointError("checkpoint envelope must be a JSON object")
    if canonical_json(envelope).encode("utf-8") != object_bytes:
        raise CheckpointError("checkpoint envelope is not canonically encoded")
    if set(envelope) != {"algorithm", "manifest", "signature_hex"} or envelope["algorithm"] != "Ed25519":
        raise CheckpointError("unsupported checkpoint signature envelope")
    manifest = validate_manifest(envelope["manifest"])
    if object_key != f"checkpoints/{manifest['service_id']}/{manifest['checkpoint_sequence']}.json":
        raise CheckpointError("checkpoint object key does not match manifest identity")
    latest = anchor.latest(manifest["service_id"])
    if not latest:
        raise CheckpointError("service has no externally anchored checkpoint sequence")
    if require_latest:
        if (latest["checkpoint_sequence"], latest["object_key"], latest["object_digest"]) != (
            manifest["checkpoint_sequence"], object_key, expected
        ):
            raise CheckpointError("checkpoint is not the latest externally anchored sequence; rollback rejected")
    elif (manifest["checkpoint_sequence"] > latest["checkpoint_sequence"]
          or not anchor.is_anchored(manifest["service_id"], manifest["checkpoint_sequence"], object_key, expected)):
        raise CheckpointError("checkpoint is not present in immutable external anchor history")
    signature_hex = envelope["signature_hex"]
    if (not isinstance(signature_hex, str) or len(signature_hex) != 128
            or any(c not in "0123456789abcdef" for c in signature_hex)):
        raise CheckpointError("checkpoint signature is malformed")
    try:
        signature = bytes.fromhex(signature_hex)
    except ValueError as exc:
        raise CheckpointError("checkpoint signature is malformed") from exc
    try:
        trust.public_key(manifest["signer_key_id"]).verify(
            signature, canonical_json(manifest).encode("utf-8")
        )
    except InvalidSignature as exc:
        raise CheckpointError("checkpoint Ed25519 signature is invalid") from exc
    return manifest


def verify_backup_bytes(manifest, backup_bytes):
    """Verify backup bytes against the signed manifest digest."""
    manifest = validate_manifest(dict(manifest))
    if not isinstance(backup_bytes, (bytes, bytearray, memoryview)):
        raise CheckpointError("backup artifact must be bytes")
    actual = sha256_bytes(bytes(backup_bytes))
    if actual != manifest["backup_sha256"]:
        raise CheckpointError("backup artifact digest does not match signed checkpoint")
    return True
