import sqlite3
from pathlib import Path

import pytest

from payment_settlement_ledger import PaymentSettlementLedger, SettlementLedgerError


def verified_payment(**overrides):
    receipt = {
        "verified": True, "payment_rail": "BANK-API",
        "transaction_id": "bank-tx-001", "log_index": 0,
        "payment_id": "payment-001", "tenant_id": "tenant-kz",
        "contract_ref": "contract-001", "payer_id": "buyer-001",
        "payee_id": "seller-001", "currency": "KZT",
        "amount_minor": 125000, "settled_at": "2026-11-16T00:00:00Z",
        "evidence_digest": "b" * 64, "settlement_status": "SETTLED",
    }
    receipt.update(overrides)
    return receipt


def test_payment_requires_independent_settlement_verifier_and_finality(tmp_path):
    ledger = PaymentSettlementLedger(
        tmp_path / "ledger.sqlite3",
        settlement_evidence_verifier=lambda _: {"verified": False},
    )
    with pytest.raises(SettlementLedgerError, match="not independently verified"):
        ledger.post_settlement(evidence={})
    ledger = PaymentSettlementLedger(
        tmp_path / "ledger2.sqlite3",
        settlement_evidence_verifier=lambda _: verified_payment(settlement_status="PENDING"),
    )
    with pytest.raises(SettlementLedgerError, match="final SETTLED"):
        ledger.post_settlement(evidence={})


def test_verified_payment_posts_balanced_double_entry_and_audit_proof(tmp_path):
    ledger = PaymentSettlementLedger(
        tmp_path / "ledger.sqlite3",
        settlement_evidence_verifier=lambda _: verified_payment(),
    )
    posted = ledger.post_settlement(evidence={"signed_bank_receipt": "opaque"})
    assert posted["accounting_status"] == "POSTED"
    assert posted["journal_entries"] == 2
    proof = ledger.audit_proof()
    assert proof["verified"] is True
    assert proof["balanced"] is True
    assert proof["settled_payments"] == 1
    assert proof["journal_entries"] == 2
    assert len(proof["proof_digest"]) == 64


def test_payment_receipt_replay_is_rejected_and_restart_preserves_audit(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    verifier = lambda _: verified_payment()
    first = PaymentSettlementLedger(path, settlement_evidence_verifier=verifier)
    first.post_settlement(evidence={})
    expected = first.audit_proof()
    restarted = PaymentSettlementLedger(path, settlement_evidence_verifier=verifier)
    assert restarted.audit_proof() == expected
    with pytest.raises(SettlementLedgerError, match="replay"):
        restarted.post_settlement(evidence={})


def test_payment_ledger_is_append_only(tmp_path):
    path = tmp_path / "ledger.sqlite3"
    ledger = PaymentSettlementLedger(
        path, settlement_evidence_verifier=lambda _: verified_payment()
    )
    ledger.post_settlement(evidence={})
    with sqlite3.connect(path) as con:
        with pytest.raises(sqlite3.IntegrityError, match="append-only"):
            con.execute("UPDATE accounting_journal SET amount_minor=1 WHERE sequence=1")
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            con.execute("DELETE FROM settled_payments")
