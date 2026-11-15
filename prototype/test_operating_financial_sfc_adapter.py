"""Adversarial tests for the native banking-to-SFC adapter."""
import json
import tempfile
import unittest
from pathlib import Path

from operating_financial_register import OperatingFinancialRegister
from sfc_projection_kernel import SFCIdentity

from operating_financial_register import bank_credit_stock_flow_movement_specs
from operating_financial_sfc_adapter import (
    OperatingFinancialSFCAdapter,
    OperatingFinancialSFCAdapterError,
)
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
            identities[:3], snapshot.positions[:3],
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
