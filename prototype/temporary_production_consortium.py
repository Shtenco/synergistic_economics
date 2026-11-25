"""Temporary Production Consortium: scoped composition over canonical agreements.

This module does not create legal entities or agreements. It validates a
time-bounded production execution plan against an existing CooperationAgreement,
ProductionOrder, ProductionGraph and canonical organization/evidence resolvers.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Mapping

from cellular_cooperative_market import (
    CooperationAgreement,
    CooperativeMarketError,
    EconomicOrganization,
    validate_agreement,
)
from cooperative_production_network import ProductionOrder
from production_graph_engine import (
    ProductionGraph,
    ProductionGraphValidation,
    validate_production_graph,
)


def _text(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CooperativeMarketError(f"{field} must be non-empty text")
    return value.strip()


def _instant(value: datetime, field: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise CooperativeMarketError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True)
class ConsortiumAssignment:
    """One agreement participant's scoped role in a temporary production plan."""

    organization_id: str
    role: str
    node_ids: frozenset[str]
    commitment_ref: str
    authority_ref: str
    scope_ref: str

    def __post_init__(self):
        for field in ("organization_id", "commitment_ref", "authority_ref", "scope_ref"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if not isinstance(self.role, str) or self.role not in {"producer", "resource_provider", "coordinator"}:
            raise CooperativeMarketError("unsupported temporary consortium assignment role")
        if not isinstance(self.node_ids, (set, frozenset)):
            raise CooperativeMarketError("assignment node_ids must be a set of graph node references")
        if any(not isinstance(x, str) or not x.strip() for x in self.node_ids):
            raise CooperativeMarketError("assignment node references must be non-empty")
        object.__setattr__(self, "node_ids", frozenset(x.strip() for x in self.node_ids))
        if self.role == "producer" and not self.node_ids:
            raise CooperativeMarketError("producer assignment must cover at least one production graph node")
        if self.role != "producer" and self.node_ids:
            raise CooperativeMarketError("only producer assignments may claim execution graph nodes")


@dataclass(frozen=True)
class TemporaryProductionConsortium:
    plan_id: str
    agreement_id: str
    agreement_ref: str
    production_order_id: str
    graph_id: str
    graph_revision: int
    effective_from: datetime
    effective_to: datetime
    assignments: tuple[ConsortiumAssignment, ...]
    evidence_refs: frozenset[str]

    def __post_init__(self):
        for field in ("plan_id", "agreement_id", "agreement_ref",
                      "production_order_id", "graph_id"):
            object.__setattr__(self, field, _text(getattr(self, field), field))
        if isinstance(self.graph_revision, bool) or not isinstance(self.graph_revision, int) or self.graph_revision < 0:
            raise CooperativeMarketError("graph_revision must be a non-negative integer")
        if _instant(self.effective_to, "effective_to") <= _instant(self.effective_from, "effective_from"):
            raise CooperativeMarketError("temporary consortium interval must be positive")
        if not isinstance(self.assignments, tuple) or len(self.assignments) < 2 or any(
            not isinstance(a, ConsortiumAssignment) for a in self.assignments
        ):
            raise CooperativeMarketError("temporary production consortium requires at least two valid assignments")
        if not isinstance(self.evidence_refs, (set, frozenset)) or any(
            not isinstance(x, str) or not x.strip() for x in self.evidence_refs
        ):
            raise CooperativeMarketError("plan evidence references must be a set of non-empty references")
        object.__setattr__(self, "evidence_refs", frozenset(x.strip() for x in self.evidence_refs))
        ids = [a.organization_id for a in self.assignments]
        if len(ids) != len(set(ids)):
            raise CooperativeMarketError("organization may have only one assignment per temporary consortium plan")


@dataclass(frozen=True)
class TemporaryConsortiumValidation:
    plan_id: str
    agreement_id: str
    production_order_id: str
    graph_id: str
    graph_revision: int
    producer_organization_ids: tuple[str, ...]
    supporting_organization_ids: tuple[str, ...]
    node_assignments: tuple[tuple[str, str], ...]


def validate_temporary_production_consortium(
    plan: TemporaryProductionConsortium,
    *,
    agreement: CooperationAgreement,
    order: ProductionOrder,
    graph: ProductionGraph,
    organizations: Mapping[str, EconomicOrganization],
    verified_evidence_refs: frozenset[str],
) -> TemporaryConsortiumValidation:
    """Validate exact participant, order, graph, scope and time-window bindings.

    A successful result is a structural validation only. It does not create or
    amend the underlying agreement, reserve resources, authorize employment,
    accept deliverables, allocate liability or settle participant claims.
    """
    if not isinstance(plan, TemporaryProductionConsortium):
        raise CooperativeMarketError("plan must be a TemporaryProductionConsortium value")
    if not isinstance(agreement, CooperationAgreement):
        raise CooperativeMarketError("agreement must be a canonical CooperationAgreement value")
    if not isinstance(order, ProductionOrder):
        raise CooperativeMarketError("order must be a canonical ProductionOrder value")
    if not isinstance(graph, ProductionGraph):
        raise CooperativeMarketError("graph must be a ProductionGraph value")
    if not isinstance(organizations, Mapping):
        raise CooperativeMarketError("organizations must come from a canonical resolver")
    if not isinstance(verified_evidence_refs, (set, frozenset)):
        raise CooperativeMarketError("verified evidence must come from a canonical resolver")
    if any(not isinstance(x, str) or not x.strip() for x in verified_evidence_refs):
        raise CooperativeMarketError("verified evidence references must be non-empty")

    if plan.agreement_id != agreement.agreement_id or plan.agreement_ref != agreement.agreement_ref:
        raise CooperativeMarketError("temporary plan is not bound to the exact cooperation agreement")
    if plan.production_order_id != order.order_id:
        raise CooperativeMarketError("temporary plan is not bound to the exact production order")
    if plan.graph_id != graph.graph_id or plan.graph_revision != graph.revision:
        raise CooperativeMarketError("temporary plan is not bound to the exact production graph revision")

    if any(not isinstance(organizations.get(p.organization_id), EconomicOrganization)
           for p in agreement.participants):
        raise CooperativeMarketError("agreement participant resolver returned an invalid organization")
    validate_agreement(agreement, organizations)
    plan_start, plan_end = _instant(plan.effective_from, "effective_from"), _instant(plan.effective_to, "effective_to")
    agreement_start = _instant(agreement.effective_from, "agreement.effective_from")
    if plan_start < agreement_start:
        raise CooperativeMarketError("temporary plan starts before the cooperation agreement")
    if agreement.effective_to is not None and plan_end > _instant(agreement.effective_to, "agreement.effective_to"):
        raise CooperativeMarketError("temporary plan extends beyond the cooperation agreement")
    if plan_start < _instant(order.delivery_from, "order.delivery_from") or plan_end > _instant(order.delivery_to, "order.delivery_to"):
        raise CooperativeMarketError("temporary plan falls outside the production order delivery window")

    agreement_participants = {p.organization_id: p for p in agreement.participants}
    assignments = {a.organization_id: a for a in plan.assignments}
    if set(assignments) != set(agreement_participants):
        raise CooperativeMarketError("temporary plan assignments must cover exactly the agreement participants")

    required_evidence = set(plan.evidence_refs) | {agreement.agreement_ref}
    for organization_id, assignment in assignments.items():
        participant = agreement_participants[organization_id]
        if (assignment.commitment_ref != participant.commitment_ref
                or assignment.authority_ref != participant.authority_ref):
            raise CooperativeMarketError("assignment commitment or authority differs from the agreement participant record")
        required_evidence.update({
            assignment.commitment_ref, assignment.authority_ref, assignment.scope_ref,
        })
    if not required_evidence.issubset(verified_evidence_refs):
        raise CooperativeMarketError("temporary consortium agreement, commitment, authority, scope or plan evidence is unverified")

    graph_validation: ProductionGraphValidation = validate_production_graph(
        graph, organizations=organizations,
        verified_evidence_refs=verified_evidence_refs,
    )
    graph_nodes = {node.node_id: node for node in graph.nodes}
    assigned_nodes: dict[str, str] = {}
    for organization_id, assignment in assignments.items():
        if assignment.role != "producer":
            continue
        for node_id in assignment.node_ids:
            if node_id not in graph_nodes:
                raise CooperativeMarketError("consortium assignment references an unknown production graph node")
            if node_id in assigned_nodes:
                raise CooperativeMarketError("production graph node is assigned to multiple consortium participants")
            if graph_nodes[node_id].executor_organization_id != organization_id:
                raise CooperativeMarketError("graph node executor does not match its consortium producer assignment")
            assigned_nodes[node_id] = organization_id

    if set(assigned_nodes) != set(graph_nodes):
        raise CooperativeMarketError("every production graph node must be assigned to exactly one consortium producer")

    producer_ids = tuple(sorted(
        organization_id for organization_id, assignment in assignments.items()
        if assignment.role == "producer"
    ))
    support_ids = tuple(sorted(
        organization_id for organization_id, assignment in assignments.items()
        if assignment.role != "producer"
    ))
    return TemporaryConsortiumValidation(
        plan.plan_id, agreement.agreement_id, order.order_id, graph.graph_id,
        graph_validation.revision, producer_ids, support_ids,
        tuple(sorted(assigned_nodes.items())),
    )
