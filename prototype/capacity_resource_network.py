"""SYNERGY Capacity & Resource Network: fail-closed capacity snapshot validation.

This module validates time-bounded resource claims against resolver-supplied
capacity snapshots. It is not an asset registry, scheduler, inventory ledger,
reservation service, employment system, or contract authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
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


def _positive_int(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CooperativeMarketError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class CapacitySnapshot:
    """A versioned, time-bounded claim from an external resource authority."""

    resource_ref: str
    provider_organization_id: str
    capability_refs: frozenset[str]
    capacity: int
    unit: str
    available_from: datetime
    available_to: datetime
    observed_at: datetime
    revision: int
    authority_ref: str
    evidence_refs: frozenset[str]
    status: str = "active"

    def __post_init__(self):
        for field in ("resource_ref", "provider_organization_id", "unit", "authority_ref"):
            _text(getattr(self, field), field)
        if not isinstance(self.capability_refs, (set, frozenset)) or not self.capability_refs:
            raise CooperativeMarketError("capacity snapshot requires capability references")
        if any(not isinstance(x, str) or not x.strip() for x in self.capability_refs):
            raise CooperativeMarketError("capability references must be non-empty")
        _positive_int(self.capacity, "capacity")
        start = _instant(self.available_from, "available_from")
        end = _instant(self.available_to, "available_to")
        observed = _instant(self.observed_at, "observed_at")
        if end <= start:
            raise CooperativeMarketError("capacity availability interval must be positive")
        if observed > end:
            raise CooperativeMarketError("capacity snapshot cannot be observed after its availability window")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise CooperativeMarketError("capacity revision must be a non-negative integer")
        if not isinstance(self.evidence_refs, (set, frozenset)) or not self.evidence_refs:
            raise CooperativeMarketError("capacity snapshot requires evidence references")
        if any(not isinstance(x, str) or not x.strip() for x in self.evidence_refs):
            raise CooperativeMarketError("capacity evidence references must be non-empty")
        if self.status not in {"active", "suspended", "withdrawn", "expired"}:
            raise CooperativeMarketError("unsupported capacity snapshot status")


@dataclass(frozen=True)
class ResourceClaim:
    """A requested quantity of one canonical resource for a bounded interval."""

    claim_id: str
    resource_ref: str
    required_capability_refs: frozenset[str]
    quantity: int
    unit: str
    start: datetime
    end: datetime
    expected_capacity_revision: int

    def __post_init__(self):
        for field in ("claim_id", "resource_ref", "unit"):
            _text(getattr(self, field), field)
        if not isinstance(self.required_capability_refs, (set, frozenset)) or not self.required_capability_refs:
            raise CooperativeMarketError("resource claim requires capability references")
        if any(not isinstance(x, str) or not x.strip() for x in self.required_capability_refs):
            raise CooperativeMarketError("required capability references must be non-empty")
        _positive_int(self.quantity, "quantity")
        if _instant(self.end, "end") <= _instant(self.start, "start"):
            raise CooperativeMarketError("resource claim interval must be positive")
        if (isinstance(self.expected_capacity_revision, bool)
                or not isinstance(self.expected_capacity_revision, int)
                or self.expected_capacity_revision < 0):
            raise CooperativeMarketError("expected capacity revision must be a non-negative integer")


@dataclass(frozen=True)
class ResourceBundleValidation:
    claim_count: int
    resource_count: int
    peak_quantities: tuple[tuple[str, int, str], ...]
    snapshot_revisions: tuple[tuple[str, int], ...]


def validate_resource_bundle(
    claims: tuple[ResourceClaim, ...],
    *,
    snapshots: Mapping[str, CapacitySnapshot],
    organizations: Mapping[str, EconomicOrganization],
    verified_evidence_refs: frozenset[str],
    at: datetime,
    max_snapshot_age: timedelta = timedelta(minutes=15),
) -> ResourceBundleValidation:
    """Validate claims against snapshots; never reserve or guarantee availability.

    Concurrent claims against the same resource are summed using half-open
    intervals [start, end). Existing reservations and competing requests are
    not visible unless reflected by the authoritative snapshot. Only an
    external atomic reservation response can confirm a booking.
    """
    instant = _instant(at, "at")
    if not isinstance(claims, tuple) or not claims:
        raise CooperativeMarketError("resource bundle must be a non-empty tuple")
    if not isinstance(snapshots, Mapping):
        raise CooperativeMarketError("capacity snapshots must come from a canonical resolver")
    if not isinstance(organizations, Mapping):
        raise CooperativeMarketError("provider organizations must come from a canonical resolver")
    if not isinstance(verified_evidence_refs, (set, frozenset)):
        raise CooperativeMarketError("verified evidence must be a resolver-produced set")
    if any(not isinstance(x, str) or not x.strip() for x in verified_evidence_refs):
        raise CooperativeMarketError("verified evidence references must be non-empty")
    if not isinstance(max_snapshot_age, timedelta) or max_snapshot_age < timedelta(0):
        raise CooperativeMarketError("max_snapshot_age must be a non-negative timedelta")

    ids = [claim.claim_id for claim in claims]
    if len(ids) != len(set(ids)):
        raise CooperativeMarketError("duplicate resource claim ID")

    grouped: dict[str, list[ResourceClaim]] = {}
    for claim in claims:
        grouped.setdefault(claim.resource_ref, []).append(claim)

    peak_rows: list[tuple[str, int, str]] = []
    revision_rows: list[tuple[str, int]] = []
    for resource_ref, resource_claims in sorted(grouped.items()):
        snapshot = snapshots.get(resource_ref)
        if snapshot is None or snapshot.resource_ref != resource_ref:
            raise CooperativeMarketError("resource snapshot is missing or keyed by a mismatched canonical reference")
        if snapshot.status != "active":
            raise CooperativeMarketError("resource capacity snapshot is not active")
        provider = organizations.get(snapshot.provider_organization_id)
        if provider is None or provider.status != "active":
            raise CooperativeMarketError("capacity provider organization is missing or inactive")
        if any(claim.expected_capacity_revision != snapshot.revision for claim in resource_claims):
            raise CooperativeMarketError("stale capacity snapshot revision")
        observed = _instant(snapshot.observed_at, "observed_at")
        if observed > instant or instant - observed > max_snapshot_age:
            raise CooperativeMarketError("capacity snapshot is stale or from the future")
        required_evidence = set(snapshot.evidence_refs) | {snapshot.authority_ref}
        if not required_evidence.issubset(verified_evidence_refs):
            raise CooperativeMarketError("capacity authority or evidence reference is unverified")

        events: list[tuple[datetime, int]] = []
        for claim in resource_claims:
            start, end = _instant(claim.start, "start"), _instant(claim.end, "end")
            if start < instant:
                raise CooperativeMarketError("resource claim cannot begin in the past")
            if start < _instant(snapshot.available_from, "available_from") or end > _instant(snapshot.available_to, "available_to"):
                raise CooperativeMarketError("resource claim is outside the snapshot availability window")
            if claim.unit != snapshot.unit:
                raise CooperativeMarketError("resource claim unit does not match capacity unit")
            if not claim.required_capability_refs.issubset(snapshot.capability_refs):
                raise CooperativeMarketError("resource snapshot does not satisfy required capabilities")
            events.append((start, claim.quantity))
            events.append((end, -claim.quantity))

        # At equal timestamps, process releases before acquisitions (half-open intervals).
        events.sort(key=lambda item: (item[0], item[1]))
        current = peak = 0
        for _, delta in events:
            current += delta
            peak = max(peak, current)
        if peak > snapshot.capacity:
            raise CooperativeMarketError("concurrent resource claims exceed declared capacity")
        peak_rows.append((resource_ref, peak, snapshot.unit))
        revision_rows.append((resource_ref, snapshot.revision))

    return ResourceBundleValidation(
        claim_count=len(claims),
        resource_count=len(grouped),
        peak_quantities=tuple(peak_rows),
        snapshot_revisions=tuple(revision_rows),
    )
