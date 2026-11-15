import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from labour_register import LabourRegister
from operating_wage_journal import (
    OperatingWageJournal, WageContract, verified_delivery_from_register,
    native_financial_operation,
)
from economic_stock_flow_reconciliation import (
    OpeningPosition, ClosingPosition, movements_from_event_groups, reconcile_periods,
)
from operating_financial_register import (
    OperatingFinancialRegister, OperatingFinancialRegisterError,
    wage_stock_flow_movement_specs,
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
        self.register.open_deposit_account(
            event_id="OPEN-EMPLOYER", entity_id="employer-1", bank_id="bank-1",
            currency="LCU", account_ref="EMPLOYER-ACCOUNT-1", opening_balance="1000",
            evidence_ref="BANK-OPEN-EMPLOYER", actor_id="financial-root",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T, expected_revision=0,
        )
        self.register.open_deposit_account(
            event_id="OPEN-WORKER", entity_id="worker-1", bank_id="bank-1",
            currency="LCU", account_ref="WORKER-ACCOUNT-1", opening_balance="10",
            evidence_ref="BANK-OPEN-WORKER", actor_id="financial-root",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T, expected_revision=1,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def operation(self, events=None):
        return native_financial_operation(
            events or (self.accrual, self.payment),
            actor_id="financial-root", authority_ref="AUTH:PAYROLL",
            effective_at=T, recorded_at=T,
            expected_revision=self.register.state("operating-financial", principal_id="financial-root")[1],
        )

    def test_verified_wage_group_commits_to_durable_financial_register(self):
        operation = self.operation()
        token = self.register.prepare("TX-WAGE-1", operation)
        receipt = self.register.commit("TX-WAGE-1", token)
        self.assertEqual(receipt["participant"], "financial")
        self.assertEqual(receipt["native_event_id"], operation["native_event_id"])
        self.assertEqual(self.register.status("TX-WAGE-1")["state"], "COMMITTED")
        self.assertEqual(self.register.event_count("TX-WAGE-1"), 1)
        state, version = self.register.state("operating-financial", principal_id="financial-root")
        claim = state["claims"][self.accrual.claim_id]
        self.assertEqual(version, 3)
        self.assertEqual(claim["status"], "PAID")
        self.assertEqual(claim["outstanding_amount"], "0.00")
        self.assertEqual(claim["event_ids"], ["WAGE-ACCRUAL-1", "WAGE-PAYMENT-1"])
        self.assertEqual(self.register.deposit_balance("employer-1", "LCU", principal_id="financial-root")[0], D("960.00"))
        self.assertEqual(self.register.deposit_balance("worker-1", "LCU", principal_id="financial-root")[0], D("50.00"))
        self.assertTrue(self.register.verify())


    def test_accrual_and_later_settlement_are_separate_durable_revisions(self):
        accrual_operation = self.operation((self.accrual,))
        accrual_token = self.register.prepare("TX-WAGE-ACCRUAL", accrual_operation)
        self.register.commit("TX-WAGE-ACCRUAL", accrual_token)
        state, version = self.register.state("operating-financial", principal_id="financial-root")
        claim = state["claims"][self.accrual.claim_id]
        self.assertEqual(version, 3)
        self.assertEqual(claim["status"], "OUTSTANDING")
        self.assertEqual(claim["outstanding_amount"], "40.00")

        payment_operation = native_financial_operation(
            (self.payment,), actor_id="financial-root", authority_ref="AUTH:PAYROLL",
            effective_at=T, recorded_at=T, expected_revision=3,
        )
        payment_token = self.register.prepare("TX-WAGE-PAYMENT", payment_operation)
        self.register.commit("TX-WAGE-PAYMENT", payment_token)
        state, version = self.register.state("operating-financial", principal_id="financial-root")
        claim = state["claims"][self.accrual.claim_id]
        self.assertEqual(version, 4)
        self.assertEqual(claim["status"], "PAID")
        self.assertEqual(claim["outstanding_amount"], "0.00")
        self.assertEqual(claim["event_ids"], ["WAGE-ACCRUAL-1", "WAGE-PAYMENT-1"])
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
        state, version = reopened.state("operating-financial", principal_id="financial-root")
        claim = state["claims"][self.accrual.claim_id]
        self.assertEqual(version, 3)
        self.assertEqual(claim["outstanding_amount"], "0.00")
        self.assertEqual(reopened.deposit_balance("employer-1", "LCU", principal_id="financial-root")[0], D("960.00"))
        self.assertEqual(reopened.deposit_balance("worker-1", "LCU", principal_id="financial-root")[0], D("50.00"))
        self.assertTrue(reopened.verify())


    def test_wage_group_movements_close_in_canonical_sfc_reconciliation(self):
        operation = self.operation()
        common_id = "COMMON-WAGE-1"
        participant_events = []
        for name in ("physical", "capital", "labour", "product", "legal_rights", "financial"):
            if name == "financial":
                payload = operation["payload"]["payload"]
            else:
                payload = {"no_stock_flow_effect": f"not implicated by wage-only fixture: {name}"}
            participant_events.append({
                "register_id": name, "common_event_id": common_id,
                "native_event_id": f"{common_id}:{name}", "aggregate_version": 1,
                "payload": payload,
            })
        groups = ({
            "schema_version": 1, "transaction_id": common_id,
            "common_event_id": common_id, "events": tuple(participant_events),
        },)
        movements = movements_from_event_groups(groups)
        self.assertEqual(len(movements), 8)
        identities = sorted({movement.identity for movement in movements})
        openings, closings = [], []
        for identity in identities:
            instrument = identity.instrument_id
            if instrument.startswith("DEPOSIT:employer-1:"):
                initial = D("1000")
            elif instrument.startswith("DEPOSIT:worker-1:"):
                initial = D("10")
            else:
                initial = D("0")
            balance = initial
            for period in (1, 2):
                openings.append(OpeningPosition(identity, period, balance, f"OPEN:{identity.position_id}:{period}"))
                balance += sum((movement.amount for movement in movements
                                if movement.identity == identity and movement.period_index == period), D("0"))
                closings.append(ClosingPosition(identity, period, balance, f"CLOSE:{identity.position_id}:{period}"))
        result = reconcile_periods(tuple(openings), movements, tuple(closings))
        self.assertEqual(result.event_count, 8)
        self.assertEqual(result.mirror_group_count, 4)
        wage_positions = [item for item in result.periods if item.identity.instrument_id.startswith("WAGE:")]
        self.assertTrue(all(item.closing == D("0.00") for item in wage_positions if item.period_index == 2))
        employer_positions = [item for item in result.periods
                              if item.identity.instrument_id.startswith("DEPOSIT:employer-1:")]
        worker_positions = [item for item in result.periods
                            if item.identity.instrument_id.startswith("DEPOSIT:worker-1:")]
        self.assertTrue(all(item.closing == D("960.00") for item in employer_positions if item.period_index == 2))
        self.assertTrue(all(item.closing == D("50.00") for item in worker_positions if item.period_index == 2))


    def test_register_rejects_unknown_sector_codes(self):
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "unsupported institutional sector"):
            OperatingFinancialRegister(
                Path(self.tmp.name) / "bad-sector.sqlite3",
                sectors={"worker-1":"HOUSEHOLD", "employer-1":"NFC", "bank-1":"CBank"},
            )

    def test_prepare_requires_explicit_bank_sector_and_distinct_entities(self):
        missing_bank = OperatingFinancialRegister(
            Path(self.tmp.name) / "missing-bank-sector.sqlite3",
            sectors={"worker-1":"H", "employer-1":"NFC"},
        )
        missing_bank.bootstrap_admin(
            principal_id="financial-root", authority_ref="BOOTSTRAP", occurred_at=T,
        )
        missing_bank.grant_access(
            event_id="ACL-MISSING-BANK", idempotency_key="ACL-MISSING-BANK",
            principal_id="coordinator", permissions=["financial:read", "financial:write"],
            actor_id="financial-root", authority_ref="POLICY", occurred_at=T,
        )
        operation = self.operation()
        operation["expected_revision"] = 0
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "missing explicit institutional sector for bank-1"):
            missing_bank.prepare("TX-MISSING-BANK", operation)

        operation = self.operation()
        operation["payload"]["payload"]["events"][0]["worker_id"] = "employer-1"
        operation["payload"]["stock_flow_movements"] = wage_stock_flow_movement_specs(
            operation["payload"]["payload"]["events"]
        )
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "must be distinct entities"):
            self.register.prepare("TX-SAME-WORKER-EMPLOYER", operation)

    def test_claim_identity_must_bind_engagement_and_verified_delivery(self):
        operation = self.operation()
        operation["payload"]["payload"]["events"][0]["engagement_id"] = "OTHER-ENGAGEMENT"
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "claim ID must bind"):
            self.register.prepare("TX-WRONG-CLAIM-IDENTITY", operation)

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


    def test_durable_deposit_balance_blocks_overdraw_after_memory_precheck(self):
        low_path = Path(self.tmp.name) / "low-balance.sqlite3"
        low = OperatingFinancialRegister(
            low_path, sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CBank"},
        )
        low.bootstrap_admin(principal_id="financial-root", authority_ref="BOOTSTRAP", occurred_at=T)
        low.open_deposit_account(
            event_id="LOW-EMPLOYER", entity_id="employer-1", bank_id="bank-1",
            currency="LCU", account_ref="LOW-EMPLOYER-ACCOUNT", opening_balance="20",
            evidence_ref="BANK-LOW-EMPLOYER", actor_id="financial-root",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T, expected_revision=0,
        )
        low.open_deposit_account(
            event_id="LOW-WORKER", entity_id="worker-1", bank_id="bank-1",
            currency="LCU", account_ref="LOW-WORKER-ACCOUNT", opening_balance="10",
            evidence_ref="BANK-LOW-WORKER", actor_id="financial-root",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T, expected_revision=1,
        )
        operation = self.operation()
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "insufficient durable employer deposit balance"):
            low.prepare("TX-LOW-DURABLE-CASH", operation)
        self.assertIsNone(low.status("TX-LOW-DURABLE-CASH"))
        self.assertEqual(low.deposit_balance("employer-1", "LCU", principal_id="financial-root")[0], D("20"))
        self.assertEqual(low.deposit_balance("worker-1", "LCU", principal_id="financial-root")[0], D("10"))

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
