"""Adversarial tests for the native banking-to-SFC adapter."""
import json
from decimal import Decimal
import tempfile
import unittest
from pathlib import Path

from operating_financial_register import OperatingFinancialRegister
from sfc_projection_kernel import SFCIdentity

from operating_financial_register import (
    bank_credit_stock_flow_movement_specs,
    interbank_payment_stock_flow_movement_specs,
    central_bank_refinancing_movement_specs,
)
from operating_financial_sfc_adapter import (
    OperatingFinancialSFCAdapter,
    OperatingFinancialSFCAdapterError,
)
from banking_sfc_projection_pipeline import project_and_persist, rebuild_and_verify
from banking_sfc_projection_store import BankingSFCProjectionStore
from sfc_source_contracts import (
    EffectiveDatedSectorRegistry,
    InstrumentTerms,
    InstrumentTermsRegistry,
    OpeningPosition,
    OpeningStockSnapshot,
    SectorMembership,
)


def instrument(instrument_id, instrument_class):
    return InstrumentTerms(
        instrument_id=instrument_id,
        instrument_class=instrument_class,
        denomination="LCU:0.01",
        currency="LCU",
        valuation_basis="NOMINAL",
        maturity="2028-12-31" if instrument_class == "LOAN" else "ON_DEMAND",
        rate_type="FIXED" if instrument_class == "LOAN" else "NONE",
        rate_reference="NONE",
        rate_spread="0",
        reset_frequency="NONE",
        day_count_convention="ACT/365F" if instrument_class == "LOAN" else "NONE",
        payment_frequency="MONTHLY" if instrument_class == "LOAN" else "ON_DEMAND",
        principal_repayment="AMORTIZING" if instrument_class == "LOAN" else "ON_DEMAND",
        effective_from_period=3,
        effective_to_period=None,
        nonnegative_gross_position=True,
    )


def fixture(period=3, balances=None):
    loan_id = "LOAN:LOAN-1"
    deposit_id = "DEPOSIT:household-1:bank-1:LCU"
    terms = InstrumentTermsRegistry("terms-v1", (
        instrument(loan_id, "LOAN"),
        instrument(deposit_id, "DEPOSIT"),
    ))
    sectors = EffectiveDatedSectorRegistry(
        "sectors-v1",
        frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"}),
        (
            SectorMembership("household-1", "H", 1, None),
            SectorMembership("bank-1", "CB", 1, None),
        ),
    )
    identities = (
        # Bank's loan asset and borrower's matching loan liability.
        __import__("sfc_projection_kernel").SFCIdentity(
            loan_id, "LOAN", "bank-1", "CB", "household-1", "H",
            "LCU", "2028-12-31", "LCU:0.01", "NOMINAL",
        ),
        __import__("sfc_projection_kernel").SFCIdentity(
            loan_id, "LOAN", "household-1", "H", "bank-1", "CB",
            "LCU", "2028-12-31", "LCU:0.01", "NOMINAL",
        ),
        # Borrower's deposit asset and bank's matching deposit liability.
        __import__("sfc_projection_kernel").SFCIdentity(
            deposit_id, "DEPOSIT", "household-1", "H", "bank-1", "CB",
            "LCU", "ON_DEMAND", "LCU:0.01", "NOMINAL",
        ),
        __import__("sfc_projection_kernel").SFCIdentity(
            deposit_id, "DEPOSIT", "bank-1", "CB", "household-1", "H",
            "LCU", "ON_DEMAND", "LCU:0.01", "NOMINAL",
        ),
    )
    if balances is None:
        balances = ["0", "0", "0", "0"]
    snapshot = OpeningStockSnapshot(
        version=f"opening-v{period}",
        period_index=period,
        instrument_registry_version=terms.version,
        instrument_registry_digest=terms.digest,
        sector_registry_version=sectors.version,
        sector_registry_digest=sectors.digest,
        expected_identities=identities,
        positions=tuple(
            OpeningPosition(identity, balance, f"CERT-{period}-{i}", f"SOURCE-{period}-{i}")
            for i, (identity, balance) in enumerate(zip(identities, balances))
        ),
    )
    return terms, sectors, identities, snapshot


def history_row(event_id, event_type, payload, sequence=1):
    envelope = {
        "event_type": event_type,
        "effective_at": "2026-11-15T00:00:00Z",
        "recorded_at": "2026-11-15T00:00:01Z",
        "actor_id": "bank-operator",
        "authority_ref": "CREDIT-POLICY-1",
        "idempotency_key": event_id,
        "payload": payload,
        "stock_flow_movements": bank_credit_stock_flow_movement_specs({
            "event_id": event_id,
            "event_type": event_type,
            **payload,
        }),
    }
    return {
        "event_id": event_id,
        "event_type": event_type,
        "commit_sequence": sequence,
        "payload_json": json.dumps(envelope),
        "payload_sha256": f"sha-{event_id}",
    }


class OperatingFinancialSFCAdapterTests(unittest.TestCase):
    def loan_event(self, event_id, event_type, amount, period, sequence=1):
        return history_row(
            event_id,
            event_type,
            {
                "loan_id": "LOAN-1",
                "borrower_id": "household-1",
                "bank_id": "bank-1",
                "currency": "LCU",
                "amount": str(amount),
                "period_index": period,
                "evidence_ref": f"EVIDENCE-{event_id}",
            },
            sequence,
        )

    def test_malformed_history_rows_fail_closed_before_sorting(self):
        terms, sectors, identities, snapshot = fixture()
        valid = self.loan_event("LOAN-ORIG-1", "bank.loan_originated", "100", 3)
        cases = (
            ([None], "history row must be a mapping"),
            ([{**valid, "commit_sequence": True}], "commit_sequence must be a positive integer"),
            ([{**valid, "commit_sequence": 0}], "commit_sequence must be a positive integer"),
            ([{**valid, "commit_sequence": "1"}], "commit_sequence must be a positive integer"),
            ([{**valid, "commit_sequence": None}], "commit_sequence must be a positive integer"),
            ([valid, {**valid, "event_id": "LOAN-ORIG-2"}], "duplicate financial history commit_sequence"),
        )
        for rows, message in cases:
            with self.subTest(message=message):
                with self.assertRaisesRegex(OperatingFinancialSFCAdapterError, message):
                    OperatingFinancialSFCAdapter.build(
                        rows, instrument_registry=terms,
                        sector_registry=sectors, opening_snapshots=[snapshot],
                    )

    def test_history_rows_are_sorted_by_unique_durable_commit_sequence(self):
        terms, sectors, identities, snapshot = fixture(3)
        first = self.loan_event("LOAN-ORIG-1", "bank.loan_originated", "100", 3, 10)
        second = self.loan_event("LOAN-REPAY-1", "bank.loan_principal_repaid", "35", 3, 20)
        result = OperatingFinancialSFCAdapter.build(
            [second, first], instrument_registry=terms,
            sector_registry=sectors, opening_snapshots=[snapshot],
        )
        self.assertEqual([item["event_id"] for item in result.events],
                         ["LOAN-ORIG-1::LOAN-ORIG-1", "LOAN-REPAY-1::LOAN-REPAY-1"])
        self.assertEqual(result.roll_forward[(identities[0], 3)].closing, 65)
    def test_loan_creation_maps_four_mirrored_positions_and_no_net_financial_wealth(self):
        terms, sectors, identities, snapshot = fixture()
        row = self.loan_event("LOAN-ORIG-1", "bank.loan_originated", "100", 3)
        result = OperatingFinancialSFCAdapter.build(
            [row],
            instrument_registry=terms,
            sector_registry=sectors,
            opening_snapshots=[snapshot],
        )
        self.assertEqual(result.mapped_source_event_count, 1)
        self.assertEqual(len(result.events[0]["deltas"]), 4)
        self.assertEqual(result.roll_forward[(identities[0], 3)].closing, 100)
        self.assertEqual(result.roll_forward[(identities[1], 3)].closing, 100)
        self.assertEqual(result.roll_forward[(identities[2], 3)].closing, 100)
        self.assertEqual(result.roll_forward[(identities[3], 3)].closing, 100)
        self.assertEqual(result.sector_financial_net_lending[(3, "H", "LCU")], 0)
        self.assertEqual(result.sector_financial_net_lending[(3, "CB", "LCU")], 0)

    def test_opening_events_are_excluded_from_transactions(self):
        terms, sectors, identities, snapshot = fixture()
        row = self.loan_event("LOAN-ORIG-1", "bank.loan_originated", "100", 3)
        opening = {
            "event_id": "DEPOSIT-OPEN-1",
            "event_type": "deposit.account_opened",
            "commit_sequence": 1,
            "payload_json": json.dumps({
                "event_type": "deposit.account_opened",
                "idempotency_key": "DEPOSIT-OPEN-1",
                "payload": {"opening_balance": "100"},
                "no_stock_flow_effect": "account opening establishes an opening stock",
                "stock_flow_movements": None,
            }),
            "payload_sha256": "sha-opening",
        }
        row["commit_sequence"] = 2
        result = OperatingFinancialSFCAdapter.build(
            [opening, row],
            instrument_registry=terms,
            sector_registry=sectors,
            opening_snapshots=[snapshot],
        )
        self.assertEqual(result.excluded_opening_event_count, 1)
        self.assertEqual(result.mapped_source_event_count, 1)

    def test_missing_opening_position_fails_closed(self):
        terms, sectors, identities, snapshot = fixture()
        incomplete = OpeningStockSnapshot(
            snapshot.version, snapshot.period_index,
            snapshot.instrument_registry_version, snapshot.instrument_registry_digest,
            snapshot.sector_registry_version, snapshot.sector_registry_digest,
            identities[:2], snapshot.positions[:2],
        )
        row = self.loan_event("LOAN-ORIG-1", "bank.loan_originated", "100", 3)
        with self.assertRaises(OperatingFinancialSFCAdapterError):
            OperatingFinancialSFCAdapter.build(
                [row],
                instrument_registry=terms,
                sector_registry=sectors,
                opening_snapshots=[incomplete],
            )

    def test_mirror_amount_tampering_is_rejected(self):
        terms, sectors, identities, snapshot = fixture()
        row = self.loan_event("LOAN-ORIG-1", "bank.loan_originated", "100", 3)
        envelope = json.loads(row["payload_json"])
        envelope["stock_flow_movements"][1]["amount"] = "99"
        row["payload_json"] = json.dumps(envelope)
        with self.assertRaises(OperatingFinancialSFCAdapterError):
            OperatingFinancialSFCAdapter.build(
                [row],
                instrument_registry=terms,
                sector_registry=sectors,
                opening_snapshots=[snapshot],
            )

    def test_multiperiod_repayment_rolls_forward_exactly(self):
        terms, sectors, identities, first = fixture(3)
        _, _, _, second = fixture(4, ["100", "100", "100", "100"])
        origination = self.loan_event("LOAN-ORIG-1", "bank.loan_originated", "100", 3, 1)
        repayment = self.loan_event("LOAN-REPAY-1", "bank.loan_principal_repaid", "35", 4, 2)
        result = OperatingFinancialSFCAdapter.build(
            [origination, repayment],
            instrument_registry=terms,
            sector_registry=sectors,
            opening_snapshots=[first, second],
        )
        self.assertEqual(result.roll_forward[(identities[0], 3)].closing, 100)
        self.assertEqual(result.roll_forward[(identities[0], 4)].opening, 100)
        self.assertEqual(result.roll_forward[(identities[0], 4)].transactions, -35)
        self.assertEqual(result.roll_forward[(identities[0], 4)].closing, 65)

    def test_from_register_replays_real_durable_financial_history(self):
        with tempfile.TemporaryDirectory() as directory:
            register = OperatingFinancialRegister(
                Path(directory) / "financial.sqlite3",
                sectors={"household-1": "H", "bank-1": "CB"},
            )
            register.bootstrap_admin(
                principal_id="financial-root",
                authority_ref="BOOTSTRAP",
                occurred_at="2026-11-15T00:00:00Z",
            )
            register.open_deposit_account(
                event_id="DEPOSIT-OPEN-1",
                entity_id="household-1",
                bank_id="bank-1",
                currency="LCU",
                account_ref="ACCOUNT-1",
                opening_balance="0",
                evidence_ref="DEPOSIT-OPEN-EVIDENCE",
                actor_id="financial-root",
                authority_ref="ACCOUNT-OPENING",
                effective_at="2026-11-15T00:00:01Z",
                recorded_at="2026-11-15T00:00:01Z",
                expected_revision=0,
            )
            register.commit_bank_credit(
                event_id="LOAN-ORIG-1",
                event_type="bank.loan_originated",
                loan_id="LOAN-1",
                borrower_id="household-1",
                bank_id="bank-1",
                currency="LCU",
                amount="100",
                period_index=3,
                evidence_ref="SIGNED-LOAN-1",
                actor_id="financial-root",
                authority_ref="CREDIT-POLICY",
                effective_at="2026-11-15T00:00:02Z",
                recorded_at="2026-11-15T00:00:02Z",
                expected_revision=1,
            )
            loan_id = "LOAN:LOAN-1"
            deposit_id = "DEPOSIT:household-1:bank-1:LCU"
            terms = InstrumentTermsRegistry("terms-v1", (
                instrument(loan_id, "LOAN"),
                instrument(deposit_id, "DEPOSIT"),
            ))
            sectors = EffectiveDatedSectorRegistry(
                "sectors-v1",
                frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"}),
                (
                    SectorMembership("household-1", "H", 1, None),
                    SectorMembership("bank-1", "CB", 1, None),
                ),
            )
            identities = (
                SFCIdentity(loan_id, "LOAN", "bank-1", "CB", "household-1", "H",
                            "LCU", "2028-12-31", "LCU:0.01", "NOMINAL"),
                SFCIdentity(loan_id, "LOAN", "household-1", "H", "bank-1", "CB",
                            "LCU", "2028-12-31", "LCU:0.01", "NOMINAL"),
                SFCIdentity(deposit_id, "DEPOSIT", "household-1", "H", "bank-1", "CB",
                            "LCU", "ON_DEMAND", "LCU:0.01", "NOMINAL"),
                SFCIdentity(deposit_id, "DEPOSIT", "bank-1", "CB", "household-1", "H",
                            "LCU", "ON_DEMAND", "LCU:0.01", "NOMINAL"),
            )
            snapshot = OpeningStockSnapshot(
                "opening-v3", 3,
                terms.version, terms.digest,
                sectors.version, sectors.digest,
                identities,
                tuple(
                    OpeningPosition(identity, "0", f"CERT-{i}", f"SOURCE-{i}")
                    for i, identity in enumerate(identities)
                ),
            )
            result = OperatingFinancialSFCAdapter.from_register(
                register,
                principal_id="financial-root",
                instrument_registry=terms,
                sector_registry=sectors,
                opening_snapshots=[snapshot],
            )
            self.assertEqual(result.source_event_count, 2)
            self.assertEqual(result.excluded_opening_event_count, 1)
            self.assertEqual(result.mapped_source_event_count, 1)
            self.assertEqual(result.roll_forward[(identities[0], 3)].closing, 100)
            self.assertEqual(result.roll_forward[(identities[1], 3)].closing, 100)

            store = BankingSFCProjectionStore(
                Path(directory) / "banking-sfc-projection.sqlite3"
            )
            persisted_projection, receipt = project_and_persist(
                register,
                principal_id="financial-root",
                instrument_registry=terms,
                sector_registry=sectors,
                opening_snapshots=[snapshot],
                store=store,
                source_register_id=f"financial:{register.register_instance_id}:financial-root",
            )
            rebuilt_projection, checkpoint = rebuild_and_verify(
                register,
                principal_id="financial-root",
                instrument_registry=terms,
                sector_registry=sectors,
                opening_snapshots=[snapshot],
                store=store,
                source_register_id="financial-register:integration-test",
            )
            self.assertEqual(persisted_projection.source_digest, rebuilt_projection.source_digest)
            self.assertEqual(receipt["projection_digest"], checkpoint["projection_digest"])
            self.assertEqual(
                checkpoint["applied_through_sequence"],
                max(row["commit_sequence"] for row in register.history(
                    "operating-financial", principal_id="financial-root"
                )),
            )

    def test_next_period_opening_must_equal_prior_period_closing(self):
        terms, sectors, identities, first = fixture(3)
        inconsistent = fixture(4, ["99", "99", "99", "99"])[3]
        origination = self.loan_event(
            "LOAN-ORIG-1", "bank.loan_originated", "100", 3, 1
        )
        with self.assertRaisesRegex(
            OperatingFinancialSFCAdapterError,
            "next-period opening differs from prior closing",
        ):
            OperatingFinancialSFCAdapter.build(
                [origination],
                instrument_registry=terms,
                sector_registry=sectors,
                opening_snapshots=[first, inconsistent],
            )

    def test_nonzero_position_cannot_disappear_from_next_period_snapshot(self):
        terms, sectors, identities, first = fixture(3)
        deposit_only = OpeningStockSnapshot(
            "opening-v4", 4,
            terms.version, terms.digest,
            sectors.version, sectors.digest,
            identities[2:],
            (
                OpeningPosition(identities[2], "100", "CERT-4-A", "SOURCE-4-A"),
                OpeningPosition(identities[3], "100", "CERT-4-B", "SOURCE-4-B"),
            ),
        )
        row = self.loan_event("LOAN-ORIG-1", "bank.loan_originated", "100", 3)
        with self.assertRaisesRegex(OperatingFinancialSFCAdapterError, "disappears"):
            OperatingFinancialSFCAdapter.build(
                [row],
                instrument_registry=terms,
                sector_registry=sectors,
                opening_snapshots=[first, deposit_only],
            )

    def test_six_sector_interbank_reserves_and_refinancing_close_without_plugs(self):
        terms = InstrumentTermsRegistry("six-sector-terms-v1", (
            instrument("DEPOSIT:row-entity:bank-1:LCU", "DEPOSIT"),
            instrument("DEPOSIT:household-1:bank-1:LCU", "DEPOSIT"),
            instrument("DEPOSIT:firm-1:bank-2:LCU", "DEPOSIT"),
            instrument("DEPOSIT:government-1:bank-2:LCU", "DEPOSIT"),
            instrument("LOAN:LOAN-GOV", "LOAN"),
            instrument("LOAN:LOAN-ROW", "LOAN"),
            instrument("LOAN:LOAN-HH", "LOAN"),
            instrument("RESERVE:bank-1:central-bank:LCU", "RESERVE"),
            instrument("RESERVE:bank-2:central-bank:LCU", "RESERVE"),
            instrument("CBREFI:FACILITY-1", "LOAN"),
        ))
        sectors = EffectiveDatedSectorRegistry(
            "six-sector-membership-v1",
            frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"}),
            (
                SectorMembership("row-entity", "ROW", 1, None),
                SectorMembership("firm-1", "NFC", 1, None),
                SectorMembership("government-1", "GOV", 1, None),
                SectorMembership("bank-1", "CB", 1, None),
                SectorMembership("bank-2", "CB", 1, None),
                SectorMembership("central-bank", "CBank", 1, None),
                SectorMembership("household-1", "H", 1, None),
            ),
        )

        interbank_payload = {
            "payment_id": "PAYMENT-ROW-FIRM",
            "payer_id": "row-entity", "payee_id": "firm-1",
            "payer_bank_id": "bank-1", "payee_bank_id": "bank-2",
            "central_bank_id": "central-bank", "currency": "LCU",
            "amount": "20", "period_index": 3, "evidence_ref": "SETTLEMENT-EVIDENCE",
        }
        interbank_event = {
            "event_id": "INTERBANK-1", "event_type": "bank.interbank_payment_settled",
            **interbank_payload,
        }
        refinancing_payload = {
            "facility_id": "FACILITY-1", "bank_id": "bank-1",
            "central_bank_id": "central-bank", "currency": "LCU",
            "amount": "50", "period_index": 3, "evidence_ref": "REFINANCING-EVIDENCE",
        }
        refinancing_event = {
            "event_id": "REFINANCING-1",
            "event_type": "central_bank.refinancing_advanced",
            **refinancing_payload,
        }
        refinancing_repayment_payload = {
            "facility_id": "FACILITY-1", "bank_id": "bank-1",
            "central_bank_id": "central-bank", "currency": "LCU",
            "amount": "20", "period_index": 4, "evidence_ref": "REFINANCING-REPAYMENT-EVIDENCE",
        }
        refinancing_repayment_event = {
            "event_id": "REFINANCING-REPAY-1",
            "event_type": "central_bank.refinancing_principal_repaid",
            **refinancing_repayment_payload,
        }
        government_loan = self.loan_event(
            "GOV-LOAN-1", "bank.loan_originated", "30", 3, 1
        )
        gov_payload = json.loads(government_loan["payload_json"])
        gov_payload["payload"]["loan_id"] = "LOAN-GOV"
        gov_payload["payload"]["borrower_id"] = "government-1"
        gov_payload["payload"]["bank_id"] = "bank-2"
        gov_payload["stock_flow_movements"] = bank_credit_stock_flow_movement_specs({
            "event_id": "GOV-LOAN-1", "event_type": "bank.loan_originated",
            **gov_payload["payload"],
        })
        government_loan["payload_json"] = json.dumps(gov_payload)

        row_loan = self.loan_event(
            "ROW-LOAN-1", "bank.loan_originated", "10", 3, 2
        )
        row_payload = json.loads(row_loan["payload_json"])
        row_payload["payload"]["loan_id"] = "LOAN-ROW"
        row_payload["payload"]["borrower_id"] = "row-entity"
        row_payload["stock_flow_movements"] = bank_credit_stock_flow_movement_specs({
            "event_id": "ROW-LOAN-1", "event_type": "bank.loan_originated",
            **row_payload["payload"],
        })
        row_loan["payload_json"] = json.dumps(row_payload)

        def native_row(event_id, event_type, payload, movements, sequence):
            envelope = {
                "event_type": event_type, "effective_at": "2026-11-15T00:00:00Z",
                "recorded_at": "2026-11-15T00:00:01Z", "actor_id": "sfc-auditor",
                "authority_ref": "SFC-SIX-SECTOR-TEST",
                "idempotency_key": event_id, "payload": payload,
                "stock_flow_movements": movements,
            }
            return {
                "event_id": event_id, "event_type": event_type,
                "commit_sequence": sequence, "payload_json": json.dumps(envelope),
                "payload_sha256": f"sha-{event_id}",
            }

        household_loan = self.loan_event(
            "HOUSEHOLD-LOAN-1", "bank.loan_originated", "15", 3, 3
        )
        household_payload = json.loads(household_loan["payload_json"])
        household_payload["payload"]["loan_id"] = "LOAN-HH"
        household_payload["stock_flow_movements"] = bank_credit_stock_flow_movement_specs({
            "event_id": "HOUSEHOLD-LOAN-1", "event_type": "bank.loan_originated",
            **household_payload["payload"],
        })
        household_loan["payload_json"] = json.dumps(household_payload)
        rows = [
            government_loan,
            row_loan,
            household_loan,
            native_row("INTERBANK-1", "bank.interbank_payment_settled",
                       interbank_payload,
                       interbank_payment_stock_flow_movement_specs(interbank_event), 4),
            native_row("REFINANCING-1", "central_bank.refinancing_advanced",
                       refinancing_payload,
                       central_bank_refinancing_movement_specs(refinancing_event), 5),
            native_row("REFINANCING-REPAY-1", "central_bank.refinancing_principal_repaid",
                       refinancing_repayment_payload,
                       central_bank_refinancing_movement_specs(refinancing_repayment_event), 6),
        ]

        from operating_financial_sfc_adapter import _resolve_identity
        identities = {}
        for row in rows:
            envelope = json.loads(row["payload_json"])
            for movement in envelope["stock_flow_movements"]:
                identity = _resolve_identity(
                    movement["identity"], 3, terms, sectors
                )
                identities[identity] = identity
        initial_balances = {identity: "0" for identity in identities}
        for identity in identities:
            if identity.instrument_id == "DEPOSIT:row-entity:bank-1:LCU":
                initial_balances[identity] = "20"
            if identity.instrument_id == "RESERVE:bank-1:central-bank:LCU":
                initial_balances[identity] = "100"
        snapshots = []
        for identity in list(identities):
            mirror = SFCIdentity(
                identity.instrument_id, identity.instrument_class,
                identity.issuer_entity_id, identity.issuer_sector,
                identity.holder_entity_id, identity.holder_sector,
                identity.currency, identity.maturity, identity.denomination,
                identity.valuation_basis,
            )
            if mirror not in identities:
                raise AssertionError(f"test fixture missing mirror for {identity.instrument_id}")
            initial_balances[mirror] = initial_balances[identity]
        snapshot3 = OpeningStockSnapshot(
            "six-sector-opening-v3", 3, terms.version, terms.digest,
            sectors.version, sectors.digest, tuple(identities),
            tuple(OpeningPosition(identity, initial_balances[identity],
                                  f"OPEN-EVIDENCE-3-{i}", f"OPEN-SOURCE-3-{i}")
                  for i, identity in enumerate(identities)),
        )
        period3_closing = dict(initial_balances)
        for row in rows[:-1]:
            envelope = json.loads(row["payload_json"])
            for movement in envelope["stock_flow_movements"]:
                identity = _resolve_identity(movement["identity"], 3, terms, sectors)
                period3_closing[identity] = (
                    Decimal(period3_closing[identity])
                    + Decimal(movement["amount"])
                )
        snapshot4 = OpeningStockSnapshot(
            "six-sector-opening-v4", 4, terms.version, terms.digest,
            sectors.version, sectors.digest, tuple(identities),
            tuple(OpeningPosition(identity, str(period3_closing[identity]),
                                  f"OPEN-EVIDENCE-4-{i}", f"OPEN-SOURCE-4-{i}")
                  for i, identity in enumerate(identities)),
        )
        result = OperatingFinancialSFCAdapter.build(
            rows, instrument_registry=terms, sector_registry=sectors,
            opening_snapshots=[snapshot3, snapshot4],
        )
        active_sectors = {key[1] for key in result.sector_financial_net_lending}
        self.assertEqual(active_sectors, {"H", "NFC", "CB", "CBank", "GOV", "ROW"})
        self.assertEqual(
            sum(result.sector_financial_net_lending.values(), 0), 0
        )
        # Check conservation independently by period and currency; summing
        # all periods together could conceal offsetting accounting defects.
        period_currency_totals = {}
        for (period, sector, currency), amount in result.sector_financial_net_lending.items():
            key = (period, currency)
            period_currency_totals[key] = period_currency_totals.get(key, 0) + amount
        self.assertTrue(period_currency_totals)
        self.assertTrue(all(total == 0 for total in period_currency_totals.values()))
        reserve_1 = next(
            identity for identity in identities
            if identity.instrument_id == "RESERVE:bank-1:central-bank:LCU"
            and identity.holder_entity_id == "bank-1"
        )
        reserve_2 = next(
            identity for identity in identities
            if identity.instrument_id == "RESERVE:bank-2:central-bank:LCU"
            and identity.holder_entity_id == "bank-2"
        )
        self.assertEqual(result.roll_forward[(reserve_1, 3)].closing, 130)
        self.assertEqual(result.roll_forward[(reserve_2, 3)].closing, 20)
        self.assertEqual(result.mapped_source_event_count, 6)
        reserve_1_period4 = result.roll_forward[(reserve_1, 4)]
        reserve_2_period4 = result.roll_forward[(reserve_2, 4)]
        self.assertEqual(reserve_1_period4.opening, 130)
        self.assertEqual(reserve_1_period4.transactions, -20)
        self.assertEqual(reserve_1_period4.closing, 110)
        self.assertEqual(reserve_2_period4.closing, 20)
        self.assertEqual(reserve_1_period4.closing + reserve_2_period4.closing, 130)
        refi_claim = next(identity for identity in identities
                          if identity.instrument_id == "CBREFI:FACILITY-1"
                          and identity.holder_entity_id == "central-bank")
        self.assertEqual(result.roll_forward[(refi_claim, 4)].closing, 30)

    def test_snapshot_period_gap_is_rejected(self):
        terms, sectors, _, first = fixture(3)
        _, _, _, third = fixture(5, ["100", "100", "100", "100"])
        row = self.loan_event("LOAN-REPAY-1", "bank.loan_principal_repaid", "35", 5)
        with self.assertRaises(OperatingFinancialSFCAdapterError):
            OperatingFinancialSFCAdapter.build(
                [row],
                instrument_registry=terms,
                sector_registry=sectors,
                opening_snapshots=[first, third],
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
