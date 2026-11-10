"""Stage-B SCCE dynamic physical economy.

A seven-cell production network with endogenous production, inventories,
intermediate-input matching, local household/community consumption, ecological
resource stocks and four coordination regimes. Standard library + the Stage-A
coordination kernel only. Money, credit, ownership and wages are intentionally
outside this physical-layer experiment and must be integrated in a later stage.
"""
from __future__ import annotations

import argparse
import json
import random
from dataclasses import dataclass, field
from typing import Dict, Mapping, Sequence

from cellular_coordination import (
    Cell as MatchCell,
    World as MatchWorld,
    Allocation,
    allocate_cellular,
    allocate_central,
    allocate_cooperative,
    allocate_market,
)

EPS = 1e-9

PRODUCTS = ("food", "materials", "energy", "machinery",
            "logistics", "software", "care", "raw_resource")
FINAL_PRODUCTS = ("food", "machinery", "logistics", "software", "care")
INPUT_PRODUCTS = ("materials", "energy", "raw_resource")
BASE_PRICES = {
    "food": 4.0, "materials": 2.2, "energy": 2.0,
    "machinery": 7.0, "logistics": 3.0, "software": 6.0,
    "care": 3.5, "raw_resource": 0.8,
}
POLICIES = ("market", "central", "cooperative", "cellular")


class DynamicEconomyError(ValueError):
    pass


@dataclass(frozen=True)
class CellSpec:
    cell_id: str
    sector: str
    output: str
    capacity: float
    labour: float
    productivity: float
    recipe: Mapping[str, float]
    final_demand: Mapping[str, float]
    priorities: Mapping[str, float]
    initial_stocks: Mapping[str, float]
    resource_regeneration: float = 0.35
    resource_capacity: float = 18.0
    safety_stock: float = 0.45


@dataclass
class CellState:
    spec: CellSpec
    stocks: Dict[str, float]
    capital: float = 1.0
    last_external_orders: float = 0.0
    output_this_period: float = 0.0
    cumulative_output: float = 0.0
    cumulative_input_shortage: float = 0.0
    cumulative_unmet_final: float = 0.0


@dataclass
class PeriodResult:
    period: int
    output_by_product: Dict[str, float]
    final_consumption_by_product: Dict[str, float]
    final_demand_by_product: Dict[str, float]
    essential_fulfilment: float
    weighted_fulfilment: float
    unmet_final_units: float
    input_shortage_units: float
    logistics_cost: float
    coordination_cost: float
    raw_resource_used: float
    raw_resource_stock: float
    fixed_price_gross_output: float
    fixed_price_final_consumption: float
    cell_fulfilment_gini: float


class DynamicCellularEconomy:
    def __init__(self, policy: str = "cellular", seed: int = 1,
                 shock: str = "none", cellular_hops: int = 2,
                 specs: Sequence[CellSpec] | None = None,
                 transport_cost_per_hop: float = 0.035,
                 transaction_cost: float = 0.12):
        if policy not in POLICIES:
            raise DynamicEconomyError("unknown policy: " + policy)
        if cellular_hops < 1:
            raise DynamicEconomyError("cellular_hops must be >= 1")
        self.policy = policy
        self.seed = seed
        self.shock = shock
        self.cellular_hops = cellular_hops
        self.rng = random.Random(seed)
        self.specs = tuple(specs or self.default_specs(seed))
        if len(self.specs) != 7 or len({s.cell_id for s in self.specs}) != 7:
            raise DynamicEconomyError("exactly seven unique production cells required")
        self.cells = {
            s.cell_id: CellState(s, {p: float(s.initial_stocks.get(p, 0.0))
                                     for p in PRODUCTS})
            for s in self.specs
        }
        self.edges = (
            ("cell-1", "cell-2"), ("cell-2", "cell-3"),
            ("cell-3", "cell-4"), ("cell-4", "cell-5"),
            ("cell-5", "cell-6"), ("cell-6", "cell-7"),
            ("cell-7", "cell-1"), ("cell-1", "cell-4"),
            ("cell-3", "cell-6"),
        )
        self.transport_cost_per_hop = transport_cost_per_hop
        self.transaction_cost = transaction_cost
        self.periods: list[PeriodResult] = []
        self.events: list[dict] = []
        self.event_keys: set[str] = set()
        self.initial_resource = sum(c.stocks["raw_resource"] for c in self.cells.values())
        self.total_regenerated = 0.0
        self.total_resource_used = 0.0
        self.total_logistics = 0.0
        self.total_coordination = 0.0
        self._validate_specs()

    @staticmethod
    def default_specs(seed: int = 1) -> tuple[CellSpec, ...]:
        rng = random.Random(seed)
        rows = [
            ("cell-1", "food", "food", 8.0, 8.0, 1.18,
             {"materials": .18, "energy": .25},
             {"food": 1.35, "care": .32, "machinery": .08, "logistics": .12, "software": .10},
             {"food": 2.0, "care": 1.8}),
            ("cell-2", "materials", "materials", 8.0, 7.0, 1.02,
             {"raw_resource": .34, "energy": .08},
             {"food": 1.35, "care": .32, "machinery": .08, "logistics": .12, "software": .10},
             {"food": 2.0, "care": 1.8}),
            ("cell-3", "energy", "energy", 9.0, 8.0, 1.28,
             {"raw_resource": .42, "materials": .10},
             {"food": 1.35, "care": .32, "machinery": .08, "logistics": .12, "software": .10},
             {"food": 2.0, "care": 1.8}),
            ("cell-4", "machinery", "machinery", 4.0, 5.0, .86,
             {"materials": .46, "energy": .30},
             {"food": 1.35, "care": .32, "machinery": .08, "logistics": .12, "software": .10},
             {"food": 2.0, "care": 1.8}),
            ("cell-5", "logistics", "logistics", 5.0, 5.0, 1.08,
             {"materials": .12, "energy": .38},
             {"food": 1.35, "care": .32, "machinery": .08, "logistics": .12, "software": .10},
             {"food": 2.0, "care": 1.8}),
            ("cell-6", "software", "software", 4.0, 4.0, 1.30,
             {"materials": .025, "energy": .12},
             {"food": 1.35, "care": .32, "machinery": .08, "logistics": .12, "software": .10},
             {"food": 2.0, "care": 1.8}),
            ("cell-7", "care", "care", 6.0, 7.0, .94,
             {"materials": .04, "energy": .16},
             {"food": 1.35, "care": .32, "machinery": .08, "logistics": .12, "software": .10},
             {"food": 2.0, "care": 1.8}),
        ]
        specs = []
        for cid, sector, output, cap, labour, prod, recipe, basket, priority in rows:
            jitter = rng.uniform(.96, 1.04)
            demand_jitter = {p: q * rng.uniform(.94, 1.06) for p, q in basket.items()}
            priorities = {p: priority.get(p, 1.0) for p in FINAL_PRODUCTS}
            stocks = {
                "food": 0.0, "materials": 0.0, "energy": 0.0,
                "machinery": 0.0, "logistics": 0.0, "software": 0.0,
                "care": 0.0, "raw_resource": rng.uniform(7.0, 11.0),
            }
            stocks[output] = 1.2 if output in FINAL_PRODUCTS else 0.0
            if cid in ("cell-1", "cell-4", "cell-5", "cell-6", "cell-7"):
                stocks["materials"] += rng.uniform(1.0, 2.5)
            if cid in ("cell-1", "cell-2", "cell-4", "cell-5", "cell-6", "cell-7"):
                stocks["energy"] += rng.uniform(1.0, 2.2)
            if cid == "cell-2":
                stocks["materials"] = 3.0
            if cid == "cell-3":
                stocks["energy"] = 3.0
            specs.append(CellSpec(
                cid, sector, output, cap * jitter, labour, prod, recipe,
                demand_jitter, priorities, stocks,
                resource_regeneration=.32, resource_capacity=18.0,
                safety_stock=.35,
            ))
        return tuple(specs)

    def _validate_specs(self):
        ids = {s.cell_id for s in self.specs}
        if ids != {f"cell-{i}" for i in range(1, 8)}:
            raise DynamicEconomyError("the Stage-B topology expects cell-1 through cell-7")
        outputs = [s.output for s in self.specs]
        if set(outputs) != set(("food", "materials", "energy", "machinery",
                                "logistics", "software", "care")):
            raise DynamicEconomyError("each production product must have one producer")
        for s in self.specs:
            if min(s.capacity, s.labour, s.productivity, s.resource_regeneration,
                   s.resource_capacity, s.safety_stock) < 0:
                raise DynamicEconomyError("negative production or resource parameter")
            if any(v < 0 for v in s.recipe.values()) or any(v < 0 for v in s.final_demand.values()):
                raise DynamicEconomyError("negative recipe or demand")
            if not set(s.recipe).issubset(INPUT_PRODUCTS):
                raise DynamicEconomyError("unknown intermediate input")
            if not set(s.final_demand).issubset(FINAL_PRODUCTS):
                raise DynamicEconomyError("unknown final-demand product")

    def _shock_values(self, period: int):
        if period < 4:
            return 1.0, 1.0, 1.0
        if self.shock == "none":
            return 1.0, 1.0, 1.0
        if self.shock == "demand_surge":
            return 1.30, 1.0, 1.0
        if self.shock == "resource_shock":
            return 1.0, .48, 1.0
        if self.shock == "productivity_shock":
            return 1.0, 1.0, .62
        if self.shock == "compound":
            return 1.20, .58, .78
        raise DynamicEconomyError("unknown shock: " + self.shock)

    def _record(self, kind: str, payload: dict, key: str):
        if key in self.event_keys:
            raise DynamicEconomyError("duplicate event key: " + key)
        self.events.append({"sequence": len(self.events) + 1, "type": kind,
                            "payload": payload, "key": key})
        self.event_keys.add(key)

    def _matching_world(self, supply: Mapping[str, Mapping[str, float]],
                        demand: Mapping[str, Mapping[str, float]],
                        priorities: Mapping[str, Mapping[str, float]] | None = None):
        cells = []
        for cid in sorted(self.cells):
            s, d = {}, {}
            for p in PRODUCTS:
                sq = max(0.0, float(supply.get(p, {}).get(cid, 0.0)))
                dq = max(0.0, float(demand.get(p, {}).get(cid, 0.0)))
                if sq > EPS:
                    s[p] = sq
                if dq > EPS:
                    d[p] = dq
            pr = {p: float((priorities or {}).get(cid, {}).get(p, 1.0))
                  for p in PRODUCTS}
            bid = {p: BASE_PRICES[p] * (1.0 + .10 * pr[p]) for p in PRODUCTS}
            cells.append(MatchCell(cid, s, d, pr, bid))
        return MatchWorld(tuple(cells), self.edges, BASE_PRICES,
                          self.transport_cost_per_hop, self.transaction_cost)

    def _allocate(self, world: MatchWorld) -> list[Allocation]:
        if self.policy == "market":
            return allocate_market(world)
        if self.policy == "central":
            return allocate_central(world)
        if self.policy == "cooperative":
            return allocate_cooperative(world)
        return allocate_cellular(world, max_hops=self.cellular_hops, max_rounds=12)

    def _apply_allocations(self, allocations: Sequence[Allocation],
                           period: int, stage: str):
        by_product = {p: 0.0 for p in PRODUCTS}
        by_seller_product: Dict[tuple[str, str], float] = {}
        logistics = coordination = 0.0
        for a in allocations:
            if a.seller == a.buyer:
                raise DynamicEconomyError("self-trade is forbidden")
            seller = self.cells[a.seller]
            buyer = self.cells[a.buyer]
            if seller.stocks[a.product] + EPS < a.quantity:
                raise DynamicEconomyError("allocation exceeds seller stock")
            seller.stocks[a.product] -= a.quantity
            buyer.stocks[a.product] += a.quantity
            by_product[a.product] += a.quantity
            key = (a.seller, a.product)
            by_seller_product[key] = by_seller_product.get(key, 0.0) + a.quantity
            logistics += a.quantity * a.distance * self.transport_cost_per_hop
            coordination += self.transaction_cost
            self._record(stage, {"product": a.product, "seller": a.seller,
                                 "buyer": a.buyer, "quantity": round(a.quantity, 10),
                                 "distance": a.distance},
                         f"{stage}:{period}:{a.product}:{a.seller}:{a.buyer}")
        return by_product, by_seller_product, logistics, coordination

    def step(self, period: int) -> PeriodResult:
        demand_mult, resource_mult, productivity_mult = self._shock_values(period)
        # Local ecological regeneration is bounded by each cell's resource capacity.
        regenerated = 0.0
        for c in self.cells.values():
            before = c.stocks["raw_resource"]
            c.stocks["raw_resource"] = min(
                c.spec.resource_capacity,
                before + c.spec.resource_regeneration * resource_mult)
            regenerated += c.stocks["raw_resource"] - before
        self.total_regenerated += regenerated

        # Each producer plans from its own community's demand, its last observed
        # external orders and its own inventory. No current global demand oracle.
        plans: Dict[str, float] = {}
        input_need: Dict[str, Dict[str, float]] = {p: {} for p in INPUT_PRODUCTS}
        for cid, c in self.cells.items():
            s = c.spec
            local_need = s.final_demand.get(s.output, 0.0) * demand_mult
            target = local_need + c.last_external_orders + s.safety_stock
            desired = max(0.0, target - c.stocks[s.output])
            cap = min(s.capacity, s.labour * s.productivity) * c.capital * productivity_mult
            plans[cid] = min(cap, desired)
            for inp in INPUT_PRODUCTS:
                input_need[inp][cid] = plans[cid] * s.recipe.get(inp, 0.0)

        # Reserve each cell's own inputs before offering surplus to neighbours.
        input_supply: Dict[str, Dict[str, float]] = {p: {} for p in INPUT_PRODUCTS}
        input_demand: Dict[str, Dict[str, float]] = {p: {} for p in INPUT_PRODUCTS}
        for p in INPUT_PRODUCTS:
            for cid, c in self.cells.items():
                need = input_need[p][cid]
                local_use = min(c.stocks[p], need)
                shortage = max(0.0, need - local_use)
                offer = max(0.0, c.stocks[p] - local_use)
                input_supply[p][cid] = offer
                input_demand[p][cid] = shortage
        input_world = self._matching_world(input_supply, input_demand)
        input_allocations = self._allocate(input_world)
        _, input_seller_deliveries, input_logistics, input_coordination = self._apply_allocations(
            input_allocations, period, "intermediate.input.delivery")

        # Production is constrained by the inputs actually on hand. No input or
        # output is created by the matching protocol itself.
        output_by_product = {p: 0.0 for p in FINAL_PRODUCTS + ("materials", "energy")}
        total_input_shortage = 0.0
        raw_used = 0.0
        for cid, c in self.cells.items():
            s = c.spec
            q = plans[cid]
            for inp, coeff in s.recipe.items():
                required = q * coeff
                available = c.stocks[inp]
                if required > available + EPS:
                    total_input_shortage += required - available
                    q = min(q, available / coeff if coeff > 0 else q)
            q = max(0.0, min(q, s.capacity, s.labour * s.productivity * productivity_mult))
            for inp, coeff in s.recipe.items():
                used = q * coeff
                c.stocks[inp] = max(0.0, c.stocks[inp] - used)
                if inp == "raw_resource":
                    raw_used += used
            c.stocks[s.output] += q
            c.output_this_period = q
            c.cumulative_output += q
            output_by_product[s.output] = output_by_product.get(s.output, 0.0) + q
            self._record("production", {"cell": cid, "product": s.output,
                                        "quantity": round(q, 10),
                                        "planned": round(plans[cid], 10)},
                         f"production:{period}:{cid}")

        self.total_resource_used += raw_used

        # First satisfy each cell's own community from its local inventory.
        final_demand = {p: {} for p in FINAL_PRODUCTS}
        own_consumption = {p: 0.0 for p in FINAL_PRODUCTS}
        unmet_by_cell = {cid: 0.0 for cid in self.cells}
        priority_by_cell = {cid: {} for cid in self.cells}
        demand_by_cell: Dict[str, Dict[str, float]] = {cid: {} for cid in self.cells}
        served_by_cell = {cid: 0.0 for cid in self.cells}
        weighted_demand = weighted_served = total_demand = 0.0
        for cid, c in self.cells.items():
            for p in FINAL_PRODUCTS:
                need = c.spec.final_demand.get(p, 0.0) * demand_mult
                local = min(c.stocks[p], need)
                c.stocks[p] -= local
                own_consumption[p] += local
                remaining = max(0.0, need - local)
                final_demand[p][cid] = remaining
                demand_by_cell[cid][p] = need
                priority = c.spec.priorities.get(p, 1.0)
                priority_by_cell[cid][p] = priority
                total_demand += need
                weighted_demand += need * priority
                served_by_cell[cid] += local
                weighted_served += local * priority

        # Remaining demand is matched through the same institutional rule.
        final_supply = {p: {cid: c.stocks[p] for cid, c in self.cells.items()}
                        for p in FINAL_PRODUCTS}
        final_world = self._matching_world(final_supply, final_demand, priority_by_cell)
        final_allocations = self._allocate(final_world)
        _, seller_product_deliveries, final_logistics, final_coordination = self._apply_allocations(
            final_allocations, period, "final.goods.delivery")
        for a in final_allocations:
            buyer = self.cells[a.buyer]
            buyer.stocks[a.product] = max(0.0, buyer.stocks[a.product] - a.quantity)
            served_by_cell[a.buyer] += a.quantity
            priority = buyer.spec.priorities.get(a.product, 1.0)
            weighted_served += a.quantity * priority
        for cid, c in self.cells.items():
            cell_demand = sum(demand_by_cell[cid].values())
            cell_served = served_by_cell[cid]
            unmet_by_cell[cid] = max(0.0, cell_demand - cell_served)
            c.cumulative_unmet_final += unmet_by_cell[cid]
            c.last_external_orders = (
                input_seller_deliveries.get((cid, c.spec.output), 0.0)
                + seller_product_deliveries.get((cid, c.spec.output), 0.0)
            )

        final_consumption = {
            p: own_consumption[p] + sum(a.quantity for a in final_allocations if a.product == p)
            for p in FINAL_PRODUCTS
        }
        final_demand_totals = {
            p: sum(c.spec.final_demand.get(p, 0.0) * demand_mult for c in self.cells.values())
            for p in FINAL_PRODUCTS
        }
        essential_demand = final_demand_totals["food"] + final_demand_totals["care"]
        essential_served = final_consumption["food"] + final_consumption["care"]
        essential_fulfilment = essential_served / essential_demand if essential_demand else 1.0
        weighted_fulfilment = weighted_served / weighted_demand if weighted_demand else 1.0
        cell_rates = []
        for cid in self.cells:
            d = sum(demand_by_cell[cid].values())
            cell_rates.append(served_by_cell[cid] / d if d else 1.0)
        gini = self._gini(cell_rates)
        logistics = input_logistics + final_logistics
        coordination = input_coordination + final_coordination
        self.total_logistics += logistics
        self.total_coordination += coordination
        fixed_gross = sum(output_by_product.get(p, 0.0) * BASE_PRICES[p]
                          for p in output_by_product)
        fixed_consumption = sum(final_consumption[p] * BASE_PRICES[p]
                                for p in FINAL_PRODUCTS)
        resource_stock = sum(c.stocks["raw_resource"] for c in self.cells.values())
        result = PeriodResult(
            period, output_by_product, final_consumption, final_demand_totals,
            essential_fulfilment, weighted_fulfilment,
            max(0.0, total_demand - sum(served_by_cell.values())),
            total_input_shortage, logistics, coordination, raw_used,
            resource_stock, fixed_gross, fixed_consumption, gini,
        )
        self.periods.append(result)
        return result

    @staticmethod
    def _gini(values):
        vals = sorted(max(0.0, float(v)) for v in values)
        total = sum(vals)
        if not vals or total <= EPS:
            return 0.0
        n = len(vals)
        return sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(vals)) / (n * total)

    def run(self, periods: int = 24):
        if periods < 1:
            raise DynamicEconomyError("periods must be positive")
        for t in range(1, periods + 1):
            self.step(t)
        return self.periods

    def validate(self):
        for cid, c in self.cells.items():
            for p, q in c.stocks.items():
                if q < -EPS:
                    raise DynamicEconomyError(f"negative stock {cid}:{p}={q}")
            if c.capital <= 0:
                raise DynamicEconomyError("non-positive capital")
        ending_resource = sum(c.stocks["raw_resource"] for c in self.cells.values())
        if abs(self.initial_resource + self.total_regenerated
               - self.total_resource_used - ending_resource) > 1e-6:
            raise DynamicEconomyError("raw resource stock-flow identity violated")
        for period in self.periods:
            if not 0 <= period.essential_fulfilment <= 1 + EPS:
                raise DynamicEconomyError("essential fulfilment outside [0,1]")
            if not 0 <= period.weighted_fulfilment <= 1 + EPS:
                raise DynamicEconomyError("weighted fulfilment outside [0,1]")
        return True

    def summary(self):
        if not self.periods:
            raise DynamicEconomyError("run the economy before requesting summary")
        output = {p: sum(r.output_by_product.get(p, 0.0) for r in self.periods)
                  for p in FINAL_PRODUCTS + ("materials", "energy")}
        consumption = {p: sum(r.final_consumption_by_product.get(p, 0.0)
                               for r in self.periods) for p in FINAL_PRODUCTS}
        total_demand = sum(sum(r.final_demand_by_product.values()) for r in self.periods)
        total_consumed = sum(sum(r.final_consumption_by_product.values()) for r in self.periods)
        return {
            "policy": self.policy, "shock": self.shock, "seed": self.seed,
            "periods": len(self.periods), "cellular_hops": self.cellular_hops,
            "cumulative_output_by_product": output,
            "cumulative_final_consumption_by_product": consumption,
            "cumulative_final_demand": total_demand,
            "cumulative_final_consumption": total_consumed,
            "final_fulfilment_rate": total_consumed / total_demand if total_demand else 1.0,
            "mean_essential_fulfilment": sum(r.essential_fulfilment for r in self.periods) / len(self.periods),
            "mean_weighted_fulfilment": sum(r.weighted_fulfilment for r in self.periods) / len(self.periods),
            "mean_cell_fulfilment_gini": sum(r.cell_fulfilment_gini for r in self.periods) / len(self.periods),
            "cumulative_unmet_final_units": sum(r.unmet_final_units for r in self.periods),
            "cumulative_input_shortage_units": sum(r.input_shortage_units for r in self.periods),
            "fixed_price_gross_output_index": sum(r.fixed_price_gross_output for r in self.periods),
            "fixed_price_final_consumption_index": sum(r.fixed_price_final_consumption for r in self.periods),
            "total_logistics_cost": self.total_logistics,
            "total_coordination_cost": self.total_coordination,
            "total_raw_resource_used": self.total_resource_used,
            "initial_raw_resource": self.initial_resource,
            "regenerated_raw_resource": self.total_regenerated,
            "ending_raw_resource": sum(c.stocks["raw_resource"] for c in self.cells.values()),
            "ending_inventory_value": sum(
                c.stocks[p] * BASE_PRICES[p] for c in self.cells.values() for p in PRODUCTS
            ),
            "events": len(self.events),
            "event_log_digest": __import__("hashlib").sha256(
                json.dumps(self.events, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest(),
        }


def compare(seed: int = 1, shock: str = "none", periods: int = 24,
            cellular_hops: int = 2):
    results = {}
    for policy in POLICIES:
        model = DynamicCellularEconomy(policy, seed, shock, cellular_hops)
        model.run(periods)
        model.validate()
        results[policy] = model.summary()
    return results


def monte_carlo(runs: int = 100, shock: str = "none", periods: int = 24,
                cellular_hops: int = 2):
    if runs < 1:
        raise DynamicEconomyError("runs must be positive")
    paired = []
    for seed in range(1, runs + 1):
        result = compare(seed, shock, periods, cellular_hops)
        for policy, metrics in result.items():
            paired.append({"seed": seed, **metrics})
    grouped = {}
    for policy in POLICIES:
        rows = [r for r in paired if r["policy"] == policy]
        keys = [k for k, v in rows[0].items() if isinstance(v, (int, float))
                and k not in ("seed", "periods", "cellular_hops", "events")]
        grouped[policy] = {
            key: sum(float(r[key]) for r in rows) / len(rows) for key in keys
        }
    return {"runs": runs, "shock": shock, "periods": periods,
            "cellular_hops": cellular_hops, "summary": grouped, "paired_runs": paired}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--policy", choices=POLICIES, default="cellular")
    parser.add_argument("--seed", type=int, default=1)
    parser.add_argument("--shock", choices=("none", "demand_surge", "resource_shock",
                                             "productivity_shock", "compound"), default="none")
    parser.add_argument("--periods", type=int, default=24)
    parser.add_argument("--hops", type=int, default=2)
    parser.add_argument("--compare", action="store_true")
    parser.add_argument("--monte-carlo", type=int, default=0)
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    if args.monte_carlo:
        result = monte_carlo(args.monte_carlo, args.shock, args.periods, args.hops)
        if args.summary_only:
            result.pop("paired_runs", None)
    elif args.compare:
        result = compare(args.seed, args.shock, args.periods, args.hops)
    else:
        model = DynamicCellularEconomy(args.policy, args.seed, args.shock, args.hops)
        model.run(args.periods)
        model.validate()
        result = model.summary()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
