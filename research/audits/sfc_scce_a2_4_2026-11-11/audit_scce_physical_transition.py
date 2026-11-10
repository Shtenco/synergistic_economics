"""A2.4.1/B4 multi-period physical transition check against the real SCCE engine.

The fixture executes DynamicCellularEconomy itself. It reconstructs every
cell/product inventory roll-forward from opening stocks, resource regeneration,
production events, mirrored inter-cell delivery events, recipe input use and
final consumption. It also validates the engine's event sequence and resource
stock-flow identity after every period.
"""
from collections import defaultdict
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[3]
PROTOTYPE = ROOT / "prototype"
sys.path.insert(0, str(PROTOTYPE))

from scc_dynamic_economy import (  # noqa: E402
    DynamicCellularEconomy,
    PRODUCTS,
)


TOL = 2e-7
ALLOWED_EVENTS = {
    "production",
    "intermediate.input.delivery",
    "final.goods.delivery",
}


def close(label, actual, expected):
    if abs(float(actual) - float(expected)) > TOL:
        raise AssertionError(f"{label}: actual={actual}, expected={expected}")


def main():
    model = DynamicCellularEconomy(
        policy="cellular", seed=23, shock="compound", cellular_hops=2)
    prior_event_count = 0
    seen_keys = set()

    for period in range(1, 9):
        opening = {
            cid: dict(cell.stocks)
            for cid, cell in model.cells.items()
        }
        _, resource_multiplier, _ = model._shock_values(period)
        regeneration = {
            cid: max(
                0.0,
                min(cell.spec.resource_capacity,
                    opening[cid]["raw_resource"]
                    + cell.spec.resource_regeneration * resource_multiplier)
                - opening[cid]["raw_resource"],
            )
            for cid, cell in model.cells.items()
        }

        result = model.step(period)
        new_events = model.events[prior_event_count:]
        prior_event_count = len(model.events)

        production = defaultdict(float)
        incoming = defaultdict(float)
        outgoing = defaultdict(float)
        input_use = defaultdict(float)
        production_by_product = defaultdict(float)

        for event in new_events:
            if event["type"] not in ALLOWED_EVENTS:
                raise AssertionError(f"unknown physical event type: {event['type']}")
            if event["sequence"] != len(seen_keys) + 1:
                raise AssertionError("event sequence is not contiguous")
            if event["key"] in seen_keys:
                raise AssertionError(f"duplicate event key: {event['key']}")
            seen_keys.add(event["key"])

            key_parts = event["key"].split(":")
            if len(key_parts) < 3 or int(key_parts[1]) != period:
                raise AssertionError(f"event key period mismatch: {event['key']}")

            payload = event["payload"]
            product = payload.get("product")
            if product not in PRODUCTS:
                raise AssertionError(f"unknown product in event: {product}")

            quantity = float(payload.get("quantity", -1.0))
            if quantity < 0:
                raise AssertionError("negative event quantity")

            if event["type"] == "production":
                cell_id = payload.get("cell")
                if cell_id not in model.cells:
                    raise AssertionError(f"unknown production cell: {cell_id}")
                if key_parts[0] != "production" or key_parts[2] != cell_id:
                    raise AssertionError("production key/payload mismatch")
                production[(cell_id, product)] += quantity
                production_by_product[product] += quantity
            else:
                seller = payload.get("seller")
                buyer = payload.get("buyer")
                distance = float(payload.get("distance", -1.0))
                if seller not in model.cells or buyer not in model.cells:
                    raise AssertionError("delivery references unknown cell")
                if seller == buyer or distance < 0:
                    raise AssertionError("invalid inter-cell delivery endpoints")
                if key_parts[0] != event["type"]:
                    raise AssertionError("delivery key/type mismatch")
                outgoing[(seller, product)] += quantity
                incoming[(buyer, product)] += quantity

        # Exactly one production event per cell per period, including zero output.
        production_cells = {
            event["payload"]["cell"]
            for event in new_events if event["type"] == "production"
        }
        if production_cells != set(model.cells):
            raise AssertionError(
                f"production event coverage mismatch: {production_cells}")

        for product, quantity in result.output_by_product.items():
            close(f"period {period} output event mirror {product}",
                  production_by_product[product], quantity)

        # Derive intermediate input use from actual production quantities and
        # the production recipes that were active in this period.
        for cid, cell in model.cells.items():
            produced = production.get((cid, cell.spec.output), 0.0)
            for input_product, coefficient in cell.spec.recipe.items():
                input_use[(cid, input_product)] += produced * coefficient

        # Full cell x product inventory roll-forward.
        for cid, cell in model.cells.items():
            for product in PRODUCTS:
                expected = opening[cid].get(product, 0.0)
                if product == "raw_resource":
                    expected += regeneration[cid]
                expected += production.get((cid, product), 0.0)
                expected += incoming.get((cid, product), 0.0)
                expected -= outgoing.get((cid, product), 0.0)
                expected -= input_use.get((cid, product), 0.0)
                expected -= result.final_consumption_by_cell.get(cid, {}).get(
                    product, 0.0)
                close(f"P{period}/{cid}/{product}",
                      cell.stocks.get(product, 0.0), expected)

        if not model.validate():
            raise AssertionError(f"engine validation returned false at period {period}")

    assert len(seen_keys) == len(model.events)
    assert len(model.periods) == 8
    assert model.total_resource_used > 0
    assert model.total_regenerated > 0
    print("A2.4.1/B4 real SCCE physical transition: PASS")
    print(f"periods={len(model.periods)}; cells={len(model.cells)}; "
          f"events={len(model.events)}")
    print("all cell/product stocks reconcile from production, transfers, "
          "recipe use, final delivery and resource regeneration")
    print("event sequence/keys unique; production event totals mirror period outputs")
    print("raw-resource stock-flow identity validated after every period")


if __name__ == "__main__":
    main()
