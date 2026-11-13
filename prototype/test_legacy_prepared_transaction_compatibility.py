"""Compatibility of durable v0 PREPARED records after envelope v1 rollout."""
import hashlib
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cross_register_coordinator import CrossRegisterCoordinator, PARTICIPANTS, _canonical
from native_store_participants import NativeStoreParticipant
from register_event_contract import normalize_event_envelope

T = "2026-11-13T07:00:00Z"


def legacy(register):
    return {
        "event_type": "domain.event", "effective_at": T, "recorded_at": T,
        "actor_id": "coordinator", "authority_ref": "AUTH:COORDINATOR",
        "idempotency_key": f"event-{register}", "payload": {"quantity": "1.25", "unit": "t"},
        "no_stock_flow_effect": "compatibility fixture",
    }


class _Store:
    def __init__(self, path):
        self.path = str(path)

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        return con


class _Adapter:
    authoritative_domain_adapter = True

    def __init__(self, name):
        self.name = name


class LegacyPreparedCompatibilityTests(unittest.TestCase):
    def test_native_prepare_retries_v0_and_v1_without_rewriting_receipt(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = _Store(Path(tmp) / "native.sqlite3")
            participant = NativeStoreParticipant(
                "physical", store, "physical", lambda con: 0,
                lambda *args: None, lambda *args: None, lambda *args: False,
                lambda *args: True,
            )
            source = legacy("physical")
            op = {"stream_id": "physical", "native_event_id": "NATIVE-1",
                  "expected_revision": 0, "payload": source}
            raw = _canonical(source)
            digest = hashlib.sha256(raw.encode()).hexdigest()
            token = participant._token("TX-V0", op, digest)
            with store._connect() as con:
                con.execute(
                    "INSERT INTO native_participant_inbox VALUES(?,?,?,?,?,?,?,'PREPARED',NULL)",
                    ("TX-V0", "physical", "NATIVE-1", digest, raw, 0, token),
                )

            self.assertEqual(participant.prepare("TX-V0", op), token)
            upgraded = normalize_event_envelope("physical", source)
            self.assertEqual(participant.prepare("TX-V0", op | {"payload": upgraded}), token)
            with store._connect() as con:
                row = con.execute(
                    "SELECT payload_json,payload_digest,prepare_token,state FROM native_participant_inbox WHERE transaction_id='TX-V0'"
                ).fetchone()
            self.assertEqual(tuple(row), (raw, digest, token, "PREPARED"))

    def test_real_labour_and_legal_rights_registers_retry_v0_prepared_rows(self):
        from labour_register import LabourRegister
        from legal_rights_register import LegalRightsRegister

        with tempfile.TemporaryDirectory() as tmp:
            registers = {
                "labour": LabourRegister(Path(tmp) / "labour.sqlite3"),
                "legal_rights": LegalRightsRegister(Path(tmp) / "legal-rights.sqlite3"),
            }
            for name, participant in registers.items():
                txid = f"TX-V0-{name.upper()}"
                stream = "ENG-1" if name == "labour" else "RIGHT-1"
                native_id = f"NATIVE-{name.upper()}-1"
                source = legacy(name)
                operation = {"stream_id": stream, "native_event_id": native_id,
                             "expected_revision": 0, "payload": source}
                raw = _canonical(source)
                token, digest = participant._participant_token(txid, operation)
                with participant._connect() as con:
                    con.execute(
                        "INSERT INTO native_participant_inbox VALUES(?,?,?,?,?,?,?,'PREPARED',NULL)",
                        (txid, stream, native_id, digest, raw, 0, token),
                    )

                upgraded = normalize_event_envelope(name, source)
                self.assertEqual(participant.prepare(
                    txid, operation | {"payload": upgraded}), token)
                with participant._connect() as con:
                    row = con.execute(
                        "SELECT payload_json,payload_digest,prepare_token,state "
                        "FROM native_participant_inbox WHERE transaction_id=?", (txid,)
                    ).fetchone()
                self.assertEqual(tuple(row), (raw, digest, token, "PREPARED"))


    def test_v0_preparing_transaction_recovers_through_all_six_real_native_registers(self):
        from dataclasses import asdict
        from decimal import Decimal as D
        import sqlite3
        import sys
        from physical_flow_store import PhysicalFlowStore
        from capital_cohort_bridge import CapitalCohort
        from capital_cohort_store import CapitalCohortStore
        from product_register import ProductRegister
        from financial_event_store import FinancialEventStore
        from entity_journal import EntityJournal
        from sfc_projection_registry import activate_sfc_projection
        from sfc_projection_store import activate_control_openings
        from native_store_participants import (
            make_physical_participant, make_capital_participant, make_product_participant,
            make_financial_participant, financial_stock_flow_movement_specs,
        )
        from cross_register_coordinator import CrossRegisterCoordinator
        from test_native_store_participants import AUTH, T, flow_pair, envelope, AUDIT_DIR, _corpus_events
        sys.path.insert(0, str(AUDIT_DIR))
        from financial_journal_adapter import _event_payload

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            physical = PhysicalFlowStore(root / "physical.sqlite3")
            capital = CapitalCohortStore(root / "capital.sqlite3")
            capital.initialize((CapitalCohort("C1","cell-1","machine",2026,0,1,1,"operating",1,1,1),))
            product = ProductRegister(root / "product.sqlite3")
            financial_store = FinancialEventStore(root / "financial.sqlite3")
            registry, corpus_events = _corpus_events()
            journal = EntityJournal(registry)
            corpus = json.loads((AUDIT_DIR / "SFC_GOLD_2A_CORPUS.json").read_text(encoding="utf-8"))
            opening = corpus["opening_snapshot"]
            self.assertTrue(activate_sfc_projection(financial_store, opening["rows"],
                mapper_version=opening["mapper_version"], evidence_ref=opening["evidence_ref"]))
            controls = (
                {"control_id":"impairment_allowance","entity_id":"bank-1","sector":"CB","currency":"LCU",
                 "valuation_basis":"NOMINAL","period":0,"amount":"0","evidence_ref":opening["evidence_ref"]},
                {"control_id":"writeoff_memorandum","entity_id":"bank-1","sector":"CB","currency":"LCU",
                 "valuation_basis":"NOMINAL","period":0,"amount":"0","evidence_ref":opening["evidence_ref"]},
            )
            self.assertTrue(activate_control_openings(financial_store, controls,
                mapper_version="gold2a-controls@1", evidence_ref=opening["evidence_ref"]))
            labour = LabourRegister(root / "labour.sqlite3")
            labour.bootstrap_admin(principal_id="labour-root",authority_ref="BOOTSTRAP:L",occurred_at=T)
            labour.grant_access(event_id="L-ACL",idempotency_key="L-ACL",principal_id="coordinator",
                permissions=["labour:read","labour:write"],actor_id="labour-root",
                authority_ref="POLICY:L",occurred_at=T)
            rights = LegalRightsRegister(root / "rights.sqlite3")
            rights.bootstrap_admin(principal_id="rights-root",authority_ref="BOOTSTRAP:R",occurred_at=T)
            rights.grant_access(event_id="R-ACL",idempotency_key="R-ACL",principal_id="coordinator",
                permissions=["legal_rights:read","legal_rights:write","legal_rights:adjudicate"],
                actor_id="rights-root",authority_ref="POLICY:R",occurred_at=T)

            participants = {
                "physical": make_physical_participant(physical, AUTH),
                "capital": make_capital_participant(capital, AUTH),
                "labour": labour,
                "product": make_product_participant(product, AUTH),
                "legal_rights": rights,
                "financial": make_financial_participant(financial_store, journal, AUTH),
            }
            coordinator = CrossRegisterCoordinator(root / "coordinator.sqlite3", participants,
                require_authoritative_adapters=True)

            outflow, inflow = flow_pair("FLOW-V0", "5")
            outdict = asdict(outflow); outdict["quantity"] = str(outdict["quantity"]); outdict["uncertainty"] = str(outdict["uncertainty"])
            indict = asdict(inflow); indict["quantity"] = str(indict["quantity"]); indict["uncertainty"] = str(indict["uncertainty"])
            identity_out = {"register_id":"physical","position_id":"mine:steel:S235","measure":"mass","unit":"t",
                "currency":"NA","valuation_basis":"PHYSICAL","holder_id":"mine","issuer_id":"mill","instrument_id":"steel:S235"}
            identity_in = {**identity_out,"position_id":"mill:steel:S235","holder_id":"mill","issuer_id":"mine"}
            movements = [
                {"movement_id":"FLOW-V0:OUT","identity":identity_out,"period_index":1,"movement_class":"T",
                 "amount":"-5","evidence_ref":"WEIGHBRIDGE-V0","mirror_group_id":"FLOW-V0","mirror_side":"sender","mirror_policy":"opposite"},
                {"movement_id":"FLOW-V0:IN","identity":identity_in,"period_index":1,"movement_class":"T",
                 "amount":"5","evidence_ref":"WEIGHBRIDGE-V0","mirror_group_id":"FLOW-V0","mirror_side":"receiver","mirror_policy":"opposite"},
            ]
            first_financial_event = corpus_events[0]
            financial_movements = financial_stock_flow_movement_specs((first_financial_event,))
            operations = {
                "physical":{"stream_id":"physical","native_event_id":"FLOW-V0","expected_revision":0,
                    "payload":envelope("physical.flow_recorded",{"outflow":outdict,"inflow":indict},"FLOW-V0") | {"stock_flow_movements":movements}},
                "capital":{"stream_id":"capital","native_event_id":"CAPITAL-PERIOD:2026","expected_revision":0,
                    "payload":envelope("capital.period_appended",{"period":2026,"events":[],"additions":[]},"CAPITAL-PERIOD:2026") | {"no_stock_flow_effect":"empty cohort period batch"}},
                "labour":{"stream_id":"ENG-1","native_event_id":"LABOUR-V0","expected_revision":0,
                    "payload":envelope("engagement.offered",{"person_ref":"PSEUDO-1","activity_id":"work","period":"P1",
                        "classification":"paid","consent_basis":"CONTRACT-1","planned_hours":"2"},"LABOUR-V0") | {"no_stock_flow_effect":"offer only; no delivered labour or accrued compensation"}},
                "product":{"stream_id":"product","native_event_id":"SPEC:steel:S235","expected_revision":0,
                    "payload":envelope("product_spec",{"product_id":"steel","grade_id":"S235","dimension":"mass",
                        "native_unit":"t","stockability":"stockable","time_basis":"period_flow","evidence_ref":"SPEC-V0"},
                        "SPEC:steel:S235") | {"no_stock_flow_effect":"specification metadata only; no position movement"}},
                "legal_rights":{"stream_id":"RIGHT-1","native_event_id":"RIGHT-V0","expected_revision":0,
                    "payload":envelope("right.created",{"holder_id":"ORG-A","obligor_id":"ORG-B","right_type":"claim",
                        "scope":"invoice:1","jurisdiction":"KZ","legal_instrument_ref":"CONTRACT-V0",
                        "effective_from":T,"evidence_refs":["SIGNED-V0"]},"RIGHT-V0") | {"no_stock_flow_effect":"legal claim recorded; no recognized financial posting"}},
                "financial":{"stream_id":"financial","native_event_id":"FIN-GROUP-V0","expected_revision":0,
                    "payload":envelope("financial.event_group_committed",{"group_id":"FIN-GROUP-V0",
                        "causation_id":"SCENARIO-V0","events":[_event_payload(first_financial_event)]},
                        "FIN-GROUP-V0") | {"stock_flow_movements":financial_movements}},
            }

            txid, scenario, causation = "TX-LEGACY-V0-SIX", "SCENARIO-V0", "CAUSE-V0"
            old_envelope = {"transaction_id":txid,"scenario_id":scenario,"causation_id":causation,
                            "schema_version":1,"participants":[]}
            old_rows = []
            historical = {}
            for name in ("physical","capital","labour","product","legal_rights","financial"):
                operation = operations[name]
                raw = _canonical(operation["payload"])
                digest = hashlib.sha256(raw.encode()).hexdigest()
                if hasattr(participants[name], "_token"):
                    token = participants[name]._token(txid, operation, digest)
                    store = participants[name].store
                else:
                    token, participant_digest = participants[name]._participant_token(txid, operation)
                    self.assertEqual(participant_digest, digest)
                    store = participants[name]
                with store._connect() as con:
                    con.execute("INSERT INTO native_participant_inbox VALUES(?,?,?,?,?,?,?,'PREPARED',NULL)",
                        (txid,operation["stream_id"],operation["native_event_id"],digest,raw,
                         operation["expected_revision"],token))
                old_envelope["participants"].append({
                    "name":name,"stream_id":operation["stream_id"],"native_event_id":operation["native_event_id"],
                    "expected_revision":operation["expected_revision"],"payload_digest":digest,
                    "event_schema_id":None,"event_schema_version":None,
                })
                old_rows.append((txid,name,operation["stream_id"],operation["native_event_id"],raw,digest,
                                 operation["expected_revision"],"PREPARED",token,None))
                historical[name] = (raw,digest,token)

            old_json = _canonical(old_envelope)
            old_digest = hashlib.sha256(old_json.encode()).hexdigest()
            with sqlite3.connect(root / "coordinator.sqlite3") as con:
                con.execute("INSERT INTO coordinator_transactions VALUES(?,?,?,'PREPARING')",
                    (txid,old_json,old_digest))
                con.execute("INSERT INTO coordinator_transitions(transaction_id,from_state,to_state,reason) "
                            "VALUES(?,NULL,'PREPARING','legacy-v0-fixture')",(txid,))
                con.executemany(
                    "INSERT INTO coordinator_operations(transaction_id,participant,stream_id,native_event_id,"
                    "payload_json,payload_digest,expected_revision,state,prepare_token,receipt_json) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?)", old_rows)

            self.assertFalse(coordinator.submit(txid,scenario,causation,operations))
            self.assertEqual(coordinator.state(txid),"PREPARING")
            self.assertEqual(coordinator.execute(txid),"COMMITTED")
            self.assertTrue(coordinator.is_visible(txid))
            self.assertEqual(physical.flow_count(),1)
            self.assertEqual(capital.current_state().last_processed_period,2026)
            self.assertTrue(product.verify())
            self.assertEqual(labour.state("ENG-1",principal_id="labour-root")[0]["status"],"OFFERED")
            self.assertEqual(rights.state("RIGHT-1",principal_id="rights-root")[0]["holder_id"],"ORG-A")
            self.assertTrue(financial_store.integrity_check())

            for name, participant in participants.items():
                status = participant.status(txid)
                self.assertEqual(status["state"],"COMMITTED",name)
                self.assertEqual(participant.event_count(txid),1,name)
                self.assertEqual(participant.committed_event(txid)["payload_json"],historical[name][0],name)
                with (participant.store if hasattr(participant,"store") else participant)._connect() as con:
                    row = con.execute("SELECT payload_json,payload_digest,prepare_token,state FROM native_participant_inbox WHERE transaction_id=?",
                                      (txid,)).fetchone()
                self.assertEqual((row["payload_json"],row["payload_digest"],row["prepare_token"]),
                                 historical[name],name)
                self.assertEqual(row["state"],"COMMITTED",name)


    def test_coordinator_submit_accepts_semantic_v0_retry_without_mutation(self):
        with tempfile.TemporaryDirectory() as tmp:
            participants = {name: _Adapter(name) for name in PARTICIPANTS}
            db = Path(tmp) / "coordinator.sqlite3"
            coordinator = CrossRegisterCoordinator(db, participants, require_authoritative_adapters=True)
            txid, scenario, causation = "TX-V0", "SCENARIO-1", "CAUSE-1"
            old_envelope = {
                "transaction_id": txid, "scenario_id": scenario, "causation_id": causation,
                "schema_version": 1, "participants": [],
            }
            old_rows = []
            upgraded_ops = {}
            for name in PARTICIPANTS:
                payload = legacy(name)
                raw = _canonical(payload)
                digest = hashlib.sha256(raw.encode()).hexdigest()
                old_envelope["participants"].append({
                    "name": name, "stream_id": name, "native_event_id": f"EVENT-{name}",
                    "expected_revision": 0, "payload_digest": digest,
                    "event_schema_id": None, "event_schema_version": None,
                })
                old_rows.append((txid, name, name, f"EVENT-{name}", raw, digest, 0, "PREPARED", f"TOKEN-{name}", None))
                upgraded_ops[name] = {
                    "stream_id": name, "native_event_id": f"EVENT-{name}", "expected_revision": 0,
                    "payload": normalize_event_envelope(name, payload),
                }
            old_json = _canonical(old_envelope)
            old_digest = hashlib.sha256(old_json.encode()).hexdigest()
            with sqlite3.connect(db) as con:
                con.execute(
                    "INSERT INTO coordinator_transactions VALUES(?,?,?,'PREPARING')",
                    (txid, old_json, old_digest),
                )
                con.executemany(
                    "INSERT INTO coordinator_operations(transaction_id,participant,stream_id,native_event_id,payload_json,payload_digest,expected_revision,state,prepare_token,receipt_json) VALUES(?,?,?,?,?,?,?,?,?,?)",
                    old_rows,
                )

            self.assertFalse(coordinator.submit(txid, scenario, causation, upgraded_ops))
            with sqlite3.connect(db) as con:
                rows = con.execute(
                    "SELECT participant,payload_json,payload_digest,prepare_token FROM coordinator_operations ORDER BY participant"
                ).fetchall()
            self.assertEqual(len(rows), 6)
            for name, raw, digest, token in rows:
                self.assertEqual(raw, _canonical(legacy(name)))
                self.assertEqual(digest, hashlib.sha256(raw.encode()).hexdigest())
                self.assertEqual(token, f"TOKEN-{name}")

            changed = dict(upgraded_ops)
            changed["physical"] = dict(upgraded_ops["physical"])
            changed["physical"]["payload"] = dict(upgraded_ops["physical"]["payload"])
            changed["physical"]["payload"]["payload"] = {"quantity": "9", "unit": "t"}
            with self.assertRaisesRegex(ValueError, "changed or unverifiable envelope"):
                coordinator.submit(txid, scenario, causation, changed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
