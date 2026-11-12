"""Fail-closed verifier for externally signed period-governance approvals.

The issuer and revocation service remain independently administered. This module
verifies Ed25519 assertions and atomically consumes assertion IDs to prevent
replay; it does not mint identities or approval credentials.
"""
from __future__ import annotations

import base64
from contextlib import closing
import json
import hashlib
import math
from pathlib import Path
import sqlite3
import time
from typing import Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


_DOMAIN = b"SYNERGY_PERIOD_APPROVAL_ASSERTION_V1\\0"
_FIELDS = {
    "alg", "iss", "sub", "aud", "service_id", "request_id",
    "request_digest", "role", "evidence_ref", "jti", "iat", "exp", "kid",
}


class ApprovalAssertionError(ValueError):
    """An approval assertion is malformed, untrusted, expired, revoked or replayed."""


def _canonical(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ApprovalAssertionError("assertion is not canonical JSON data") from exc


def _b64decode(value):
    if not isinstance(value, str) or not value or any(ch.isspace() for ch in value):
        raise ApprovalAssertionError("assertion segment must be non-empty base64url text")
    try:
        raw = base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except Exception as exc:
        raise ApprovalAssertionError("invalid base64url assertion segment") from exc
    if base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=") != value:
        raise ApprovalAssertionError("assertion segment is not canonical base64url")
    return raw


def encode_assertion_payload(payload):
    """Canonical base64url payload helper for independently signing test fixtures."""
    raw = _canonical(payload)
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


class SignedApprovalVerifier:
    """Callable PeriodGovernance authorization_verifier implementation.

    key_resolver(issuer, key_id) -> raw 32-byte Ed25519 public key or None.
    is_revoked(issuer, key_id, jti) -> literal bool; True means revoked.
    Both resolvers must consult independently administered, current trust state.
    evidence_ref passed by PeriodGovernance is the compact payload.signature token.
    """

    def __init__(self, database_path, *, issuer: str, audience: str,
                 key_resolver: Callable[[str, str], bytes | None],
                 is_revoked: Callable[[str, str, str], bool],
                 clock: Callable[[], float] = time.time,
                 clock_skew_seconds: int = 30,
                 max_lifetime_seconds: int = 300):
        if not isinstance(issuer, str) or not issuer or issuer != issuer.strip():
            raise ApprovalAssertionError("trusted issuer must be trimmed non-empty text")
        if not isinstance(audience, str) or not audience or audience != audience.strip():
            raise ApprovalAssertionError("expected audience must be trimmed non-empty text")
        if not callable(key_resolver) or not callable(is_revoked) or not callable(clock):
            raise ApprovalAssertionError("key, revocation and clock resolvers are mandatory")
        if (not isinstance(clock_skew_seconds, int) or isinstance(clock_skew_seconds, bool)
                or clock_skew_seconds < 0 or clock_skew_seconds > 300):
            raise ApprovalAssertionError("clock skew must be an integer in [0,300]")
        if (not isinstance(max_lifetime_seconds, int) or isinstance(max_lifetime_seconds, bool)
                or max_lifetime_seconds < 1 or max_lifetime_seconds > 3600):
            raise ApprovalAssertionError("assertion lifetime must be in [1,3600] seconds")
        self.database_path = Path(database_path)
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self.issuer = issuer
        self.audience = audience
        self.key_resolver = key_resolver
        self.is_revoked = is_revoked
        self.clock = clock
        self.clock_skew_seconds = clock_skew_seconds
        self.max_lifetime_seconds = max_lifetime_seconds
        with closing(sqlite3.connect(self.database_path)) as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.execute("PRAGMA synchronous=FULL")
            con.execute("""CREATE TABLE IF NOT EXISTS approval_assertion_replays(
                issuer TEXT NOT NULL,
                jti TEXT NOT NULL,
                assertion_digest TEXT NOT NULL,
                consumed_at INTEGER NOT NULL,
                PRIMARY KEY(issuer,jti)
            )""")
            con.commit()

    def _decode_and_verify(self, token):
        if not isinstance(token, str) or len(token) > 16384 or token.count(".") != 2:
            raise ApprovalAssertionError("approval evidence must be a compact EdDSA JWS")
        header_segment, payload_segment, signature_segment = token.split(".")
        header_bytes = _b64decode(header_segment)
        payload_bytes = _b64decode(payload_segment)
        signature = _b64decode(signature_segment)
        if len(signature) != 64:
            raise ApprovalAssertionError("Ed25519 signature must contain 64 bytes")
        try:
            header = json.loads(header_bytes.decode("utf-8"))
            payload = json.loads(payload_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ApprovalAssertionError("JWS header or payload is not valid UTF-8 JSON") from exc
        if not isinstance(header, dict) or set(header) != _HEADER_FIELDS:
            raise ApprovalAssertionError("JWS protected header does not match the strict schema")
        if (_canonical(header) != header_bytes or header["alg"] != "EdDSA"
                or header["typ"] != "JWT"):
            raise ApprovalAssertionError("only canonical JWT JWS with EdDSA is accepted")
        if not isinstance(header["kid"], str) or not header["kid"] or header["kid"] != header["kid"].strip():
            raise ApprovalAssertionError("JWS kid must be trimmed non-empty text")
        if not isinstance(payload, dict) or set(payload) != _FIELDS:
            raise ApprovalAssertionError("assertion claims do not match the strict schema")
        if _canonical(payload) != payload_bytes:
            raise ApprovalAssertionError("assertion payload is not canonical JSON")
        for field in ("iss", "sub", "aud", "service_id", "request_id",
                      "request_digest", "role", "evidence_ref", "jti", "kid"):
            value = payload[field]
            if not isinstance(value, str) or not value or value != value.strip():
                raise ApprovalAssertionError(f"assertion {field} must be trimmed non-empty text")
        digest = payload["request_digest"]
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
            raise ApprovalAssertionError("request_digest must be lowercase SHA-256 hex")
        for field in ("iat", "exp"):
            if not isinstance(payload[field], int) or isinstance(payload[field], bool):
                raise ApprovalAssertionError(f"assertion {field} must be an integer Unix timestamp")
        if payload["exp"] <= payload["iat"]:
            raise ApprovalAssertionError("assertion expiry must follow issue time")
        if payload["exp"] - payload["iat"] > self.max_lifetime_seconds:
            raise ApprovalAssertionError("assertion lifetime exceeds the configured maximum")
        if payload["iss"] != self.issuer or payload["aud"] != self.audience:
            raise ApprovalAssertionError("assertion issuer or audience is not trusted")
        try:
            raw_key = self.key_resolver(payload["iss"], header["kid"])
        except Exception as exc:
            raise ApprovalAssertionError("trusted signing-key lookup failed") from exc
        if not isinstance(raw_key, bytes) or len(raw_key) != 32:
            raise ApprovalAssertionError("assertion signing key is not trusted")
        try:
            Ed25519PublicKey.from_public_bytes(raw_key).verify(
                signature, (header_segment + "." + payload_segment).encode("ascii")
            )
        except (InvalidSignature, ValueError) as exc:
            raise ApprovalAssertionError("approval assertion signature is invalid") from exc
        try:
            revoked = self.is_revoked(payload["iss"], header["kid"], payload["jti"])
        except Exception as exc:
            raise ApprovalAssertionError("live revocation check failed") from exc
        if revoked is not False:
            raise ApprovalAssertionError("approval assertion or signing key is revoked")
        now = self.clock()
        if (not isinstance(now, (int, float)) or isinstance(now, bool)
                or not math.isfinite(now)):
            raise ApprovalAssertionError("clock returned an invalid timestamp")
        if payload["iat"] > now + self.clock_skew_seconds:
            raise ApprovalAssertionError("approval assertion is not yet valid")
        if payload["exp"] <= now - self.clock_skew_seconds:
            raise ApprovalAssertionError("approval assertion has expired")
        return payload, _canonical(payload), int(now)

    def __call__(self, approver_id, role, request_context, evidence_ref):
        if not isinstance(request_context, dict):
            raise ApprovalAssertionError("request context must be a mapping")
        payload, canonical, now = self._decode_and_verify(evidence_ref)
        expected = {
            "sub": approver_id,
            "role": role,
            "service_id": request_context.get("service_id"),
            "request_id": request_context.get("request_id"),
            "request_digest": request_context.get("request_digest"),
        }
        for claim, value in expected.items():
            if payload[claim] != value:
                raise ApprovalAssertionError(f"approval assertion {claim} does not match the request")
        assertion_digest = hashlib.sha256(token.encode("ascii")).hexdigest()
        with closing(sqlite3.connect(self.database_path, timeout=30)) as con:
            con.execute("PRAGMA synchronous=FULL")
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute(
                    "SELECT assertion_digest FROM approval_assertion_replays "
                    "WHERE issuer=? AND jti=?",
                    (payload["iss"], payload["jti"]),
                ).fetchone()
                if old:
                    if old[0] != assertion_digest:
                        raise ApprovalAssertionError(
                            "approval assertion jti was reused with different signed content"
                        )
                    # Exact assertion retries are idempotent. The governance
                    # ledger's unique (request, role) key prevents a second effect.
                    con.execute("COMMIT")
                    return True
                con.execute(
                    "INSERT INTO approval_assertion_replays VALUES(?,?,?,?)",
                    (payload["iss"], payload["jti"], assertion_digest, now),
                )
                con.execute("COMMIT")
            except sqlite3.IntegrityError as exc:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise ApprovalAssertionError("approval assertion jti has already been consumed") from exc
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
        return True
