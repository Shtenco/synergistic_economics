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
    CohortEvent,
    advance_cohort_period,
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


def check_cohort_lifecycle(seed_cohorts):
    opening = next(row for row in seed_cohorts if row.cell_id == "cell-1")
    repair_event = CohortEvent(
        "repair-start-1", opening.cohort_id, "state_transition",
        2, "operating", "repair")
    repair_child = f"{opening.cohort_id}::event::repair-start-1"
    repair_complete = CohortEvent(
        "repair-complete-1", repair_child, "state_transition",
        1, "repair", "operating")
    retirement = CohortEvent(
        "retirement-1", opening.cohort_id, "final_retirement",
        1, "operating", "retired", "planned")
    physical_loss = CohortEvent(
        "loss-1", opening.cohort_id, "physical_loss",
        1, "operating", None, "accident")
    addition = CapitalCohort(
        "machine-cell-1-new-period-1", "cell-1", "machine",
        1, 0, 2, 10, "operating", .9, .8, .95)
    result = advance_cohort_period(
        (opening,),
        (repair_event, repair_complete, retirement, physical_loss),
        (addition,),
        period=1)
    close(result.opening_physical_units, 10.0, "opening physical units")
    close(result.additions, 2.0, "period additions")
    close(result.final_retirements, 1.0, "final retirements")
    close(result.physical_losses, 1.0, "physical losses")
    close(result.closing_physical_units, 10.0, "closing physical units")
    rows = {row.cohort_id: row for row in result.closing_cohorts}
    close(rows[opening.cohort_id].quantity, 6.0, "remaining original cohort")
    close(rows[opening.cohort_id].age, 7.0, "aged original cohort")
    close(rows[repair_child].quantity, 1.0, "remaining repair cohort")
    close(rows[repair_child].age, 7.0, "aged repair cohort")
    close(rows[addition.cohort_id].age, 0.0, "new cohort entry age")
    if rows[repair_child].operating_status != "repair":
        raise AssertionError("repair state was not retained after period transition")
    if not any(row.operating_status == "retired" and row.retirement_reason == "planned"
               for row in result.closing_cohorts):
        raise AssertionError("final retirement record/reason was not retained")

    # An overdrawn event must fail rather than silently clamp or destroy stock.
    try:
        advance_cohort_period(
            (opening,),
            (CohortEvent(
                "overdraw-1", opening.cohort_id, "state_transition",
                11, "operating", "repair"),),
            (),
            period=1)
    except CapitalBridgeError:
        pass
    else:
        raise AssertionError("overdrawn cohort transition accepted")
    return result


def main():
    model = DynamicCellularEconomy(
        policy="cellular", seed=23, shock="compound", cellular_hops=2)
    cohorts = build_cohorts(model)
    lifecycle = check_cohort_lifecycle(cohorts)
    if lifecycle.closing_physical_units != 10.0:
        raise AssertionError("cohort lifecycle stock-flow did not close")
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
        replace(row, operating_status="repair")
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

    # A partial final retirement creates an auditable terminal child record,
    # subtracts only the retired quantity from physical stock, and does not
    # age the retired record after its retirement event.
    opening = (CapitalCohort(
        "retire-source", "cell-1", "machine", 2020, 6, 10, 10,
        "operating", .9, .8, .95),)
    retirement = CohortEvent(
        "retire-event-1", "retire-source", "final_retirement",
        3, "operating", "retired", "planned")
    advanced = advance_cohort_period(opening, (retirement,), (), period=2026)
    close(advanced.opening_physical_units, 10.0, "retirement opening units")
    close(advanced.final_retirements, 3.0, "partial final retirement")
    close(advanced.closing_physical_units, 7.0, "retirement closing units")
    active = [x for x in advanced.closing_cohorts if x.operating_status != "retired"]
    retired = [x for x in advanced.closing_cohorts if x.operating_status == "retired"]
    if len(active) != 1 or len(retired) != 1:
        raise AssertionError("partial retirement did not preserve active and terminal cohorts")
    close(active[0].quantity, 7.0, "active residual quantity")
    close(retired[0].quantity, 3.0, "retired child quantity")
    if active[0].age != 7 or retired[0].age != 6:
        raise AssertionError("cohort ageing across retirement boundary is incorrect")
    if retired[0].retirement_reason != "planned":
        raise AssertionError("retirement reason was not preserved")

    # Retired tombstones are excluded from the physical/service aggregate.
    # A retired-only cell has zero current service and must fail closed rather
    # than being mapped to an epsilon multiplier.
    try:
        aggregate_capital_services(
            ("cell-1",),
            (replace(opening[0], operating_status="retired",
                     retirement_reason="planned"),),
            {"cell-1": 68.4})
    except CapitalBridgeError:
        pass
    else:
        raise AssertionError("retired-only cohort generated capital services")

    # A terminally retired cohort cannot be transitioned back into operation.
    try:
        advance_cohort_period(
            advanced.closing_cohorts,
            (CohortEvent("reactivate-1", retired[0].cohort_id,
                         "state_transition", 1, "retired", "operating"),),
            (), period=2027)
    except CapitalBridgeError:
        pass
    else:
        raise AssertionError("terminal retirement was reversible")

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

    # A malformed later target cell must not leave earlier cells mutated.
    class RejectingCell:
        def __init__(self):
            object.__setattr__(self, "capital", 1.0)

        def __setattr__(self, name, value):
            if name == "capital" and value != 1.0:
                raise RuntimeError("synthetic write rejection")
            object.__setattr__(self, name, value)

    class FakeModel:
        pass

    fake = FakeModel()
    first_cell = type("Cell", (), {})()
    first_cell.capital = 1.0
    fake.cells = {"a": first_cell, "b": RejectingCell()}
    fake_cohorts = (
        CapitalCohort("a-1", "a", "machine", 2020, 6, 10, 10,
                      "operating", .9, .8, .95),
        CapitalCohort("b-1", "b", "machine", 2020, 6, 10, 10,
                      "operating", .9, .8, .95),
    )
    try:
        apply_capital_cohorts(fake, fake_cohorts, {"a": 136.8, "b": 136.8})
    except CapitalBridgeError:
        pass
    else:
        raise AssertionError("write failure in later cell was accepted")
    close(fake.cells["a"].capital, 1.0, "rollback of first cell")
    close(fake.cells["b"].capital, 1.0, "unchanged rejecting cell")

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
    print("identity-preserving lifecycle: age, repair, partial retirement and physical-loss flows reconcile")
    print("physical units remain distinct from operating units and service flow")
    print("B8.1 active states and terminal retirement records are distinct; retired tombstones do not enter physical/service stock")
    print("repair downtime reduces service, not physical stock; utilization scales service")
    print("service index maps atomically to CellState.capital before a real SCCE step")
    print("negative control: later-cell write failure rolls back earlier capital updates")
    print("local production proposal responds proportionally to the applied capital multiplier")
    print("negative controls: zero service, terminal reactivation, duplicate cohort ID, incomplete baseline, boolean quantity, NaN factor and invalid retirement reason rejected")


if __name__ == "__main__":
    main()
