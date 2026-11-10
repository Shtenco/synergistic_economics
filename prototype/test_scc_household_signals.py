import unittest

from scc_dynamic_economy import DynamicCellularEconomy
from scc_household_bridge import households_from_cell_demand
from scc_household_signals import (
    HouseholdSignalError,
    aggregate_household_requests,
    household_demand_specs,
    run_household_signal_economy,
    signals_to_cell_demand,
)


class SCCEHouseholdSignalTests(unittest.TestCase):
    def test_household_signals_reconcile_to_original_cell_demand(self):
        seed = 17
        base_specs = DynamicCellularEconomy.default_specs(seed)
        updated, households, snapshot = household_demand_specs(
            base_specs, households_per_cell=8, seed=seed,
            priority_dispersion=0.3, minimum_households=3,
        )
        self.assertEqual(len(households), 56)
        self.assertEqual(snapshot.suppressed, ())
        self.assertEqual(len(snapshot.published), sum(
            len(spec.final_demand) for spec in base_specs
        ))
        for original, rebuilt in zip(base_specs, updated):
            self.assertEqual(original.cell_id, rebuilt.cell_id)
            for product, quantity in original.final_demand.items():
                self.assertAlmostEqual(
                    rebuilt.final_demand[product], quantity, places=10
                )

    def test_signal_payload_contains_no_household_identifiers_or_priorities(self):
        base_specs = DynamicCellularEconomy.default_specs(3)
        _, _, snapshot = household_demand_specs(
            base_specs, households_per_cell=6, seed=3,
        )
        for signal in snapshot.published:
            self.assertFalse(hasattr(signal, "household_id"))
            self.assertFalse(hasattr(signal, "essential_priority"))
            self.assertFalse(hasattr(signal, "discretionary_priority"))
            self.assertGreaterEqual(signal.contributor_count, 3)
            self.assertAlmostEqual(
                signal.total_quantity,
                signal.essential_quantity + signal.discretionary_quantity,
            )

    def test_small_group_aggregate_is_suppressed_and_fails_closed(self):
        households = households_from_cell_demand(
            {"cell-a": {"food": 3.0}},
            households_per_cell=2,
            seed=1,
        )
        snapshot = aggregate_household_requests(
            households, minimum_households=3,
        )
        self.assertEqual(len(snapshot.published), 0)
        self.assertEqual(snapshot.suppressed, (("cell-a", "food", 2),))
        with self.assertRaises(HouseholdSignalError):
            signals_to_cell_demand(
                snapshot, expected_cells=("cell-a",),
                expected_products=("food",),
            )

    def test_household_signal_bridge_does_not_change_stage_b_physical_outcome(self):
        seed = 23
        base_specs = DynamicCellularEconomy.default_specs(seed)
        household_specs, _, _ = household_demand_specs(
            base_specs, households_per_cell=10, seed=seed,
            priority_dispersion=0.4,
        )
        for policy in ("market", "central", "cooperative", "cellular"):
            baseline = DynamicCellularEconomy(
                policy, seed, "compound", 2, specs=base_specs,
            )
            household_driven = DynamicCellularEconomy(
                policy, seed, "compound", 2, specs=household_specs,
            )
            baseline.run(10)
            household_driven.run(10)
            baseline.validate()
            household_driven.validate()
            a, b = baseline.summary(), household_driven.summary()
            for metric in (
                "final_fulfilment_rate",
                "mean_essential_fulfilment",
                "fixed_price_final_consumption_index",
                "fixed_price_gross_output_index",
                "total_raw_resource_used",
            ):
                self.assertAlmostEqual(a[metric], b[metric], places=9)

    def test_end_to_end_household_signal_runner_reports_aggregate_only(self):
        result = run_household_signal_economy(
            policy="cellular", seed=5, shock="none", periods=4,
            households_per_cell=5,
        )
        self.assertEqual(result["households"], 35)
        self.assertGreater(result["published_signal_count"], 0)
        self.assertEqual(result["suppressed_signal_count"], 0)
        self.assertIn("economy", result)
        self.assertTrue(result["economy"]["policy"] == "cellular")


if __name__ == "__main__":
    unittest.main(verbosity=2)
