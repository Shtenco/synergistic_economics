import unittest

from scc_endogenous_household_experiment import (
    EndogenousHouseholdExperimentError,
    run_endogenous_household_experiment,
    run_backlog_sensitivity,
)


class SCCEEndogenousHouseholdExperimentTests(unittest.TestCase):
    def test_paired_household_feedback_experiment_structure(self):
        result = run_endogenous_household_experiment(
            runs=2, shock="compound", periods=6, cellular_hops=2,
            households_per_cell=5, priority_dispersion=0.3,
            backlog_retention=0.5, max_backlog_periods=1.0,
        )
        self.assertEqual(result["runs"], 2)
        self.assertEqual(len(result["paired_runs"]), 2 * 4 * 3)
        self.assertEqual(
            result["summary"]["cellular"]["proportional"]
            ["current_essential_fulfilment"]["n"], 2,
        )
        self.assertEqual(
            result["paired_differences_vs_market"]["cellular"]["proportional"]
            ["current_essential_fulfilment"]["n"], 2,
        )
        self.assertEqual(
            result["paired_differences_vs_proportional"]["cellular"]["priority_weighted"]
            ["cumulative_lower_decile_current_essential_fulfilment"]["n"], 2,
        )

    def test_paired_backlog_sensitivity_uses_identical_seeds(self):
        result = run_backlog_sensitivity(
            runs=2, shock="compound", periods=8, cellular_hops=2,
            households_per_cell=5, priority_dispersion=0.3,
            backlog_retention=0.5, max_backlog_periods=1.0,
        )
        self.assertEqual(result["runs"], 2)
        cellular = result["sensitivity"]["cellular"]
        self.assertEqual(
            cellular["fixed_price_final_consumption_index"]
            ["paired_backlog_minus_zero"]["n"], 2,
        )
        self.assertGreater(
            cellular["ending_essential_backlog"]
            ["with_backlog_mean"], 0.0,
        )
        self.assertEqual(
            cellular["ending_essential_backlog"]
            ["without_backlog_mean"], 0.0,
        )

    def test_invalid_experiment_size_or_policy_is_rejected(self):
        with self.assertRaises(EndogenousHouseholdExperimentError):
            run_endogenous_household_experiment(runs=1)
        with self.assertRaises(EndogenousHouseholdExperimentError):
            run_endogenous_household_experiment(
                runs=2, economic_policies=("market", "unknown"),
            )
        with self.assertRaises(EndogenousHouseholdExperimentError):
            run_endogenous_household_experiment(
                runs=2, household_policies=("proportional", "unknown"),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
