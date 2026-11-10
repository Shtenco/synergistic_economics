"""Paired Stage-C1 household-distribution experiments over Stage-B worlds."""
from __future__ import annotations

import argparse
import json
import math
import statistics
from typing import Sequence

from scc_dynamic_economy import DynamicCellularEconomy, POLICIES
from scc_household_bridge import summarize_periods_to_households


HOUSEHOLD_POLICIES = ("proportional", "priority_weighted", "floor_priority")
METRICS = (
    "essential_fulfilment",
    "overall_fulfilment",
    "lower_decile_household_essential_fulfilment",
    "minimum_household_essential_fulfilment",
    "essential_fulfilment_gini",
    "overall_fulfilment_gini",
    "mean_period_lower_decile_household_essential_fulfilment",
    "mean_period_minimum_household_essential_fulfilment",
    "mean_period_household_essential_fulfilment_gini",
    "worst_period_minimum_household_essential_fulfilment",
)


def _summary(values: Sequence[float]) -> dict:
    if not values:
        raise ValueError("cannot summarize an empty sample")
    n = len(values)
    mean = statistics.mean(values)
    sd = statistics.stdev(values) if n > 1 else 0.0
    half = 1.96 * sd / math.sqrt(n) if n > 1 else 0.0
    return {
        "n": n,
        "mean": mean,
        "sd": sd,
        "ci95_low": mean - half,
        "ci95_high": mean + half,
        "median": statistics.median(values),
    }


def run_household_distribution_experiment(
    runs: int = 20,
    shock: str = "compound",
    periods: int = 24,
    cellular_hops: int = 2,
    households_per_cell: int = 10,
    priority_dispersion: float = 0.4,
    essential_floor_fraction: float = 0.5,
    economic_policies: Sequence[str] = POLICIES,
) -> dict:
    """Compare household rationing rules on identical Stage-B consumption.

    Each Stage-B world is simulated once per seed/economic policy. Both
    household rules then receive exactly the same per-cell physical consumption
    snapshots and the same synthetic household needs and priorities.
    """
    if runs < 2 or periods < 1:
        raise ValueError("runs must be >=2 and periods must be positive")
    if not economic_policies or any(p not in POLICIES for p in economic_policies):
        raise ValueError("unknown or empty economic policy set")
    if households_per_cell < 1:
        raise ValueError("households_per_cell must be positive")
    if not 0.0 <= priority_dispersion < 1.0:
        raise ValueError("priority_dispersion must be in [0, 1)")
    if not 0.0 <= essential_floor_fraction <= 1.0:
        raise ValueError("essential_floor_fraction must be in [0, 1]")

    rows = []
    for economic_policy in economic_policies:
        for seed in range(1, runs + 1):
            model = DynamicCellularEconomy(
                economic_policy, seed=seed, shock=shock,
                cellular_hops=cellular_hops,
            )
            model.run(periods)
            model.validate()
            distributions = {}
            for household_policy in HOUSEHOLD_POLICIES:
                # The same seed preserves a stable household panel across all
                # periods and across both rationing policies.
                distributions[household_policy] = summarize_periods_to_households(
                    model.periods,
                    households_per_cell=households_per_cell,
                    policy=household_policy,
                    seed=seed * 100_000,
                    priority_dispersion=priority_dispersion,
                    essential_floor_fraction=essential_floor_fraction,
                )

            for household_policy in HOUSEHOLD_POLICIES:
                row = {
                    "economic_policy": economic_policy,
                    "household_policy": household_policy,
                    "seed": seed,
                }
                row.update({
                    metric: distributions[household_policy][metric]
                    for metric in METRICS
                })
                rows.append(row)

    summary = {}
    paired = {}
    for economic_policy in economic_policies:
        summary[economic_policy] = {}
        by_rule = {
            rule: {row["seed"]: row for row in rows
                   if row["economic_policy"] == economic_policy
                   and row["household_policy"] == rule}
            for rule in HOUSEHOLD_POLICIES
        }
        for rule in HOUSEHOLD_POLICIES:
            summary[economic_policy][rule] = {
                metric: _summary([by_rule[rule][seed][metric]
                                  for seed in range(1, runs + 1)])
                for metric in METRICS
            }
        paired[economic_policy] = {
            rule: {
                metric: _summary([
                    by_rule[rule][seed][metric]
                    - by_rule["proportional"][seed][metric]
                    for seed in range(1, runs + 1)
                ])
                for metric in METRICS
            }
            for rule in ("priority_weighted", "floor_priority")
        }

    return {
        "runs": runs,
        "shock": shock,
        "periods": periods,
        "cellular_hops": cellular_hops,
        "households_per_cell": households_per_cell,
        "priority_dispersion": priority_dispersion,
        "essential_floor_fraction": essential_floor_fraction,
        "economic_policies": list(economic_policies),
        "household_policies": list(HOUSEHOLD_POLICIES),
        "summary": summary,
        "paired_priority_weighted_minus_proportional": paired,
        "paired_runs": rows,
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
    parser.add_argument("--priority-dispersion", type=float, default=0.4)
    parser.add_argument("--essential-floor-fraction", type=float, default=0.5)
    parser.add_argument("--economic-policies", default="market,central,cooperative,cellular")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    policies = tuple(x.strip() for x in args.economic_policies.split(",") if x.strip())
    result = run_household_distribution_experiment(
        args.runs, args.shock, args.periods, args.hops,
        args.households_per_cell, args.priority_dispersion,
        args.essential_floor_fraction, policies,
    )
    if args.summary_only:
        result.pop("paired_runs", None)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
