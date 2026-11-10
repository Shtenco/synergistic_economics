"""Paired multi-seed experiments for SCCE C2-A2 household feedback."""
from __future__ import annotations

import argparse
import json
import statistics
from typing import Sequence

from scc_dynamic_economy import POLICIES
from scc_endogenous_household_economy import EndogenousHouseholdEconomy


HOUSEHOLD_POLICIES = ("proportional", "priority_weighted", "floor_priority")
METRICS = (
    "current_essential_fulfilment",
    "current_food_fulfilment",
    "current_care_fulfilment",
    "total_food_delivered",
    "total_care_delivered",
    "cumulative_care_backlog_served",
    "current_overall_fulfilment",
    "cumulative_unmet_food_units",
    "cumulative_expired_care_claim_units",
    "cumulative_attrited_care_claim_units",
    "cumulative_unqueued_care_claim_units",
    "cumulative_lower_decile_current_essential_fulfilment",
    "cumulative_minimum_current_essential_fulfilment",
    "cumulative_household_essential_gini",
    "mean_period_lower_decile_current_essential_fulfilment",
    "worst_period_minimum_current_essential_fulfilment",
    "ending_essential_backlog",
    "peak_essential_backlog",
    "fixed_price_final_consumption_index",
    "fixed_price_gross_output_index",
    "total_coordination_hours",
)


class EndogenousHouseholdExperimentError(ValueError):
    pass


def confidence_summary(values: Sequence[float]) -> dict:
    values = [float(x) for x in values]
    n = len(values)
    mean = statistics.mean(values) if n else 0.0
    sd = statistics.stdev(values) if n > 1 else 0.0
    half = 1.96 * sd / (n ** 0.5) if n > 1 else 0.0
    return {
        "n": n,
        "mean": mean,
        "median": statistics.median(values) if n else 0.0,
        "sd": sd,
        "ci95_low": mean - half,
        "ci95_high": mean + half,
    }


def run_endogenous_household_experiment(
    runs: int = 20,
    shock: str = "compound",
    periods: int = 24,
    cellular_hops: int = 2,
    households_per_cell: int = 10,
    priority_dispersion: float = 0.4,
    essential_floor_fraction: float = 0.5,
    backlog_retention: float = 1.0,
    max_backlog_periods: float = 1.0,
    economic_policies: Sequence[str] = POLICIES,
    household_policies: Sequence[str] = HOUSEHOLD_POLICIES,
    backlog_service_order: str = "backlog_first",
    max_care_queue_age_periods: int = 3,
) -> dict:
    if runs < 2:
        raise EndogenousHouseholdExperimentError("at least two paired runs are required")
    if not economic_policies or any(p not in POLICIES for p in economic_policies):
        raise EndogenousHouseholdExperimentError("invalid economic policy selection")
    if not household_policies or any(
        p not in HOUSEHOLD_POLICIES for p in household_policies
    ):
        raise EndogenousHouseholdExperimentError("invalid household policy selection")

    paired_runs = []
    for seed in range(1, runs + 1):
        for economic_policy in economic_policies:
            for household_policy in household_policies:
                model = EndogenousHouseholdEconomy(
                    policy=economic_policy,
                    seed=seed,
                    shock=shock,
                    cellular_hops=cellular_hops,
                    households_per_cell=households_per_cell,
                    priority_dispersion=priority_dispersion,
                    household_policy=household_policy,
                    essential_floor_fraction=essential_floor_fraction,
                    backlog_retention=backlog_retention,
                    max_backlog_periods=max_backlog_periods,
                    backlog_service_order=backlog_service_order,
                    max_care_queue_age_periods=max_care_queue_age_periods,
                )
                model.run(periods)
                summary = model.summary()
                physical = summary.pop("physical_economy")
                row = {
                    "seed": seed,
                    "economic_policy": economic_policy,
                    "household_policy": household_policy,
                    **summary,
                    "fixed_price_final_consumption_index":
                        physical["fixed_price_final_consumption_index"],
                    "fixed_price_gross_output_index":
                        physical["fixed_price_gross_output_index"],
                    "total_coordination_hours":
                        physical["total_coordination_hours"],
                }
                paired_runs.append(row)

    by_arm = {
        (row["seed"], row["economic_policy"], row["household_policy"]): row
        for row in paired_runs
    }
    summary = {}
    for economic_policy in economic_policies:
        summary[economic_policy] = {}
        for household_policy in household_policies:
            rows = [
                by_arm[(seed, economic_policy, household_policy)]
                for seed in range(1, runs + 1)
            ]
            summary[economic_policy][household_policy] = {
                metric: confidence_summary([row[metric] for row in rows])
                for metric in METRICS
            }

    paired_vs_market = {}
    if "market" in economic_policies:
        for economic_policy in economic_policies:
            if economic_policy == "market":
                continue
            paired_vs_market[economic_policy] = {}
            for household_policy in household_policies:
                paired_vs_market[economic_policy][household_policy] = {}
                for metric in METRICS:
                    differences = [
                        by_arm[(seed, economic_policy, household_policy)][metric]
                        - by_arm[(seed, "market", household_policy)][metric]
                        for seed in range(1, runs + 1)
                    ]
                    paired_vs_market[economic_policy][household_policy][metric] = (
                        confidence_summary(differences)
                    )

    paired_vs_proportional = {}
    if "proportional" in household_policies:
        for economic_policy in economic_policies:
            paired_vs_proportional[economic_policy] = {}
            for household_policy in household_policies:
                if household_policy == "proportional":
                    continue
                paired_vs_proportional[economic_policy][household_policy] = {}
                for metric in METRICS:
                    differences = [
                        by_arm[(seed, economic_policy, household_policy)][metric]
                        - by_arm[(seed, economic_policy, "proportional")][metric]
                        for seed in range(1, runs + 1)
                    ]
                    paired_vs_proportional[economic_policy][household_policy][metric] = (
                        confidence_summary(differences)
                    )

    return {
        "runs": runs,
        "shock": shock,
        "periods": periods,
        "cellular_hops": cellular_hops,
        "households_per_cell": households_per_cell,
        "priority_dispersion": priority_dispersion,
        "essential_floor_fraction": essential_floor_fraction,
        "backlog_retention": backlog_retention,
        "max_backlog_periods": max_backlog_periods,
        "backlog_service_order": backlog_service_order,
        "max_care_queue_age_periods": max_care_queue_age_periods,
        "economic_policies": list(economic_policies),
        "household_policies": list(household_policies),
        "summary": summary,
        "paired_differences_vs_market": paired_vs_market,
        "paired_differences_vs_proportional": paired_vs_proportional,
        "paired_runs": paired_runs,
    }




def run_backlog_sensitivity(
    runs: int = 20,
    shock: str = "compound",
    periods: int = 24,
    cellular_hops: int = 2,
    households_per_cell: int = 10,
    priority_dispersion: float = 0.4,
    backlog_retention: float = 0.5,
    max_backlog_periods: float = 1.0,
    economic_policies: Sequence[str] = POLICIES,
    max_care_queue_age_periods: int = 3,
) -> dict:
    """Paired same-seed comparison of bounded essential backlog vs no carry-over."""
    common = {
        "runs": runs,
        "shock": shock,
        "periods": periods,
        "cellular_hops": cellular_hops,
        "households_per_cell": households_per_cell,
        "priority_dispersion": priority_dispersion,
        "economic_policies": economic_policies,
        "household_policies": ("proportional",),
        "backlog_service_order": "backlog_first",
        "max_care_queue_age_periods": max_care_queue_age_periods,
    }
    with_backlog = run_endogenous_household_experiment(
        **common,
        backlog_retention=backlog_retention,
        max_backlog_periods=max_backlog_periods,
    )
    without_backlog = run_endogenous_household_experiment(
        **common,
        backlog_retention=0.0,
        max_backlog_periods=0.0,
    )
    with_rows = {
        (row["seed"], row["economic_policy"]): row
        for row in with_backlog["paired_runs"]
    }
    without_rows = {
        (row["seed"], row["economic_policy"]): row
        for row in without_backlog["paired_runs"]
    }
    metrics = (
        "current_essential_fulfilment",
        "current_food_fulfilment",
        "current_care_fulfilment",
        "current_overall_fulfilment",
        "cumulative_unmet_food_units",
        "cumulative_expired_care_claim_units",
        "cumulative_attrited_care_claim_units",
        "cumulative_unqueued_care_claim_units",
        "cumulative_lower_decile_current_essential_fulfilment",
        "cumulative_minimum_current_essential_fulfilment",
        "cumulative_household_essential_gini",
        "ending_essential_backlog",
        "peak_essential_backlog",
        "fixed_price_final_consumption_index",
        "fixed_price_gross_output_index",
        "total_coordination_hours",
    )
    result = {}
    for policy in economic_policies:
        result[policy] = {}
        for metric in metrics:
            paired = [
                with_rows[(seed, policy)][metric]
                - without_rows[(seed, policy)][metric]
                for seed in range(1, runs + 1)
            ]
            result[policy][metric] = {
                "with_backlog_mean": statistics.mean(
                    with_rows[(seed, policy)][metric] for seed in range(1, runs + 1)),
                "without_backlog_mean": statistics.mean(
                    without_rows[(seed, policy)][metric] for seed in range(1, runs + 1)),
                "paired_backlog_minus_zero": confidence_summary(paired),
            }
    return {
        "runs": runs,
        "shock": shock,
        "periods": periods,
        "households_per_cell": households_per_cell,
        "backlog_retention": backlog_retention,
        "max_backlog_periods": max_backlog_periods,
        "max_care_queue_age_periods": max_care_queue_age_periods,
        "household_policy": "proportional",
        "reference": "zero essential-backlog retention and zero backlog cap",
        "sensitivity": result,
    }


def run_service_order_sensitivity(
    runs: int = 20,
    shock: str = "compound",
    periods: int = 24,
    cellular_hops: int = 2,
    households_per_cell: int = 10,
    priority_dispersion: float = 0.4,
    backlog_retention: float = 0.5,
    max_backlog_periods: float = 1.0,
    economic_policies: Sequence[str] = POLICIES,
    max_care_queue_age_periods: int = 3,
) -> dict:
    """Paired same-seed comparison of current-first and backlog-first service."""
    common = {
        "runs": runs,
        "shock": shock,
        "periods": periods,
        "cellular_hops": cellular_hops,
        "households_per_cell": households_per_cell,
        "priority_dispersion": priority_dispersion,
        "backlog_retention": backlog_retention,
        "max_backlog_periods": max_backlog_periods,
        "economic_policies": economic_policies,
        "household_policies": ("proportional",),
        "max_care_queue_age_periods": max_care_queue_age_periods,
    }
    current_first = run_endogenous_household_experiment(
        **common, backlog_service_order="current_first")
    backlog_first = run_endogenous_household_experiment(
        **common, backlog_service_order="backlog_first")
    current_rows = {
        (row["seed"], row["economic_policy"]): row
        for row in current_first["paired_runs"]
    }
    backlog_rows = {
        (row["seed"], row["economic_policy"]): row
        for row in backlog_first["paired_runs"]
    }
    metrics = (
        "current_essential_fulfilment",
        "current_food_fulfilment",
        "current_care_fulfilment",
        "total_food_delivered",
        "total_care_delivered",
        "cumulative_care_backlog_served",
        "current_overall_fulfilment",
        "cumulative_lower_decile_current_essential_fulfilment",
        "cumulative_minimum_current_essential_fulfilment",
        "cumulative_household_essential_gini",
        "ending_essential_backlog",
        "peak_essential_backlog",
        "fixed_price_final_consumption_index",
        "fixed_price_gross_output_index",
    )
    sensitivity = {}
    for policy in economic_policies:
        sensitivity[policy] = {}
        for metric in metrics:
            differences = [
                backlog_rows[(seed, policy)][metric]
                - current_rows[(seed, policy)][metric]
                for seed in range(1, runs + 1)
            ]
            sensitivity[policy][metric] = {
                "current_first_mean": statistics.mean(
                    current_rows[(seed, policy)][metric]
                    for seed in range(1, runs + 1)),
                "backlog_first_mean": statistics.mean(
                    backlog_rows[(seed, policy)][metric]
                    for seed in range(1, runs + 1)),
                "paired_backlog_first_minus_current_first": confidence_summary(
                    differences),
            }
    return {
        "runs": runs,
        "shock": shock,
        "periods": periods,
        "backlog_retention": backlog_retention,
        "max_backlog_periods": max_backlog_periods,
        "max_care_queue_age_periods": max_care_queue_age_periods,
        "household_policy": "proportional",
        "sensitivity": sensitivity,
    }
def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=20)
    parser.add_argument("--shock", choices=(
        "none", "demand_surge", "resource_shock", "productivity_shock", "compound"
    ), default="compound")
    parser.add_argument("--periods", type=int, default=24)
    parser.add_argument("--hops", type=int, default=2)
    parser.add_argument("--households-per-cell", type=int, default=10)
    parser.add_argument("--priority-dispersion", type=float, default=0.4)
    parser.add_argument("--essential-floor-fraction", type=float, default=0.5)
    parser.add_argument("--backlog-retention", type=float, default=1.0)
    parser.add_argument("--max-backlog-periods", type=float, default=1.0)
    parser.add_argument("--max-care-queue-age-periods", type=int, default=3)
    parser.add_argument("--economic-policies", default="market,central,cooperative,cellular")
    parser.add_argument("--household-policies",
                        default="proportional,priority_weighted,floor_priority")
    parser.add_argument("--backlog-sensitivity", action="store_true")
    parser.add_argument("--service-order-sensitivity", action="store_true")
    parser.add_argument("--summary-only", action="store_true")
    args = parser.parse_args()
    economic_policies = tuple(
        x.strip() for x in args.economic_policies.split(",") if x.strip())
    household_policies = tuple(
        x.strip() for x in args.household_policies.split(",") if x.strip())
    if args.service_order_sensitivity:
        result = run_service_order_sensitivity(
            args.runs, args.shock, args.periods, args.hops,
            args.households_per_cell, args.priority_dispersion,
            args.backlog_retention, args.max_backlog_periods,
            economic_policies, args.max_care_queue_age_periods,
        )
    elif args.backlog_sensitivity:
        result = run_backlog_sensitivity(
            args.runs, args.shock, args.periods, args.hops,
            args.households_per_cell, args.priority_dispersion,
            args.backlog_retention, args.max_backlog_periods,
            economic_policies,
        )
    else:
        result = run_endogenous_household_experiment(
            args.runs, args.shock, args.periods, args.hops,
            args.households_per_cell, args.priority_dispersion,
            args.essential_floor_fraction, args.backlog_retention,
            args.max_backlog_periods, economic_policies, household_policies,
            "backlog_first", args.max_care_queue_age_periods,
        )
        if args.summary_only:
            result.pop("paired_runs", None)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
