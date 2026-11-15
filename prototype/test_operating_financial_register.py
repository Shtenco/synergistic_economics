import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from labour_register import LabourRegister
from operating_wage_journal import (
    OperatingWageJournal, WageContract, verified_delivery_from_register,
    native_financial_operation,
)
from operating_financial_register import (
    OperatingFinancialRegister, OperatingFinancialRegisterError,
)


T = "2026-11-15T00:00:00Z"


def append_labour(register, event_id, event_type, payload, version):
    return register.append_event(
        event_id=event_id, idempotency_key=event_id, aggregate_id="ENG-1",
        event_type=event_type, effective_at=T, recorded_at=T,
        actor_id="coordinator", authority_ref="AUTH:LABOUR",
        payload=payload, expected_version=version,
    )


class OperatingFinancialRegisterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.labour = LabourRegister(root / "labour.sqlite3")
        self.labour.bootstrap_admin(principal_id="labour-root", authority_ref="BOOTSTRAP", occurred_at=T)
        self.labour.grant_access(
            event_id="LABOUR-ACL", idempotency_key="LABOUR-ACL", principal_id="coordinator",
            permissions=["labour:read", "labour:write"], actor_id="labour-root",
            authority_ref="POLICY", occurred_at=T,
        )
        append_labour(self.labour, "L1", "engagement.offered", {
            "person_ref":"worker-1", "activity_id":"employer-1", "period":"P1",
            "classification":"paid", "consent_basis":"CONTRACT-1", "planned_hours":"2",
        }, 0)
        append_labour(self.labour, "L2", "engagement.accepted", {
            "consent_ref":"CONSENT-1", "accepted_hours":"2",
        }, 1)
        append_labour(self.labour, "L3", "engagement.scheduled", {"scheduled_hours":"2"}, 2)
        append_labour(self.labour, "L4", "engagement.started", {}, 3)
        append_labour(self.labour, "L5", "engagement.delivered", {
            "delivered_hours":"2", "evidence_ref":"TIMESHEET-1",
        }, 4)
        append_labour(self.labour, "L6", "engagement.verified", {
            "verification_ref":"VERIFY-1",
        }, 5)
        self.delivery = verified_delivery_from_register(
            self.labour, "ENG-1", "coordinator", verification_ref="VERIFY-1",
        )
        self.contract = WageContract(
            worker_id="worker-1", employer_id="employer-1", period_label="P1",
            period_index=1, currency="LCU", hourly_rate=D("20"),
            contract_ref="SIGNED-CONTRACT-1", evidence_ref="PAYROLL-RULE-1",
        )
        self.journal = OperatingWageJournal(
            bank_id="bank-1",
            sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CBank"},
            opening_deposits={("employer-1","LCU"):D("1000"), ("worker-1","LCU"):D("10")},
        )
        self.accrual = self.journal.accrue_verified_wage(
            event_id="WAGE-ACCRUAL-1", delivery=self.delivery, contract=self.contract,
            causation_id="L5", labour_register=self.labour, principal_id="coordinator",
        )
        self.payment = self.journal.pay_wage(
            event_id="WAGE-PAYMENT-1", claim_id=self.accrual.claim_id, amount="40",
            causation_id=self.accrual.event_id, evidence_ref="BANK-TRANSFER-1", period_index=2,
        )
        self.register_path = root / "financial.sqlite3"
        self.register = OperatingFinancialRegister(
            self.register_path,
            sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CBank"},
        )
        self.register.bootstrap_admin(
            principal_id="financial-root", authority_ref="BOOTSTRAP", occurred_at=T,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def operation(self, events=None):
        return native_financial_operation(
            events or (self.accrual, self.payment),
            actor_id="financial-root", authority_ref="AUTH:PAYROLL",
            effective_at=T, recorded_at=T,
        )

    def test_verified_wage_group_commits_to_durable_financial_register(self):
        operation = self.operation()
        token = self.register.prepare("TX-WAGE-1", operation)
        receipt = self.register.commit("TX-WAGE-1", token)
        self.assertEqual(receipt["participant"], "financial")
        self.assertEqual(receipt["native_event_id"], operation["native_event_id"])
        self.assertEqual(self.register.status("TX-WAGE-1")["state"], "COMMITTED")
        self.assertEqual(self.register.event_count("TX-WAGE-1"), 1)
        state, version = self.register.state(operation["stream_id"], principal_id="financial-root")
        self.assertEqual(version, 1)
        self.assertEqual(state["status"], "PAID")
        self.assertEqual(state["outstanding_amount"], "0.00")
        self.assertEqual(state["event_ids"], ["WAGE-ACCRUAL-1", "WAGE-PAYMENT-1"])
        self.assertTrue(self.register.verify())

    def test_restart_replays_claim_and_preserves_commit_receipt(self):
        operation = self.operation()
        token = self.register.prepare("TX-WAGE-RESTART", operation)
        receipt = self.register.commit("TX-WAGE-RESTART", token)
        reopened = OperatingFinancialRegister(
            self.register_path,
            sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CBank"},
        )
        self.assertEqual(reopened.status("TX-WAGE-RESTART")["state"], "COMMITTED")
        self.assertEqual(reopened.commit("TX-WAGE-RESTART", token), receipt)
        state, version = reopened.state(operation["stream_id"], principal_id="financial-root")
        self.assertEqual(version, 1)
        self.assertEqual(state["outstanding_amount"], "0.00")
        self.assertTrue(reopened.verify())

    def test_stock_flow_mapper_tampering_is_rejected_before_prepare(self):
        operation = self.operation()
        operation["payload"]["stock_flow_movements"][0]["amount"] = "999"
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "canonical wage mapper"):
            self.register.prepare("TX-WAGE-TAMPER", operation)
        self.assertIsNone(self.register.status("TX-WAGE-TAMPER"))

    def test_unbalanced_or_wrong_sector_posting_is_rejected(self):
        operation = self.operation()
        operation["payload"]["payload"]["events"][0]["postings"][0]["amount"] = "39"
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "canonical wage mapper|balanced|equal"):
            self.register.prepare("TX-WAGE-POSTING-TAMPER", operation)
        self.assertIsNone(self.register.status("TX-WAGE-POSTING-TAMPER"))

    def test_payment_cannot_be_committed_without_accrual_in_group_or_stream(self):
        operation = self.operation((self.payment,))
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "requires an existing accrued claim"):
            self.register.prepare("TX-WAGE-PAYMENT-FIRST", operation)
        self.assertIsNone(self.register.status("TX-WAGE-PAYMENT-FIRST"))

    def test_authorization_is_required_before_prepare(self):
        operation = self.operation()
        operation["payload"]["actor_id"] = "untrusted-actor"
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "not authorized"):
            self.register.prepare("TX-WAGE-UNAUTHORIZED", operation)
        self.assertIsNone(self.register.status("TX-WAGE-UNAUTHORIZED"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
