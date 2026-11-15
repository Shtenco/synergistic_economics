import json
import tempfile
import unittest
from dataclasses import asdict
from decimal import Decimal as D
from pathlib import Path

from physical_flow_store import FlowPosting, PhysicalFlowStore
from capital_cohort_bridge import CapitalCohort
from capital_cohort_store import CapitalCohortStore
from product_register import ProductRegister
from labour_register import LabourRegister
from legal_rights_register import LegalRightsRegister
from cross_register_coordinator import CrossRegisterCoordinator, PARTICIPANTS
from native_store_participants import (
    make_physical_participant, make_capital_participant, make_product_participant,
)
from operating_financial_register import OperatingFinancialRegister
from operating_wage_coordinator import OperatingWageCoordinator
from operating_wage_journal import (
    OperatingWageJournal, WageContract, verified_delivery_from_register,
)
from economic_stock_flow_reconciliation import (
    PositionIdentity, OpeningPosition, ClosingPosition,
    movements_from_event_groups, reconcile_periods,
)

T = "2026-11-15T00:00:00Z"
AUTH = lambda actor, authority, event_type, payload: actor == "coordinator" and authority.startswith("AUTH:")


def envelope(event_type, payload, event_id):
    return {
        "event_type": event_type, "effective_at": T, "recorded_at": T,
        "actor_id": "coordinator", "authority_ref": "AUTH:COORDINATOR",
        "idempotency_key": event_id, "payload": payload,
    }


def append_labour(register, event_id, event_type, payload, version, aggregate_id="ENG-1"):
    return register.append_event(
        event_id=event_id, idempotency_key=event_id, aggregate_id=aggregate_id,
        event_type=event_type, effective_at=T, recorded_at=T,
        actor_id="coordinator", authority_ref="AUTH:LABOUR",
        payload=payload, expected_version=version,
    )


def labour_fixture(path):
    labour = LabourRegister(path)
    labour.bootstrap_admin(principal_id="labour-root", authority_ref="BOOTSTRAP:L", occurred_at=T)
    labour.grant_access(
        event_id="L-ACL", idempotency_key="L-ACL", principal_id="coordinator",
        permissions=["labour:read", "labour:write"], actor_id="labour-root",
        authority_ref="POLICY:L", occurred_at=T,
    )
    append_labour(labour, "L1", "engagement.offered", {
        "person_ref": "worker-1", "activity_id": "employer-1", "period": "P1",
        "classification": "paid", "consent_basis": "SIGNED-WAGE-CONTRACT-1",
        "planned_hours": "2",
    }, 0)
    append_labour(labour, "L2", "engagement.accepted", {
        "consent_ref": "WORKER-CONSENT-1", "accepted_hours": "2",
    }, 1)
    append_labour(labour, "L3", "engagement.scheduled", {"scheduled_hours": "2"}, 2)
    append_labour(labour, "L4", "engagement.started", {}, 3)
    append_labour(labour, "L5", "engagement.delivered", {
        "delivered_hours": "2", "evidence_ref": "TIMESHEET-1",
    }, 4)
    append_labour(labour, "L6", "engagement.verified", {
        "verification_ref": "SUPERVISOR-VERIFY-1",
    }, 5)
    return labour


def build_wage_events(labour, *, payment_amount="40"):
    delivery = verified_delivery_from_register(
        labour, "ENG-1", "coordinator", verification_ref="SUPERVISOR-VERIFY-1",
    )
    contract = WageContract(
        worker_id="worker-1", employer_id="employer-1", period_label="P1",
        period_index=1, currency="LCU", hourly_rate=D("20"),
        contract_ref="SIGNED-WAGE-CONTRACT-1", evidence_ref="PAYROLL-RULE-1",
    )
    journal = OperatingWageJournal(
        bank_id="bank-1",
        sectors={"worker-1": "H", "employer-1": "NFC", "bank-1": "CB"},
        opening_deposits={("employer-1", "LCU"): D("1000"), ("worker-1", "LCU"): D("10")},
    )
    accrual = journal.accrue_verified_wage(
        event_id="WAGE-ACCRUAL-1", delivery=delivery, contract=contract,
        causation_id="L5", labour_register=labour, principal_id="coordinator",
    )
    payment = journal.pay_wage(
        event_id="WAGE-PAYMENT-1", claim_id=accrual.claim_id, amount=payment_amount,
        causation_id=accrual.event_id, evidence_ref="BANK-TRANSFER-1", period_index=2,
    )
    return delivery, contract, journal, (accrual, payment)


def make_operations(delivery, contract, events, *, labour_settled_hours="2"):
    accrual = events[0]
    claim_id = accrual.claim_id
    outflow = FlowPosting(
        flow_id="LABOUR-FLOW-1", node_id="worker-1", role="outflow",
        origin_node="worker-1", destination_node="employer-1",
        origin_boundary="domestic", destination_boundary="domestic",
        product_id="labour_service", grade_id="verified", quantity=D("2"), unit="h",
        event_time=T, period="P1", flow_class="service_delivery", quality="verified",
        measurement_method="TIMESHEET-1", uncertainty=D("0"), evidence_status="documented",
    )
    inflow = FlowPosting(**(asdict(outflow) | {"node_id": "employer-1", "role": "inflow"}))
    outdict = asdict(outflow)
    outdict["quantity"] = str(outdict["quantity"])
    outdict["uncertainty"] = str(outdict["uncertainty"])
    indict = asdict(inflow)
    indict["quantity"] = str(indict["quantity"])
    indict["uncertainty"] = str(indict["uncertainty"])
    financial_movements = [
        dict(movement) for event in events for movement in event.stock_flow_movements
    ]
    financial_payload = {
        "claim_id": claim_id,
        "events": [event.to_native_payload() for event in events],
    }
    paid_amount = sum((event.amount for event in events[1:]), D("0"))
    fully_paid = paid_amount == accrual.amount
    evidence = [
        contract.contract_ref, contract.evidence_ref,
        delivery.delivery_evidence_ref, delivery.verification_ref,
        *(event.evidence_ref for event in events[1:]),
    ]
    return {
        "physical": {
            "stream_id": "physical", "native_event_id": "LABOUR-FLOW-1", "expected_revision": 0,
            "payload": envelope("physical.flow_recorded", {"outflow": outdict, "inflow": indict},
                                "LABOUR-FLOW-1") | {
                "no_stock_flow_effect": "verified labour service is a non-stockable period flow, not an opening/closing inventory",
            },
        },
        "capital": {
            "stream_id": "capital", "native_event_id": "CAPITAL-PERIOD:2026", "expected_revision": 0,
            "payload": envelope("capital.period_appended", {
                "period": 2026, "events": [], "additions": [],
            }, "CAPITAL-PERIOD:2026") | {
                "no_stock_flow_effect": "no capital cohort change is caused by this wage settlement",
            },
        },
        "labour": {
            "stream_id": delivery.engagement_id, "native_event_id": "LABOUR-SETTLED-1",
            "expected_revision": delivery.aggregate_version,
            "payload": envelope("engagement.settled", {
                "settled_hours": labour_settled_hours, "settlement_ref": accrual.event_id,
            }, "LABOUR-SETTLED-1") | {
                "no_stock_flow_effect": "measured service hours are represented by the paired physical flow",
            },
        },
        "product": {
            "stream_id": "product", "native_event_id": "SPEC:labour_service:verified",
            "expected_revision": 0,
            "payload": envelope("product_spec", {
                "product_id": "labour_service", "grade_id": "verified",
                "dimension": "time", "native_unit": "h", "stockability": "non_stockable",
                "time_basis": "period_flow", "evidence_ref": "LABOUR-SERVICE-SPEC",
            }, "SPEC:labour_service:verified") | {
                "no_stock_flow_effect": "service specification metadata only",
            },
        },
        "legal_rights": {
            "stream_id": f"WAGE-RIGHT:{claim_id}", "native_event_id": f"WAGE-RIGHT:{claim_id}",
            "expected_revision": 0,
            "payload": envelope(
                "right.created_and_extinguished" if fully_paid else "right.created",
                {
                    "holder_id": delivery.worker_id, "obligor_id": delivery.employer_id,
                    "right_type": "wage_claim", "scope": claim_id, "jurisdiction": "KZ",
                    "legal_instrument_ref": contract.contract_ref, "effective_from": T,
                    "claim_amount": str(accrual.amount), "currency": accrual.currency,
                    "evidence_refs": evidence,
                    **({
                        "settlement_event_id": events[-1].event_id,
                        "settlement_evidence_ref": events[-1].evidence_ref,
                        "settled_amount": str(paid_amount),
                    } if fully_paid else {}),
                }, f"WAGE-RIGHT:{claim_id}",
            ) | {
                "no_stock_flow_effect": "legal claim is mirrored in the financial wage receivable/payable positions",
            },
        },
        "financial": {
            "stream_id": "operating-financial", "native_event_id": "WAGE-GROUP-1",
            "expected_revision": 2,
            "payload": envelope("wage.event_group_committed", financial_payload, "WAGE-GROUP-1")
                       | {"stock_flow_movements": financial_movements},
        },
    }


def make_participants(root):
    physical = PhysicalFlowStore(root / "physical.sqlite3")
    capital = CapitalCohortStore(root / "capital.sqlite3")
    with capital._connect() as con:
        initialized = con.execute(
            "SELECT 1 FROM capital_cohort_meta WHERE singleton_id=1"
        ).fetchone() is not None
    if not initialized:
        capital.initialize((CapitalCohort("C1", "cell-1", "machine", 2026, 0, 1, 1,
                                          "operating", 1, 1, 1),))
    product = ProductRegister(root / "product.sqlite3")
    labour = LabourRegister(root / "labour.sqlite3")
    if labour.total_event_count == 0:
        labour = labour_fixture(root / "labour.sqlite3")
    rights = LegalRightsRegister(root / "rights.sqlite3")
    if rights.total_event_count == 0:
        rights.bootstrap_admin(principal_id="rights-root", authority_ref="BOOTSTRAP:R", occurred_at=T)
        rights.grant_access(
            event_id="R-ACL", idempotency_key="R-ACL", principal_id="coordinator",
            permissions=["legal_rights:read", "legal_rights:write", "legal_rights:adjudicate"],
            actor_id="rights-root", authority_ref="POLICY:R", occurred_at=T,
        )
    financial = OperatingFinancialRegister(
        root / "operating-financial.sqlite3",
        sectors={"worker-1": "H", "employer-1": "NFC", "bank-1": "CB"},
    )
    if financial.total_event_count == 0:
        financial.bootstrap_admin(principal_id="financial-root", authority_ref="BOOTSTRAP:F", occurred_at=T)
        financial.grant_access(
            event_id="F-ACL", idempotency_key="F-ACL", principal_id="coordinator",
            permissions=["financial:read", "financial:write"], actor_id="financial-root",
            authority_ref="POLICY:F", occurred_at=T,
        )
        financial.open_deposit_account(
            event_id="OPEN-EMPLOYER", entity_id="employer-1", bank_id="bank-1",
            currency="LCU", account_ref="EMPLOYER-ACCOUNT-1", opening_balance="1000",
            evidence_ref="BANK-OPEN-EMPLOYER", actor_id="coordinator",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T, expected_revision=0,
        )
        financial.open_deposit_account(
            event_id="OPEN-WORKER", entity_id="worker-1", bank_id="bank-1",
            currency="LCU", account_ref="WORKER-ACCOUNT-1", opening_balance="10",
            evidence_ref="BANK-OPEN-WORKER", actor_id="coordinator",
            authority_ref="BANK-OPENING", effective_at=T, recorded_at=T, expected_revision=1,
        )
    return {
        "physical": make_physical_participant(physical, AUTH),
        "capital": make_capital_participant(capital, AUTH),
        "labour": labour,
        "product": make_product_participant(product, AUTH),
        "legal_rights": rights,
        "financial": financial,
    }


class OperatingWageCrossRegisterTests(unittest.TestCase):
    def test_verified_labour_wage_accrual_payment_commit_as_one_six_register_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labour = labour_fixture(root / "labour.sqlite3")
            delivery, contract, journal, events = build_wage_events(labour)
            participants = make_participants(root)
            coordinator = OperatingWageCoordinator(
                root / "coordinator.sqlite3", participants,
                require_authoritative_adapters=True,
            )
            operations = make_operations(delivery, contract, events)
            self.assertTrue(coordinator.submit(
                "TX-WAGE-1", "SCENARIO-WAGE-1", "CAUSE-WAGE-1", operations,
            ))
            self.assertEqual(coordinator.execute("TX-WAGE-1"), "COMMITTED")
            self.assertTrue(coordinator.is_visible("TX-WAGE-1"))

            labour_state, labour_version = labour.state("ENG-1", principal_id="coordinator")
            self.assertEqual(labour_state["status"], "SETTLED")
            self.assertEqual(labour_state["settlement_ref"], "WAGE-ACCRUAL-1")
            self.assertEqual(labour_version, 7)

            financial = participants["financial"]
            financial_state, financial_version = financial.claim_state(
                events[0].claim_id, principal_id="coordinator",
            )
            self.assertEqual(financial_state["status"], "PAID")
            self.assertEqual(financial_state["outstanding_amount"], "0.00")
            self.assertEqual(financial_state["event_ids"], ["WAGE-ACCRUAL-1", "WAGE-PAYMENT-1"])
            self.assertEqual(financial_version, 3)
            self.assertEqual(financial.deposit_balance("employer-1", "LCU", principal_id="coordinator")[0], D("960.00"))
            self.assertEqual(financial.deposit_balance("worker-1", "LCU", principal_id="coordinator")[0], D("50.00"))
            self.assertTrue(financial.verify())

            rights_state, rights_version = participants["legal_rights"].state(
                f"WAGE-RIGHT:{events[0].claim_id}", principal_id="coordinator",
            )
            self.assertEqual(rights_state["status"], "EXTINGUISHED")
            self.assertEqual(rights_state["extinguishment"]["settlement_event_id"], "WAGE-PAYMENT-1")
            self.assertEqual(D(rights_state["extinguishment"]["settled_amount"]), D("40.00"))
            self.assertEqual(rights_version, 1)

            group = coordinator.committed_event_group("TX-WAGE-1")
            self.assertEqual({event["register_id"] for event in group["events"]}, set(PARTICIPANTS))
            movements = movements_from_event_groups((group,))
            identities = sorted({movement.identity for movement in movements})
            durable_openings = {
                row.identity: (row.amount, row.evidence_ref)
                for row in participants["financial"].deposit_opening_positions(
                    period_index=1, principal_id="coordinator",
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
                    delta = sum((m.amount for m in movements
                                 if m.identity == identity and m.period_index == period), D("0"))
                    balance += delta
                    closings.append(ClosingPosition(
                        identity, period, balance, f"CLOSE:{identity.position_id}:{period}",
                    ))
            result = reconcile_periods(tuple(openings), movements, tuple(closings))
            self.assertEqual(coordinator.reconcile_event_stream(tuple(openings), tuple(closings)), result)
            self.assertEqual(result.mirror_group_count, 4)
            self.assertEqual(result.event_count, 8)
            self.assertTrue(all(m.identity.register_id == "financial" for m in movements))
            self.assertEqual(journal.outstanding[events[0].claim_id], D("0.00"))

            reopened = make_participants(root)
            restarted = OperatingWageCoordinator(
                root / "coordinator.sqlite3", reopened,
                require_authoritative_adapters=True,
            )
            self.assertTrue(restarted.is_visible("TX-WAGE-1"))
            self.assertEqual(restarted.committed_event_group("TX-WAGE-1"), group)
            replayed, replayed_version = reopened["financial"].claim_state(
                events[0].claim_id, principal_id="coordinator",
            )
            self.assertEqual(replayed["outstanding_amount"], "0.00")
            self.assertEqual(replayed_version, 3)
            self.assertEqual(reopened["financial"].deposit_balance("employer-1", "LCU", principal_id="coordinator")[0], D("960.00"))
            self.assertEqual(reopened["financial"].deposit_balance("worker-1", "LCU", principal_id="coordinator")[0], D("50.00"))
            self.assertTrue(reopened["financial"].verify())



    def test_partial_wage_payment_keeps_legal_claim_active_in_six_register_commit(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labour = labour_fixture(root / "labour.sqlite3")
            delivery, contract, journal, events = build_wage_events(labour, payment_amount="15")
            participants = make_participants(root)
            coordinator = OperatingWageCoordinator(
                root / "coordinator.sqlite3", participants,
                require_authoritative_adapters=True,
            )
            operations = make_operations(delivery, contract, events)
            self.assertEqual(operations["legal_rights"]["payload"]["event_type"], "right.created")
            self.assertTrue(coordinator.submit(
                "TX-WAGE-PARTIAL", "SCENARIO-WAGE-PARTIAL", "CAUSE-WAGE-PARTIAL", operations,
            ))
            self.assertEqual(coordinator.execute("TX-WAGE-PARTIAL"), "COMMITTED")
            claim_id = events[0].claim_id
            financial_state, financial_version = participants["financial"].claim_state(
                claim_id, principal_id="coordinator",
            )
            self.assertEqual(financial_state["status"], "OUTSTANDING")
            self.assertEqual(financial_state["outstanding_amount"], "25.00")
            self.assertEqual(financial_version, 3)
            self.assertEqual(participants["financial"].deposit_balance("employer-1", "LCU", principal_id="coordinator")[0], D("985.00"))
            self.assertEqual(participants["financial"].deposit_balance("worker-1", "LCU", principal_id="coordinator")[0], D("25.00"))
            legal_state, legal_version = participants["legal_rights"].state(
                f"WAGE-RIGHT:{claim_id}", principal_id="coordinator",
            )
            self.assertEqual(legal_state["status"], "ACTIVE")
            self.assertNotIn("extinguishment", legal_state)
            self.assertEqual(legal_version, 1)
            self.assertTrue(coordinator.is_visible("TX-WAGE-PARTIAL"))
            self.assertTrue(participants["financial"].verify())


    def test_legal_claim_principal_and_currency_must_match_financial_accrual(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labour = labour_fixture(root / "labour.sqlite3")
            delivery, contract, _, events = build_wage_events(labour)
            participants = make_participants(root)
            coordinator = OperatingWageCoordinator(
                root / "coordinator.sqlite3", participants,
                require_authoritative_adapters=True,
            )
            operations = make_operations(delivery, contract, events)
            operations["legal_rights"]["payload"]["payload"]["claim_amount"] = "39.99"
            from cross_register_coordinator import CoordinatorError
            with self.assertRaisesRegex(CoordinatorError, "principal or currency"):
                coordinator.submit("TX-WAGE-LEGAL-AMOUNT", "SCENARIO-LEGAL-AMOUNT",
                                   "CAUSE-LEGAL-AMOUNT", operations)
            operations = make_operations(delivery, contract, events)
            operations["legal_rights"]["payload"]["payload"]["currency"] = "USD"
            with self.assertRaisesRegex(CoordinatorError, "principal or currency"):
                coordinator.submit("TX-WAGE-LEGAL-CURRENCY", "SCENARIO-LEGAL-CURRENCY",
                                   "CAUSE-LEGAL-CURRENCY", operations)

    def test_fully_paid_wage_claim_cannot_remain_legally_active(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labour = labour_fixture(root / "labour.sqlite3")
            delivery, contract, _, events = build_wage_events(labour)
            participants = make_participants(root)
            coordinator = OperatingWageCoordinator(
                root / "coordinator.sqlite3", participants,
                require_authoritative_adapters=True,
            )
            operations = make_operations(delivery, contract, events)
            operations["legal_rights"]["payload"]["event_type"] = "right.created"
            from cross_register_coordinator import CoordinatorError
            with self.assertRaisesRegex(CoordinatorError, "legal wage claim state"):
                coordinator.submit("TX-WAGE-LIVE-RIGHT", "SCENARIO-WAGE-LIVE", "CAUSE-WAGE-LIVE", operations)
            self.assertIsNone(coordinator.state("TX-WAGE-LIVE-RIGHT"))

    def test_labour_change_after_submit_aborts_all_six_register_prepares(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labour = labour_fixture(root / "labour.sqlite3")
            delivery, contract, _, events = build_wage_events(labour)
            participants = make_participants(root)
            coordinator = OperatingWageCoordinator(
                root / "coordinator.sqlite3", participants,
                require_authoritative_adapters=True,
            )
            operations = make_operations(delivery, contract, events)
            coordinator.submit("TX-WAGE-STALE", "SCENARIO-WAGE-STALE", "CAUSE-WAGE-STALE", operations)

            append_labour(participants["labour"], "L7", "hours.corrected", {
                "corrects_event_id":"L5", "reason":"Corrected verified timesheet before prepare",
                "delta_hours":"-0.5",
            }, 6)
            with self.assertRaisesRegex(ValueError, "revision conflict"):
                coordinator.execute("TX-WAGE-STALE")
            self.assertEqual(coordinator.state("TX-WAGE-STALE"), "ABORTED")
            self.assertFalse(coordinator.is_visible("TX-WAGE-STALE"))
            labour_state, labour_version = participants["labour"].state(
                "ENG-1", principal_id="coordinator",
            )
            self.assertEqual(labour_version, 7)
            self.assertEqual(labour_state["status"], "VERIFIED")
            self.assertEqual(labour_state["delivered_hours"], "1.5")
            self.assertEqual(participants["financial"].claim_state(
                events[0].claim_id, principal_id="coordinator",
            ), (None, 2))
            self.assertEqual(participants["financial"].status("TX-WAGE-STALE"), None)
            self.assertEqual(participants["legal_rights"].status("TX-WAGE-STALE"), None)
            self.assertEqual(participants["physical"].status("TX-WAGE-STALE")["state"], "ABORTED")
            self.assertEqual(participants["capital"].status("TX-WAGE-STALE")["state"], "ABORTED")

    def test_coordinator_rejects_mismatched_labour_hours_before_prepare(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            labour = labour_fixture(root / "labour.sqlite3")
            delivery, contract, _, events = build_wage_events(labour)
            participants = make_participants(root)
            coordinator = OperatingWageCoordinator(
                root / "coordinator.sqlite3", participants,
                require_authoritative_adapters=True,
            )
            operations = make_operations(delivery, contract, events, labour_settled_hours="1.5")
            from cross_register_coordinator import CoordinatorError
            with self.assertRaisesRegex(CoordinatorError, "hours/reference differ"):
                coordinator.submit("TX-WAGE-BAD", "SCENARIO-WAGE-BAD", "CAUSE-WAGE-BAD", operations)
            self.assertIsNone(coordinator.state("TX-WAGE-BAD"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
