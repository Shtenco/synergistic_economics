"""Adversarial tests for temporary production consortium composition."""
import unittest
from datetime import datetime, timedelta, timezone

from cellular_cooperative_market import (
    CooperationAgreement, ConsortiumParticipant, CooperativeMarketError, EconomicOrganization,
)
from cooperative_production_network import ProductionOrder
from production_graph_engine import ProductionGraph, ProductionGraphNode
from temporary_production_consortium import (
    ConsortiumAssignment, TemporaryProductionConsortium,
    validate_temporary_production_consortium,
)

NOW = datetime(2026, 11, 25, 7, 0, tzinfo=timezone.utc)
VERIFIED = frozenset({
    "agreement:1", "commit:a", "authority:a", "scope:a",
    "commit:b", "authority:b", "scope:b",
    "graph:evidence", "accept:a", "work:a", "accept:b", "work:b",
})


def org(identifier, roles=frozenset({"enterprise"}), status="active"):
    return EconomicOrganization(identifier, "KZ", "cooperative", roles, f"charter:{identifier}", status)


def fixtures():
    organizations = {"org-a": org("org-a"), "org-b": org("org-b")}
    agreement = CooperationAgreement(
        "agreement-1", "Manufacture product X", "graph:1", "KZ",
        (
            ConsortiumParticipant("org-a", "commit:a", "authority:a"),
            ConsortiumParticipant("org-b", "commit:b", "authority:b"),
        ),
        "agreement:1", NOW, NOW + timedelta(days=10),
    )
    order = ProductionOrder(
        order_id="order-1", requester_organization_id="buyer",
        router_demand_id="demand:1", scope="product X",
        deliverable_ref="product:x", required_capability_refs=frozenset({"manufacturing"}),
        quantity=1, unit="batch", delivery_from=NOW,
        delivery_to=NOW + timedelta(days=8), quality_criteria_ref="quality:1",
        contract_terms_ref="contract:1", expected_revision=1, idempotency_key="order:create:1",
    )
    graph = ProductionGraph(
        "graph-1", 4,
        (
            ProductionGraphNode("cut", "org-a", frozenset({"steel:1"}), frozenset({"blank:1"}),
                                frozenset(), "accept:a", "work:a"),
            ProductionGraphNode("finish", "org-b", frozenset({"blank:1"}), frozenset({"product:x"}),
                                frozenset({"cut"}), "accept:b", "work:b"),
        ),
        frozenset({"steel:1"}), frozenset({"graph:evidence"}),
    )
    plan = TemporaryProductionConsortium(
        "plan-1", "agreement-1", "agreement:1", "order-1", "graph-1", 4,
        NOW + timedelta(hours=1), NOW + timedelta(days=7),
        (
            ConsortiumAssignment("org-a", "producer", frozenset({"cut"}), "commit:a", "authority:a", "scope:a"),
            ConsortiumAssignment("org-b", "producer", frozenset({"finish"}), "commit:b", "authority:b", "scope:b"),
        ),
        frozenset({"graph:evidence"}),
    )
    return organizations, agreement, order, graph, plan


def validate(organizations=None, agreement=None, order=None, graph=None, plan=None, verified=VERIFIED):
    o, a, p, g, x = fixtures()
    return validate_temporary_production_consortium(
        plan or x, agreement=agreement or a, order=order or p, graph=graph or g,
        organizations=o if organizations is None else organizations,
        verified_evidence_refs=verified,
    )


class TemporaryProductionConsortiumTests(unittest.TestCase):
    def test_valid_two_organization_chain(self):
        result = validate()
        self.assertEqual(result.producer_organization_ids, ("org-a", "org-b"))
        self.assertEqual(result.node_assignments, (("cut", "org-a"), ("finish", "org-b")))

    def test_exact_agreement_reference_required(self):
        o, a, p, g, x = fixtures()
        wrong = TemporaryProductionConsortium(
            x.plan_id, x.agreement_id, "agreement:other", x.production_order_id,
            x.graph_id, x.graph_revision, x.effective_from, x.effective_to, x.assignments, x.evidence_refs,
        )
        with self.assertRaises(CooperativeMarketError):
            validate(plan=wrong)

    def test_exact_order_required(self):
        o, a, p, g, x = fixtures()
        with self.assertRaises(CooperativeMarketError):
            validate(order=ProductionOrder(
                order_id="other-order", requester_organization_id=p.requester_organization_id,
                router_demand_id=p.router_demand_id, scope=p.scope, deliverable_ref=p.deliverable_ref,
                required_capability_refs=p.required_capability_refs, quantity=p.quantity, unit=p.unit,
                delivery_from=p.delivery_from, delivery_to=p.delivery_to, quality_criteria_ref=p.quality_criteria_ref,
                contract_terms_ref=p.contract_terms_ref, expected_revision=p.expected_revision,
                idempotency_key=p.idempotency_key,
            ))

    def test_graph_revision_mismatch_rejected(self):
        o, a, p, g, x = fixtures()
        changed = ProductionGraph(g.graph_id, g.revision + 1, g.nodes, g.external_input_refs, g.evidence_refs)
        with self.assertRaises(CooperativeMarketError):
            validate(graph=changed)

    def test_inactive_participant_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate(organizations={"org-a": org("org-a", status="suspended"), "org-b": org("org-b")})

    def test_plan_outside_agreement_window_rejected(self):
        o, a, p, g, x = fixtures()
        invalid = TemporaryProductionConsortium(
            x.plan_id, x.agreement_id, x.agreement_ref, x.production_order_id, x.graph_id, x.graph_revision,
            NOW - timedelta(days=1), x.effective_to, x.assignments, x.evidence_refs,
        )
        with self.assertRaises(CooperativeMarketError):
            validate(plan=invalid)

    def test_plan_outside_order_window_rejected(self):
        o, a, p, g, x = fixtures()
        invalid = TemporaryProductionConsortium(
            x.plan_id, x.agreement_id, x.agreement_ref, x.production_order_id, x.graph_id, x.graph_revision,
            x.effective_from, NOW + timedelta(days=9), x.assignments, x.evidence_refs,
        )
        with self.assertRaises(CooperativeMarketError):
            validate(plan=invalid)

    def test_participant_commitment_must_match_agreement(self):
        o, a, p, g, x = fixtures()
        assignments = (
            ConsortiumAssignment("org-a", "producer", frozenset({"cut"}), "forged:commit", "authority:a", "scope:a"),
            x.assignments[1],
        )
        invalid = TemporaryProductionConsortium(
            x.plan_id, x.agreement_id, x.agreement_ref, x.production_order_id, x.graph_id, x.graph_revision,
            x.effective_from, x.effective_to, assignments, x.evidence_refs,
        )
        with self.assertRaises(CooperativeMarketError):
            validate(plan=invalid)

    def test_unverified_participant_scope_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate(verified=VERIFIED - {"scope:b"})

    def test_duplicate_node_assignment_rejected(self):
        o, a, p, g, x = fixtures()
        assignments = (
            ConsortiumAssignment("org-a", "producer", frozenset({"cut", "finish"}), "commit:a", "authority:a", "scope:a"),
            x.assignments[1],
        )
        invalid = TemporaryProductionConsortium(
            x.plan_id, x.agreement_id, x.agreement_ref, x.production_order_id, x.graph_id, x.graph_revision,
            x.effective_from, x.effective_to, assignments, x.evidence_refs,
        )
        with self.assertRaises(CooperativeMarketError):
            validate(plan=invalid)

    def test_unassigned_graph_node_rejected(self):
        o, a, p, g, x = fixtures()
        assignments = (
            ConsortiumAssignment("org-a", "producer", frozenset({"cut"}), "commit:a", "authority:a", "scope:a"),
            ConsortiumAssignment("org-b", "resource_provider", frozenset(), "commit:b", "authority:b", "scope:b"),
        )
        invalid = TemporaryProductionConsortium(
            x.plan_id, x.agreement_id, x.agreement_ref, x.production_order_id, x.graph_id, x.graph_revision,
            x.effective_from, x.effective_to, assignments, x.evidence_refs,
        )
        with self.assertRaises(CooperativeMarketError):
            validate(plan=invalid)

    def test_assignment_freezes_mutable_node_set(self):
        o, a, p, g, x = fixtures()
        node_ids = {"cut"}
        assignment = ConsortiumAssignment("org-a", "producer", node_ids, "commit:a", "authority:a", "scope:a")
        node_ids.add("finish")
        self.assertEqual(assignment.node_ids, frozenset({"cut"}))

    def test_node_executor_must_match_assignment(self):
        o, a, p, g, x = fixtures()
        assignments = (
            ConsortiumAssignment("org-b", "producer", frozenset({"cut"}), "commit:b", "authority:b", "scope:b"),
            ConsortiumAssignment("org-a", "producer", frozenset({"finish"}), "commit:a", "authority:a", "scope:a"),
        )
        invalid = TemporaryProductionConsortium(
            x.plan_id, x.agreement_id, x.agreement_ref, x.production_order_id, x.graph_id, x.graph_revision,
            x.effective_from, x.effective_to, assignments, x.evidence_refs,
        )
        with self.assertRaises(CooperativeMarketError):
            validate(plan=invalid)


if __name__ == "__main__":
    unittest.main(verbosity=2)
