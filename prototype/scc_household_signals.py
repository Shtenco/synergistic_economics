"""C2-A1: privacy-scoped household demand signals for SCCE cells.

This module turns persistent synthetic household need profiles into aggregate
cell-level demand packets. It deliberately exposes no household identifiers,
priority weights or individual need vectors to the production engine.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace
from typing import Mapping, Sequence

from scc_dynamic_economy import CellSpec, DynamicCellularEconomy, POLICIES
from scc_household_bridge import households_from_cell_demand
from household_distribution import Household


EPS = 1e-9


class HouseholdSignalError(ValueError):
    pass


@dataclass(frozen=True)
class HouseholdDemandSignal:
    cell_id: str
    product: str
    essential_quantity: float
    discretionary_quantity: float
    total_quantity: float
    contributor_count: int
    schema_version: str = "1.0"


@dataclass(frozen=True)
class HouseholdSignalSnapshot:
    published: tuple[HouseholdDemandSignal, ...]
    suppressed: tuple[tuple[str, str, int], ...]


def aggregate_household_requests(
    households: Sequence[Household],
    minimum_households: int = 3,
) -> HouseholdSignalSnapshot:
    """Publish cell/product aggregates without household-level identifiers."""
    if minimum_households < 1:
        raise HouseholdSignalError("minimum_households must be positive")
    ids = [h.household_id for h in households]
    if not households or len(ids) != len(set(ids)):
        raise HouseholdSignalError("households must be non-empty with unique ids")

    aggregates: dict[tuple[str, str], dict[str, float]] = {}
    contributors: dict[tuple[str, str], set[str]] = {}
    for h in households:
        if not h.cell_id:
            raise HouseholdSignalError("household cell_id is required")
        products = set(h.essential_needs) | set(h.discretionary_needs)
        for product in products:
            essential = float(h.essential_needs.get(product, 0.0))
            discretionary = float(h.discretionary_needs.get(product, 0.0))
            if (not math.isfinite(essential) or not math.isfinite(discretionary)
                    or essential < 0 or discretionary < 0):
                raise HouseholdSignalError("household claims must be finite and non-negative")
            key = (h.cell_id, product)
            item = aggregates.setdefault(key, {"essential": 0.0, "discretionary": 0.0})
            item["essential"] += essential
            item["discretionary"] += discretionary
            if essential + discretionary > EPS:
                contributors.setdefault(key, set()).add(h.household_id)

    published = []
    suppressed = []
    for (cell_id, product), item in sorted(aggregates.items()):
        count = len(contributors.get((cell_id, product), set()))
        if count < minimum_households:
            suppressed.append((cell_id, product, count))
            continue
        total = item["essential"] + item["discretionary"]
        published.append(HouseholdDemandSignal(
            cell_id=cell_id,
            product=product,
            essential_quantity=item["essential"],
            discretionary_quantity=item["discretionary"],
            total_quantity=total,
            contributor_count=count,
        ))
    return HouseholdSignalSnapshot(tuple(published), tuple(suppressed))


def signals_to_cell_demand(
    snapshot: HouseholdSignalSnapshot,
    expected_cells: Sequence[str],
    expected_products: Sequence[str],
) -> dict[str, dict[str, float]]:
    """Rebuild cell demand; fail closed if any required aggregate is suppressed."""
    if snapshot.suppressed:
        cell_id, product, count = snapshot.suppressed[0]
        raise HouseholdSignalError(
            f"cannot publish {cell_id}:{product}; only {count} contributors")
    result = {cell_id: {product: 0.0 for product in expected_products}
              for cell_id in expected_cells}
    for signal in snapshot.published:
        if signal.cell_id not in result or signal.product not in result[signal.cell_id]:
            raise HouseholdSignalError("signal references unknown cell or product")
        values = (
            signal.essential_quantity,
            signal.discretionary_quantity,
            signal.total_quantity,
        )
        if any(not math.isfinite(x) or x < 0 for x in values):
            raise HouseholdSignalError("signal quantity must be finite and non-negative")
        if abs(signal.total_quantity - sum(values[:2])) > 1e-8:
            raise HouseholdSignalError("signal components do not reconcile")
        result[signal.cell_id][signal.product] = signal.total_quantity
    return result


def household_demand_specs(
    base_specs: Sequence[CellSpec],
    households_per_cell: int = 10,
    seed: int = 1,
    priority_dispersion: float = 0.4,
    minimum_households: int = 3,
) -> tuple[tuple[CellSpec, ...], tuple[Household, ...], HouseholdSignalSnapshot]:
    """Create a persistent household panel and replace cell demand by its aggregates.

    The aggregate quantities must exactly reproduce the original CellSpec demand.
    This is a controlled bridge: it makes households the explicit source of cell
    demand without changing the physical demand totals or the Stage-B baseline.
    """
    if not base_specs:
        raise HouseholdSignalError("base cell specifications are required")
    cell_demand = {spec.cell_id: dict(spec.final_demand) for spec in base_specs}
    households = households_from_cell_demand(
        cell_demand,
        households_per_cell=households_per_cell,
        seed=seed,
        essential_products=("food", "care"),
        priority_dispersion=priority_dispersion,
    )
    snapshot = aggregate_household_requests(households, minimum_households)
    products = sorted({p for spec in base_specs for p in spec.final_demand})
    rebuilt = signals_to_cell_demand(
        snapshot, [spec.cell_id for spec in base_specs], products)
    updated_specs = tuple(
        replace(spec, final_demand={
            product: rebuilt[spec.cell_id][product]
            for product in spec.final_demand
        })
        for spec in base_specs
    )
    for spec in base_specs:
        for product, original in spec.final_demand.items():
            if abs(updated_specs[[x.cell_id for x in updated_specs].index(spec.cell_id)]
                   .final_demand[product] - float(original)) > 1e-8:
                raise HouseholdSignalError(
                    f"household demand does not reconcile at {spec.cell_id}:{product}")
    return updated_specs, households, snapshot


def run_household_signal_economy(
    policy: str = "cellular",
    seed: int = 1,
    shock: str = "none",
    periods: int = 24,
    cellular_hops: int = 2,
    households_per_cell: int = 10,
    priority_dispersion: float = 0.4,
    minimum_households: int = 3,
) -> dict:
    """Run Stage B with cell demand sourced from privacy-scoped household signals."""
    if policy not in POLICIES:
        raise HouseholdSignalError("unknown economic policy")
    base_specs = DynamicCellularEconomy.default_specs(seed)
    specs, households, snapshot = household_demand_specs(
        base_specs, households_per_cell, seed, priority_dispersion,
        minimum_households)
    economy = DynamicCellularEconomy(
        policy, seed, shock, cellular_hops, specs=specs)
    economy.run(periods)
    economy.validate()
    return {
        "policy": policy,
        "seed": seed,
        "shock": shock,
        "periods": periods,
        "households": len(households),
        "published_signal_count": len(snapshot.published),
        "suppressed_signal_count": len(snapshot.suppressed),
        "household_demand_total": sum(
            signal.total_quantity for signal in snapshot.published),
        "economy": economy.summary(),
    }
