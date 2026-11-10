import unittest

from scc_dynamic_economy import DynamicCellularEconomy
from scc_household_bridge import (
    HouseholdBridgeError,
    distribute_period_to_households,
    households_from_cell_demand,
)


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
        for cell_id, products in period.final_consumption_by_cell.items():
            for product, quantity in products.items():
                unallocated = result["unallocated_supply_by_cell"][cell_id][product]
                self.assertGreaterEqual(unallocated, -1e-10)
                self.assertLessEqual(unallocated, quantity + 1e-10)

    def test_invalid_household_count_rejected(self):
        with self.assertRaises(HouseholdBridgeError):
            households_from_cell_demand({"cell-a": {"food": 1.0}}, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
