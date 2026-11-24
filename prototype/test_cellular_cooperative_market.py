import unittest
from datetime import datetime, timedelta, timezone

from cellular_cooperative_market import (
    Ballot,
    CooperativeMarketError,
    CooperationAgreement,
    ConsortiumParticipant,
    DistributionShare,
    EconomicOrganization,
    GovernancePolicy,
    MarketMatchReference,
    OrganizationRelation,
    Participation,
    RecipientWeight,
    VerifiedResidualPool,
    evaluate_governance,
    propose_distribution,
    validate_agreement,
    validate_market_match,
    validate_network,
)


NOW = datetime(2026, 11, 24, 12, 0, tzinfo=timezone.utc)


def org(org_id, *roles, legal_form="company", status="active"):
    return EconomicOrganization(
        organization_id=org_id,
        jurisdiction="KZ",
        legal_form=legal_form,
        coordination_roles=frozenset(roles),
        charter_ref=f"charter:{org_id}",
        status=status,
    )


def member(pid, org_id, capacity="member", status="active"):
    return Participation(
        participation_id=f"p:{pid}:{org_id}",
        subject_id=pid,
        organization_id=org_id,
        capacity=capacity,
        consent_ref=f"consent:{pid}:{org_id}",
        rights_ref=f"rights:{pid}:{org_id}",
        effective_from=NOW - timedelta(days=1),
        status=status,
    )


class OrganizationOntologyTests(unittest.TestCase):
    def test_legal_form_and_coordination_roles_are_orthogonal(self):
        cooperative = org("coop-1", "artel", "dao_cell", legal_form="kz_production_cooperative")
        self.assertEqual(cooperative.legal_form, "kz_production_cooperative")
        self.assertEqual(cooperative.coordination_roles, frozenset({"artel", "dao_cell"}))

    def test_participation_can_overlap_across_organizations(self):
        p1 = member("person-1", "cell-1")
        p2 = member("person-1", "artel-1")
        self.assertTrue(p1.active_at(NOW))
        self.assertTrue(p2.active_at(NOW))
        self.assertNotEqual(p1.organization_id, p2.organization_id)

    def test_invalid_relation_reference_is_rejected(self):
        organizations = {"a": org("a", "enterprise"), "b": org("b", "artel")}
        relation = OrganizationRelation(
            "r1", "a", "missing", "collaborates_with", "pilot",
            "agreement:1", NOW,
        )
        with self.assertRaises(CooperativeMarketError):
            validate_network(organizations, [relation])

    def test_duplicate_relation_id_is_rejected(self):
        organizations = {"a": org("a", "enterprise"), "b": org("b", "artel")}
        relation = OrganizationRelation(
            "r1", "a", "b", "collaborates_with", "pilot",
            "agreement:1", NOW,
        )
        with self.assertRaises(CooperativeMarketError):
            validate_network(organizations, [relation, relation])


class GovernanceTests(unittest.TestCase):
    def setUp(self):
        self.organization = org("cell-1", "dao_cell")
        self.organizations = {"cell-1": self.organization}
        self.policy = GovernancePolicy(
            policy_id="policy-1",
            organization_id="cell-1",
            allowed_domains=frozenset({"local_operations", "shared_services"}),
            voting_rule="one_member_one_vote",
            quorum_bps=6000,
            approval_bps=5000,
            policy_ref="policy:evidence:1",
        )
        self.members = [
            member("alice", "cell-1"),
            member("bob", "cell-1"),
            member("carol", "cell-1"),
        ]

    def test_valid_vote_is_evaluated_without_execution(self):
        result = evaluate_governance(
            policy=self.policy,
            decision_domain="local_operations",
            action="approve_weekly_schedule",
            participations=self.members,
            ballots=[
                Ballot("alice", "approve", "ballot:a"),
                Ballot("bob", "approve", "ballot:b"),
            ],
            organizations=self.organizations,
            at=NOW,
        )
        self.assertTrue(result.approved)
        self.assertEqual(result.eligible_count, 3)
        self.assertEqual(result.participating_count, 2)
        self.assertEqual(result.approval_bps, 10000)

    def test_quorum_failure_is_not_approved(self):
        result = evaluate_governance(
            policy=self.policy,
            decision_domain="local_operations",
            action="approve_schedule",
            participations=self.members,
            ballots=[Ballot("alice", "approve", "ballot:a")],
            organizations=self.organizations,
            at=NOW,
        )
        self.assertFalse(result.approved)
        self.assertFalse(result.quorum_met)

    def test_out_of_mandate_domain_fails_closed(self):
        with self.assertRaises(CooperativeMarketError):
            evaluate_governance(
                policy=self.policy,
                decision_domain="external_finance",
                action="approve_loan",
                participations=self.members,
                ballots=[],
                organizations=self.organizations,
                at=NOW,
            )

    def test_protected_action_cannot_be_approved_by_generic_vote(self):
        with self.assertRaises(CooperativeMarketError):
            evaluate_governance(
                policy=self.policy,
                decision_domain="local_operations",
                action="transfer_legal_title",
                participations=self.members,
                ballots=[Ballot("alice", "approve", "ballot:a")],
                organizations=self.organizations,
                at=NOW,
            )

    def test_duplicate_ballot_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            evaluate_governance(
                policy=self.policy,
                decision_domain="local_operations",
                action="approve_schedule",
                participations=self.members,
                ballots=[
                    Ballot("alice", "approve", "ballot:a"),
                    Ballot("alice", "reject", "ballot:b"),
                ],
                organizations=self.organizations,
                at=NOW,
            )

    def test_organization_delegate_rule_uses_delegate_subjects(self):
        policy = GovernancePolicy(
            "policy-org", "cell-1", frozenset({"federation_budget"}),
            "one_organization_one_vote", 5000, 5000, "policy:org",
        )
        delegates = [
            member("artel-a", "cell-1", capacity="organization_delegate"),
            member("artel-b", "cell-1", capacity="organization_delegate"),
        ]
        result = evaluate_governance(
            policy=policy,
            decision_domain="federation_budget",
            action="approve_shared_budget",
            participations=delegates,
            ballots=[
                Ballot("artel-a", "approve", "ballot:a"),
                Ballot("artel-b", "reject", "ballot:b"),
            ],
            organizations=self.organizations,
            at=NOW,
        )
        self.assertFalse(result.approved)
        self.assertEqual(result.eligible_count, 2)
        self.assertEqual(result.approval_bps, 5000)


class ConsortiumTests(unittest.TestCase):
    def test_agreement_requires_two_active_independent_participants(self):
        organizations = {
            "artel": org("artel", "artel", legal_form="production_cooperative"),
            "firm": org("firm", "enterprise"),
        }
        agreement = CooperationAgreement(
            "consortium-project-1", "industrial equipment", "deliverable-1",
            "KZ", (
                ConsortiumParticipant("artel", "commitment:artel", "authority:artel"),
                ConsortiumParticipant("firm", "commitment:firm", "authority:firm"),
            ), "agreement:project-1", NOW,
        )
        validate_agreement(agreement, organizations)

    def test_inactive_participant_blocks_agreement(self):
        organizations = {
            "artel": org("artel", "artel"),
            "firm": org("firm", "enterprise", status="suspended"),
        }
        agreement = CooperationAgreement(
            "project-2", "production", "scope", "KZ", (
                ConsortiumParticipant("artel", "commitment:a", "authority:a"),
                ConsortiumParticipant("firm", "commitment:f", "authority:f"),
            ), "agreement:2", NOW,
        )
        with self.assertRaises(CooperativeMarketError):
            validate_agreement(agreement, organizations)


class DistributionTests(unittest.TestCase):
    def setUp(self):
        self.pool = VerifiedResidualPool(
            "residual-1", 10001, "KZT", "financial-authority:event-91", True
        )

    def test_hybrid_pool_is_exact_and_remainder_is_retained(self):
        shares = [
            DistributionShare(
                "residual-1", 5000, "equal_membership",
                (
                    RecipientWeight("alice", 1, "membership:a"),
                    RecipientWeight("bob", 1, "membership:b"),
                    RecipientWeight("carol", 1, "membership:c"),
                ),
                "constitution:v1",
            ),
            DistributionShare(
                "residual-1", 4000, "project_contribution",
                (
                    RecipientWeight("team-a", 3, "sci:evidence:a"),
                    RecipientWeight("team-b", 1, "sci:evidence:b"),
                ),
                "constitution:v1",
            ),
        ]
        proposal = propose_distribution(self.pool, shares)
        self.assertEqual(proposal.allocated_minor, 9000)
        self.assertEqual(proposal.retained_minor, 1001)
        self.assertEqual(sum(x.amount_minor for x in proposal.allocations), 9000)
        self.assertEqual(proposal.currency, "KZT")

    def test_equal_pool_uses_deterministic_largest_remainder(self):
        share = DistributionShare(
            "residual-1", 5000, "equal_membership",
            (
                RecipientWeight("alice", 1, "membership:a"),
                RecipientWeight("bob", 1, "membership:b"),
                RecipientWeight("carol", 1, "membership:c"),
            ),
            "constitution:v1",
        )
        proposal = propose_distribution(self.pool, [share])
        amounts = {x.recipient_id: x.amount_minor for x in proposal.allocations}
        self.assertEqual(amounts, {"alice": 1667, "bob": 1667, "carol": 1666})

    def test_unverified_pool_is_rejected(self):
        pool = VerifiedResidualPool(
            "residual-1", 1000, "KZT", "unverified", False
        )
        with self.assertRaises(CooperativeMarketError):
            propose_distribution(pool, [])

    def test_overallocated_distribution_is_rejected(self):
        shares = [
            DistributionShare("residual-1", 7000, "equal_membership",
                              (RecipientWeight("alice", 1, "member:a"),), "policy"),
            DistributionShare("residual-1", 4000, "verified_usage",
                              (RecipientWeight("bob", 1, "usage:b"),), "policy"),
        ]
        with self.assertRaises(CooperativeMarketError):
            propose_distribution(self.pool, shares)

    def test_duplicate_recipient_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            DistributionShare(
                "residual-1", 10000, "equal_membership",
                (
                    RecipientWeight("alice", 1, "membership:a"),
                    RecipientWeight("alice", 1, "membership:a2"),
                ),
                "constitution:v1",
            )


class MarketReferenceTests(unittest.TestCase):
    def test_router_match_reference_requires_active_counterparties(self):
        organizations = {
            "buyer": org("buyer", "enterprise"),
            "seller": org("seller", "artel"),
        }
        match = MarketMatchReference(
            "demand-1", "offer-1", "candidate-1", "buyer", "seller",
            "bilateral-consent:evidence", "router-policy:v1",
        )
        validate_market_match(match, organizations)

    def test_market_match_does_not_accept_unknown_counterparty(self):
        organizations = {"buyer": org("buyer", "enterprise")}
        match = MarketMatchReference(
            "demand-1", "offer-1", "candidate-1", "buyer", "missing",
            "bilateral-consent:evidence", "router-policy:v1",
        )
        with self.assertRaises(CooperativeMarketError):
            validate_market_match(match, organizations)


if __name__ == "__main__":
    unittest.main()
