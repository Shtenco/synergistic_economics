import unittest

from scc_dynamic_economy import DynamicCellularEconomy
from scc_household_bridge import (
    HouseholdBridgeError,
    distribute_period_to_households,
    households_from_cell_demand,
    summarize_periods_to_households,
)
from scc_household_experiment import run_household_distribution_experiment


class SCCHouseholdBridgeTests(unittest.TestCase):
    def test_generated_households_reconcile_to_each_cell_product_demand(self):
        demand = {
            "cell-a": {"food": 10.0, "care": 2.0, "software": 3.0},
            "cell-b": {"food": 7.0, "care": 1.0, "software": 4.0},
        }
        households = households_from_cell_demand(
            demand, households_per_cell=7, seed=41)
        reconstructed = {cid: {} for cid in demand}
        for household in households:
            for product, quantity in household.essential_needs.items():
                reconstructed[household.cell_id][product] = (
                    reconstructed[household.cell_id].get(product, 0.0) + quantity
                )
            for product, quantity in household.discretionary_needs.items():
                reconstructed[household.cell_id][product] = (
                    reconstructed[household.cell_id].get(product, 0.0) + quantity
                )
        for cid, products in demand.items():
            for product, quantity in products.items():
                self.assertAlmostEqual(reconstructed[cid][product], quantity)

    def test_household_panel_is_stable_when_period_demand_scales(self):
        base = {"cell-a": {"food": 10.0, "care": 2.0}}
        doubled = {"cell-a": {"food": 20.0, "care": 4.0}}
        first = households_from_cell_demand(
            base, households_per_cell=5, seed=123, priority_dispersion=0.4)
        second = households_from_cell_demand(
            doubled, households_per_cell=5, seed=123, priority_dispersion=0.4)
        self.assertEqual([h.household_id for h in first],
                         [h.household_id for h in second])
        for a, b in zip(first, second):
            self.assertAlmostEqual(a.essential_priority, b.essential_priority)
            self.assertAlmostEqual(a.discretionary_priority, b.discretionary_priority)
            for product, quantity in a.essential_needs.items():
                self.assertAlmostEqual(b.essential_needs[product], 2.0 * quantity)

    def test_stage_b_consumption_is_disaggregated_without_new_goods(self):
        model = DynamicCellularEconomy(
            "cellular", seed=12, shock="compound", cellular_hops=2)
        period = model.step(1)
        result = distribute_period_to_households(
            period, households_per_cell=4, policy="proportional", seed=99)
        self.assertTrue(result["is_posthoc_decomposition"])
        self.assertEqual(result["metrics"]["households"], 28)
        self.assertAlmostEqual(
            result["metrics"]["essential_fulfilment"],
            period.essential_fulfilment,
            places=9,
        )
        stage_b_total = sum(
            quantity
            for products in period.final_consumption_by_cell.values()
            for quantity in products.values()
        )
        self.assertAlmostEqual(result["metrics"]["overall_served"], stage_b_total, places=9)
        for cell_id, products in period.final_consumption_by_cell.items():
            for product, quantity in products.items():
                unassigned = result["unassigned_consumption_by_cell"][cell_id][product]
                self.assertGreaterEqual(unassigned, -1e-10)
                self.assertAlmostEqual(
                    unassigned, quantity - sum(
                        a.essential_served.get(product, 0.0)
                        + a.discretionary_served.get(product, 0.0)
                        for a in result["allocations"] if a.cell_id == cell_id
                    ),
                    places=9,
                )

    def test_horizon_summary_preserves_persistent_households_and_physical_totals(self):
        model = DynamicCellularEconomy(
            "cellular", seed=18, shock="compound", cellular_hops=2)
        model.run(5)
        result = summarize_periods_to_households(
            model.periods, households_per_cell=4, policy="priority_weighted",
            seed=1800, priority_dispersion=0.4,
        )
        self.assertEqual(result["periods"], 5)
        self.assertEqual(result["households"], 28)
        expected_essential = sum(
            period.final_consumption_by_product.get("food", 0.0)
            + period.final_consumption_by_product.get("care", 0.0)
            for period in model.periods
        )
        self.assertAlmostEqual(result["essential_served"], expected_essential)
        self.assertGreaterEqual(
            result["worst_period_minimum_household_essential_fulfilment"], 0.0)
        self.assertLessEqual(
            result["worst_period_minimum_household_essential_fulfilment"], 1.0)

    def test_paired_distribution_experiment_preserves_aggregate_physical_service(self):
        result = run_household_distribution_experiment(
            runs=3, shock="compound", periods=6, cellular_hops=2,
            households_per_cell=4, priority_dispersion=0.4,
            economic_policies=("cellular",),
        )
        paired = result["paired_priority_weighted_minus_proportional"]["cellular"]
        for rule in ("priority_weighted", "floor_priority"):
            self.assertEqual(paired[rule]["overall_fulfilment"]["n"], 3)
            self.assertAlmostEqual(
                paired[rule]["overall_fulfilment"]["mean"], 0.0, places=10)
            self.assertAlmostEqual(
                paired[rule]["essential_fulfilment"]["mean"], 0.0, places=10)

    def test_invalid_household_count_rejected(self):
        with self.assertRaises(HouseholdBridgeError):
            households_from_cell_demand({"cell-a": {"food": 1.0}}, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
