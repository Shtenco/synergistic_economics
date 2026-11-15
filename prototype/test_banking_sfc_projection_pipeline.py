"""Integration tests for source-verified banking SFC persistence/recovery."""
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from banking_sfc_projection_pipeline import (
    build_opening_snapshots_from_register, project_and_persist, rebuild_and_verify,
)
from banking_sfc_projection_store import BankingSFCProjectionStore
from operating_financial_register import OperatingFinancialRegister
from test_operating_financial_sfc_adapter import fixture, history_row


class FakeFinancialRegister:
    REGISTER_NAME = "financial"

    def __init__(self, rows):
        self.rows = tuple(rows)

    def verify(self):
        return True

    def source_checkpoint(self):
        return {
            "register_instance_id": "a" * 32,
            "event_count": 7,
            "tail_hash": "b" * 64,
        }

    def chain_hash_at(self, sequence):
        if sequence == 7:
            return "b" * 64
        if sequence == 0:
            return "0" * 64
        raise AssertionError("unexpected source-chain ancestor cursor")

    def history_with_checkpoint(self, aggregate_id, *, principal_id):
        if not self.verify():
            raise ValueError("source register verification failed")
        return self.history(aggregate_id, principal_id=principal_id), self.source_checkpoint()

    def history(self, aggregate_id, *, principal_id):
        if aggregate_id != "operating-financial" or principal_id != "auditor":
            raise AssertionError("unexpected source scope")
        return self.rows


class BankingSFCPipelineTests(unittest.TestCase):
    @staticmethod
    def pinned(snapshot, principal_id="auditor"):
        return replace(
            snapshot,
            source_register_id=f"financial:{'a' * 32}:{principal_id}",
            source_sequence=7,
            source_chain_hash="b" * 64,
        )

    def test_verified_source_replay_persists_and_recovers_same_checkpoint(self):
        terms, sectors, _identities, snapshot = fixture()
        snapshot = self.pinned(snapshot)
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
                source_register_id="financial:" + "a" * 32 + ":auditor",
            )
            recovered, checkpoint = rebuild_and_verify(
                source, principal_id="auditor", instrument_registry=terms,
                sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                source_register_id="financial:" + "a" * 32 + ":auditor",
            )
            self.assertEqual(projection.source_digest, recovered.source_digest)
            self.assertEqual(receipt["checkpoint_digest"], checkpoint["checkpoint_digest"])
            self.assertEqual(checkpoint["applied_through_sequence"], 7)

    def test_real_durable_financial_register_projects_and_recovers_exact_chain_tail(self):
        terms, sectors, _identities, _fixture_snapshot = fixture()
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            register_path = root / "financial.sqlite3"
            register = OperatingFinancialRegister(
                register_path,
                sectors={"household-1": "H", "bank-1": "CB"},
            )
            register.bootstrap_admin(
                principal_id="financial-root", authority_ref="BOOTSTRAP",
                occurred_at="2026-11-15T00:00:00Z",
            )
            register.open_deposit_account(
                event_id="OPEN-HOUSEHOLD", entity_id="household-1", bank_id="bank-1",
                currency="LCU", account_ref="HOUSEHOLD-ACCOUNT", opening_balance="0",
                evidence_ref="BANK-OPEN-HOUSEHOLD", actor_id="financial-root",
                authority_ref="BANK-OPENING", effective_at="2026-11-15T00:00:00Z",
                recorded_at="2026-11-15T00:00:00Z", expected_revision=0,
            )
            register.commit_bank_credit(
                event_id="REAL-LOAN-ORIGINATION", event_type="bank.loan_originated",
                loan_id="LOAN-1", borrower_id="household-1", bank_id="bank-1",
                currency="LCU", amount="100", period_index=3,
                evidence_ref="SIGNED-REAL-LOAN", actor_id="financial-root",
                authority_ref="CREDIT-POLICY", effective_at="2026-11-15T00:00:00Z",
                recorded_at="2026-11-15T00:00:01Z", expected_revision=1,
            )
            snapshot = build_opening_snapshots_from_register(
                register, principal_id="financial-root", periods=[3],
                instrument_registry=terms, sector_registry=sectors,
            )[0]
            self.assertEqual(snapshot.source_register_id,
                             f"financial:{register.register_instance_id}:financial-root")
            self.assertEqual(snapshot.source_sequence, 3)
            self.assertEqual(snapshot.source_chain_hash, register.source_checkpoint()["tail_hash"])
            self.assertEqual(len(snapshot.positions), 4)
            store = BankingSFCProjectionStore(root / "projection.sqlite")
            projection, receipt = project_and_persist(
                register, principal_id="financial-root", instrument_registry=terms,
                sector_registry=sectors, opening_snapshots=[snapshot], store=store,
            )
            recovered, checkpoint = rebuild_and_verify(
                register, principal_id="financial-root", instrument_registry=terms,
                sector_registry=sectors, opening_snapshots=[snapshot], store=store,
            )
            self.assertEqual(projection.source_digest, recovered.source_digest)
            self.assertEqual(receipt["checkpoint_digest"], checkpoint["checkpoint_digest"])
            self.assertEqual(checkpoint["applied_through_sequence"], 3)
            self.assertEqual(projection.mapped_source_event_count, 1)
            self.assertEqual(register.source_checkpoint()["tail_hash"],
                             store.latest_checkpoint(
                                 "financial:" + register.register_instance_id + ":financial-root"
                             )["source_chain_hash"])

    def test_pipeline_rejects_openings_without_source_checkpoint_provenance(self):
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
            with self.assertRaisesRegex(ValueError, "not pinned to the exact verified financial source checkpoint"):
                project_and_persist(
                    source, principal_id="auditor", instrument_registry=terms,
                    sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                )
            self.assertIsNone(store.latest_checkpoint("financial:" + "a" * 32 + ":auditor"))

    def test_caller_cannot_substitute_another_source_register_identity(self):
        terms, sectors, _identities, snapshot = fixture()
        snapshot = self.pinned(snapshot)
        source = FakeFinancialRegister([
            history_row("LOAN-ORIG-1", "bank.loan_originated", {
                "loan_id": "LOAN-1", "borrower_id": "household-1",
                "bank_id": "bank-1", "currency": "LCU", "amount": "100",
                "period_index": 3, "evidence_ref": "SIGNED-LOAN-1",
            }, sequence=7)
        ])
        with tempfile.TemporaryDirectory() as directory:
            store = BankingSFCProjectionStore(Path(directory) / "projection.sqlite")
            with self.assertRaisesRegex(ValueError, "differs from durable register identity"):
                project_and_persist(
                    source, principal_id="auditor", instrument_registry=terms,
                    sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                    source_register_id="caller-controlled-register-id",
                )

    def test_pipeline_requires_atomic_history_checkpoint_api(self):
        terms, sectors, _identities, snapshot = fixture()
        source = FakeFinancialRegister([
            history_row("LOAN-ORIG-1", "bank.loan_originated", {
                "loan_id": "LOAN-1", "borrower_id": "household-1",
                "bank_id": "bank-1", "currency": "LCU", "amount": "100",
                "period_index": 3, "evidence_ref": "SIGNED-LOAN-1",
            }, sequence=7)
        ])
        source.history_with_checkpoint = None
        with tempfile.TemporaryDirectory() as directory:
            store = BankingSFCProjectionStore(Path(directory) / "projection.sqlite")
            with self.assertRaisesRegex(ValueError, "atomic verified history/checkpoint read"):
                project_and_persist(
                    source, principal_id="auditor", instrument_registry=terms,
                    sector_registry=sectors, opening_snapshots=[snapshot], store=store,
                )
            self.assertIsNone(store.latest_checkpoint("financial:" + "a" * 32 + ":auditor"))

    def test_forked_source_cannot_advance_a_sealed_projection_checkpoint(self):
        terms, sectors, _identities, snapshot = fixture()
        snapshot = self.pinned(snapshot)
        source = FakeFinancialRegister([
            history_row("LOAN-ORIG-1", "bank.loan_originated", {
                "loan_id": "LOAN-1", "borrower_id": "household-1",
                "bank_id": "bank-1", "currency": "LCU", "amount": "100",
                "period_index": 3, "evidence_ref": "SIGNED-LOAN-1",
            }, sequence=7)
        ])
        with tempfile.TemporaryDirectory() as directory:
            store = BankingSFCProjectionStore(Path(directory) / "projection.sqlite")
            project_and_persist(
                source, principal_id="auditor", instrument_registry=terms,
                sector_registry=sectors, opening_snapshots=[snapshot], store=store,
            )
            source.source_checkpoint = lambda: {
                "register_instance_id": "a" * 32,
                "event_count": 8,
                "tail_hash": "c" * 64,
            }
            source.history_with_checkpoint = lambda aggregate_id, *, principal_id: (
                source.history(aggregate_id, principal_id=principal_id),
                {"register_instance_id": "a" * 32, "event_count": 8, "tail_hash": "c" * 64},
            )
            source.chain_hash_at = lambda sequence: "d" * 64
            forked_snapshot = replace(
                snapshot, source_sequence=8, source_chain_hash="c" * 64,
            )
            with self.assertRaisesRegex(ValueError, "diverges from the previously sealed checkpoint"):
                project_and_persist(
                    source, principal_id="auditor", instrument_registry=terms,
                    sector_registry=sectors, opening_snapshots=[forked_snapshot], store=store,
                )
            latest = store.latest_checkpoint("financial:" + "a" * 32 + ":auditor")
            self.assertEqual(latest["applied_through_sequence"], 7)
            self.assertEqual(latest["source_chain_hash"], "b" * 64)

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
            self.assertIsNone(store.latest_checkpoint("financial:" + "a" * 32 + ":auditor"))


if __name__ == "__main__":
    unittest.main()
