"""Durable physical-flow event store: append, retry, replay and tamper controls."""
from contextlib import closing
from dataclasses import replace
from decimal import Decimal as D
from pathlib import Path
import sqlite3, sys, tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))
from physical_flow_store import FlowPosting, PhysicalFlowError, PhysicalFlowStore, validate_pair


def pair(flow_id, origin, destination, quantity):
    common = dict(flow_id=flow_id, origin_node=origin, destination_node=destination,
        origin_boundary="domestic", destination_boundary="domestic", product_id="steel",
        grade_id="S235", quantity=D(str(quantity)), unit="t", event_time="2026-11-12T12:00:00Z",
        period="P1", flow_class="internal_transfer", quality="conforming",
        measurement_method="weighbridge", uncertainty=D("0.01"), evidence_status="measured")
    return FlowPosting(node_id=origin, role="outflow", **common), FlowPosting(node_id=destination, role="inflow", **common)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "physical.sqlite3"
        store = PhysicalFlowStore(db)
        f1, f2 = pair("PF-001","mine","mill","12"), pair("PF-002","mill","export","3")
        assert store.append(*f1) is True and store.append(*f2) is True
        assert store.verify() and store.flow_count() == 2
        assert store.node_net("mine","steel","S235","P1","t") == D("-12")
        assert store.node_net("mill","steel","S235","P1","t") == D("9")
        assert store.node_net("export","steel","S235","P1","t") == D("3")
        assert store.consolidated_net({"mine","mill"},"steel","S235","P1","t") == D("-3")
        assert store.consolidated_net({"mine","mill","export"},"steel","S235","P1","t") == D("0")
        restarted = PhysicalFlowStore(db)
        assert restarted.append(*f1) is False and restarted.flow_count() == 2 and restarted.verify()
        try:
            restarted.append(*pair("PF-001","mine","mill","13"))
        except PhysicalFlowError:
            pass
        else:
            raise AssertionError("changed flow retry accepted")
        bad_out,bad_in = pair("PF-BAD","mine","mill","1")
        try:
            validate_pair(bad_out,replace(bad_in,quantity=D("2")))
        except PhysicalFlowError:
            pass
        else:
            raise AssertionError("mismatched endpoints accepted")
        with closing(sqlite3.connect(db)) as con:
            con.execute("DROP TRIGGER physical_flows_no_update")
            con.execute("UPDATE physical_flows SET payload_json='{}' WHERE flow_id='PF-001'")
        assert restarted.verify() is False
    print("A2.4 durable physical flow register: PASS")
    print("paired endpoints, append-only hash chain, restart retry and node consolidation verified")
    print("changed-ID retry, mismatched endpoints and tampered replay rejected")


if __name__ == "__main__":
    main()
