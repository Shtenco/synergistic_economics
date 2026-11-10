"""Paired Stage-C1 household distribution experiment.

Runs Stage B under each production/coordination regime, aggregates physical
final demand and consumption by cell over the selected horizon, then applies
both Stage-C1 distribution rules to the same synthetic household population.
This is a money-free, intertemporal-aggregate distribution test.
"""
from __future__ import annotations

import argparse
import json
import math
import statistics
from types import SimpleNamespace

from household_distribution import compare_household_distribution_policies
from scc_dynamic_economy import DynamicCellularEconomy, POLICIES as PRODUCTION_POLICIES


METRICS = (
    "essential_fulfilment",
    "overall_fulfilment",
    "lower_decile_household_essential_fulfilment",
    "minimum_household_essential_fulfilment",
    "essential_fulfilment_gini",
    "overall_fulfilment_gini",
)


def confidence_summary(values):
    values = [float(x) for x in values]
    n = len(values)
    mean = statistics.mean(values) if n else 0.0
    sd = statistics.stdev(values) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n, "mean": mean,
        "median": statistics.median(values) if n else 0.0,
        "sd": sd, "ci95_low": mean - half, "ci95_high": mean + half,
    }


def aggregate_periods(periods):
    if not periods:
        raise ValueError("at least one Stage-B period is required")
    demand = {}
    consumption = {}
    for period in periods:
        for cid, products in period.final_demand_by_cell.items():
            target = demand.setdefault(cid, {})
            for product, quantity in products.items():
                target[product] = target.get(product, 0.0) + float(quantity)
        for cid, products in period.final_consumption_by_cell.items():
            target = consumption.setdefault(cid, {})
            for product, quantity in products.items():
                target[product] = target.get(product, 0.0) + float(quantity)
    return SimpleNamespace(
        final_demand_by_cell=demand,
        final_consumption_by_cell=consumption,
    )


def run_experiment(runs=20, shock="compound", periods=24, cellular_hops=2,
                   households_per_cell=10):
    if runs < 2:
        raise ValueError("at least two paired seeds are required")
    observations = {
        production: {distribution: {metric: [] for metric in METRICS}
                     for distribution in ("proportional", "priority_weighted")}
        for production in PRODUCTION_POLICIES
    }
    paired_differences = {
        production: {metric: [] for metric in METRICS}
        for production in PRODUCTION_POLICIES
    }

    for seed in range(1, runs + 1):
        for production in PRODUCTION_POLICIES:
            model = DynamicCellularEconomy(
                production, seed=seed, shock=shock,
                cellular_hops=cellular_hops,
            )
            model.run(periods)
            model.validate()
            aggregate = aggregate_periods(model.periods)
            comparison = compare_household_distribution_policies(
                aggregate, households_per_cell=households_per_cell, seed=seed + 90000,
            )
            results = comparison["policies"]
            for distribution in ("proportional", "priority_weighted"):
                for metric in METRICS:
                    observations[production][distribution][metric].append(
                        results[distribution][metric]
                    )
            for metric in METRICS:
                paired_differences[production][metric].append(
                    results["priority_weighted"][metric]
                    - results["proportional"][metric]
                )

    summary = {}
    paired = {}
    for production in PRODUCTION_POLICIES:
        summary[production] = {}
        paired[production] = {}
        for distribution in ("proportional", "priority_weighted"):
            summary[production][distribution] = {
                metric: confidence_summary(observations[production][distribution][metric])
                for metric in METRICS
            }
        paired[production] = {
            metric: confidence_summary(paired_differences[production][metric])
            for metric in METRICS
        }

    return {
        "runs": runs,
        "shock": shock,
        "periods": periods,
        "cellular_hops": cellular_hops,
        "households_per_cell": households_per_cell,
        "total_households_per_run": households_per_cell * 7,
        "aggregation": "sum of Stage-B final demand and cell consumption across all periods",
        "essential_products": ["food", "care"],
        "summary": summary,
        "paired_priority_weighted_minus_proportional": paired,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--shock", choices=("none", "demand_surge", "resource_shock",
                                             "productivity_shock", "compound"),
                        default="compound")
    parser.add_argument("--periods", type=int, default=24)
    parser.add_argument("--hops", type=int, default=2)
    parser.add_argument("--households-per-cell", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(run_experiment(
        args.runs, args.shock, args.periods, args.hops,
        args.households_per_cell,
    ), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
