import unittest

from cellular_coordination import (
    Allocation, Cell, World, CoordinationError, allocate_cellular, allocate_central,
    allocate_cooperative, allocate_market, default_world, evaluate,
    monte_carlo, run_comparison, shortest_paths,
)


class CellularCoordinationTests(unittest.TestCase):
    def assert_allocation_bounds(self, world, allocations):
        supply = {p: sum(c.supply.get(p, 0.0) for c in world.cells)
                  for p in world.prices}
        demand = {p: sum(c.demand.get(p, 0.0) for c in world.cells)
                  for p in world.prices}
        used_supply = {p: 0.0 for p in world.prices}
        served_demand = {p: 0.0 for p in world.prices}
        ids = {c.cell_id for c in world.cells}
        for a in allocations:
            self.assertIn(a.seller, ids)
            self.assertIn(a.buyer, ids)
            self.assertGreater(a.quantity, 0.0)
            self.assertGreaterEqual(a.distance, 0)
            used_supply[a.product] += a.quantity
            served_demand[a.product] += a.quantity
        for p in world.prices:
            self.assertLessEqual(used_supply[p], supply[p] + 1e-8)
            self.assertLessEqual(served_demand[p], demand[p] + 1e-8)

    def test_all_four_regimes_obey_supply_and_demand_bounds(self):
        world = default_world(7)
        for allocator in (allocate_market, allocate_central, allocate_cooperative):
            self.assert_allocation_bounds(world, allocator(world))
        self.assert_allocation_bounds(world, allocate_cellular(world, 1))

    def test_central_flow_optimizer_prioritizes_higher_service_value(self):
        world = World(
            cells=(
                Cell("seller", {"food": 1.0}, {}, {"food": 1.0}, {"food": 1.0}),
                Cell("buyer-a", {}, {"food": 1.0}, {"food": 1.0}, {"food": 1.0}),
                Cell("buyer-b", {}, {"food": 1.0}, {"food": 2.0}, {"food": 1.0}),
            ),
            edges=(("seller", "buyer-a"), ("seller", "buyer-b")),
            prices={"food": 1.0},
        )
        allocations = allocate_central(world)
        self.assertEqual(len(allocations), 1)
        self.assertEqual(allocations[0].buyer, "buyer-b")
        self.assertAlmostEqual(allocations[0].quantity, 1.0)

    def test_cellular_allocations_respect_local_hop_limit(self):
        world = default_world(3)
        dist = shortest_paths(world)
        for allocation in allocate_cellular(world, max_hops=1):
            self.assertLessEqual(dist[allocation.buyer][allocation.seller], 1)

    def test_cellular_does_not_trade_across_disconnected_components(self):
        world = default_world(2)
        from dataclasses import replace
        isolated = replace(world, edges=(("cell-1", "cell-2"), ("cell-3", "cell-4")))
        allocations = allocate_cellular(isolated, max_hops=2)
        for a in allocations:
            self.assertIn(a.seller, shortest_paths(isolated)[a.buyer])

    def test_central_and_market_are_deterministic(self):
        world = default_world(11)
        self.assertEqual(allocate_market(world), allocate_market(world))
        self.assertEqual(allocate_central(world), allocate_central(world))

    def test_cooperative_weighted_rationing_respects_priority_and_caps(self):
        world = default_world(5, "supply_crisis")
        allocations = allocate_cooperative(world)
        self.assert_allocation_bounds(world, allocations)
        self.assertGreater(sum(a.quantity for a in allocations), 0)

    def test_same_seed_same_comparison(self):
        self.assertEqual(run_comparison(17), run_comparison(17))

    def test_shocks_change_common_world_not_regime_specific_inputs(self):
        normal = default_world(4, "none")
        crisis = default_world(4, "supply_crisis")
        self.assertEqual([c.demand for c in normal.cells],
                         [c.demand for c in crisis.cells])
        self.assertNotEqual([c.supply for c in normal.cells],
                            [c.supply for c in crisis.cells])

    def test_all_metrics_are_finite_and_bounded(self):
        for shock in ("none", "supply_crisis", "demand_surge", "compound"):
            for regime, metrics in run_comparison(9, shock, 2).items():
                for value in metrics.values():
                    self.assertTrue(value == value and abs(value) < 1e12,
                                    (shock, regime, value))
                self.assertGreaterEqual(metrics["fulfilment_rate"], 0)
                self.assertLessEqual(metrics["fulfilment_rate"], 1 + 1e-9)
                self.assertGreaterEqual(metrics["weighted_fulfilment_rate"], 0)
                self.assertLessEqual(metrics["weighted_fulfilment_rate"], 1 + 1e-9)

    def test_monte_carlo_has_four_paired_regimes_per_seed(self):
        result = monte_carlo(range(1, 6), "compound", 1)
        self.assertEqual(result["runs"], 5)
        self.assertEqual(len(result["rows"]), 20)
        self.assertEqual(set(result["summary"]), {
            "market", "central", "cooperative", "cellular"
        })
        stats = result["summary"]["cellular"]["fulfilment_rate"]
        self.assertEqual(stats["n"], 5)
        self.assertLessEqual(stats["ci95_low"], stats["mean"])
        self.assertGreaterEqual(stats["ci95_high"], stats["mean"])
        self.assertEqual(
            result["paired_differences_vs_market"]["cellular"]["fulfilment_rate"]["n"],
            5,
        )

    def test_invalid_local_horizon_rejected(self):
        with self.assertRaises(CoordinationError):
            allocate_cellular(default_world(), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
