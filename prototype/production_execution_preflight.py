"""SYNERGY production execution preflight: read-only composition of canonical checks.

This module composes the existing production graph, temporary consortium and
capacity/resource validators into one immutable preflight receipt. It does not
reserve resources, transition an order, authorize work, create a contract,
dispatch execution, accept output or settle claims.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Mapping

from cellular_cooperative_market import (
    CooperationAgreement,
    CooperativeMarketError,
    EconomicOrganization,
)
from cooperative_production_network import ProductionOrder
from production_graph_engine import ProductionGraph
from capacity_resource_network import (
    CapacitySnapshot,
    ProductionGraphResourceValidation,
    ResourceClaim,
    validate_production_graph_resources,
)
from temporary_production_consortium import (
    TemporaryConsortiumValidation,
    TemporaryProductionConsortium,
    validate_temporary_production_consortium,
)


def _instant(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CooperativeMarketError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ProductionExecutionPreflightReceipt:
    """A structural, point-in-time validation receipt; never a reservation receipt."""

    plan_id: str
    agreement_id: str
    production_order_id: str
    graph_id: str
    graph_revision: int
    checked_at: datetime
    consortium_validation: TemporaryConsortiumValidation
    resource_validation: ProductionGraphResourceValidation
    verified_evidence_refs: frozenset[str]

    def __post_init__(self):
        for field in ("plan_id", "agreement_id", "production_order_id", "graph_id"):
            value = getattr(self, field)
            if not isinstance(value, str) or not value.strip():
                raise CooperativeMarketError(f"{field} must be non-empty text")
        if isinstance(self.graph_revision, bool) or not isinstance(self.graph_revision, int) or self.graph_revision < 0:
            raise CooperativeMarketError("graph_revision must be a non-negative integer")
        object.__setattr__(self, "checked_at", _instant(self.checked_at, "checked_at"))
        if not isinstance(self.consortium_validation, TemporaryConsortiumValidation):
            raise CooperativeMarketError("consortium validation receipt has an invalid type")
        if not isinstance(self.resource_validation, ProductionGraphResourceValidation):
            raise CooperativeMarketError("resource validation receipt has an invalid type")
        if not isinstance(self.verified_evidence_refs, (set, frozenset)):
            raise CooperativeMarketError("verified evidence references must be a set")
        if any(not isinstance(ref, str) or not ref.strip() for ref in self.verified_evidence_refs):
            raise CooperativeMarketError("verified evidence references must be non-empty text")
        object.__setattr__(self, "verified_evidence_refs", frozenset(
            ref.strip() for ref in self.verified_evidence_refs
        ))
        if (self.consortium_validation.plan_id != self.plan_id
                or self.consortium_validation.agreement_id != self.agreement_id
                or self.consortium_validation.production_order_id != self.production_order_id
                or self.consortium_validation.graph_id != self.graph_id
                or self.consortium_validation.graph_revision != self.graph_revision):
            raise CooperativeMarketError("preflight receipt contains mismatched consortium bindings")
        if (self.resource_validation.graph_id != self.graph_id
                or self.resource_validation.graph_revision != self.graph_revision):
            raise CooperativeMarketError("preflight receipt contains mismatched resource graph bindings")


def validate_production_execution_preflight(
    *,
    plan: TemporaryProductionConsortium,
    agreement: CooperationAgreement,
    order: ProductionOrder,
    graph: ProductionGraph,
    claims_by_requirement: Mapping[str, tuple[ResourceClaim, ...]],
    snapshots: Mapping[str, CapacitySnapshot],
    organizations: Mapping[str, EconomicOrganization],
    verified_evidence_refs: frozenset[str],
    at: datetime,
    max_snapshot_age: timedelta = timedelta(minutes=15),
) -> ProductionExecutionPreflightReceipt:
    """Compose structural checks over one exact plan/order/graph revision.

    All resolver inputs must be obtained from authoritative services by the
    caller. The receipt is valid only for the checked snapshot/time; it must
    not be reused as proof that capacity remains available or has been booked.
    """
    instant = _instant(at, "at")
    if not isinstance(plan, TemporaryProductionConsortium):
        raise CooperativeMarketError("plan must be a TemporaryProductionConsortium")
    if not isinstance(agreement, CooperationAgreement):
        raise CooperativeMarketError("agreement must be a canonical CooperationAgreement")
    if not isinstance(order, ProductionOrder):
        raise CooperativeMarketError("order must be a canonical ProductionOrder")
    if not isinstance(graph, ProductionGraph):
        raise CooperativeMarketError("graph must be a ProductionGraph")
    if not isinstance(organizations, Mapping):
        raise CooperativeMarketError("organizations must come from a canonical resolver")
    if not isinstance(snapshots, Mapping):
        raise CooperativeMarketError("capacity snapshots must come from a canonical resolver")
    if not isinstance(claims_by_requirement, Mapping):
        raise CooperativeMarketError("resource requirements must come from a canonical resolver")
    if not isinstance(verified_evidence_refs, (set, frozenset)):
        raise CooperativeMarketError("verified evidence must come from a canonical resolver")

    consortium = validate_temporary_production_consortium(
        plan,
        agreement=agreement,
        order=order,
        graph=graph,
        organizations=organizations,
        verified_evidence_refs=verified_evidence_refs,
    )
    resources = validate_production_graph_resources(
        graph,
        claims_by_requirement=claims_by_requirement,
        snapshots=snapshots,
        organizations=organizations,
        verified_evidence_refs=verified_evidence_refs,
        at=instant,
        max_snapshot_age=max_snapshot_age,
    )
    return ProductionExecutionPreflightReceipt(
        plan_id=plan.plan_id,
        agreement_id=agreement.agreement_id,
        production_order_id=order.order_id,
        graph_id=graph.graph_id,
        graph_revision=graph.revision,
        checked_at=instant,
        consortium_validation=consortium,
        resource_validation=resources,
        verified_evidence_refs=frozenset(verified_evidence_refs),
    )
