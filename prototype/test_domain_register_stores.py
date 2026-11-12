"""Unit coverage for the durable physical, capital and product domain stores."""
import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from physical_flow_store import FlowPosting, PhysicalFlowStore, PhysicalFlowError
from capital_cohort_bridge import CapitalCohort, CohortEvent
from capital_cohort_store import CapitalCohortStore, CapitalCohortStoreError
from product_register import ProductSpec, ProductBalance, PriceQuote, ValuationRecord, ProductRegister, ProductRegisterError


def flow_pair(flow_id, origin, destination, quantity, unit="t"):
    common=dict(flow_id=flow_id,origin_node=origin,destination_node=destination,
        origin_boundary="domestic",destination_boundary="domestic",product_id="steel",
        grade_id="S235",quantity=D(str(quantity)),unit=unit,event_time="2026-11-12T12:00:00Z",
        period="P1",flow_class="internal_transfer",quality="conforming",
        measurement_method="weighbridge",uncertainty=D("0.01"),evidence_status="measured")
    return (FlowPosting(node_id=origin,role="outflow",**common),
            FlowPosting(node_id=destination,role="inflow",**common))


class DurableDomainRegisterTests(unittest.TestCase):
    def test_physical_flow_append_replay_and_unit_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=PhysicalFlowStore(Path(tmp)/"physical.sqlite3")
            pair=flow_pair("F-1","mine","mill",12)
            self.assertTrue(store.append(*pair))
            self.assertFalse(store.append(*pair))
            self.assertTrue(store.append(*flow_pair("F-2","mine","mill",1000,"kg")))
            self.assertEqual(store.node_net("mine","steel","S235","P1","t"),D("-12"))
            self.assertEqual(store.node_net("mine","steel","S235","P1","kg"),D("-1000"))
            self.assertEqual(store.consolidated_net({"mine","mill"},"steel","S235","P1","t"),D("0"))
            self.assertTrue(store.verify())

    def test_capital_periods_replay_and_processed_event_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CapitalCohortStore(Path(tmp)/"capital.sqlite3")
            opening=(CapitalCohort("C1","cell-1","machine",2020,6,10,10,"operating",.9,.8,.95),)
            loss=(CohortEvent("E1","C1","physical_loss",2,"operating",None,"accident"),)
            addition=(CapitalCohort("C2","cell-1","machine",2026,0,3,10,"operating",.9,.8,.95),)
            self.assertTrue(store.initialize(opening))
            self.assertTrue(store.append_period(2026,loss,addition))
            self.assertFalse(store.append_period(2026,loss,addition))
            self.assertEqual(sum(x.quantity for x in store.current_state().cohorts),11)
            self.assertTrue(store.verify())

    def test_product_balance_price_and_valuation_are_linked(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=ProductRegister(Path(tmp)/"products.sqlite3")
            spec=ProductSpec("steel","S235","mass","t","stockable","period_flow","SPEC-E1")
            balance=ProductBalance("B1","steel","S235","P1",0,"plant-A","t",
                D("0"),D("10"),D("2"),D("3"),D("4"),D("0"),D("2"),D("1"),D("2"),"BAL-E1")
            price=PriceQuote("P1-PRICE","steel","S235",D("2"),"t","LCU","P1","basic_price","SRC-1","PRICE-E1")
            value=ValuationRecord("V1","B1","P1-PRICE","output",D("20"),"VAL-E1")
            self.assertTrue(store.register_product(spec))
            self.assertTrue(store.record_balance(balance))
            self.assertTrue(store.record_price(price))
            self.assertTrue(store.record_valuation(value))
            self.assertEqual(store.valuation("V1"),value)
            self.assertTrue(store.verify())



    def test_physical_integrity_matrix(self):
        cases=[("payload","UPDATE physical_flows SET payload_json='{}' WHERE flow_id='F-1'"),("digest","UPDATE physical_flows SET payload_sha256='bad' WHERE flow_id='F-1'"),("chain","UPDATE physical_flows SET chain_hash='bad' WHERE flow_id='F-1'"),("tail","UPDATE physical_flow_meta SET tail_hash='bad' WHERE singleton_id=1"),("count","UPDATE physical_flow_meta SET event_count=8 WHERE singleton_id=1")]
        for name,sql in cases:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                db=Path(tmp)/"p.db"; st=PhysicalFlowStore(db); st.append(*flow_pair("F-1","mine","mill",12))
                with closing(__import__("sqlite3").connect(db)) as con: con.execute("DROP TRIGGER physical_flows_no_update"); con.execute(sql); con.commit()
                self.assertFalse(st.verify())
                for read in (st.flow_count,lambda:st.node_net("mine","steel","S235","P1","t"),lambda:st.consolidated_net({"mine","mill"},"steel","S235","P1","t")):
                    with self.assertRaises(PhysicalFlowError): read()

    def test_capital_integrity_matrix(self):
        cases=[("payload","UPDATE capital_cohort_periods SET payload_json='{}' WHERE period=2026"),("payload_hash","UPDATE capital_cohort_periods SET payload_sha256='bad' WHERE period=2026"),("chain","UPDATE capital_cohort_periods SET chain_hash='bad' WHERE period=2026"),("closing","UPDATE capital_cohort_periods SET closing_state_json='{}' WHERE period=2026"),("closing_hash","UPDATE capital_cohort_periods SET state_sha256='bad' WHERE period=2026"),("tail","UPDATE capital_cohort_meta SET tail_hash='bad' WHERE singleton_id=1"),("count","UPDATE capital_cohort_meta SET period_count=8 WHERE singleton_id=1"),("opening","UPDATE capital_cohort_meta SET opening_state_json='{}' WHERE singleton_id=1"),("opening_hash","UPDATE capital_cohort_meta SET opening_state_sha256='bad' WHERE singleton_id=1")]
        for name,sql in cases:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                db=Path(tmp)/"c.db"; st=CapitalCohortStore(db)
                opening=(CapitalCohort("C1","cell-1","machine",2020,6,10,10,"operating",.9,.8,.95),)
                ev=(CohortEvent("E1","C1","physical_loss",2,"operating",None,"accident"),)
                st.initialize(opening); st.append_period(2026,ev,())
                with closing(__import__("sqlite3").connect(db)) as con: con.execute("DROP TRIGGER capital_cohort_periods_no_update"); con.execute(sql); con.commit()
                self.assertFalse(st.verify())
                with self.assertRaises(CapitalCohortStoreError): st.current_state()

    def test_product_integrity_matrix(self):
        cases=[("payload","UPDATE product_events SET payload_json='{}' WHERE event_id='V1'"),("digest","UPDATE product_events SET payload_sha256='bad' WHERE event_id='V1'"),("chain","UPDATE product_events SET chain_hash='bad' WHERE event_id='V1'"),("tail","UPDATE product_register_meta SET tail_hash='bad' WHERE singleton_id=1"),("count","UPDATE product_register_meta SET event_count=8 WHERE singleton_id=1")]
        for name,sql in cases:
            with self.subTest(name=name),tempfile.TemporaryDirectory() as tmp:
                db=Path(tmp)/"r.db"; st=ProductRegister(db)
                spec=ProductSpec("steel","S235","mass","t","stockable","period_flow","SPEC-E1")
                bal=ProductBalance("B1","steel","S235","P1",0,"plant-A","t",D("0"),D("10"),D("2"),D("3"),D("4"),D("0"),D("2"),D("1"),D("2"),"BAL-E1")
                price=PriceQuote("P1-PRICE","steel","S235",D("2"),"t","LCU","P1","basic_price","SRC-1","PRICE-E1")
                val=ValuationRecord("V1","B1","P1-PRICE","output",D("20"),"VAL-E1")
                st.register_product(spec); st.record_balance(bal); st.record_price(price); st.record_valuation(val)
                with closing(__import__("sqlite3").connect(db)) as con: con.execute("DROP TRIGGER product_events_no_update"); con.execute(sql); con.commit()
                self.assertFalse(st.verify())
                with self.assertRaises(ProductRegisterError): st.valuation("V1")

    def test_correction_lineage_replayed_after_fully_rehashed_orphan_tamper(self):
        import hashlib,json
        from physical_flow_store import _canonical
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"p.db"; st=PhysicalFlowStore(db); st.append(*flow_pair("ORIG","mine","mill",12))
            common=dict(flow_id="CORR",origin_node="mill",destination_node="mine",origin_boundary="domestic",destination_boundary="domestic",product_id="steel",grade_id="S235",quantity=D("12"),unit="t",event_time="2026-11-12T12:00:00Z",period="P1",flow_class="compensation",quality="conforming",measurement_method="weighbridge",uncertainty=D("0.01"),evidence_status="measured",correction_of="ORIG",correction_reason="reversal")
            st.append(FlowPosting(node_id="mill",role="outflow",**common),FlowPosting(node_id="mine",role="inflow",**common))
            self.assertTrue(st.verify())
            with closing(__import__("sqlite3").connect(db)) as con:
                con.execute("DROP TRIGGER physical_flows_no_update")
                seq,raw=con.execute("SELECT commit_sequence,payload_json FROM physical_flows WHERE flow_id='CORR'").fetchone()
                payload=json.loads(raw); payload["outflow"]["correction_of"]="ORPHAN"; payload["inflow"]["correction_of"]="ORPHAN"
                encoded=_canonical(payload); digest=hashlib.sha256(encoded.encode()).hexdigest()
                prev=con.execute("SELECT chain_hash FROM physical_flows WHERE flow_id='ORIG'").fetchone()[0]
                chain=PhysicalFlowStore._chain_hash(seq,"CORR",digest,prev)
                con.execute("UPDATE physical_flows SET payload_json=?,payload_sha256=?,previous_hash=?,chain_hash=? WHERE flow_id='CORR'",(encoded,digest,prev,chain))
                con.execute("UPDATE physical_flow_meta SET tail_hash=? WHERE singleton_id=1",(chain,)); con.commit()
            self.assertFalse(st.verify())
            with self.assertRaises(PhysicalFlowError): st.node_net("mine","steel","S235","P1","t")

if __name__=="__main__":
    unittest.main()
