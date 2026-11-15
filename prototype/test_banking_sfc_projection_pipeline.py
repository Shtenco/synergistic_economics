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
from test_operating_financial_sfc_adapter import fixture, history_row, instrument
from sfc_source_contracts import EffectiveDatedSectorRegistry, InstrumentTermsRegistry, SectorMembership


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
            snapshots = build_opening_snapshots_from_register(
                register, principal_id="financial-root", periods=[3, 4],
                instrument_registry=terms, sector_registry=sectors,
            )
            snapshot, next_snapshot = snapshots
            self.assertEqual(snapshot.source_register_id,
                             f"financial:{register.register_instance_id}:financial-root")
            self.assertEqual(snapshot.source_sequence, 3)
            self.assertEqual(snapshot.source_chain_hash, register.source_checkpoint()["tail_hash"])
            self.assertEqual(len(snapshot.positions), 4)
            for item in snapshot.positions:
                self.assertEqual(item.balance, "0")
                self.assertIn(snapshot.source_chain_hash, item.source_ref)
            next_balances = {
                (item.identity.instrument_id, item.identity.holder_entity_id): item.balance
                for item in next_snapshot.positions
            }
            self.assertEqual(next_balances[("LOAN:LOAN-1", "bank-1")], "100")
            self.assertEqual(next_balances[("LOAN:LOAN-1", "household-1")], "100")
            self.assertEqual(next_balances[("DEPOSIT:household-1:bank-1:LCU", "household-1")], "100")
            self.assertEqual(next_balances[("DEPOSIT:household-1:bank-1:LCU", "bank-1")], "100")
            self.assertNotEqual(snapshot.digest, replace(snapshot, source_chain_hash="c" * 64).digest)
            store = BankingSFCProjectionStore(root / "projection.sqlite")
            projection, receipt = project_and_persist(
                register, principal_id="financial-root", instrument_registry=terms,
                sector_registry=sectors, opening_snapshots=snapshots, store=store,
            )
            recovered, checkpoint = rebuild_and_verify(
                register, principal_id="financial-root", instrument_registry=terms,
                sector_registry=sectors, opening_snapshots=snapshots, store=store,
            )
            self.assertEqual(projection.source_digest, recovered.source_digest)
            self.assertEqual(receipt["checkpoint_digest"], checkpoint["checkpoint_digest"])
            self.assertEqual(checkpoint["applied_through_sequence"], 3)
            self.assertEqual(projection.mapped_source_event_count, 1)
            self.assertEqual(register.source_checkpoint()["tail_hash"],
                             store.latest_checkpoint(
                                 "financial:" + register.register_instance_id + ":financial-root"
                             )["source_chain_hash"])

    def test_opening_builder_composes_deposit_reserve_loan_and_refinancing_stocks(self):
        base_terms, base_sectors, _identities, _fixture_snapshot = fixture()
        reserve_id = "RESERVE:bank-1:central-bank-1:LCU"
        refinancing_id = "CBREFI:FACILITY-1"
        terms = InstrumentTermsRegistry(
            "terms-banking-v1",
            base_terms.terms + (
                instrument(reserve_id, "RESERVE"),
                instrument(refinancing_id, "CBREFI"),
            ),
        )
        sectors = EffectiveDatedSectorRegistry(
            base_sectors.version,
            base_sectors.allowed_sector_codes,
            base_sectors.memberships + (
                SectorMembership("central-bank-1", "CBank", 1, None),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            register = OperatingFinancialRegister(
                Path(directory) / "financial.sqlite3",
                sectors={
                    "household-1": "H", "bank-1": "CB",
                    "central-bank-1": "CBank",
                },
            )
            register.bootstrap_admin(
                principal_id="financial-root", authority_ref="BOOTSTRAP",
                occurred_at="2026-11-15T00:00:00Z",
            )
            register.open_deposit_account(
                event_id="OPEN-DEPOSIT", entity_id="household-1", bank_id="bank-1",
                currency="LCU", account_ref="DEPOSIT-ACCOUNT", opening_balance="0",
                evidence_ref="DEPOSIT-OPEN-EVIDENCE", actor_id="financial-root",
                authority_ref="BANK-OPENING", effective_at="2026-11-15T00:00:00Z",
                recorded_at="2026-11-15T00:00:00Z", expected_revision=0,
            )
            register.open_bank_reserve_account(
                event_id="OPEN-RESERVE", bank_id="bank-1", central_bank_id="central-bank-1",
                currency="LCU", account_ref="RESERVE-ACCOUNT", opening_balance="50",
                evidence_ref="RESERVE-OPEN-EVIDENCE", actor_id="financial-root",
                authority_ref="CBANK-OPENING", effective_at="2026-11-15T00:00:01Z",
                recorded_at="2026-11-15T00:00:01Z", expected_revision=1,
            )
            register.commit_bank_credit(
                event_id="LOAN-ORIGINATION", event_type="bank.loan_originated",
                loan_id="LOAN-1", borrower_id="household-1", bank_id="bank-1",
                currency="LCU", amount="100", period_index=3,
                evidence_ref="SIGNED-LOAN", actor_id="financial-root",
                authority_ref="CREDIT-POLICY", effective_at="2026-11-15T00:00:02Z",
                recorded_at="2026-11-15T00:00:02Z", expected_revision=2,
            )
            register.commit_central_bank_refinancing(
                event_id="REFINANCING-ADVANCE",
                event_type="central_bank.refinancing_advanced",
                facility_id="FACILITY-1", bank_id="bank-1",
                central_bank_id="central-bank-1", currency="LCU", amount="100",
                period_index=3, evidence_ref="SIGNED-REFINANCING",
                actor_id="financial-root", authority_ref="CBANK-POLICY",
                effective_at="2026-11-15T00:00:03Z",
                recorded_at="2026-11-15T00:00:03Z", expected_revision=3,
            )
            snapshots = build_opening_snapshots_from_register(
                register, principal_id="financial-root", periods=[3, 4],
                instrument_registry=terms, sector_registry=sectors,
            )
            self.assertEqual(len(snapshots[0].positions), 8)
            opening3 = {
                (row.identity.instrument_id, row.identity.holder_entity_id): row.balance
                for row in snapshots[0].positions
            }
            opening4 = {
                (row.identity.instrument_id, row.identity.holder_entity_id): row.balance
                for row in snapshots[1].positions
            }
            self.assertEqual(opening3[(reserve_id, "bank-1")], "50")
            self.assertEqual(opening3[(refinancing_id, "central-bank-1")], "0")
            self.assertEqual(opening3[("LOAN:LOAN-1", "bank-1")], "0")
            self.assertEqual(opening4[(reserve_id, "bank-1")], "150")
            self.assertEqual(opening4[(refinancing_id, "central-bank-1")], "100")
            self.assertEqual(opening4[("LOAN:LOAN-1", "bank-1")], "100")
            self.assertEqual(opening4[("DEPOSIT:household-1:bank-1:LCU", "household-1")], "100")
            self.assertEqual(snapshots[0].source_sequence, 5)
            self.assertEqual(snapshots[1].source_chain_hash, snapshots[0].source_chain_hash)

    def test_opening_builder_fails_if_source_changes_during_export(self):
        terms, sectors, _identities, _fixture_snapshot = fixture()
        with tempfile.TemporaryDirectory() as directory:
            register = OperatingFinancialRegister(
                Path(directory) / "financial.sqlite3",
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
            original_export = register.refinancing_opening_positions
            def append_during_export(*, period_index, principal_id):
                rows = original_export(period_index=period_index, principal_id=principal_id)
                register.commit_bank_credit(
                    event_id="CONCURRENT-LOAN-ORIGINATION",
                    event_type="bank.loan_originated", loan_id="LOAN-2",
                    borrower_id="household-1", bank_id="bank-1", currency="LCU",
                    amount="5", period_index=4, evidence_ref="SIGNED-LOAN-2",
                    actor_id="financial-root", authority_ref="CREDIT-POLICY",
                    effective_at="2026-11-15T00:00:02Z",
                    recorded_at="2026-11-15T00:00:02Z", expected_revision=2,
                )
                return rows
            register.refinancing_opening_positions = append_during_export
            with self.assertRaisesRegex(ValueError, "source changed while opening snapshots were being assembled"):
                build_opening_snapshots_from_register(
                    register, principal_id="financial-root", periods=[3],
                    instrument_registry=terms, sector_registry=sectors,
                )

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
