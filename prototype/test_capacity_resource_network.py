"""Adversarial tests for Capacity & Resource Network validation."""
import unittest
from datetime import datetime, timedelta, timezone

from cellular_cooperative_market import CooperativeMarketError
from cellular_cooperative_market import EconomicOrganization
from capacity_resource_network import (
    CapacitySnapshot, ResourceClaim, validate_resource_bundle,
    validate_production_graph_resources,
)
from production_graph_engine import ProductionGraph, ProductionGraphNode

NOW = datetime(2026, 11, 25, 5, 0, tzinfo=timezone.utc)
VERIFIED = frozenset({"asset-authority:1", "capacity-evidence:1", "capacity-evidence:2",
                    "resource:req-a", "resource:req-b", "accept:a", "scope:a", "accept:b", "scope:b"})


def snapshot(*, capacity=10, revision=3, observed=NOW, status="active", unit="machine-hour",
             available_from=NOW, available_to=NOW + timedelta(hours=8),
             capabilities=frozenset({"milling", "precision"}), evidence=frozenset({"capacity-evidence:1"})):
    return CapacitySnapshot(
        "asset:cnc-01", "factory-1", capabilities, capacity, unit,
        available_from, available_to, observed, revision, "asset-authority:1", evidence, status,
    )


def claim(identifier, *, quantity=4, start=NOW + timedelta(hours=1),
          end=NOW + timedelta(hours=3), revision=3, unit="machine-hour",
          capabilities=frozenset({"milling"})):
    return ResourceClaim(identifier, "asset:cnc-01", capabilities, quantity,
                         unit, start, end, revision)


def validate(claims, snap=None, verified=VERIFIED, at=NOW, age=timedelta(minutes=15), organizations=None):
    return validate_resource_bundle(
        tuple(claims), snapshots={"asset:cnc-01": snap or snapshot()},
        organizations=({"factory-1": EconomicOrganization("factory-1", "KZ", "cooperative", frozenset({"enterprise"}), "charter:factory-1", "active")} if organizations is None else organizations),
        verified_evidence_refs=verified, at=at, max_snapshot_age=age,
    )


class CapacityResourceNetworkTests(unittest.TestCase):
    def test_valid_single_claim(self):
        result = validate([claim("c1")])
        self.assertEqual(result.peak_quantities, (("asset:cnc-01", 4, "machine-hour"),))
        self.assertEqual(result.snapshot_revisions, (("asset:cnc-01", 3),))

    def test_overlapping_claims_are_aggregated(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1", quantity=6), claim("c2", quantity=5)])

    def test_non_overlapping_claims_do_not_consume_same_peak(self):
        result = validate([
            claim("c1", quantity=8, start=NOW + timedelta(hours=1), end=NOW + timedelta(hours=2)),
            claim("c2", quantity=8, start=NOW + timedelta(hours=2), end=NOW + timedelta(hours=3)),
        ])
        self.assertEqual(result.peak_quantities[0][1], 8)

    def test_half_open_boundary_releases_before_new_claim(self):
        result = validate([
            claim("c1", quantity=10, start=NOW + timedelta(hours=1), end=NOW + timedelta(hours=2)),
            claim("c2", quantity=10, start=NOW + timedelta(hours=2), end=NOW + timedelta(hours=3)),
        ])
        self.assertEqual(result.peak_quantities[0][1], 10)

    def test_stale_revision_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1", revision=2)])

    def test_stale_snapshot_rejected(self):
        old = NOW - timedelta(minutes=16)
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1")], snapshot(observed=old))

    def test_future_snapshot_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1")], snapshot(observed=NOW + timedelta(seconds=1)))

    def test_inactive_snapshot_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1")], snapshot(status="suspended"))

    def test_inactive_provider_rejected(self):
        inactive = EconomicOrganization("factory-1", "KZ", "cooperative", frozenset({"enterprise"}), "charter:factory-1", "suspended")
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1")], organizations={"factory-1": inactive})

    def test_missing_provider_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1")], organizations={})

    def test_unverified_authority_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1")], verified=frozenset({"capacity-evidence:1"}))

    def test_unverified_snapshot_evidence_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1")], snapshot(evidence=frozenset({"capacity-evidence:untrusted"})))

    def test_unit_mismatch_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1", unit="kilogram")])

    def test_capability_mismatch_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1", capabilities=frozenset({"welding"}))])

    def test_outside_availability_window_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1", end=NOW + timedelta(hours=9))])

    def test_past_claim_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("c1", start=NOW - timedelta(minutes=1))])

    def test_duplicate_claim_id_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([claim("same"), claim("same")])

    def test_empty_bundle_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate([])

    def test_bool_quantity_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            claim("c1", quantity=True)

    def test_naive_timestamp_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            claim("c1", start=datetime(2026, 11, 25, 6, 0))

    def test_bool_revision_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            claim("c1", revision=True)

    def test_snapshot_freezes_mutable_capability_and_evidence_sets(self):
        capabilities = {"milling"}
        evidence = {"capacity-evidence:1"}
        value = snapshot(capabilities=capabilities, evidence=evidence)
        capabilities.add("forged")
        evidence.add("forged:evidence")
        self.assertEqual(value.capability_refs, frozenset({"milling"}))
        self.assertEqual(value.evidence_refs, frozenset({"capacity-evidence:1"}))

    def test_claim_freezes_mutable_capability_set(self):
        capabilities = {"milling"}
        value = claim("c1", capabilities=capabilities)
        capabilities.add("forged")
        self.assertEqual(value.required_capability_refs, frozenset({"milling"}))

    def test_invalid_claim_object_rejected_cleanly(self):
        with self.assertRaises(CooperativeMarketError):
            validate([object()])

    def test_invalid_snapshot_status_type_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            snapshot(status=[])
 
    def test_graph_resource_binding_aggregates_across_nodes(self):
        graph = ProductionGraph(
            "graph-r", 1,
            (
                ProductionGraphNode("a", "factory-1", frozenset({"raw:a"}), frozenset({"out:a"}),
                                    frozenset(), "accept:a", "scope:a", resource_requirement_ref="resource:req-a"),
                ProductionGraphNode("b", "factory-1", frozenset({"raw:b"}), frozenset({"out:b"}),
                                    frozenset(), "accept:b", "scope:b", resource_requirement_ref="resource:req-b"),
            ),
            frozenset({"raw:a", "raw:b"}), frozenset(),
        )
        claims = {
            "resource:req-a": (claim("node-a", quantity=6),),
            "resource:req-b": (claim("node-b", quantity=5),),
        }
        with self.assertRaises(CooperativeMarketError):
            validate_production_graph_resources(
                graph, claims_by_requirement=claims,
                snapshots={"asset:cnc-01": snapshot()}, organizations={
                    "factory-1": EconomicOrganization("factory-1", "KZ", "cooperative",
                        frozenset({"enterprise"}), "charter:factory-1", "active")
                }, verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_graph_resource_binding_valid_single_requirement(self):
        graph = ProductionGraph(
            "graph-r", 1,
            (ProductionGraphNode("a", "factory-1", frozenset({"raw"}), frozenset({"out"}),
                                 frozenset(), "accept:a", "scope:a", resource_requirement_ref="resource:req-a"),),
            frozenset({"raw"}), frozenset(),
        )
        result = validate_production_graph_resources(
            graph, claims_by_requirement={"resource:req-a": (claim("node-a", quantity=4),)},
            snapshots={"asset:cnc-01": snapshot()},
            organizations={"factory-1": EconomicOrganization("factory-1", "KZ", "cooperative",
                frozenset({"enterprise"}), "charter:factory-1", "active")},
            verified_evidence_refs=VERIFIED, at=NOW,
        )
        self.assertEqual(result.graph_id, "graph-r")
        self.assertEqual(result.requirement_count, 1)
        self.assertEqual(result.resource_validation.claim_count, 1)

    def test_graph_resource_binding_requires_exact_requirement_keys(self):
        graph = ProductionGraph(
            "graph-r", 1,
            (ProductionGraphNode("a", "factory-1", frozenset({"raw"}), frozenset({"out"}),
                                 frozenset(), "accept:a", "scope:a", resource_requirement_ref="resource:req-a"),),
            frozenset({"raw"}), frozenset(),
        )
        with self.assertRaises(CooperativeMarketError):
            validate_production_graph_resources(
                graph, claims_by_requirement={}, snapshots={"asset:cnc-01": snapshot()},
                organizations={"factory-1": EconomicOrganization("factory-1", "KZ", "cooperative",
                    frozenset({"enterprise"}), "charter:factory-1", "active")},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

if __name__ == "__main__":
    unittest.main(verbosity=2)
