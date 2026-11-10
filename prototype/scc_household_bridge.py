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
) -> tuple[Household, ...]:
    """Split each cell's declared product demand into reproducible households.

    Product totals are preserved exactly per cell. Household shares are
    heterogeneous but synthetic; this generator is a test fixture, not a
    substitute for calibrated household survey data.
    """
    if households_per_cell < 1:
        raise HouseholdBridgeError("households_per_cell must be positive")
    rng = random.Random(seed)
    essential_set = set(essential_products)
    households: dict[str, dict[str, dict[str, float]]] = {}
    for cell_id in sorted(cell_demand):
        for index in range(households_per_cell):
            household_id = f"{cell_id}:h{index + 1:03d}"
            households[household_id] = {"essential": {}, "discretionary": {}}

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
        )
        for household_id, values in sorted(households.items())
    )


def distribute_period_to_households(
    period_result,
    households_per_cell: int = 5,
    policy: str = "proportional",
    seed: int = 1,
    essential_products: Sequence[str] = ("food", "care"),
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

    households = households_from_cell_demand(
        cell_demand, households_per_cell, seed, essential_products)
    allocations = allocate_households(households, cell_supply, policy)
    validate_household_allocation(households, cell_supply, allocations)
    metrics = evaluate_households(households, allocations)

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
        "households": households,
        "allocations": allocations,
        "metrics": metrics,
        "unallocated_supply_by_cell": unallocated,
        "is_posthoc_decomposition": True,
    }
