import unittest
from types import SimpleNamespace

from household_distribution_experiment import aggregate_periods, run_experiment


class HouseholdDistributionExperimentTests(unittest.TestCase):
    def test_aggregate_periods_sums_cell_demand_and_consumption(self):
        periods = (
            SimpleNamespace(
                final_demand_by_cell={"cell-a": {"food": 3.0}},
                final_consumption_by_cell={"cell-a": {"food": 2.0}},
            ),
            SimpleNamespace(
                final_demand_by_cell={"cell-a": {"food": 4.0}, "cell-b": {"care": 1.0}},
                final_consumption_by_cell={"cell-a": {"food": 3.0}, "cell-b": {"care": 0.5}},
            ),
        )
        aggregate = aggregate_periods(periods)
        self.assertEqual(aggregate.final_demand_by_cell["cell-a"]["food"], 7.0)
        self.assertEqual(aggregate.final_consumption_by_cell["cell-a"]["food"], 5.0)
        self.assertEqual(aggregate.final_demand_by_cell["cell-b"]["care"], 1.0)
        self.assertEqual(aggregate.final_consumption_by_cell["cell-b"]["care"], 0.5)

    def test_paired_household_experiment_is_deterministic_and_complete(self):
        result = run_experiment(
            runs=2, shock="compound", periods=6, cellular_hops=2,
            households_per_cell=3,
        )
        self.assertEqual(result["runs"], 2)
        self.assertEqual(result["total_households_per_run"], 21)
        self.assertEqual(set(result["summary"]), {
            "market", "central", "cooperative", "cellular",
        })
        for production in result["summary"]:
            self.assertIn("proportional", result["summary"][production])
            self.assertIn("priority_weighted", result["summary"][production])
            for metric in result["paired_priority_weighted_minus_proportional"][production].values():
                self.assertEqual(metric["n"], 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
