"""B3-compliant A2.4.3 physical flow endpoint and consolidation fixture."""
from dataclasses import dataclass
from decimal import Decimal as D


class FlowError(ValueError):
    pass


@dataclass(frozen=True)
class FlowPosting:
    flow_id: str
    node_id: str
    role: str
    origin_node: str
    destination_node: str
    origin_boundary: str
    destination_boundary: str
    product_id: str
    grade_id: str
    quantity: D
    unit: str
    event_time: str
    period: str
    flow_class: str
    quality: str
    measurement_method: str
    uncertainty: D
    evidence_status: str


class PhysicalFlowRegister:
    EVIDENCE = {"measured", "documented", "estimated", "simulated"}

    def __init__(self):
        self._flows = {}

    def record(self, outflow, inflow):
        if not outflow.flow_id or outflow.flow_id in self._flows:
            raise FlowError("missing or duplicate flow_id")
        if outflow.role != "outflow" or inflow.role != "inflow":
            raise FlowError("endpoint roles must be outflow then inflow")
        if outflow.flow_id != inflow.flow_id:
            raise FlowError("flow_id mismatch")
        shared = (
            "origin_node", "destination_node", "origin_boundary",
            "destination_boundary", "product_id", "grade_id", "quantity",
            "unit", "event_time", "period", "flow_class", "quality",
            "measurement_method", "uncertainty", "evidence_status",
        )
        for field in shared:
            if getattr(outflow, field) != getattr(inflow, field):
                raise FlowError(f"endpoint {field} mismatch")
        if outflow.node_id != outflow.origin_node:
            raise FlowError("outflow posting must belong to origin_node")
        if inflow.node_id != inflow.destination_node:
            raise FlowError("inflow posting must belong to destination_node")
        if outflow.origin_node == outflow.destination_node:
            raise FlowError("self-transfer is not a valid inter-node flow")
        if outflow.quantity <= 0 or outflow.uncertainty < 0:
            raise FlowError("quantity must be positive and uncertainty non-negative")
        required = (
            outflow.origin_node, outflow.destination_node,
            outflow.origin_boundary, outflow.destination_boundary,
            outflow.product_id, outflow.grade_id, outflow.unit,
            outflow.event_time, outflow.period, outflow.flow_class,
            outflow.quality, outflow.measurement_method,
        )
        if not all(required):
            raise FlowError("required B3 flow metadata is missing")
        if outflow.evidence_status not in self.EVIDENCE:
            raise FlowError("unknown evidence_status")
        self._flows[outflow.flow_id] = (outflow, inflow)

    def node_net(self, node_id, product_id, grade_id, period):
        net = D("0")
        for outflow, inflow in self._flows.values():
            if (outflow.product_id, outflow.grade_id, outflow.period) != (
                    product_id, grade_id, period):
                continue
            if outflow.node_id == node_id:
                net -= outflow.quantity
            if inflow.node_id == node_id:
                net += inflow.quantity
        return net

    def consolidated_net(self, node_ids, product_id, grade_id, period):
        return sum((self.node_net(node, product_id, grade_id, period)
                    for node in set(node_ids)), D("0"))

    @property
    def flow_count(self):
        return len(self._flows)


def pair(flow_id, origin, destination, quantity, *,
         product="steel", grade="S235", unit="t", period="P1",
         origin_boundary="domestic", destination_boundary="domestic",
         event_time="P1-D1T12:00", flow_class="internal_transfer",
         quality="conforming", measurement_method="weighbridge",
         uncertainty="0.01", evidence_status="measured"):
    common = dict(
        flow_id=flow_id, origin_node=origin, destination_node=destination,
        origin_boundary=origin_boundary, destination_boundary=destination_boundary,
        product_id=product, grade_id=grade, quantity=D(str(quantity)),
        unit=unit, event_time=event_time, period=period, flow_class=flow_class,
        quality=quality, measurement_method=measurement_method,
        uncertainty=D(str(uncertainty)), evidence_status=evidence_status,
    )
    outflow = FlowPosting(node_id=origin, role="outflow", **common)
    inflow = FlowPosting(node_id=destination, role="inflow", **common)
    return outflow, inflow


def main():
    register = PhysicalFlowRegister()
    register.record(*pair("F-001", "smelter", "fabricator", 12))
    assert register.flow_count == 1
    assert register.node_net("smelter", "steel", "S235", "P1") == D("-12")
    assert register.node_net("fabricator", "steel", "S235", "P1") == D("12")
    assert register.consolidated_net(
        {"smelter", "fabricator"}, "steel", "S235", "P1") == 0

    # External export remains visible when consolidating only domestic nodes.
    register.record(*pair(
        "F-002", "fabricator", "ROW", 3,
        destination_boundary="external", flow_class="export"))
    assert register.consolidated_net(
        {"smelter", "fabricator"}, "steel", "S235", "P1") == D("-3")

    # Adversarial endpoint and provenance checks.
    outflow, inflow = pair("F-003", "A", "B", 4)
    bad_quantity = FlowPosting(**{**inflow.__dict__, "quantity": D("5")})
    try:
        register.record(outflow, bad_quantity)
    except FlowError:
        pass
    else:
        raise AssertionError("mismatched endpoint quantity accepted")

    outflow, inflow = pair("F-004", "A", "B", 4)
    bad_endpoint = FlowPosting(**{**inflow.__dict__, "node_id": "C"})
    try:
        register.record(outflow, bad_endpoint)
    except FlowError:
        pass
    else:
        raise AssertionError("inflow posted to wrong node accepted")

    outflow, inflow = pair("F-005", "A", "B", 4)
    bad_quality = FlowPosting(**{**inflow.__dict__, "quality": "unclassified"})
    try:
        register.record(outflow, bad_quality)
    except FlowError:
        pass
    else:
        raise AssertionError("endpoint quality mismatch accepted")

    try:
        register.record(*pair("F-001", "smelter", "fabricator", 12))
    except FlowError:
        pass
    else:
        raise AssertionError("duplicate flow_id accepted")

    print("A2.4.3 B3 physical flow contract fixture: PASS")
    print("internal transfer=12 t; domestic consolidated net=0")
    print("external export=3 t; domestic consolidated net=-3 t")
    print("quantity, endpoint identity, quality mismatch and duplicate ID rejected")


if __name__ == "__main__":
    main()
