"""Tests for the strict canonical-evidence governance boundary."""

import unittest
from datetime import datetime, timedelta, timezone

from cellular_cooperative_market import (
    Ballot,
    CooperativeMarketError,
    CoordinationUnit,
    EconomicOrganization,
    GovernancePolicy,
    Participation,
)
from cellular_cooperative_evidence import (
    CanonicalEvidence,
    evaluate_governance_with_canonical_evidence,
)


NOW = datetime(2026, 11, 24, 16, 0, tzinfo=timezone.utc)
CELL = CoordinationUnit("cell-1", "dao_cell", "charter:cell-1")
POLICY = GovernancePolicy(
    "policy-1", "cell-1", "coordination_unit",
    frozenset({"local_operations"}),
    frozenset({"approve_schedule"}),
    "one_member_one_vote", 5000, 5000, "policy:cell:ops",
)


def member(subject="alice", *, capacity="member", represented=None, authority=None):
    return Participation(
        participation_id=f"participation:{subject}",
        subject_id=subject,
        host_id="cell-1",
        host_kind="coordination_unit",
        capacity=capacity,
        consent_ref=f"consent:{subject}",
        rights_ref=f"rights:{subject}",
        effective_from=NOW - timedelta(days=2),
        represented_organization_id=represented,
        delegation_authority_ref=authority,
    )


def evidence(ref, kind, subject, resource, scope, **overrides):
    values = dict(
        evidence_ref=ref,
        evidence_kind=kind,
        subject_id=subject,
        resource_id=resource,
        scope=scope,
        issuer_ref="canonical-authority:1",
        source_snapshot_ref="authority-snapshot:2026-11-24T15:00Z",
        payload_sha256="a" * 64,
        verified_at=NOW - timedelta(hours=1),
        valid_from=NOW - timedelta(days=1),
    )
    values.update(overrides)
    return CanonicalEvidence(**values)


def evidence_set(participations, ballots, policy=POLICY):
    result = {
        policy.policy_ref: evidence(
            policy.policy_ref, "governance_policy",
            policy.governing_subject_id, policy.governing_subject_id,
            "local_operations:approve_schedule",
        )
    }
    for p in participations:
        result[p.consent_ref] = evidence(
            p.consent_ref, "participation_consent", p.subject_id,
            p.host_id, p.capacity,
        )
        result[p.rights_ref] = evidence(
            p.rights_ref, "participation_rights", p.subject_id,
            p.host_id, p.capacity,
        )
        if p.capacity == "organization_delegate":
            result[p.delegation_authority_ref] = evidence(
                p.delegation_authority_ref, "delegation_authority",
                p.represented_organization_id, p.host_id,
                "local_operations:approve_schedule",
            )
    for b in ballots:
        result[b.evidence_ref] = evidence(
            b.evidence_ref, "governance_ballot", b.voter_id,
            policy.governing_subject_id,
            "local_operations:approve_schedule",
        )
    return result


class CanonicalEvidenceGovernanceTests(unittest.TestCase):
    def evaluate(self, participations, ballots, records, *, policy=POLICY, organizations=None):
        return evaluate_governance_with_canonical_evidence(
            policy=policy,
            decision_domain="local_operations",
            action="approve_schedule",
            participations=participations,
            ballots=ballots,
            organizations=organizations or {},
            coordination_units={"cell-1": CELL},
            at=NOW,
            verified_evidence=records,
        )

    def test_valid_vote_requires_and_accepts_all_canonical_evidence(self):
        people = [member("alice"), member("bob"), member("carol")]
        ballots = [Ballot("alice", "approve", "ballot:alice"),
                   Ballot("bob", "approve", "ballot:bob")]
        result = self.evaluate(people, ballots, evidence_set(people, ballots))
        self.assertTrue(result.approved)
        self.assertEqual(result.eligible_count, 3)
        self.assertEqual(result.participating_count, 2)

    def test_missing_participation_consent_fails_closed(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        del records["consent:alice"]
        with self.assertRaisesRegex(CooperativeMarketError, "missing canonical evidence"):
            self.evaluate(people, ballots, records)

    def test_consent_for_another_subject_is_rejected(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        records["consent:alice"] = evidence(
            "consent:alice", "participation_consent", "mallory",
            "cell-1", "member",
        )
        with self.assertRaisesRegex(CooperativeMarketError, "subject mismatch"):
            self.evaluate(people, ballots, records)

    def test_rights_for_another_host_are_rejected(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        records["rights:alice"] = evidence(
            "rights:alice", "participation_rights", "alice",
            "other-cell", "member",
        )
        with self.assertRaisesRegex(CooperativeMarketError, "resource mismatch"):
            self.evaluate(people, ballots, records)

    def test_expired_participation_rights_are_rejected(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        records["rights:alice"] = evidence(
            "rights:alice", "participation_rights", "alice", "cell-1", "member",
            valid_until=NOW - timedelta(seconds=1),
        )
        with self.assertRaisesRegex(CooperativeMarketError, "expired"):
            self.evaluate(people, ballots, records)

    def test_revoked_participation_consent_is_rejected(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        records["consent:alice"] = evidence(
            "consent:alice", "participation_consent", "alice", "cell-1", "member",
            revoked_at=NOW - timedelta(seconds=1),
        )
        with self.assertRaisesRegex(CooperativeMarketError, "revoked"):
            self.evaluate(people, ballots, records)

    def test_missing_ballot_evidence_fails_closed(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        del records["ballot:alice"]
        with self.assertRaisesRegex(CooperativeMarketError, "missing canonical evidence"):
            self.evaluate(people, ballots, records)

    def test_ballot_evidence_must_bind_exact_decision_scope(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        records["ballot:alice"] = evidence(
            "ballot:alice", "governance_ballot", "alice",
            "cell-1", "shared_services:approve_schedule",
        )
        with self.assertRaisesRegex(CooperativeMarketError, "scope mismatch"):
            self.evaluate(people, ballots, records)

    def test_ballot_evidence_reference_cannot_be_reused(self):
        people = [member("alice"), member("bob")]
        ballots = [Ballot("alice", "approve", "ballot:shared"),
                   Ballot("bob", "reject", "ballot:shared")]
        records = evidence_set(people, [ballots[0]])
        with self.assertRaisesRegex(CooperativeMarketError, "cannot be reused"):
            self.evaluate(people, ballots, records)

    def test_delegation_requires_canonical_authority_for_exact_org_and_scope(self):
        policy = GovernancePolicy(
            "policy-org", "cell-1", "coordination_unit",
            frozenset({"local_operations"}), frozenset({"approve_schedule"}),
            "one_organization_one_vote", 5000, 5000, "policy:cell:ops",
        )
        artel = EconomicOrganization(
            "artel-1", "KZ", "production_cooperative",
            frozenset({"artel"}), "charter:artel-1",
        )
        delegate = member(
            "delegate-person", capacity="organization_delegate",
            represented="artel-1", authority="authority:artel-1",
        )
        ballot = Ballot("artel-1", "approve", "ballot:artel")
        records = evidence_set([delegate], [ballot], policy)
        records["authority:artel-1"] = evidence(
            "authority:artel-1", "delegation_authority",
            "someone-else", "cell-1", "local_operations:approve_schedule",
        )
        with self.assertRaisesRegex(CooperativeMarketError, "subject mismatch"):
            self.evaluate([delegate], [ballot], records, policy=policy,
                          organizations={"artel-1": artel})

    def test_valid_delegation_and_organization_ballot_are_accepted(self):
        policy = GovernancePolicy(
            "policy-org", "cell-1", "coordination_unit",
            frozenset({"local_operations"}), frozenset({"approve_schedule"}),
            "one_organization_one_vote", 5000, 5000, "policy:cell:ops",
        )
        artel = EconomicOrganization(
            "artel-1", "KZ", "production_cooperative",
            frozenset({"artel"}), "charter:artel-1",
        )
        delegate = member(
            "delegate-person", capacity="organization_delegate",
            represented="artel-1", authority="authority:artel-1",
        )
        ballot = Ballot("artel-1", "approve", "ballot:artel")
        records = evidence_set([delegate], [ballot], policy)
        result = self.evaluate([delegate], [ballot], records, policy=policy,
                               organizations={"artel-1": artel})
        self.assertTrue(result.approved)
        self.assertEqual(result.eligible_count, 1)

    def test_policy_evidence_must_bind_exact_domain_and_action(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        records[POLICY.policy_ref] = evidence(
            POLICY.policy_ref, "governance_policy", "cell-1",
            "cell-1", "external_finance:release_payment",
        )
        with self.assertRaisesRegex(CooperativeMarketError, "scope mismatch"):
            self.evaluate(people, ballots, records)

    def test_future_verified_evidence_is_rejected(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        records["ballot:alice"] = evidence(
            "ballot:alice", "governance_ballot", "alice", "cell-1",
            "local_operations:approve_schedule",
            verified_at=NOW + timedelta(seconds=1),
        )
        with self.assertRaisesRegex(CooperativeMarketError, "verified after"):
            self.evaluate(people, ballots, records)

    def test_malformed_evidence_digest_is_rejected_at_construction(self):
        with self.assertRaisesRegex(CooperativeMarketError, "64 lowercase hexadecimal"):
            evidence("bad", "governance_ballot", "alice", "cell-1", "scope",
                     payload_sha256="not-a-digest")

    def test_evidence_mapping_key_must_match_record_reference(self):
        people = [member()]
        ballots = [Ballot("alice", "approve", "ballot:alice")]
        records = evidence_set(people, ballots)
        records["substituted-key"] = records.pop("ballot:alice")
        with self.assertRaisesRegex(CooperativeMarketError, "map key"):
            self.evaluate(people, ballots, records)


if __name__ == "__main__":
    unittest.main()
