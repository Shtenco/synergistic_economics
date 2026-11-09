"""General input-output network prototype for SYNERGY (standard library only).

This is a transparent, deterministic research model, not a calibrated forecast.
Money is Decimal; physical quantities are Decimal; spot markets clear by product.
"""
from dataclasses import dataclass, field
from decimal import Decimal as D, ROUND_HALF_UP
from hashlib import sha256
import argparse
import json
from pathlib import Path

ZERO = D("0")
QTY = D("0.00000001")
CENT = D("0.01")

def dec(value):
    return D(str(value))

def qty(value):
    return dec(value).quantize(QTY, rounding=ROUND_HALF_UP)

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

@dataclass(frozen=True)
class HouseholdConfig:
    household_id: str
    initial_cash: D
    basket: dict
    consumption_propensity: D = D("0.35")

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
                 household_demand_multiplier=D("1")):
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
            FirmConfig("farm-north", "grain", {"energy": D("0.12"), "logistics": D("0.08")}, D("0.40"), D("12"), D("24"), D("8"), D("5200"), {"grain": D("7"), "energy": D("1"), "logistics": D("1")}),
            FirmConfig("farm-south", "grain", {"energy": D("0.15"), "logistics": D("0.10")}, D("0.42"), D("10"), D("20"), D("8"), D("4100"), {"grain": D("5"), "energy": D("1"), "logistics": D("1")}),
            FirmConfig("power-east", "energy", {"metals": D("0.025"), "machinery": D("0.006")}, D("0.18"), D("15"), D("28"), D("9"), D("6200"), {"energy": D("5"), "metals": D("0.5"), "machinery": D("0.1")}),
            FirmConfig("power-west", "energy", {"metals": D("0.03"), "machinery": D("0.005")}, D("0.20"), D("12"), D("22"), D("9"), D("5000"), {"energy": D("4"), "metals": D("0.5"), "machinery": D("0.1")}),
            FirmConfig("mine-central", "metals", {"energy": D("0.20"), "machinery": D("0.012"), "logistics": D("0.04")}, D("0.35"), D("11"), D("18"), D("10"), D("6000"), {"metals": D("3"), "energy": D("2"), "machinery": D("0.2"), "logistics": D("0.5")}),
            FirmConfig("machine-works", "machinery", {"metals": D("0.55"), "energy": D("0.30"), "logistics": D("0.10")}, D("1.20"), D("8"), D("7"), D("14"), D("8500"), {"machinery": D("1"), "metals": D("2"), "energy": D("2"), "logistics": D("0.5")}),
            FirmConfig("transport-coop", "logistics", {"energy": D("0.28"), "machinery": D("0.018")}, D("0.55"), D("14"), D("22"), D("9"), D("4800"), {"logistics": D("3"), "energy": D("2"), "machinery": D("0.2")}),
            FirmConfig("food-coop", "food", {"grain": D("0.72"), "energy": D("0.10"), "logistics": D("0.12")}, D("0.62"), D("12"), D("18"), D("9"), D("5600"), {"food": D("2"), "grain": D("2"), "energy": D("1"), "logistics": D("0.5")}),
            FirmConfig("care-network", "care", {"food": D("0.025"), "energy": D("0.08"), "logistics": D("0.04")}, D("1.10"), D("9"), D("12"), D("11"), D("6300"), {"care": D("1"), "food": D("0.2"), "energy": D("1"), "logistics": D("0.2")}),
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
        for h in self.household_configs:
            if set(h.basket) - known or any(not v.is_finite() or v < 0 for v in h.basket.values()):
                raise EconomyError("invalid household basket")
            if (not h.initial_cash.is_finite() or not h.consumption_propensity.is_finite()
                    or h.initial_cash < 0
                    or not D("0") <= h.consumption_propensity <= D("1")):
                raise EconomyError("invalid household budget")

    def _system_cash(self):
        return sum((f.cash for f in self.firms.values()), ZERO) + sum((h.cash for h in self.households.values()), ZERO) + self.import_cash

    def _event(self, key, kind, payload):
        if key in self._event_keys:
            raise EconomyError("duplicate event key")
        self._event_keys.add(key)
        row = {"key": key, "kind": kind, "payload": payload}
        self.events.append(row)

    def _plan_production(self):
        plans = {}
        for firm_id, state in sorted(self.firms.items()):
            c = state.config
            labour_limited = c.labour_capacity / c.labour_per_unit
            output_stock = state.inventory.get(c.output_product, ZERO)
            inventory_gap = max(ZERO, c.output_capacity - output_stock)
            plans[firm_id] = min(c.output_capacity, labour_limited, inventory_gap)
        return plans

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
        buyer_allocations = {}
        if requested > 0 and traded > 0:
            for order in eligible_demand:
                allocation = qty(traded * order.quantity / requested)
                buyer_allocations[(order.buyer_kind, order.buyer_id)] = buyer_allocations.get((order.buyer_kind, order.buyer_id), ZERO) + allocation
        seller_allocations = {}
        if available > 0 and traded > 0:
            # Merit order: use the lowest-ask supplier first; expensive imports
            # fill only the residual quantity once their ask is reached.
            remaining_supply = traded
            for seller_id, seller_kind, offer_qty, ask in sorted(eligible_offers, key=lambda x: (x[3], x[1], x[0])):
                allocation = min(offer_qty, remaining_supply)
                if allocation > 0:
                    seller_allocations[(seller_kind, seller_id)] = qty(allocation)
                    remaining_supply -= allocation
                if remaining_supply <= 0:
                    break
        # Correct tiny Decimal rounding drift deterministically on the last eligible buyer/seller.
        if buyer_allocations:
            drift = traded - sum(buyer_allocations.values(), ZERO)
            key = sorted(buyer_allocations)[-1]
            buyer_allocations[key] += drift
        if seller_allocations:
            drift = traded - sum(seller_allocations.values(), ZERO)
            key = sorted(seller_allocations)[-1]
            seller_allocations[key] += drift
        # Cash cap is checked again at execution; any residual quantity remains unfilled.
        actual_buyer_allocations = {}
        for key, amount in sorted(buyer_allocations.items()):
            kind, buyer_id = key
            available_cash = self.firms[buyer_id].cash if kind == "firm" else self.households[buyer_id].cash
            remaining_budget = buyer_budget.get(key, available_cash)
            spendable = min(available_cash, remaining_budget)
            affordable = qty(spendable / clearing_price) if clearing_price > 0 else ZERO
            actual_buyer_allocations[key] = min(amount, affordable)
        actual_traded = sum(actual_buyer_allocations.values(), ZERO)
        if actual_traded < traded and seller_allocations:
            # Scale seller deliveries to actual buyer settlement.
            for key in list(seller_allocations):
                seller_allocations[key] = qty(seller_allocations[key] * actual_traded / traded)
            drift = actual_traded - sum(seller_allocations.values(), ZERO)
            key = sorted(seller_allocations)[-1]
            seller_allocations[key] += drift
        else:
            actual_traded = traded
        # Allocate the actual quantity to buyers' firm input stocks or household consumption.
        for (kind, buyer_id), amount in actual_buyer_allocations.items():
            payment = cash(amount * clearing_price)
            if payment <= 0 or amount <= 0:
                continue
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
        buyer_cash = sum((cash(qty_value * clearing_price) for qty_value in actual_buyer_allocations.values()), ZERO)
        seller_items = [(key, amount) for key, amount in sorted(seller_allocations.items()) if amount > 0]
        seller_cash_assigned = ZERO
        for index, ((kind, seller_id), amount) in enumerate(seller_items):
            # Allocate cent-rounding residual to the final actual seller, not to an artificial plug account.
            revenue = cash(amount * clearing_price) if index < len(seller_items) - 1 else buyer_cash - seller_cash_assigned
            if revenue < 0:
                raise EconomyError("negative seller settlement after rounding")
            seller_cash_assigned += revenue
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
        cash_open = self._system_cash()
        household_spend_open = sum((h.expenditure for h in self.households.values()), ZERO)
        household_consumption_open = {
            p.product_id: sum((h.consumption.get(p.product_id, ZERO) for h in self.households.values()), ZERO)
            for p in self.products
        }
        opening_stock = {
            p.product_id: sum((f.inventory.get(p.product_id, ZERO) for f in self.firms.values()), ZERO)
            for p in self.products
        }
        plans = self._plan_production()
        orders, budgets = self._build_orders(plans)
        market = {}
        for product_id in sorted(self.product_by_id):
            market[product_id] = self._clear_product(product_id, orders, period, budgets)
        production = {p.product_id: ZERO for p in self.products}
        input_consumption = {p.product_id: ZERO for p in self.products}
        wages_total = ZERO
        gross_value_added = ZERO
        for firm_id, state in sorted(self.firms.items()):
            c = state.config
            possible = plans[firm_id]
            for product_id, coefficient in c.recipe.items():
                possible = min(possible, state.inventory.get(product_id, ZERO) / coefficient)
            wage_per_output = c.labour_per_unit * c.wage_per_labour
            if wage_per_output > 0:
                possible = min(possible, state.cash / wage_per_output)
            actual = qty(max(ZERO, possible))
            if actual <= 0:
                state.production = ZERO
                continue
            input_value = ZERO
            for product_id, coefficient in c.recipe.items():
                used = qty(actual * coefficient)
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
            # Wage payments become household income, split evenly across households.
            household_states = list(self.households.values())
            if household_states and wage > 0:
                shares = [cash(wage / D(len(household_states))) for _ in household_states]
                shares[-1] += wage - sum(shares, ZERO)
                for household, share in zip(household_states, shares):
                    household.cash += share
                    household.wage_income += share
            self._event(f"p{period}:production:{firm_id}", "production", {
                "firm": firm_id, "product": c.output_product, "quantity": str(actual),
                "intermediate_input_value": str(input_value), "wages": str(wage)
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
            rhs = input_consumption[pid] + household_consumption[pid] + closing_stock[pid]
            physical_error[pid] = lhs - rhs
            if abs(physical_error[pid]) > D("0.000001"):
                raise EconomyError(f"physical stock balance failed for {pid}: {physical_error[pid]}")
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
            wages=wages_total, household_expenditure=sum((h.expenditure for h in self.households.values()), ZERO) - household_spend_open,
            import_expenditure=sum((market[k]["imports"] * market[k]["price"] for k in market), ZERO),
            gross_value_added_proxy=gross_value_added, system_cash=system_cash,
            cash_error=cash_error, physical_balance_error=physical_error, event_digest=digest
        )
        self.period_results.append(result)
        return result

    def run(self, periods=12):
        if periods < 1:
            raise EconomyError("periods must be positive")
        for period in range(1, periods + 1):
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
            "cumulative_household_expenditure": str(sum((r.household_expenditure for r in self.period_results), ZERO)),
            "cumulative_import_expenditure": str(sum((r.import_expenditure for r in self.period_results), ZERO)),
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
