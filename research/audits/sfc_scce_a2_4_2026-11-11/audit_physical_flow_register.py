"""A2.4.3 node-to-node physical flow mirror and consolidation controls.

Each physical transfer has two endpoint postings: one source outflow and one
receiver inflow. The pair shares an immutable flow ID and identical physical
classification, but has opposite node roles. Internal transfers cancel only
when both endpoint nodes are inside the chosen consolidation boundary.
"""
from dataclasses import dataclass
from decimal import Decimal as D


class FlowError(ValueError):
    pass


@dataclass(frozen=True)
class FlowPosting:
    flow_id: str
    node_id: str
    counterparty_id: str
    role: str
    product_id: str
    grade_id: str
    quantity: D
    unit: str
    period: str


class PhysicalFlowRegister:
    def __init__(self):
        self._flows = {}

    def record(self, outflow, inflow):
        if not outflow.flow_id or outflow.flow_id in self._flows:
            raise FlowError("missing or duplicate flow_id")
        if outflow.role != "outflow" or inflow.role != "inflow":
            raise FlowError("endpoint roles must be outflow then inflow")
        if outflow.flow_id != inflow.flow_id:
            raise FlowError("flow_id mismatch")
        for field in ("product_id", "grade_id", "quantity", "unit", "period"):
            if getattr(outflow, field) != getattr(inflow, field):
                raise FlowError(f"endpoint {field} mismatch")
        if outflow.node_id == inflow.node_id:
            raise FlowError("self-transfer is not a valid inter-node flow")
        if (outflow.counterparty_id != inflow.node_id
                or inflow.counterparty_id != outflow.node_id):
            raise FlowError("endpoint counterparty identities are not reciprocal")
        if outflow.quantity <= 0 or not outflow.unit:
            raise FlowError("flow quantity and unit must be positive/present")
        if not all((outflow.node_id, inflow.node_id, outflow.product_id,
                    outflow.grade_id, outflow.period)):
            raise FlowError("required flow classification is missing")
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
        # Transfers with both endpoints inside the boundary cancel exactly.
        return sum((self.node_net(node, product_id, grade_id, period)
                    for node in set(node_ids)), D("0"))

    @property
    def flow_count(self):
        return len(self._flows)


def posting(flow_id, node_id, counterparty_id, role, quantity,
            product="steel", grade="S235", unit="t", period="P1"):
    return FlowPosting(flow_id, node_id, counterparty_id, role, product, grade,
                       D(str(quantity)), unit, period)


def main():
    register = PhysicalFlowRegister()

    # Internal 12 t transfer: source and receiver have opposite endpoint roles.
    register.record(
        posting("F-001", "smelter", "fabricator", "outflow", 12),
        posting("F-001", "fabricator", "smelter", "inflow", 12))
    assert register.flow_count == 1
    assert register.node_net("smelter", "steel", "S235", "P1") == D("-12")
    assert register.node_net("fabricator", "steel", "S235", "P1") == D("12")
    assert register.consolidated_net(
        {"smelter", "fabricator"}, "steel", "S235", "P1") == 0

    # Export leaves the domestic boundary; it must not disappear on consolidation.
    register.record(
        posting("F-002", "fabricator", "ROW", "outflow", 3),
        posting("F-002", "ROW", "fabricator", "inflow", 3))
    assert register.consolidated_net(
        {"smelter", "fabricator"}, "steel", "S235", "P1") == D("-3")

    # Adversarial mirror failures.
    try:
        register.record(
            posting("F-003", "A", "B", "outflow", 4),
            posting("F-003", "B", "A", "inflow", 5))
    except FlowError:
        pass
    else:
        raise AssertionError("mismatched endpoint quantity accepted")
    try:
        register.record(
            posting("F-004", "A", "B", "outflow", 4),
            posting("F-004", "C", "A", "inflow", 4))
    except FlowError:
        pass
    else:
        raise AssertionError("non-reciprocal endpoint identity accepted")
    try:
        register.record(
            posting("F-001", "smelter", "fabricator", "outflow", 12),
            posting("F-001", "fabricator", "smelter", "inflow", 12))
    except FlowError:
        pass
    else:
        raise AssertionError("duplicate flow_id accepted")

    print("A2.4.3 physical flow mirror fixture: PASS")
    print("internal transfer=12 t; domestic consolidated net=0")
    print("external export=3 t; domestic consolidated net=-3 t")
    print("mismatched quantity, non-reciprocal endpoint and duplicate ID rejected")


if __name__ == "__main__":
    main()
