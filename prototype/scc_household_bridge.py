"""Post-hoc bridge from Stage-B cell consumption to Stage-C1 households.

This bridge does not change Stage-B production or deliveries. It decomposes
physical quantities already consumed at cell level into household allocations,
so the household layer cannot create a second delivery or additional goods.
"""
from __future__ import annotations

import random
from typing import Mapping, Sequence

from household_distribution import (
    Household,
    HouseholdAllocation,
    allocate_households,
    evaluate_households,
    validate_household_allocation,
)


class HouseholdBridgeError(ValueError):
    pass


def households_from_cell_demand(
    cell_demand: Mapping[str, Mapping[str, float]],
    households_per_cell: int = 5,
    seed: int = 1,
    essential_products: Sequence[str] = ("food", "care"),
    priority_dispersion: float = 0.0,
) -> tuple[Household, ...]:
    """Split each cell's declared product demand into reproducible households.

    Product totals are preserved exactly per cell. Household shares are
    heterogeneous but synthetic; this generator is a test fixture, not a
    substitute for calibrated household survey data.
    """
    if households_per_cell < 1:
        raise HouseholdBridgeError("households_per_cell must be positive")
    if not 0.0 <= priority_dispersion < 1.0:
        raise HouseholdBridgeError("priority_dispersion must be in [0, 1)")
    rng = random.Random(seed)
    essential_set = set(essential_products)
    households: dict[str, dict[str, dict[str, float]]] = {}
    for cell_id in sorted(cell_demand):
        for index in range(households_per_cell):
            household_id = f"{cell_id}:h{index + 1:03d}"
            households[household_id] = {
                "essential": {}, "discretionary": {},
                "essential_priority": rng.uniform(
                    1.0 - priority_dispersion, 1.0 + priority_dispersion),
                "discretionary_priority": rng.uniform(
                    1.0 - priority_dispersion, 1.0 + priority_dispersion),
            }

        for product, total in sorted(cell_demand[cell_id].items()):
            total = float(total)
            if total < 0:
                raise HouseholdBridgeError("negative cell demand")
            raw = [rng.uniform(0.5, 1.5) for _ in range(households_per_cell)]
            denominator = sum(raw)
            shares = [value / denominator for value in raw]
            target = "essential" if product in essential_set else "discretionary"
            allocated = 0.0
            for index, share in enumerate(shares):
                household_id = f"{cell_id}:h{index + 1:03d}"
                quantity = total - allocated if index == households_per_cell - 1 else total * share
                allocated += quantity
                households[household_id][target][product] = quantity

    return tuple(
        Household(
            household_id=household_id,
            cell_id=household_id.rsplit(":h", 1)[0],
            essential_needs=values["essential"],
            discretionary_needs=values["discretionary"],
            essential_priority=values["essential_priority"],
            discretionary_priority=values["discretionary_priority"],
        )
        for household_id, values in sorted(households.items())
    )


def distribute_period_to_households(
    period_result,
    households_per_cell: int = 5,
    policy: str = "proportional",
    seed: int = 1,
    essential_products: Sequence[str] = ("food", "care"),
    priority_dispersion: float = 0.0,
) -> dict:
    """Disaggregate one Stage-B period's cell consumption among households.

    The period result's per-cell final consumption is treated as the complete
    physical stock available to that cell's households for this accounting
    pass. The result is a decomposition of Stage-B consumption, not a new flow.
    """
    try:
        cell_demand = period_result.final_demand_by_cell
        cell_supply = period_result.final_consumption_by_cell
    except AttributeError as exc:
        raise HouseholdBridgeError(
            "period result lacks per-cell demand/consumption snapshots"
        ) from exc

    def clamp_physical_map(values, label):
        normalized = {}
        for cell_id, products in values.items():
            normalized[cell_id] = {}
            for product, quantity in products.items():
                quantity = float(quantity)
                if quantity < -1e-8:
                    raise HouseholdBridgeError(
                        f"negative {label} quantity {cell_id}:{product}={quantity}")
                normalized[cell_id][product] = max(0.0, quantity)
        return normalized

    # Stage-B permits sub-EPS floating-point residue in physical balances.
    # Normalize only tiny negative residue at this accounting boundary.
    cell_demand = clamp_physical_map(cell_demand, "household demand")
    cell_supply = clamp_physical_map(cell_supply, "household supply")
    households = households_from_cell_demand(
        cell_demand, households_per_cell, seed, essential_products,
        priority_dispersion)
    allocations = allocate_households(households, cell_supply, policy)
    validate_household_allocation(households, cell_supply, allocations)
    metrics = evaluate_households(households, allocations)
    stage_b_demand = sum(
        float(quantity)
        for products in cell_demand.values()
        for quantity in products.values()
    )
    stage_b_consumption = sum(
        float(quantity)
        for products in cell_supply.values()
        for quantity in products.values()
    )
    if abs(metrics["overall_demand"] - stage_b_demand) > 1e-7:
        raise HouseholdBridgeError("household demand does not reconcile to Stage-B")
    if abs(metrics["overall_served"] - stage_b_consumption) > 1e-7:
        raise HouseholdBridgeError("household consumption does not reconcile to Stage-B")

    served: dict[str, dict[str, float]] = {cid: {} for cid in cell_supply}
    for allocation in allocations:
        for product, quantity in allocation.essential_served.items():
            served[allocation.cell_id][product] = (
                served[allocation.cell_id].get(product, 0.0) + quantity
            )
        for product, quantity in allocation.discretionary_served.items():
            served[allocation.cell_id][product] = (
                served[allocation.cell_id].get(product, 0.0) + quantity
            )

    unallocated: dict[str, dict[str, float]] = {}
    for cell_id, products in cell_supply.items():
        unallocated[cell_id] = {}
        for product, available in products.items():
            used = served[cell_id].get(product, 0.0)
            unallocated[cell_id][product] = max(0.0, float(available) - used)

    stage_b_total_consumption = sum(
        float(quantity)
        for products in cell_supply.values()
        for quantity in products.values()
    )
    if abs(metrics["overall_served"] - stage_b_total_consumption) > 1e-7:
        raise HouseholdBridgeError(
            "total household allocation does not reconcile to Stage-B consumption"
        )

    if set(essential_products) == {"food", "care"}:
        stage_b_essential = (
            sum(v.get("food", 0.0) for v in cell_supply.values())
            + sum(v.get("care", 0.0) for v in cell_supply.values())
        )
        if abs(metrics["essential_served"] - stage_b_essential) > 1e-7:
            raise HouseholdBridgeError(
                "household essential service does not reconcile to Stage-B"
            )

    return {
        "policy": policy,
        "seed": seed,
        "households_per_cell": households_per_cell,
        "priority_dispersion": priority_dispersion,
        "households": households,
        "allocations": allocations,
        "metrics": metrics,
        "unassigned_consumption_by_cell": unallocated,
        "is_posthoc_decomposition": True,
    }



def summarize_periods_to_households(
    period_results,
    households_per_cell: int = 5,
    policy: str = "proportional",
    seed: int = 1,
    essential_products: Sequence[str] = ("food", "care"),
    priority_dispersion: float = 0.0,
) -> dict:
    """Aggregate stable synthetic households over a Stage-B simulation horizon.

    The same household shares and priority draws are reused each period, so
    household identities represent persistent synthetic households rather
    than newly sampled people. This is a post-hoc decomposition of already
    consumed quantities and does not feed back into production.
    """
    periods = tuple(period_results)
    if not periods:
        raise HouseholdBridgeError("at least one Stage-B period is required")

    demand_by_household = {}
    served_by_household = {}
    aggregate_cell_supply = {}
    period_metrics = []

    for period in periods:
        result = distribute_period_to_households(
            period, households_per_cell, policy, seed, essential_products,
            priority_dispersion)
        period_metrics.append(result["metrics"])

        for household in result["households"]:
            state = demand_by_household.setdefault(
                household.household_id,
                {
                    "cell_id": household.cell_id,
                    "essential": {},
                    "discretionary": {},
                    "essential_priority": household.essential_priority,
                    "discretionary_priority": household.discretionary_priority,
                },
            )
            for product, quantity in household.essential_needs.items():
                state["essential"][product] = (
                    state["essential"].get(product, 0.0) + float(quantity))
            for product, quantity in household.discretionary_needs.items():
                state["discretionary"][product] = (
                    state["discretionary"].get(product, 0.0) + float(quantity))
            served_by_household.setdefault(
                household.household_id,
                {"essential": {}, "discretionary": {}},
            )

        for allocation in result["allocations"]:
            state = served_by_household[allocation.household_id]
            for product, quantity in allocation.essential_served.items():
                state["essential"][product] = (
                    state["essential"].get(product, 0.0) + float(quantity))
            for product, quantity in allocation.discretionary_served.items():
                state["discretionary"][product] = (
                    state["discretionary"].get(product, 0.0) + float(quantity))

        for cell_id, products in period.final_consumption_by_cell.items():
            target = aggregate_cell_supply.setdefault(cell_id, {})
            for product, quantity in products.items():
                quantity = float(quantity)
                if quantity < -1e-8:
                    raise HouseholdBridgeError(
                        f"negative cumulative household supply {cell_id}:{product}={quantity}")
                target[product] = target.get(product, 0.0) + max(0.0, quantity)

    households = tuple(
        Household(
            household_id=household_id,
            cell_id=state["cell_id"],
            essential_needs=state["essential"],
            discretionary_needs=state["discretionary"],
            essential_priority=state["essential_priority"],
            discretionary_priority=state["discretionary_priority"],
        )
        for household_id, state in sorted(demand_by_household.items())
    )
    allocations = tuple(
        HouseholdAllocation(
            household_id=household_id,
            cell_id=demand_by_household[household_id]["cell_id"],
            essential_served=served_by_household[household_id]["essential"],
            discretionary_served=served_by_household[household_id]["discretionary"],
        )
        for household_id in sorted(demand_by_household)
    )
    validate_household_allocation(households, aggregate_cell_supply, allocations)
    aggregate = evaluate_households(households, allocations)

    expected_total = sum(
        float(quantity)
        for period in periods
        for products in period.final_consumption_by_cell.values()
        for quantity in products.values()
    )
    if abs(aggregate["overall_served"] - expected_total) > 1e-7:
        raise HouseholdBridgeError(
            "horizon household consumption does not reconcile to Stage-B"
        )

    expected_essential = sum(
        float(period.final_consumption_by_product.get(product, 0.0))
        for period in periods for product in essential_products
    )
    if abs(aggregate["essential_served"] - expected_essential) > 1e-7:
        raise HouseholdBridgeError(
            "horizon household essential service does not reconcile to Stage-B"
        )

    return {
        **aggregate,
        "policy": policy,
        "households_per_cell": households_per_cell,
        "priority_dispersion": priority_dispersion,
        "periods": len(periods),
        "mean_period_lower_decile_household_essential_fulfilment": (
            sum(m["lower_decile_household_essential_fulfilment"]
                for m in period_metrics) / len(period_metrics)
        ),
        "mean_period_minimum_household_essential_fulfilment": (
            sum(m["minimum_household_essential_fulfilment"]
                for m in period_metrics) / len(period_metrics)
        ),
        "mean_period_household_essential_fulfilment_gini": (
            sum(m["essential_fulfilment_gini"]
                for m in period_metrics) / len(period_metrics)
        ),
        "worst_period_minimum_household_essential_fulfilment": min(
            m["minimum_household_essential_fulfilment"]
            for m in period_metrics
        ),
    }