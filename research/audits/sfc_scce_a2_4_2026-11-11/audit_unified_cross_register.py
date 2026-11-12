"""Synthetic cross-register integration fixture for one shared scenario identity.

This test composes the actual SCCE physical engine, B8.1 cohort bridge, B3
physical-flow endpoints, typed product valuation, labour/consent controls and
the atomic GOLD-2A financial projection. It proves scenario-level provenance
and each register's own closure; it does NOT claim a single cross-register
production transaction or empirical synergy.
"""
from contextlib import closing
from decimal import Decimal as D
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))
AUDIT_DIR = ROOT / "research" / "audits" / "sfc_scce_a2_4_2026-11-11"

from scc_dynamic_economy import DynamicCellularEconomy
from capital_cohort_bridge import (
    CapitalCohort, CohortEvent, advance_cohort_period,
    apply_capital_cohorts, initial_cohort_state,
)
from audit_physical_flow_register import PhysicalFlowRegister, pair
from audit_product_valuation_adapter import ProductSpec, PhysicalQuantity, UnitPrice, value_quantity
from audit_labour_consent import Interval, validate_time_budget, delivered_hours
from audit_financial_journal_adapter import _corpus_events
from entity_journal import EntityJournal
from financial_event_store import FinancialEventStore
from sfc_projection_registry import activate_sfc_projection
from sfc_projection_store import activate_control_openings, append_projected_group, verify_projection_replay


def main():
    scenario_id = "XREG-SCENARIO-2026-11-12-001"

    # 1) Actual seven-cell physical engine, driven by cohort-derived service.
    model = DynamicCellularEconomy(policy="cellular", seed=17)
    cohorts = []
    for cell_id in sorted(model.cells):
        cohorts.append(CapitalCohort(
            cohort_id=f"asset-{cell_id}-A", cell_id=cell_id,
            asset_type="productive_equipment", vintage=0, age=0, quantity=1.0,
            service_capacity_per_asset=1.0, operating_status="operating",
            availability=1.0, utilization=1.0, service_quality=1.0))
        if cell_id == "cell-4":
            cohorts.append(CapitalCohort(
                cohort_id="asset-cell-4-B", cell_id=cell_id,
                asset_type="productive_equipment", vintage=0, age=0, quantity=1.0,
                service_capacity_per_asset=1.0, operating_status="operating",
                availability=1.0, utilization=1.0, service_quality=1.0))
    opening_cohorts = tuple(cohorts)
    cohort_state = initial_cohort_state(opening_cohorts)
    capital_event_id = f"{scenario_id}::CAPITAL::001"
    cohort_event = CohortEvent(
        capital_event_id, "asset-cell-4-A", "state_transition", 1.0,
        "operating", "repair")
    cohort_result = advance_cohort_period(cohort_state, (cohort_event,), (), 1)
    baseline_services = {cell_id: (2.0 if cell_id == "cell-4" else 1.0)
                         for cell_id in model.cells}
    services = apply_capital_cohorts(model, cohort_result.closing_cohorts, baseline_services)
    service_by_cell = {row.cell_id: row for row in services}
    assert service_by_cell["cell-4"].physical_units == 2.0
    assert service_by_cell["cell-4"].operating_units == 1.0
    assert service_by_cell["cell-4"].capital_multiplier == 0.5
    assert model.cells["cell-4"].capital == 0.5
    assert all(model.cells[cell_id].capital == 1.0
               for cell_id in model.cells if cell_id != "cell-4")
    result = model.step(1)
    assert model.validate() is True
    assert result.period == 1 and model.periods[-1].period == 1
    model._record("cross_register_scenario_link",
                  {"scenario_id":scenario_id,"period":1},scenario_id)
    assert cohort_result.opening_physical_units == cohort_result.closing_physical_units

    # 2) Physical flow endpoint register and native-unit product valuation.
    physical = PhysicalFlowRegister()
    physical_flow_id = f"{scenario_id}::PHYSICAL::001"
    outflow, inflow = pair(
        physical_flow_id, "cell-2", "cell-4", "2.5",
        product="materials", grade="standard", unit="t",
        period="P1", flow_class="internal_transfer",
        origin_boundary="SCCE", destination_boundary="SCCE",
        event_time="2026-11-12T09:00:00",
        evidence_status="simulated", measurement_method="engine_event")
    physical.record(outflow, inflow)
    assert physical.flow_count == 1
    assert physical.consolidated_net(
        {"cell-2","cell-4"}, "materials","standard","P1") == D("0")

    product = ProductSpec("materials","standard","mass","t","stockable","period_flow")
    quantity = PhysicalQuantity("materials","standard",D("2.5"),"t","P1","SCCE")
    price = UnitPrice("materials","standard",D("4"),"t","LCU","P1",
                      "synthetic_basic_price",f"{scenario_id}::PRICE::001")
    valuation = value_quantity(product,quantity,price)
    assert valuation.quantity == D("2.5") and valuation.value == D("10")
    assert valuation.source_id == f"{scenario_id}::PRICE::001"
    assert valuation.native_unit == "t" and valuation.currency == "LCU"

    # 3) Labour/time/consent: planned and delivered hours remain distinct.
    allocated = validate_time_budget((
        Interval("paid_work",D("0"),D("40"),"paid"),
        Interval("care",D("40"),D("48"),"unpaid_care"),
        Interval("rest",D("48"),D("104"),"rest"),
    ))
    delivered = delivered_hours(8,7,6,5,"delivered",6)
    labour_event = {"event_id":f"{scenario_id}::LABOUR::001","scenario_id":scenario_id,
                    "period":1,"allocated_hours":allocated,
                    "delivered_hours":delivered,"consent_state":"delivered"}
    assert labour_event["delivered_hours"] <= labour_event["allocated_hours"]

    # 4) GOLD-2A financial journal + P2. One causation root links the durable
    # financial transaction group to the cross-register scenario envelope.
    registry, events = _corpus_events()
    corpus = json.loads((AUDIT_DIR / "SFC_GOLD_2A_CORPUS.json").read_text(encoding="utf-8"))
    opening = corpus["opening_snapshot"]
    with tempfile.TemporaryDirectory() as directory:
        store = FinancialEventStore(Path(directory)/"unified.sqlite3")
        assert activate_sfc_projection(
            store,opening["rows"],mapper_version=opening["mapper_version"],
            evidence_ref=opening["evidence_ref"])
        controls = (
            {"control_id":"impairment_allowance","entity_id":"bank-1","sector":"CB",
             "currency":"LCU","valuation_basis":"NOMINAL","period":0,"amount":"0",
             "evidence_ref":"GOLD2A:synthetic-opening-v1"},
            {"control_id":"writeoff_memorandum","entity_id":"bank-1","sector":"CB",
             "currency":"LCU","valuation_basis":"NOMINAL","period":0,"amount":"0",
             "evidence_ref":"GOLD2A:synthetic-opening-v1"},
        )
        assert activate_control_openings(
            store,controls,mapper_version="gold2a-controls@1",
            evidence_ref="GOLD2A:synthetic-opening-v1")
        assert append_projected_group(
            EntityJournal(registry),store,"GOLD2A-UNIFIED-CONTROL",events,
            causation_id=scenario_id)
        assert verify_projection_replay(store)
        group = store.get_group("GOLD2A-UNIFIED-CONTROL")
        assert group["causation_id"] == scenario_id
        with closing(store._connect()) as con:
            final = {r["instrument_id"]:D(r["closing_balance"]) for r in con.execute(
                "SELECT instrument_id,closing_balance FROM sfc_projection_positions WHERE period=4")}
            controls_final = {r["control_id"]:D(r["closing_balance"]) for r in con.execute(
                "SELECT control_id,closing_balance FROM sfc_control_positions WHERE period=4")}
            assert final == {"LOAN-001":D("60"),"DEP-001":D("76"),"INT-001":D("6")}
            assert controls_final == {"impairment_allowance":D("5"),"writeoff_memorandum":D("15")}

    # 5) Cross-register manifest: every subsystem is traceable to one scenario
    # root while preserving its own event identity, period and physical units.
    manifest = {
        "scenario_id":scenario_id,
        "physical_flow_id":outflow.flow_id,
        "capital_event_id":cohort_event.event_id,
        "labour_event_id":labour_event["event_id"],
        "valuation_source_id":valuation.source_id,
        "financial_causation_id":group["causation_id"],
        "scce_event_key":model.events[-1]["key"],
        "register_envelopes": (
            {"register":"scce","scenario_id":scenario_id,"event_id":model.events[-1]["key"]},
            {"register":"physical","scenario_id":scenario_id,"event_id":outflow.flow_id},
            {"register":"capital","scenario_id":scenario_id,"event_id":cohort_event.event_id},
            {"register":"labour","scenario_id":scenario_id,"event_id":labour_event["event_id"]},
            {"register":"product_valuation","scenario_id":scenario_id,"event_id":valuation.source_id},
            {"register":"financial","scenario_id":scenario_id,"event_id":group["group_id"]},
        ),
        "physical_period":outflow.period,
        "capital_period":cohort_result.period,
        "labour_period":labour_event["period"],
        "financial_event_periods":sorted({e["effective_period"] for e in group["events"]}),
        "physical_unit":valuation.native_unit,
        "financial_currency":valuation.currency,
    }
    envelopes = manifest["register_envelopes"]
    assert len(envelopes) == 6
    assert {row["scenario_id"] for row in envelopes} == {scenario_id}
    assert {row["event_id"] for row in envelopes} == {
        manifest["physical_flow_id"], manifest["capital_event_id"],
        manifest["labour_event_id"], manifest["valuation_source_id"],
        manifest["scce_event_key"], group["group_id"],
    }
    assert len({row["event_id"] for row in envelopes}) == 6
    assert manifest["financial_causation_id"] == scenario_id
    assert manifest["physical_period"] == "P1"
    assert manifest["capital_period"] == manifest["labour_period"] == 1
    assert manifest["financial_event_periods"] == [1,2,3,4]
    assert manifest["physical_unit"] == "t" and manifest["financial_currency"] == "LCU"

    print("A2.4.7 unified synthetic cross-register fixture: PASS")
    print("SCCE production, cohort service, physical flow, product valuation and labour/consent controls closed")
    print("GOLD-2A financial event store, T/V/O, control positions, coverage and replay closed")
    print("one scenario root links six distinct register event IDs; native units and currency remain distinct")
    print("LIMIT: no single production transaction spans all registers; Gate 2 runtime closure remains OPEN")


if __name__ == "__main__":
    main()
