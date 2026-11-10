"""Explicit B8.1 cohort-to-SCCE capital-service adapter.

The SCCE engine currently consumes CellState.capital as a dimensionless
productive-capacity multiplier. This module derives that multiplier from
physical asset cohorts and a declared per-cell baseline service flow.

It deliberately does not infer asset counts, ownership or baseline services
from the engine's scalar capital field. Call apply_capital_cohorts before each
model period whose production should use the cohort-derived service index.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping, Sequence


class CapitalBridgeError(ValueError):
    """Invalid cohort state or an unsafe mapping into the SCCE engine."""


# Match the B8.1 active-cohort operating-state vocabulary exactly.
# Final retirement is a stock-removal event, not a persistent operating state.
OPERATING_STATES = {
    "operating", "reserve", "diagnostics", "repair", "remanufacturing", "storage"
}
RETIREMENT_REASONS = {"none", "planned", "failure", "obsolescence", "accident", "other"}


@dataclass(frozen=True)
class CapitalCohort:
    cohort_id: str
    cell_id: str
    asset_type: str
    vintage: int
    age: int
    quantity: float
    service_capacity_per_asset: float
    operating_status: str
    availability: float
    utilization: float
    service_quality: float
    retirement_reason: str = "none"


@dataclass(frozen=True)
class CellCapitalService:
    cell_id: str
    physical_units: float
    operating_units: float
    service_flow: float
    baseline_service_flow: float
    capital_multiplier: float


def _finite_nonnegative(value, field: str) -> float:
    if isinstance(value, bool):
        raise CapitalBridgeError(f"{field} must be numeric, not boolean")
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise CapitalBridgeError(f"{field} must be numeric") from exc
    if not math.isfinite(number) or number < 0:
        raise CapitalBridgeError(f"{field} must be finite and non-negative")
    return number


def _factor(value, field: str) -> float:
    number = _finite_nonnegative(value, field)
    if number > 1:
        raise CapitalBridgeError(f"{field} must be in [0,1]")
    return number


def validate_cohort(cohort: CapitalCohort) -> None:
    if not isinstance(cohort, CapitalCohort):
        raise CapitalBridgeError("all cohort records must be CapitalCohort values")
    if not all(isinstance(value, str) and value.strip() for value in (
            cohort.cohort_id, cohort.cell_id, cohort.asset_type)):
        raise CapitalBridgeError("cohort, cell and asset type identities must be non-empty strings")
    if (not isinstance(cohort.vintage, int) or isinstance(cohort.vintage, bool)
            or not isinstance(cohort.age, int) or isinstance(cohort.age, bool)
            or cohort.vintage < 0 or cohort.age < 0):
        raise CapitalBridgeError("vintage and age must be non-negative integer periods")
    _finite_nonnegative(cohort.quantity, "quantity")
    capacity = _finite_nonnegative(
        cohort.service_capacity_per_asset, "service_capacity_per_asset")
    if capacity <= 0:
        raise CapitalBridgeError("service capacity per asset must be positive")
    if (not isinstance(cohort.operating_status, str)
            or cohort.operating_status not in OPERATING_STATES):
        raise CapitalBridgeError("unknown operating status")
    _factor(cohort.availability, "availability")
    _factor(cohort.utilization, "utilization")
    _factor(cohort.service_quality, "service_quality")
    if (not isinstance(cohort.retirement_reason, str)
            or cohort.retirement_reason not in RETIREMENT_REASONS):
        raise CapitalBridgeError("unknown retirement reason")
    if cohort.retirement_reason != "none":
        raise CapitalBridgeError(
            "active cohort records must use retirement_reason='none'; "
            "final retirement removes quantity through a separate transition event")


def aggregate_capital_services(
    cell_ids: Sequence[str],
    cohorts: Sequence[CapitalCohort],
    baseline_services: Mapping[str, float],
) -> tuple[CellCapitalService, ...]:
    """Aggregate physical units and service flows, then normalize by baseline."""
    ids = tuple(cell_ids)
    if (not ids or any(not isinstance(x, str) or not x.strip() for x in ids)
            or len(ids) != len(set(ids))):
        raise CapitalBridgeError("cell IDs must be non-empty strings and unique")
    known = set(ids)
    if set(baseline_services) != known:
        raise CapitalBridgeError("baseline service map must cover exactly the model cells")

    physical = {cid: 0.0 for cid in ids}
    operating = {cid: 0.0 for cid in ids}
    services = {cid: 0.0 for cid in ids}
    seen = set()

    for cohort in cohorts:
        validate_cohort(cohort)
        if cohort.cohort_id in seen:
            raise CapitalBridgeError(f"duplicate cohort ID: {cohort.cohort_id}")
        seen.add(cohort.cohort_id)
        if cohort.cell_id not in known:
            raise CapitalBridgeError(f"cohort references unknown cell: {cohort.cell_id}")

        quantity = float(cohort.quantity)
        # Every record in this adapter is an extant physical cohort. A final
        # retirement is represented by removing quantity in the B8.1 state
        # transition and recording its retirement event, not by retaining a
        # pseudo-state that is absent from the canonical B8.1 state vocabulary.
        physical[cohort.cell_id] += quantity
        if cohort.operating_status == "operating":
            operating[cohort.cell_id] += quantity
            services[cohort.cell_id] += (
                quantity
                * float(cohort.service_capacity_per_asset)
                * float(cohort.availability)
                * float(cohort.utilization)
                * float(cohort.service_quality)
            )

    result = []
    for cid in ids:
        baseline = _finite_nonnegative(baseline_services[cid], f"{cid} baseline")
        if baseline <= 0:
            raise CapitalBridgeError(f"{cid} baseline service flow must be positive")
        service = services[cid]
        if not math.isfinite(service) or service <= 0:
            raise CapitalBridgeError(
                f"{cid} has no positive operating capital service; "
                "the current SCCE engine cannot represent a zero capital multiplier")
        multiplier = service / baseline
        if not math.isfinite(multiplier) or multiplier <= 0:
            raise CapitalBridgeError(f"{cid} produced an invalid capital multiplier")
        if not math.isfinite(physical[cid]) or not math.isfinite(operating[cid]):
            raise CapitalBridgeError(f"{cid} physical/operating unit aggregate is non-finite")
        result.append(CellCapitalService(
            cid, physical[cid], operating[cid], service, baseline, multiplier))
    return tuple(result)


def apply_capital_cohorts(
    model,
    cohorts: Sequence[CapitalCohort],
    baseline_services: Mapping[str, float],
) -> tuple[CellCapitalService, ...]:
    """Atomically map cohort service indices onto a live SCCE model instance.

    The function validates and computes every cell before mutating any
    CellState.capital. Existing callers that do not invoke this adapter retain
    the engine's original scalar-capital behaviour.
    """
    if not hasattr(model, "cells") or not isinstance(model.cells, dict):
        raise CapitalBridgeError("model must expose the SCCE cells mapping")
    snapshots = aggregate_capital_services(
        tuple(model.cells), cohorts, baseline_services)

    # Preflight every target before mutating the first one. In particular, a
    # malformed later cell must not leave earlier cells with new multipliers.
    targets = []
    for snapshot in snapshots:
        cell = model.cells[snapshot.cell_id]
        try:
            old_value = cell.capital
        except Exception as exc:
            raise CapitalBridgeError(
                f"{snapshot.cell_id} does not expose a readable capital field") from exc
        old_number = _finite_nonnegative(old_value, f"{snapshot.cell_id} existing capital")
        if not hasattr(cell, "__dict__") or "capital" not in vars(cell):
            raise CapitalBridgeError(
                f"{snapshot.cell_id} capital must be a writable instance field")
        targets.append((cell, old_value, snapshot.capital_multiplier, snapshot.cell_id))

    attempted = []
    try:
        for cell, old_value, new_value, cell_id in targets:
            attempted.append((cell, old_value, cell_id))
            cell.capital = new_value
    except Exception as exc:
        rollback_errors = []
        for cell, old_value, cell_id in reversed(attempted):
            try:
                cell.capital = old_value
            except Exception as rollback_exc:
                rollback_errors.append((cell_id, str(rollback_exc)))
        if rollback_errors:
            raise CapitalBridgeError(
                f"capital mapping failed and rollback was incomplete: {rollback_errors}") from exc
        raise CapitalBridgeError(
            "capital mapping failed; all attempted cell values were rolled back") from exc
    return snapshots
