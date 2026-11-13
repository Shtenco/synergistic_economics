"""SYNERGY LEAGUES phase-1 domain contracts.

This is a dependency-free research/domain prototype. It records eligibility and
work-order state transitions; it does not authenticate users, persist state,
hold funds, or post financial entries.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
import re
from typing import Iterable


class LeagueError(ValueError):
    """Invalid league, profile, or work-order transition."""


class League(str, Enum):
    STARTER = "starter"
    EXPERT = "expert"
    BUSINESS = "business"
    CAPITAL = "capital"


class WorkStatus(str, Enum):
    OPEN = "open"
    ASSIGNED = "assigned"
    SUBMITTED = "submitted"
    REVISION_REQUESTED = "revision_requested"
    ACCEPTED = "accepted"
    CANCELLED = "cancelled"


def _required(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LeagueError(f"{field} is required")
    return value.strip()


def _timestamp(value: str, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as exc:
        raise LeagueError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise LeagueError(f"{field} must include a timezone")
    return parsed


def _money(value: Decimal | str | int) -> Decimal:
    if isinstance(value, bool):
        raise LeagueError("budget must be a finite positive decimal amount")
    try:
        amount = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise LeagueError("budget must be a finite positive decimal amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise LeagueError("budget must be a finite positive decimal amount")
    return amount


@dataclass(frozen=True)
class SkillEvidence:
    skill_code: str
    evidence_ref: str
    issuer: str
    verified_at: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "skill_code", _required(self.skill_code, "skill_code").lower())
        object.__setattr__(self, "evidence_ref", _required(self.evidence_ref, "evidence_ref"))
        object.__setattr__(self, "issuer", _required(self.issuer, "issuer"))
        _timestamp(self.verified_at, "verified_at")


@dataclass(frozen=True)
class ParticipantProfile:
    participant_id: str
    display_name: str
    skill_evidence: tuple[SkillEvidence, ...] = ()
    discoverable: bool = False
    version: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(self, "participant_id", _required(self.participant_id, "participant_id"))
        object.__setattr__(self, "display_name", _required(self.display_name, "display_name"))
        if self.version < 1:
            raise LeagueError("profile version must be positive")
        codes = [item.skill_code for item in self.skill_evidence]
        if len(codes) != len(set(codes)):
            raise LeagueError("duplicate skill evidence is not allowed")

    @property
    def verified_skills(self) -> frozenset[str]:
        return frozenset(item.skill_code for item in self.skill_evidence)


@dataclass(frozen=True)
class LeagueMembership:
    """An earned/access-granted membership, never a payment-tier purchase."""

    membership_id: str
    participant_id: str
    league: League
    awarded_at: str
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        for field in ("membership_id", "participant_id"):
            object.__setattr__(self, field, _required(getattr(self, field), field))
        _timestamp(self.awarded_at, "awarded_at")
        if not self.evidence_refs or any(not str(ref).strip() for ref in self.evidence_refs):
            raise LeagueError("league membership requires verifiable evidence references")
        if len(set(self.evidence_refs)) != len(self.evidence_refs):
            raise LeagueError("duplicate membership evidence reference")


@dataclass(frozen=True)
class PayoutShare:
    recipient_id: str
    basis_points: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "recipient_id", _required(self.recipient_id, "recipient_id"))
        if isinstance(self.basis_points, bool) or not isinstance(self.basis_points, int):
            raise LeagueError("basis_points must be an integer")
        if not 1 <= self.basis_points <= 10_000:
            raise LeagueError("basis_points must be between 1 and 10000")


@dataclass(frozen=True)
class WorkOrder:
    order_id: str
    buyer_id: str
    title: str
    description: str
    required_skills: tuple[str, ...]
    budget: Decimal
    currency: str
    created_at: str
    deadline: str
    status: WorkStatus = WorkStatus.OPEN
    applications: tuple[str, ...] = ()
    assignee_id: str | None = None
    payout_shares: tuple[PayoutShare, ...] = ()
    delivery_evidence_refs: tuple[str, ...] = ()
    reviewer_id: str | None = None
    version: int = 1

    def __post_init__(self) -> None:
        for field in ("order_id", "buyer_id", "title", "description"):
            object.__setattr__(self, field, _required(getattr(self, field), field))
        normalized = tuple(sorted({_required(skill, "required_skill").lower() for skill in self.required_skills}))
        object.__setattr__(self, "required_skills", normalized)
        object.__setattr__(self, "budget", _money(self.budget))
        if not isinstance(self.currency, str) or not re.fullmatch(r"[A-Z]{3}", self.currency):
            raise LeagueError("currency must be a three-letter uppercase code")
        created, deadline = _timestamp(self.created_at, "created_at"), _timestamp(self.deadline, "deadline")
        if deadline <= created:
            raise LeagueError("deadline must be later than created_at")
        if self.version < 1:
            raise LeagueError("work-order version must be positive")
        if len(self.applications) != len(set(self.applications)):
            raise LeagueError("duplicate applications are not allowed")
        if self.payout_shares:
            recipients = [share.recipient_id for share in self.payout_shares]
            if len(recipients) != len(set(recipients)):
                raise LeagueError("duplicate payout recipients are not allowed")
            if sum(share.basis_points for share in self.payout_shares) != 10_000:
                raise LeagueError("payout shares must total exactly 10000 basis points")
        if self.status in (WorkStatus.ASSIGNED, WorkStatus.SUBMITTED, WorkStatus.REVISION_REQUESTED, WorkStatus.ACCEPTED) and not self.assignee_id:
            raise LeagueError("assigned work order requires an assignee")
        if self.status in (WorkStatus.SUBMITTED, WorkStatus.REVISION_REQUESTED, WorkStatus.ACCEPTED) and not self.delivery_evidence_refs:
            raise LeagueError("submitted work requires delivery evidence")
        if self.status == WorkStatus.ACCEPTED and not self.reviewer_id:
            raise LeagueError("accepted work requires an independent reviewer")

    def _check_version(self, expected_version: int) -> None:
        if expected_version != self.version:
            raise LeagueError(f"stale work-order version: expected {expected_version}, current {self.version}")

    def apply(self, profile: ParticipantProfile, *, expected_version: int) -> "WorkOrder":
        self._check_version(expected_version)
        if self.status != WorkStatus.OPEN:
            raise LeagueError("applications are accepted only for open work orders")
        if profile.participant_id == self.buyer_id:
            raise LeagueError("buyer cannot apply to its own work order")
        if profile.participant_id in self.applications:
            raise LeagueError("participant has already applied")
        missing = set(self.required_skills) - profile.verified_skills
        if missing:
            raise LeagueError(f"missing verified skills: {', '.join(sorted(missing))}")
        return replace(self, applications=self.applications + (profile.participant_id,), version=self.version + 1)

    def assign(
        self,
        participant_id: str,
        *,
        expected_version: int,
        payout_shares: Iterable[PayoutShare] = (),
    ) -> "WorkOrder":
        self._check_version(expected_version)
        participant_id = _required(participant_id, "participant_id")
        if self.status != WorkStatus.OPEN or participant_id not in self.applications:
            raise LeagueError("only an applicant can be assigned to an open work order")
        shares = tuple(payout_shares) or (PayoutShare(participant_id, 10_000),)
        if sum(item.basis_points for item in shares) != 10_000:
            raise LeagueError("payout shares must total exactly 10000 basis points")
        if participant_id not in {item.recipient_id for item in shares}:
            raise LeagueError("assignee must be included in the agreed payout shares")
        return replace(
            self, status=WorkStatus.ASSIGNED, assignee_id=participant_id,
            payout_shares=shares, version=self.version + 1,
        )

    def submit(
        self, participant_id: str, evidence_refs: Iterable[str], *, expected_version: int
    ) -> "WorkOrder":
        self._check_version(expected_version)
        if self.status not in (WorkStatus.ASSIGNED, WorkStatus.REVISION_REQUESTED):
            raise LeagueError("only assigned work can be submitted")
        if participant_id != self.assignee_id:
            raise LeagueError("only the assigned participant can submit delivery")
        refs = tuple(_required(ref, "evidence_ref") for ref in evidence_refs)
        if not refs or len(refs) != len(set(refs)):
            raise LeagueError("delivery requires unique evidence references")
        return replace(
            self, status=WorkStatus.SUBMITTED, delivery_evidence_refs=refs,
            reviewer_id=None, version=self.version + 1,
        )

    def request_revision(self, reviewer_id: str, *, expected_version: int) -> "WorkOrder":
        self._check_version(expected_version)
        reviewer_id = _required(reviewer_id, "reviewer_id")
        if self.status != WorkStatus.SUBMITTED:
            raise LeagueError("revision can be requested only for submitted work")
        if reviewer_id == self.assignee_id:
            raise LeagueError("assignee cannot review their own delivery")
        return replace(self, status=WorkStatus.REVISION_REQUESTED, reviewer_id=reviewer_id, version=self.version + 1)

    def accept(self, reviewer_id: str, *, expected_version: int) -> "WorkOrder":
        self._check_version(expected_version)
        reviewer_id = _required(reviewer_id, "reviewer_id")
        if self.status != WorkStatus.SUBMITTED:
            raise LeagueError("only submitted work can be accepted")
        if reviewer_id in (self.buyer_id, self.assignee_id):
            raise LeagueError("reviewer must be independent of buyer and assignee")
        return replace(self, status=WorkStatus.ACCEPTED, reviewer_id=reviewer_id, version=self.version + 1)

    @property
    def settlement_ready(self) -> bool:
        """True means accepted evidence exists; it does not authorize or execute payment."""
        return self.status == WorkStatus.ACCEPTED and bool(self.payout_shares)

    def settlement_amounts(self) -> dict[str, Decimal]:
        """Return the agreed split for a downstream settlement authority to review."""
        if not self.settlement_ready:
            raise LeagueError("settlement requires accepted work")
        allocated = Decimal("0.00")
        result: dict[str, Decimal] = {}
        shares = sorted(self.payout_shares, key=lambda item: item.recipient_id)
        for share in shares[:-1]:
            amount = (self.budget * Decimal(share.basis_points) / Decimal(10_000)).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            result[share.recipient_id] = amount
            allocated += amount
        result[shares[-1].recipient_id] = self.budget - allocated
        if sum(result.values(), Decimal("0.00")) != self.budget:
            raise LeagueError("settlement split does not conserve the agreed budget")
        return result
