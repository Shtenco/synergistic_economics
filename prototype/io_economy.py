"""General input-output network prototype for SYNERGY (standard library only).

This is a transparent, deterministic research model, not a calibrated forecast.
Money is Decimal; physical quantities are Decimal; spot markets clear by product.
"""
from dataclasses import dataclass, field
from decimal import Decimal as D, ROUND_DOWN, ROUND_HALF_UP
from hashlib import sha256
import argparse
import json
from pathlib import Path

from firm_fixed_assets import FixedAssetError, FixedAssetLedger, InvestmentOrder

ZERO = D("0")
QTY = D("0.00000001")
CENT = D("0.01")

def dec(value):
    return D(str(value))

def qty(value):
    return dec(value).quantize(QTY, rounding=ROUND_HALF_UP)

def qty_floor(value):
    """Round physical quantities down so execution cannot consume unavailable stock."""
    return dec(value).quantize(QTY, rounding=ROUND_DOWN)

def _scale_allocations(allocations, total):
    """Scale non-negative physical allocations without negative residual plugs."""
    total = dec(total)
    if not total.is_finite() or total < 0:
        raise EconomyError("allocation target must be finite and non-negative")
    source_total = sum(allocations.values(), ZERO)
    if any(not value.is_finite() or value < 0 for value in allocations.values()):
        raise EconomyError("source allocations must be finite and non-negative")
    if total > source_total:
        raise EconomyError("allocation target exceeds source quantity")
    if source_total == 0:
        if total != 0:
            raise EconomyError("cannot allocate a positive target from zero source quantity")
        return {key: ZERO for key in allocations}
    scaled = {
        key: qty_floor(value * total / source_total)
        for key, value in allocations.items()
    }
    residual = total - sum(scaled.values(), ZERO)
    # Assign the sub-quantum residual to the largest remaining capacity first.
    # This prevents a tiny final seller/buyer from becoming negative and then
    # disappearing from settlement when positive rows are filtered.
    for key in sorted(allocations, key=lambda item: (-allocations[item], item)):
        if residual <= 0:
            break
        capacity = allocations[key] - scaled[key]
        addition = min(capacity, residual)
        scaled[key] += addition
        residual -= addition
    if residual != 0 or any(value < 0 or value > allocations[key] for key, value in scaled.items()):
        raise EconomyError("deterministic allocation residual could not be assigned within source capacities")
    return scaled

def cash(value):
    return dec(value).quantize(CENT, rounding=ROUND_HALF_UP)

class EconomyError(ValueError):
    pass

@dataclass(frozen=True)
class Product:
    product_id: str
    unit: str
    base_price: D
    import_price: D
    import_capacity: D
    demand_weight: D = D("1")

@dataclass(frozen=True)
class FirmConfig:
    firm_id: str
    output_product: str
    recipe: dict
    labour_per_unit: D
    labour_capacity: D
    output_capacity: D
    wage_per_labour: D
    initial_cash: D
    initial_inventory: dict
    domestic_ask_markup: D = D("0.90")
    household_labour_shares: dict = field(default_factory=dict)

@dataclass(frozen=True)
class HouseholdConfig:
    household_id: str
    initial_cash: D
    basket: dict
    consumption_propensity: D = D("0.35")
    labour_supply_hours: D = D("25")

@dataclass(frozen=True)
class HouseholdIncomePayment:
    payment_id: str
    source_type: str
    payer_kind: str
    payer_id: str
    recipient_id: str
    amount: D
    period: int
    evidence_ref: str

    def __post_init__(self):
        try:
            amount = dec(self.amount)
        except Exception as exc:
            raise EconomyError("income payment amount must be a finite positive Decimal") from exc
        if not amount.is_finite() or amount <= 0:
            raise EconomyError("income payment amount must be a finite positive Decimal")
        object.__setattr__(self, "amount", amount)

@dataclass
class FirmState:
    config: FirmConfig
    cash: D
    inventory: dict
    production: D = ZERO
    wages_paid: D = ZERO
    intermediate_consumption_value: D = ZERO
    sales_revenue: D = ZERO

@dataclass
class HouseholdState:
    config: HouseholdConfig
    cash: D
    consumption: dict = field(default_factory=dict)
    wage_income: D = ZERO
    period_wage_income: D = ZERO
    period_labour_hours: D = ZERO
    period_unemployment_hours: D = ZERO
    cumulative_unemployment_hours: D = ZERO
    period_income_by_source: dict = field(default_factory=dict)
    cumulative_income_by_source: dict = field(default_factory=dict)
    expenditure: D = ZERO

@dataclass
class MarketOrder:
    buyer_id: str
    product_id: str
    quantity: D
    buyer_kind: str

@dataclass
class PeriodResult:
    period: int
    prices: dict
    production: dict
    imports: dict
    intermediate_consumption: dict
    household_consumption: dict
    closing_inventory: dict
    shortages: dict
    wages: D
    household_wage_income: dict
    household_labour_hours: dict
    household_labour_supply_hours: dict
    household_unemployment_hours: dict
    household_employment_rate: dict
    household_income_by_source: dict
    household_total_income: dict
    household_income_payment_arrears: dict
    capital_formation: dict
    firm_production_by_firm: dict
    firm_commissioned_capacity_by_firm: dict
    household_expenditure: D
    import_expenditure: D
    gross_value_added_proxy: D
    system_cash: D
    cash_error: D
    physical_balance_error: dict
    event_digest: str

class InputOutputEconomy:
    """Multi-product, multi-firm economy with product-level spot clearing."""

    def __init__(self, products=None, firms=None, households=None,
                 price_adjustment=D("0.18"), max_price_change=D("0.35"),
                 household_demand_multiplier=D("1"),
                 income_payments=None, income_source_funds=None):
        self.products = products or self.default_products()
        self.firm_configs = firms or self.default_firms()
        self.household_configs = households or self.default_households()
        self._validate_config()
        self.product_by_id = {p.product_id: p for p in self.products}
        self.firms = {
            f.firm_id: FirmState(f, f.initial_cash, dict(f.initial_inventory))
            for f in self.firm_configs
        }
        self.households = {
            h.household_id: HouseholdState(h, h.initial_cash)
            for h in self.household_configs
        }
        self.income_source_cash = {key: dec(value) for key, value in (income_source_funds or {}).items()}
        if any(not isinstance(key, str) or not key or not value.is_finite() or value < 0
               for key, value in self.income_source_cash.items()):
            raise EconomyError("income source funds require named non-negative finite opening balances")
        self.income_payments = list(income_payments or [])
        self.income_payment_arrears = {}
        self._validate_income_payments()
        self.fixed_asset_ledger = FixedAssetLedger()
        self.capex_supplier_reservations = {}
        self.capex_orders = {}
        self.current_period = 0
        self.prices = {p.product_id: p.base_price for p in self.products}
        self.price_adjustment = dec(price_adjustment)
        self.max_price_change = dec(max_price_change)
        self.household_demand_multiplier = dec(household_demand_multiplier)
        if (not self.price_adjustment.is_finite() or self.price_adjustment < 0
                or not self.max_price_change.is_finite()
                or not ZERO <= self.max_price_change < D("1")
                or not self.household_demand_multiplier.is_finite()
                or self.household_demand_multiplier < 0):
            raise EconomyError("invalid price adjustment or demand multiplier")
        self.import_cash = ZERO
        self.initial_cash = self._system_cash()
        self.period_results = []
        self.events = []
        self._event_keys = set()

    @staticmethod
    def default_products():
        return [
            Product("grain", "tonne", D("100"), D("128"), D("18"), D("1.0")),
            Product("energy", "MWh", D("70"), D("105"), D("24"), D("1.0")),
            Product("metals", "tonne", D("180"), D("225"), D("12"), D("0.7")),
            Product("machinery", "unit", D("520"), D("650"), D("4"), D("0.45")),
            Product("logistics", "service_unit", D("45"), D("62"), D("16"), D("0.8")),
            Product("food", "basket_unit", D("165"), D("210"), D("8"), D("1.0")),
            Product("care", "care_unit", D("90"), D("115"), D("4"), D("0.9")),
        ]

    @staticmethod
    def default_firms():
        return [
            FirmConfig("farm-north", "grain", {"energy": D("0.12"), "logistics": D("0.08")}, D("0.40"), D("12"), D("24"), D("8"), D("5200"), {"grain": D("7"), "energy": D("1"), "logistics": D("1")}, household_labour_shares={"household-1": D("0.8"), "household-2": D("0.2")}),
            FirmConfig("farm-south", "grain", {"energy": D("0.15"), "logistics": D("0.10")}, D("0.42"), D("10"), D("20"), D("8"), D("4100"), {"grain": D("5"), "energy": D("1"), "logistics": D("1")}, household_labour_shares={"household-2": D("0.7"), "household-3": D("0.3")}),
            FirmConfig("power-east", "energy", {"metals": D("0.025"), "machinery": D("0.006")}, D("0.18"), D("15"), D("28"), D("9"), D("6200"), {"energy": D("5"), "metals": D("0.5"), "machinery": D("0.1")}, household_labour_shares={"household-1": D("0.6"), "household-2": D("0.4")}),
            FirmConfig("power-west", "energy", {"metals": D("0.03"), "machinery": D("0.005")}, D("0.20"), D("12"), D("22"), D("9"), D("5000"), {"energy": D("4"), "metals": D("0.5"), "machinery": D("0.1")}, household_labour_shares={"household-2": D("0.4"), "household-3": D("0.6")}),
            FirmConfig("mine-central", "metals", {"energy": D("0.20"), "machinery": D("0.012"), "logistics": D("0.04")}, D("0.35"), D("11"), D("18"), D("10"), D("6000"), {"metals": D("3"), "energy": D("2"), "machinery": D("0.2"), "logistics": D("0.5")}, household_labour_shares={"household-1": D("0.2"), "household-3": D("0.8")}),
            FirmConfig("machine-works", "machinery", {"metals": D("0.55"), "energy": D("0.30"), "logistics": D("0.10")}, D("1.20"), D("8"), D("7"), D("14"), D("8500"), {"machinery": D("1"), "metals": D("2"), "energy": D("2"), "logistics": D("0.5")}, household_labour_shares={"household-1": D("0.5"), "household-2": D("0.5")}),
            FirmConfig("transport-coop", "logistics", {"energy": D("0.28"), "machinery": D("0.018")}, D("0.55"), D("14"), D("22"), D("9"), D("4800"), {"logistics": D("3"), "energy": D("2"), "machinery": D("0.2")}, household_labour_shares={"household-2": D("0.7"), "household-3": D("0.3")}),
            FirmConfig("food-coop", "food", {"grain": D("0.72"), "energy": D("0.10"), "logistics": D("0.12")}, D("0.62"), D("12"), D("18"), D("9"), D("5600"), {"food": D("2"), "grain": D("2"), "energy": D("1"), "logistics": D("0.5")}, household_labour_shares={"household-1": D("0.3"), "household-2": D("0.7")}),
            FirmConfig("care-network", "care", {"food": D("0.025"), "energy": D("0.08"), "logistics": D("0.04")}, D("1.10"), D("9"), D("12"), D("11"), D("6300"), {"care": D("1"), "food": D("0.2"), "energy": D("1"), "logistics": D("0.2")}, household_labour_shares={"household-1": D("0.2"), "household-3": D("0.8")}),
        ]

    @staticmethod
    def default_households():
        return [
            HouseholdConfig("household-1", D("4200"), {"food": D("5.0"), "energy": D("2.0"), "care": D("1.0"), "logistics": D("0.7")}, D("0.34")),
            HouseholdConfig("household-2", D("3600"), {"food": D("4.0"), "energy": D("1.7"), "care": D("0.8"), "logistics": D("0.6")}, D("0.32")),
            HouseholdConfig("household-3", D("3100"), {"food": D("3.5"), "energy": D("1.5"), "care": D("0.6"), "logistics": D("0.5")}, D("0.30")),
        ]

    def _validate_config(self):
        product_ids = [p.product_id for p in self.products]
        firm_ids = [f.firm_id for f in self.firm_configs]
        household_ids = [h.household_id for h in self.household_configs]
        if len(set(product_ids)) != len(product_ids) or not product_ids:
            raise EconomyError("product ids must be non-empty and unique")
        if len(set(firm_ids)) != len(firm_ids) or not firm_ids:
            raise EconomyError("firm ids must be non-empty and unique")
        if len(set(household_ids)) != len(household_ids) or not household_ids:
            raise EconomyError("household ids must be non-empty and unique")
        known = set(product_ids)
        for p in self.products:
            values = (p.base_price, p.import_price, p.import_capacity, p.demand_weight)
            if (any(not value.is_finite() for value in values)
                    or p.base_price <= 0 or p.import_price <= 0
                    or p.import_capacity < 0 or p.demand_weight < 0):
                raise EconomyError("invalid product price, capacity or demand weight")
        for f in self.firm_configs:
            if f.output_product not in known or set(f.recipe) - known or set(f.initial_inventory) - known:
                raise EconomyError("firm references unknown product")
            if f.output_product in f.recipe:
                raise EconomyError("self-input recipes are not supported in this prototype")
            if any(v <= 0 for v in f.recipe.values()) or any(v < 0 for v in f.initial_inventory.values()):
                raise EconomyError("recipe coefficients must be positive and stocks non-negative")
            numeric_values = (f.labour_per_unit, f.labour_capacity, f.output_capacity,
                              f.wage_per_labour, f.initial_cash, f.domestic_ask_markup,
                              *f.recipe.values(), *f.initial_inventory.values())
            if any(not value.is_finite() for value in numeric_values):
                raise EconomyError("non-finite firm parameter")
            if (min(f.labour_per_unit, f.labour_capacity, f.output_capacity,
                    f.wage_per_labour, f.initial_cash) < 0
                    or f.domestic_ask_markup <= 0):
                raise EconomyError("negative firm parameter or non-positive ask markup")
            if f.labour_per_unit <= 0:
                raise EconomyError("labour_per_unit must be positive")
        household_ids_set = set(household_ids)
        for f in self.firm_configs:
            shares = f.household_labour_shares
            if shares:
                if set(shares) - household_ids_set:
                    raise EconomyError("firm labour allocation references unknown household")
                if any(not value.is_finite() or value < 0 for value in shares.values()):
                    raise EconomyError("firm labour shares must be finite and non-negative")
                if sum(shares.values(), ZERO) != D("1"):
                    raise EconomyError("explicit firm labour shares must sum exactly to one")
        for h in self.household_configs:
            if set(h.basket) - known or any(not v.is_finite() or v < 0 for v in h.basket.values()):
                raise EconomyError("invalid household basket")
            if (not h.initial_cash.is_finite() or not h.consumption_propensity.is_finite()
                    or not h.labour_supply_hours.is_finite()
                    or h.initial_cash < 0 or h.labour_supply_hours < 0
                    or not D("0") <= h.consumption_propensity <= D("1")):
                raise EconomyError("invalid household budget or labour supply")

    def _labour_shares(self, firm_config):
        if firm_config.household_labour_shares:
            return dict(sorted(firm_config.household_labour_shares.items()))
        # Backwards-compatible fallback for custom legacy fixtures only. The
        # canonical default economy uses explicit firm-to-household allocations.
        household_ids = sorted(self.households)
        if not household_ids:
            return {}
        each = D("1") / D(len(household_ids))
        shares = {key: each for key in household_ids}
        shares[household_ids[-1]] += D("1") - sum(shares.values(), ZERO)
        return shares

    def _validate_income_payments(self):
        allowed_sources = {"dividend", "interest", "pension", "public_transfer", "rental", "self_employment"}
        ids = set()
        for payment in self.income_payments:
            if not isinstance(payment, HouseholdIncomePayment):
                raise EconomyError("income payments must be HouseholdIncomePayment records")
            if (not payment.payment_id or payment.payment_id in ids
                    or payment.source_type not in allowed_sources
                    or payment.recipient_id not in self.households
                    or not payment.payer_id or not payment.evidence_ref
                    or payment.payer_kind not in {"firm", "income_fund"}
                    or not payment.amount.is_finite() or payment.amount <= 0
                    or not isinstance(payment.period, int) or isinstance(payment.period, bool)
                    or payment.period < 1):
                raise EconomyError("invalid or duplicate household income payment")
            if payment.payer_kind == "firm" and payment.payer_id not in self.firms:
                raise EconomyError("income payment references an unknown firm payer")
            if payment.payer_kind == "income_fund" and payment.payer_id not in self.income_source_cash:
                raise EconomyError("income payment references an unfunded income source account")
            ids.add(payment.payment_id)

    def _settle_household_income(self, period):
        due_rows = [p for p in self.income_payments if p.period == period]
        due_rows += [p for p in self.income_payments if self.income_payment_arrears.get(p.payment_id, ZERO) > 0]
        seen = set()
        for payment in sorted(due_rows, key=lambda item: (item.period, item.payment_id)):
            if payment.payment_id in seen:
                continue
            seen.add(payment.payment_id)
            due = payment.amount if payment.period == period else ZERO
            due += self.income_payment_arrears.get(payment.payment_id, ZERO)
            if payment.payer_kind == "firm":
                payer = self.firms[payment.payer_id]
                available = payer.cash
            else:
                available = self.income_source_cash[payment.payer_id]
            paid = cash(min(available, due))
            if paid > 0:
                if payment.payer_kind == "firm":
                    payer.cash -= paid
                else:
                    self.income_source_cash[payment.payer_id] -= paid
                household = self.households[payment.recipient_id]
                household.cash += paid
                household.period_income_by_source[payment.source_type] = (
                    household.period_income_by_source.get(payment.source_type, ZERO) + paid
                )
                household.cumulative_income_by_source[payment.source_type] = (
                    household.cumulative_income_by_source.get(payment.source_type, ZERO) + paid
                )
            arrears = max(ZERO, due - paid)
            self.income_payment_arrears[payment.payment_id] = arrears
            self._event(f"p{period}:income:{payment.payment_id}", "household_income_payment", {
                "payment_id": payment.payment_id, "source_type": payment.source_type,
                "payer_kind": payment.payer_kind, "payer_id": payment.payer_id,
                "recipient_id": payment.recipient_id, "due": str(due),
                "paid": str(paid), "arrears": str(arrears),
                "evidence_ref": payment.evidence_ref,
            })

    def _system_cash(self):
        return (sum((f.cash for f in self.firms.values()), ZERO)
                + sum((h.cash for h in self.households.values()), ZERO)
                + sum(self.income_source_cash.values(), ZERO) + self.import_cash)

    def _event(self, key, kind, payload):
        if key in self._event_keys:
            raise EconomyError("duplicate event key")
        self._event_keys.add(key)
        row = {"key": key, "kind": kind, "payload": payload}
        self.events.append(row)

    def place_capex_order(self, *, order_id, credit_event_id, payment_event_id,
                          buyer_id, supplier_id, asset_type, quantity, unit_cost,
                          order_period, delivery_period, commissioning_period,
                          useful_life_periods, residual_value_per_unit,
                          service_capacity_per_unit, currency="LCU",
                          payment_evidence_ref):
        """Pay a machinery supplier, reserve physical stock, and register an asset order."""
        if buyer_id not in self.firms or supplier_id not in self.firms:
            raise EconomyError("capex buyer and supplier must be existing firms")
        buyer, supplier = self.firms[buyer_id], self.firms[supplier_id]
        if buyer_id == supplier_id or supplier.config.output_product != asset_type:
            raise EconomyError("capex supplier must be a distinct producer of the ordered asset product")
        try:
            order = InvestmentOrder(
                order_id, credit_event_id, payment_event_id, buyer_id, supplier_id,
                asset_type, dec(quantity), dec(unit_cost), order_period, delivery_period,
                commissioning_period, useful_life_periods, dec(residual_value_per_unit),
                dec(service_capacity_per_unit),
            )
        except (FixedAssetError, ArithmeticError, ValueError) as exc:
            raise EconomyError(str(exc)) from exc
        if order.order_period != self.current_period + 1:
            raise EconomyError("capex orders must be paid in the next unstarted IO period")
        payment_event_key = f"p{order.order_period}:capex-payment:{order.order_id}"
        if payment_event_key in self._event_keys:
            raise EconomyError("capex payment event key already exists")
        acquisition_cost = order.acquisition_cost
        payment = cash(acquisition_cost)
        if payment != acquisition_cost:
            raise EconomyError("capex acquisition cost must be exactly representable in currency cents")
        reserved_key = (supplier_id, asset_type)
        already_reserved = self.capex_supplier_reservations.get(reserved_key, ZERO)
        available = supplier.inventory.get(asset_type, ZERO) - already_reserved
        if order.quantity > available:
            raise EconomyError("supplier lacks unreserved physical asset inventory")
        if buyer.cash < payment:
            raise EconomyError("capex buyer cannot fully settle the investment order")
        try:
            self.fixed_asset_ledger.place_paid_order(
                order, payment_amount=payment, payment_currency=currency,
                order_currency=currency, payment_evidence_ref=payment_evidence_ref,
            )
        except FixedAssetError as exc:
            raise EconomyError(str(exc)) from exc
        buyer.cash -= payment
        supplier.cash += payment
        self.capex_supplier_reservations[reserved_key] = already_reserved + order.quantity
        self.capex_orders[order.order_id] = order
        self._event(f"p{order_period}:capex-payment:{order.order_id}", "capex_payment", {
            "order_id": order.order_id, "credit_event_id": order.credit_event_id,
            "payment_event_id": order.payment_event_id, "buyer_id": buyer_id,
            "supplier_id": supplier_id, "asset_type": asset_type,
            "quantity": str(order.quantity), "unit_cost": str(order.unit_cost),
            "amount": str(payment), "evidence_ref": payment_evidence_ref,
        })
        return order

    def _commission_capex_deliveries(self, period, capital_formation):
        for order in sorted(self.capex_orders.values(), key=lambda item: item.order_id):
            if order.delivery_period != period:
                continue
            supplier = self.firms[order.supplier_id]
            if supplier.inventory.get(order.asset_type, ZERO) < order.quantity:
                raise EconomyError("reserved capex goods disappeared before physical delivery")
            event_id = f"delivery:{order.order_id}"
            delivery_event_key = f"p{period}:capex-delivery:{order.order_id}"
            if delivery_event_key in self._event_keys:
                raise EconomyError("capex delivery event key already exists")
            try:
                self.fixed_asset_ledger.deliver(
                    event_id=event_id, order_id=order.order_id,
                    quantity=order.quantity, period=period,
                    evidence_ref=f"goods-receipt:{order.order_id}",
                )
            except FixedAssetError as exc:
                raise EconomyError(str(exc)) from exc
            supplier.inventory[order.asset_type] -= order.quantity
            key = (order.supplier_id, order.asset_type)
            self.capex_supplier_reservations[key] -= order.quantity
            if self.capex_supplier_reservations[key] == 0:
                del self.capex_supplier_reservations[key]
            capital_formation[order.asset_type] += order.quantity
            self._event(f"p{period}:capex-delivery:{order.order_id}", "capex_physical_delivery", {
                "order_id": order.order_id, "delivery_event_id": event_id,
                "credit_event_id": order.credit_event_id,
                "payment_event_id": order.payment_event_id,
                "supplier_id": order.supplier_id, "buyer_id": order.borrower_id,
                "asset_type": order.asset_type, "quantity": str(order.quantity),
                "capital_formation": str(order.quantity),
                "evidence_ref": f"goods-receipt:{order.order_id}",
            })

    def _commissioned_capacity(self, firm_id, period):
        return self.fixed_asset_ledger.commissioned_capacity(firm_id, period)

    def _plan_production(self, period=None):
        period = period if period is not None else max(1, self.current_period + 1)
        plans = {}
        for firm_id, state in sorted(self.firms.items()):
            c = state.config
            asset_capacity = self._commissioned_capacity(firm_id, period)
            effective_output_capacity = c.output_capacity + asset_capacity
            effective_labour_capacity = c.labour_capacity + asset_capacity * c.labour_per_unit
            labour_limited = effective_labour_capacity / c.labour_per_unit
            output_stock = state.inventory.get(c.output_product, ZERO)
            inventory_gap = max(ZERO, effective_output_capacity - output_stock)
            plans[firm_id] = min(effective_output_capacity, labour_limited, inventory_gap)
        return plans

    def _allocate_labour(self, plans):
        """Allocate scarce household hours to firms using declared hiring weights.

        Firm-level household shares are hiring preferences, not wage entitlements.
        Actual wage income is paid only for hours used in production.
        """
        requested = {household_id: ZERO for household_id in self.households}
        firm_requests = {}
        for firm_id, state in sorted(self.firms.items()):
            asset_capacity = self._commissioned_capacity(firm_id, self.current_period)
            effective_labour_capacity = (state.config.labour_capacity
                                          + asset_capacity * state.config.labour_per_unit)
            demand = min(plans[firm_id] * state.config.labour_per_unit,
                         effective_labour_capacity)
            shares = self._labour_shares(state.config)
            firm_requests[firm_id] = {h: demand * share for h, share in shares.items()}
            for household_id, hours in firm_requests[firm_id].items():
                requested[household_id] += hours
        scale = {}
        rounding_buffer = QTY * D(len(self.firms) + 1)
        for household_id, state in self.households.items():
            supply = state.config.labour_supply_hours
            # Reserve enough sub-quantum slack for per-firm Decimal rounding
            # and the per-firm residual assignment below. This prevents the
            # realized hours from exceeding a hard household supply ceiling.
            safe_supply = max(ZERO, supply - rounding_buffer)
            scale[household_id] = min(D("1"), safe_supply / requested[household_id]) if requested[household_id] > 0 else ZERO
        allocations = {}
        firm_hired = {firm_id: ZERO for firm_id in self.firms}
        household_hired = {household_id: ZERO for household_id in self.households}
        for firm_id, rows in firm_requests.items():
            allocations[firm_id] = {}
            for household_id, hours in rows.items():
                allocated = qty(hours * scale[household_id])
                allocations[firm_id][household_id] = allocated
                firm_hired[firm_id] += allocated
                household_hired[household_id] += allocated
        # Keep rounded allocations within each household's hard hour limit.
        for household_id, state in self.households.items():
            excess = household_hired[household_id] - state.config.labour_supply_hours
            if excess > 0:
                candidates = [(firm_id, allocations[firm_id].get(household_id, ZERO))
                              for firm_id in sorted(allocations)]
                firm_id, amount = max(candidates, key=lambda item: (item[1], item[0]))
                allocations[firm_id][household_id] -= excess
                firm_hired[firm_id] -= excess
                household_hired[household_id] -= excess
        return allocations, firm_hired, household_hired, requested

    def _build_orders(self, plans):
        orders = []
        budgets = {}
        for firm_id, state in sorted(self.firms.items()):
            budget = max(ZERO, state.cash * D("0.72"))
            budgets[("firm", firm_id)] = budget
            plan = plans[firm_id]
            for product_id, coefficient in sorted(state.config.recipe.items()):
                need = max(ZERO, plan * coefficient - state.inventory.get(product_id, ZERO))
                if need > 0:
                    orders.append(MarketOrder(firm_id, product_id, need, "firm"))
        for household_id, state in sorted(self.households.items()):
            budget = state.cash * state.config.consumption_propensity * self.household_demand_multiplier
            budgets[("household", household_id)] = max(ZERO, budget)
            for product_id, amount in sorted(state.config.basket.items()):
                if amount > 0:
                    orders.append(MarketOrder(household_id, product_id, amount * self.household_demand_multiplier, "household"))
        # Scale all orders of each buyer together so no buyer can spend more than its period budget.
        notional = {}
        for order in orders:
            notional[(order.buyer_kind, order.buyer_id)] = notional.get((order.buyer_kind, order.buyer_id), ZERO) + order.quantity * self.prices[order.product_id]
        scaled = []
        for order in orders:
            key = (order.buyer_kind, order.buyer_id)
            # Reserve for the maximum permitted one-period price increase so the
            # realized spend remains within the buyer's configured budget.
            protected_notional = notional[key] * (D("1") + self.max_price_change)
            scale = min(D("1"), budgets[key] / protected_notional) if protected_notional > 0 else ZERO
            scaled.append(MarketOrder(order.buyer_id, order.product_id, qty(order.quantity * scale), order.buyer_kind))
        return scaled, budgets

    def _clear_product(self, product_id, orders, period, buyer_budget):
        product = self.product_by_id[product_id]
        offers = []
        for firm_id, state in sorted(self.firms.items()):
            if state.config.output_product == product_id:
                stock = state.inventory.get(product_id, ZERO)
                stock -= self.capex_supplier_reservations.get((firm_id, product_id), ZERO)
                if stock > 0:
                    offers.append((firm_id, "firm", stock, self.prices[product_id] * state.config.domestic_ask_markup))
        offers.append(("external-supplier", "external", product.import_capacity, product.import_price))
        demand_orders = [o for o in orders if o.product_id == product_id and o.quantity > 0]
        total_demand = sum((o.quantity for o in demand_orders), ZERO)
        total_supply = sum((x[2] for x in offers), ZERO)
        reference = self.prices[product_id]
        # Only supply offered at or below the current reference price enters the
        # current-price imbalance signal. Higher-ask imports are not treated as
        # immediately available merely because their capacity exists.
        priced_supply = sum((x[2] for x in offers if x[3] <= reference), ZERO)
        if priced_supply > 0:
            imbalance = (total_demand - priced_supply) / max(priced_supply, D("0.00000001"))
        else:
            imbalance = D("1") if total_demand > 0 else ZERO
        imbalance = max(D("-1"), min(D("1"), imbalance))
        factor = max(D("1") - self.max_price_change,
                     min(D("1") + self.max_price_change, D("1") + self.price_adjustment * imbalance))
        proposed_price = reference * factor
        lowest_ask = min((o[3] for o in offers if o[2] > 0), default=reference)
        highest_bid = reference * D("1.8")
        upper_price = reference * (D("1") + self.max_price_change)
        # Do not jump the reference price to an expensive ask. If the lowest
        # ask lies above the permitted one-period price band or buyer bid cap,
        # this period has no executable trade at that ask; the bounded reference
        # price moves only by the configured adjustment rule.
        if lowest_ask <= min(upper_price, highest_bid):
            clearing_price = max(lowest_ask, min(highest_bid, proposed_price))
        else:
            clearing_price = proposed_price
        eligible_offers = [o for o in offers if o[2] > 0 and o[3] <= clearing_price]
        eligible_demand = [o for o in demand_orders if o.quantity > 0 and clearing_price <= highest_bid]
        available = sum((o[2] for o in eligible_offers), ZERO)
        requested = sum((o.quantity for o in eligible_demand), ZERO)
        traded = min(available, requested)
        buyer_weights = {}
        if requested > 0 and traded > 0:
            for order in eligible_demand:
                key = (order.buyer_kind, order.buyer_id)
                buyer_weights[key] = buyer_weights.get(key, ZERO) + order.quantity
        buyer_allocations = _scale_allocations(buyer_weights, traded) if traded > 0 else {}
        seller_allocations = {}
        if available > 0 and traded > 0:
            # Merit order: use the lowest-ask supplier first; expensive imports
            # fill only the residual quantity once their ask is reached.
            remaining_supply = traded
            for seller_id, seller_kind, offer_qty, ask in sorted(eligible_offers, key=lambda x: (x[3], x[1], x[0])):
                allocation = min(offer_qty, remaining_supply)
                if allocation > 0:
                    seller_allocations[(seller_kind, seller_id)] = allocation
                    remaining_supply -= allocation
                if remaining_supply <= 0:
                    break
        # Cash cap is checked again at execution; any residual quantity remains unfilled.
        actual_buyer_allocations = {}
        for key, amount in sorted(buyer_allocations.items()):
            kind, buyer_id = key
            available_cash = self.firms[buyer_id].cash if kind == "firm" else self.households[buyer_id].cash
            remaining_budget = buyer_budget.get(key, available_cash)
            spendable = min(available_cash, remaining_budget)
            affordable = qty_floor(spendable / clearing_price) if clearing_price > 0 else ZERO
            actual_buyer_allocations[key] = min(amount, affordable)
        # A positive physical allocation is not executable if its cash settlement
        # rounds to zero cents. Exclude it before computing traded quantity; otherwise
        # sellers lose inventory while buyers receive nothing, breaking the stock-flow
        # identity by the sum of these unpayable micro-allocations.
        settled_buyer_allocations = {}
        for key, amount in actual_buyer_allocations.items():
            if amount > 0 and cash(amount * clearing_price) > 0:
                settled_buyer_allocations[key] = amount
        actual_traded = sum(settled_buyer_allocations.values(), ZERO)
        if actual_traded < traded and seller_allocations:
            # Reconcile seller deliveries without assigning a negative rounding
            # residual to a small final seller.
            seller_allocations = _scale_allocations(seller_allocations, actual_traded)
        else:
            actual_traded = traded
        # Preflight seller-side cent settlement before mutating either side. Several
        # tiny suppliers can each round up to a cent even when the buyer's aggregate
        # settlement is smaller; fail closed rather than partially debiting buyers.
        buyer_cash = sum((cash(qty_value * clearing_price)
                          for qty_value in settled_buyer_allocations.values()), ZERO)
        seller_items = [(key, amount) for key, amount in sorted(seller_allocations.items()) if amount > 0]
        seller_revenues = {}
        seller_cash_assigned = ZERO
        for index, (key, amount) in enumerate(seller_items):
            revenue = (cash(amount * clearing_price)
                       if index < len(seller_items) - 1
                       else buyer_cash - seller_cash_assigned)
            if revenue < 0:
                raise EconomyError("seller-side cent rounding exceeds executable buyer settlement")
            seller_revenues[key] = revenue
            seller_cash_assigned += revenue

        # Allocate only settled quantities to buyers' firm input stocks or household consumption.
        for (kind, buyer_id), amount in settled_buyer_allocations.items():
            payment = cash(amount * clearing_price)
            buyer_budget[(kind, buyer_id)] = max(ZERO, buyer_budget.get((kind, buyer_id), ZERO) - payment)
            if kind == "firm":
                state = self.firms[buyer_id]
                state.cash -= payment
                state.inventory[product_id] = state.inventory.get(product_id, ZERO) + amount
            else:
                state = self.households[buyer_id]
                state.cash -= payment
                state.consumption[product_id] = state.consumption.get(product_id, ZERO) + amount
                state.expenditure += payment
        imported = ZERO
        domestic_sold = ZERO
        for (kind, seller_id), amount in seller_items:
            revenue = seller_revenues[(kind, seller_id)]
            if kind == "firm":
                seller = self.firms[seller_id]
                seller.inventory[product_id] = max(ZERO, seller.inventory.get(product_id, ZERO) - amount)
                seller.cash += revenue
                seller.sales_revenue += revenue
                domestic_sold += amount
            else:
                self.import_cash += revenue
                imported += amount
        self.prices[product_id] = clearing_price
        shortage = max(ZERO, total_demand - actual_traded)
        self._event(f"p{period}:market:{product_id}", "market_clearing", {
            "product": product_id, "demand": str(total_demand), "supply": str(total_supply),
            "traded": str(actual_traded), "price": str(clearing_price), "shortage": str(shortage),
            "imports": str(imported), "domestic_sales": str(domestic_sold)
        })
        return {"imports": imported, "domestic_sales": domestic_sold,
                "traded": actual_traded, "shortage": shortage, "price": clearing_price}

    def step(self, period):
        if (not isinstance(period, int) or isinstance(period, bool)
                or period != self.current_period + 1):
            raise EconomyError("IO periods must advance exactly one step from the current period")
        # Preflight all deterministic delivery event identities before changing
        # the period, asset ledger, supplier inventory or household state.
        for order in self.capex_orders.values():
            if order.delivery_period == period:
                delivery_event_key = f"p{period}:capex-delivery:{order.order_id}"
                if delivery_event_key in self._event_keys:
                    raise EconomyError("capex delivery event key already exists")
        for household in self.households.values():
            household.period_wage_income = ZERO
            household.period_labour_hours = ZERO
            household.period_income_by_source = {}
        household_spend_open = sum((h.expenditure for h in self.households.values()), ZERO)
        household_consumption_open = {
            p.product_id: sum((h.consumption.get(p.product_id, ZERO) for h in self.households.values()), ZERO)
            for p in self.products
        }
        opening_stock = {
            p.product_id: sum((f.inventory.get(p.product_id, ZERO) for f in self.firms.values()), ZERO)
            for p in self.products
        }
        self.current_period = period
        capital_formation = {p.product_id: ZERO for p in self.products}
        self._commission_capex_deliveries(period, capital_formation)
        plans = self._plan_production(period)
        orders, budgets = self._build_orders(plans)
        market = {}
        for product_id in sorted(self.product_by_id):
            market[product_id] = self._clear_product(product_id, orders, period, budgets)
        labour_allocations, firm_hired_hours, household_hired_hours, household_labour_demand = self._allocate_labour(plans)
        production = {p.product_id: ZERO for p in self.products}
        input_consumption = {p.product_id: ZERO for p in self.products}
        wages_total = ZERO
        gross_value_added = ZERO
        for firm_id, state in sorted(self.firms.items()):
            c = state.config
            possible = min(plans[firm_id], firm_hired_hours[firm_id] / c.labour_per_unit)
            for product_id, coefficient in c.recipe.items():
                possible = min(possible, state.inventory.get(product_id, ZERO) / coefficient)
            wage_per_output = c.labour_per_unit * c.wage_per_labour
            if wage_per_output > 0:
                possible = min(possible, state.cash / wage_per_output)
            # Production must never round above a binding stock, labour or capacity constraint.
            actual = qty_floor(max(ZERO, possible))
            if actual <= 0:
                state.production = ZERO
                continue
            input_value = ZERO
            for product_id, coefficient in c.recipe.items():
                # Conservative quantity rounding prevents the inventory clamp from silently
                # deleting an unaccounted physical shortfall at the last sub-quantum.
                used = qty_floor(actual * coefficient)
                state.inventory[product_id] = max(ZERO, state.inventory.get(product_id, ZERO) - used)
                input_consumption[product_id] += used
                input_value += used * self.prices[product_id]
            wage = cash(actual * wage_per_output)
            state.cash -= wage
            state.wages_paid = wage
            state.production = actual
            state.inventory[c.output_product] = state.inventory.get(c.output_product, ZERO) + actual
            state.intermediate_consumption_value = input_value
            production[c.output_product] += actual
            wages_total += wage
            gross_value_added += actual * self.prices[c.output_product] - input_value
            # Allocate wages and paid labour hours through explicit firm-level
            # employment shares; cash and hour residuals are assigned exactly.
            labour_hours = actual * c.labour_per_unit
            hired = firm_hired_hours[firm_id]
            hours_by_household = {
                key: qty(labour_hours * allocation / hired)
                for key, allocation in labour_allocations[firm_id].items()
            } if hired > 0 else {}
            if hours_by_household:
                residual_household = max(hours_by_household, key=lambda key: (hours_by_household[key], key))
                hours_by_household[residual_household] += labour_hours - sum(hours_by_household.values(), ZERO)
            wage_by_household = {key: cash(hours * c.wage_per_labour)
                                 for key, hours in hours_by_household.items()}
            if wage_by_household:
                residual_household = max(wage_by_household, key=lambda key: (wage_by_household[key], key))
                wage_by_household[residual_household] += wage - sum(wage_by_household.values(), ZERO)
            wage_payment_event_ids = {}
            active_cohorts = [
                cohort for cohort in self.fixed_asset_ledger.cohorts.values()
                if cohort.owner_id == firm_id and cohort.productive_capacity(period) > 0
            ]
            active_credit_event_ids = [
                self.capex_orders[cohort.order_id].credit_event_id for cohort in active_cohorts
            ]
            active_asset_order_ids = [cohort.order_id for cohort in active_cohorts]
            production_event_key = f"p{period}:production:{firm_id}"
            wage_payment_event_ids = {
                household_id: f"WAGE-PAYMENT:{period}:{firm_id}:{household_id}"
                for household_id, share in wage_by_household.items() if share > 0
            }
            self._event(production_event_key, "production", {
                "firm": firm_id, "product": c.output_product, "quantity": str(actual),
                "intermediate_input_value": str(input_value), "wages": str(wage),
                "labour_hours": str(labour_hours),
                "wage_by_household": {k: str(v) for k, v in wage_by_household.items()},
                "wage_payment_event_ids_by_household": wage_payment_event_ids,
                "labour_hours_by_household": {k: str(v) for k, v in hours_by_household.items()},
                "hired_hours_by_household": {k: str(v) for k, v in labour_allocations[firm_id].items()},
                "commissioned_capital_capacity": str(self._commissioned_capacity(firm_id, period)),
                "capital_asset_cohort_ids": [cohort.cohort_id for cohort in active_cohorts],
                "capital_asset_order_ids": active_asset_order_ids,
                "capital_asset_credit_event_ids": active_credit_event_ids,
                "capital_asset_payment_event_ids": [
                    self.capex_orders[cohort.order_id].payment_event_id for cohort in active_cohorts
                ],
            })
            for household_id, hours in hours_by_household.items():
                household = self.households[household_id]
                household.period_labour_hours += hours
                share = wage_by_household.get(household_id, ZERO)
                if share <= 0:
                    continue
                household.cash += share
                household.wage_income += share
                household.period_wage_income += share
                household.period_income_by_source["wages"] = household.period_income_by_source.get("wages", ZERO) + share
                household.cumulative_income_by_source["wages"] = household.cumulative_income_by_source.get("wages", ZERO) + share
                wage_event_id = wage_payment_event_ids[household_id]
                self._event(f"p{period}:wage-payment:{firm_id}:{household_id}", "wage_payment", {
                    "event_id": wage_event_id, "firm_id": firm_id,
                    "household_id": household_id, "amount": str(share),
                    "labour_hours": str(hours_by_household[household_id]),
                    "production_event_key": production_event_key,
                    "capital_asset_order_ids": active_asset_order_ids,
                    "credit_event_ids": active_credit_event_ids,
                })
        self._settle_household_income(period)
        for household_id, household in self.households.items():
            used_hours = household.period_labour_hours
            household.period_unemployment_hours = max(ZERO, household.config.labour_supply_hours - used_hours)
            household.cumulative_unemployment_hours += household.period_unemployment_hours
        self._event(f"p{period}:labour_market", "labour_market_clearing", {
            "household_supply_hours": {k: str(v.config.labour_supply_hours) for k, v in self.households.items()},
            "household_requested_hours": {k: str(v) for k, v in household_labour_demand.items()},
            "household_hired_hours": {k: str(v) for k, v in household_hired_hours.items()},
            "household_worked_hours": {k: str(v.period_labour_hours) for k, v in self.households.items()},
            "household_unemployment_hours": {k: str(v.period_unemployment_hours) for k, v in self.households.items()},
        })
        household_consumption = {
            p.product_id: sum((h.consumption.get(p.product_id, ZERO) for h in self.households.values()), ZERO)
            - household_consumption_open[p.product_id]
            for p in self.products
        }
        imports = {pid: market[pid]["imports"] for pid in self.product_by_id}
        closing_stock = {
            p.product_id: sum((f.inventory.get(p.product_id, ZERO) for f in self.firms.values()), ZERO)
            for p in self.products
        }
        physical_error = {}
        for p in self.products:
            pid = p.product_id
            lhs = opening_stock[pid] + imports[pid] + production[pid]
            rhs = (input_consumption[pid] + household_consumption[pid]
                   + capital_formation[pid] + closing_stock[pid])
            physical_error[pid] = lhs - rhs
            if abs(physical_error[pid]) > D("0.000001"):
                firm_input_flows = {
                    firm_id: str(qty_floor(state.production * state.config.recipe[pid]))
                    for firm_id, state in sorted(self.firms.items())
                    if pid in state.config.recipe and state.production > 0
                }
                raise EconomyError(
                    f"physical stock balance failed for {pid}: {physical_error[pid]}; "
                    f"opening={opening_stock[pid]}, imports={imports[pid]}, "
                    f"production={production[pid]}, intermediate={input_consumption[pid]}, "
                    f"household={household_consumption[pid]}, "
                    f"capital_formation={capital_formation[pid]}, closing={closing_stock[pid]}, "
                    f"firm_input_flows={firm_input_flows}"
                )
        system_cash = self._system_cash()
        cash_error = system_cash - self.initial_cash
        if cash_error != 0:
            raise EconomyError(f"system cash conservation failed: {cash_error}")
        if any(f.cash < 0 for f in self.firms.values()) or any(h.cash < 0 for h in self.households.values()):
            raise EconomyError("negative cash balance")
        self._event(f"p{period}:period_close", "period_close", {
            "system_cash": str(system_cash), "cash_error": str(cash_error),
            "gross_value_added_proxy": str(gross_value_added)
        })
        event_payload = json.dumps(self.events, sort_keys=True, separators=(",", ":"))
        digest = sha256(event_payload.encode("utf-8")).hexdigest()
        result = PeriodResult(
            period=period, prices={k: str(v) for k, v in self.prices.items()},
            production={k: str(v) for k, v in production.items()},
            imports={k: str(v) for k, v in imports.items()},
            intermediate_consumption={k: str(v) for k, v in input_consumption.items()},
            household_consumption={k: str(v) for k, v in household_consumption.items()},
            closing_inventory={k: str(v) for k, v in closing_stock.items()},
            shortages={k: str(market[k]["shortage"]) for k in market},
            wages=wages_total,
            household_wage_income={k: str(v.period_wage_income) for k, v in self.households.items()},
            household_labour_hours={k: str(v.period_labour_hours) for k, v in self.households.items()},
            household_labour_supply_hours={k: str(v.config.labour_supply_hours) for k, v in self.households.items()},
            household_unemployment_hours={k: str(v.period_unemployment_hours) for k, v in self.households.items()},
            household_employment_rate={k: str((v.period_labour_hours / v.config.labour_supply_hours) if v.config.labour_supply_hours > 0 else ZERO) for k, v in self.households.items()},
            household_income_by_source={k: {source: str(amount) for source, amount in v.period_income_by_source.items()} for k, v in self.households.items()},
            household_total_income={k: str(sum(v.period_income_by_source.values(), ZERO)) for k, v in self.households.items()},
            household_income_payment_arrears={p.payment_id: str(self.income_payment_arrears.get(p.payment_id, ZERO)) for p in self.income_payments},
            capital_formation={k: str(v) for k, v in capital_formation.items()},
            firm_production_by_firm={k: str(v.production) for k, v in self.firms.items()},
            firm_commissioned_capacity_by_firm={k: str(self._commissioned_capacity(k, period)) for k in self.firms},
            household_expenditure=sum((h.expenditure for h in self.households.values()), ZERO) - household_spend_open,
            import_expenditure=sum((market[k]["imports"] * market[k]["price"] for k in market), ZERO),
            gross_value_added_proxy=gross_value_added, system_cash=system_cash,
            cash_error=cash_error, physical_balance_error=physical_error, event_digest=digest
        )
        self.period_results.append(result)
        return result

    def run(self, periods=12):
        if periods < 1:
            raise EconomyError("periods must be positive")
        start_period = self.current_period + 1
        for period in range(start_period, start_period + periods):
            self.step(period)
        return self.summary()

    def summary(self):
        if not self.period_results:
            raise EconomyError("run the model before requesting summary")
        total_production = {p.product_id: sum((dec(r.production[p.product_id]) for r in self.period_results), ZERO) for p in self.products}
        total_imports = {p.product_id: sum((dec(r.imports[p.product_id]) for r in self.period_results), ZERO) for p in self.products}
        total_shortages = {p.product_id: sum((dec(r.shortages[p.product_id]) for r in self.period_results), ZERO) for p in self.products}
        final = self.period_results[-1]
        return {
            "periods": len(self.period_results),
            "cumulative_production_by_product": {k: str(v) for k, v in total_production.items()},
            "cumulative_imports_by_product": {k: str(v) for k, v in total_imports.items()},
            "cumulative_shortages_by_product": {k: str(v) for k, v in total_shortages.items()},
            "final_prices": final.prices,
            "final_household_cash": str(sum((h.cash for h in self.households.values()), ZERO)),
            "final_firm_cash": str(sum((f.cash for f in self.firms.values()), ZERO)),
            "external_supplier_cash": str(self.import_cash),
            "system_cash": str(final.system_cash),
            "cash_conservation_error": str(final.cash_error),
            "max_abs_physical_balance_error": str(max((abs(dec(x)) for r in self.period_results for x in r.physical_balance_error.values()), default=ZERO)),
            "cumulative_wages": str(sum((r.wages for r in self.period_results), ZERO)),
            "final_household_unemployment_hours": final.household_unemployment_hours,
            "final_household_employment_rate": final.household_employment_rate,
            "final_household_income_by_source": final.household_income_by_source,
            "final_household_total_income": final.household_total_income,
            "outstanding_household_income_payment_arrears": {k: v for k, v in final.household_income_payment_arrears.items() if D(v) > 0},
            "cumulative_household_expenditure": str(sum((r.household_expenditure for r in self.period_results), ZERO)),
            "cumulative_import_expenditure": str(sum((r.import_expenditure for r in self.period_results), ZERO)),
            "cumulative_capital_formation_by_product": {p.product_id: str(sum((dec(r.capital_formation[p.product_id]) for r in self.period_results), ZERO)) for p in self.products},
            "cumulative_gross_value_added_proxy": str(sum((r.gross_value_added_proxy for r in self.period_results), ZERO)),
            "ending_inventory_by_product": final.closing_inventory,
            "event_count": len(self.events),
            "event_log_digest": final.event_digest
        }

def run_scenario(name="baseline", periods=12):
    model = InputOutputEconomy()
    if name == "demand_collapse":
        model.household_demand_multiplier = D("0.58")
    elif name == "energy_import_shock":
        for i, p in enumerate(model.products):
            if p.product_id == "energy":
                model.products[i] = Product(p.product_id, p.unit, p.base_price, p.import_price * D("1.65"), p.import_capacity * D("0.45"), p.demand_weight)
        model.product_by_id = {p.product_id: p for p in model.products}
    elif name == "metals_shortage":
        for i, p in enumerate(model.products):
            if p.product_id == "metals":
                model.products[i] = Product(p.product_id, p.unit, p.base_price, p.import_price, p.import_capacity * D("0.25"), p.demand_weight)
        model.product_by_id = {p.product_id: p for p in model.products}
    elif name == "compound_shock":
        model.household_demand_multiplier = D("0.72")
        for i, p in enumerate(model.products):
            if p.product_id in ("energy", "metals"):
                factor = D("0.50") if p.product_id == "energy" else D("0.30")
                price_factor = D("1.40") if p.product_id == "energy" else D("1.25")
                model.products[i] = Product(p.product_id, p.unit, p.base_price, p.import_price * price_factor, p.import_capacity * factor, p.demand_weight)
        model.product_by_id = {p.product_id: p for p in model.products}
    elif name != "baseline":
        raise EconomyError("unknown scenario")
    summary = model.run(periods)
    return {"scenario": name, "summary": summary,
            "periods": [r.__dict__ for r in model.period_results]}

def main():
    parser = argparse.ArgumentParser(description="SYNERGY general input-output economy prototype")
    parser.add_argument("--scenario", default="baseline",
                        choices=["baseline", "demand_collapse", "energy_import_shock", "metals_shortage", "compound_shock"])
    parser.add_argument("--periods", type=int, default=12)
    parser.add_argument("--output", default="")
    args = parser.parse_args()
    result = run_scenario(args.scenario, args.periods)
    rendered = json.dumps(result, indent=2, sort_keys=True, default=str)
    if args.output:
        Path(args.output).write_text(rendered + "\n", encoding="utf-8")
    print(rendered)

if __name__ == "__main__":
    main()
