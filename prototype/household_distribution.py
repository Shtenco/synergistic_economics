"""Stage-C1 physical distribution from economic cells to households.

This module is intentionally money-free. It distributes quantities already
available inside each cell; it does not create goods, transfer goods between
cells, or claim to measure utility or welfare.
"""
from __future__ import annotations

import math
import random
import statistics
from dataclasses import dataclass
from typing import Dict, Mapping, Sequence


EPS = 1e-10
POLICIES = ("proportional", "priority_weighted")


class HouseholdDistributionError(ValueError):
    pass


@dataclass(frozen=True)
class Household:
    household_id: str
    cell_id: str
    essential_needs: Mapping[str, float]
    discretionary_needs: Mapping[str, float]
    essential_priority: float = 1.0
    discretionary_priority: float = 1.0


@dataclass(frozen=True)
class HouseholdAllocation:
    household_id: str
    cell_id: str
    essential_served: Mapping[str, float]
    discretionary_served: Mapping[str, float]


def _gini(values: Sequence[float]) -> float:
    vals = [max(0.0, float(v)) for v in values]
    if not vals:
        return 0.0
    mean = statistics.mean(vals)
    if mean <= EPS:
        return 0.0
    return sum(abs(a - b) for a in vals for b in vals) / (
        2.0 * len(vals) ** 2 * mean
    )


def _waterfill(needs: Mapping[str, float], weights: Mapping[str, float],
               capacity: float) -> Dict[str, float]:
    remaining = {k: max(0.0, float(v)) for k, v in needs.items()}
    result = {k: 0.0 for k in remaining}
    left = max(0.0, float(capacity))
    active = {k for k, q in remaining.items() if q > EPS}
    while active and left > EPS:
        total_weight = sum(max(EPS, float(weights.get(k, 1.0))) for k in active)
        if total_weight <= EPS:
            break
        level = left / total_weight
        saturated = [
            k for k in active
            if remaining[k] <= level * max(EPS, float(weights.get(k, 1.0))) + EPS
        ]
        if saturated:
            for k in sorted(saturated):
                q = remaining[k]
                result[k] += q
                left -= q
                remaining[k] = 0.0
                active.remove(k)
        else:
            for k in sorted(active):
                q = level * max(EPS, float(weights.get(k, 1.0)))
                result[k] += q
                remaining[k] -= q
            left = 0.0
    return result


def _allocate_group(households: Sequence[Household], product: str,
                    needs: Mapping[str, float], weights: Mapping[str, float],
                    capacity: float, policy: str) -> Dict[str, float]:
    if policy == "proportional":
        total = sum(needs.values())
        if total <= EPS:
            return {h.household_id: 0.0 for h in households}
        ratio = min(1.0, max(0.0, capacity) / total)
        return {h.household_id: needs[h.household_id] * ratio for h in households}
    return _waterfill(needs, weights, capacity)


def allocate_households(
    households: Sequence[Household],
    cell_supply: Mapping[str, Mapping[str, float]],
    policy: str = "proportional",
) -> tuple[HouseholdAllocation, ...]:
    """Allocate each cell's available product stocks to its own households.

    Essential claims are served before discretionary claims within each cell
    and product. No household can receive more than its declared demand.
    """
    if policy not in POLICIES:
        raise HouseholdDistributionError("unknown household allocation policy")
    ids = [h.household_id for h in households]
    if not households or len(ids) != len(set(ids)):
        raise HouseholdDistributionError("household ids must be unique and non-empty")
    known_cells = set(cell_supply)
    for h in households:
        if h.cell_id not in known_cells:
            raise HouseholdDistributionError("household references unknown cell")
        if h.essential_priority <= 0 or h.discretionary_priority <= 0:
            raise HouseholdDistributionError("household priorities must be positive")
        if any(float(q) < 0 for q in h.essential_needs.values()):
            raise HouseholdDistributionError("negative essential need")
        if any(float(q) < 0 for q in h.discretionary_needs.values()):
            raise HouseholdDistributionError("negative discretionary need")
    for cid, stocks in cell_supply.items():
        if any(float(q) < -EPS for q in stocks.values()):
            raise HouseholdDistributionError("negative cell supply")

    by_cell: Dict[str, list[Household]] = {cid: [] for cid in known_cells}
    for h in households:
        by_cell[h.cell_id].append(h)

    essential_out = {h.household_id: {} for h in households}
    discretionary_out = {h.household_id: {} for h in households}

    for cid in sorted(known_cells):
        members = sorted(by_cell[cid], key=lambda h: h.household_id)
        products = sorted({
            p for h in members
            for p in set(h.essential_needs) | set(h.discretionary_needs)
        } | set(cell_supply[cid]))
        for product in products:
            # Clamp only numerical residue; material negative stocks remain invalid.
            available = max(0.0, float(cell_supply[cid].get(product, 0.0)))
            essential_needs = {
                h.household_id: float(h.essential_needs.get(product, 0.0))
                for h in members
            }
            essential_weights = {
                h.household_id: h.essential_priority for h in members
            }
            essential = _allocate_group(
                members, product, essential_needs, essential_weights,
                available, policy,
            )
            for h in members:
                essential_out[h.household_id][product] = essential.get(h.household_id, 0.0)
            available = max(0.0, available - sum(essential.values()))

            discretionary_needs = {
                h.household_id: float(h.discretionary_needs.get(product, 0.0))
                for h in members
            }
            discretionary_weights = {
                h.household_id: h.discretionary_priority for h in members
            }
            discretionary = _allocate_group(
                members, product, discretionary_needs, discretionary_weights,
                available, policy,
            )
            for h in members:
                discretionary_out[h.household_id][product] = discretionary.get(
                    h.household_id, 0.0
                )

    return tuple(
        HouseholdAllocation(h.household_id, h.cell_id,
                            dict(essential_out[h.household_id]),
                            dict(discretionary_out[h.household_id]))
        for h in sorted(households, key=lambda x: x.household_id)
    )


def generate_synthetic_households(
    cell_demand: Mapping[str, Mapping[str, float]],
    households_per_cell: int = 10,
    seed: int = 1,
    essential_products: Sequence[str] = ("food", "care"),
) -> tuple[Household, ...]:
    """Split cell demand into reproducible heterogeneous synthetic households."""
    if households_per_cell < 1:
        raise HouseholdDistributionError("households_per_cell must be positive")
    rng = random.Random(seed)
    essential_set = set(essential_products)
    households = []
    for cid in sorted(cell_demand):
        shares = [rng.expovariate(1.0) for _ in range(households_per_cell)]
        total_share = sum(shares)
        shares = [x / total_share for x in shares]
        essential = [{} for _ in range(households_per_cell)]
        discretionary = [{} for _ in range(households_per_cell)]
        for product, total in sorted(cell_demand[cid].items()):
            quantity = float(total)
            if not math.isfinite(quantity) or quantity < 0:
                raise HouseholdDistributionError("invalid synthetic cell demand")
            target = essential if product in essential_set else discretionary
            for index, share in enumerate(shares):
                target[index][product] = quantity * share
        for index in range(households_per_cell):
            households.append(Household(
                f"{cid}-hh-{index + 1:03d}", cid,
                essential[index], discretionary[index],
                essential_priority=rng.uniform(0.8, 2.0),
                discretionary_priority=rng.uniform(0.8, 1.2),
            ))
    return tuple(households)


def allocate_period_households(
    households: Sequence[Household],
    period_result,
    policy: str = "proportional",
) -> tuple[HouseholdAllocation, ...]:
    """Distribute Stage-B cell consumption without counting it a second time.

    The adapter consumes PeriodResult.final_consumption_by_cell, which is the
    physical quantity already counted as cell-level final consumption.
    Returned household allocations are a disaggregation of that same quantity,
    not an additional delivery or consumption event.
    """
    cell_supply = getattr(period_result, "final_consumption_by_cell", None)
    if not isinstance(cell_supply, Mapping):
        raise HouseholdDistributionError(
            "period result must expose final_consumption_by_cell"
        )
    return allocate_households(households, cell_supply, policy)


def evaluate_households(
    households: Sequence[Household],
    allocations: Sequence[HouseholdAllocation],
) -> Dict[str, object]:
    by_id = {a.household_id: a for a in allocations}
    if len(by_id) != len(allocations) or set(by_id) != {h.household_id for h in households}:
        raise HouseholdDistributionError("allocation set does not match households")

    for h in households:
        allocation = by_id[h.household_id]
        if allocation.cell_id != h.cell_id:
            raise HouseholdDistributionError("cross-cell household allocation")
        for product, quantity in allocation.essential_served.items():
            if (quantity < -EPS
                    or quantity > float(h.essential_needs.get(product, 0.0)) + EPS):
                raise HouseholdDistributionError("essential allocation exceeds need")
        for product, quantity in allocation.discretionary_served.items():
            if (quantity < -EPS
                    or quantity > float(h.discretionary_needs.get(product, 0.0)) + EPS):
                raise HouseholdDistributionError("discretionary allocation exceeds need")

    essential_demand = essential_served = 0.0
    total_demand = total_served = 0.0
    per_household = {}
    per_product = {}
    for h in households:
        a = by_id[h.household_id]
        h_essential_demand = sum(float(q) for q in h.essential_needs.values())
        h_essential_served = sum(
            min(float(q), float(a.essential_served.get(p, 0.0)))
            for p, q in h.essential_needs.items()
        )
        h_total_demand = h_essential_demand + sum(
            float(q) for q in h.discretionary_needs.values()
        )
        h_total_served = h_essential_served + sum(
            min(float(q), float(a.discretionary_served.get(p, 0.0)))
            for p, q in h.discretionary_needs.items()
        )
        essential_demand += h_essential_demand
        essential_served += h_essential_served
        total_demand += h_total_demand
        total_served += h_total_served
        per_household[h.household_id] = {
            "essential_fulfilment": (
                h_essential_served / h_essential_demand
                if h_essential_demand > EPS else 1.0
            ),
            "overall_fulfilment": (
                h_total_served / h_total_demand if h_total_demand > EPS else 1.0
            ),
            "essential_demand": h_essential_demand,
            "essential_served": h_essential_served,
            "total_demand": h_total_demand,
            "total_served": h_total_served,
        }
        for product, need in h.essential_needs.items():
            item = per_product.setdefault(product, {"demand": 0.0, "served": 0.0})
            item["demand"] += float(need)
            item["served"] += min(float(need), float(a.essential_served.get(product, 0.0)))

    essential_rates = [v["essential_fulfilment"] for v in per_household.values()]
    overall_rates = [v["overall_fulfilment"] for v in per_household.values()]
    ordered = sorted(essential_rates)
    lower_decile = ordered[max(0, math.ceil(0.10 * len(ordered)) - 1)] if ordered else 1.0
    return {
        "households": len(households),
        "essential_demand": essential_demand,
        "essential_served": essential_served,
        "essential_fulfilment": essential_served / essential_demand
            if essential_demand > EPS else 1.0,
        "overall_demand": total_demand,
        "overall_served": total_served,
        "overall_fulfilment": total_served / total_demand
            if total_demand > EPS else 1.0,
        "lower_decile_household_essential_fulfilment": lower_decile,
        "minimum_household_essential_fulfilment": min(essential_rates)
            if essential_rates else 1.0,
        "essential_fulfilment_gini": _gini(essential_rates),
        "overall_fulfilment_gini": _gini(overall_rates),
        "per_household": per_household,
        "per_product_essential": {
            p: {**v, "fulfilment": v["served"] / v["demand"] if v["demand"] > EPS else 1.0}
            for p, v in per_product.items()
        },
    }


def compare_household_distribution_policies(
    period_result,
    households_per_cell: int = 10,
    seed: int = 1,
) -> Dict[str, object]:
    """Compare both rules on the same Stage-B supplies and household needs."""
    demand = getattr(period_result, "final_demand_by_cell", None)
    supply = getattr(period_result, "final_consumption_by_cell", None)
    if not isinstance(demand, Mapping) or not isinstance(supply, Mapping):
        raise HouseholdDistributionError(
            "period result must expose final_demand_by_cell and final_consumption_by_cell"
        )
    households = generate_synthetic_households(
        demand, households_per_cell=households_per_cell, seed=seed)
    results = {}
    for policy in POLICIES:
        allocations = allocate_period_households(households, period_result, policy)
        validate_household_allocation(households, supply, allocations)
        results[policy] = evaluate_households(households, allocations)
    return {
        "seed": seed,
        "households_per_cell": households_per_cell,
        "household_count": len(households),
        "policies": results,
    }


def validate_household_allocation(
    households: Sequence[Household],
    cell_supply: Mapping[str, Mapping[str, float]],
    allocations: Sequence[HouseholdAllocation],
) -> bool:
    """Check no creation, no cross-cell transfer and no over-fulfilment."""
    by_id = {a.household_id: a for a in allocations}
    if len(by_id) != len(allocations) or set(by_id) != {h.household_id for h in households}:
        raise HouseholdDistributionError("allocation set does not match households")
    if any(float(q) < -EPS for stocks in cell_supply.values() for q in stocks.values()):
        raise HouseholdDistributionError("negative cell supply")
    used: Dict[tuple[str, str], float] = {}
    household_used: Dict[tuple[str, str, str], float] = {}
    needs = {h.household_id: h for h in households}
    for a in allocations:
        h = needs[a.household_id]
        if a.cell_id != h.cell_id:
            raise HouseholdDistributionError("cross-cell household allocation")
        for p, q in a.essential_served.items():
            if q < -EPS:
                raise HouseholdDistributionError("negative essential allocation")
            household_used[(h.household_id, "essential", p)] = (
                household_used.get((h.household_id, "essential", p), 0.0) + q)
            used[(a.cell_id, p)] = used.get((a.cell_id, p), 0.0) + q
        for p, q in a.discretionary_served.items():
            if q < -EPS:
                raise HouseholdDistributionError("negative discretionary allocation")
            household_used[(h.household_id, "discretionary", p)] = (
                household_used.get((h.household_id, "discretionary", p), 0.0) + q)
            used[(a.cell_id, p)] = used.get((a.cell_id, p), 0.0) + q
    for (household_id, need_type, product), quantity in household_used.items():
        h = needs[household_id]
        limit = (h.essential_needs if need_type == "essential"
                 else h.discretionary_needs).get(product, 0.0)
        if quantity > float(limit) + EPS:
            raise HouseholdDistributionError("household receives more than declared need")
    for (cid, product), quantity in used.items():
        if quantity > max(0.0, float(cell_supply[cid].get(product, 0.0))) + EPS:
            raise HouseholdDistributionError("household allocation exceeds cell supply")
    return True
