"""Integration tests for the read-only production execution preflight."""
import unittest
from datetime import timedelta

from cellular_cooperative_market import CooperativeMarketError
from capacity_resource_network import CapacitySnapshot, ResourceClaim
from production_graph_engine import ProductionGraph, ProductionGraphNode
from production_execution_preflight import validate_production_execution_preflight
from test_temporary_production_consortium import NOW, VERIFIED, fixtures


RESOURCE_EVIDENCE = frozenset({
    *VERIFIED,
    "requirement:cut", "requirement:finish",
    "capacity-authority", "capacity-evidence",
})


def scenario(capacity=4):
    organizations, agreement, order, _, plan = fixtures()
    graph = ProductionGraph(
        "graph-1", 4,
        (
            ProductionGraphNode(
                "cut", "org-a", frozenset({"steel:1"}), frozenset({"blank:1"}),
                frozenset(), "accept:a", "work:a",
                resource_requirement_ref="requirement:cut",
            ),
            ProductionGraphNode(
                "finish", "org-b", frozenset({"blank:1"}), frozenset({"product:x"}),
                frozenset({"cut"}), "accept:b", "work:b",
                resource_requirement_ref="requirement:finish",
            ),
        ),
        frozenset({"steel:1"}),
        frozenset({"graph:evidence", "requirement:cut", "requirement:finish"}),
    )
    start = NOW + timedelta(hours=1)
    end = NOW + timedelta(hours=3)
    claims = {
        "requirement:cut": (
            ResourceClaim("claim:cut", "machine:1", frozenset({"machining"}),
                          2, "machine-hour", start, end, 7),
        ),
        "requirement:finish": (
            ResourceClaim("claim:finish", "machine:1", frozenset({"machining"}),
                          2, "machine-hour", start, end, 7),
        ),
    }
    snapshot = CapacitySnapshot(
        "machine:1", "org-a", frozenset({"machining"}), capacity,
        "machine-hour", NOW, NOW + timedelta(days=1), NOW, 7,
        "capacity-authority", frozenset({"capacity-evidence"}),
    )
    return organizations, agreement, order, graph, plan, claims, {"machine:1": snapshot}


def run_preflight(data, verified=RESOURCE_EVIDENCE):
    organizations, agreement, order, graph, plan, claims, snapshots = data
    return validate_production_execution_preflight(
        plan=plan, agreement=agreement, order=order, graph=graph,
        claims_by_requirement=claims, snapshots=snapshots,
        organizations=organizations, verified_evidence_refs=verified, at=NOW,
    )


class ProductionExecutionPreflightTests(unittest.TestCase):
    def test_valid_plan_produces_exact_revision_receipt(self):
        receipt = run_preflight(scenario())
        self.assertEqual(receipt.plan_id, "plan-1")
        self.assertEqual(receipt.production_order_id, "order-1")
        self.assertEqual(receipt.graph_id, "graph-1")
        self.assertEqual(receipt.graph_revision, 4)
        self.assertEqual(receipt.resource_validation.resource_validation.peak_quantities,
                         (("machine:1", 4, "machine-hour"),))

    def test_cross_node_overbooking_fails_closed(self):
        with self.assertRaises(CooperativeMarketError):
            run_preflight(scenario(capacity=3))

    def test_missing_requirement_bundle_fails_closed(self):
        data = list(scenario())
        data[5] = {"requirement:cut": data[5]["requirement:cut"]}
        with self.assertRaises(CooperativeMarketError):
            run_preflight(tuple(data))

    def test_unverified_capacity_authority_fails_closed(self):
        with self.assertRaises(CooperativeMarketError):
            run_preflight(scenario(), RESOURCE_EVIDENCE - {"capacity-authority"})

    def test_stale_capacity_revision_fails_closed(self):
        data = list(scenario())
        claims = dict(data[5])
        claims["requirement:finish"] = (
            ResourceClaim("claim:finish", "machine:1", frozenset({"machining"}),
                          2, "machine-hour", NOW + timedelta(hours=1),
                          NOW + timedelta(hours=3), 6),
        )
        data[5] = claims
        with self.assertRaises(CooperativeMarketError):
            run_preflight(tuple(data))


if __name__ == "__main__":
    unittest.main(verbosity=2)
