"""Cross-register wage transaction guard for the six-register coordinator.

This specializes the generic coordinator without changing its protocol or the
canonical GOLD-2A journal. It verifies that the financial wage batch, settled
labour aggregate, physical service flow, legal claim and product specification
describe the same delivered work before the six participants are prepared.
"""
from __future__ import annotations

from decimal import Decimal

from cross_register_coordinator import CrossRegisterCoordinator, CoordinatorError
from register_event_contract import normalize_event_envelope
from operating_financial_register import wage_stock_flow_movement_specs


D = Decimal


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise CoordinatorError(f"{field} must be trimmed non-empty text")
    return value


def _decimal(value, field):
    try:
        number = D(str(value))
    except Exception as exc:
        raise CoordinatorError(f"{field} must be a finite Decimal") from exc
    if not number.is_finite():
        raise CoordinatorError(f"{field} must be finite")
    return number


def _envelope(operations, register):
    try:
        return normalize_event_envelope(register, operations[register]["payload"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CoordinatorError(f"{register} wage transaction envelope is invalid") from exc


class OperatingWageCoordinator(CrossRegisterCoordinator):
    """Coordinator that rejects semantically mismatched six-register wage groups."""

    def submit(self, transaction_id, scenario_id, causation_id, operations):
        if not isinstance(operations, dict) or set(operations) != {
            "physical", "capital", "labour", "product", "legal_rights", "financial"
        }:
            raise CoordinatorError("wage transaction requires exactly six native register operations")

        financial = _envelope(operations, "financial")
        financial_payload = financial["payload"]
        if financial["event_type"] != "wage.event_group_committed":
            raise CoordinatorError("financial participant must commit a wage event group")
        claim_id = _text(financial_payload.get("claim_id"), "financial claim_id")
        financial_events = financial_payload.get("events")
        if not isinstance(financial_events, list) or not financial_events:
            raise CoordinatorError("financial wage group must contain events")
        accruals = [x for x in financial_events if isinstance(x, dict) and x.get("event_type") == "wage_accrual"]
        if len(accruals) != 1 or financial_events[0] is not accruals[0]:
            raise CoordinatorError("wage transaction must begin with exactly one accrual")
        accrual = accruals[0]
        if accrual.get("claim_id") != claim_id:
            raise CoordinatorError("financial accrual claim differs from financial stream claim")
        payment_events = financial_events[1:]
        if any(not isinstance(item, dict) or item.get("event_type") != "wage_payment"
               for item in payment_events):
            raise CoordinatorError("financial wage group may contain only one accrual followed by wage payments")
        accrual_amount = _decimal(accrual.get("amount"), "wage accrual amount")
        if accrual_amount <= 0:
            raise CoordinatorError("wage accrual amount must be positive")
        paid_amount = D("0")
        for payment in payment_events:
            payment_amount = _decimal(payment.get("amount"), "wage payment amount")
            if payment_amount <= 0:
                raise CoordinatorError("wage payment amount must be positive")
            if payment.get("claim_id") != claim_id:
                raise CoordinatorError("wage payment references a different claim")
            paid_amount += payment_amount
        if paid_amount > accrual_amount:
            raise CoordinatorError("wage payments exceed the original accrual")
        fully_paid = paid_amount == accrual_amount
        engagement_id = _text(accrual.get("engagement_id"), "engagement_id")
        worker = _text(accrual.get("worker_id"), "worker_id")
        employer = _text(accrual.get("employer_id"), "employer_id")
        delivered_hours = _decimal(accrual.get("delivered_hours"), "delivered_hours")
        delivery_event_id = _text(accrual.get("delivery_event_id"), "delivery_event_id")
        if accrual.get("causation_id") != delivery_event_id:
            raise CoordinatorError("wage accrual must reference its source labour delivery")
        if financial_payload.get("claim_id") != f"{engagement_id}:{delivery_event_id}":
            raise CoordinatorError("wage claim identity does not bind engagement and delivery event")
        labour = _envelope(operations, "labour")
        labour_payload = labour["payload"]
        if labour["event_type"] != "engagement.settled":
            raise CoordinatorError("wage accrual must atomically settle the source labour engagement")
        if operations["labour"].get("stream_id") != engagement_id:
            raise CoordinatorError("labour participant stream differs from wage engagement")
        if (labour_payload.get("settlement_ref") != accrual.get("event_id")
                or _decimal(labour_payload.get("settled_hours"), "settled_hours") != delivered_hours):
            raise CoordinatorError("labour settlement hours/reference differ from wage accrual")
        labour_register = self.participants["labour"]
        live_state, live_version = labour_register.state(
            engagement_id, principal_id=labour["actor_id"]
        )
        if live_version != accrual.get("labour_aggregate_version"):
            raise CoordinatorError("labour aggregate changed after wage verification")
        if not isinstance(live_state, dict) or any((
            live_state.get("status") != "VERIFIED",
            live_state.get("classification") != "paid",
            live_state.get("person_ref") != worker,
            live_state.get("activity_id") != employer,
            live_state.get("period") != accrual.get("period_label"),
            live_state.get("delivery_event_id") != delivery_event_id,
            live_state.get("delivery_evidence_ref") != accrual.get("delivery_evidence_ref"),
            live_state.get("verification_ref") != accrual.get("verification_ref"),
            _decimal(live_state.get("delivered_hours"), "labour delivered_hours") != delivered_hours,
        )):
            raise CoordinatorError("live verified labour state differs from wage accrual evidence")
        if operations["labour"].get("expected_revision") != live_version:
            raise CoordinatorError("labour operation expected_revision is stale")

        physical = _envelope(operations, "physical")
        if physical["event_type"] != "physical.flow_recorded":
            raise CoordinatorError("wage transaction must record the delivered labour service as a physical flow")
        physical_payload = physical["payload"]
        outflow, inflow = physical_payload.get("outflow"), physical_payload.get("inflow")
        if not isinstance(outflow, dict) or not isinstance(inflow, dict):
            raise CoordinatorError("physical labour service requires paired outflow/inflow endpoints")
        if (outflow.get("origin_node"), outflow.get("destination_node"),
            outflow.get("product_id"), outflow.get("grade_id"), outflow.get("unit"),
            outflow.get("period"), _decimal(outflow.get("quantity"), "physical quantity")) != (
            worker, employer, "labour_service", "verified", "h", accrual.get("period_label"), delivered_hours):
            raise CoordinatorError("physical service flow differs from verified labour delivery")
        if "stock_flow_movements" in physical:
            raise CoordinatorError("non-stockable labour service must not be represented as a physical stock position")
        physical_no_stock = _text(physical.get("no_stock_flow_effect"), "physical no_stock_flow_effect")
        if "non-stockable" not in physical_no_stock.lower() or "period flow" not in physical_no_stock.lower():
            raise CoordinatorError("physical labour service must be explicitly classified as a non-stockable period flow")

        product = _envelope(operations, "product")
        product_payload = product["payload"]
        if (product["event_type"], product_payload.get("product_id"), product_payload.get("grade_id"),
            product_payload.get("dimension"), product_payload.get("native_unit"),
            product_payload.get("stockability"), product_payload.get("time_basis")) != (
            "product_spec", "labour_service", "verified", "time", "h", "non_stockable", "period_flow"):
            raise CoordinatorError("product specification does not define the delivered labour service")

        rights = _envelope(operations, "legal_rights")
        rights_payload = rights["payload"]
        expected_right_type = "right.created_and_extinguished" if fully_paid else "right.created"
        if (rights["event_type"], rights_payload.get("holder_id"), rights_payload.get("obligor_id"),
            rights_payload.get("right_type"), rights_payload.get("scope"),
            rights_payload.get("legal_instrument_ref")) != (
            expected_right_type, worker, employer, "wage_claim", claim_id, accrual.get("contract_ref")):
            raise CoordinatorError("legal wage claim state does not match the wage payment state")
        required_evidence = {
            accrual.get("contract_ref"), accrual.get("contract_evidence_ref"),
            accrual.get("delivery_evidence_ref"), accrual.get("verification_ref"),
        }
        if fully_paid:
            last_payment = payment_events[-1]
            settlement_event_id = _text(rights_payload.get("settlement_event_id"), "settlement_event_id")
            settlement_evidence_ref = _text(rights_payload.get("settlement_evidence_ref"), "settlement_evidence_ref")
            settled_amount = _decimal(rights_payload.get("settled_amount"), "settled_amount")
            if (settlement_event_id != last_payment.get("event_id")
                    or settlement_evidence_ref != last_payment.get("evidence_ref")
                    or settled_amount != accrual_amount):
                raise CoordinatorError("legal extinguishment must reference the final full wage settlement")
            required_evidence.add(settlement_evidence_ref)
        elif any(field in rights_payload for field in (
            "settlement_event_id", "settlement_evidence_ref", "settled_amount"
        )):
            raise CoordinatorError("an unpaid or partially paid wage claim cannot be extinguished")
        if not required_evidence.issubset(set(rights_payload.get("evidence_refs", []))):
            raise CoordinatorError("legal wage claim omits one or more source evidence references")

        for register in ("physical", "capital", "labour", "product", "legal_rights"):
            participant_envelope = _envelope(operations, register)
            if ("stock_flow_movements" not in participant_envelope
                    and not isinstance(participant_envelope.get("no_stock_flow_effect"), str)):
                raise CoordinatorError(f"{register} participant must explicitly declare its stock-flow effect")

        if operations["financial"].get("stream_id") != f"wage:{claim_id}":
            raise CoordinatorError("financial participant stream does not bind the wage claim")
        if operations["financial"].get("expected_revision") != 0:
            raise CoordinatorError("initial wage accrual group must start at financial revision zero")
        expected_movements = wage_stock_flow_movement_specs(financial_events)
        if financial.get("stock_flow_movements") != expected_movements:
            raise CoordinatorError("financial movements do not match wage event postings")

        return super().submit(transaction_id, scenario_id, causation_id, operations)
