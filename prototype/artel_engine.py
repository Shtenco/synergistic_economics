"""SYNERGY Artel Engine: read-only production mandate contract.

This module validates references and bounded work-package proposals. It does
not create legal entities, employment, asset title, IP rights, reservations,
journal entries, debt, payments or settlement.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from cellular_cooperative_market import CooperativeMarketError, EconomicOrganization


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CooperativeMarketError(f"{field} must be non-empty text")
    return value.strip()


def _instant(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CooperativeMarketError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def _nonnegative_minor(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise CooperativeMarketError(f"{field} must be a non-negative integer")
    return value


@dataclass(frozen=True)
class ArtelProductionMandate:
    """A bounded, evidence-backed mandate; not a legal or financial authority."""

    mandate_id: str
    artel_organization_id: str
    constitution_ref: str
    scope: str
    allowed_work_scopes: frozenset[str]
    authority_ref: str
    budget_authority_ref: str
    budget_limit_minor: int
    budget_currency: str
    effective_from: datetime
    effective_to: datetime | None = None
    status: str = "active"

    def __post_init__(self):
        for field in (
            "mandate_id", "artel_organization_id", "constitution_ref", "scope",
            "authority_ref", "budget_authority_ref", "budget_currency",
        ):
            _text(getattr(self, field), field)
        if not self.allowed_work_scopes or any(
            not isinstance(item, str) or not item.strip()
            for item in self.allowed_work_scopes
        ):
            raise CooperativeMarketError("allowed_work_scopes must contain non-empty scopes")
        _nonnegative_minor(self.budget_limit_minor, "budget_limit_minor")
        start = _instant(self.effective_from, "effective_from")
        if self.effective_to is not None and _instant(self.effective_to, "effective_to") <= start:
            raise CooperativeMarketError("mandate end must follow its start")
        if self.status not in {"active", "suspended", "revoked", "expired"}:
            raise CooperativeMarketError("unsupported mandate status")

    def active_at(self, at: datetime) -> bool:
        instant = _instant(at, "at")
        return (
            self.status == "active"
            and _instant(self.effective_from, "effective_from") <= instant
            and (self.effective_to is None or instant < _instant(self.effective_to, "effective_to"))
        )


@dataclass(frozen=True)
class ArtelWorkPackage:
    """A proposed production scope carrying references to canonical evidence."""

    work_package_id: str
    artel_organization_id: str
    mandate_id: str
    project_ref: str
    scope: str
    deliverable_ref: str
    budget_minor: int
    currency: str
    budget_authority_ref: str
    effective_from: datetime
    effective_to: datetime
    evidence_refs: tuple[str, ...]
    expected_revision: int
    idempotency_key: str

    def __post_init__(self):
        for field in (
            "work_package_id", "artel_organization_id", "mandate_id", "project_ref",
            "scope", "deliverable_ref", "currency", "budget_authority_ref",
            "idempotency_key",
        ):
            _text(getattr(self, field), field)
        _nonnegative_minor(self.budget_minor, "budget_minor")
        start = _instant(self.effective_from, "effective_from")
        if _instant(self.effective_to, "effective_to") <= start:
            raise CooperativeMarketError("work-package end must follow its start")
        if isinstance(self.expected_revision, bool) or not isinstance(self.expected_revision, int) or self.expected_revision < 0:
            raise CooperativeMarketError("expected_revision must be a non-negative integer")
        if not self.evidence_refs:
            raise CooperativeMarketError("work package requires at least one canonical evidence reference")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.evidence_refs):
            raise CooperativeMarketError("evidence references must be non-empty")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise CooperativeMarketError("duplicate work-package evidence reference")


def validate_artel_work_package(
    *,
    work_package: ArtelWorkPackage,
    mandate: ArtelProductionMandate,
    organizations: Mapping[str, EconomicOrganization],
    verified_evidence_refs: frozenset[str],
    at: datetime,
) -> None:
    """Validate a proposal against resolver-verified evidence and mandate bounds.

    The verified reference set must come from the canonical authority resolver;
    callers must never populate it from self-asserted work-package data.
    """
    instant = _instant(at, "at")
    artel = organizations.get(work_package.artel_organization_id)
    if artel is None or artel.status != "active":
        raise CooperativeMarketError("artel organization is missing or inactive")
    if "artel" not in artel.coordination_roles:
        raise CooperativeMarketError("organization does not carry the artel production role")
    if work_package.artel_organization_id != mandate.artel_organization_id:
        raise CooperativeMarketError("work package and mandate refer to different artels")
    if work_package.mandate_id != mandate.mandate_id:
        raise CooperativeMarketError("work package references a different mandate")
    if not mandate.active_at(instant):
        raise CooperativeMarketError("production mandate is not active")
    if work_package.scope not in mandate.allowed_work_scopes:
        raise CooperativeMarketError("work-package scope is outside the mandate")
    if work_package.budget_minor > mandate.budget_limit_minor:
        raise CooperativeMarketError("work-package budget exceeds mandate limit")
    if work_package.currency != mandate.budget_currency:
        raise CooperativeMarketError("work-package currency differs from mandate currency")
    if work_package.budget_authority_ref != mandate.budget_authority_ref:
        raise CooperativeMarketError("work package uses a different budget authority reference")
    start = _instant(work_package.effective_from, "work_package.effective_from")
    end = _instant(work_package.effective_to, "work_package.effective_to")
    mandate_start = _instant(mandate.effective_from, "mandate.effective_from")
    mandate_end = _instant(mandate.effective_to, "mandate.effective_to") if mandate.effective_to else None
    if start < mandate_start or (mandate_end is not None and end > mandate_end):
        raise CooperativeMarketError("work-package interval exceeds mandate validity")
    required = {
        mandate.constitution_ref,
        mandate.authority_ref,
        mandate.budget_authority_ref,
        work_package.project_ref,
        work_package.deliverable_ref,
        *work_package.evidence_refs,
    }
    missing = required.difference(verified_evidence_refs)
    if missing:
        raise CooperativeMarketError("canonical evidence is missing or unverified")


ARTEL_PARTICIPATION_CAPACITIES = frozenset({
    "member", "worker", "contractor", "apprentice", "investor",
    "asset_provider", "service_provider", "advisor", "delegate",
})


def validate_artel_participation(
    *,
    participation,
    existing_participations,
    organizations: Mapping[str, EconomicOrganization],
    verified_evidence_refs: frozenset[str],
    at: datetime,
) -> None:
    """Validate a voluntary, time-bounded participation against canonical evidence.

    Participation is a role-specific relationship, not proof of employment,
    ownership, voting power, debt, profit entitlement or asset title.
    The evidence set must be returned by the canonical authority resolver.
    """
    instant = _instant(at, "at")
    if participation.capacity not in ARTEL_PARTICIPATION_CAPACITIES:
        raise CooperativeMarketError("unsupported artel participation capacity")
    if participation.host_kind != "organization":
        raise CooperativeMarketError("artel participation must be hosted by an organization")
    artel = organizations.get(participation.host_id)
    if artel is None or artel.status != "active":
        raise CooperativeMarketError("host artel is missing or inactive")
    if "artel" not in artel.coordination_roles:
        raise CooperativeMarketError("participation host does not carry the artel role")
    if not participation.active_at(instant):
        raise CooperativeMarketError("participation is not active at the requested time")
    required = {participation.consent_ref, participation.rights_ref, artel.charter_ref}
    missing = required.difference(verified_evidence_refs)
    if missing:
        raise CooperativeMarketError("consent, rights or artel constitution evidence is unverified")

    seen_ids = set()
    for existing in existing_participations:
        if existing.participation_id in seen_ids:
            raise CooperativeMarketError("duplicate participation ID in host roster")
        seen_ids.add(existing.participation_id)
        if (
            existing.host_id == participation.host_id
            and existing.host_kind == "organization"
            and existing.active_at(instant)
            and existing.subject_id == participation.subject_id
            and existing.capacity == "member"
            and participation.capacity == "member"
            and existing.participation_id != participation.participation_id
        ):
            raise CooperativeMarketError("subject already has an active member participation in this artel")
    if participation.participation_id in seen_ids:
        raise CooperativeMarketError("participation ID already exists in host roster")
