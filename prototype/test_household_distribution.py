import unittest

from household_distribution import (
    Household, HouseholdDistributionError, allocate_households,
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
            "cell-a": {"food": 7.0, "care": 1.0, "books": 1.0},
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

    def test_unknown_policy_rejected(self):
        with self.assertRaises(HouseholdDistributionError):
            allocate_households(self.households, self.supply, "central")

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
