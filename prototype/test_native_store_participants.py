"""Integration tests binding physical, capital and product stores to the coordinator."""
from dataclasses import asdict
from decimal import Decimal as D
import tempfile
import unittest
from pathlib import Path

from physical_flow_store import FlowPosting, PhysicalFlowStore, PhysicalFlowError
from capital_cohort_bridge import CapitalCohort
from capital_cohort_store import CapitalCohortStore
from product_register import ProductRegister
from labour_register import LabourRegister
from legal_rights_register import LegalRightsRegister
from cross_register_coordinator import CrossRegisterCoordinator, SQLiteParticipant, PARTICIPANTS
from native_store_participants import make_physical_participant, make_capital_participant, make_product_participant
from economic_stock_flow_reconciliation import PositionIdentity,OpeningPosition,ClosingPosition,reconcile_periods,movements_from_event_groups

T="2026-11-13T05:00:00Z"
AUTH=lambda actor,authority,event_type,payload: actor=="coordinator" and authority.startswith("AUTH:")


def flow_pair(flow_id="FLOW-1",quantity="5"):
    common=dict(flow_id=flow_id,origin_node="mine",destination_node="mill",
        origin_boundary="domestic",destination_boundary="domestic",product_id="steel",grade_id="S235",
        quantity=D(quantity),unit="t",event_time=T,period="P1",flow_class="internal_transfer",
        quality="conforming",measurement_method="weighbridge",uncertainty=D("0.01"),evidence_status="measured")
    return (FlowPosting(node_id="mine",role="outflow",**common),FlowPosting(node_id="mill",role="inflow",**common))


def envelope(event_type,payload,idempotency):
    return {"event_type":event_type,"effective_at":T,"recorded_at":T,"actor_id":"coordinator",
        "authority_ref":"AUTH:COORDINATOR","idempotency_key":idempotency,"payload":payload}


class NativeStoreParticipantTests(unittest.TestCase):
    def test_five_native_registers_commit_as_one_six_participant_event_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            physical=PhysicalFlowStore(root/"physical.sqlite3")
            capital=CapitalCohortStore(root/"capital.sqlite3")
            capital.initialize((CapitalCohort("C1","cell-1","machine",2026,0,1,1,"operating",1,1,1),))
            product=ProductRegister(root/"product.sqlite3")
            labour=LabourRegister(root/"labour.sqlite3")
            labour.bootstrap_admin(principal_id="labour-root",authority_ref="BOOTSTRAP:L",occurred_at=T)
            labour.grant_access(event_id="L-ACL",idempotency_key="L-ACL",principal_id="coordinator",
                permissions=["labour:read","labour:write"],actor_id="labour-root",authority_ref="POLICY:L",occurred_at=T)
            rights=LegalRightsRegister(root/"rights.sqlite3")
            rights.bootstrap_admin(principal_id="rights-root",authority_ref="BOOTSTRAP:R",occurred_at=T)
            rights.grant_access(event_id="R-ACL",idempotency_key="R-ACL",principal_id="coordinator",
                permissions=["legal_rights:read","legal_rights:write","legal_rights:adjudicate"],
                actor_id="rights-root",authority_ref="POLICY:R",occurred_at=T)
            participants={
                "physical":make_physical_participant(physical,AUTH),
                "capital":make_capital_participant(capital,AUTH),
                "product":make_product_participant(product,AUTH),
                "labour":labour,"legal_rights":rights,
                "financial":SQLiteParticipant("financial",root/"financial.sqlite3"),
            }
            coordinator=CrossRegisterCoordinator(root/"coordinator.sqlite3",participants)
            outflow,inflow=flow_pair()
            outdict=asdict(outflow); outdict["quantity"]=str(outdict["quantity"]); outdict["uncertainty"]=str(outdict["uncertainty"])
            indict=asdict(inflow); indict["quantity"]=str(indict["quantity"]); indict["uncertainty"]=str(indict["uncertainty"])
            identity_out={"register_id":"physical","position_id":"mine:steel:S235","measure":"mass","unit":"t",
                "currency":"NA","valuation_basis":"PHYSICAL","holder_id":"mine","issuer_id":"mill","instrument_id":"steel:S235"}
            identity_in={**identity_out,"position_id":"mill:steel:S235","holder_id":"mill","issuer_id":"mine"}
            movements=[
                {"movement_id":"FLOW-1:OUT","identity":identity_out,"period_index":1,"movement_class":"T",
                 "amount":"-5","evidence_ref":"WEIGHBRIDGE-1","mirror_group_id":"FLOW-1","mirror_side":"sender","mirror_policy":"opposite"},
                {"movement_id":"FLOW-1:IN","identity":identity_in,"period_index":1,"movement_class":"T",
                 "amount":"5","evidence_ref":"WEIGHBRIDGE-1","mirror_group_id":"FLOW-1","mirror_side":"receiver","mirror_policy":"opposite"},
            ]
            operations={
                "physical":{"stream_id":"physical","native_event_id":"FLOW-1","expected_revision":0,
                    "payload":envelope("physical.flow_recorded",{"outflow":outdict,"inflow":indict},"FLOW-1") | {"stock_flow_movements":movements}},
                "capital":{"stream_id":"capital","native_event_id":"CAPITAL-PERIOD:1","expected_revision":0,
                    "payload":envelope("capital.period_appended",{"period":1,"events":[],"additions":[]},"CAPITAL-PERIOD:1") | {"no_stock_flow_effect":"empty cohort period batch"}},
                "product":{"stream_id":"product","native_event_id":"SPEC:steel:S235","expected_revision":0,
                    "payload":envelope("product_spec",{"product_id":"steel","grade_id":"S235","dimension":"mass",
                        "native_unit":"t","stockability":"stockable","time_basis":"period_flow","evidence_ref":"SPEC-1"},
                        "SPEC:steel:S235") | {"no_stock_flow_effect":"specification metadata only; no position movement"}},
                "labour":{"stream_id":"ENG-1","native_event_id":"LABOUR-1","expected_revision":0,
                    "payload":envelope("engagement.offered",{"person_ref":"PSEUDO-1","activity_id":"work","period":"P1",
                        "classification":"paid","consent_basis":"CONTRACT-1","planned_hours":"2"},"LABOUR-1") | {"no_stock_flow_effect":"offer only; no delivered labour or accrued compensation"}},
                "legal_rights":{"stream_id":"RIGHT-1","native_event_id":"RIGHT-1","expected_revision":0,
                    "payload":envelope("right.created",{"holder_id":"ORG-A","obligor_id":"ORG-B","right_type":"claim",
                        "scope":"invoice:1","jurisdiction":"KZ","legal_instrument_ref":"CONTRACT-1",
                        "effective_from":T,"evidence_refs":["SIGNED-1"]},"RIGHT-1") | {"no_stock_flow_effect":"legal claim recorded; no recognized financial posting"}},
                "financial":{"stream_id":"stream:financial","native_event_id":"FIN-1","expected_revision":0,
                    "payload":{"no_stock_flow_effect":"no financial event in this physical-flow test"}},
            }
            self.assertTrue(coordinator.submit("TX-NATIVE-5","SCENARIO-NATIVE-5","CAUSE-NATIVE-5",operations))
            self.assertEqual(coordinator.execute("TX-NATIVE-5"),"COMMITTED")
            self.assertTrue(coordinator.is_visible("TX-NATIVE-5"))
            self.assertEqual(physical.flow_count,1); self.assertTrue(physical.verify())
            self.assertEqual(capital.current_state().last_processed_period,1); self.assertTrue(capital.verify())
            self.assertTrue(product.verify())
            group=coordinator.committed_event_group("TX-NATIVE-5")
            self.assertEqual({x["register_id"] for x in group["events"]},set(PARTICIPANTS))
            movements=movements_from_event_groups((group,))
            sender=PositionIdentity(**identity_out); receiver=PositionIdentity(**identity_in)
            openings=(OpeningPosition(sender,1,D("10"),"OPEN-SENDER"),OpeningPosition(receiver,1,D("0"),"OPEN-RECEIVER"))
            closings=(ClosingPosition(sender,1,D("5"),"CLOSE-SENDER"),ClosingPosition(receiver,1,D("5"),"CLOSE-RECEIVER"))
            reconciled=reconcile_periods(openings,movements,closings)
            self.assertEqual(reconciled.mirror_group_count,1)

    def test_prepared_physical_stream_blocks_direct_write_until_abort(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=PhysicalFlowStore(Path(tmp)/"physical.sqlite3")
            participant=make_physical_participant(store,AUTH)
            outflow,inflow=flow_pair("FLOW-RESERVED")
            outdict=asdict(outflow); outdict["quantity"]=str(outdict["quantity"]); outdict["uncertainty"]=str(outdict["uncertainty"])
            indict=asdict(inflow); indict["quantity"]=str(indict["quantity"]); indict["uncertainty"]=str(indict["uncertainty"])
            op={"stream_id":"physical","native_event_id":"FLOW-RESERVED","expected_revision":0,
                "payload":envelope("physical.flow_recorded",{"outflow":outdict,"inflow":indict},"FLOW-RESERVED")}
            token=participant.prepare("TX-RESERVED",op)
            with self.assertRaises(PhysicalFlowError): store.append(outflow,inflow)
            participant.abort("TX-RESERVED")
            self.assertEqual(store.flow_count,0)
            self.assertIsNotNone(token)


if __name__=="__main__": unittest.main(verbosity=2)
