"""SYNERGY Cooperative Production Network: non-authoritative coordination contract.

CPN composes canonical Economic Router candidates with verified production
capability, organizational eligibility and a guarded work-order lifecycle.
It does not create contracts, reserve assets, assign labour, transfer title,
incur debt, post journals, release payments or settle transactions.
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


def _positive_int(value: int, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise CooperativeMarketError(f"{field} must be a positive integer")
    return value


@dataclass(frozen=True)
class ProductionCapability:
    """A provider's evidence-backed capability declaration, not an asset booking."""

    capability_id: str
    provider_organization_id: str
    router_offer_id: str
    resource_ref: str
    capability_refs: frozenset[str]
    capacity: int
    unit: str
    available_from: datetime
    available_to: datetime
    asset_authority_ref: str
    evidence_refs: tuple[str, ...]
    revision: int = 0
    status: str = "active"

    def __post_init__(self):
        for field in ("capability_id", "provider_organization_id", "router_offer_id",
                      "resource_ref", "unit", "asset_authority_ref"):
            _text(getattr(self, field), field)
        if not self.capability_refs or any(not isinstance(x, str) or not x.strip() for x in self.capability_refs):
            raise CooperativeMarketError("capability_refs must contain non-empty references")
        _positive_int(self.capacity, "capacity")
        start, end = _instant(self.available_from, "available_from"), _instant(self.available_to, "available_to")
        if end <= start:
            raise CooperativeMarketError("capability availability interval must be positive")
        if not self.evidence_refs or any(not isinstance(x, str) or not x.strip() for x in self.evidence_refs):
            raise CooperativeMarketError("capability evidence_refs must be non-empty")
        if len(self.evidence_refs) != len(set(self.evidence_refs)):
            raise CooperativeMarketError("duplicate capability evidence reference")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise CooperativeMarketError("revision must be a non-negative integer")
        if self.status not in {"active", "suspended", "withdrawn", "expired"}:
            raise CooperativeMarketError("unsupported capability status")


@dataclass(frozen=True)
class ProductionOrder:
    """A scoped production request linked to, but not replacing, router demand."""

    order_id: str
    requester_organization_id: str
    router_demand_id: str
    scope: str
    deliverable_ref: str
    required_capability_refs: frozenset[str]
    quantity: int
    unit: str
    delivery_from: datetime
    delivery_to: datetime
    quality_criteria_ref: str
    contract_terms_ref: str
    expected_revision: int
    idempotency_key: str

    def __post_init__(self):
        for field in ("order_id", "requester_organization_id", "router_demand_id",
                      "scope", "deliverable_ref", "unit", "quality_criteria_ref",
                      "contract_terms_ref", "idempotency_key"):
            _text(getattr(self, field), field)
        if not self.required_capability_refs or any(not isinstance(x, str) or not x.strip() for x in self.required_capability_refs):
            raise CooperativeMarketError("required_capability_refs must be non-empty")
        _positive_int(self.quantity, "quantity")
        if _instant(self.delivery_to, "delivery_to") <= _instant(self.delivery_from, "delivery_from"):
            raise CooperativeMarketError("delivery interval must be positive")
        if isinstance(self.expected_revision, bool) or not isinstance(self.expected_revision, int) or self.expected_revision < 0:
            raise CooperativeMarketError("expected_revision must be a non-negative integer")


@dataclass(frozen=True)
class ProductionMatchProposal:
    """A proposed cross-organization match; never a contract or reservation."""

    proposal_id: str
    order_id: str
    router_match_id: str
    router_offer_id: str
    requester_organization_id: str
    provider_organization_id: str
    capability_id: str
    quantity: int
    unit: str
    scheduled_from: datetime
    scheduled_to: datetime
    cost_evidence_ref: str
    schedule_evidence_ref: str
    expected_order_revision: int
    expected_capability_revision: int
    bilateral_terms_ref: str

    def __post_init__(self):
        for field in ("proposal_id", "order_id", "router_match_id", "router_offer_id",
                      "requester_organization_id", "provider_organization_id", "capability_id",
                      "unit", "cost_evidence_ref", "schedule_evidence_ref", "bilateral_terms_ref"):
            _text(getattr(self, field), field)
        if self.requester_organization_id == self.provider_organization_id:
            raise CooperativeMarketError("production proposal requires distinct counterparties")
        _positive_int(self.quantity, "quantity")
        if _instant(self.scheduled_to, "scheduled_to") <= _instant(self.scheduled_from, "scheduled_from"):
            raise CooperativeMarketError("scheduled interval must be positive")
        for field in ("expected_order_revision", "expected_capability_revision"):
            value = getattr(self, field)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise CooperativeMarketError(f"{field} must be a non-negative integer")


def validate_production_match(
    *,
    order: ProductionOrder,
    capability: ProductionCapability,
    proposal: ProductionMatchProposal,
    organizations: Mapping[str, EconomicOrganization],
    verified_evidence_refs: frozenset[str],
    at: datetime,
) -> None:
    """Fail-closed validation of a candidate against current org/capability/order data.

    verified_evidence_refs must be supplied by the canonical evidence resolver;
    this function does not authenticate evidence, assets, router records or signatures.
    """
    instant = _instant(at, "at")
    if not isinstance(verified_evidence_refs, (set, frozenset)):
        raise CooperativeMarketError("verified evidence must be a resolver-produced set")
    if any(not isinstance(x, str) or not x.strip() for x in verified_evidence_refs):
        raise CooperativeMarketError("verified evidence references must be non-empty strings")
    for org_id in (order.requester_organization_id, capability.provider_organization_id):
        organization = organizations.get(org_id)
        if organization is None or organization.status != "active":
            raise CooperativeMarketError("production counterparty is missing or inactive")
    if proposal.order_id != order.order_id or proposal.capability_id != capability.capability_id:
        raise CooperativeMarketError("proposal does not bind the supplied order and capability")
    if proposal.requester_organization_id != order.requester_organization_id:
        raise CooperativeMarketError("proposal requester does not match the production order")
    if proposal.provider_organization_id != capability.provider_organization_id:
        raise CooperativeMarketError("proposal provider does not match the capability owner")
    if proposal.router_offer_id != capability.router_offer_id:
        raise CooperativeMarketError("proposal offer does not match the canonical capability offer")
    if proposal.expected_order_revision != order.expected_revision:
        raise CooperativeMarketError("stale production-order revision")
    if proposal.expected_capability_revision != capability.revision:
        raise CooperativeMarketError("stale capability revision")
    if capability.status != "active":
        raise CooperativeMarketError("production capability is not active")
    if proposal.unit != order.unit or proposal.unit != capability.unit:
        raise CooperativeMarketError("production quantity units do not match")
    if proposal.quantity != order.quantity or proposal.quantity > capability.capacity:
        raise CooperativeMarketError("proposal quantity exceeds or differs from the declared order/capacity")
    if not order.required_capability_refs.issubset(capability.capability_refs):
        raise CooperativeMarketError("provider capability does not satisfy the production order")
    start, end = _instant(proposal.scheduled_from, "scheduled_from"), _instant(proposal.scheduled_to, "scheduled_to")
    if start < _instant(order.delivery_from, "delivery_from") or end > _instant(order.delivery_to, "delivery_to"):
        raise CooperativeMarketError("proposed schedule is outside the order delivery window")
    if start < _instant(capability.available_from, "available_from") or end > _instant(capability.available_to, "available_to"):
        raise CooperativeMarketError("proposed schedule is outside declared capability availability")
    required = {capability.asset_authority_ref, *capability.evidence_refs,
                proposal.cost_evidence_ref, proposal.schedule_evidence_ref,
                proposal.bilateral_terms_ref, order.quality_criteria_ref,
                order.contract_terms_ref}
    if not required.issubset(verified_evidence_refs):
        raise CooperativeMarketError("one or more production, asset, cost, schedule or terms references are unverified")
    # Router match ID is deliberately opaque here: the canonical router remains its authority.


WORK_ORDER_TRANSITIONS = {
    "draft": frozenset({"published", "cancelled"}),
    "published": frozenset({"matched", "cancelled", "expired"}),
    "matched": frozenset({"proposed", "published", "cancelled", "expired"}),
    "proposed": frozenset({"accepted", "rejected", "published", "cancelled", "expired", "disputed"}),
    "accepted": frozenset({"reserved", "cancelled", "disputed"}),
    "reserved": frozenset({"in_progress", "cancelled", "disputed"}),
    "in_progress": frozenset({"delivered", "cancelled", "disputed"}),
    "delivered": frozenset({"verified", "disputed"}),
    "verified": frozenset({"settled", "disputed"}),
    "disputed": frozenset({"cancelled", "delivered", "verified"}),
    "rejected": frozenset(),
    "cancelled": frozenset(),
    "expired": frozenset(),
    "settled": frozenset(),
}

TRANSITION_AUTHORITY_DOMAIN = {
    "published": "workflow", "matched": "router", "proposed": "workflow",
    "accepted": "contract", "rejected": "contract", "reserved": "inventory",
    "in_progress": "execution", "delivered": "delivery", "verified": "quality",
    "settled": "settlement", "disputed": "dispute", "cancelled": "workflow",
    "expired": "workflow",
}


@dataclass(frozen=True)
class WorkOrderEvent:
    order_id: str
    from_status: str
    to_status: str
    revision: int
    actor_ref: str
    authority_domain: str
    authority_ref: str
    idempotency_key: str
    occurred_at: datetime


@dataclass(frozen=True)
class WorkOrderState:
    order_id: str
    status: str = "draft"
    revision: int = 0
    events: tuple[WorkOrderEvent, ...] = ()


def transition_work_order(
    state: WorkOrderState,
    *,
    target_status: str,
    actor_ref: str,
    authority_ref: str,
    expected_revision: int,
    idempotency_key: str,
    verified_authority_refs: Mapping[str, frozenset[str]],
    at: datetime,
) -> WorkOrderState:
    """Return a new state only after resolver-verified authority and CAS checks.

    The caller's persistence layer must atomically enforce revision and global
    idempotency uniqueness. This in-memory value object cannot provide that guarantee.
    """
    if state.status not in WORK_ORDER_TRANSITIONS or target_status not in WORK_ORDER_TRANSITIONS:
        raise CooperativeMarketError("unknown work-order lifecycle status")
    if target_status not in WORK_ORDER_TRANSITIONS[state.status]:
        raise CooperativeMarketError(f"illegal work-order transition: {state.status} -> {target_status}")
    for field, value in (("actor_ref", actor_ref), ("authority_ref", authority_ref),
                         ("idempotency_key", idempotency_key), ("order_id", state.order_id)):
        _text(value, field)
    if isinstance(expected_revision, bool) or not isinstance(expected_revision, int) or expected_revision != state.revision:
        raise CooperativeMarketError("work-order revision conflict")
    if any(event.idempotency_key == idempotency_key for event in state.events):
        raise CooperativeMarketError("replayed work-order idempotency key")
    domain = TRANSITION_AUTHORITY_DOMAIN[target_status]
    if not isinstance(verified_authority_refs, Mapping):
        raise CooperativeMarketError("verified authority references must be resolver-provided mapping")
    verified = verified_authority_refs.get(domain, frozenset())
    if not isinstance(verified, (set, frozenset)) or authority_ref not in verified:
        raise CooperativeMarketError(f"authority reference is not verified for domain: {domain}")
    instant = _instant(at, "at")
    event = WorkOrderEvent(state.order_id, state.status, target_status,
                           state.revision + 1, actor_ref, domain, authority_ref,
                           idempotency_key, instant)
    return WorkOrderState(state.order_id, target_status, state.revision + 1,
                          state.events + (event,))
