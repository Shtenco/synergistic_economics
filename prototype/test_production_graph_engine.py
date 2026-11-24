"""Adversarial tests for production dependency graph validation."""
import unittest

from cellular_cooperative_market import CooperativeMarketError, EconomicOrganization
from production_graph_engine import (
    ProductionGraph, ProductionGraphNode, validate_production_graph,
)

VERIFIED = frozenset({
    "scope:a", "scope:b", "scope:c", "accept:a", "accept:b", "accept:c",
    "mandate:a", "wp:a",
})


def org(identifier, roles=frozenset({"enterprise"}), status="active"):
    return EconomicOrganization(identifier, "KZ", "cooperative", roles,
                                 f"charter:{identifier}", status)


def node(identifier, *, inputs=(), outputs=(), predecessors=(), executor="factory-a",
         acceptance="accept:a", scope="scope:a", mandate=None, work_package=None):
    return ProductionGraphNode(
        identifier, executor, frozenset(inputs), frozenset(outputs),
        frozenset(predecessors), acceptance, scope, mandate, work_package,
    )


def graph(nodes, external=(), evidence=VERIFIED):
    return ProductionGraph("graph-1", 4, tuple(nodes), frozenset(external), evidence)


class ProductionGraphTests(unittest.TestCase):
    def validate(self, value, organizations=None, verified=None):
        return validate_production_graph(
            value, organizations=organizations or {
                "factory-a": org("factory-a"), "artel-b": org("artel-b", frozenset({"artel"})),
                "factory-c": org("factory-c"),
            }, verified_evidence_refs=value.evidence_refs if verified is None else verified,
        )

    def test_valid_linear_multi_organization_graph(self):
        value = graph([
            node("cut", inputs={"steel:lot-1"}, outputs={"blank:1"}),
            node("mill", inputs={"blank:1"}, outputs={"part:1"}, predecessors={"cut"}, executor="artel-b",
                 acceptance="accept:b", scope="scope:b", mandate="mandate:a", work_package="wp:a"),
            node("assemble", inputs={"part:1", "electronics:lot-2"}, outputs={"product:1"},
                 predecessors={"mill"}, executor="factory-c", acceptance="accept:c", scope="scope:c"),
        ], external={"steel:lot-1", "electronics:lot-2"})
        result = self.validate(value)
        self.assertEqual(result.topological_order, ("cut", "mill", "assemble"))
        self.assertEqual(result.node_count, 3)
        self.assertEqual(len(result.organization_ids), 3)

    def test_topological_order_is_deterministic(self):
        value = graph([
            node("z", inputs={"raw:z"}, outputs={"out:z"}),
            node("a", inputs={"raw:a"}, outputs={"out:a"}),
        ], external={"raw:z", "raw:a"})
        self.assertEqual(self.validate(value).topological_order, ("a", "z"))

    def test_duplicate_node_id_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([node("same", inputs={"raw"}, outputs={"x"}),
                                 node("same", inputs={"raw"}, outputs={"y"})], external={"raw"}))

    def test_duplicate_output_provenance_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([node("a", inputs={"raw"}, outputs={"x"}),
                                 node("b", inputs={"raw"}, outputs={"x"})], external={"raw"}))

    def test_external_input_cannot_also_be_produced(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([node("a", inputs={"raw"}, outputs={"x"})], external={"raw", "x"}))

    def test_missing_input_source_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([node("a", inputs={"missing"}, outputs={"x"})]))

    def test_unknown_predecessor_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([node("a", inputs={"raw"}, outputs={"x"}, predecessors={"ghost"})], external={"raw"}))

    def test_predecessor_must_match_data_provenance(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([
                node("a", inputs={"raw"}, outputs={"x"}),
                node("b", inputs={"raw"}, outputs={"y"}, predecessors={"a"}),
            ], external={"raw"}))

    def test_cycle_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([
                node("a", inputs={"y"}, outputs={"x"}, predecessors={"b"}),
                node("b", inputs={"x"}, outputs={"y"}, predecessors={"a"}),
            ]))

    def test_inactive_executor_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([node("a", inputs={"raw"}, outputs={"x"})], external={"raw"}),
                          organizations={"factory-a": org("factory-a", status="suspended")})

    def test_missing_artel_mandate_and_work_package_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(graph([node("a", inputs={"raw"}, outputs={"x"}, executor="artel-b")],
                                external={"raw"}))

    def test_artel_mandate_and_work_package_accepted(self):
        value = graph([node("a", inputs={"raw"}, outputs={"x"}, executor="artel-b",
                            mandate="mandate:a", work_package="wp:a")], external={"raw"})
        self.assertEqual(self.validate(value).topological_order, ("a",))

    def test_unverified_scope_or_acceptance_rejected(self):
        value = graph([node("a", inputs={"raw"}, outputs={"x"})], external={"raw"},
                      evidence=frozenset())
        with self.assertRaises(CooperativeMarketError):
            self.validate(value)

    def test_graph_level_evidence_must_be_verified(self):
        value = graph([node("a", inputs={"raw"}, outputs={"x"})], external={"raw"},
                      evidence=frozenset({"graph-manifest:1"}))
        with self.assertRaises(CooperativeMarketError):
            self.validate(value, verified=frozenset())

    def test_bool_revision_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            ProductionGraph("graph-1", True, (node("a", inputs={"raw"}, outputs={"x"}),),
                            frozenset({"raw"}), VERIFIED)

    def test_empty_graph_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            ProductionGraph("graph-1", 0, (), frozenset(), VERIFIED)


if __name__ == "__main__":
    unittest.main(verbosity=2)
