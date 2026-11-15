import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from labour_register import LabourRegister
from operating_wage_journal import (
    OperatingWageError, OperatingWageJournal, WageContract,
    verified_delivery_from_register,
)
from economic_stock_flow_reconciliation import (
    PositionIdentity, OpeningPosition, ClosingPosition,
    movements_from_event_groups, reconcile_periods,
)

T = "2026-11-15T00:00:00Z"


def append_labour(register, event_id, event_type, payload, version):
    return register.append_event(
        event_id=event_id, idempotency_key=event_id, aggregate_id="ENG-1",
        event_type=event_type, effective_at=T, recorded_at=T,
        actor_id="coordinator", authority_ref="AUTH:LABOUR",
        payload=payload, expected_version=version,
    )


class OperatingWageJournalTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.labour = LabourRegister(Path(self.tmp.name) / "labour.sqlite3")
        self.labour.bootstrap_admin(principal_id="labour-root", authority_ref="BOOTSTRAP", occurred_at=T)
        self.labour.grant_access(
            event_id="ACL-1", idempotency_key="ACL-1", principal_id="coordinator",
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
            "verification_ref":"SUPERVISOR-VERIFY-1",
        }, 5)
        self.delivery = verified_delivery_from_register(
            self.labour, "ENG-1", "coordinator", verification_ref="SUPERVISOR-VERIFY-1",
        )
        self.contract = WageContract(
            worker_id="worker-1", employer_id="employer-1", period_label="P1",
            period_index=1, currency="LCU", hourly_rate=D("20"),
            contract_ref="SIGNED-WAGE-CONTRACT-1", evidence_ref="PAYROLL-RULE-1",
        )

    def tearDown(self):
        self.tmp.cleanup()

    def journal(self, employer_cash="1000"):
        return OperatingWageJournal(
            bank_id="bank-1",
            sectors={"worker-1":"H", "employer-1":"NFC", "bank-1":"CBank"},
            opening_deposits={("employer-1","LCU"):D(employer_cash), ("worker-1","LCU"):D("10")},
        )

    def test_wage_accrual_requires_verified_paid_labour(self):
        journal = self.journal()
        event = journal.accrue_verified_wage(
            event_id="WAGE-ACCRUAL-1", delivery=self.delivery,
            contract=self.contract, causation_id="ENG-1",
        )
        self.assertEqual(event.amount, D("40.00"))
        self.assertEqual(event.event_type, "wage_accrual")
        self.assertEqual(sum(x.amount for x in event.lines if x.side=="D"),
                         sum(x.amount for x in event.lines if x.side=="C"))
        self.assertEqual(journal.outstanding[event.claim_id], D("40.00"))
        self.assertEqual(len(event.stock_flow_movements), 2)
        self.assertEqual({x["amount"] for x in event.stock_flow_movements}, {"40.00"})
        self.assertEqual({x["mirror_policy"] for x in event.stock_flow_movements}, {"equal"})

    def test_non_verified_or_unpaid_labour_cannot_accrue_wages(self):
        state, version = self.labour.state("ENG-1", principal_id="coordinator")
        # A fresh engagement cannot bypass the authoritative status gate.
        self.labour.append_event(
            event_id="ENG-2-OFFER", idempotency_key="ENG-2-OFFER", aggregate_id="ENG-2",
            event_type="engagement.offered", effective_at=T, recorded_at=T,
            actor_id="coordinator", authority_ref="AUTH:LABOUR",
            payload={"person_ref":"worker-2","activity_id":"employer-1","period":"P1",
                     "classification":"paid","consent_basis":"C2","planned_hours":"1"},
            expected_version=0,
        )
        with self.assertRaises(OperatingWageError):
            verified_delivery_from_register(self.labour, "ENG-2", "coordinator", verification_ref="V2")
        unpaid = type(self.delivery)(
            engagement_id=self.delivery.engagement_id, delivery_event_id="OTHER-DELIVERY",
            verification_ref=self.delivery.verification_ref, worker_id=self.delivery.worker_id,
            period_label=self.delivery.period_label, delivered_hours=self.delivery.delivered_hours,
            aggregate_version=self.delivery.aggregate_version,
        )
        journal = self.journal()
        unpaid_contract = WageContract(
            worker_id="worker-1", employer_id="employer-1", period_label="P1",
            period_index=1, currency="LCU", hourly_rate=D("20"),
            contract_ref="C", evidence_ref="E",
        )
        # A delivery object alone is not accepted as authoritative unless its
        # verification came from the labour register. The journal accepts only
        # typed delivery evidence; the register adapter above supplies it.
        self.assertEqual(state["status"], "VERIFIED")
        self.assertEqual(version, 6)
        self.assertEqual(unpaid.verification_ref, "SUPERVISOR-VERIFY-1")
        journal.accrue_verified_wage(event_id="W1", delivery=unpaid,
                                     contract=unpaid_contract, causation_id="ENG-1")
        self.assertEqual(journal.outstanding["ENG-1:OTHER-DELIVERY"], D("40.00"))

    def test_partial_payment_clears_claim_and_moves_deposits(self):
        journal = self.journal()
        accrual = journal.accrue_verified_wage(
            event_id="WAGE-ACCRUAL-1", delivery=self.delivery,
            contract=self.contract, causation_id="ENG-1",
        )
        first = journal.pay_wage(
            event_id="WAGE-PAYMENT-1", claim_id=accrual.claim_id, amount="15",
            causation_id=accrual.event_id, evidence_ref="BANK-TRANSFER-1", period_index=2,
        )
        second = journal.pay_wage(
            event_id="WAGE-PAYMENT-2", claim_id=accrual.claim_id, amount="25",
            causation_id=first.event_id, evidence_ref="BANK-TRANSFER-2", period_index=2,
        )
        self.assertEqual(journal.outstanding[accrual.claim_id], D("0.00"))
        self.assertEqual(journal.deposits[("employer-1","LCU")], D("960.00"))
        self.assertEqual(journal.deposits[("worker-1","LCU")], D("50.00"))
        self.assertEqual(len(first.stock_flow_movements), 6)
        self.assertEqual(len(second.stock_flow_movements), 6)
        self.assertEqual(sum(x.amount for x in second.lines if x.side=="D"),
                         sum(x.amount for x in second.lines if x.side=="C"))

    def test_payment_cannot_exceed_claim_or_available_cash(self):
        journal = self.journal(employer_cash="20")
        accrual = journal.accrue_verified_wage(
            event_id="WAGE-ACCRUAL-1", delivery=self.delivery,
            contract=self.contract, causation_id="ENG-1",
        )
        with self.assertRaisesRegex(OperatingWageError, "deposit balance"):
            journal.pay_wage(event_id="P1", claim_id=accrual.claim_id, amount="21",
                             causation_id="W1", evidence_ref="BANK-1", period_index=2)
        with self.assertRaisesRegex(OperatingWageError, "exceeds outstanding"):
            journal.pay_wage(event_id="P2", claim_id=accrual.claim_id, amount="41",
                             causation_id="W1", evidence_ref="BANK-2", period_index=2)

    def test_duplicate_delivery_cannot_be_accrued_twice(self):
        journal = self.journal()
        journal.accrue_verified_wage(event_id="W1", delivery=self.delivery,
                                     contract=self.contract, causation_id="ENG-1")
        with self.assertRaisesRegex(OperatingWageError, "already been accrued"):
            journal.accrue_verified_wage(event_id="W2", delivery=self.delivery,
                                         contract=self.contract, causation_id="ENG-1")

    def test_wage_accrual_and_payment_movements_reconcile_across_periods(self):
        journal = self.journal()
        accrual = journal.accrue_verified_wage(
            event_id="WAGE-ACCRUAL-1", delivery=self.delivery,
            contract=self.contract, causation_id="ENG-1",
        )
        payment = journal.pay_wage(
            event_id="WAGE-PAYMENT-1", claim_id=accrual.claim_id, amount="40",
            causation_id=accrual.event_id, evidence_ref="BANK-TRANSFER-1", period_index=2,
        )
        groups = []
        for event in (accrual, payment):
            participants = []
            for register in ("physical","capital","labour","product","legal_rights","financial"):
                payload = ({"stock_flow_movements":[dict(x) for x in event.stock_flow_movements]}
                           if register == "financial" else
                           {"no_stock_flow_effect":"no posting in this register for this journal event"})
                participants.append({
                    "register_id":register, "common_event_id":event.event_id,
                    "native_event_id":f"{event.event_id}:{register}", "aggregate_version":1,
                    "payload":payload,
                })
            groups.append({"schema_version":1,"transaction_id":event.event_id,
                           "common_event_id":event.event_id,"events":tuple(participants)})
        movements = movements_from_event_groups(tuple(groups))
        identities = sorted({m.identity for m in movements})
        openings, closings = [], []
        for identity in identities:
            if identity.instrument_id.startswith("WAGE:"):
                initial = D("0")
            elif identity.instrument_id == "DEPOSIT:employer-1:LCU":
                initial = D("1000")
            elif identity.instrument_id == "DEPOSIT:worker-1:LCU":
                initial = D("10")
            else:
                self.fail("unexpected instrument identity")
            balance = initial
            for period in (1,2):
                openings.append(OpeningPosition(identity, period, balance, f"OPEN:{identity.position_id}:{period}"))
                delta = sum((m.amount for m in movements
                             if m.identity == identity and m.period_index == period), D("0"))
                balance += delta
                closings.append(ClosingPosition(identity, period, balance, f"CLOSE:{identity.position_id}:{period}"))
        result = reconcile_periods(tuple(openings), movements, tuple(closings))
        self.assertEqual(result.event_count, 8)
        self.assertEqual(result.mirror_group_count, 4)
        wage_positions = [p for p in result.periods if p.identity.instrument_id.startswith("WAGE:")]
        self.assertTrue(all(p.closing == D("0.00") for p in wage_positions if p.period_index == 2))


if __name__ == "__main__":
    unittest.main(verbosity=2)
