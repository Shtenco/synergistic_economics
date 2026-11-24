"""SYNERGY Production Graph Engine: dependency and responsibility validation.

This module validates a proposed production dependency graph. It does not
schedule work, reserve capacity, authorize labour, form contracts, or attest
that physical inputs/outputs exist. Those remain canonical authority duties.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from cellular_cooperative_market import CooperativeMarketError, EconomicOrganization


def _ref(value: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CooperativeMarketError(f"{field} must be non-empty text")
    return value.strip()


@dataclass(frozen=True)
class ProductionGraphNode:
    node_id: str
    executor_organization_id: str
    input_refs: frozenset[str]
    output_refs: frozenset[str]
    predecessor_ids: frozenset[str]
    acceptance_criteria_ref: str
    work_scope_ref: str
    production_mandate_ref: str | None = None
    work_package_ref: str | None = None

    def __post_init__(self):
        for field in ("node_id", "executor_organization_id", "acceptance_criteria_ref", "work_scope_ref"):
            _ref(getattr(self, field), field)
        for field in ("input_refs", "output_refs", "predecessor_ids"):
            values = getattr(self, field)
            if not isinstance(values, (set, frozenset)) or any(not isinstance(x, str) or not x.strip() for x in values):
                raise CooperativeMarketError(f"{field} must be a set of non-empty references")
        if not self.output_refs:
            raise CooperativeMarketError("each production node must declare at least one output")
        if self.production_mandate_ref is not None:
            _ref(self.production_mandate_ref, "production_mandate_ref")
        if self.work_package_ref is not None:
            _ref(self.work_package_ref, "work_package_ref")


@dataclass(frozen=True)
class ProductionGraph:
    graph_id: str
    revision: int
    nodes: tuple[ProductionGraphNode, ...]
    external_input_refs: frozenset[str]
    evidence_refs: frozenset[str]

    def __post_init__(self):
        _ref(self.graph_id, "graph_id")
        if isinstance(self.revision, bool) or not isinstance(self.revision, int) or self.revision < 0:
            raise CooperativeMarketError("graph revision must be a non-negative integer")
        if not isinstance(self.nodes, tuple) or not self.nodes:
            raise CooperativeMarketError("production graph must contain a non-empty tuple of nodes")
        for field in ("external_input_refs", "evidence_refs"):
            values = getattr(self, field)
            if not isinstance(values, (set, frozenset)) or any(not isinstance(x, str) or not x.strip() for x in values):
                raise CooperativeMarketError(f"{field} must be a set of non-empty references")


@dataclass(frozen=True)
class ProductionGraphValidation:
    graph_id: str
    revision: int
    topological_order: tuple[str, ...]
    node_count: int
    organization_ids: frozenset[str]
    output_producers: tuple[tuple[str, str], ...]


def validate_production_graph(
    graph: ProductionGraph,
    *,
    organizations: Mapping[str, EconomicOrganization],
    verified_evidence_refs: frozenset[str],
) -> ProductionGraphValidation:
    """Validate DAG structure, unique provenance, executor eligibility and evidence.

    Evidence authenticity, organization authority, scope authorization and physical
    feasibility must be checked by upstream canonical resolvers.
    """
    if not isinstance(verified_evidence_refs, (set, frozenset)):
        raise CooperativeMarketError("verified evidence must be a resolver-produced set")
    if any(not isinstance(x, str) or not x.strip() for x in verified_evidence_refs):
        raise CooperativeMarketError("verified evidence references must be non-empty strings")
    node_map: dict[str, ProductionGraphNode] = {}
    producer_by_output: dict[str, str] = {}
    for node in graph.nodes:
        if node.node_id in node_map:
            raise CooperativeMarketError("duplicate production graph node ID")
        node_map[node.node_id] = node
        for output in node.output_refs:
            if output in producer_by_output or output in graph.external_input_refs:
                raise CooperativeMarketError("ambiguous or duplicate output provenance")
            producer_by_output[output] = node.node_id

    if set(graph.external_input_refs) & set(producer_by_output):
        raise CooperativeMarketError("external input cannot also be produced inside the graph")

    inferred_predecessors: dict[str, set[str]] = {node_id: set() for node_id in node_map}
    for node in graph.nodes:
        org = organizations.get(node.executor_organization_id)
        if org is None or org.status != "active":
            raise CooperativeMarketError("production node executor is missing or inactive")
        if "artel" in org.coordination_roles and (not node.production_mandate_ref or not node.work_package_ref):
            raise CooperativeMarketError("artel production node requires mandate and Artel Engine work-package references")
        if node.node_id in node.predecessor_ids:
            raise CooperativeMarketError("production node cannot depend on itself")
        for predecessor_id in node.predecessor_ids:
            if predecessor_id not in node_map:
                raise CooperativeMarketError("production node references an unknown predecessor")
        for input_ref in node.input_refs:
            producer_id = producer_by_output.get(input_ref)
            if producer_id is None:
                if input_ref not in graph.external_input_refs:
                    raise CooperativeMarketError("production input has no declared upstream producer or external source")
            else:
                inferred_predecessors[node.node_id].add(producer_id)
        if inferred_predecessors[node.node_id] != set(node.predecessor_ids):
            raise CooperativeMarketError("declared predecessors do not match input/output provenance")
        required = {node.acceptance_criteria_ref, node.work_scope_ref}
        if node.production_mandate_ref:
            required.add(node.production_mandate_ref)
        if node.work_package_ref:
            required.add(node.work_package_ref)
        if not required.issubset(verified_evidence_refs):
            raise CooperativeMarketError("production node has unverified scope, acceptance or mandate evidence")

    indegree = {node_id: len(predecessors) for node_id, predecessors in inferred_predecessors.items()}
    successors: dict[str, set[str]] = {node_id: set() for node_id in node_map}
    for node_id, predecessors in inferred_predecessors.items():
        for predecessor_id in predecessors:
            successors[predecessor_id].add(node_id)
    ready = sorted(node_id for node_id, degree in indegree.items() if degree == 0)
    ordered: list[str] = []
    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for successor in sorted(successors[current]):
            indegree[successor] -= 1
            if indegree[successor] == 0:
                ready.append(successor)
                ready.sort()
    if len(ordered) != len(node_map):
        raise CooperativeMarketError("production dependency graph contains a cycle")

    return ProductionGraphValidation(
        graph.graph_id, graph.revision, tuple(ordered), len(node_map),
        frozenset(node.executor_organization_id for node in graph.nodes),
        tuple(sorted(producer_by_output.items())),
    )
