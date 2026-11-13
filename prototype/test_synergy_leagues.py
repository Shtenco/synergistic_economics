import unittest
from decimal import Decimal

from synergy_leagues import (
    League, LeagueError, LeagueMembership, ParticipantProfile, PayoutShare,
    SkillEvidence, WorkOrder, WorkStatus,
)


def profile(participant_id="worker-1", skills=("ai_automation", "python")):
    return ParticipantProfile(
        participant_id=participant_id,
        display_name="Worker",
        skill_evidence=tuple(
            SkillEvidence(skill, f"evidence:{skill}", "issuer:test", "2026-11-13T10:00:00Z")
            for skill in skills
        ),
    )


def order():
    return WorkOrder(
        order_id="order-1",
        buyer_id="buyer-1",
        title="Automate invoice processing",
        description="Build and document an invoice workflow.",
        required_skills=("python", "ai_automation"),
        budget=Decimal("1000.00"),
        currency="KZT",
        created_at="2026-11-13T09:00:00Z",
        deadline="2026-11-20T09:00:00Z",
    )


class LeagueContractTests(unittest.TestCase):
    def test_membership_requires_evidence_and_is_not_a_paid_tier(self):
        membership = LeagueMembership(
            "membership-1", "worker-1", League.EXPERT,
            "2026-11-13T10:00:00Z", ("portfolio:project-7",),
        )
        self.assertEqual(membership.league, League.EXPERT)
        with self.assertRaises(LeagueError):
            LeagueMembership("m2", "worker-1", League.EXPERT, "2026-11-13T10:00:00Z", ())

    def test_work_order_happy_path_and_exact_split(self):
        current = order().apply(profile(), expected_version=1)
        self.assertEqual(current.version, 2)
        current = current.assign(
            "worker-1", expected_version=2,
            payout_shares=(PayoutShare("worker-1", 7000), PayoutShare("partner-2", 3000)),
        )
        self.assertEqual(current.status, WorkStatus.ASSIGNED)
        current = current.submit("worker-1", ("delivery:sha256:abc",), expected_version=3)
        current = current.accept("buyer-1", expected_version=4)
        self.assertTrue(current.settlement_ready)
        amounts = current.settlement_amounts()
        self.assertEqual(amounts, {"partner-2": Decimal("300.00"), "worker-1": Decimal("700.00")})
        self.assertEqual(sum(amounts.values()), current.budget)

    def test_unverified_skill_cannot_apply(self):
        with self.assertRaisesRegex(LeagueError, "missing verified skills"):
            order().apply(profile(skills=("python",)), expected_version=1)

    def test_duplicate_application_and_stale_version_rejected(self):
        current = order().apply(profile(), expected_version=1)
        with self.assertRaisesRegex(LeagueError, "already applied"):
            current.apply(profile(), expected_version=2)
        with self.assertRaisesRegex(LeagueError, "stale"):
            current.assign("worker-1", expected_version=1)

    def test_only_applicant_can_be_assigned(self):
        with self.assertRaisesRegex(LeagueError, "only an applicant"):
            order().assign("worker-1", expected_version=1)

    def test_delivery_requires_evidence_and_assignee(self):
        current = order().apply(profile(), expected_version=1).assign("worker-1", expected_version=2)
        with self.assertRaises(LeagueError):
            current.submit("worker-1", (), expected_version=3)
        with self.assertRaisesRegex(LeagueError, "only the assigned"):
            current.submit("worker-2", ("delivery:1",), expected_version=3)

    def test_assignee_cannot_self_accept(self):
        current = order().apply(profile(), expected_version=1).assign("worker-1", expected_version=2)
        current = current.submit("worker-1", ("delivery:1",), expected_version=3)
        with self.assertRaisesRegex(LeagueError, "independent"):
            current.accept("worker-1", expected_version=4)

    def test_unaccepted_work_cannot_be_settled(self):
        current = order().apply(profile(), expected_version=1).assign("worker-1", expected_version=2)
        with self.assertRaisesRegex(LeagueError, "accepted work"):
            current.settlement_amounts()
        self.assertFalse(current.settlement_ready)

    def test_payout_shares_must_balance(self):
        current = order().apply(profile(), expected_version=1)
        with self.assertRaisesRegex(LeagueError, "10000"):
            current.assign(
                "worker-1", expected_version=2,
                payout_shares=(PayoutShare("worker-1", 6000), PayoutShare("partner-2", 3000)),
            )

    def test_invalid_money_and_naive_timestamps_rejected(self):
        with self.assertRaises(LeagueError):
            WorkOrder(
                "bad", "buyer", "Title", "Description", (), Decimal("NaN"), "KZT",
                "2026-11-13T09:00:00", "2026-11-20T09:00:00Z",
            )


if __name__ == "__main__":
    unittest.main()
