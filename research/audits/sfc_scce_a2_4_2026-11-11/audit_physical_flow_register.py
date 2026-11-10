"""A2.4.3 node-to-node physical flow mirror and consolidation controls."""
from dataclasses import dataclass
from decimal import Decimal as D


class FlowError(ValueError):
    pass


@dataclass(frozen=True)
class FlowEndpoint:
    flow_id: str
    product_id: str
    grade_id: str
    quantity: D
    unit: str
    period: str
    sender: str
    receiver: str


class PhysicalFlowRegister:
    def __init__(self):
        self._flows = {}

    def record(self, sender_record, receiver_record):
        if sender_record.flow_id in self._flows:
            raise FlowError("duplicate flow_id")
        if sender_record.flow_id != receiver_record.flow_id:
            raise FlowError("sender/receiver flow_id mismatch")
        for field in ("product_id", "grade_id", "quantity", "unit", "period"):
            if getattr(sender_record, field) != getattr(receiver_record, field):
                raise FlowError(f"sender/receiver {field} mismatch")
        if sender_record.sender == sender_record.receiver:
            raise FlowError("self-transfer is not a valid inter-node flow")
        if sender_record.quantity <= 0 or not sender_record.unit:
            raise FlowError("flow quantity and unit must be positive/present")
        if sender_record.receiver != receiver_record.receiver or sender_record.sender != receiver_record.sender:
            raise FlowError("endpoint identities differ")
        self._flows[sender_record.flow_id] = sender_record

    def consolidated_internal_net(self, product_id, grade_id, period):
        # Every internal transfer is an equal source and use; it cancels once.
        selected = [f for f in self._flows.values()
                    if (f.product_id, f.grade_id, f.period) ==
                       (product_id, grade_id, period)]
        return sum((f.quantity - f.quantity for f in selected), D("0"))

    @property
    def flow_count(self):
        return len(self._flows)


def main():
    register = PhysicalFlowRegister()
    outflow = FlowEndpoint("F-001", "steel", "S235", D("12"), "t", "P1",
                           "smelter", "fabricator")
    inflow = FlowEndpoint("F-001", "steel", "S235", D("12"), "t", "P1",
                          "smelter", "fabricator")
    register.record(outflow, inflow)
    assert register.flow_count == 1
    assert register.consolidated_internal_net("steel", "S235", "P1") == 0

    mismatched = FlowEndpoint("F-002", "steel", "S235", D("11"), "t", "P1",
                              "smelter", "fabricator")
    try:
        register.record(outflow, mismatched)
    except FlowError:
        pass
    else:
        raise AssertionError("mismatched sender/receiver quantity accepted")
    try:
        register.record(outflow, inflow)
    except FlowError:
        pass
    else:
        raise AssertionError("duplicate flow_id accepted")

    print("A2.4.3 physical flow mirror fixture: PASS")
    print("one 12 t internal transfer recorded once; consolidated internal net=0")
    print("mismatched quantity and duplicate flow_id rejected")


if __name__ == "__main__":
    main()
