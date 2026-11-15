"""Evidence-linked fixed-asset ledger used by the IO productive-capex vertical slice.

A paid investment order is not productive capacity: payment, physical delivery
and commissioning are separate, identity-preserving events. The IO adapter
reserves supplier inventory, settles buyer/supplier cash and posts delivered
units to capital formation. This ledger owns cohort valuation and lifecycle.
All amounts and physical quantities use Decimal; missing evidence fails closed.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Mapping

D = Decimal
ZERO = D("0")


class FixedAssetError(ValueError):
    """Invalid fixed-asset lifecycle, evidence or accounting transition."""


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise FixedAssetError(f"{field} must be trimmed non-empty text")
    return value


def _number(value, field, *, positive=False):
    if isinstance(value, bool):
        raise FixedAssetError(f"{field} must be a finite Decimal")
    try:
        result = D(str(value))
    except Exception as exc:
        raise FixedAssetError(f"{field} must be a finite Decimal") from exc
    if not result.is_finite() or result < 0 or (positive and result <= 0):
        raise FixedAssetError(f"{field} must be finite and " + ("positive" if positive else "non-negative"))
    return result


def _period(value, field):
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise FixedAssetError(f"{field} must be a positive integer period")
    return value


@dataclass(frozen=True)
class InvestmentOrder:
    order_id: str
    credit_event_id: str
    payment_event_id: str
    borrower_id: str
    supplier_id: str
    asset_type: str
    quantity: D
    unit_cost: D
    order_period: int
    delivery_period: int
    commissioning_period: int
    useful_life_periods: int
    residual_value_per_unit: D
    service_capacity_per_unit: D

    def __post_init__(self):
        for name in ("order_id", "credit_event_id", "payment_event_id", "borrower_id",
                     "supplier_id", "asset_type"):
            _text(getattr(self, name), name)
        if self.borrower_id == self.supplier_id:
            raise FixedAssetError("asset buyer and supplier must be distinct")
        for name in ("quantity", "unit_cost", "residual_value_per_unit",
                     "service_capacity_per_unit"):
            object.__setattr__(self, name, _number(getattr(self, name), name,
                                                   positive=name in {"quantity", "unit_cost", "service_capacity_per_unit"}))
        for name in ("order_period", "delivery_period", "commissioning_period",
                     "useful_life_periods"):
            _period(getattr(self, name), name)
        if self.delivery_period < self.order_period:
            raise FixedAssetError("delivery cannot precede the order")
        if self.commissioning_period < self.delivery_period:
            raise FixedAssetError("commissioning cannot precede physical delivery")
        if self.useful_life_periods < 1:
            raise FixedAssetError("useful_life_periods must be positive")
        if self.residual_value_per_unit > self.unit_cost:
            raise FixedAssetError("residual value cannot exceed acquisition cost")

    @property
    def acquisition_cost(self):
        return self.quantity * self.unit_cost

    @property
    def paid_amount(self):
        return self.acquisition_cost


@dataclass(frozen=True)
class AssetEvent:
    event_id: str
    order_id: str
    event_type: str
    period: int
    quantity: D
    evidence_ref: str


@dataclass(frozen=True)
class AssetCohort:
    cohort_id: str
    order_id: str
    owner_id: str
    asset_type: str
    quantity: D
    unit_cost: D
    residual_value_per_unit: D
    service_capacity_per_unit: D
    commissioning_period: int
    useful_life_periods: int
    retired_quantity: D = ZERO
    retirement_history: tuple[tuple[int, D], ...] = ()

    @property
    def active_quantity(self):
        return self.quantity - self.retired_quantity

    def active_quantity_at(self, period):
        _period(period, "period")
        retired_by_period = sum(
            (quantity for retired_period, quantity in self.retirement_history
             if retired_period <= period), ZERO
        )
        return self.quantity - retired_by_period

    def carrying_value(self, period):
        _period(period, "period")
        if period < self.commissioning_period:
            return ZERO
        elapsed = min(period - self.commissioning_period, self.useful_life_periods)
        depreciable = self.unit_cost - self.residual_value_per_unit
        depreciation_per_unit = depreciable / D(self.useful_life_periods)
        per_unit = max(self.residual_value_per_unit,
                       self.unit_cost - depreciation_per_unit * D(elapsed))
        return self.active_quantity_at(period) * per_unit

    def productive_capacity(self, period):
        _period(period, "period")
        if period < self.commissioning_period:
            return ZERO
        if period >= self.commissioning_period + self.useful_life_periods:
            return ZERO
        return self.active_quantity_at(period) * self.service_capacity_per_unit


class FixedAssetLedger:
    """Append-only investment lifecycle with exact cash/physical evidence links."""

    def __init__(self):
        self.orders: dict[str, InvestmentOrder] = {}
        self.cohorts: dict[str, AssetCohort] = {}
        self.events: list[AssetEvent] = []
        self._event_ids: set[str] = set()
        self._delivered: dict[str, D] = {}

    def place_paid_order(self, order: InvestmentOrder, *, payment_amount,
                         payment_currency: str, order_currency: str,
                         payment_evidence_ref: str):
        if not isinstance(order, InvestmentOrder):
            raise FixedAssetError("order must be an InvestmentOrder")
        if order.order_id in self.orders:
            raise FixedAssetError("duplicate investment order")
        payment_currency = _text(payment_currency, "payment_currency")
        order_currency = _text(order_currency, "order_currency")
        if payment_currency != order_currency:
            raise FixedAssetError("payment and order currencies differ")
        paid = _number(payment_amount, "payment_amount")
        if paid != order.acquisition_cost:
            raise FixedAssetError("investment order must be fully paid before recognition")
        _text(payment_evidence_ref, "payment_evidence_ref")
        if order.payment_event_id in self._event_ids:
            raise FixedAssetError("duplicate payment event identity")
        self.orders[order.order_id] = order
        self._event_ids.add(order.payment_event_id)
        self.events.append(AssetEvent(order.payment_event_id, order.order_id,
                                      "capex_paid", order.order_period,
                                      order.quantity, payment_evidence_ref))
        self._delivered[order.order_id] = ZERO

    def deliver(self, *, event_id, order_id, quantity, period, evidence_ref):
        event_id = _text(event_id, "event_id")
        evidence_ref = _text(evidence_ref, "evidence_ref")
        period = _period(period, "period")
        quantity = _number(quantity, "quantity", positive=True)
        if event_id in self._event_ids:
            raise FixedAssetError("duplicate asset event identity")
        if order_id not in self.orders:
            raise FixedAssetError("delivery references an unknown paid order")
        order = self.orders[order_id]
        if period != order.delivery_period:
            raise FixedAssetError("delivery period differs from contracted delivery period")
        if self._delivered[order_id] + quantity > order.quantity:
            raise FixedAssetError("physical deliveries exceed paid order quantity")
        self._delivered[order_id] += quantity
        self._event_ids.add(event_id)
        self.events.append(AssetEvent(event_id, order_id, "asset_delivered",
                                      period, quantity, evidence_ref))
        # Each evidenced delivery becomes its own physical cohort. A partial
        # shipment can therefore enter service on the contracted commissioning
        # date without waiting for unrelated remaining units.
        cohort_id = f"cohort:{order_id}:{event_id}"
        self.cohorts[cohort_id] = AssetCohort(
            cohort_id, order.order_id, order.borrower_id, order.asset_type,
            quantity, order.unit_cost, order.residual_value_per_unit,
            order.service_capacity_per_unit, order.commissioning_period,
            order.useful_life_periods,
        )
        return self._delivered[order_id]

    def retire(self, *, event_id, cohort_id, quantity, period, evidence_ref):
        event_id = _text(event_id, "event_id")
        evidence_ref = _text(evidence_ref, "evidence_ref")
        period = _period(period, "period")
        quantity = _number(quantity, "quantity", positive=True)
        if event_id in self._event_ids:
            raise FixedAssetError("duplicate asset event identity")
        if cohort_id not in self.cohorts:
            raise FixedAssetError("retirement references an unknown commissioned cohort")
        cohort = self.cohorts[cohort_id]
        if period < cohort.commissioning_period:
            raise FixedAssetError("asset cannot retire before commissioning")
        if cohort.retirement_history and period < cohort.retirement_history[-1][0]:
            raise FixedAssetError("retirement effective periods cannot move backwards")
        if quantity > cohort.active_quantity:
            raise FixedAssetError("retirement exceeds active physical quantity")
        self.cohorts[cohort_id] = AssetCohort(
            cohort.cohort_id, cohort.order_id, cohort.owner_id, cohort.asset_type,
            cohort.quantity, cohort.unit_cost, cohort.residual_value_per_unit,
            cohort.service_capacity_per_unit, cohort.commissioning_period,
            cohort.useful_life_periods, cohort.retired_quantity + quantity,
            cohort.retirement_history + ((period, quantity),),
        )
        self._event_ids.add(event_id)
        self.events.append(AssetEvent(event_id, cohort.order_id, "asset_retired",
                                      period, quantity, evidence_ref))

    def commissioned_capacity(self, owner_id, period):
        _text(owner_id, "owner_id")
        return sum((cohort.productive_capacity(period)
                    for cohort in self.cohorts.values()
                    if cohort.owner_id == owner_id), ZERO)

    def carrying_value(self, owner_id, period):
        _text(owner_id, "owner_id")
        return sum((cohort.carrying_value(period)
                    for cohort in self.cohorts.values()
                    if cohort.owner_id == owner_id), ZERO)

    def work_in_progress_value(self, owner_id, period):
        """Paid supplier advances plus delivered assets not yet commissioned."""
        _text(owner_id, "owner_id")
        _period(period, "period")
        total = ZERO
        for order_id, order in self.orders.items():
            if order.borrower_id != owner_id:
                continue
            delivered = self._delivered[order_id]
            undelivered = order.quantity - delivered
            not_yet_commissioned = delivered if period < order.commissioning_period else ZERO
            total += (undelivered + not_yet_commissioned) * order.unit_cost
        return total

    def physical_reconciliation(self, order_id):
        if order_id not in self.orders:
            raise FixedAssetError("unknown investment order")
        return {
            "ordered": self.orders[order_id].quantity,
            "delivered": self._delivered[order_id],
            "undelivered": self.orders[order_id].quantity - self._delivered[order_id],
        }
