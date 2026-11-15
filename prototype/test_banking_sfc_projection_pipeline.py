"""Integration tests for source-verified banking SFC persistence/recovery."""
import tempfile
import unittest
from pathlib import Path

from banking_sfc_projection_pipeline import project_and_persist, rebuild_and_verify
from banking_sfc_projection_store import BankingSFCProjectionStore
from test_operating_financial_sfc_adapter import fixture, history_row


class FakeFinancialRegister:
    REGISTER_NAME = "financial"
    register_instance_id = "11111111111141118111111111111111"

    def __init__(self, rows):
        self.rows = tuple(rows)

    def verify(self):
        return True

    def history(self, aggregate_id, *, principal_id):
        if aggregate_id != "operating-financial" or principal_id != "auditor":
            raise AssertionError("unexpected source scope")
        return self.rows


class BankingSFCPipelineTests(unittest.TestCase):
    def test_verified_source_replay_persists_and_recovers_same_checkpoint(self):
        terms, sectors, _identities, snapshot = fixture()
        payload = {
            "loan_id": "LOAN-1",
            "borrower_id": "household-1",
            "bank_id": "bank-1",
            "currency": "LCU",
            "amount": "100",
            "period_index": 3,
            "evidence_ref": "SIGNED-LOAN-1",
        }
        source = FakeFinancialRegister([
            history_row("LOAN-ORIG-1", "bank.loan_originated", payload, sequence=7)
        ])
        with tempfile.TemporaryDirectory() as directory:
            store = BankingSFCProjectionStore(Path(directory) / "projection.sqlite")
            projection, receipt = project_and_persist(
                source, principal_id="auditor", instrument_registry=terms,
                sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                source_register_id=source.register_instance_id,
            )
            recovered, checkpoint = rebuild_and_verify(
                source, principal_id="auditor", instrument_registry=terms,
                sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                source_register_id="financial-register:auditor",
            )
            self.assertEqual(projection.source_digest, recovered.source_digest)
            self.assertEqual(receipt["checkpoint_digest"], checkpoint["checkpoint_digest"])
            self.assertEqual(checkpoint["applied_through_sequence"], 7)

    def test_caller_cannot_substitute_or_omit_source_register_identity(self):
        terms, sectors, _identities, snapshot = fixture()
        source = FakeFinancialRegister([
            history_row("LOAN-ORIG-1", "bank.loan_originated", {
                "loan_id": "LOAN-1", "borrower_id": "household-1",
                "bank_id": "bank-1", "currency": "LCU", "amount": "100",
                "period_index": 3, "evidence_ref": "SIGNED-LOAN-1",
            }, sequence=7)
        ])
        with tempfile.TemporaryDirectory() as directory:
            store = BankingSFCProjectionStore(Path(directory) / "projection.sqlite")
            with self.assertRaisesRegex(ValueError, "exactly match.*instance identity"):
                project_and_persist(
                    source, principal_id="auditor", instrument_registry=terms,
                    sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                    source_register_id="22222222222242228222222222222222",
                )
            with self.assertRaisesRegex(ValueError, "exactly match.*instance identity"):
                rebuild_and_verify(
                    source, principal_id="auditor", instrument_registry=terms,
                    sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                    source_register_id="22222222222242228222222222222222",
                )
            source.register_instance_id = None
            with self.assertRaisesRegex(ValueError, "exactly match.*instance identity"):
                project_and_persist(
                    source, principal_id="auditor", instrument_registry=terms,
                    sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                    source_register_id="11111111111141118111111111111111",
                )
            self.assertIsNone(store.latest_checkpoint(
                "11111111111141118111111111111111"
            ))


    def test_unverified_source_chain_is_rejected_before_persistence(self):
        terms, sectors, _identities, snapshot = fixture()
        source = FakeFinancialRegister([
            history_row("LOAN-ORIG-1", "bank.loan_originated", {
                "loan_id": "LOAN-1", "borrower_id": "household-1",
                "bank_id": "bank-1", "currency": "LCU", "amount": "100",
                "period_index": 3, "evidence_ref": "SIGNED-LOAN-1",
            }, sequence=7)
        ])
        source.verify = lambda: False
        with tempfile.TemporaryDirectory() as directory:
            store = BankingSFCProjectionStore(Path(directory) / "projection.sqlite")
            with self.assertRaisesRegex(ValueError, "verified native financial"):
                project_and_persist(
                    source, principal_id="auditor", instrument_registry=terms,
                    sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                    source_register_id="financial-register:auditor",
                )
            self.assertIsNone(store.latest_checkpoint(source.register_instance_id))


if __name__ == "__main__":
    unittest.main()
