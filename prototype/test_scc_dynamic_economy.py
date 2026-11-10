import unittest
from dataclasses import replace

from cellular_coordination import (
    Cell, World, allocate_cellular, allocate_relay_cellular, allocate_central,
    allocate_cooperative, allocate_market,
)
from scc_dynamic_economy import (
    DynamicCellularEconomy, DynamicEconomyError, compare, monte_carlo,
    coordination_sensitivity, coordination_frontier, coordination_curve,
)


class StageBPhysicalEconomyTests(unittest.TestCase):
    def test_stage_a_nets_own_stock_before_external_matching(self):
        world = World(
            cells=(
                Cell("a", {"food": 10.0}, {"food": 7.0}, {"food": 1.0}, {"food": 20.0}),
                Cell("b", {}, {}, {"food": 1.0}, {"food": 20.0}),
            ),
            edges=(("a", "b"),),
            prices={"food": 4.0},
        )
        for allocator in (allocate_market, allocate_central, allocate_cooperative):
            allocations = allocator(world)
            self.assertEqual(len(allocations), 0)
        self.assertEqual(allocate_cellular(world, 1), [])

    def test_no_regime_creates_self_trade(self):
        from cellular_coordination import default_world
        world = default_world(13)
        for allocator in (allocate_market, allocate_central, allocate_cooperative):
            for a in allocator(world):
                self.assertNotEqual(a.seller, a.buyer)
        for a in allocate_cellular(world, 2):
            self.assertNotEqual(a.seller, a.buyer)

    def test_all_regimes_run_dynamic_economy_and_preserve_resource_stock(self):
        for policy in ("market", "central", "cooperative", "cellular"):
            model = DynamicCellularEconomy(policy=policy, seed=5, shock="none")
            model.run(16)
            self.assertTrue(model.validate())
            summary = model.summary()
            self.assertGreater(summary["fixed_price_gross_output_index"], 0)
            self.assertGreater(summary["cumulative_final_consumption"], 0)
            self.assertGreater(summary["total_messages"], 0)
            self.assertGreater(summary["total_communication_cost"], 0)
            self.assertGreaterEqual(
                summary["total_coordination_cost"],
                summary["total_communication_cost"],
            )
            self.assertGreaterEqual(summary["ending_raw_resource"], 0)
            self.assertAlmostEqual(
                summary["initial_raw_resource"] + summary["regenerated_raw_resource"],
                summary["total_raw_resource_used"] + summary["ending_raw_resource"],
                places=6,
            )
            for c in model.cells.values():
                self.assertTrue(all(v >= -1e-9 for v in c.stocks.values()))

    def test_global_planner_uses_aggregate_declared_demand(self):
        central = DynamicCellularEconomy("central", seed=2, shock="none")
        cellular = DynamicCellularEconomy("cellular", seed=2, shock="none", cellular_hops=1)
        central.step(1)
        cellular.step(1)
        central_food = central.cells["cell-1"].output_this_period
        cellular_food = cellular.cells["cell-1"].output_this_period
        self.assertGreater(central_food, cellular_food)

    def test_local_reach_changes_cellular_information_boundary(self):
        local = DynamicCellularEconomy("cellular", seed=12, shock="none", cellular_hops=1)
        federated_reach = DynamicCellularEconomy("cellular", seed=12, shock="none", cellular_hops=2)
        local.run(10)
        federated_reach.run(10)
        self.assertNotEqual(
            local.summary()["fixed_price_gross_output_index"],
            federated_reach.summary()["fixed_price_gross_output_index"],
        )

    def test_same_seed_same_policy_is_reproducible(self):
        a = DynamicCellularEconomy("cellular", seed=19, shock="compound", cellular_hops=2)
        b = DynamicCellularEconomy("cellular", seed=19, shock="compound", cellular_hops=2)
        a.run(12)
        b.run(12)
        self.assertEqual(a.summary(), b.summary())

    def test_shocks_are_applied_and_reduce_resource_regeneration(self):
        normal = DynamicCellularEconomy("cellular", seed=4, shock="none")
        stressed = DynamicCellularEconomy("cellular", seed=4, shock="resource_shock")
        normal.run(12)
        stressed.run(12)
        self.assertLess(stressed.summary()["regenerated_raw_resource"],
                        normal.summary()["regenerated_raw_resource"])

    def test_paired_comparison_uses_same_seed_and_scenario(self):
        result = compare(seed=3, shock="compound", periods=10, cellular_hops=2)
        self.assertEqual(set(result), {"market", "central", "cooperative", "cellular"})
        for metrics in result.values():
            self.assertEqual(metrics["seed"], 3)
            self.assertEqual(metrics["shock"], "compound")
            self.assertEqual(metrics["periods"], 10)

    def test_monte_carlo_returns_paired_regimes(self):
        result = monte_carlo(runs=4, shock="demand_surge", periods=8, cellular_hops=2)
        self.assertEqual(result["runs"], 4)
        self.assertEqual(len(result["paired_runs"]), 16)
        for seed in range(1, 5):
            self.assertEqual(
                {r["policy"] for r in result["paired_runs"] if r["seed"] == seed},
                {"market", "central", "cooperative", "cellular"},
            )
        stats = result["summary"]["cellular"]["final_fulfilment_rate"]
        self.assertEqual(stats["n"], 4)
        self.assertLessEqual(stats["ci95_low"], stats["mean"])
        self.assertGreaterEqual(stats["ci95_high"], stats["mean"])
        difference = result["paired_differences_vs_market"]["cellular"]["final_fulfilment_rate"]
        self.assertEqual(difference["n"], 4)

    def test_coordination_messages_consume_productive_labour(self):
        zero_cost = DynamicCellularEconomy(
            "cellular", seed=23, shock="none", cellular_hops=2,
            coordination_hours_per_message=0.0,
        )
        costly = DynamicCellularEconomy(
            "cellular", seed=23, shock="none", cellular_hops=2,
            coordination_hours_per_message=0.10,
        )
        zero_cost.run(12)
        costly.run(12)
        self.assertGreater(costly.summary()["total_coordination_hours"], 0)
        self.assertLess(
            costly.summary()["fixed_price_gross_output_index"],
            zero_cost.summary()["fixed_price_gross_output_index"],
        )

    def test_stage_b_preserves_cell_trade_and_relay_permissions(self):
        specs = list(DynamicCellularEconomy.default_specs(17))
        specs[0] = replace(
            specs[0], trade_consent=False, relay_consent=False,
            allowed_counterparties=frozenset({"cell-2"}),
        )
        model = DynamicCellularEconomy(
            "cellular", seed=17, shock="none", specs=tuple(specs))
        world = model._matching_world(
            {"food": {"cell-1": 3.0}},
            {"food": {"cell-2": 2.0}},
        )
        seller = next(c for c in world.cells if c.cell_id == "cell-1")
        self.assertFalse(seller.trade_consent)
        self.assertFalse(seller.relay_consent)
        self.assertEqual(seller.allowed_counterparties, frozenset({"cell-2"}))

    def test_dynamic_model_accepts_distinct_sparse_communication_network(self):
        sparse_messages = (
            ("cell-1", "cell-2"),
            ("cell-2", "cell-3"),
            ("cell-3", "cell-4"),
        )
        model = DynamicCellularEconomy(
            "cellular", seed=8, shock="none", cellular_hops=2,
            communication_edges=sparse_messages,
        )
        model.run(8)
        self.assertTrue(model.validate())
        self.assertGreaterEqual(model.summary()["total_messages"], 0)

    def test_batched_packets_reduce_fixed_coordination_overhead(self):
        model = DynamicCellularEconomy(
            "cellular", seed=5, shock="none",
            coordination_hours_per_message=0.01,
            coordination_hours_per_additional_record=0.002,
        )
        bundled = model._message_load([
            {"sender": "cell-1", "receiver": "cell-2", "records": 2},
        ])
        separate = model._message_load([
            {"sender": "cell-1", "receiver": "cell-2", "records": 1},
            {"sender": "cell-1", "receiver": "cell-2", "records": 1},
        ])
        self.assertAlmostEqual(sum(bundled.values()), 0.012)
        self.assertAlmostEqual(sum(separate.values()), 0.020)
        model.run(6)
        summary = model.summary()
        self.assertGreater(summary["total_coordination_hours"], 0.0)
        self.assertEqual(summary["coordination_hours_per_additional_record"], 0.002)

    def test_per_record_labour_cost_is_propagated_into_monte_carlo(self):
        free_records = monte_carlo(
            runs=2, shock="compound", periods=8, cellular_hops=2,
            coordination_hours_per_message=0.01,
            coordination_hours_per_additional_record=0.0,
        )
        costly_records = monte_carlo(
            runs=2, shock="compound", periods=8, cellular_hops=2,
            coordination_hours_per_message=0.01,
            coordination_hours_per_additional_record=0.01,
        )
        free = free_records["summary"]["cellular"]["coordination_hours_per_additional_record"]["mean"]
        costly = costly_records["summary"]["cellular"]["coordination_hours_per_additional_record"]["mean"]
        self.assertEqual(free, 0.0)
        self.assertEqual(costly, 0.01)

    def test_paired_coordination_sensitivity_uses_same_seeds(self):
        result = coordination_sensitivity(
            runs=3, shock="compound", periods=8, cellular_hops=2,
            base_hours=0.01, stress_hours=0.05,
        )
        self.assertEqual(result["runs"], 3)
        cellular = result["sensitivity"]["cellular"]
        self.assertEqual(
            cellular["fixed_price_final_consumption_index"]["paired_stress_minus_base"]["n"],
            3,
        )
        self.assertLess(
            cellular["fixed_price_final_consumption_index"]["paired_stress_minus_base"]["mean"],
            0,
        )
        self.assertGreater(
            cellular["total_coordination_hours"]["paired_stress_minus_base"]["mean"],
            0,
        )

    def test_coordination_curve_is_paired_and_reports_all_levels(self):
        result = coordination_curve(
            runs=3, shock="compound", periods=8, cellular_hops=2,
            hours_per_message=(0.0, 0.01, 0.05),
        )
        self.assertEqual(result["hours_per_message"], [0.0, 0.01, 0.05])
        cellular = result["curve"]["cellular"]
        self.assertIn("0.0", cellular)
        self.assertIn("0.01", cellular)
        self.assertIn("0.05", cellular)
        self.assertEqual(
            cellular["0.05"]["final_fulfilment_rate"]["paired_delta_vs_reference"]["n"],
            3,
        )
        self.assertGreater(
            cellular["0.05"]["total_coordination_hours"]["mean"],
            cellular["0.0"]["total_coordination_hours"]["mean"],
        )

    def test_coordination_frontier_is_paired_and_validates_levels(self):
        result = coordination_frontier(
            runs=3, shock="compound", periods=8, cellular_hops=2,
            hours_levels=(0.0, 0.01, 0.05),
        )
        self.assertEqual(result["runs"], 3)
        cellular = result["frontier"]["cellular"]
        self.assertEqual(
            cellular["0.05"]["paired_difference_vs_zero_hours"]
            ["fixed_price_final_consumption_index"]["n"], 3,
        )
        self.assertLess(
            cellular["0.05"]["paired_difference_vs_zero_hours"]
            ["fixed_price_final_consumption_index"]["mean"], 0,
        )
        self.assertGreater(
            cellular["0.05"]["metrics"]["total_coordination_hours"]["mean"],
            cellular["0.01"]["metrics"]["total_coordination_hours"]["mean"],
        )
        with self.assertRaises(DynamicEconomyError):
            coordination_frontier(runs=3, hours_levels=(0.01, 0.05))

    def test_stage_b_trade_consent_blocks_external_delivery(self):
        specs = list(DynamicCellularEconomy.default_specs(31))
        specs = [
            replace(spec, trade_consent=False) if spec.cell_id == "cell-1" else spec
            for spec in specs
        ]
        model = DynamicCellularEconomy(
            "cellular", specs=specs, cellular_hops=2,
            communication_edges=(("cell-1", "cell-2"), ("cell-2", "cell-3")),
        )
        world = model._matching_world(
            {"food": {"cell-1": 5.0}},
            {"food": {"cell-3": 5.0}},
        )
        self.assertEqual(allocate_relay_cellular(world, max_hops=2), [])

    def test_stage_b_relay_consent_controls_multihop_reach(self):
        base = list(DynamicCellularEconomy.default_specs(32))
        chain = (("cell-1", "cell-2"), ("cell-2", "cell-3"))
        supply = {"food": {"cell-1": 5.0}}
        demand = {"food": {"cell-3": 5.0}}

        blocked_specs = [
            replace(spec, relay_consent=False) if spec.cell_id == "cell-2" else spec
            for spec in base
        ]
        blocked = DynamicCellularEconomy(
            "cellular", specs=blocked_specs, cellular_hops=2,
            communication_edges=chain,
        )
        blocked_world = blocked._matching_world(supply, demand)
        self.assertEqual(allocate_relay_cellular(blocked_world, max_hops=2), [])

        permitted = DynamicCellularEconomy(
            "cellular", specs=base, cellular_hops=2,
            communication_edges=chain,
        )
        permitted_world = permitted._matching_world(supply, demand)
        self.assertEqual(
            sum(a.quantity for a in allocate_relay_cellular(permitted_world, max_hops=2)),
            5.0,
        )

    def test_invalid_policy_rejected(self):
        with self.assertRaises(DynamicEconomyError):
            DynamicCellularEconomy("wishful-thinking")


if __name__ == "__main__":
    unittest.main(verbosity=2)
