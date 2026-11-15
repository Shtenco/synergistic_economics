"""Integration tests for source-verified banking SFC persistence/recovery."""
import tempfile
import unittest
from dataclasses import replace
from decimal import Decimal
from pathlib import Path

from banking_sfc_projection_pipeline import (
    build_opening_snapshots_from_register, project_and_persist, rebuild_and_verify,
)
from banking_sfc_projection_store import BankingSFCProjectionStore
from operating_financial_register import (
    OperatingFinancialRegister, wage_stock_flow_movement_specs,
)
from test_operating_financial_sfc_adapter import fixture, history_row, instrument
from sfc_source_contracts import EffectiveDatedSectorRegistry, InstrumentTermsRegistry, SectorMembership
from test_operating_wage_cross_register import build_wage_events, labour_fixture


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

    def test_legacy_loan_and_refinancing_openings_project_without_double_counting_creation(self):
        base_terms, base_sectors, _identities, _fixture_snapshot = fixture()
        loan_id = "LOAN:LEGACY-LOAN-1"
        deposit_id = "DEPOSIT:household-1:bank-1:LCU"
        reserve_id = "RESERVE:bank-1:central-bank-1:LCU"
        refi_id = "CBREFI:LEGACY-REFI-1"
        terms = InstrumentTermsRegistry(
            "terms-legacy-opening-v1",
            tuple(replace(term, effective_from_period=1) for term in base_terms.terms)
            + tuple(replace(instrument(item_id, instrument_class), effective_from_period=1)
                    for item_id, instrument_class in (
                        (loan_id, "LOAN"), (reserve_id, "RESERVE"),
                        (refi_id, "CBREFI"),
                    )),
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
                Path(directory) / "legacy-financial.sqlite3",
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
                event_id="LEGACY-DEPOSIT-OPEN", entity_id="household-1",
                bank_id="bank-1", currency="LCU", account_ref="LEGACY-DEPOSIT",
                opening_balance="1000", evidence_ref="DEPOSIT-OPEN-EVIDENCE",
                actor_id="financial-root", authority_ref="BANK-OPENING",
                effective_at="2026-11-15T00:00:00Z",
                recorded_at="2026-11-15T00:00:00Z", expected_revision=0,
            )
            register.open_bank_reserve_account(
                event_id="LEGACY-RESERVE-OPEN", bank_id="bank-1",
                central_bank_id="central-bank-1", currency="LCU",
                account_ref="LEGACY-RESERVE", opening_balance="200",
                evidence_ref="RESERVE-OPEN-EVIDENCE", actor_id="financial-root",
                authority_ref="CBANK-OPENING", effective_at="2026-11-15T00:00:01Z",
                recorded_at="2026-11-15T00:00:01Z", expected_revision=1,
            )
            register.record_existing_bank_loan(
                event_id="LEGACY-LOAN-OPENING", loan_id="LEGACY-LOAN-1",
                borrower_id="household-1", bank_id="bank-1", currency="LCU",
                original_principal="150", outstanding_principal="100",
                origination_period_index=0, opening_period_index=1,
                source_account_ref="LEGACY-DEPOSIT",
                contract_ref="LEGACY-LOAN-CONTRACT",
                contract_evidence_ref="SIGNED-LEGACY-LOAN-CONTRACT",
                evidence_ref="LEGACY-LOAN-OPENING-CERTIFICATE",
                actor_id="financial-root", authority_ref="LOAN-OPENING-AUTHORITY",
                effective_at="2026-11-15T00:00:02Z",
                recorded_at="2026-11-15T00:00:02Z", expected_revision=2,
            )
            register.record_existing_refinancing_facility(
                event_id="LEGACY-REFI-OPENING", facility_id="LEGACY-REFI-1",
                bank_id="bank-1", central_bank_id="central-bank-1", currency="LCU",
                original_principal="150", outstanding_principal="100",
                origination_period_index=0, opening_period_index=1,
                source_account_ref="LEGACY-RESERVE",
                contract_ref="LEGACY-REFI-CONTRACT",
                contract_evidence_ref="SIGNED-LEGACY-REFI-CONTRACT",
                evidence_ref="LEGACY-REFI-OPENING-CERTIFICATE",
                actor_id="financial-root", authority_ref="REFI-OPENING-AUTHORITY",
                effective_at="2026-11-15T00:00:03Z",
                recorded_at="2026-11-15T00:00:03Z", expected_revision=3,
            )
            self.assertEqual(
                register.deposit_balance("household-1", "LCU", principal_id="financial-root")[0],
                Decimal("1000"),
            )
            self.assertEqual(
                register.reserve_balance("bank-1", "central-bank-1", "LCU", principal_id="financial-root")[0],
                Decimal("200"),
            )
            register.commit_bank_credit(
                event_id="LEGACY-LOAN-REPAY", event_type="bank.loan_principal_repaid",
                loan_id="LEGACY-LOAN-1", borrower_id="household-1", bank_id="bank-1",
                currency="LCU", amount="20", period_index=1,
                evidence_ref="LEGACY-LOAN-REPAYMENT", causation_id="LEGACY-LOAN-OPENING",
                actor_id="financial-root", authority_ref="BANK-CREDIT-POLICY",
                effective_at="2026-11-15T00:00:04Z",
                recorded_at="2026-11-15T00:00:04Z", expected_revision=4,
            )
            register.commit_central_bank_refinancing(
                event_id="LEGACY-REFI-REPAY",
                event_type="central_bank.refinancing_principal_repaid",
                facility_id="LEGACY-REFI-1", bank_id="bank-1",
                central_bank_id="central-bank-1", currency="LCU", amount="30",
                period_index=1, evidence_ref="LEGACY-REFI-REPAYMENT",
                actor_id="financial-root", authority_ref="REFI-POLICY",
                effective_at="2026-11-15T00:00:05Z",
                recorded_at="2026-11-15T00:00:05Z", expected_revision=5,
                causation_id="LEGACY-REFI-OPENING",
            )
            snapshots = build_opening_snapshots_from_register(
                register, principal_id="financial-root", periods=[1, 2],
                instrument_registry=terms, sector_registry=sectors,
            )
            self.assertEqual(len(snapshots[0].positions), 8)
            opening1 = {
                (item.identity.instrument_id, item.identity.holder_entity_id): Decimal(item.balance)
                for item in snapshots[0].positions
            }
            opening2 = {
                (item.identity.instrument_id, item.identity.holder_entity_id): Decimal(item.balance)
                for item in snapshots[1].positions
            }
            self.assertEqual(opening1[(loan_id, "bank-1")], Decimal("100"))
            self.assertEqual(opening1[(refi_id, "central-bank-1")], Decimal("100"))
            self.assertEqual(opening1[(deposit_id, "household-1")], Decimal("1000"))
            self.assertEqual(opening1[(reserve_id, "bank-1")], Decimal("200"))
            self.assertEqual(opening2[(loan_id, "bank-1")], Decimal("80"))
            self.assertEqual(opening2[(refi_id, "central-bank-1")], Decimal("70"))
            self.assertEqual(opening2[(deposit_id, "household-1")], Decimal("980"))
            self.assertEqual(opening2[(reserve_id, "bank-1")], Decimal("170"))
            store = BankingSFCProjectionStore(Path(directory) / "legacy-projection.sqlite")
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
            self.assertEqual(projection.excluded_opening_event_count, 4)

    def test_opening_builder_includes_unpaid_wage_claim_and_payable_stocks(self):
        claim_id = "ENGAGEMENT-1:DELIVERY-1"
        wage_instrument = f"WAGE:{claim_id}"
        base_terms, _base_sectors, _identities, _snapshot = fixture()
        wage_terms = instrument(wage_instrument, "WAGE_CLAIM")
        terms = InstrumentTermsRegistry("terms-wage-v1", base_terms.terms + (wage_terms,))
        sectors = EffectiveDatedSectorRegistry(
            "sectors-wage-v1", frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"}),
            (
                SectorMembership("worker-1", "H", 1, None),
                SectorMembership("employer-1", "NFC", 1, None),
                SectorMembership("bank-1", "CB", 1, None),
            ),
        )
        with tempfile.TemporaryDirectory() as directory:
            register = OperatingFinancialRegister(
                Path(directory) / "financial.sqlite3",
                sectors={"worker-1": "H", "employer-1": "NFC", "bank-1": "CB"},
            )
            register.bootstrap_admin(
                principal_id="financial-root", authority_ref="BOOTSTRAP",
                occurred_at="2026-11-15T00:00:00Z",
            )
            subevent = {
                "event_id": "WAGE-ACCRUAL-1", "event_type": "wage_accrual",
                "claim_id": claim_id, "engagement_id": "ENGAGEMENT-1",
                "worker_id": "worker-1", "employer_id": "employer-1",
                "bank_id": "bank-1", "currency": "LCU", "amount": "100",
                "minor_unit": "0.01", "period_index": 3,
                "period_label": "P3", "delivery_event_id": "DELIVERY-1",
                "causation_id": "DELIVERY-1", "evidence_ref": "WAGE-EVIDENCE",
                "delivery_evidence_ref": "DELIVERY-EVIDENCE",
                "verification_ref": "SUPERVISOR-VERIFICATION",
                "contract_ref": "SIGNED-CONTRACT",
                "contract_evidence_ref": "CONTRACT-EVIDENCE",
                "labour_aggregate_version": 7, "delivered_hours": "10",
                "hourly_rate": "10",
            }
            posting_template = (
                ("wage_expense", "D", "employer-1", "worker-1", claim_id, "NFC"),
                ("wage_payable", "C", "employer-1", "worker-1", claim_id, "NFC"),
                ("wage_receivable", "D", "worker-1", "employer-1", claim_id, "H"),
                ("wage_income", "C", "worker-1", "employer-1", claim_id, "H"),
            )
            subevent["postings"] = [
                {
                    "account": account, "side": side, "entity_id": entity,
                    "counterparty_id": counterparty, "instrument_id": instrument_id,
                    "currency": "LCU", "sector": sector, "amount": "100",
                }
                for account, side, entity, counterparty, instrument_id, sector
                in posting_template
            ]
            event_id = "WAGE-GROUP-1"
            envelope = {
                "event_type": "wage.event_group_committed",
                "effective_at": "2026-11-15T00:00:01Z",
                "recorded_at": "2026-11-15T00:00:01Z",
                "actor_id": "financial-root", "authority_ref": "WAGE-POLICY",
                "idempotency_key": event_id,
                "payload": {"claim_id": claim_id, "events": [subevent]},
                "stock_flow_movements": wage_stock_flow_movement_specs([subevent]),
            }
            operation = {
                "stream_id": "operating-financial", "native_event_id": event_id,
                "expected_revision": 0, "payload": envelope,
            }
            token = register.prepare(event_id, operation)
            register.commit(event_id, token)
            snapshots = build_opening_snapshots_from_register(
                register, principal_id="financial-root", periods=[3, 4],
                instrument_registry=terms, sector_registry=sectors,
            )
            self.assertEqual(len(snapshots[0].positions), 2)
            self.assertEqual({item.balance for item in snapshots[0].positions}, {"0"})
            self.assertEqual({item.balance for item in snapshots[1].positions}, {"100"})
            self.assertEqual(
                {item.identity.instrument_id for item in snapshots[1].positions},
                {wage_instrument},
            )
            self.assertEqual(
                {item.identity.holder_entity_id for item in snapshots[1].positions},
                {"worker-1", "employer-1"},
            )

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


    def test_opening_builder_includes_bilateral_wage_claim_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            labour = labour_fixture(root / "labour.sqlite3")
            _delivery, _contract, _journal, wage_events = build_wage_events(labour)
            accrual = wage_events[0]
            register = OperatingFinancialRegister(
                root / "financial.sqlite3",
                sectors={"worker-1": "H", "employer-1": "NFC", "bank-1": "CB"},
            )
            register.bootstrap_admin(
                principal_id="financial-root", authority_ref="BOOTSTRAP",
                occurred_at="2026-11-15T00:00:00Z",
            )
            event_payload = accrual.to_native_payload()
            financial_payload = {
                "claim_id": accrual.claim_id,
                "events": [event_payload],
            }
            movements = [
                dict(movement) for movement in accrual.stock_flow_movements
            ]
            event_id = "WAGE-GROUP-OPENING-1"
            operation = {
                "stream_id": "operating-financial",
                "native_event_id": event_id,
                "expected_revision": 0,
                "payload": {
                    "event_type": "wage.event_group_committed",
                    "effective_at": "2026-11-15T00:00:01Z",
                    "recorded_at": "2026-11-15T00:00:01Z",
                    "actor_id": "financial-root",
                    "authority_ref": "WAGE-ACCRUAL-AUTHORITY",
                    "idempotency_key": event_id,
                    "payload": financial_payload,
                    "stock_flow_movements": movements,
                },
            }
            token = register.prepare(event_id, operation)
            register.commit(event_id, token)

            wage_instrument_id = f"WAGE:{accrual.claim_id}"
            wage_terms = replace(
                instrument(wage_instrument_id, "WAGE"),
                effective_from_period=1,
            )
            terms = InstrumentTermsRegistry(
                "terms-wage-v1", (wage_terms,),
            )
            sectors = EffectiveDatedSectorRegistry(
                "sectors-wage-v1",
                frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"}),
                (
                    SectorMembership("worker-1", "H", 1, None),
                    SectorMembership("employer-1", "NFC", 1, None),
                ),
            )
            snapshots = build_opening_snapshots_from_register(
                register, principal_id="financial-root", periods=[1, 2],
                instrument_registry=terms, sector_registry=sectors,
            )
            self.assertEqual(len(snapshots[0].positions), 2)
            self.assertEqual(len(snapshots[1].positions), 2)
            opening_period_1 = {
                (row.identity.holder_entity_id, row.identity.issuer_entity_id): row.balance
                for row in snapshots[0].positions
            }
            opening_period_2 = {
                (row.identity.holder_entity_id, row.identity.issuer_entity_id): row.balance
                for row in snapshots[1].positions
            }
            self.assertEqual(
                opening_period_1[("worker-1", "employer-1")], "0",
            )
            self.assertEqual(
                opening_period_1[("employer-1", "worker-1")], "0",
            )
            self.assertEqual(
                Decimal(opening_period_2[("worker-1", "employer-1")]), accrual.amount,
            )
            self.assertEqual(
                Decimal(opening_period_2[("employer-1", "worker-1")]), accrual.amount,
            )
            self.assertTrue(all(
                row.source_ref.startswith(
                    f"financial:{register.register_instance_id}:financial-root@"
                )
                for row in snapshots[1].positions
            ))



if __name__ == "__main__":
    unittest.main()
