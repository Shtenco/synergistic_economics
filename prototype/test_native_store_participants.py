"""Integration tests binding physical, capital and product stores to the coordinator."""
from dataclasses import asdict
from decimal import Decimal as D
import tempfile
import unittest
import sys, json
from pathlib import Path

from physical_flow_store import FlowPosting, PhysicalFlowStore, PhysicalFlowError
from capital_cohort_bridge import CapitalCohort
from capital_cohort_store import CapitalCohortStore
from product_register import ProductRegister
from financial_event_store import FinancialEventStore
from entity_journal import EntityJournal
from external_checkpoints import LocalImmutableAnchor
from sfc_projection_registry import activate_sfc_projection
from sfc_projection_store import activate_control_openings, verify_projection_replay
from labour_register import LabourRegister
from legal_rights_register import LegalRightsRegister
from cross_register_coordinator import CrossRegisterCoordinator, PARTICIPANTS
from native_store_participants import (make_physical_participant, make_capital_participant,
    make_product_participant, make_financial_participant, financial_stock_flow_movement_specs)
from economic_stock_flow_reconciliation import PositionIdentity,OpeningPosition,ClosingPosition,reconcile_periods,movements_from_event_groups

T="2026-11-13T05:00:00Z"
ROOT=Path(__file__).resolve().parents[1]
AUDIT_DIR=ROOT/"research"/"audits"/"sfc_scce_a2_4_2026-11-11"
sys.path.insert(0,str(AUDIT_DIR))
from audit_financial_journal_adapter import _corpus_events
from financial_journal_adapter import _event_payload
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
    def test_six_native_registers_commit_as_one_six_participant_event_group(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            physical=PhysicalFlowStore(root/"physical.sqlite3")
            capital=CapitalCohortStore(root/"capital.sqlite3")
            capital.initialize((CapitalCohort("C1","cell-1","machine",2026,0,1,1,"operating",1,1,1),))
            product=ProductRegister(root/"product.sqlite3")
            financial_store=FinancialEventStore(root/"financial.sqlite3")
            registry,corpus_events=_corpus_events()
            journal=EntityJournal(registry)
            corpus=json.loads((AUDIT_DIR/"SFC_GOLD_2A_CORPUS.json").read_text(encoding="utf-8"))
            opening=corpus["opening_snapshot"]
            self.assertTrue(activate_sfc_projection(financial_store,opening["rows"],
                mapper_version=opening["mapper_version"],evidence_ref=opening["evidence_ref"]))
            controls=(
                {"control_id":"impairment_allowance","entity_id":"bank-1","sector":"CB","currency":"LCU",
                 "valuation_basis":"NOMINAL","period":0,"amount":"0","evidence_ref":opening["evidence_ref"]},
                {"control_id":"writeoff_memorandum","entity_id":"bank-1","sector":"CB","currency":"LCU",
                 "valuation_basis":"NOMINAL","period":0,"amount":"0","evidence_ref":opening["evidence_ref"]},
            )
            self.assertTrue(activate_control_openings(financial_store,controls,
                mapper_version="gold2a-controls@1",evidence_ref=opening["evidence_ref"]))
            first_financial_event=corpus_events[0]
            financial_movements=financial_stock_flow_movement_specs((first_financial_event,))
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
                "financial":make_financial_participant(financial_store,journal,AUTH),
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
                "capital":{"stream_id":"capital","native_event_id":"CAPITAL-PERIOD:2026","expected_revision":0,
                    "payload":envelope("capital.period_appended",{"period":2026,"events":[],"additions":[]},"CAPITAL-PERIOD:2026") | {"no_stock_flow_effect":"empty cohort period batch"}},
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
                "financial":{"stream_id":"financial","native_event_id":"FIN-GROUP-1","expected_revision":0,
                    "payload":envelope("financial.event_group_committed",{"group_id":"FIN-GROUP-1",
                        "causation_id":"SCENARIO-NATIVE-5","events":[_event_payload(first_financial_event)]},
                        "FIN-GROUP-1") | {"stock_flow_movements":financial_movements}},
            }
            self.assertTrue(coordinator.submit("TX-NATIVE-5","SCENARIO-NATIVE-5","CAUSE-NATIVE-5",operations))
            self.assertEqual(coordinator.execute("TX-NATIVE-5"),"COMMITTED")
            self.assertTrue(coordinator.is_visible("TX-NATIVE-5"))
            physical_status=participants["physical"].status("TX-NATIVE-5")
            self.assertEqual(participants["physical"].commit("TX-NATIVE-5",physical_status["prepare_token"]),
                             __import__("json").loads(physical_status["receipt_json"]))
            self.assertEqual(physical.flow_count(),1); self.assertTrue(physical.verify())
            self.assertEqual(capital.current_state().last_processed_period,2026); self.assertTrue(capital.verify())
            self.assertTrue(product.verify())
            group=coordinator.committed_event_group("TX-NATIVE-5")
            self.assertEqual(coordinator.iter_committed_event_groups(),[group])
            checkpoint=coordinator.latest_event_group_checkpoint()
            self.assertEqual(checkpoint["sequence"],1)
            self.assertEqual(len(checkpoint["group_hash"]),64)
            external_anchor=LocalImmutableAnchor(root/"external-anchor.sqlite3")
            manifest=coordinator.publish_event_stream_checkpoint(external_anchor,"SYNERGY-TEST")
            anchored=external_anchor.latest("SYNERGY-TEST")
            self.assertEqual(anchored["checkpoint_sequence"],1)
            self.assertEqual(manifest["group_hash"],checkpoint["group_hash"])
            self.assertTrue(external_anchor.is_anchored("SYNERGY-TEST",1,
                anchored["object_key"],anchored["object_digest"]))
            self.assertEqual(coordinator.publish_event_stream_checkpoint(
                external_anchor,"SYNERGY-TEST"),manifest)
            self.assertEqual({x["register_id"] for x in group["events"]},set(PARTICIPANTS))
            movements=movements_from_event_groups((group,))
            sender=PositionIdentity(**identity_out); receiver=PositionIdentity(**identity_in)
            physical_openings=(OpeningPosition(sender,1,D("10"),"OPEN-SENDER"),OpeningPosition(receiver,1,D("0"),"OPEN-RECEIVER"))
            physical_closings=(ClosingPosition(sender,1,D("5"),"CLOSE-SENDER"),ClosingPosition(receiver,1,D("5"),"CLOSE-RECEIVER"))
            financial_rows=[m for m in movements if m.identity.register_id=="financial"]
            financial_openings=tuple(OpeningPosition(m.identity,m.period_index,D("0"),"GOLD2A:synthetic-opening-v1") for m in financial_rows)
            financial_closings=tuple(ClosingPosition(m.identity,m.period_index,m.amount,"GOLD2A:bank-loan-origination") for m in financial_rows)
            openings=physical_openings+financial_openings
            closings=physical_closings+financial_closings
            reconciled=reconcile_periods(openings,movements,closings)
            self.assertEqual(coordinator.reconcile_event_stream(openings,closings),reconciled)
            self.assertTrue(verify_projection_replay(financial_store))
            self.assertEqual(financial_store.counts()["groups"],1)
            self.assertEqual(reconciled.mirror_group_count,1)

            # Re-open all six native stores and the coordinator as after a process restart.
            # The financial adapter must rebuild its in-memory journal from the durable group log.
            reopened_journal=EntityJournal(registry)
            reopened_financial_store=FinancialEventStore(root/"financial.sqlite3")
            reopened_financial=make_financial_participant(reopened_financial_store,reopened_journal,AUTH)
            self.assertIn(first_financial_event.event_id,reopened_journal.events)
            self.assertTrue(verify_projection_replay(reopened_financial_store))
            reopened_participants={
                "physical":make_physical_participant(PhysicalFlowStore(root/"physical.sqlite3"),AUTH),
                "capital":make_capital_participant(CapitalCohortStore(root/"capital.sqlite3"),AUTH),
                "product":make_product_participant(ProductRegister(root/"product.sqlite3"),AUTH),
                "labour":LabourRegister(root/"labour.sqlite3"),
                "legal_rights":LegalRightsRegister(root/"rights.sqlite3"),
                "financial":reopened_financial,
            }
            reopened_coordinator=CrossRegisterCoordinator(root/"coordinator.sqlite3",reopened_participants)
            self.assertTrue(reopened_coordinator.is_visible("TX-NATIVE-5"))
            replayed_group=reopened_coordinator.committed_event_group("TX-NATIVE-5")
            self.assertEqual(reopened_coordinator.iter_committed_event_groups(),[group])
            self.assertEqual(reopened_coordinator.latest_event_group_checkpoint(),checkpoint)
            self.assertEqual(replayed_group["common_event_id"],group["common_event_id"])
            self.assertEqual({x["register_id"] for x in replayed_group["events"]},set(PARTICIPANTS))

    def test_native_append_before_receipt_is_recovered_idempotently(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=PhysicalFlowStore(Path(tmp)/"physical.sqlite3")
            participant=make_physical_participant(store,AUTH)
            outflow,inflow=flow_pair("FLOW-CRASH")
            outdict=asdict(outflow); outdict["quantity"]=str(outdict["quantity"]); outdict["uncertainty"]=str(outdict["uncertainty"])
            indict=asdict(inflow); indict["quantity"]=str(indict["quantity"]); indict["uncertainty"]=str(indict["uncertainty"])
            operation={"stream_id":"physical","native_event_id":"FLOW-CRASH","expected_revision":0,
                "payload":envelope("physical.flow_recorded",{"outflow":outdict,"inflow":indict},"FLOW-CRASH")}
            token=participant.prepare("TX-CRASH-AFTER-APPEND",operation)
            native_append=participant.applier
            def crash_after_native_append(native_id,event_envelope,txid):
                native_append(native_id,event_envelope,txid)
                raise RuntimeError("simulated process loss after native append and before receipt")
            participant.applier=crash_after_native_append
            with self.assertRaisesRegex(RuntimeError,"before receipt"):
                participant.commit("TX-CRASH-AFTER-APPEND",token)
            self.assertEqual(store.flow_count(),1)
            self.assertEqual(participant.status("TX-CRASH-AFTER-APPEND")["state"],"PREPARED")
            restarted=make_physical_participant(store,AUTH)
            receipt=restarted.commit("TX-CRASH-AFTER-APPEND",token)
            self.assertEqual(restarted.status("TX-CRASH-AFTER-APPEND")["state"],"COMMITTED")
            self.assertEqual(restarted.event_count("TX-CRASH-AFTER-APPEND"),1)
            self.assertEqual(store.flow_count(),1)
            self.assertEqual(receipt["native_event_id"],"FLOW-CRASH")

    def test_prepared_capital_stream_blocks_direct_period_append_until_abort(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=CapitalCohortStore(Path(tmp)/"capital.sqlite3")
            store.initialize((CapitalCohort("C1","cell-1","machine",2026,0,1,1,"operating",1,1,1),))
            participant=make_capital_participant(store,AUTH)
            op={"stream_id":"capital","native_event_id":"CAPITAL-PERIOD:2026","expected_revision":0,
                "payload":envelope("capital.period_appended",{"period":2026,"events":[],"additions":[]},"CAPITAL-PERIOD:2026")}
            participant.prepare("TX-CAPITAL-RESERVED",op)
            from capital_cohort_store import CapitalCohortStoreError
            with self.assertRaises(CapitalCohortStoreError): store.append_period(2026,(),())
            participant.abort("TX-CAPITAL-RESERVED")
            self.assertIsNone(store.current_state().last_processed_period)

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
            self.assertEqual(store.flow_count(),0)
            self.assertIsNotNone(token)


if __name__=="__main__": unittest.main(verbosity=2)
