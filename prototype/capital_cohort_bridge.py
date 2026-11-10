"""Explicit B8.1 cohort-to-SCCE capital-service adapter.

The SCCE engine currently consumes CellState.capital as a dimensionless
productive-capacity multiplier. This module derives that multiplier from
physical asset cohorts and a declared per-cell baseline service flow.

It deliberately does not infer asset counts, ownership or baseline services
from the engine's scalar capital field. Call apply_capital_cohorts before each
model period whose production should use the cohort-derived service index.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
from typing import Mapping, Sequence


class CapitalBridgeError(ValueError):
    """Invalid cohort state or an unsafe mapping into the SCCE engine."""


# B8.1 active operating states. "retired" is a terminal audit state, not an
# active operating state; it is retained only to preserve lifecycle provenance.
NON_RETIRED_STATES = {
    "operating", "reserve", "diagnostics", "repair", "remanufacturing", "storage"
}
COHORT_STATES = NON_RETIRED_STATES | {"retired"}
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
class CohortEvent:
    event_id: str
    cohort_id: str
    event_type: str
    quantity: float
    from_status: str
    to_status: str | None = None
    reason: str = ""


@dataclass(frozen=True)
class CohortPeriodResult:
    period: int
    opening_physical_units: float
    additions: float
    final_retirements: float
    physical_losses: float
    closing_physical_units: float
    closing_cohorts: tuple[CapitalCohort, ...]
    events: tuple[CohortEvent, ...]


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
            or cohort.operating_status not in COHORT_STATES):
        raise CapitalBridgeError("unknown cohort lifecycle state")
    _factor(cohort.availability, "availability")
    _factor(cohort.utilization, "utilization")
    _factor(cohort.service_quality, "service_quality")
    if (not isinstance(cohort.retirement_reason, str)
            or cohort.retirement_reason not in RETIREMENT_REASONS):
        raise CapitalBridgeError("unknown retirement reason")
    if cohort.operating_status == "retired":
        if cohort.retirement_reason == "none":
            raise CapitalBridgeError("retired cohort requires an explicit retirement reason")
    elif cohort.retirement_reason != "none":
        raise CapitalBridgeError("active cohort cannot carry a final retirement reason")


def advance_cohort_period(
    opening_cohorts: Sequence[CapitalCohort],
    events: Sequence[CohortEvent],
    additions: Sequence[CapitalCohort],
    period: int,
) -> CohortPeriodResult:
    """Apply identity-preserving asset events and advance cohort ages once.

    Partial state transitions/retirements split a cohort into a deterministic
    event-derived child ID. Physical loss removes quantity; final retirement
    remains as a retired record. Repair/reserve/storage transitions preserve
    physical quantity and vintage. New additions enter at age zero.
    """
    if not isinstance(period, int) or isinstance(period, bool) or period < 0:
        raise CapitalBridgeError("period must be a non-negative integer")
    if not isinstance(opening_cohorts, tuple) or not isinstance(events, tuple) or not isinstance(additions, tuple):
        raise CapitalBridgeError("opening cohorts, events and additions must be immutable tuples")

    records = {}
    for cohort in opening_cohorts:
        validate_cohort(cohort)
        if cohort.cohort_id in records:
            raise CapitalBridgeError(f"duplicate opening cohort ID: {cohort.cohort_id}")
        records[cohort.cohort_id] = cohort

    used_cohort_ids = set(records)
    opening_units = sum(
        float(row.quantity) for row in records.values()
        if row.operating_status != "retired"
    )
    if not math.isfinite(opening_units):
        raise CapitalBridgeError("opening physical cohort stock is non-finite")
    seen_event_ids = set()
    retired_quantity = 0.0
    lost_quantity = 0.0

    for event in events:
        if not isinstance(event, CohortEvent):
            raise CapitalBridgeError("cohort events must be CohortEvent values")
        if (not isinstance(event.event_id, str) or not event.event_id.strip()
                or not isinstance(event.cohort_id, str) or not event.cohort_id.strip()):
            raise CapitalBridgeError("event and cohort IDs must be non-empty strings")
        if event.event_id in seen_event_ids:
            raise CapitalBridgeError(f"duplicate cohort event ID: {event.event_id}")
        if not isinstance(event.event_type, str):
            raise CapitalBridgeError("cohort event type must be a string")
        seen_event_ids.add(event.event_id)
        if event.cohort_id not in records:
            raise CapitalBridgeError(f"event references unknown cohort: {event.cohort_id}")
        source = records[event.cohort_id]
        if source.operating_status == "retired":
            raise CapitalBridgeError("terminally retired cohort cannot receive further events")
        if event.from_status != source.operating_status:
            raise CapitalBridgeError("event source state does not match current cohort state")
        quantity = _finite_nonnegative(event.quantity, "event quantity")
        if quantity <= 0 or quantity > float(source.quantity):
            raise CapitalBridgeError("event quantity must be positive and not exceed cohort quantity")

        if event.event_type == "state_transition":
            if (not isinstance(event.to_status, str)
                    or event.to_status not in NON_RETIRED_STATES
                    or event.to_status == source.operating_status
                    or event.reason != ""):
                raise CapitalBridgeError("invalid non-retirement state transition")
            retirement_reason = "none"
        elif event.event_type == "final_retirement":
            if (event.to_status != "retired"
                    or not isinstance(event.reason, str)
                    or event.reason not in RETIREMENT_REASONS - {"none"}):
                raise CapitalBridgeError("final retirement requires retired state and explicit reason")
            retirement_reason = event.reason
            retired_quantity += quantity
        elif event.event_type == "physical_loss":
            if (event.to_status is not None
                    or not isinstance(event.reason, str)
                    or event.reason not in {"accident", "catastrophe", "disaster", "other"}):
                raise CapitalBridgeError("physical loss requires an explicit loss reason and no destination")
            lost_quantity += quantity
            remaining = float(source.quantity) - quantity
            if remaining <= 0:
                del records[source.cohort_id]
            else:
                records[source.cohort_id] = replace(source, quantity=remaining)
            continue
        else:
            raise CapitalBridgeError(f"unknown cohort event type: {event.event_type}")

        remaining = float(source.quantity) - quantity
        if remaining > 0:
            records[source.cohort_id] = replace(source, quantity=remaining)
            child_id = f"{source.cohort_id}::event::{event.event_id}"
            if child_id in used_cohort_ids:
                raise CapitalBridgeError(f"derived cohort ID collision: {child_id}")
            used_cohort_ids.add(child_id)
            records[child_id] = replace(
                source, cohort_id=child_id, quantity=quantity,
                operating_status=event.to_status,
                retirement_reason=retirement_reason)
        else:
            records[source.cohort_id] = replace(
                source, quantity=quantity, operating_status=event.to_status,
                retirement_reason=retirement_reason)

    addition_ids = set()
    addition_quantity = 0.0
    for cohort in additions:
        validate_cohort(cohort)
        if cohort.cohort_id in used_cohort_ids or cohort.cohort_id in addition_ids:
            raise CapitalBridgeError(f"duplicate addition cohort ID: {cohort.cohort_id}")
        if cohort.vintage != period or cohort.age != 0:
            raise CapitalBridgeError("new additions must use current-period vintage and age zero")
        if cohort.operating_status == "retired":
            raise CapitalBridgeError("new additions cannot enter already retired")
        addition_ids.add(cohort.cohort_id)
        used_cohort_ids.add(cohort.cohort_id)
        addition_quantity += float(cohort.quantity)
        records[cohort.cohort_id] = cohort

    # Age each surviving opening cohort and any split child exactly once;
    # additions are already at age zero and must not age in their entry period.
    for cohort_id in tuple(records):
        if (cohort_id not in addition_ids
                and records[cohort_id].operating_status != "retired"):
            records[cohort_id] = replace(records[cohort_id], age=records[cohort_id].age + 1)

    closing = tuple(sorted(records.values(), key=lambda row: row.cohort_id))
    closing_units = sum(
        float(row.quantity) for row in closing
        if row.operating_status != "retired"
    )
    expected = opening_units + addition_quantity - retired_quantity - lost_quantity
    if not math.isfinite(closing_units) or not math.isfinite(expected):
        raise CapitalBridgeError("closing or expected physical cohort stock is non-finite")
    if not math.isclose(closing_units, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise CapitalBridgeError(
            f"physical cohort stock-flow mismatch: closing={closing_units}, expected={expected}")
    return CohortPeriodResult(
        period, opening_units, addition_quantity, retired_quantity, lost_quantity,
        closing_units, closing, events)


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
        # Retired records remain as terminal audit tombstones, but do not
        # contribute to current physical stock or capital services.
        if cohort.operating_status != "retired":
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
