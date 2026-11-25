"""SYNERGY cellular cooperative market: non-authoritative domain contract.

This module composes organizational roles, non-exclusive participation,
scoped governance, consortium agreements and distribution proposals.

It deliberately does NOT create legal entities, infer title, create debt,
reserve inventory, post journals, custody money, execute contracts or settle
payments. Existing SYNERGY registers and authorities remain canonical.
Only the Python standard library is used.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, Mapping, Sequence


ROLE_KINDS = frozenset({"artel", "enterprise", "project_vehicle", "shared_infrastructure_operator"})
COORDINATION_UNIT_KINDS = frozenset({"dao_cell", "federation", "project_cell", "consortium"})
HOST_KINDS = frozenset({"organization", "coordination_unit"})
ORG_STATUSES = frozenset({"active", "suspended", "retired"})
PARTICIPATION_STATUSES = frozenset({"active", "suspended", "exited"})
RELATION_KINDS = frozenset({
    "membership", "contract", "supplies", "uses_service", "federates_with",
    "shares_infrastructure", "delegates_to", "collaborates_with",
})
PROTECTED_ACTIONS = frozenset({
    "transfer_legal_title", "release_external_payment", "create_debt",
    "create_guarantee", "change_existing_claim", "expel_member",
    "amend_fundamental_rights", "dissolve_organization", "use_sensitive_data",
})
DISTRIBUTION_RULES = frozenset({
    "equal_membership", "verified_ownership", "project_contribution",
    "verified_usage", "needs_access",
})


class CooperativeMarketError(ValueError):
    """Invalid domain object or unauthorized proposed transition."""


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CooperativeMarketError(f"{field} must be non-empty text")
    return value.strip()


def _instant(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CooperativeMarketError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _basis_points(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 10_000:
        raise CooperativeMarketError(f"{field} must be an integer from 0 to 10000")
    return value


@dataclass(frozen=True)
class EconomicOrganization:
    organization_id: str
    jurisdiction: str
    legal_form: str
    coordination_roles: frozenset[str]
    charter_ref: str
    status: str = "active"

    def __post_init__(self):
        _text(self.organization_id, "organization_id")
        _text(self.jurisdiction, "jurisdiction")
        _text(self.legal_form, "legal_form")
        _text(self.charter_ref, "charter_ref")
        if not self.coordination_roles or not self.coordination_roles.issubset(ROLE_KINDS):
            raise CooperativeMarketError("coordination_roles must contain known roles")
        if self.status not in ORG_STATUSES:
            raise CooperativeMarketError("unsupported organization status")


@dataclass(frozen=True)
class CoordinationUnit:
    unit_id: str
    unit_kind: str
    charter_ref: str
    legal_entity_id: str | None = None
    status: str = "active"

    def __post_init__(self):
        _text(self.unit_id, "unit_id")
        _text(self.charter_ref, "charter_ref")
        if self.unit_kind not in COORDINATION_UNIT_KINDS:
            raise CooperativeMarketError("unsupported coordination unit kind")
        if self.legal_entity_id is not None:
            _text(self.legal_entity_id, "legal_entity_id")
        if self.status not in ORG_STATUSES:
            raise CooperativeMarketError("unsupported coordination unit status")


@dataclass(frozen=True)
class Participation:
    participation_id: str
    subject_id: str
    host_id: str
    host_kind: str
    capacity: str
    consent_ref: str
    rights_ref: str
    effective_from: datetime
    effective_to: datetime | None = None
    status: str = "active"
    represented_organization_id: str | None = None
    delegation_authority_ref: str | None = None

    def __post_init__(self):
        for field in ("participation_id", "subject_id", "host_id",
                      "capacity", "consent_ref", "rights_ref"):
            _text(getattr(self, field), field)
        if self.host_kind not in HOST_KINDS:
            raise CooperativeMarketError("host_kind must be organization or coordination_unit")
        if self.capacity == "organization_delegate":
            if self.host_kind != "coordination_unit":
                raise CooperativeMarketError("organization delegates may only participate in coordination units")
            _text(self.represented_organization_id, "represented_organization_id")
            _text(self.delegation_authority_ref, "delegation_authority_ref")
        elif self.represented_organization_id is not None or self.delegation_authority_ref is not None:
            raise CooperativeMarketError("organization representation fields are only valid for organization delegates")
        _instant(self.effective_from, "effective_from")
        if self.effective_to is not None:
            if _instant(self.effective_to, "effective_to") <= _instant(self.effective_from, "effective_from"):
                raise CooperativeMarketError("effective_to must follow effective_from")
        if self.status not in PARTICIPATION_STATUSES:
            raise CooperativeMarketError("unsupported participation status")

    def active_at(self, at: datetime) -> bool:
        instant = _instant(at, "at")
        return (
            self.status == "active"
            and _instant(self.effective_from, "effective_from") <= instant
            and (self.effective_to is None or instant < _instant(self.effective_to, "effective_to"))
        )


@dataclass(frozen=True)
class OrganizationRelation:
    relation_id: str
    source_id: str
    target_id: str
    relation_kind: str
    scope: str
    agreement_ref: str
    effective_from: datetime
    effective_to: datetime | None = None

    def __post_init__(self):
        for field in ("relation_id", "source_id", "target_id", "scope", "agreement_ref"):
            _text(getattr(self, field), field)
        if self.source_id == self.target_id:
            raise CooperativeMarketError("self-relations are not permitted")
        if self.relation_kind not in RELATION_KINDS:
            raise CooperativeMarketError("unsupported relation_kind")
        _instant(self.effective_from, "effective_from")
        if self.effective_to is not None and _instant(self.effective_to, "effective_to") <= _instant(self.effective_from, "effective_from"):
            raise CooperativeMarketError("relation end must follow its start")


@dataclass(frozen=True)
class GovernancePolicy:
    policy_id: str
    governing_subject_id: str
    governing_subject_kind: str
    allowed_domains: frozenset[str]
    allowed_actions: frozenset[str]
    voting_rule: str
    quorum_bps: int
    approval_bps: int
    policy_ref: str

    def __post_init__(self):
        for field in ("policy_id", "governing_subject_id", "voting_rule", "policy_ref"):
            _text(getattr(self, field), field)
        if self.governing_subject_kind not in HOST_KINDS:
            raise CooperativeMarketError("governing_subject_kind must be organization or coordination_unit")
        if not self.allowed_domains or any(not isinstance(x, str) or not x.strip() for x in self.allowed_domains):
            raise CooperativeMarketError("allowed_domains must contain non-empty values")
        if not self.allowed_actions or any(not isinstance(x, str) or not x.strip() for x in self.allowed_actions):
            raise CooperativeMarketError("allowed_actions must contain non-empty values")
        if self.voting_rule not in {"one_member_one_vote", "one_organization_one_vote"}:
            raise CooperativeMarketError("unsupported voting_rule")
        _basis_points(self.quorum_bps, "quorum_bps")
        _basis_points(self.approval_bps, "approval_bps")
        if self.quorum_bps == 0 or self.approval_bps == 0:
            raise CooperativeMarketError("quorum and approval thresholds must be positive")


@dataclass(frozen=True)
class Ballot:
    voter_id: str
    choice: str
    evidence_ref: str

    def __post_init__(self):
        _text(self.voter_id, "voter_id")
        _text(self.evidence_ref, "evidence_ref")
        if self.choice not in {"approve", "reject", "abstain"}:
            raise CooperativeMarketError("choice must be approve, reject or abstain")


@dataclass(frozen=True)
class GovernanceResult:
    approved: bool
    eligible_count: int
    participating_count: int
    approval_bps: int
    quorum_met: bool
    reason: str


def evaluate_governance(
    *,
    policy: GovernancePolicy,
    decision_domain: str,
    action: str,
    participations: Sequence[Participation],
    ballots: Sequence[Ballot],
    organizations: Mapping[str, EconomicOrganization],
    coordination_units: Mapping[str, CoordinationUnit],
    at: datetime,
    verified_delegation_authority_refs: frozenset[str] = frozenset(),
) -> GovernanceResult:
    """Evaluate a vote; never executes the proposal or changes external state."""
    _text(decision_domain, "decision_domain")
    _text(action, "action")
    _instant(at, "at")
    if policy.governing_subject_kind == "organization":
        governing = organizations.get(policy.governing_subject_id)
    else:
        governing = coordination_units.get(policy.governing_subject_id)
    if governing is None or governing.status != "active":
        raise CooperativeMarketError("governing subject is missing or inactive")
    if decision_domain not in policy.allowed_domains:
        raise CooperativeMarketError("decision domain is outside the policy mandate")
    if action not in policy.allowed_actions:
        raise CooperativeMarketError("action is outside the explicit policy allowlist")
    if action in PROTECTED_ACTIONS:
        raise CooperativeMarketError("protected action requires a separate legal/authority workflow")

    active = [p for p in participations
              if p.host_id == policy.governing_subject_id
              and p.host_kind == policy.governing_subject_kind
              and p.active_at(at)]
    participation_ids = [p.participation_id for p in active]
    if len(participation_ids) != len(set(participation_ids)):
        raise CooperativeMarketError("duplicate active participation ID")

    if policy.voting_rule == "one_member_one_vote":
        eligible = {p.subject_id for p in active if p.capacity != "organization_delegate"}
    else:
        delegates = [p for p in active if p.capacity == "organization_delegate"]
        represented = [p.represented_organization_id for p in delegates]
        if len(represented) != len(set(represented)):
            raise CooperativeMarketError("an organization may have only one active delegate per decision")
        for delegate in delegates:
            organization = organizations.get(delegate.represented_organization_id)
            if organization is None or organization.status != "active":
                raise CooperativeMarketError("delegated organization is missing or inactive")
            if delegate.delegation_authority_ref not in verified_delegation_authority_refs:
                raise CooperativeMarketError("delegation authority reference is not verified by the canonical authority source")
        eligible = set(represented)
    if not eligible:
        raise CooperativeMarketError("no eligible voters")

    seen = set()
    counts = {"approve": 0, "reject": 0, "abstain": 0}
    for ballot in ballots:
        if ballot.voter_id in seen:
            raise CooperativeMarketError("duplicate ballot")
        seen.add(ballot.voter_id)
        if ballot.voter_id not in eligible:
            raise CooperativeMarketError("ballot from an ineligible voter")
        counts[ballot.choice] += 1

    participating = len(seen)
    quorum_met = participating * 10_000 >= len(eligible) * policy.quorum_bps
    cast = counts["approve"] + counts["reject"]
    approval_bps = (counts["approve"] * 10_000 // cast) if cast else 0
    approved = quorum_met and cast > 0 and approval_bps >= policy.approval_bps
    reason = "approved" if approved else (
        "quorum_not_met" if not quorum_met else "approval_threshold_not_met"
    )
    return GovernanceResult(approved, len(eligible), participating,
                            approval_bps, quorum_met, reason)


@dataclass(frozen=True)
class ConsortiumParticipant:
    organization_id: str
    commitment_ref: str
    authority_ref: str


@dataclass(frozen=True)
class CooperationAgreement:
    agreement_id: str
    purpose: str
    scope: str
    jurisdiction: str
    participants: tuple[ConsortiumParticipant, ...]
    agreement_ref: str
    effective_from: datetime
    effective_to: datetime | None = None

    def __post_init__(self):
        for field in ("agreement_id", "purpose", "scope", "jurisdiction", "agreement_ref"):
            _text(getattr(self, field), field)
        _instant(self.effective_from, "effective_from")
        if self.effective_to is not None and _instant(self.effective_to, "effective_to") <= _instant(self.effective_from, "effective_from"):
            raise CooperativeMarketError("agreement end must follow its start")
        ids = [p.organization_id for p in self.participants]
        if len(ids) < 2 or len(ids) != len(set(ids)):
            raise CooperativeMarketError("a consortium agreement requires at least two distinct organizations")
        for participant in self.participants:
            _text(participant.organization_id, "participant.organization_id")
            _text(participant.commitment_ref, "participant.commitment_ref")
            _text(participant.authority_ref, "participant.authority_ref")


def validate_agreement(
    agreement: CooperationAgreement,
    organizations: Mapping[str, EconomicOrganization],
) -> None:
    for participant in agreement.participants:
        organization = organizations.get(participant.organization_id)
        if organization is None or organization.status != "active":
            raise CooperativeMarketError("agreement participant is missing or inactive")
        if not participant.authority_ref:
            raise CooperativeMarketError("participant authority reference is required")


@dataclass(frozen=True)
class RecipientWeight:
    recipient_id: str
    weight: int
    evidence_ref: str

    def __post_init__(self):
        _text(self.recipient_id, "recipient_id")
        _text(self.evidence_ref, "evidence_ref")
        if isinstance(self.weight, bool) or not isinstance(self.weight, int) or self.weight < 0:
            raise CooperativeMarketError("recipient weight must be a non-negative integer")


@dataclass(frozen=True)
class DistributionShare:
    pool_id: str
    basis_points: int
    rule: str
    recipients: tuple[RecipientWeight, ...]
    policy_ref: str

    def __post_init__(self):
        _text(self.pool_id, "pool_id")
        _text(self.policy_ref, "policy_ref")
        _basis_points(self.basis_points, "basis_points")
        if self.rule not in DISTRIBUTION_RULES:
            raise CooperativeMarketError("unsupported distribution rule")
        if not self.recipients:
            raise CooperativeMarketError("distribution share requires recipients")
        ids = [r.recipient_id for r in self.recipients]
        if len(ids) != len(set(ids)):
            raise CooperativeMarketError("duplicate distribution recipient")
        if self.rule == "equal_membership" and any(r.weight != 1 for r in self.recipients):
            raise CooperativeMarketError("equal_membership uses unit weights")
        if self.rule != "equal_membership" and any(not r.evidence_ref for r in self.recipients):
            raise CooperativeMarketError("non-equal allocation requires evidence references")


@dataclass(frozen=True)
class VerifiedResidualPool:
    pool_id: str
    amount_minor: int
    currency: str
    source_authority_ref: str
    verified_distributable: bool

    def __post_init__(self):
        _text(self.pool_id, "pool_id")
        _text(self.currency, "currency")
        _text(self.source_authority_ref, "source_authority_ref")
        if isinstance(self.amount_minor, bool) or not isinstance(self.amount_minor, int) or self.amount_minor < 0:
            raise CooperativeMarketError("amount_minor must be a non-negative integer")
        if self.verified_distributable is not True:
            raise CooperativeMarketError("distribution requires an authoritative verified residual pool")


@dataclass(frozen=True)
class ProposedAllocation:
    pool_id: str
    recipient_id: str
    amount_minor: int
    currency: str
    rule: str
    evidence_ref: str


@dataclass(frozen=True)
class DistributionProposal:
    allocations: tuple[ProposedAllocation, ...]
    allocated_minor: int
    retained_minor: int
    currency: str
    source_authority_ref: str


def _largest_remainder(total: int, recipients: Sequence[RecipientWeight]) -> dict[str, int]:
    positive = [r for r in recipients if r.weight > 0]
    weight_sum = sum(r.weight for r in positive)
    if total == 0 or weight_sum == 0:
        return {r.recipient_id: 0 for r in recipients}
    base = {r.recipient_id: (total * r.weight) // weight_sum for r in positive}
    remainders = sorted(
        positive,
        key=lambda r: (-(total * r.weight % weight_sum), r.recipient_id),
    )
    residual = total - sum(base.values())
    for recipient in remainders[:residual]:
        base[recipient.recipient_id] += 1
    return {r.recipient_id: base.get(r.recipient_id, 0) for r in recipients}


def propose_distribution(
    pool: VerifiedResidualPool,
    shares: Sequence[DistributionShare],
) -> DistributionProposal:
    """Produce a proposal only; no journal posting, payment or title change occurs."""
    if any(share.pool_id != pool.pool_id for share in shares):
        raise CooperativeMarketError("share references a different residual pool")
    ids = [share.pool_id + ":" + share.rule for share in shares]
    if len(ids) != len(set(ids)):
        raise CooperativeMarketError("duplicate pool/rule share")
    total_bps = sum(share.basis_points for share in shares)
    if total_bps > 10_000:
        raise CooperativeMarketError("distribution shares exceed the verified residual pool")
    allocations = []
    allocated_total = 0
    for share in shares:
        share_amount = pool.amount_minor * share.basis_points // 10_000
        amounts = _largest_remainder(share_amount, share.recipients)
        by_id = {r.recipient_id: r for r in share.recipients}
        for recipient_id in sorted(amounts):
            amount = amounts[recipient_id]
            if amount:
                allocations.append(ProposedAllocation(
                    pool.pool_id, recipient_id, amount, pool.currency,
                    share.rule, by_id[recipient_id].evidence_ref,
                ))
                allocated_total += amount
    return DistributionProposal(
        tuple(allocations), allocated_total, pool.amount_minor - allocated_total,
        pool.currency, pool.source_authority_ref,
    )


@dataclass(frozen=True)
class MarketMatchReference:
    demand_id: str
    offer_id: str
    match_candidate_id: str
    buyer_organization_id: str
    seller_organization_id: str
    bilateral_consent_ref: str
    router_policy_ref: str

    def __post_init__(self):
        for field in ("demand_id", "offer_id", "match_candidate_id",
                      "buyer_organization_id", "seller_organization_id",
                      "bilateral_consent_ref", "router_policy_ref"):
            _text(getattr(self, field), field)
        if self.buyer_organization_id == self.seller_organization_id:
            raise CooperativeMarketError("market match must identify distinct buyer and seller")


def validate_market_match(
    match: MarketMatchReference,
    organizations: Mapping[str, EconomicOrganization],
) -> None:
    for org_id in (match.buyer_organization_id, match.seller_organization_id):
        organization = organizations.get(org_id)
        if organization is None or organization.status != "active":
            raise CooperativeMarketError("market counterparty is missing or inactive")
    # A reference and consent proof do not create a contract or settle a deal.


def validate_coordination_units(
    units: Mapping[str, CoordinationUnit],
    organizations: Mapping[str, EconomicOrganization],
) -> None:
    for unit_id, unit in units.items():
        if unit_id != unit.unit_id:
            raise CooperativeMarketError("coordination-unit map key does not match ID")
        if unit.legal_entity_id is not None:
            legal_entity = organizations.get(unit.legal_entity_id)
            if legal_entity is None:
                raise CooperativeMarketError("coordination unit references an unknown legal entity")
            if unit.status == "active" and legal_entity.status != "active":
                raise CooperativeMarketError("active coordination unit cannot bind to an inactive legal entity")


def validate_participations(
    participations: Iterable[Participation],
    organizations: Mapping[str, EconomicOrganization],
    coordination_units: Mapping[str, CoordinationUnit],
) -> None:
    """Validate participation identities, host references and delegate principals."""
    seen_ids = set()
    for participation in participations:
        if participation.participation_id in seen_ids:
            raise CooperativeMarketError("duplicate participation ID")
        seen_ids.add(participation.participation_id)
        if participation.host_kind == "organization":
            host = organizations.get(participation.host_id)
        else:
            host = coordination_units.get(participation.host_id)
        if host is None:
            raise CooperativeMarketError("participation references an unknown host")
        if participation.status == "active" and host.status != "active":
            raise CooperativeMarketError("active participation cannot attach to an inactive host")
        if participation.capacity == "organization_delegate":
            represented = organizations.get(participation.represented_organization_id)
            if represented is None or represented.status != "active":
                raise CooperativeMarketError("delegate principal is missing or inactive")


def validate_network(
    organizations: Mapping[str, EconomicOrganization],
    relations: Iterable[OrganizationRelation],
) -> None:
    seen = set()
    for organization_id, organization in organizations.items():
        if organization_id != organization.organization_id:
            raise CooperativeMarketError("organization map key does not match canonical ID")
    for relation in relations:
        if relation.relation_id in seen:
            raise CooperativeMarketError("duplicate relation ID")
        seen.add(relation.relation_id)
        if relation.source_id not in organizations or relation.target_id not in organizations:
            raise CooperativeMarketError("relation references an unknown organization")
