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


def _physical_movement_specs(outflow, inflow):
    flow_id = _text(outflow.get("flow_id"), "flow_id")
    origin = _text(outflow.get("origin_node"), "origin_node")
    destination = _text(outflow.get("destination_node"), "destination_node")
    product = _text(outflow.get("product_id"), "product_id")
    grade = _text(outflow.get("grade_id"), "grade_id")
    unit = _text(outflow.get("unit"), "unit")
    quantity = _decimal(outflow.get("quantity"), "quantity")
    common = {
        "register_id": "physical", "measure": "time", "unit": unit,
        "currency": "NA", "valuation_basis": "PHYSICAL",
        "instrument_id": f"{product}:{grade}",
    }
    return [
        {
            "movement_id": f"{flow_id}:OUT",
            "identity": common | {
                "position_id": f"{origin}:{product}:{grade}",
                "holder_id": origin, "issuer_id": destination,
            },
            "period_index": 1, "movement_class": "T", "amount": str(-quantity),
            "evidence_ref": _text(outflow.get("measurement_method"), "physical measurement_method"),
            "mirror_group_id": flow_id, "mirror_side": "sender", "mirror_policy": "opposite",
        },
        {
            "movement_id": f"{flow_id}:IN",
            "identity": common | {
                "position_id": f"{destination}:{product}:{grade}",
                "holder_id": destination, "issuer_id": origin,
            },
            "period_index": 1, "movement_class": "T", "amount": str(quantity),
            "evidence_ref": _text(outflow.get("evidence_ref", "TIMESHEET-VERIFIED"), "physical evidence_ref"),
            "mirror_group_id": flow_id, "mirror_side": "receiver", "mirror_policy": "opposite",
        },
    ]


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
            _decimal(outflow.get("quantity"), "physical quantity")) != (
            worker, employer, "labour_service", "verified", "h", delivered_hours):
            raise CoordinatorError("physical service flow differs from verified labour delivery")
        if operations["physical"]["payload"].get("stock_flow_movements") != _physical_movement_specs(outflow, inflow):
            raise CoordinatorError("physical stock-flow movements differ from delivered labour service")

        product = _envelope(operations, "product")
        product_payload = product["payload"]
        if (product["event_type"], product_payload.get("product_id"), product_payload.get("grade_id"),
            product_payload.get("dimension"), product_payload.get("native_unit"),
            product_payload.get("stockability"), product_payload.get("time_basis")) != (
            "product_spec", "labour_service", "verified", "time", "h", "non_stockable", "period_flow"):
            raise CoordinatorError("product specification does not define the delivered labour service")

        rights = _envelope(operations, "legal_rights")
        rights_payload = rights["payload"]
        if (rights["event_type"], rights_payload.get("holder_id"), rights_payload.get("obligor_id"),
            rights_payload.get("right_type"), rights_payload.get("scope"),
            rights_payload.get("legal_instrument_ref")) != (
            "right.created", worker, employer, "wage_claim", claim_id, accrual.get("contract_ref")):
            raise CoordinatorError("legal wage claim differs from verified worker, employer or contract")
        required_evidence = {
            accrual.get("contract_ref"), accrual.get("contract_evidence_ref"),
            accrual.get("delivery_evidence_ref"), accrual.get("verification_ref"),
        }
        if not required_evidence.issubset(set(rights_payload.get("evidence_refs", []))):
            raise CoordinatorError("legal wage claim omits one or more source evidence references")

        capital = _envelope(operations, "capital")
        if capital.get("no_stock_flow_effect") is None and "stock_flow_movements" not in capital:
            raise CoordinatorError("capital participant must explicitly declare its no-stock-flow effect for this wage transaction")

        if operations["financial"].get("stream_id") != f"wage:{claim_id}":
            raise CoordinatorError("financial participant stream does not bind the wage claim")
        if operations["financial"].get("expected_revision") != 0:
            raise CoordinatorError("initial wage accrual group must start at financial revision zero")
        expected_movements = wage_stock_flow_movement_specs(financial_events)
        if financial.get("stock_flow_movements") != expected_movements:
            raise CoordinatorError("financial movements do not match wage event postings")

        return super().submit(transaction_id, scenario_id, causation_id, operations)
