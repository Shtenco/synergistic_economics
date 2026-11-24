"""Adversarial tests for the read-only SYNERGY Artel Engine contract."""
import unittest
from datetime import datetime, timedelta, timezone

from cellular_cooperative_market import CooperativeMarketError, EconomicOrganization
from artel_engine import ArtelProductionMandate, ArtelWorkPackage, validate_artel_work_package

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
VERIFIED = frozenset({
    "constitution:1", "authority:1", "budget:1", "project:1",
    "deliverable:1", "labour:1", "asset-use:1", "ip:1",
})


def make_org(*roles, status="active"):
    return EconomicOrganization(
        organization_id="artel-1",
        jurisdiction="KZ",
        legal_form="production_cooperative",
        coordination_roles=frozenset(roles),
        charter_ref="constitution:1",
        status=status,
    )


def make_mandate(**overrides):
    values = dict(
        mandate_id="mandate-1",
        artel_organization_id="artel-1",
        constitution_ref="constitution:1",
        scope="precision-machinery",
        allowed_work_scopes=frozenset({"machining", "assembly"}),
        authority_ref="authority:1",
        budget_authority_ref="budget:1",
        budget_limit_minor=1_000_000,
        budget_currency="KZT",
        effective_from=NOW - timedelta(days=1),
        effective_to=NOW + timedelta(days=30),
    )
    values.update(overrides)
    return ArtelProductionMandate(**values)


def make_package(**overrides):
    values = dict(
        work_package_id="wp-1",
        artel_organization_id="artel-1",
        mandate_id="mandate-1",
        project_ref="project:1",
        scope="machining",
        deliverable_ref="deliverable:1",
        budget_minor=500_000,
        currency="KZT",
        budget_authority_ref="budget:1",
        effective_from=NOW,
        effective_to=NOW + timedelta(days=7),
        evidence_refs=("labour:1", "asset-use:1", "ip:1"),
        expected_revision=0,
        idempotency_key="tenant-a:wp-1:v1",
    )
    values.update(overrides)
    return ArtelWorkPackage(**values)


class ArtelMandateValidationTests(unittest.TestCase):
    def test_valid_artel_work_package_is_accepted_as_proposal(self):
        validate_artel_work_package(
            work_package=make_package(),
            mandate=make_mandate(),
            organizations={"artel-1": make_org("artel")},
            verified_evidence_refs=VERIFIED,
            at=NOW,
        )

    def test_non_artel_organization_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(), mandate=make_mandate(),
                organizations={"artel-1": make_org("enterprise")},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_inactive_artel_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(), mandate=make_mandate(),
                organizations={"artel-1": make_org("artel", status="suspended")},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_cross_artel_mandate_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(artel_organization_id="artel-2"),
                mandate=make_mandate(),
                organizations={"artel-2": EconomicOrganization(
                    "artel-2", "KZ", "cooperative", frozenset({"artel"}),
                    "constitution:2"
                )},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_inactive_mandate_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(),
                mandate=make_mandate(status="suspended"),
                organizations={"artel-1": make_org("artel")},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_scope_outside_mandate_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(scope="unrelated"),
                mandate=make_mandate(),
                organizations={"artel-1": make_org("artel")},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_budget_overrun_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(budget_minor=1_000_001),
                mandate=make_mandate(),
                organizations={"artel-1": make_org("artel")},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_currency_mismatch_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(currency="USD"),
                mandate=make_mandate(),
                organizations={"artel-1": make_org("artel")},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_work_package_outside_mandate_dates_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(effective_to=NOW + timedelta(days=31)),
                mandate=make_mandate(),
                organizations={"artel-1": make_org("artel")},
                verified_evidence_refs=VERIFIED, at=NOW,
            )

    def test_unverified_canonical_reference_fails_closed(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(),
                mandate=make_mandate(),
                organizations={"artel-1": make_org("artel")},
                verified_evidence_refs=frozenset({"constitution:1"}),
                at=NOW,
            )

    def test_budget_authority_cannot_be_swapped(self):
        with self.assertRaises(CooperativeMarketError):
            validate_artel_work_package(
                work_package=make_package(budget_authority_ref="budget:other"),
                mandate=make_mandate(),
                organizations={"artel-1": make_org("artel")},
                verified_evidence_refs=VERIFIED | {"budget:other"}, at=NOW,
            )

    def test_bool_is_not_accepted_as_budget_or_revision_integer(self):
        with self.assertRaises(CooperativeMarketError):
            make_package(budget_minor=True)
        with self.assertRaises(CooperativeMarketError):
            make_package(expected_revision=True)


class ArtelParticipationValidationTests(unittest.TestCase):
    def make_participation(self, **overrides):
        from cellular_cooperative_market import Participation
        values = dict(
            participation_id="part-1",
            subject_id="person-1",
            host_id="artel-1",
            host_kind="organization",
            capacity="member",
            consent_ref="consent:1",
            rights_ref="rights:1",
            effective_from=NOW - timedelta(days=1),
            effective_to=NOW + timedelta(days=30),
            status="active",
        )
        values.update(overrides)
        return Participation(**values)

    def validate(self, participation=None, existing=(), orgs=None, evidence=None):
        from artel_engine import validate_artel_participation
        validate_artel_participation(
            participation=participation or self.make_participation(),
            existing_participations=existing,
            organizations=orgs or {"artel-1": make_org("artel")},
            verified_evidence_refs=evidence or frozenset({
                "consent:1", "rights:1", "constitution:1"
            }),
            at=NOW,
        )

    def test_valid_voluntary_membership_is_accepted(self):
        self.validate()

    def test_non_artel_host_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(orgs={"artel-1": make_org("enterprise")})

    def test_inactive_artel_host_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(orgs={"artel-1": make_org("artel", status="suspended")})

    def test_unverified_consent_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(evidence=frozenset({"rights:1", "constitution:1"}))

    def test_unverified_rights_terms_are_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(evidence=frozenset({"consent:1", "constitution:1"}))

    def test_inactive_or_expired_participation_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(participation=self.make_participation(status="exited"))

    def test_unknown_capacity_is_rejected(self):
        with self.assertRaises(CooperativeMarketError):
            self.validate(participation=self.make_participation(capacity="owner_by_score"))

    def test_member_and_worker_are_distinct_capacities(self):
        self.validate(participation=self.make_participation(capacity="worker"))

    def test_duplicate_active_membership_is_rejected(self):
        existing = self.make_participation(participation_id="part-old")
        with self.assertRaises(CooperativeMarketError):
            self.validate(existing=(existing,))

    def test_same_person_can_hold_different_participation_capacities(self):
        existing = self.make_participation(participation_id="part-worker", capacity="worker")
        self.validate(existing=(existing,))

    def test_same_person_can_participate_in_another_artel(self):
        from cellular_cooperative_market import Participation
        other = Participation(
            participation_id="part-other", subject_id="person-1",
            host_id="artel-2", host_kind="organization", capacity="member",
            consent_ref="consent:other", rights_ref="rights:other",
            effective_from=NOW - timedelta(days=1),
        )
        self.validate(existing=(other,))

    def test_participation_id_collision_is_rejected(self):
        existing = self.make_participation()
        with self.assertRaises(CooperativeMarketError):
            self.validate(existing=(existing,))



if __name__ == "__main__":
    unittest.main()
