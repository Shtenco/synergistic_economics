import unittest
from types import SimpleNamespace

from household_distribution import (
    Household, HouseholdDistributionError, allocate_households,
    allocate_period_households, generate_synthetic_households,
    compare_household_distribution_policies,
    evaluate_households, validate_household_allocation,
)


class HouseholdDistributionTests(unittest.TestCase):
    def setUp(self):
        self.households = (
            Household(
                "h1", "cell-a", {"food": 4.0, "care": 1.0},
                {"food": 2.0, "books": 1.0}, 2.0, 1.0,
            ),
            Household(
                "h2", "cell-a", {"food": 2.0, "care": 1.0},
                {"food": 2.0, "books": 1.0}, 1.0, 1.0,
            ),
            Household(
                "h3", "cell-b", {"food": 3.0, "care": 1.0},
                {"books": 2.0}, 1.5, 1.0,
            ),
        )
        self.supply = {
            "cell-a": {"food": 6.0, "care": 1.0, "books": 1.0},
            "cell-b": {"food": 2.0, "care": 1.0, "books": 2.0},
        }

    def test_essential_needs_are_served_before_discretionary_needs(self):
        allocations = allocate_households(self.households, self.supply, "proportional")
        by_id = {a.household_id: a for a in allocations}
        self.assertAlmostEqual(by_id["h1"].essential_served["food"], 4.0)
        self.assertAlmostEqual(by_id["h2"].essential_served["food"], 2.0)
        self.assertAlmostEqual(by_id["h1"].discretionary_served["food"], 0.0)
        self.assertAlmostEqual(by_id["h2"].discretionary_served["food"], 0.0)
        self.assertTrue(validate_household_allocation(
            self.households, self.supply, allocations))

    def test_priority_weighting_changes_scarce_essential_distribution(self):
        households = (
            Household("priority", "cell", {"food": 4.0}, {}, 3.0),
            Household("standard", "cell", {"food": 4.0}, {}, 1.0),
        )
        supply = {"cell": {"food": 4.0}}
        proportional = allocate_households(households, supply, "proportional")
        weighted = allocate_households(households, supply, "priority_weighted")
        p = {a.household_id: a.essential_served["food"] for a in proportional}
        w = {a.household_id: a.essential_served["food"] for a in weighted}
        self.assertAlmostEqual(p["priority"], 2.0)
        self.assertAlmostEqual(p["standard"], 2.0)
        self.assertAlmostEqual(w["priority"], 3.0)
        self.assertAlmostEqual(w["standard"], 1.0)
        self.assertAlmostEqual(sum(w.values()), 4.0)

    def test_cell_supply_cannot_be_used_by_another_cell(self):
        households = (
            Household("need-a", "cell-a", {"food": 5.0}, {}),
            Household("need-b", "cell-b", {"food": 5.0}, {}),
        )
        supply = {"cell-a": {"food": 5.0}, "cell-b": {"food": 0.0}}
        allocations = allocate_households(households, supply)
        by_id = {a.household_id: a for a in allocations}
        self.assertAlmostEqual(by_id["need-a"].essential_served["food"], 5.0)
        self.assertAlmostEqual(by_id["need-b"].essential_served["food"], 0.0)
        self.assertTrue(validate_household_allocation(households, supply, allocations))

    def test_supply_conservation_and_need_bounds(self):
        allocations = allocate_households(self.households, self.supply, "priority_weighted")
        self.assertTrue(validate_household_allocation(
            self.households, self.supply, allocations))
        for allocation in allocations:
            household = next(h for h in self.households if h.household_id == allocation.household_id)
            for product, quantity in allocation.essential_served.items():
                self.assertLessEqual(quantity, household.essential_needs.get(product, 0.0) + 1e-10)
            for product, quantity in allocation.discretionary_served.items():
                self.assertLessEqual(quantity, household.discretionary_needs.get(product, 0.0) + 1e-10)

    def test_metrics_expose_lower_tail_and_inequality(self):
        allocations = allocate_households(self.households, self.supply, "proportional")
        metrics = evaluate_households(self.households, allocations)
        self.assertEqual(metrics["households"], 3)
        self.assertGreaterEqual(metrics["essential_fulfilment"], 0.0)
        self.assertLessEqual(metrics["essential_fulfilment"], 1.0)
        self.assertLessEqual(
            metrics["lower_decile_household_essential_fulfilment"],
            metrics["essential_fulfilment"] + 1e-10,
        )
        self.assertGreaterEqual(metrics["essential_fulfilment_gini"], 0.0)
        self.assertIn("food", metrics["per_product_essential"])

    def test_stage_b_period_result_is_disaggregated_without_double_counting(self):
        households = (
            Household("h-a", "cell-a", {"food": 2.0}, {"books": 1.0}),
            Household("h-b", "cell-b", {"food": 3.0}, {"books": 2.0}),
        )
        period = SimpleNamespace(final_consumption_by_cell={
            "cell-a": {"food": 2.0, "books": 1.0},
            "cell-b": {"food": 3.0, "books": 2.0},
        })
        allocations = allocate_period_households(households, period)
        self.assertEqual(
            sum(sum(a.essential_served.values()) for a in allocations), 5.0
        )
        self.assertEqual(
            sum(sum(a.discretionary_served.values()) for a in allocations), 3.0
        )
        self.assertTrue(validate_household_allocation(
            households, period.final_consumption_by_cell, allocations))

    def test_validator_rejects_duplicate_allocation_records(self):
        household = Household("h", "cell-a", {"food": 1.0}, {})
        allocation = allocate_households(
            (household,), {"cell-a": {"food": 3.0}})[0]
        with self.assertRaises(HouseholdDistributionError):
            validate_household_allocation(
                (household,), {"cell-a": {"food": 3.0}},
                (allocation, allocation),
            )

    def test_evaluation_rejects_cross_cell_and_over_need_records(self):
        household = Household("h", "cell-a", {"food": 1.0}, {})
        wrong_cell = type(allocate_households(
            (household,), {"cell-a": {"food": 1.0}})[0])(
                "h", "cell-b", {"food": 1.0}, {})
        with self.assertRaises(HouseholdDistributionError):
            evaluate_households((household,), (wrong_cell,))
        over_need = type(wrong_cell)("h", "cell-a", {"food": 2.0}, {})
        with self.assertRaises(HouseholdDistributionError):
            evaluate_households((household,), (over_need,))

    def test_synthetic_households_are_reproducible_and_reconcile_to_cell_demand(self):
        demand = {
            "cell-a": {"food": 12.0, "care": 3.0, "books": 6.0},
            "cell-b": {"food": 8.0, "care": 2.0, "books": 4.0},
        }
        a = generate_synthetic_households(demand, households_per_cell=5, seed=71)
        b = generate_synthetic_households(demand, households_per_cell=5, seed=71)
        self.assertEqual(a, b)
        for cid, products in demand.items():
            members = [h for h in a if h.cell_id == cid]
            for product, total in products.items():
                if product in ("food", "care"):
                    actual = sum(h.essential_needs.get(product, 0.0) for h in members)
                else:
                    actual = sum(h.discretionary_needs.get(product, 0.0) for h in members)
                self.assertAlmostEqual(actual, total)

    def test_distribution_policies_use_identical_stage_b_world_and_supplies(self):
        period = SimpleNamespace(
            final_demand_by_cell={
                "cell-a": {"food": 10.0, "care": 2.0, "books": 4.0},
                "cell-b": {"food": 8.0, "care": 2.0, "books": 3.0},
            },
            final_consumption_by_cell={
                "cell-a": {"food": 5.0, "care": 1.0, "books": 2.0},
                "cell-b": {"food": 4.0, "care": 1.0, "books": 1.0},
            },
        )
        result = compare_household_distribution_policies(
            period, households_per_cell=6, seed=19)
        self.assertEqual(result["household_count"], 12)
        self.assertEqual(set(result["policies"]), {"proportional", "priority_weighted"})
        for metrics in result["policies"].values():
            self.assertAlmostEqual(metrics["essential_served"], 11.0)
            self.assertAlmostEqual(metrics["overall_served"], 14.0)

    def test_tiny_negative_floating_residue_is_clamped_but_not_material_shortage(self):
        household = Household("h", "cell-a", {"food": 1.0}, {})
        supply = {"cell-a": {"food": -1e-12}}
        allocations = allocate_households((household,), supply)
        self.assertAlmostEqual(allocations[0].essential_served["food"], 0.0)
        self.assertTrue(validate_household_allocation(
            (household,), supply, allocations))
        with self.assertRaises(HouseholdDistributionError):
            allocate_households(
                (household,), {"cell-a": {"food": -1e-4}})

    def test_unknown_policy_rejected(self):
        with self.assertRaises(HouseholdDistributionError):
            allocate_households(self.households, self.supply, "central")

    def test_non_finite_needs_priorities_and_supply_rejected(self):
        with self.assertRaises(HouseholdDistributionError):
            allocate_households(
                (Household("nan", "cell", {"food": float("nan")}, {}),),
                {"cell": {"food": 1.0}},
            )
        with self.assertRaises(HouseholdDistributionError):
            allocate_households(
                (Household("inf", "cell", {"food": 1.0}, {},
                           essential_priority=float("inf")),),
                {"cell": {"food": 1.0}},
            )
        with self.assertRaises(HouseholdDistributionError):
            allocate_households(
                (Household("ok", "cell", {"food": 1.0}, {}),),
                {"cell": {"food": float("nan")}},
            )

    def test_negative_needs_and_unknown_cells_rejected(self):
        with self.assertRaises(HouseholdDistributionError):
            allocate_households(
                (Household("bad", "cell-a", {"food": -1.0}, {}),),
                {"cell-a": {"food": 1.0}},
            )
        with self.assertRaises(HouseholdDistributionError):
            allocate_households(
                (Household("orphan", "missing", {"food": 1.0}, {}),),
                {"cell-a": {"food": 1.0}},
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
