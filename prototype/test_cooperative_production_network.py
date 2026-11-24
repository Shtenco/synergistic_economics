"""Adversarial tests for the SYNERGY Cooperative Production Network contract."""
import unittest
from datetime import datetime, timedelta, timezone

from cellular_cooperative_market import CooperativeMarketError, EconomicOrganization
from cooperative_production_network import (
    ProductionCapability, ProductionMatchProposal, ProductionOrder,
    WorkOrderState, transition_work_order, validate_production_match,
)

NOW = datetime(2026, 11, 25, 12, tzinfo=timezone.utc)
VERIFIED = frozenset({
    "asset-authority:1", "asset-evidence:1", "mandate:1", "work-package:1", "cost:1", "schedule:1",
    "bilateral-terms:1", "quality:1", "contract-terms:1",
})


def org(identifier):
    return EconomicOrganization(identifier, "KZ", "cooperative",
                                 frozenset({"artel", "enterprise"}),
                                 f"charter:{identifier}")


def order(**changes):
    values = dict(
        order_id="order-1", requester_organization_id="buyer",
        router_demand_id="demand-1", scope="machine assembly",
        deliverable_ref="deliverable:1", required_capability_refs=frozenset({"cnc"}),
        quantity=5, unit="units", delivery_from=NOW,
        delivery_to=NOW + timedelta(days=10), quality_criteria_ref="quality:1",
        contract_terms_ref="contract-terms:1", expected_revision=2,
        idempotency_key="order:create:1",
    )
    values.update(changes)
    return ProductionOrder(**values)


def capability(**changes):
    values = dict(
        capability_id="cap-1", provider_organization_id="supplier",
        router_offer_id="offer-1", resource_ref="asset:machine-1",
        capability_refs=frozenset({"cnc", "milling"}), capacity=8, unit="units",
        available_from=NOW, available_to=NOW + timedelta(days=8),
        asset_authority_ref="asset-authority:1",
        evidence_refs=("asset-evidence:1",), production_mandate_ref="mandate:1", revision=3, status="active",
    )
    values.update(changes)
    return ProductionCapability(**values)


def proposal(**changes):
    values = dict(
        proposal_id="proposal-1", order_id="order-1",
        router_match_id="router-match:1", router_offer_id="offer-1",
        requester_organization_id="buyer", provider_organization_id="supplier",
        capability_id="cap-1", quantity=5, unit="units",
        scheduled_from=NOW + timedelta(days=1),
        scheduled_to=NOW + timedelta(days=3),
        cost_evidence_ref="cost:1", schedule_evidence_ref="schedule:1",
        expected_order_revision=2, expected_capability_revision=3,
        bilateral_terms_ref="bilateral-terms:1", provider_work_package_ref="work-package:1",
    )
    values.update(changes)
    return ProductionMatchProposal(**values)


class ProductionMatchTests(unittest.TestCase):
    def validate(self, o=None, c=None, p=None, evidence=VERIFIED, organizations=None):
        validate_production_match(
            order=o or order(), capability=c or capability(), proposal=p or proposal(),
            organizations=organizations or {"buyer": org("buyer"), "supplier": org("supplier")},
            verified_evidence_refs=evidence, at=NOW,
        )

    def test_valid_production_match_is_accepted_as_proposal(self):
        self.validate()

    def test_inactive_counterparty_rejected(self):
        inactive = org("supplier")
        inactive = EconomicOrganization(inactive.organization_id, inactive.jurisdiction,
            inactive.legal_form, inactive.coordination_roles, inactive.charter_ref, "suspended")
        with self.assertRaises(CooperativeMarketError):
            self.validate(organizations={"buyer": org("buyer"), "supplier": inactive})

    def test_missing_counterparty_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(organizations={"buyer": org("buyer")})

    def test_cross_order_or_capability_binding_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(order_id="other"))
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(capability_id="other"))

    def test_provider_and_requester_substitution_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(provider_organization_id="attacker"))
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(requester_organization_id="attacker"))

    def test_router_offer_must_match_capability(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(router_offer_id="other"))

    def test_stale_order_or_capability_revision_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(expected_order_revision=1))
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(expected_capability_revision=2))

    def test_artel_requires_mandate_and_work_package_refs(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(c=capability(production_mandate_ref=None))
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(provider_work_package_ref=None))

    def test_suspended_capability_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(c=capability(status="suspended"))

    def test_unit_quantity_and_capacity_constraints(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(unit="hours"))
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(quantity=4))
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(quantity=9), c=capability(capacity=8))

    def test_missing_capability_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(c=capability(capability_refs=frozenset({"welding"})))

    def test_schedule_must_fit_order_and_provider_window(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(scheduled_to=NOW + timedelta(days=11)))
        with self.assertRaises(CooperativeMarketError):
            self.validate(p=proposal(scheduled_to=NOW + timedelta(days=9)))

    def test_unverified_evidence_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(evidence=frozenset({"cost:1"}))

    def test_malformed_evidence_collection_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(evidence=["cost:1"])
        with self.assertRaises(CooperativeMarketError):
            self.validate(evidence=frozenset({""}))

    def test_boolean_revision_and_quantity_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            order(quantity=True)
        with self.assertRaises(CooperativeMarketError):
            proposal(expected_order_revision=True)


AUTH = {
    "workflow": frozenset({"workflow:1"}),
    "router": frozenset({"router:1"}),
    "contract": frozenset({"contract:1"}),
    "inventory": frozenset({"inventory:1"}),
    "execution": frozenset({"execution:1"}),
    "delivery": frozenset({"delivery:1"}),
    "quality": frozenset({"quality:1"}),
    "settlement": frozenset({"settlement:1"}),
    "dispute": frozenset({"dispute:1"}),
}


class WorkOrderLifecycleTests(unittest.TestCase):
    def advance(self, state, target, domain, authority=None, key=None, expected=None, refs=AUTH):
        return transition_work_order(
            state, target_status=target, actor_ref="actor:1",
            authority_ref=authority or f"{domain}:1",
            expected_revision=state.revision if expected is None else expected,
            idempotency_key=key or f"event:{state.revision + 1}",
            verified_authority_refs=refs, at=NOW,
        )

    def test_happy_path_requires_each_authority_domain(self):
        state = WorkOrderState("order-1")
        for target, domain in [
            ("published", "workflow"), ("matched", "router"),
            ("proposed", "workflow"), ("accepted", "contract"),
            ("reserved", "inventory"), ("in_progress", "execution"),
            ("delivered", "delivery"), ("verified", "quality"),
            ("settled", "settlement"),
        ]:
            state = self.advance(state, target, domain)
        self.assertEqual(state.status, "settled")
        self.assertEqual(state.revision, 9)
        self.assertEqual(len(state.events), 9)

    def test_wrong_authority_domain_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.advance(WorkOrderState("order-1"), "published", "contract")

    def test_missing_authority_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.advance(WorkOrderState("order-1"), "published", "workflow",
                         refs={"workflow": frozenset()})

    def test_unverified_authority_collection_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.advance(WorkOrderState("order-1"), "published", "workflow",
                         refs={"workflow": ["workflow:1"]})

    def test_illegal_transition_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.advance(WorkOrderState("order-1"), "settled", "settlement")

    def test_stale_revision_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.advance(WorkOrderState("order-1"), "published", "workflow", expected=1)

    def test_idempotency_replay_rejected(self):
        state = self.advance(WorkOrderState("order-1"), "published", "workflow", key="same")
        with self.assertRaises(CooperativeMarketError):
            self.advance(state, "matched", "router", key="same")

    def test_disputed_requires_resolution_authority(self):
        state = self.advance(WorkOrderState("order-1"), "published", "workflow")
        state = self.advance(state, "matched", "router")
        state = self.advance(state, "proposed", "workflow")
        state = self.advance(state, "disputed", "dispute")
        with self.assertRaises(CooperativeMarketError):
            self.advance(state, "verified", "quality", refs={"quality": frozenset()})
        state = self.advance(state, "verified", "quality")
        self.assertEqual(state.status, "verified")

    def test_terminal_settled_state_cannot_transition(self):
        state = WorkOrderState("order-1", status="settled")
        with self.assertRaises(CooperativeMarketError):
            self.advance(state, "cancelled", "workflow")


if __name__ == "__main__":
    unittest.main(verbosity=2)
