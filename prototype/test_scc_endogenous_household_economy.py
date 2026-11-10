import unittest

from scc_dynamic_economy import DynamicCellularEconomy
from scc_endogenous_household_economy import (
    EndogenousHouseholdEconomy,
    EndogenousHouseholdError,
)


class SCCEEndogenousHouseholdEconomyTests(unittest.TestCase):
    def test_zero_backlog_is_exact_stage_b_physical_control(self):
        seed = 31
        baseline = DynamicCellularEconomy(
            "cellular", seed, "compound", 2,
        )
        endogenous = EndogenousHouseholdEconomy(
            "cellular", seed, "compound", 2,
            households_per_cell=8, priority_dispersion=0.4,
            household_policy="proportional", backlog_retention=0.0,
        )
        baseline.run(10)
        endogenous.run(10)
        a = baseline.summary()
        b = endogenous.summary()["physical_economy"]
        for metric in (
            "final_fulfilment_rate",
            "mean_essential_fulfilment",
            "fixed_price_final_consumption_index",
            "fixed_price_gross_output_index",
            "total_raw_resource_used",
        ):
            self.assertAlmostEqual(a[metric], b[metric], places=9)
        self.assertAlmostEqual(
            endogenous.summary()["ending_essential_backlog"], 0.0, places=10,
        )

    def test_household_backlog_is_bounded_and_reenters_local_cell_demand(self):
        model = EndogenousHouseholdEconomy(
            "cellular", seed=41, shock="compound", cellular_hops=2,
            households_per_cell=10, priority_dispersion=0.4,
            household_policy="proportional", backlog_retention=0.8,
            max_backlog_periods=0.5,
        )
        model.run(16)
        self.assertTrue(model.validate())
        base_care = sum(
            h.essential_needs.get("care", 0.0) for h in model.households
        )
        for result in model.period_results:
            self.assertGreaterEqual(result.opening_essential_backlog, 0.0)
            self.assertGreaterEqual(result.closing_essential_backlog, 0.0)
            self.assertLessEqual(
                result.closing_essential_backlog,
                base_care * 0.5 + 1e-7,
            )
        self.assertGreater(model.summary()["peak_essential_backlog"], 0.0)
        # Care is a delayed service queue; food is a recurring period need.
        base_care = sum(
            spec.final_demand.get("care", 0.0)
            for spec in model.base_specs
        )
        period5_care = sum(
            values.get("care", 0.0)
            for values in model.period_results[4].cell_demand.values()
        )
        self.assertGreater(period5_care, base_care * 1.2)
        base_food = sum(
            spec.final_demand.get("food", 0.0)
            for spec in model.base_specs
        )
        period5_food = sum(
            values.get("food", 0.0)
            for values in model.period_results[4].cell_demand.values()
        )
        self.assertAlmostEqual(period5_food, base_food * 1.2, places=7)
        self.assertGreater(model.summary()["cumulative_unmet_food_units"], 0.0)

    def test_allocation_rule_changes_household_distribution_metrics(self):
        proportional = EndogenousHouseholdEconomy(
            "cellular", seed=53, shock="compound", cellular_hops=2,
            households_per_cell=10, priority_dispersion=0.8,
            household_policy="proportional", backlog_retention=0.7,
            max_backlog_periods=5.0,
        )
        weighted = EndogenousHouseholdEconomy(
            "cellular", seed=53, shock="compound", cellular_hops=2,
            households_per_cell=10, priority_dispersion=0.8,
            household_policy="priority_weighted", backlog_retention=0.7,
            max_backlog_periods=5.0,
        )
        proportional.run(12)
        weighted.run(12)
        a, b = proportional.summary(), weighted.summary()
        self.assertNotAlmostEqual(
            a["cumulative_lower_decile_current_essential_fulfilment"],
            b["cumulative_lower_decile_current_essential_fulfilment"],
            places=5,
        )
        self.assertGreaterEqual(a["ending_essential_backlog"], 0.0)
        self.assertGreaterEqual(b["ending_essential_backlog"], 0.0)

    def test_invalid_backlog_parameters_are_rejected(self):
        with self.assertRaises(EndogenousHouseholdError):
            EndogenousHouseholdEconomy(backlog_retention=1.1)
        with self.assertRaises(EndogenousHouseholdError):
            EndogenousHouseholdEconomy(max_backlog_periods=-1.0)
        with self.assertRaises(EndogenousHouseholdError):
            EndogenousHouseholdEconomy(household_policy="unknown")
        with self.assertRaises(EndogenousHouseholdError):
            EndogenousHouseholdEconomy(backlog_service_order="random")


if __name__ == "__main__":
    unittest.main(verbosity=2)
