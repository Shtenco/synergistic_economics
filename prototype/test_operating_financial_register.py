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
            sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CB"},
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
            sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CB"},
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
        deposit_opening_p2 = self.register.deposit_opening_positions(
            period_index=2, principal_id="financial-root",
        )
        deposit_opening_p3 = self.register.deposit_opening_positions(
            period_index=3, principal_id="financial-root",
        )
        p2_balances = {row.identity.position_id: row.amount for row in deposit_opening_p2}
        p3_balances = {row.identity.position_id: row.amount for row in deposit_opening_p3}
        self.assertEqual(p2_balances["DEPOSIT:employer-1:bank-1:LCU:ASSET"], D("1000"))
        self.assertEqual(p2_balances["DEPOSIT:worker-1:bank-1:LCU:ASSET"], D("10"))
        self.assertEqual(p3_balances["DEPOSIT:employer-1:bank-1:LCU:ASSET"], D("960"))
        self.assertEqual(p3_balances["DEPOSIT:worker-1:bank-1:LCU:ASSET"], D("50"))
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
            sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CB"},
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
        durable_openings = {
            row.identity: (row.amount, row.evidence_ref)
            for row in self.register.deposit_opening_positions(
                period_index=1, principal_id="financial-root",
            )
        }
        openings, closings = [], []
        for identity in identities:
            initial, opening_evidence = durable_openings.get(
                identity, (D("0"), f"OPEN-WAGE:{identity.position_id}"),
            )
            balance = initial
            for period in (1, 2):
                openings.append(OpeningPosition(
                    identity, period, balance,
                    opening_evidence if period == 1 else f"OPEN:{identity.position_id}:{period}",
                ))
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
                sectors={"worker-1":"HOUSEHOLD", "employer-1":"NFC", "bank-1":"CB"},
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



    def test_deposit_opening_balance_requires_currency_minor_unit_precision(self):
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "exact multiple of its minor unit"):
            self.register.open_deposit_account(
                event_id="BAD-OPENING-PRECISION", entity_id="worker-2", bank_id="bank-1",
                currency="LCU", account_ref="BAD-PRECISION-ACCOUNT", opening_balance="1.001",
                evidence_ref="BANK-BAD-PRECISION", actor_id="financial-root",
                authority_ref="BANK-OPENING", effective_at=T, recorded_at=T,
                expected_revision=2, minor_unit="0.01",
            )
        self.assertIsNone(self.register.status("BAD-OPENING-PRECISION"))

    def test_payment_minor_unit_must_match_both_durable_deposit_accounts(self):
        mismatch_path = Path(self.tmp.name) / "minor-mismatch.sqlite3"
        mismatch = OperatingFinancialRegister(
            mismatch_path, sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CB"},
        )
        mismatch.bootstrap_admin(principal_id="financial-root", authority_ref="BOOTSTRAP", occurred_at=T)
        mismatch.open_deposit_account(
            event_id="MISMATCH-EMPLOYER", entity_id="employer-1", bank_id="bank-1",
            currency="LCU", account_ref="MISMATCH-EMPLOYER-ACCOUNT", opening_balance="1000",
            evidence_ref="BANK-MISMATCH-EMPLOYER", actor_id="financial-root",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T,
            expected_revision=0, minor_unit="0.001",
        )
        mismatch.open_deposit_account(
            event_id="MISMATCH-WORKER", entity_id="worker-1", bank_id="bank-1",
            currency="LCU", account_ref="MISMATCH-WORKER-ACCOUNT", opening_balance="10",
            evidence_ref="BANK-MISMATCH-WORKER", actor_id="financial-root",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T,
            expected_revision=1, minor_unit="0.001",
        )
        operation = self.operation()
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "minor unit differs"):
            mismatch.prepare("TX-MINOR-UNIT-MISMATCH", operation)
        self.assertIsNone(mismatch.status("TX-MINOR-UNIT-MISMATCH"))

    def test_durable_deposit_balance_blocks_overdraw_after_memory_precheck(self):
        low_path = Path(self.tmp.name) / "low-balance.sqlite3"
        low = OperatingFinancialRegister(
            low_path, sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CB"},
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


    def test_bank_loan_origination_and_repayment_are_durable_and_change_deposit_stock(self):
        receipt = self.register.commit_bank_credit(
            event_id="BANK-LOAN-1", event_type="bank.loan_originated",
            loan_id="LOAN-1", borrower_id="worker-1", bank_id="bank-1",
            currency="LCU", amount="100", period_index=3,
            evidence_ref="SIGNED-LOAN-1", actor_id="financial-root",
            authority_ref="BANK-CREDIT-POLICY", effective_at=T, recorded_at=T,
            expected_revision=2,
        )
        self.assertEqual(receipt["participant"], "financial")
        self.assertEqual(self.register.deposit_balance(
            "worker-1", "LCU", principal_id="financial-root")[0], D("110.00"))
        loan, version = self.register.loan_state("LOAN-1", principal_id="financial-root")
        self.assertEqual(version, 3)
        self.assertEqual(loan["outstanding_principal"], "100")
        self.assertEqual(loan["bank_id"], "bank-1")
        self.assertEqual(loan["origination_period_index"], 3)
        snapshot = self.register.bank_principal_snapshot(
            "bank-1", "LCU", principal_id="financial-root")
        self.assertEqual(snapshot["deposit_liabilities"], D("1110.00"))
        self.assertEqual(snapshot["loan_assets"], D("100"))

        self.register.commit_bank_credit(
            event_id="BANK-LOAN-REPAY-1", event_type="bank.loan_principal_repaid",
            loan_id="LOAN-1", borrower_id="worker-1", bank_id="bank-1",
            currency="LCU", amount="35", period_index=4,
            evidence_ref="BANK-REPAYMENT-1", causation_id="BANK-LOAN-1",
            actor_id="financial-root", authority_ref="BANK-CREDIT-POLICY",
            effective_at=T, recorded_at=T, expected_revision=3,
        )
        self.assertEqual(self.register.deposit_balance(
            "worker-1", "LCU", principal_id="financial-root")[0], D("75.00"))
        loan, version = self.register.loan_state("LOAN-1", principal_id="financial-root")
        self.assertEqual(version, 4)
        self.assertEqual(loan["outstanding_principal"], "65")
        self.assertEqual(loan["origination_period_index"], 3)
        self.assertEqual(loan["status"], "OUTSTANDING")
        snapshot = self.register.bank_principal_snapshot(
            "bank-1", "LCU", principal_id="financial-root")
        self.assertEqual(snapshot["deposit_liabilities"], D("1075.00"))
        self.assertEqual(snapshot["loan_assets"], D("65"))
        opening_at_origination = self.register.loan_opening_positions(
            period_index=3, principal_id="financial-root",
        )
        opening_before_repayment = self.register.loan_opening_positions(
            period_index=4, principal_id="financial-root",
        )
        opening_after_repayment = self.register.loan_opening_positions(
            period_index=5, principal_id="financial-root",
        )
        self.assertEqual([row.amount for row in opening_at_origination], [D("0"), D("0")])
        self.assertEqual([row.amount for row in opening_before_repayment], [D("100"), D("100")])
        self.assertEqual([row.amount for row in opening_after_repayment], [D("65"), D("65")])
        self.assertEqual(len({row.evidence_ref for row in opening_after_repayment}), 1)
        deposit_opening_before_loan = self.register.deposit_opening_positions(
            period_index=3, principal_id="financial-root",
        )
        deposit_opening_before_repayment = self.register.deposit_opening_positions(
            period_index=4, principal_id="financial-root",
        )
        deposit_opening_after_repayment = self.register.deposit_opening_positions(
            period_index=5, principal_id="financial-root",
        )
        worker_asset = next(row for row in deposit_opening_before_loan
                            if row.identity.position_id == "DEPOSIT:worker-1:bank-1:LCU:ASSET")
        worker_asset_p4 = next(row for row in deposit_opening_before_repayment
                               if row.identity.position_id == "DEPOSIT:worker-1:bank-1:LCU:ASSET")
        worker_asset_p5 = next(row for row in deposit_opening_after_repayment
                               if row.identity.position_id == "DEPOSIT:worker-1:bank-1:LCU:ASSET")
        self.assertEqual(worker_asset.amount, D("10.00"))
        self.assertEqual(worker_asset_p4.amount, D("110.00"))
        self.assertEqual(worker_asset_p5.amount, D("75.00"))
        self.assertEqual(len({row.evidence_ref for row in deposit_opening_after_repayment
                              if row.identity.instrument_id == "DEPOSIT:worker-1:bank-1:LCU"}), 1)
        self.assertTrue(self.register.verify())

    def test_large_principal_repayments_preserve_all_accepted_decimal_digits(self):
        principal = "123456789012345678901234567890.00"
        self.register.commit_bank_credit(
            event_id="BANK-LOAN-LARGE", event_type="bank.loan_originated",
            loan_id="LOAN-LARGE", borrower_id="worker-1", bank_id="bank-1",
            currency="LCU", amount=principal, period_index=3,
            evidence_ref="SIGNED-LOAN-LARGE", actor_id="financial-root",
            authority_ref="BANK-CREDIT-POLICY", effective_at=T, recorded_at=T,
            expected_revision=2,
        )
        self.register.commit_bank_credit(
            event_id="BANK-LOAN-LARGE-REPAY", event_type="bank.loan_principal_repaid",
            loan_id="LOAN-LARGE", borrower_id="worker-1", bank_id="bank-1",
            currency="LCU", amount="1.00", period_index=4,
            evidence_ref="BANK-LOAN-LARGE-REPAYMENT",
            causation_id="BANK-LOAN-LARGE", actor_id="financial-root",
            authority_ref="BANK-CREDIT-POLICY", effective_at=T, recorded_at=T,
            expected_revision=3,
        )
        expected = D("123456789012345678901234567889.00")
        loan, _ = self.register.loan_state(
            "LOAN-LARGE", principal_id="financial-root",
        )
        self.assertEqual(D(loan["outstanding_principal"]), expected)
        self.assertEqual(
            self.register.deposit_balance(
                "worker-1", "LCU", principal_id="financial-root",
            )[0],
            D("123456789012345678901234567899.00"),
        )
        snapshot = self.register.bank_principal_snapshot(
            "bank-1", "LCU", principal_id="financial-root",
        )
        self.assertEqual(snapshot["loan_assets"], expected)
        self.assertEqual(
            snapshot["deposit_liabilities"],
            D("123456789012345678901234568899.00"),
        )

    def test_refinancing_state_retains_original_advance_period_after_repayment(self):
        register = OperatingFinancialRegister(
            Path(self.tmp.name) / "refinancing-period.sqlite3",
            sectors={"bank-1": "CB", "central-bank-1": "CBank"},
        )
        register.bootstrap_admin(
            principal_id="financial-root", authority_ref="BOOTSTRAP", occurred_at=T,
        )
        register.open_bank_reserve_account(
            event_id="OPEN-RESERVE-REFI", bank_id="bank-1",
            central_bank_id="central-bank-1", currency="LCU",
            account_ref="RESERVE-ACCOUNT-1", opening_balance="0",
            evidence_ref="RESERVE-OPENING-EVIDENCE", actor_id="financial-root",
            authority_ref="CENTRAL-BANK-OPENING", effective_at=T, recorded_at=T,
            expected_revision=0,
        )
        register.commit_central_bank_refinancing(
            event_id="REFI-ADVANCE-1", event_type="central_bank.refinancing_advanced",
            facility_id="FACILITY-1", bank_id="bank-1",
            central_bank_id="central-bank-1", currency="LCU", amount="100",
            period_index=2, evidence_ref="REFI-ADVANCE-EVIDENCE",
            actor_id="financial-root", authority_ref="REFI-POLICY",
            effective_at=T, recorded_at=T, expected_revision=1,
        )
        register.commit_central_bank_refinancing(
            event_id="REFI-REPAY-1", event_type="central_bank.refinancing_principal_repaid",
            facility_id="FACILITY-1", bank_id="bank-1",
            central_bank_id="central-bank-1", currency="LCU", amount="40",
            period_index=3, evidence_ref="REFI-REPAY-EVIDENCE",
            actor_id="financial-root", authority_ref="REFI-POLICY",
            effective_at=T, recorded_at=T, expected_revision=2,
            causation_id="REFI-ADVANCE-1",
        )
        facility, version = register.refinancing_state(
            "FACILITY-1", principal_id="financial-root",
        )
        self.assertEqual(version, 3)
        self.assertEqual(facility["origination_period_index"], 2)
        self.assertEqual(facility["outstanding_principal"], "60")
        opening_at_advance = register.refinancing_opening_positions(
            period_index=2, principal_id="financial-root",
        )
        opening_before_repayment = register.refinancing_opening_positions(
            period_index=3, principal_id="financial-root",
        )
        opening_after_repayment = register.refinancing_opening_positions(
            period_index=4, principal_id="financial-root",
        )
        self.assertEqual([row.amount for row in opening_at_advance], [D("0"), D("0")])
        self.assertEqual([row.amount for row in opening_before_repayment], [D("100"), D("100")])
        self.assertEqual([row.amount for row in opening_after_repayment], [D("60"), D("60")])
        reserve_opening_before_advance = register.reserve_opening_positions(
            period_index=2, principal_id="financial-root",
        )
        reserve_opening_before_repayment = register.reserve_opening_positions(
            period_index=3, principal_id="financial-root",
        )
        reserve_opening_after_repayment = register.reserve_opening_positions(
            period_index=4, principal_id="financial-root",
        )
        self.assertEqual([row.amount for row in reserve_opening_before_advance], [D("0"), D("0")])
        self.assertEqual([row.amount for row in reserve_opening_before_repayment], [D("100"), D("100")])
        self.assertEqual([row.amount for row in reserve_opening_after_repayment], [D("60"), D("60")])
        self.assertEqual(len({row.evidence_ref for row in reserve_opening_after_repayment}), 1)
        self.assertTrue(register.verify())

    def test_interbank_settlement_replays_shared_deposit_and_reserve_openings(self):
        register = OperatingFinancialRegister(
            Path(self.tmp.name) / "interbank-openings.sqlite3",
            sectors={
                "payer-1": "H", "payee-1": "H",
                "bank-1": "CB", "bank-2": "CB",
                "central-bank-1": "CBank",
            },
        )
        register.bootstrap_admin(
            principal_id="financial-root", authority_ref="BOOTSTRAP", occurred_at=T,
        )
        register.open_deposit_account(
            event_id="IB-PAYER-DEPOSIT", entity_id="payer-1", bank_id="bank-1",
            currency="LCU", account_ref="IB-PAYER-ACCOUNT", opening_balance="100",
            evidence_ref="IB-PAYER-OPEN", actor_id="financial-root",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T,
            expected_revision=0,
        )
        register.open_deposit_account(
            event_id="IB-PAYEE-DEPOSIT", entity_id="payee-1", bank_id="bank-2",
            currency="LCU", account_ref="IB-PAYEE-ACCOUNT", opening_balance="5",
            evidence_ref="IB-PAYEE-OPEN", actor_id="financial-root",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T,
            expected_revision=1,
        )
        register.open_bank_reserve_account(
            event_id="IB-PAYER-RESERVE", bank_id="bank-1",
            central_bank_id="central-bank-1", currency="LCU",
            account_ref="IB-PAYER-RESERVE-ACCOUNT", opening_balance="50",
            evidence_ref="IB-PAYER-RESERVE-OPEN", actor_id="financial-root",
            authority_ref="CENTRAL-BANK-OPENING", effective_at=T, recorded_at=T,
            expected_revision=2,
        )
        register.open_bank_reserve_account(
            event_id="IB-PAYEE-RESERVE", bank_id="bank-2",
            central_bank_id="central-bank-1", currency="LCU",
            account_ref="IB-PAYEE-RESERVE-ACCOUNT", opening_balance="20",
            evidence_ref="IB-PAYEE-RESERVE-OPEN", actor_id="financial-root",
            authority_ref="CENTRAL-BANK-OPENING", effective_at=T, recorded_at=T,
            expected_revision=3,
        )
        register.settle_interbank_payment(
            event_id="IB-SETTLEMENT-1", payment_id="PAYMENT-1",
            payer_id="payer-1", payee_id="payee-1",
            payer_bank_id="bank-1", payee_bank_id="bank-2",
            central_bank_id="central-bank-1", currency="LCU",
            amount="30", period_index=2, evidence_ref="IB-SETTLEMENT-EVIDENCE",
            actor_id="financial-root", authority_ref="INTERBANK-POLICY",
            effective_at=T, recorded_at=T, expected_revision=4,
        )
        deposits = register.deposit_opening_positions(
            period_index=3, principal_id="financial-root",
        )
        reserves = register.reserve_opening_positions(
            period_index=3, principal_id="financial-root",
        )
        deposit_balances = {
            row.identity.position_id: row.amount for row in deposits
        }
        reserve_balances = {
            row.identity.position_id: row.amount for row in reserves
        }
        self.assertEqual(deposit_balances["DEPOSIT:payer-1:bank-1:LCU:ASSET"], D("70"))
        self.assertEqual(deposit_balances["DEPOSIT:payee-1:bank-2:LCU:ASSET"], D("35"))
        self.assertEqual(reserve_balances["RESERVE:bank-1:central-bank-1:LCU:ASSET"], D("20"))
        self.assertEqual(reserve_balances["RESERVE:bank-2:central-bank-1:LCU:ASSET"], D("50"))
        self.assertTrue(register.verify())

    def test_bank_credit_rejects_wrong_bank_and_unmatched_repayment_without_commit(self):
        self.register.sectors["other-bank"] = "CB"
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "deposit bank"):
            self.register.commit_bank_credit(
                event_id="BANK-LOAN-WRONG-BANK", event_type="bank.loan_originated",
                loan_id="LOAN-WRONG-BANK", borrower_id="worker-1", bank_id="other-bank",
                currency="LCU", amount="100", period_index=3,
                evidence_ref="SIGNED-LOAN-WRONG-BANK", actor_id="financial-root",
                authority_ref="BANK-CREDIT-POLICY", effective_at=T, recorded_at=T,
                expected_revision=2,
            )
        self.assertIsNone(self.register.status("BANK-LOAN-WRONG-BANK"))
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "existing durable loan"):
            self.register.commit_bank_credit(
                event_id="BANK-LOAN-REPAY-NO-LOAN", event_type="bank.loan_principal_repaid",
                loan_id="NO-LOAN", borrower_id="worker-1", bank_id="bank-1",
                currency="LCU", amount="11", period_index=3,
                evidence_ref="REPAYMENT-NO-LOAN", causation_id="NO-LOAN",
                actor_id="financial-root", authority_ref="BANK-CREDIT-POLICY",
                effective_at=T, recorded_at=T, expected_revision=2,
            )
        self.assertIsNone(self.register.status("BANK-LOAN-REPAY-NO-LOAN"))
        self.assertEqual(self.register.deposit_balance(
            "worker-1", "LCU", principal_id="financial-root")[0], D("10.00"))



if __name__ == "__main__":
    unittest.main(verbosity=2)
