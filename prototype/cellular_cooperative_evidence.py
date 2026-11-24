"""Strict, read-only governance evidence gate for the CCM domain contract.

The canonical authority adapter must resolve and verify each record before
passing it here. This module validates the adapter's typed assertions and
binds them to the exact subject, resource, scope and decision time.

A CanonicalEvidence instance is NOT a signature, credential or trust root.
Constructing one in application code does not prove authority. Production
callers must obtain these records from the canonical rights/consent/policy
resolver and independently enforce its authentication and revocation rules.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping, Sequence

from cellular_cooperative_market import (
    Ballot,
    CooperativeMarketError,
    CoordinationUnit,
    EconomicOrganization,
    GovernancePolicy,
    GovernanceResult,
    Participation,
    evaluate_governance,
)

_EVIDENCE_KINDS = frozenset({
    "participation_consent",
    "participation_rights",
    "delegation_authority",
    "governance_policy",
    "governance_ballot",
})
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _required_text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CooperativeMarketError(f"{field} must be non-empty text")
    return value.strip()


def _utc(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CooperativeMarketError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class CanonicalEvidence:
    """A resolver-verified evidence assertion; not a self-authenticating proof."""

    evidence_ref: str
    evidence_kind: str
    subject_id: str
    resource_id: str
    scope: str
    issuer_ref: str
    source_snapshot_ref: str
    payload_sha256: str
    verified_at: datetime
    valid_from: datetime
    valid_until: datetime | None = None
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        for field in (
            "evidence_ref", "subject_id", "resource_id", "scope",
            "issuer_ref", "source_snapshot_ref",
        ):
            _required_text(getattr(self, field), field)
        if self.evidence_kind not in _EVIDENCE_KINDS:
            raise CooperativeMarketError("unsupported canonical evidence kind")
        if not isinstance(self.payload_sha256, str) or not _SHA256_RE.fullmatch(self.payload_sha256):
            raise CooperativeMarketError("payload_sha256 must be 64 lowercase hexadecimal characters")
        verified = _utc(self.verified_at, "verified_at")
        start = _utc(self.valid_from, "valid_from")
        if verified < start:
            raise CooperativeMarketError("evidence cannot be verified before its validity begins")
        if self.valid_until is not None and _utc(self.valid_until, "valid_until") <= start:
            raise CooperativeMarketError("valid_until must follow valid_from")
        if self.revoked_at is not None:
            _utc(self.revoked_at, "revoked_at")

    def assert_valid_at(self, at: datetime) -> None:
        instant = _utc(at, "at")
        if _utc(self.verified_at, "verified_at") > instant:
            raise CooperativeMarketError("evidence was verified after the decision time")
        if _utc(self.valid_from, "valid_from") > instant:
            raise CooperativeMarketError("evidence is not yet valid")
        if self.valid_until is not None and instant >= _utc(self.valid_until, "valid_until"):
            raise CooperativeMarketError("evidence has expired")
        if self.revoked_at is not None and instant >= _utc(self.revoked_at, "revoked_at"):
            raise CooperativeMarketError("evidence was revoked before the decision time")


def _require_evidence(
    evidence: Mapping[str, CanonicalEvidence],
    *,
    evidence_ref: str,
    evidence_kind: str,
    subject_id: str,
    resource_id: str,
    scope: str,
    at: datetime,
) -> CanonicalEvidence:
    record = evidence.get(evidence_ref)
    if record is None:
        raise CooperativeMarketError(f"missing canonical evidence: {evidence_ref}")
    if not isinstance(record, CanonicalEvidence):
        raise CooperativeMarketError("evidence resolver returned an unsupported record type")
    if record.evidence_ref != evidence_ref:
        raise CooperativeMarketError("evidence map key does not match canonical evidence reference")
    if record.evidence_kind != evidence_kind:
        raise CooperativeMarketError("canonical evidence kind mismatch")
    if record.subject_id != subject_id:
        raise CooperativeMarketError("canonical evidence subject mismatch")
    if record.resource_id != resource_id:
        raise CooperativeMarketError("canonical evidence resource mismatch")
    if record.scope != scope:
        raise CooperativeMarketError("canonical evidence scope mismatch")
    record.assert_valid_at(at)
    return record


def evaluate_governance_with_canonical_evidence(
    *,
    policy: GovernancePolicy,
    decision_domain: str,
    action: str,
    participations: Sequence[Participation],
    ballots: Sequence[Ballot],
    organizations: Mapping[str, EconomicOrganization],
    coordination_units: Mapping[str, CoordinationUnit],
    at: datetime,
    verified_evidence: Mapping[str, CanonicalEvidence],
) -> GovernanceResult:
    """Fail-closed governance evaluation using resolver-verified evidence.

    Required evidence:
    - governance_policy for the exact governing subject and domain/action;
    - participation_consent and participation_rights for each active record;
    - delegation_authority for each active organization delegate;
    - governance_ballot for every submitted ballot.

    The function only evaluates a proposal. It does not execute it, persist a
    vote, change membership, transfer title, post a journal or settle funds.
    """
    instant = _utc(at, "at")
    decision_scope = f"{_required_text(decision_domain, 'decision_domain')}:{_required_text(action, 'action')}"

    # Reject malformed resolver output rather than silently ignoring it.
    for key, record in verified_evidence.items():
        if not isinstance(record, CanonicalEvidence):
            raise CooperativeMarketError("evidence resolver returned an unsupported record type")
        if key != record.evidence_ref:
            raise CooperativeMarketError("evidence map key does not match canonical evidence reference")

    governing = (
        organizations.get(policy.governing_subject_id)
        if policy.governing_subject_kind == "organization"
        else coordination_units.get(policy.governing_subject_id)
    )
    if governing is None or governing.status != "active":
        raise CooperativeMarketError("governing subject is missing or inactive")

    _require_evidence(
        verified_evidence,
        evidence_ref=policy.policy_ref,
        evidence_kind="governance_policy",
        subject_id=policy.governing_subject_id,
        resource_id=policy.governing_subject_id,
        scope=decision_scope,
        at=instant,
    )

    active = [
        p for p in participations
        if p.host_id == policy.governing_subject_id
        and p.host_kind == policy.governing_subject_kind
        and p.active_at(instant)
    ]
    for participation in active:
        participation_scope = participation.capacity
        _require_evidence(
            verified_evidence,
            evidence_ref=participation.consent_ref,
            evidence_kind="participation_consent",
            subject_id=participation.subject_id,
            resource_id=participation.host_id,
            scope=participation_scope,
            at=instant,
        )
        _require_evidence(
            verified_evidence,
            evidence_ref=participation.rights_ref,
            evidence_kind="participation_rights",
            subject_id=participation.subject_id,
            resource_id=participation.host_id,
            scope=participation_scope,
            at=instant,
        )
        if participation.capacity == "organization_delegate":
            _require_evidence(
                verified_evidence,
                evidence_ref=participation.delegation_authority_ref,
                evidence_kind="delegation_authority",
                subject_id=participation.represented_organization_id,
                resource_id=participation.host_id,
                scope=decision_scope,
                at=instant,
            )

    ballot_refs = set()
    for ballot in ballots:
        if ballot.evidence_ref in ballot_refs:
            raise CooperativeMarketError("a ballot evidence reference cannot be reused")
        ballot_refs.add(ballot.evidence_ref)
        _require_evidence(
            verified_evidence,
            evidence_ref=ballot.evidence_ref,
            evidence_kind="governance_ballot",
            subject_id=ballot.voter_id,
            resource_id=policy.governing_subject_id,
            scope=decision_scope,
            at=instant,
        )

    delegation_refs = frozenset(
        p.delegation_authority_ref
        for p in active
        if p.capacity == "organization_delegate"
    )
    return evaluate_governance(
        policy=policy,
        decision_domain=decision_domain,
        action=action,
        participations=participations,
        ballots=ballots,
        organizations=organizations,
        coordination_units=coordination_units,
        at=instant,
        verified_delegation_authority_refs=delegation_refs,
    )
