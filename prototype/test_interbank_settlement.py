import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from operating_financial_register import (
    OperatingFinancialRegister, OperatingFinancialRegisterError,
    interbank_payment_stock_flow_movement_specs,
)

T = "2026-11-15T00:00:00Z"


class InterbankSettlementTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "interbank.sqlite3"
        self.register = OperatingFinancialRegister(
            self.path,
            sectors={
                "payer": "H", "payee": "H",
                "bank-a": "CBank", "bank-b": "CBank", "central-bank": "CB",
            },
        )
        self.register.bootstrap_admin(
            principal_id="root", authority_ref="BOOTSTRAP", occurred_at=T,
        )
        self.register.open_deposit_account(
            event_id="OPEN-PAYER", entity_id="payer", bank_id="bank-a",
            currency="LCU", account_ref="PAYER-ACCOUNT", opening_balance="100.00",
            evidence_ref="OPEN-PAYER-EVIDENCE", actor_id="root",
            authority_ref="ACCOUNT-OPENING", effective_at=T, recorded_at=T,
            expected_revision=0,
        )
        self.register.open_deposit_account(
            event_id="OPEN-PAYEE", entity_id="payee", bank_id="bank-b",
            currency="LCU", account_ref="PAYEE-ACCOUNT", opening_balance="30.00",
            evidence_ref="OPEN-PAYEE-EVIDENCE", actor_id="root",
            authority_ref="ACCOUNT-OPENING", effective_at=T, recorded_at=T,
            expected_revision=1,
        )
        self.register.open_bank_reserve_account(
            event_id="OPEN-RESERVE-A", bank_id="bank-a", central_bank_id="central-bank",
            currency="LCU", account_ref="RESERVE-A", opening_balance="500.00",
            evidence_ref="RESERVE-A-OPENING", actor_id="root",
            authority_ref="CB-OPENING", effective_at=T, recorded_at=T,
            expected_revision=2,
        )
        self.register.open_bank_reserve_account(
            event_id="OPEN-RESERVE-B", bank_id="bank-b", central_bank_id="central-bank",
            currency="LCU", account_ref="RESERVE-B", opening_balance="100.00",
            evidence_ref="RESERVE-B-OPENING", actor_id="root",
            authority_ref="CB-OPENING", effective_at=T, recorded_at=T,
            expected_revision=3,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def settle(self, *, event_id="PAYMENT-EVENT-1", payment_id="PAYMENT-1",
               amount="70.00", expected_revision=4):
        return self.register.settle_interbank_payment(
            event_id=event_id, payment_id=payment_id,
            payer_id="payer", payee_id="payee",
            payer_bank_id="bank-a", payee_bank_id="bank-b",
            central_bank_id="central-bank", currency="LCU",
            amount=amount, period_index=2, evidence_ref=f"EVIDENCE:{payment_id}",
            actor_id="root", authority_ref="INTERBANK-SETTLEMENT",
            effective_at=T, recorded_at=T, expected_revision=expected_revision,
        )

    def test_interbank_payment_moves_deposits_and_reserves_atomically(self):
        self.settle()
        self.assertEqual(
            self.register.deposit_balance("payer", "LCU", bank_id="bank-a", principal_id="root")[0],
            D("30.00"),
        )
        self.assertEqual(
            self.register.deposit_balance("payee", "LCU", bank_id="bank-b", principal_id="root")[0],
            D("100.00"),
        )
        self.assertEqual(
            self.register.bank_reserve_snapshot("bank-a", "central-bank", "LCU", principal_id="root")["reserve_balance"],
            D("430.00"),
        )
        self.assertEqual(
            self.register.bank_reserve_snapshot("bank-b", "central-bank", "LCU", principal_id="root")["reserve_balance"],
            D("170.00"),
        )
        payment, revision = self.register.interbank_payment_state("PAYMENT-1", principal_id="root")
        self.assertEqual(payment["status"], "SETTLED")
        self.assertEqual(payment["amount"], "70.00")
        self.assertEqual(revision, 5)
        self.assertTrue(self.register.verify())

    def test_insufficient_reserves_reject_without_any_partial_posting(self):
        self.register.open_bank_reserve_account(
            event_id="OPEN-RESERVE-A-LOW", bank_id="bank-a", central_bank_id="central-bank",
            currency="USD", account_ref="RESERVE-A-USD", opening_balance="0.00",
            evidence_ref="RESERVE-A-USD-OPENING", actor_id="root",
            authority_ref="CB-OPENING", effective_at=T, recorded_at=T,
            expected_revision=4,
        )
        before_payer = self.register.deposit_balance(
            "payer", "LCU", bank_id="bank-a", principal_id="root"
        )[0]
        before_payee = self.register.deposit_balance(
            "payee", "LCU", bank_id="bank-b", principal_id="root"
        )[0]
        with self.assertRaisesRegex(
            OperatingFinancialRegisterError, "insufficient payer bank reserves"
        ):
            self.settle(event_id="PAYMENT-LOW-RESERVES", payment_id="PAYMENT-LOW",
                        amount="70.00", expected_revision=5)
        self.assertIsNone(self.register.status("PAYMENT-LOW-RESERVES"))
        self.assertEqual(self.register.deposit_balance(
            "payer", "LCU", bank_id="bank-a", principal_id="root"
        )[0], before_payer)
        self.assertEqual(self.register.deposit_balance(
            "payee", "LCU", bank_id="bank-b", principal_id="root"
        )[0], before_payee)
        self.assertEqual(self.register.bank_reserve_snapshot(
            "bank-a", "central-bank", "LCU", principal_id="root"
        )["reserve_balance"], D("500.00"))

    def test_duplicate_payment_id_is_rejected_without_commit(self):
        self.settle()
        with self.assertRaisesRegex(
            OperatingFinancialRegisterError, "payment ID already exists"
        ):
            self.settle(event_id="PAYMENT-EVENT-2", payment_id="PAYMENT-1",
                        amount="1.00", expected_revision=5)
        self.assertIsNone(self.register.status("PAYMENT-EVENT-2"))
        self.assertEqual(self.register.deposit_balance(
            "payer", "LCU", bank_id="bank-a", principal_id="root"
        )[0], D("30.00"))

    def test_interbank_mapper_has_eight_balanced_mirror_movements(self):
        event = {
            "event_id": "PAYMENT-EVENT", "event_type": "bank.interbank_payment_settled",
            "payment_id": "PAYMENT", "payer_id": "payer", "payee_id": "payee",
            "payer_bank_id": "bank-a", "payee_bank_id": "bank-b",
            "central_bank_id": "central-bank", "currency": "LCU",
            "amount": "70.00", "period_index": 2, "evidence_ref": "PAYMENT-EVIDENCE",
        }
        movements = interbank_payment_stock_flow_movement_specs(event)
        self.assertEqual(len(movements), 8)
        self.assertEqual(
            {item["mirror_group_id"] for item in movements},
            {"PAYMENT-EVENT:PAYER-DEPOSIT", "PAYMENT-EVENT:PAYEE-DEPOSIT",
             "PAYMENT-EVENT:PAYER-RESERVE", "PAYMENT-EVENT:PAYEE-RESERVE"},
        )
        for group in {item["mirror_group_id"] for item in movements}:
            pair = [item for item in movements if item["mirror_group_id"] == group]
            self.assertEqual(len(pair), 2)
            self.assertEqual(pair[0]["amount"], pair[1]["amount"])
            self.assertEqual({item["mirror_side"] for item in pair},
                             {"asset_holder", "liability_issuer"})

    def test_reserve_opening_positions_are_mirrored_and_replayable(self):
        positions = self.register.reserve_opening_positions(
            period_index=1, principal_id="root",
        )
        self.assertEqual(len(positions), 4)
        self.assertEqual(
            {position.identity.instrument_id for position in positions},
            {"RESERVE:bank-a:central-bank:LCU", "RESERVE:bank-b:central-bank:LCU"},
        )
        reopened = OperatingFinancialRegister(
            self.path,
            sectors={
                "payer": "H", "payee": "H",
                "bank-a": "CBank", "bank-b": "CBank", "central-bank": "CB",
            },
        )
        self.assertEqual(
            reopened.bank_reserve_snapshot("bank-a", "central-bank", "LCU",
                                            principal_id="root")["reserve_balance"],
            D("500.00"),
        )
        self.assertTrue(reopened.verify())


if __name__ == "__main__":
    unittest.main(verbosity=2)
