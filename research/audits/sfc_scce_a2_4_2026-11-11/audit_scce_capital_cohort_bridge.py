"""Exercise the B8.1 cohort service adapter against the actual SCCE engine.

This is a synthetic integration fixture. It proves that explicit cohort
service flows can be normalized to a declared baseline and applied to the
engine's existing CellState.capital multiplier before a real production step.
It does not claim empirical asset data or replace the scalar default path.
"""
from dataclasses import replace
import math
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
PROTOTYPE = ROOT / "prototype"
sys.path.insert(0, str(PROTOTYPE))

from capital_cohort_bridge import (  # noqa: E402
    CapitalBridgeError,
    CapitalCohort,
    aggregate_capital_services,
    apply_capital_cohorts,
)
from scc_dynamic_economy import (  # noqa: E402
    CellLocalView,
    DynamicCellularEconomy,
    propose_cellular_output,
)


def build_cohorts(model):
    rows = []
    for cell_id in model.cells:
        if cell_id == "cell-4":
            rows.extend((
                CapitalCohort(
                    "machine-cell-4-operating", cell_id, "machine",
                    2020, 6, 8, 10, "operating", .9, .8, .95),
                CapitalCohort(
                    "machine-cell-4-repair", cell_id, "machine",
                    2020, 6, 2, 10, "repair", .9, .8, .95),
            ))
        elif cell_id == "cell-5":
            rows.append(CapitalCohort(
                "machine-cell-5", cell_id, "machine",
                2020, 6, 10, 10, "operating", .9, .4, .95))
        else:
            rows.append(CapitalCohort(
                f"machine-{cell_id}", cell_id, "machine",
                2020, 6, 10, 10, "operating", .9, .8, .95))
    return tuple(rows)


def close(actual, expected, label):
    if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-12):
        raise AssertionError(f"{label}: {actual} != {expected}")


def main():
    model = DynamicCellularEconomy(
        policy="cellular", seed=23, shock="compound", cellular_hops=2)
    cohorts = build_cohorts(model)
    baseline = {cell_id: 68.4 for cell_id in model.cells}

    snapshots = apply_capital_cohorts(model, cohorts, baseline)
    by_cell = {row.cell_id: row for row in snapshots}
    if set(by_cell) != set(model.cells):
        raise AssertionError("cohort bridge did not cover every SCCE cell")

    # A repair queue preserves physical units but contributes no current service.
    close(by_cell["cell-4"].physical_units, 10.0, "cell-4 physical units")
    close(by_cell["cell-4"].operating_units, 8.0, "cell-4 operating units")
    close(by_cell["cell-4"].service_flow, 54.72, "cell-4 service flow")
    close(by_cell["cell-4"].capital_multiplier, .8, "cell-4 capital multiplier")

    # Lower utilization reduces services without destroying physical assets.
    close(by_cell["cell-5"].physical_units, 10.0, "cell-5 physical units")
    close(by_cell["cell-5"].service_flow, 34.2, "cell-5 service flow")
    close(by_cell["cell-5"].capital_multiplier, .5, "cell-5 capital multiplier")

    for cell_id in model.cells:
        close(model.cells[cell_id].capital,
              by_cell[cell_id].capital_multiplier,
              f"{cell_id} applied engine multiplier")

    # Verify the actual SCCE local production rule consumes the applied ratio.
    view = CellLocalView(
        cell_id="cell-5", output="logistics", inventory=0.0,
        local_final_need=100.0, previous_external_orders=0.0,
        safety_stock=0.0, capacity=100.0, labour_hours=100.0,
        productivity=1.0, capital=model.cells["cell-5"].capital,
        productivity_multiplier=1.0, neighbour_ids=(),
        tradeable_neighbour_ids=(), neighbour_input_demand=0.0)
    reduced_proposal = propose_cellular_output(view)
    full_proposal = propose_cellular_output(replace(view, capital=1.0))
    close(full_proposal, 100.0, "full-service proposal")
    close(reduced_proposal, 50.0, "half-service proposal")

    # Run a real engine period after the adapter has populated CellState.capital.
    result = model.step(1)
    if result.period != 1 or len(model.events) == 0 or not model.validate():
        raise AssertionError("SCCE did not complete a valid period after cohort mapping")
    production_events = [
        event for event in model.events if event["type"] == "production"
    ]
    if len(production_events) != len(model.cells):
        raise AssertionError("production event coverage changed after cohort mapping")

    # Fail closed and do not partially mutate the engine when one cell has no
    # operating service (the current SCCE engine rejects capital <= 0).
    untouched = DynamicCellularEconomy(
        policy="cellular", seed=23, shock="compound", cellular_hops=2)
    original = {cid: cell.capital for cid, cell in untouched.cells.items()}
    zero_service = tuple(
        replace(row, operating_status="retired", retirement_reason="planned")
        if row.cell_id == "cell-1" else row
        for row in cohorts
    )
    try:
        apply_capital_cohorts(untouched, zero_service, baseline)
    except CapitalBridgeError:
        pass
    else:
        raise AssertionError("zero operating service was silently mapped")
    if {cid: cell.capital for cid, cell in untouched.cells.items()} != original:
        raise AssertionError("failed cohort mapping partially mutated engine capital")

    # Malformed numeric and lifecycle fields are rejected explicitly.
    for malformed in (
        replace(cohorts[0], quantity=True),
        replace(cohorts[0], availability=float("nan")),
        replace(cohorts[0], retirement_reason="magically_retired"),
    ):
        try:
            aggregate_capital_services(tuple(model.cells), (malformed,), baseline)
        except CapitalBridgeError:
            pass
        else:
            raise AssertionError("malformed cohort numeric/lifecycle field accepted")

    # Duplicate identities and incomplete baselines are rejected.
    try:
        aggregate_capital_services(
            tuple(model.cells), cohorts + (cohorts[0],), baseline)
    except CapitalBridgeError:
        pass
    else:
        raise AssertionError("duplicate cohort identity accepted")
    try:
        aggregate_capital_services(
            tuple(model.cells), cohorts, {"cell-1": 68.4})
    except CapitalBridgeError:
        pass
    else:
        raise AssertionError("incomplete baseline map accepted")

    print("A2.4.2/B8.1 cohort-to-SCCE runtime adapter: PASS")
    print("physical units remain distinct from operating units and service flow")
    print("repair downtime reduces service, not physical stock; utilization scales service")
    print("service index maps atomically to CellState.capital before a real SCCE step")
    print("local production proposal responds proportionally to the applied capital multiplier")
    print("negative controls: zero service, duplicate cohort ID, incomplete baseline, boolean quantity, NaN factor and invalid retirement reason rejected")


if __name__ == "__main__":
    main()
