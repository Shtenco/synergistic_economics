"""C2-A2: in-loop household delivery and bounded essential-need backlog.

Household claims are explicit inputs to each period's cell production plan.
Actual Stage-B cell consumption is then allocated to the persistent household
panel, reconciled exactly, and unmet essential claims feed back into the next
period's local cell demand. This is a physical model: no money, wages, credit,
ownership income or utility is inferred here.
"""
from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, replace
from typing import Mapping

from scc_dynamic_economy import (
    DynamicCellularEconomy,
    DynamicEconomyError,
    FINAL_PRODUCTS,
    POLICIES,
)
from scc_household_bridge import households_from_cell_demand
from household_distribution import (
    Household,
    HouseholdAllocation,
    allocate_households,
    evaluate_households,
    validate_household_allocation,
)


EPS = 1e-9
ESSENTIAL_PRODUCTS = ("food", "care")
CARRYOVER_ESSENTIAL_PRODUCTS = ("care",)
NONCARRYOVER_ESSENTIAL_PRODUCTS = ("food",)


class EndogenousHouseholdError(ValueError):
    pass


@dataclass(frozen=True)
class HouseholdPeriodResult:
    period: int
    current_essential_demand: float
    current_essential_served: float
    current_food_demand: float
    current_food_served: float
    current_care_demand: float
    current_care_served: float
    current_overall_demand: float
    current_overall_served: float
    total_claim_essential_demand: float
    total_claim_essential_served: float
    lower_decile_current_essential_fulfilment: float
    minimum_current_essential_fulfilment: float
    opening_essential_backlog: float
    closing_essential_backlog: float
    household_metrics: Mapping[str, object]
    cell_demand: Mapping[str, Mapping[str, float]]
    cell_consumption: Mapping[str, Mapping[str, float]]
    allocations: tuple[HouseholdAllocation, ...]


class EndogenousHouseholdEconomy:
    """Stage-B physical economy with household claims and essential backlog."""

    def __init__(
        self,
        policy: str = "cellular",
        seed: int = 1,
        shock: str = "none",
        cellular_hops: int = 2,
        households_per_cell: int = 10,
        priority_dispersion: float = 0.4,
        household_policy: str = "proportional",
        essential_floor_fraction: float = 0.5,
        backlog_retention: float = 0.5,
        max_backlog_periods: float = 1.0,
        backlog_service_order: str = "backlog_first",
    ):
        if policy not in POLICIES:
            raise EndogenousHouseholdError("unknown economic policy")
        if household_policy not in ("proportional", "priority_weighted", "floor_priority"):
            raise EndogenousHouseholdError("unknown household allocation policy")
        if not 0.0 <= backlog_retention <= 1.0:
            raise EndogenousHouseholdError("backlog_retention must be in [0, 1]")
        if not math.isfinite(max_backlog_periods) or max_backlog_periods < 0:
            raise EndogenousHouseholdError("max_backlog_periods must be finite and non-negative")
        if not 0.0 <= essential_floor_fraction <= 1.0:
            raise EndogenousHouseholdError("essential_floor_fraction must be in [0, 1]")
        if backlog_service_order not in ("current_first", "backlog_first"):
            raise EndogenousHouseholdError("backlog_service_order must be current_first or backlog_first")

        self.policy = policy
        self.seed = seed
        self.shock = shock
        self.cellular_hops = cellular_hops
        self.household_policy = household_policy
        self.essential_floor_fraction = essential_floor_fraction
        self.backlog_retention = backlog_retention
        self.max_backlog_periods = max_backlog_periods
        self.backlog_service_order = backlog_service_order

        self.base_specs = DynamicCellularEconomy.default_specs(seed)
        self.base_specs_by_id = {spec.cell_id: spec for spec in self.base_specs}
        base_demand = {
            spec.cell_id: dict(spec.final_demand) for spec in self.base_specs
        }
        self.households = households_from_cell_demand(
            base_demand,
            households_per_cell=households_per_cell,
            seed=seed,
            essential_products=ESSENTIAL_PRODUCTS,
            priority_dispersion=priority_dispersion,
        )
        self.households_by_cell = {
            cell_id: tuple(h for h in self.households if h.cell_id == cell_id)
            for cell_id in self.base_specs_by_id
        }
        self.households_by_id = {h.household_id: h for h in self.households}
        if any(not members for members in self.households_by_cell.values()):
            raise EndogenousHouseholdError("every production cell needs household agents")

        # Only delayed care-service claims carry over. Recurring food needs are
        # period-specific: unmet food is recorded as deprivation exposure, not
        # converted into a larger food order in the next period.
        self.essential_backlog = {
            h.household_id: {
                p: 0.0 for p in h.essential_needs
                if p in CARRYOVER_ESSENTIAL_PRODUCTS
            }
            for h in self.households
        }
        self.cumulative_unmet_food = {h.household_id: 0.0 for h in self.households}
        self._cumulative_food_need = {h.household_id: 0.0 for h in self.households}
        self._cumulative_food_served = {h.household_id: 0.0 for h in self.households}
        self._cumulative_care_need = {h.household_id: 0.0 for h in self.households}
        self._cumulative_care_served = {h.household_id: 0.0 for h in self.households}
        self.engine = DynamicCellularEconomy(
            policy, seed, shock, cellular_hops, specs=self.base_specs)
        self.period_results: list[HouseholdPeriodResult] = []
        self._cumulative_current_need: dict[str, float] = {
            h.household_id: 0.0 for h in self.households
        }
        self._cumulative_current_served: dict[str, float] = {
            h.household_id: 0.0 for h in self.households
        }

    @staticmethod
    def _gini(values):
        vals = sorted(max(0.0, float(v)) for v in values)
        total = sum(vals)
        if not vals or total <= EPS:
            return 0.0
        n = len(vals)
        return sum((2 * (i + 1) - n - 1) * v
                   for i, v in enumerate(vals)) / (n * total)

    def _claims_for_period(self, demand_multiplier: float):
        claims = []
        current_by_household = {}
        opening_backlog = sum(
            sum(products.values()) for products in self.essential_backlog.values()
        )
        for base in self.households:
            essential_current = {
                p: float(q) * demand_multiplier
                for p, q in base.essential_needs.items()
            }
            essential_claim = {
                p: essential_current[p] + (
                    self.essential_backlog[base.household_id].get(p, 0.0)
                    if p in CARRYOVER_ESSENTIAL_PRODUCTS else 0.0
                )
                for p in essential_current
            }
            discretionary_current = {
                p: float(q) * demand_multiplier
                for p, q in base.discretionary_needs.items()
            }
            claim = replace(
                base,
                essential_needs=essential_claim,
                discretionary_needs=discretionary_current,
            )
            claims.append(claim)
            current_by_household[base.household_id] = {
                "essential": essential_current,
                "discretionary": discretionary_current,
                "opening_backlog": dict(self.essential_backlog[base.household_id]),
            }
        return tuple(claims), current_by_household, opening_backlog

    def _set_cell_demand(self, claims, demand_multiplier: float):
        by_cell_product = {
            cid: {p: 0.0 for p in FINAL_PRODUCTS}
            for cid in self.base_specs_by_id
        }
        for h in claims:
            for p, q in h.essential_needs.items():
                by_cell_product[h.cell_id][p] += float(q)
            for p, q in h.discretionary_needs.items():
                by_cell_product[h.cell_id][p] += float(q)

        # DynamicCellularEconomy applies its demand shock internally. Divide
        # by that multiplier here so the engine sees current need + backlog once.
        if demand_multiplier <= EPS:
            raise EndogenousHouseholdError("demand multiplier must be positive")
        for cid, base_spec in self.base_specs_by_id.items():
            effective = by_cell_product[cid]
            updated = {
                p: effective[p] / demand_multiplier
                for p in base_spec.final_demand
            }
            self.engine.cells[cid].spec = replace(
                base_spec, final_demand=updated)
        return by_cell_product

    def step(self, period: int) -> HouseholdPeriodResult:
        demand_multiplier, _, _ = self.engine._shock_values(period)
        claims, current, opening_backlog = self._claims_for_period(demand_multiplier)
        expected_demand = self._set_cell_demand(claims, demand_multiplier)

        physical = self.engine.step(period)
        supply = {
            cid: dict(products)
            for cid, products in physical.final_consumption_by_cell.items()
        }
        allocations = allocate_households(
            claims, supply, self.household_policy, self.essential_floor_fraction)
        validate_household_allocation(claims, supply, allocations)
        metrics = evaluate_households(claims, allocations)
        allocation_by_id = {a.household_id: a for a in allocations}

        # Every household claim must reconcile to the exact Stage-B demand.
        for cid, products in physical.final_demand_by_cell.items():
            for product, quantity in products.items():
                expected = expected_demand[cid].get(product, 0.0)
                if abs(float(quantity) - expected) > 1e-7:
                    raise EndogenousHouseholdError(
                        f"household demand mismatch at {cid}:{product}")

        # Household service is a decomposition of the already-consumed goods.
        # The allocator may not create, duplicate or move physical stock.
        allocated_by_cell = {
            cid: {p: 0.0 for p in FINAL_PRODUCTS}
            for cid in self.base_specs_by_id
        }
        for allocation in allocations:
            for p, q in allocation.essential_served.items():
                allocated_by_cell[allocation.cell_id][p] += float(q)
            for p, q in allocation.discretionary_served.items():
                allocated_by_cell[allocation.cell_id][p] += float(q)
        for cid, products in supply.items():
            for product, quantity in products.items():
                allocated = allocated_by_cell[cid].get(product, 0.0)
                if abs(allocated - float(quantity)) > 1e-7:
                    raise EndogenousHouseholdError(
                        f"household delivery mismatch at {cid}:{product}")

        current_essential_demand = current_essential_served = 0.0
        current_food_demand = current_food_served = 0.0
        current_care_demand = current_care_served = 0.0
        current_overall_demand = current_overall_served = 0.0
        household_current_rates = []
        claim_essential_demand = float(metrics["essential_demand"])
        claim_essential_served = float(metrics["essential_served"])

        for base in self.households:
            claim = allocation_by_id[base.household_id]
            state = current[base.household_id]
            household_e_demand = sum(state["essential"].values())
            household_e_served = 0.0
            household_total_demand = household_e_demand + sum(state["discretionary"].values())
            household_total_served = 0.0
            next_backlog = {}
            for product, need in state["essential"].items():
                delivered = float(claim.essential_served.get(product, 0.0))
                if product in CARRYOVER_ESSENTIAL_PRODUCTS:
                    old_backlog = float(state["opening_backlog"].get(product, 0.0))
                    if self.backlog_service_order == "current_first":
                        current_served = min(float(need), delivered)
                        backlog_served = max(0.0, delivered - current_served)
                    else:
                        backlog_served = min(old_backlog, delivered)
                        current_served = min(
                            float(need), max(0.0, delivered - backlog_served))
                    residual_backlog = max(0.0, old_backlog - backlog_served)
                    current_unmet = max(0.0, float(need) - current_served)
                    retained = self.backlog_retention * (
                        residual_backlog + current_unmet)
                    cap = float(base.essential_needs.get(product, 0.0)) * self.max_backlog_periods
                    next_backlog[product] = min(cap, retained)
                    current_care_demand += float(need)
                    current_care_served += current_served
                    self._cumulative_care_need[base.household_id] += float(need)
                    self._cumulative_care_served[base.household_id] += current_served
                else:
                    # Food is a recurring period-specific need, not a queue.
                    current_served = min(float(need), delivered)
                    current_food_demand += float(need)
                    current_food_served += current_served
                    self.cumulative_unmet_food[base.household_id] += max(
                        0.0, float(need) - current_served)
                    self._cumulative_food_need[base.household_id] += float(need)
                    self._cumulative_food_served[base.household_id] += current_served
                household_e_served += current_served
                household_total_served += current_served
            for product, need in state["discretionary"].items():
                delivered = float(claim.discretionary_served.get(product, 0.0))
                served = min(float(need), delivered)
                household_total_served += served

            self.essential_backlog[base.household_id] = next_backlog
            current_essential_demand += household_e_demand
            current_essential_served += household_e_served
            current_overall_demand += household_total_demand
            current_overall_served += household_total_served
            household_current_rates.append(
                household_e_served / household_e_demand
                if household_e_demand > EPS else 1.0
            )
            self._cumulative_current_need[base.household_id] += household_e_demand
            self._cumulative_current_served[base.household_id] += household_e_served

        closing_backlog = sum(
            sum(products.values()) for products in self.essential_backlog.values()
        )
        sorted_rates = sorted(household_current_rates)
        lower_index = max(0, math.ceil(0.10 * len(sorted_rates)) - 1)
        result = HouseholdPeriodResult(
            period=period,
            current_essential_demand=current_essential_demand,
            current_essential_served=current_essential_served,
            current_food_demand=current_food_demand,
            current_food_served=current_food_served,
            current_care_demand=current_care_demand,
            current_care_served=current_care_served,
            current_overall_demand=current_overall_demand,
            current_overall_served=current_overall_served,
            total_claim_essential_demand=claim_essential_demand,
            total_claim_essential_served=claim_essential_served,
            lower_decile_current_essential_fulfilment=sorted_rates[lower_index],
            minimum_current_essential_fulfilment=min(sorted_rates, default=1.0),
            opening_essential_backlog=opening_backlog,
            closing_essential_backlog=closing_backlog,
            household_metrics=metrics,
            cell_demand=physical.final_demand_by_cell,
            cell_consumption=physical.final_consumption_by_cell,
            allocations=tuple(allocations),
        )
        self.period_results.append(result)
        return result

    def run(self, periods: int = 24):
        if periods < 1:
            raise EndogenousHouseholdError("periods must be positive")
        for period in range(1, periods + 1):
            self.step(period)
        self.validate()
        return tuple(self.period_results)

    def validate(self):
        self.engine.validate()
        for result in self.period_results:
            if result.closing_essential_backlog < -EPS:
                raise EndogenousHouseholdError("negative household backlog")
            if result.current_essential_served > result.current_essential_demand + 1e-7:
                raise EndogenousHouseholdError("current essential service exceeds need")
            if result.current_overall_served > result.current_overall_demand + 1e-7:
                raise EndogenousHouseholdError("current total service exceeds need")
            if not 0.0 - EPS <= result.lower_decile_current_essential_fulfilment <= 1.0 + EPS:
                raise EndogenousHouseholdError("lower-decile fulfilment outside [0, 1]")
        for household_id, products in self.essential_backlog.items():
            base = self.households_by_id[household_id]
            for product, quantity in products.items():
                cap = float(base.essential_needs.get(product, 0.0)) * self.max_backlog_periods
                if quantity < -EPS or quantity > cap + EPS:
                    raise EndogenousHouseholdError("household essential backlog exceeds its cap")
        return True

    def summary(self):
        if not self.period_results:
            raise EndogenousHouseholdError("run the economy before requesting summary")
        current_e_demand = sum(r.current_essential_demand for r in self.period_results)
        current_e_served = sum(r.current_essential_served for r in self.period_results)
        current_total_demand = sum(r.current_overall_demand for r in self.period_results)
        current_total_served = sum(r.current_overall_served for r in self.period_results)
        household_rates = [
            self._cumulative_current_served[h.household_id]
            / self._cumulative_current_need[h.household_id]
            if self._cumulative_current_need[h.household_id] > EPS else 1.0
            for h in self.households
        ]
        sorted_rates = sorted(household_rates)
        lower_index = max(0, math.ceil(0.10 * len(sorted_rates)) - 1)
        total_care_delivered = sum(
            float(products.get("care", 0.0))
            for result in self.period_results
            for products in result.cell_consumption.values()
        )
        cumulative_current_care_served = sum(
            result.current_care_served for result in self.period_results
        )
        cumulative_care_backlog_served = max(
            0.0, total_care_delivered - cumulative_current_care_served)
        return {
            "policy": self.policy,
            "household_policy": self.household_policy,
            "backlog_service_order": self.backlog_service_order,
            "seed": self.seed,
            "shock": self.shock,
            "periods": len(self.period_results),
            "households": len(self.households),
            "current_essential_fulfilment": (
                current_e_served / current_e_demand if current_e_demand > EPS else 1.0),
            "current_overall_fulfilment": (
                current_total_served / current_total_demand
                if current_total_demand > EPS else 1.0),
            "current_food_fulfilment": (
                sum(r.current_food_served for r in self.period_results)
                / sum(r.current_food_demand for r in self.period_results)
                if sum(r.current_food_demand for r in self.period_results) > EPS else 1.0),
            "current_care_fulfilment": (
                cumulative_current_care_served
                / sum(r.current_care_demand for r in self.period_results)
                if sum(r.current_care_demand for r in self.period_results) > EPS else 1.0),
            "total_care_delivered": total_care_delivered,
            "cumulative_care_backlog_served": cumulative_care_backlog_served,
            "cumulative_unmet_food_units": sum(self.cumulative_unmet_food.values()),
            "cumulative_lower_decile_current_essential_fulfilment": sorted_rates[lower_index],
            "cumulative_minimum_current_essential_fulfilment": min(sorted_rates, default=1.0),
            "cumulative_household_essential_gini": self._gini(household_rates),
            "mean_period_lower_decile_current_essential_fulfilment": statistics.mean(
                r.lower_decile_current_essential_fulfilment for r in self.period_results),
            "worst_period_minimum_current_essential_fulfilment": min(
                r.minimum_current_essential_fulfilment for r in self.period_results),
            "ending_essential_backlog": self.period_results[-1].closing_essential_backlog,
            "ending_care_service_backlog": self.period_results[-1].closing_essential_backlog,
            "peak_essential_backlog": max(
                r.closing_essential_backlog for r in self.period_results),
            "peak_care_service_backlog": max(
                r.closing_essential_backlog for r in self.period_results),
            "physical_economy": self.engine.summary(),
        }
