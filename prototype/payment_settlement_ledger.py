"""Evidence-gated, durable double-entry payment settlement journal prototype.

Only an injected trusted payment-rail verifier may normalize external evidence.
This module posts a balanced accounting pair and a local tamper-evident chain;
it is not a payment processor, bank connection, or externally anchored ledger.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import sqlite3
from pathlib import Path
from typing import Callable, Mapping


class SettlementLedgerError(ValueError):
    """Unverified, malformed, replayed or inconsistent settlement evidence."""


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise SettlementLedgerError(f"{field} must be trimmed non-empty text")
    return value


def _timestamp(value, field):
    value = _text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SettlementLedgerError(f"{field} must be ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SettlementLedgerError(f"{field} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False)


class PaymentSettlementLedger:
    """Durable settlement inbox + balanced append-only accounting journal."""

    def __init__(self, database_path, *, settlement_evidence_verifier: Callable[[Mapping], Mapping]):
        if str(database_path) == ":memory:":
            raise SettlementLedgerError("file-backed durable ledger is required")
        if not callable(settlement_evidence_verifier):
            raise SettlementLedgerError("trusted settlement evidence verifier is mandatory")
        self.database_path = str(database_path)
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.settlement_evidence_verifier = settlement_evidence_verifier
        self._initialize()
        self.audit_proof()

    def _connect(self):
        con = sqlite3.connect(self.database_path, isolation_level=None, timeout=10)
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA synchronous=FULL")
        con.execute("PRAGMA busy_timeout=10000")
        return con

    def _initialize(self):
        with closing(self._connect()) as con:
            mode = con.execute("PRAGMA journal_mode=WAL").fetchone()[0]
            if str(mode).lower() != "wal" or con.execute("PRAGMA synchronous").fetchone()[0] != 2:
                raise SettlementLedgerError("WAL and FULL synchronous mode are required")
            con.executescript("""
                CREATE TABLE IF NOT EXISTS settled_payments(
                    receipt_id TEXT PRIMARY KEY,
                    payment_id TEXT NOT NULL,
                    tenant_id TEXT NOT NULL,
                    contract_ref TEXT NOT NULL,
                    payment_rail TEXT NOT NULL,
                    transaction_id TEXT NOT NULL,
                    log_index INTEGER NOT NULL,
                    payer_id TEXT NOT NULL,
                    payee_id TEXT NOT NULL,
                    currency TEXT NOT NULL,
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    settled_at TEXT NOT NULL,
                    evidence_digest TEXT NOT NULL,
                    UNIQUE(payment_rail,transaction_id,log_index)
                );
                CREATE TABLE IF NOT EXISTS accounting_journal(
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    entry_id TEXT NOT NULL UNIQUE,
                    receipt_id TEXT NOT NULL REFERENCES settled_payments(receipt_id),
                    account_id TEXT NOT NULL,
                    side TEXT NOT NULL CHECK(side IN ('DEBIT','CREDIT')),
                    amount_minor INTEGER NOT NULL CHECK(amount_minor > 0),
                    currency TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    previous_digest TEXT NOT NULL,
                    entry_digest TEXT NOT NULL UNIQUE
                );
                CREATE TRIGGER IF NOT EXISTS settled_payments_no_update
                    BEFORE UPDATE ON settled_payments
                    BEGIN SELECT RAISE(ABORT,'settlement records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS settled_payments_no_delete
                    BEFORE DELETE ON settled_payments
                    BEGIN SELECT RAISE(ABORT,'settlement records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS accounting_journal_no_update
                    BEFORE UPDATE ON accounting_journal
                    BEGIN SELECT RAISE(ABORT,'accounting journal is append-only'); END;
                CREATE TRIGGER IF NOT EXISTS accounting_journal_no_delete
                    BEFORE DELETE ON accounting_journal
                    BEGIN SELECT RAISE(ABORT,'accounting journal is append-only'); END;
            """)

    def post_settlement(self, *, evidence: Mapping) -> dict:
        if not isinstance(evidence, Mapping):
            raise SettlementLedgerError("settlement evidence must be a mapping")
        try:
            verified = self.settlement_evidence_verifier(evidence)
        except Exception as exc:
            raise SettlementLedgerError("payment-rail evidence verification failed") from exc
        if not isinstance(verified, Mapping) or verified.get("verified") is not True:
            raise SettlementLedgerError("payment settlement is not independently verified")

        required = (
            "payment_rail", "transaction_id", "log_index", "payment_id",
            "tenant_id", "contract_ref", "payer_id", "payee_id", "currency",
            "amount_minor", "settled_at", "evidence_digest", "settlement_status",
        )
        if any(key not in verified for key in required):
            raise SettlementLedgerError("verified settlement receipt is missing required fields")
        if verified["settlement_status"] != "SETTLED":
            raise SettlementLedgerError("only final SETTLED payments can be posted")
        for field in ("payment_rail", "transaction_id", "payment_id", "tenant_id",
                      "contract_ref", "payer_id", "payee_id", "currency", "evidence_digest"):
            _text(verified[field], field)
        if len(verified["currency"]) != 3 or not verified["currency"].isalpha() or not verified["currency"].isupper():
            raise SettlementLedgerError("currency must be a three-letter uppercase code")
        if isinstance(verified["log_index"], bool) or not isinstance(verified["log_index"], int) or verified["log_index"] < 0:
            raise SettlementLedgerError("log_index must be a non-negative integer")
        if isinstance(verified["amount_minor"], bool) or not isinstance(verified["amount_minor"], int) or verified["amount_minor"] <= 0:
            raise SettlementLedgerError("amount_minor must be a positive integer")
        digest = verified["evidence_digest"]
        if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest.lower()):
            raise SettlementLedgerError("evidence_digest must be a SHA-256 hex digest")
        settled_at = _timestamp(verified["settled_at"], "settled_at").isoformat()
        receipt_id = f'{verified["payment_rail"]}:{verified["transaction_id"]}:{verified["log_index"]}'
        payment = {
            "receipt_id": receipt_id, "payment_id": verified["payment_id"],
            "tenant_id": verified["tenant_id"], "contract_ref": verified["contract_ref"],
            "payment_rail": verified["payment_rail"], "transaction_id": verified["transaction_id"],
            "log_index": verified["log_index"], "payer_id": verified["payer_id"],
            "payee_id": verified["payee_id"], "currency": verified["currency"],
            "amount_minor": verified["amount_minor"], "settled_at": settled_at,
            "evidence_digest": digest.lower(),
        }
        entries = [
            {"entry_id": receipt_id + ":debit", "receipt_id": receipt_id,
             "account_id": "cash_clearing:" + verified["currency"], "side": "DEBIT",
             "amount_minor": verified["amount_minor"], "currency": verified["currency"]},
            {"entry_id": receipt_id + ":credit", "receipt_id": receipt_id,
             "account_id": "merchant_payable:" + verified["tenant_id"] + ":" + verified["payee_id"] + ":" + verified["currency"],
             "side": "CREDIT", "amount_minor": verified["amount_minor"],
             "currency": verified["currency"]},
        ]
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                con.execute(
                    """INSERT INTO settled_payments VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    tuple(payment[key] for key in (
                        "receipt_id","payment_id","tenant_id","contract_ref","payment_rail",
                        "transaction_id","log_index","payer_id","payee_id","currency",
                        "amount_minor","settled_at","evidence_digest"
                    )),
                )
                previous_row = con.execute(
                    "SELECT entry_digest FROM accounting_journal ORDER BY sequence DESC LIMIT 1"
                ).fetchone()
                previous = previous_row[0] if previous_row else "0" * 64
                for entry in entries:
                    payload_json = _canonical(entry)
                    entry_digest = hashlib.sha256((previous + payload_json).encode("utf-8")).hexdigest()
                    con.execute(
                        """INSERT INTO accounting_journal
                           (entry_id,receipt_id,account_id,side,amount_minor,currency,
                            payload_json,previous_digest,entry_digest)
                           VALUES(?,?,?,?,?,?,?,?,?)""",
                        (entry["entry_id"], entry["receipt_id"], entry["account_id"],
                         entry["side"], entry["amount_minor"], entry["currency"],
                         payload_json, previous, entry_digest),
                    )
                    previous = entry_digest
                con.commit()
            except sqlite3.IntegrityError as exc:
                con.rollback()
                raise SettlementLedgerError("settlement replay or journal uniqueness conflict") from exc
            except Exception:
                con.rollback()
                raise
        return {"receipt_id": receipt_id, "journal_entries": 2, "amount_minor": verified["amount_minor"],
                "currency": verified["currency"], "accounting_status": "POSTED"}

    def audit_proof(self) -> dict:
        with closing(self._connect()) as con:
            payments = con.execute("SELECT receipt_id,amount_minor,currency FROM settled_payments ORDER BY receipt_id").fetchall()
            entries = con.execute(
                "SELECT entry_id,receipt_id,side,amount_minor,currency,payload_json,previous_digest,entry_digest "
                "FROM accounting_journal ORDER BY sequence"
            ).fetchall()
        previous = "0" * 64
        totals = {}
        for entry_id, receipt_id, side, amount, currency, payload_json, previous_digest, entry_digest in entries:
            expected = hashlib.sha256((previous + payload_json).encode("utf-8")).hexdigest()
            if previous_digest != previous or entry_digest != expected:
                raise SettlementLedgerError("accounting journal hash-chain verification failed")
            raw = json.loads(payload_json)
            if raw.get("entry_id") != entry_id or raw.get("receipt_id") != receipt_id:
                raise SettlementLedgerError("accounting journal row identity mismatch")
            key = (receipt_id, currency)
            totals.setdefault(key, {"DEBIT": 0, "CREDIT": 0})
            totals[key][side] += amount
            previous = entry_digest
        for payment_id, amount, currency in payments:
            pair = totals.get((payment_id, currency))
            if pair != {"DEBIT": amount, "CREDIT": amount}:
                raise SettlementLedgerError("settlement journal is not balanced")
        if len(entries) != 2 * len(payments):
            raise SettlementLedgerError("settlement journal has orphan or missing entries")
        return {
            "verified": True, "settled_payments": len(payments),
            "journal_entries": len(entries), "balanced": True,
            "head_digest": previous,
            "proof_digest": hashlib.sha256((previous + str(len(payments))).encode()).hexdigest(),
        }
