import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from economic_stock_flow_reconciliation import (
    OpeningPosition, ClosingPosition, PositionIdentity,
    movements_from_event_groups, reconcile_periods,
)
from operating_financial_register import (
    OperatingFinancialRegister, OperatingFinancialRegisterError,
    bank_credit_stock_flow_movement_specs,
)

T = "2026-11-15T00:00:00Z"


class BankCreditLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "financial.sqlite3"
        self.register = OperatingFinancialRegister(
            self.path,
            sectors={"borrower": "H", "bank": "CBank"},
        )
        self.register.bootstrap_admin(
            principal_id="root", authority_ref="BOOTSTRAP", occurred_at=T,
        )
        self.register.open_deposit_account(
            event_id="OPEN-BORROWER", entity_id="borrower", bank_id="bank",
            currency="LCU", account_ref="BORROWER-ACCOUNT",
            opening_balance="10.00", evidence_ref="BANK-OPENING",
            actor_id="root", authority_ref="BANK-OPENING",
            effective_at=T, recorded_at=T, expected_revision=0,
            minor_unit="0.01",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, event_id, event_type, amount, period, expected_revision,
             causation_id=None):
        return self.register.commit_bank_credit(
            event_id=event_id, event_type=event_type, loan_id="LOAN-1",
            borrower_id="borrower", bank_id="bank", currency="LCU",
            amount=amount, period_index=period, evidence_ref=f"EVIDENCE:{event_id}",
            actor_id="root", authority_ref="BANK-CREDIT-POLICY",
            effective_at=T, recorded_at=T, expected_revision=expected_revision,
            minor_unit="0.01", causation_id=causation_id,
        )

    def test_full_repayment_closes_loan_and_replay_survives_restart(self):
        self.post("LOAN-ORIGINATE", "bank.loan_originated", "100.00", 2, 1)
        self.post("LOAN-REPAY-FULL", "bank.loan_principal_repaid", "100.00", 3, 2,
                  causation_id="LOAN-ORIGINATE")
        loan, revision = self.register.loan_state("LOAN-1", principal_id="root")
        self.assertEqual(revision, 3)
        self.assertEqual(loan["outstanding_principal"], "0.00")
        self.assertEqual(loan["status"], "REPAID")
        self.assertEqual(loan["event_ids"], ["LOAN-ORIGINATE", "LOAN-REPAY-FULL"])
        self.assertEqual(
            self.register.deposit_balance("borrower", "LCU", principal_id="root")[0],
            D("10.00"),
        )

        reopened = OperatingFinancialRegister(
            self.path, sectors={"borrower": "H", "bank": "CBank"},
        )
        replayed, replay_revision = reopened.loan_state("LOAN-1", principal_id="root")
        self.assertEqual(replay_revision, 3)
        self.assertEqual(replayed, loan)
        self.assertTrue(reopened.verify())

    def test_over_repayment_is_rejected_without_any_state_change(self):
        self.post("LOAN-ORIGINATE", "bank.loan_originated", "100.00", 2, 1)
        before_balance = self.register.deposit_balance(
            "borrower", "LCU", principal_id="root"
        )[0]
        before_loan, before_revision = self.register.loan_state(
            "LOAN-1", principal_id="root"
        )
        with self.assertRaisesRegex(
            OperatingFinancialRegisterError, "exceeds outstanding loan principal"
        ):
            self.post("LOAN-OVERPAY", "bank.loan_principal_repaid", "100.01", 3, 2,
                      causation_id="LOAN-ORIGINATE")
        self.assertIsNone(self.register.status("LOAN-OVERPAY"))
        self.assertEqual(
            self.register.deposit_balance("borrower", "LCU", principal_id="root")[0],
            before_balance,
        )
        after_loan, after_revision = self.register.loan_state(
            "LOAN-1", principal_id="root"
        )
        self.assertEqual(after_loan, before_loan)
        self.assertEqual(after_revision, before_revision)
        self.assertTrue(self.register.verify())

    def test_repayment_requires_immediate_causation_and_non_decreasing_period(self):
        self.post("LOAN-ORIGINATE", "bank.loan_originated", "100.00", 4, 1)
        with self.assertRaisesRegex(
            OperatingFinancialRegisterError, "immediately preceding loan event"
        ):
            self.post("LOAN-WRONG-CAUSE", "bank.loan_principal_repaid", "10.00", 5, 2,
                      causation_id="SOME-OTHER-EVENT")
        self.assertIsNone(self.register.status("LOAN-WRONG-CAUSE"))
        with self.assertRaisesRegex(
            OperatingFinancialRegisterError, "period cannot move backwards"
        ):
            self.post("LOAN-OLD-PERIOD", "bank.loan_principal_repaid", "10.00", 3, 2,
                      causation_id="LOAN-ORIGINATE")
        self.assertIsNone(self.register.status("LOAN-OLD-PERIOD"))
        self.assertEqual(
            self.register.deposit_balance("borrower", "LCU", principal_id="root")[0],
            D("110.00"),
        )


    def test_borrower_can_hold_deposits_at_two_banks_without_aliasing(self):
        self.register.sectors["bank-2"] = "CBank"
        self.register.open_deposit_account(
            event_id="OPEN-BORROWER-BANK-2", entity_id="borrower", bank_id="bank-2",
            currency="LCU", account_ref="BORROWER-ACCOUNT-BANK-2",
            opening_balance="20.00", evidence_ref="BANK-2-OPENING",
            actor_id="root", authority_ref="BANK-OPENING",
            effective_at=T, recorded_at=T, expected_revision=1,
            minor_unit="0.01",
        )
        self.register.commit_bank_credit(
            event_id="BANK-2-LOAN", event_type="bank.loan_originated",
            loan_id="LOAN-BANK-2", borrower_id="borrower", bank_id="bank-2",
            currency="LCU", amount="30.00", period_index=2,
            evidence_ref="BANK-2-LOAN-EVIDENCE", actor_id="root",
            authority_ref="BANK-CREDIT-POLICY", effective_at=T, recorded_at=T,
            expected_revision=2, minor_unit="0.01",
        )
        self.assertEqual(
            self.register.deposit_balance("borrower", "LCU", principal_id="root",
                                          bank_id="bank")[0],
            D("10.00"),
        )
        self.assertEqual(
            self.register.deposit_balance("borrower", "LCU", principal_id="root",
                                          bank_id="bank-2")[0],
            D("50.00"),
        )
        with self.assertRaisesRegex(
            OperatingFinancialRegisterError, "ambiguous across banks"
        ):
            self.register.deposit_balance("borrower", "LCU", principal_id="root")
        bank_1 = self.register.bank_principal_snapshot("bank", "LCU", principal_id="root")
        bank_2 = self.register.bank_principal_snapshot("bank-2", "LCU", principal_id="root")
        self.assertEqual(bank_1["deposit_liabilities"], D("10.00"))
        self.assertEqual(bank_1["loan_assets"], D("0"))
        self.assertEqual(bank_2["deposit_liabilities"], D("50.00"))
        self.assertEqual(bank_2["loan_assets"], D("30.00"))
        opening_positions = self.register.deposit_opening_positions(
            period_index=1, principal_id="root",
        )
        self.assertEqual(len(opening_positions), 4)
        self.assertEqual(
            len({position.identity.instrument_id for position in opening_positions}),
            2,
        )
        self.assertTrue(self.register.verify())

    def test_loan_origination_and_repayment_close_all_sfc_positions(self):
        origination = {
            "event_id": "LOAN-ORIGINATE", "event_type": "bank.loan_originated",
            "loan_id": "LOAN-1", "borrower_id": "borrower", "bank_id": "bank",
            "currency": "LCU", "amount": "100.00", "period_index": 2,
            "evidence_ref": "EVIDENCE:ORIGINATION",
        }
        repayment = {
            "event_id": "LOAN-REPAY", "event_type": "bank.loan_principal_repaid",
            "loan_id": "LOAN-1", "borrower_id": "borrower", "bank_id": "bank",
            "currency": "LCU", "amount": "40.00", "period_index": 3,
            "evidence_ref": "EVIDENCE:REPAYMENT",
        }
        participant_names = ("physical", "capital", "labour", "product",
                             "legal_rights", "financial")
        groups = []
        for event in (origination, repayment):
            specs = bank_credit_stock_flow_movement_specs(event)
            participants = []
            for name in participant_names:
                payload = ({"stock_flow_movements": specs} if name == "financial"
                           else {"no_stock_flow_effect": f"not implicated: {name}"})
                participants.append({
                    "register_id": name,
                    "common_event_id": event["event_id"],
                    "native_event_id": f'{event["event_id"]}:{name}',
                    "aggregate_version": 1,
                    "payload": payload,
                })
            groups.append({
                "schema_version": 1,
                "transaction_id": event["event_id"],
                "common_event_id": event["event_id"],
                "events": tuple(participants),
            })

        movements = movements_from_event_groups(tuple(groups))
        self.assertEqual(len(movements), 8)

        instrument = "DEPOSIT:borrower:bank:LCU"
        loan_instrument = "LOAN:LOAN-1"
        identities = (
            PositionIdentity("financial", f"{instrument}:ASSET", "monetary",
                             "LCU", "LCU", "NOMINAL", "borrower", "bank", instrument),
            PositionIdentity("financial", f"{instrument}:LIABILITY", "monetary",
                             "LCU", "LCU", "NOMINAL", "bank", "borrower", instrument),
            PositionIdentity("financial", f"{loan_instrument}:BANK-ASSET", "monetary",
                             "LCU", "LCU", "NOMINAL", "bank", "borrower", loan_instrument),
            PositionIdentity("financial", f"{loan_instrument}:BORROWER-LIABILITY", "monetary",
                             "LCU", "LCU", "NOMINAL", "borrower", "bank", loan_instrument),
        )
        initial = {identities[0]: D("10.00"), identities[1]: D("10.00"),
                   identities[2]: D("0"), identities[3]: D("0")}
        openings, closings = [], []
        for identity in identities:
            balance = initial[identity]
            for period in (1, 2, 3):
                openings.append(OpeningPosition(
                    identity, period, balance, f"OPEN:{identity.position_id}:{period}"
                ))
                balance += sum((
                    movement.amount for movement in movements
                    if movement.identity == identity and movement.period_index == period
                ), D("0"))
                closings.append(ClosingPosition(
                    identity, period, balance, f"CLOSE:{identity.position_id}:{period}"
                ))
        result = reconcile_periods(tuple(openings), movements, tuple(closings))
        self.assertEqual(result.event_count, 8)
        self.assertEqual(result.mirror_group_count, 4)
        closing = {row.identity.position_id: row.closing for row in result.periods
                   if row.period_index == 3}
        self.assertEqual(closing[f"{instrument}:ASSET"], D("70.00"))
        self.assertEqual(closing[f"{instrument}:LIABILITY"], D("70.00"))
        self.assertEqual(closing[f"{loan_instrument}:BANK-ASSET"], D("60.00"))
        self.assertEqual(closing[f"{loan_instrument}:BORROWER-LIABILITY"], D("60.00"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
