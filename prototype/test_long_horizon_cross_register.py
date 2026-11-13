"""Eight-transaction native-domain lifecycle, correction and replay integration."""
from dataclasses import asdict, replace
from decimal import Decimal as D
import base64
import hashlib
import json
import sqlite3
import tempfile
import time
import unittest

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from pathlib import Path

from physical_flow_store import PhysicalFlowStore
from capital_cohort_bridge import CapitalCohort
from capital_cohort_store import CapitalCohortStore
from product_register import ProductRegister
from financial_event_store import FinancialEventStore
from entity_journal import EntityJournal
from sfc_projection_registry import activate_sfc_projection
from sfc_projection_store import activate_control_openings, verify_projection_replay
from labour_register import LabourRegister
from legal_rights_register import LegalRightsRegister
from cross_register_coordinator import CrossRegisterCoordinator
from native_store_participants import (
    make_physical_participant, make_capital_participant, make_product_participant,
    make_financial_participant, financial_stock_flow_movement_specs,
)
from economic_stock_flow_reconciliation import (
    PositionIdentity, OpeningPosition, ClosingPosition, movements_from_event_groups, reconcile_periods,
)
from test_native_store_participants import AUTH, T, envelope, flow_pair, _corpus_events, _event_payload, AUDIT_DIR
from signed_approval_assertions import SignedApprovalVerifier, encode_assertion_payload


def _signed_governance_approval(context, private_key, *, subject, role, jti):
    now=int(time.time())
    header={"alg":"EdDSA","kid":"period-governance-integration-key","typ":"JWT"}
    header_segment=base64.urlsafe_b64encode(json.dumps(
        header,sort_keys=True,separators=(",",":")).encode()).decode().rstrip("=")
    claims={
        "iss":"https://identity.synergy.example",
        "sub":subject,
        "aud":"synergy-period-governance",
        "service_id":context["service_id"],
        "request_id":context["request_id"],
        "request_digest":context["request_digest"],
        "role":role,
        "evidence_ref":context["evidence_ref"],
        "jti":jti,
        "iat":now-5,
        "exp":now+120,
    }
    payload_segment=encode_assertion_payload(claims)
    signing_input=header_segment+"."+payload_segment
    signature=base64.urlsafe_b64encode(
        private_key.sign(signing_input.encode("ascii"))).decode().rstrip("=")
    return signing_input+"."+signature


class LongHorizonNativeCrossRegisterTests(unittest.TestCase):
    def test_eight_native_transactions_include_compensations_corrections_and_full_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            import hashlib, sqlite3

            def canonical(value):
                return json.dumps(value, sort_keys=True, separators=(",",":"),
                                  ensure_ascii=False, allow_nan=False)

            def sha(value):
                return hashlib.sha256(value.encode("utf-8")).hexdigest()

            def sqlite_state_hash(database):
                with sqlite3.connect(database) as con:
                    table_names=[row[0] for row in con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
                    inventory=[]
                    for table in table_names:
                        quoted='"'+table.replace('"','""')+'"'
                        columns=con.execute(f"PRAGMA table_info({quoted})").fetchall()
                        primary=sorted((row[5],row[1]) for row in columns if row[5])
                        order=[name for _,name in primary] or [row[1] for row in columns]
                        order_sql=",".join('"'+name.replace('"','""')+'"' for name in order)
                        rows=con.execute(f"SELECT * FROM {quoted} ORDER BY {order_sql}").fetchall()
                        inventory.append({"table":table,"rows":[
                            [value.hex() if isinstance(value,bytes) else value for value in row] for row in rows]})
                return sha(canonical(inventory))
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

            participants={
                "physical":make_physical_participant(physical,AUTH),
                "capital":make_capital_participant(capital,AUTH),
                "labour":labour,
                "product":make_product_participant(product,AUTH),
                "legal_rights":rights,
                "financial":make_financial_participant(financial_store,journal,AUTH),
            }
            coordinator=CrossRegisterCoordinator(root/"coordinator.sqlite3",participants,
                require_authoritative_adapters=True)
            database_paths={
                "physical":root/"physical.sqlite3","capital":root/"capital.sqlite3",
                "labour":root/"labour.sqlite3","product":root/"product.sqlite3",
                "legal_rights":root/"rights.sqlite3","financial":root/"financial.sqlite3",
            }
            # Capture the true period opening state before any of the eight
            # coordinated native transactions are submitted.
            opening_hashes={name:sqlite_state_hash(path) for name,path in database_paths.items()}

            mine_identity={"register_id":"physical","position_id":"mine:steel:S235","measure":"mass","unit":"t",
                "currency":"NA","valuation_basis":"PHYSICAL","holder_id":"mine","issuer_id":"mill","instrument_id":"steel:S235"}
            mill_identity={**mine_identity,"position_id":"mill:steel:S235","holder_id":"mill","issuer_id":"mine"}
            product_identity={"register_id":"product","position_id":"steel:S235:inventory","measure":"mass","unit":"t",
                "currency":"NA","valuation_basis":"PHYSICAL","holder_id":"national-warehouse","issuer_id":"producers",
                "instrument_id":"steel:S235"}
            labour_identity={"register_id":"labour","position_id":"ENG-1:delivered-hours","measure":"time","unit":"hour",
                "currency":"NA","valuation_basis":"TIME","holder_id":"PSEUDO-1","issuer_id":"ORG-A","instrument_id":"ENG-1"}

            product_events=[
                ("product_spec","SPEC:steel:S235",{"product_id":"steel","grade_id":"S235","dimension":"mass",
                    "native_unit":"t","stockability":"stockable","time_basis":"period_stock","evidence_ref":"SPEC-STEEL-1"},None),
                ("product_balance","BALANCE-1",{"balance_id":"BALANCE-1","product_id":"steel","grade_id":"S235",
                    "period":"P1","period_index":1,"boundary":"national","unit":"t","opening":"0","output":"10",
                    "imports":"0","intermediate":"0","final":"0","gfcf":"0","exports":"0","losses":"0",
                    "closing":"10","evidence_ref":"STOCKTAKE-P1"},("PRODUCT:P1","10",1,None)),
                ("price_quote","PRICE-1",{"price_id":"PRICE-1","product_id":"steel","grade_id":"S235","price":"2",
                    "denominator_unit":"t","currency":"LCU","period":"P1","valuation_basis":"NOMINAL",
                    "source_id":"MARKET-P1","evidence_ref":"PRICE-EVIDENCE-P1"},None),
                ("valuation","VALUATION-1",{"valuation_id":"VALUATION-1","balance_id":"BALANCE-1","price_id":"PRICE-1",
                    "quantity_component":"closing","value":"20","evidence_ref":"VALUATION-P1"},None),
                ("product_balance","BALANCE-2",{"balance_id":"BALANCE-2","product_id":"steel","grade_id":"S235",
                    "period":"P2","period_index":2,"boundary":"national","unit":"t","opening":"10","output":"5",
                    "imports":"0","intermediate":"0","final":"0","gfcf":"0","exports":"0","losses":"0",
                    "closing":"15","evidence_ref":"STOCKTAKE-P2"},("PRODUCT:P2","5",2,None)),
                ("price_quote","PRICE-2",{"price_id":"PRICE-2","product_id":"steel","grade_id":"S235","price":"3",
                    "denominator_unit":"t","currency":"LCU","period":"P2","valuation_basis":"NOMINAL",
                    "source_id":"MARKET-P2","evidence_ref":"PRICE-EVIDENCE-P2"},None),
                ("valuation","VALUATION-2",{"valuation_id":"VALUATION-2","balance_id":"BALANCE-2","price_id":"PRICE-2",
                    "quantity_component":"closing","value":"45","evidence_ref":"VALUATION-P2"},None),
                ("product_balance","BALANCE-3",{"balance_id":"BALANCE-3","product_id":"steel","grade_id":"S235",
                    "period":"P3","period_index":3,"boundary":"national","unit":"t","opening":"15","output":"0",
                    "imports":"0","intermediate":"0","final":"0","gfcf":"0","exports":"0","losses":"2",
                    "closing":"13","evidence_ref":"CORRECTED-STOCKTAKE-P3"},("PRODUCT:P3","-2",3,"PRODUCT:P2")),
            ]

            labour_events=[
                ("engagement.offered","LABOUR-E1",{"person_ref":"PSEUDO-1","activity_id":"steel-production",
                    "period":"P1","classification":"paid","consent_basis":"CONTRACT-L1","planned_hours":"4"}),
                ("engagement.accepted","LABOUR-E2",{"accepted_hours":"4","consent_ref":"CONSENT-L1"}),
                ("engagement.scheduled","LABOUR-E3",{"scheduled_hours":"4"}),
                ("engagement.started","LABOUR-E4",{}),
                ("engagement.delivered","LABOUR-E5",{"delivered_hours":"3.5","evidence_ref":"TIMESHEET-L1"}),
                ("engagement.verified","LABOUR-E6",{"verification_ref":"VERIFIED-TIMESHEET-L1"}),
                ("engagement.settled","LABOUR-E7",{"settled_hours":"3.5","settlement_ref":"PAYROLL-L1"}),
                ("hours.corrected","LABOUR-E8",{"corrects_event_id":"LABOUR-E5","delta_hours":"-0.5",
                    "reason":"Duplicate interval removed","settlement_adjustment_ref":"PAYROLL-ADJUSTMENT-L1"}),
            ]
            rights_events=[
                ("right.created","RIGHT-E1",{"holder_id":"ORG-A","obligor_id":"ORG-B","right_type":"receivable",
                    "scope":"invoice:100","jurisdiction":"KZ","legal_instrument_ref":"CONTRACT-100",
                    "effective_from":T,"evidence_refs":["SIGNED-CONTRACT","DELIVERY-RECEIPT"]}),
                ("right.evidence_attached","RIGHT-E2",{"evidence_ref":"LATE-DELIVERY-RECEIPT"}),
                ("right.transferred","RIGHT-E3",{"from_holder_id":"ORG-A","to_holder_id":"ORG-C",
                    "transfer_instrument_ref":"ASSIGNMENT-1","evidence_ref":"ASSIGNMENT-NOTICE-1"}),
                ("right.encumbered","RIGHT-E4",{"encumbrance_id":"ENC-1","beneficiary_id":"BANK-1",
                    "scope":"invoice:100","priority":1,"instrument_ref":"PLEDGE-1","evidence_ref":"PLEDGE-EVIDENCE"}),
                ("right.released","RIGHT-E5",{"encumbrance_id":"ENC-1","release_instrument_ref":"RELEASE-1",
                    "evidence_ref":"RELEASE-EVIDENCE"}),
                ("right.disputed","RIGHT-E6",{"dispute_ref":"CASE-1","forum_ref":"COURT-1","evidence_ref":"CLAIM-1"}),
                ("right.adjudicated","RIGHT-E7",{"outcome":"upheld","decision_ref":"DECISION-1"}),
                ("right.corrected","RIGHT-E8",{"corrects_event_id":"RIGHT-E1","reason":"Late contractual scope evidence",
                    "evidence_ref":"CORRECTION-AUTHORITY-1","changes":{"scope":"invoice:100 plus accrued contractual interest"}}),
            ]
            financial_events=list(corpus_events)+[
                replace(corpus_events[1],event_id="G2A-LATE-INTEREST-ADJUSTMENT",effective_period=5)
            ]

            txids=[]
            for index in range(8):
                sequence=index+1
                flow_id=f"FLOW-{sequence}"
                reverse=sequence==8
                quantity="0.5" if reverse else "1"
                outflow,inflow=flow_pair(flow_id,quantity,reverse=reverse,period=f"P{sequence}")
                outdict=asdict(outflow); outdict["quantity"]=str(outdict["quantity"]); outdict["uncertainty"]=str(outdict["uncertainty"])
                indict=asdict(inflow); indict["quantity"]=str(indict["quantity"]); indict["uncertainty"]=str(indict["uncertainty"])
                sender_identity=mill_identity if reverse else mine_identity
                receiver_identity=mine_identity if reverse else mill_identity
                physical_movements=[
                    {"movement_id":f"{flow_id}:OUT","identity":sender_identity,"period_index":sequence,
                     "movement_class":"T","amount":str(-D(quantity)),"evidence_ref":f"WEIGHBRIDGE-{sequence}",
                     "mirror_group_id":flow_id,"mirror_side":"sender","mirror_policy":"opposite"},
                    {"movement_id":f"{flow_id}:IN","identity":receiver_identity,"period_index":sequence,
                     "movement_class":"T","amount":str(D(quantity)),"evidence_ref":f"WEIGHBRIDGE-{sequence}",
                     "mirror_group_id":flow_id,"mirror_side":"receiver","mirror_policy":"opposite"},
                ]
                if reverse:
                    physical_movements[0]["correction_of"]="FLOW-1:IN"
                    physical_movements[1]["correction_of"]="FLOW-1:OUT"

                capital_period=2025+sequence
                capital_id=f"CAPITAL-PERIOD:{capital_period}"
                product_type,product_id,product_payload,product_movement=product_events[index]
                product_metadata={"no_stock_flow_effect":"product specification, quote or valuation metadata only"}
                if product_movement is not None:
                    movement_id,amount,period_index,correction_of=product_movement
                    spec={"movement_id":movement_id,"identity":product_identity,"period_index":period_index,
                        "movement_class":"T","amount":amount,"evidence_ref":product_payload["evidence_ref"]}
                    if correction_of: spec["correction_of"]=correction_of
                    product_metadata={"stock_flow_movements":[spec]}

                labour_type,labour_id,labour_payload=labour_events[index]
                labour_metadata={"no_stock_flow_effect":"labour lifecycle transition without delivered time"}
                if index==4:
                    labour_metadata={"stock_flow_movements":[{"movement_id":"LABOUR:DELIVERED:5","identity":labour_identity,
                        "period_index":5,"movement_class":"T","amount":"3.5","evidence_ref":"TIMESHEET-L1"}]}
                elif index==7:
                    labour_metadata={"stock_flow_movements":[{"movement_id":"LABOUR:CORRECTION:8","identity":labour_identity,
                        "period_index":8,"movement_class":"T","amount":"-0.5","evidence_ref":"PAYROLL-ADJUSTMENT-L1",
                        "correction_of":"LABOUR:DELIVERED:5"}]}

                rights_type,rights_id,rights_payload=rights_events[index]
                financial_event=financial_events[index]
                financial_id=f"FIN-GROUP-{sequence}"
                financial_specs=financial_stock_flow_movement_specs((financial_event,))
                financial_metadata=({"stock_flow_movements":financial_specs} if financial_specs else
                    {"no_stock_flow_effect":"journal event has no instrument stock or valuation movement"})

                operations={
                    "physical":{"stream_id":"physical","native_event_id":flow_id,"expected_revision":index,
                        "payload":envelope("physical.flow_recorded",{"outflow":outdict,"inflow":indict},flow_id)|{
                            "stock_flow_movements":physical_movements}},
                    "capital":{"stream_id":"capital","native_event_id":capital_id,"expected_revision":index,
                        "payload":envelope("capital.period_appended",{"period":capital_period,"events":[],"additions":[]},capital_id)|{
                            "no_stock_flow_effect":"cohort period advanced without a cohort transition"}},
                    "product":{"stream_id":"product","native_event_id":product_id,"expected_revision":index,
                        "payload":envelope(product_type,product_payload,product_id)|product_metadata},
                    "labour":{"stream_id":"ENG-1","native_event_id":labour_id,"expected_revision":index,
                        "payload":envelope(labour_type,labour_payload,labour_id)|labour_metadata},
                    "legal_rights":{"stream_id":"RIGHT-1","native_event_id":rights_id,"expected_revision":index,
                        "payload":envelope(rights_type,rights_payload,rights_id)|{
                            "no_stock_flow_effect":"legal rights evidence/state transition without a recognized quantity movement"}},
                    "financial":{"stream_id":"financial","native_event_id":financial_id,"expected_revision":index,
                        "payload":envelope("financial.event_group_committed",{"group_id":financial_id,
                            "causation_id":financial_event.event_id,"events":[_event_payload(financial_event)]},financial_id)|financial_metadata},
                }
                txid=f"LONG-HORIZON-TX-{sequence}"
                self.assertTrue(coordinator.submit(txid,"LONG-HORIZON-2026",f"CAUSE-{sequence}",operations))
                self.assertEqual(coordinator.execute(txid),"COMMITTED")
                self.assertTrue(coordinator.is_visible(txid))
                txids.append(txid)

            groups=tuple(coordinator.iter_committed_event_groups())
            self.assertEqual(len(groups),8)
            self.assertTrue(all(event["event_schema_id"]=="synergy.native-register-event"
                and event["event_schema_version"]==1 for group in groups for event in group["events"]))
            movements=movements_from_event_groups(groups)

            openings=[]; closings=[]
            def add_series(identity,first,last,initial,selected):
                balance=D(str(initial))
                for period in range(first,last+1):
                    openings.append(OpeningPosition(identity,period,balance,f"OPEN:{identity.position_id}:{period}"))
                    delta=sum((row.amount for row in selected if row.identity==identity and row.period_index==period),D("0"))
                    balance+=delta
                    closings.append(ClosingPosition(identity,period,balance,f"CLOSE:{identity.position_id}:{period}"))

            mine=PositionIdentity(**mine_identity); mill=PositionIdentity(**mill_identity)
            add_series(mine,1,8,"10",movements)
            add_series(mill,1,8,"0",movements)
            product_position=PositionIdentity(**product_identity)
            add_series(product_position,1,3,"0",movements)
            labour_position=PositionIdentity(**labour_identity)
            add_series(labour_position,5,8,"0",movements)
            financial_positions=sorted({row.identity for row in movements if row.identity.register_id=="financial"})
            for identity in financial_positions:
                periods=[row.period_index for row in movements if row.identity==identity]
                add_series(identity,min(periods),max(periods),"0",movements)

            reconciled=reconcile_periods(tuple(openings),tuple(movements),tuple(closings))
            self.assertEqual(coordinator.reconcile_event_stream(tuple(openings),tuple(closings)),reconciled)
            self.assertGreaterEqual(reconciled.mirror_group_count,8)
            self.assertTrue(physical.verify()); self.assertEqual(physical.flow_count(),8)
            self.assertTrue(capital.verify()); self.assertEqual(capital.current_state().last_processed_period,2033)
            self.assertTrue(product.verify())
            labour_state,labour_version=labour.state("ENG-1",principal_id="labour-root")
            self.assertEqual((labour_state["status"],labour_state["delivered_hours"],labour_state["settled_hours"],labour_version),
                ("SETTLED","3.0","3.0",8))
            rights_state,rights_version=rights.state("RIGHT-1",principal_id="rights-root")
            self.assertEqual((rights_state["holder_id"],rights_state["scope"],rights_version),
                ("ORG-C","invoice:100 plus accrued contractual interest",8))
            self.assertTrue(labour.verify()); self.assertTrue(rights.verify())
            self.assertTrue(financial_store.integrity_check()); self.assertTrue(verify_projection_replay(financial_store))
            self.assertEqual(financial_store.counts()["groups"],8)
            self.assertEqual(coordinator.latest_event_group_checkpoint()["sequence"],8)

            reopened_journal=EntityJournal(registry)
            reopened_financial_store=FinancialEventStore(root/"financial.sqlite3")
            reopened_financial=make_financial_participant(reopened_financial_store,reopened_journal,AUTH)
            reopened_participants={
                "physical":make_physical_participant(PhysicalFlowStore(root/"physical.sqlite3"),AUTH),
                "capital":make_capital_participant(CapitalCohortStore(root/"capital.sqlite3"),AUTH),
                "labour":LabourRegister(root/"labour.sqlite3"),
                "product":make_product_participant(ProductRegister(root/"product.sqlite3"),AUTH),
                "legal_rights":LegalRightsRegister(root/"rights.sqlite3"),
                "financial":reopened_financial,
            }
            reopened=CrossRegisterCoordinator(root/"coordinator.sqlite3",reopened_participants,
                require_authoritative_adapters=True)
            for txid in txids: self.assertTrue(reopened.is_visible(txid))
            replayed=tuple(reopened.iter_committed_event_groups())
            self.assertEqual(replayed,groups)
            self.assertEqual(reopened.reconcile_event_stream(tuple(openings),tuple(closings)),reconciled)
            self.assertTrue(verify_projection_replay(reopened_financial_store))

            # Bind period close/reopen governance to replay-verified snapshots of
            # the six real authoritative SQLite stores, not synthetic receipt fixtures.
            from external_checkpoints import (
                Ed25519Signer, TrustedKeyRegistry, LocalImmutableAnchor,
                publish_checkpoint, verify_checkpoint, verify_backup_bytes, CheckpointError,
            )
            from period_governance import PeriodGovernance, REGISTERS

            generation_root=root/"period-2033-generation-1"
            generation_root.mkdir()
            generation_paths={}
            for name,source in database_paths.items():
                target=generation_root/f"{name}.sqlite3"
                with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
                    src.backup(dst)
                generation_paths[name]=target

            # Re-open each copied store through its real domain implementation and
            # force its native replay/integrity verifier before issuing a receipt.
            generation_stores={
                "physical":PhysicalFlowStore(generation_paths["physical"]),
                "capital":CapitalCohortStore(generation_paths["capital"]),
                "labour":LabourRegister(generation_paths["labour"]),
                "product":ProductRegister(generation_paths["product"]),
                "legal_rights":LegalRightsRegister(generation_paths["legal_rights"]),
                "financial":FinancialEventStore(generation_paths["financial"]),
            }
            self.assertTrue(generation_stores["physical"].verify())
            self.assertTrue(generation_stores["capital"].verify())
            self.assertTrue(generation_stores["labour"].verify())
            self.assertTrue(generation_stores["product"].verify())
            self.assertTrue(generation_stores["legal_rights"].verify())
            self.assertTrue(generation_stores["financial"].integrity_check())
            self.assertTrue(verify_projection_replay(generation_stores["financial"]))
            closing_hashes={name:sqlite_state_hash(path) for name,path in generation_paths.items()}
            for name in REGISTERS:
                self.assertEqual(closing_hashes[name],sqlite_state_hash(database_paths[name]))
                self.assertNotEqual(opening_hashes[name],closing_hashes[name])

            event_checkpoint=reopened.latest_event_group_checkpoint()
            self.assertEqual(event_checkpoint["sequence"],8)
            source_root=event_checkpoint["group_hash"]
            event_counts={
                "physical":8,
                "capital":8,
                "labour":generation_stores["labour"].total_event_count,
                "product":8,
                "legal_rights":generation_stores["legal_rights"].total_event_count,
                "financial":generation_stores["financial"].counts()["events"],
            }
            # The generation-0 closing snapshot is the true opening state for
            # a governed correction/rebuild, after the eight original transactions.
            opening_hashes={name:sqlite_state_hash(path) for name,path in database_paths.items()}
            closed_hashes=dict(opening_hashes)
            closed_source_root=source_root
            closed_event_counts=dict(event_counts)
            signer=Ed25519Signer.generate("synergy-period-test-key")
            trust=TrustedKeyRegistry({signer.key_id:signer.public_bytes()})
            anchor=LocalImmutableAnchor(root/"period-checkpoint-anchor.sqlite3")

            def make_checkpoint(generation, sequence, projection_hash, event_root,
                                snapshot_hashes, commit_sequence, event_count):
                # Hash the actual six-file SQLite backup artifact, not merely
                # a manifest of logical database-state hashes. The exact same
                # bytes are passed to verify_backup_bytes after signing.
                backup_bytes=canonical({
                    name:base64.b64encode(path.read_bytes()).decode("ascii")
                    for name,path in sorted(generation_paths.items())
                }).encode("utf-8")
                backup_digest=hashlib.sha256(backup_bytes).hexdigest()
                manifest={
                    "manifest_schema_version":1,"service_id":"SYNERGY-LONG-HORIZON-TEST",
                    "database_schema_version":4,"mapper_version":"gold2a-entity-journal-mapper@1",
                    "projection_generation":generation,"commit_sequence":commit_sequence,"event_count":event_count,
                    "event_log_root":event_root,
                    "instrument_opening_hash":sha(canonical(opening_hashes)),
                    "control_opening_hash":sha("period-2033-control-openings"),
                    "projection_state_hash":projection_hash,"coverage_count":event_count,
                    "applied_through_cursor":commit_sequence,"period":2033,"period_closed":True,
                    "backup_sha256":backup_digest,"checkpoint_sequence":sequence,
                    "created_at_utc":"2026-11-13T13:00:00Z","signer_key_id":signer.key_id,
                }
                return publish_checkpoint(manifest,signer,anchor)

            approval_private_key=Ed25519PrivateKey.generate()
            approval_public_key=approval_private_key.public_key().public_bytes(
                encoding=serialization.Encoding.Raw,format=serialization.PublicFormat.Raw)
            approval_verifier=SignedApprovalVerifier(
                root/"approval-assertion-replays.sqlite3",
                issuer="https://identity.synergy.example",
                audience="synergy-period-governance",
                key_resolver=lambda issuer,kid: (
                    approval_public_key if issuer=="https://identity.synergy.example"
                    and kid=="period-governance-integration-key" else None),
                is_revoked=lambda issuer,kid,jti: False,
            )
            governance=PeriodGovernance(
                root/"period-governance.sqlite3",
                lambda ref,digest:verify_checkpoint(ref,digest,trust,anchor,require_latest=False),
                "SYNERGY-LONG-HORIZON-TEST",
                approval_verifier,
            )
            close_ref,close_digest=make_checkpoint(
                0,0,sha("generation-0-projection"),closed_source_root,closed_hashes,8,8)
            close_manifest=verify_checkpoint(close_ref,close_digest,trust,anchor,require_latest=True)
            close_backup_artifact=canonical({
                name:base64.b64encode(path.read_bytes()).decode("ascii")
                for name,path in sorted(generation_paths.items())
            }).encode("utf-8")
            self.assertTrue(verify_backup_bytes(close_manifest,close_backup_artifact))
            with self.assertRaises(CheckpointError):
                verify_backup_bytes(close_manifest,close_backup_artifact+b"tampered")
            self.assertTrue(governance.close_period(2033,0,close_ref,close_digest,"period-controller"))
            self.assertFalse(governance.close_period(2033,0,close_ref,close_digest,"period-controller"))
            self.assertEqual(governance.active_generation(2033),0)
            with self.assertRaisesRegex(ValueError,"governed reopening"):
                governance.append_correction("CORR-CLOSED-1",2033,"FLOW-1",
                    "late correction","AUTH:PERIOD","EVIDENCE:CORR-1",{"delta":"-1"})

            scope=list(REGISTERS)
            self.assertTrue(governance.request_reopen(
                "REOPEN-LONG-HORIZON-2033",2033,"reconcile late labour and rights evidence",
                "EVIDENCE:REOPEN-2033",scope,close_ref,close_digest))
            with sqlite3.connect(root/"period-governance.sqlite3") as con:
                con.row_factory=sqlite3.Row
                request=con.execute(
                    "SELECT * FROM reopen_requests WHERE request_id=?",
                    ("REOPEN-LONG-HORIZON-2033",)).fetchone()
            approval_context={
                "service_id":"SYNERGY-LONG-HORIZON-TEST",
                "request_id":request["request_id"],"period":request["period"],
                "old_generation":request["old_generation"],"new_generation":request["new_generation"],
                "reason":request["reason"],"evidence_ref":request["evidence_ref"],
                "scope":json.loads(request["scope_json"]),
                "pre_reopen_checkpoint_ref":request["pre_reopen_checkpoint_ref"],
                "pre_reopen_checkpoint_digest":request["pre_reopen_checkpoint_digest"],
            }
            approval_context["request_digest"]=hashlib.sha256(
                canonical(approval_context).encode("utf-8")).hexdigest()
            owner_assertion=_signed_governance_approval(
                approval_context,approval_private_key,subject="person-A",
                role="period_owner",jti="reopen-2033-owner")
            self.assertTrue(governance.approve_reopen(
                "REOPEN-LONG-HORIZON-2033","person-A","period_owner",owner_assertion))
            self.assertFalse(governance.approve_reopen(
                "REOPEN-LONG-HORIZON-2033","person-A","period_owner",owner_assertion))
            same_person_assertion=_signed_governance_approval(
                approval_context,approval_private_key,subject="person-A",
                role="independent_controller",jti="reopen-2033-same-person")
            with self.assertRaisesRegex(ValueError,"two distinct people"):
                governance.approve_reopen(
                    "REOPEN-LONG-HORIZON-2033","person-A","independent_controller",
                    same_person_assertion)
            controller_assertion=_signed_governance_approval(
                approval_context,approval_private_key,subject="person-B",
                role="independent_controller",jti="reopen-2033-controller")
            self.assertTrue(governance.approve_reopen(
                "REOPEN-LONG-HORIZON-2033","person-B","independent_controller",
                controller_assertion))

            # Only after both independent approvals, append a real corrective
            # transaction through all six native participants.
            correction_flow_out,correction_flow_in=flow_pair("FLOW-9","0.25",reverse=True,period="P9")
            correction_out=asdict(correction_flow_out)
            correction_out["quantity"]=str(correction_out["quantity"])
            correction_out["uncertainty"]=str(correction_out["uncertainty"])
            correction_in=asdict(correction_flow_in)
            correction_in["quantity"]=str(correction_in["quantity"])
            correction_in["uncertainty"]=str(correction_in["uncertainty"])
            physical_correction_movements=[
                {"movement_id":"FLOW-9:OUT","identity":mill_identity,"period_index":9,
                 "movement_class":"T","amount":"-0.25","evidence_ref":"WEIGHBRIDGE-POST-CLOSE",
                 "mirror_group_id":"FLOW-9","mirror_side":"sender","mirror_policy":"opposite"},
                {"movement_id":"FLOW-9:IN","identity":mine_identity,"period_index":9,
                 "movement_class":"T","amount":"0.25","evidence_ref":"WEIGHBRIDGE-POST-CLOSE",
                 "mirror_group_id":"FLOW-9","mirror_side":"receiver","mirror_policy":"opposite"},
            ]
            post_close_financial_event=replace(
                corpus_events[1],event_id="G2A-POST-CLOSE-ADJUSTMENT",effective_period=9)
            post_close_financial_movements=financial_stock_flow_movement_specs(
                (post_close_financial_event,))
            correction_operations={
                "physical":{"stream_id":"physical","native_event_id":"FLOW-9","expected_revision":8,
                    "payload":envelope("physical.flow_recorded",{
                        "outflow":correction_out,"inflow":correction_in},"FLOW-9")|{
                        "stock_flow_movements":physical_correction_movements}},
                "capital":{"stream_id":"capital","native_event_id":"CAPITAL-PERIOD:2034","expected_revision":8,
                    "payload":envelope("capital.period_appended",{
                        "period":2034,"events":[],"additions":[]},"CAPITAL-PERIOD:2034")|{
                        "no_stock_flow_effect":"post-close period continuity marker"}},
                "labour":{"stream_id":"ENG-1","native_event_id":"LABOUR-E9","expected_revision":8,
                    "payload":envelope("hours.corrected",{
                        "corrects_event_id":"LABOUR-E5","delta_hours":"-0.25",
                        "reason":"Post-close timesheet reconciliation",
                        "settlement_adjustment_ref":"PAYROLL-ADJUSTMENT-L2"},"LABOUR-E9")|{
                        "stock_flow_movements":[{
                            "movement_id":"LABOUR:CORRECTION:9","identity":labour_identity,
                            "period_index":9,"movement_class":"T","amount":"-0.25",
                            "evidence_ref":"PAYROLL-ADJUSTMENT-L2",
                            "correction_of":"LABOUR:DELIVERED:5"}]}},
                "product":{"stream_id":"product","native_event_id":"PRICE-POST-CLOSE","expected_revision":8,
                    "payload":envelope("price_quote",{
                        "price_id":"PRICE-POST-CLOSE","product_id":"steel","grade_id":"S235",
                        "price":"3.5","denominator_unit":"t","currency":"LCU","period":"P4",
                        "valuation_basis":"NOMINAL","source_id":"MARKET-P4",
                        "evidence_ref":"PRICE-EVIDENCE-P4"},"PRICE-POST-CLOSE")|{
                        "no_stock_flow_effect":"post-close price evidence only"}},
                "legal_rights":{"stream_id":"RIGHT-1","native_event_id":"RIGHT-E9","expected_revision":8,
                    "payload":envelope("right.evidence_attached",{
                        "evidence_ref":"POST-CLOSE-LEGAL-EVIDENCE"},"RIGHT-E9")|{
                        "no_stock_flow_effect":"additional legal evidence; no recognized quantity movement"}},
                "financial":{"stream_id":"financial","native_event_id":"FIN-GROUP-9","expected_revision":8,
                    "payload":envelope("financial.event_group_committed",{
                        "group_id":"FIN-GROUP-9","causation_id":post_close_financial_event.event_id,
                        "events":[_event_payload(post_close_financial_event)]},"FIN-GROUP-9")|{
                        "stock_flow_movements":post_close_financial_movements}},
            }
            self.assertTrue(reopened.submit(
                "LONG-HORIZON-POST-CLOSE-TX-9","LONG-HORIZON-2026","CAUSE-POST-CLOSE-9",
                correction_operations))
            self.assertEqual(reopened.execute("LONG-HORIZON-POST-CLOSE-TX-9"),"COMMITTED")
            self.assertTrue(reopened.is_visible("LONG-HORIZON-POST-CLOSE-TX-9"))
            self.assertEqual(reopened.latest_event_group_checkpoint()["sequence"],9)
            self.assertEqual(physical.flow_count(),9)
            self.assertEqual(capital.current_state().last_processed_period,2034)
            corrected_labour,corrected_labour_version=labour.state("ENG-1",principal_id="labour-root")
            self.assertEqual((corrected_labour["delivered_hours"],corrected_labour["settled_hours"],
                              corrected_labour_version),("2.75","2.75",9))
            corrected_rights,_=rights.state("RIGHT-1",principal_id="rights-root")
            self.assertIn("POST-CLOSE-LEGAL-EVIDENCE",corrected_rights["evidence_refs"])
            self.assertEqual(financial_store.counts()["groups"],9)

            post_close_groups=tuple(reopened.iter_committed_event_groups())
            self.assertEqual(len(post_close_groups),9)
            post_close_movements=movements_from_event_groups(post_close_groups)
            openings=[]; closings=[]
            add_series(mine,1,9,"10",post_close_movements)
            add_series(mill,1,9,"0",post_close_movements)
            add_series(product_position,1,3,"0",post_close_movements)
            add_series(labour_position,5,9,"0",post_close_movements)
            post_close_financial_positions=sorted({
                row.identity for row in post_close_movements if row.identity.register_id=="financial"})
            for identity in post_close_financial_positions:
                periods=[row.period_index for row in post_close_movements if row.identity==identity]
                add_series(identity,min(periods),max(periods),"0",post_close_movements)
            post_close_reconciliation=reconcile_periods(
                tuple(openings),post_close_movements,tuple(closings))
            self.assertEqual(reopened.reconcile_event_stream(
                tuple(openings),tuple(closings)),post_close_reconciliation)

            # Re-copy the post-correction authoritative stores and replay them
            # independently before generating the six generation-1 receipts.
            for name,source in database_paths.items():
                target=generation_paths[name]
                with sqlite3.connect(source) as src, sqlite3.connect(target) as dst:
                    src.backup(dst)
            self.assertTrue(generation_stores["physical"].verify())
            self.assertTrue(generation_stores["capital"].verify())
            self.assertTrue(generation_stores["labour"].verify())
            self.assertTrue(generation_stores["product"].verify())
            self.assertTrue(generation_stores["legal_rights"].verify())
            self.assertTrue(generation_stores["financial"].integrity_check())
            self.assertTrue(verify_projection_replay(generation_stores["financial"]))
            closing_hashes={name:sqlite_state_hash(path) for name,path in generation_paths.items()}
            for name in REGISTERS:
                self.assertEqual(closing_hashes[name],sqlite_state_hash(database_paths[name]))
                self.assertNotEqual(opening_hashes[name],closing_hashes[name])

            event_checkpoint=reopened.latest_event_group_checkpoint()
            self.assertEqual(event_checkpoint["sequence"],9)
            source_root=event_checkpoint["group_hash"]
            event_counts={
                "physical":9,
                "capital":9,
                "labour":generation_stores["labour"].total_event_count,
                "product":9,
                "legal_rights":generation_stores["legal_rights"].total_event_count,
                "financial":generation_stores["financial"].counts()["events"],
            }

            for name in REGISTERS:
                reconciliation=sha(canonical({
                    "register":name,"source_event_root":source_root,"event_count":event_counts[name],
                    "opening_state_hash":opening_hashes[name],"closing_state_hash":closing_hashes[name],
                }))
                self.assertTrue(governance.record_rebuild(
                    "REOPEN-LONG-HORIZON-2033",name,source_root,event_counts[name],
                    opening_hashes[name],closing_hashes[name],reconciliation))

            receipt_commitment=[{
                "register_name":name,"old_generation":0,"new_generation":1,
                "source_event_root":source_root,"event_count":event_counts[name],
                "opening_state_hash":opening_hashes[name],"closing_state_hash":closing_hashes[name],
                "reconciliation_hash":sha(canonical({
                    "register":name,"source_event_root":source_root,"event_count":event_counts[name],
                    "opening_state_hash":opening_hashes[name],"closing_state_hash":closing_hashes[name],
                })),
            } for name in sorted(REGISTERS)]
            global_reconciliation=sha(canonical(receipt_commitment))
            generation_ref,generation_digest=make_checkpoint(
                1,1,global_reconciliation,source_root,closing_hashes,9,9)
            self.assertTrue(governance.publish_generation(
                "REOPEN-LONG-HORIZON-2033",global_reconciliation,generation_ref,generation_digest))
            generation_manifest=verify_checkpoint(
                generation_ref,generation_digest,trust,anchor,require_latest=True)
            generation_backup_artifact=canonical({
                name:base64.b64encode(path.read_bytes()).decode("ascii")
                for name,path in sorted(generation_paths.items())
            }).encode("utf-8")
            self.assertTrue(verify_backup_bytes(generation_manifest,generation_backup_artifact))
            with self.assertRaises(CheckpointError):
                verify_backup_bytes(generation_manifest,generation_backup_artifact+b"tampered")
            self.assertFalse(governance.publish_generation(
                "REOPEN-LONG-HORIZON-2033",global_reconciliation,generation_ref,generation_digest))
            self.assertEqual(governance.active_generation(2033),1)
            with sqlite3.connect(root/"period-governance.sqlite3") as con:
                history=con.execute(
                    "SELECT generation,checkpoint_ref FROM generation_history WHERE period=2033 ORDER BY generation"
                ).fetchall()
            self.assertEqual(history,[(0,close_ref),(1,generation_ref)])
            self.assertTrue(all(sqlite_state_hash(generation_paths[name])==closing_hashes[name] for name in REGISTERS))


if __name__=="__main__": unittest.main(verbosity=2)
