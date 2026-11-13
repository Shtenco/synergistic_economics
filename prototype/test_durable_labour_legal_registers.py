"""Acceptance tests for durable Labour and Legal Rights event registers."""
import sqlite3
import tempfile
import unittest
from pathlib import Path

from durable_event_register import RegisterError
from labour_register import LabourRegister, LabourRegisterError
from legal_rights_register import LegalRightsRegister, LegalRightsRegisterError
from cross_register_coordinator import CrossRegisterCoordinator, SQLiteParticipant, PARTICIPANTS

T = "2026-11-13T05:00:00Z"


class DurableLabourRegisterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = LabourRegister(Path(self.tmp.name) / "labour.sqlite3")
        self.store.bootstrap_admin(principal_id="root", authority_ref="BOOTSTRAP:POLICY-1", occurred_at=T)
        self.store.grant_access(event_id="ACL-LABOUR-WRITER", idempotency_key="ACL-LABOUR-WRITER",
            principal_id="worker-agent", permissions=["labour:read", "labour:write"],
            actor_id="root", authority_ref="POLICY:LABOUR-WRITER", occurred_at=T)
        self.store.grant_access(event_id="ACL-LABOUR-READER", idempotency_key="ACL-LABOUR-READER",
            principal_id="auditor", permissions=["labour:read"],
            actor_id="root", authority_ref="POLICY:LABOUR-READER", occurred_at=T)
        self.store.grant_access(event_id="ACL-LABOUR-ASSESSOR", idempotency_key="ACL-LABOUR-ASSESSOR",
            principal_id="assessor", permissions=["labour:read","labour:admin"],
            actor_id="root", authority_ref="POLICY:LABOUR-ASSESSOR", occurred_at=T)

    def tearDown(self): self.tmp.cleanup()

    def append(self, eid, typ, aggregate="ENG-1", payload=None, version=0):
        return self.store.append_event(event_id=eid,idempotency_key=eid,aggregate_id=aggregate,
            event_type=typ,effective_at=T,recorded_at=T,actor_id="worker-agent",
            authority_ref="CONTRACT:ENG-1",payload=payload or {},expected_version=version)

    def test_consent_delivery_correction_and_replay(self):
        self.append("E1","engagement.offered",payload={"person_ref":"PSEUDO-1","activity_id":"care",
            "period":"2026-W46","classification":"paid","consent_basis":"CONTRACT-1","planned_hours":"8"})
        self.append("E2","engagement.accepted",payload={"accepted_hours":"6","consent_ref":"CONSENT-1"},version=1)
        self.append("E3","engagement.scheduled",payload={"scheduled_hours":"5"},version=2)
        self.append("E4","engagement.started",version=3)
        self.append("E5","engagement.delivered",payload={"delivered_hours":"4.5","evidence_ref":"TIMESHEET-1"},version=4)
        self.append("E6","engagement.verified",payload={"verification_ref":"VERIFIER-1"},version=5)
        self.append("E7","hours.corrected",payload={"corrects_event_id":"E5","delta_hours":"-0.5",
            "reason":"Duplicate interval removed"},version=6)
        state, version = self.store.state("ENG-1",principal_id="auditor")
        self.assertEqual(version,7)
        self.assertEqual(state["delivered_hours"],"4.0")
        self.assertEqual(state["status"],"VERIFIED")
        self.assertEqual(len(self.store.history("ENG-1",principal_id="auditor")),7)
        self.assertTrue(self.store.verify())

    def test_access_denial_and_expected_version_conflict(self):
        with self.assertRaises(RegisterError): self.store.state("ENG-1",principal_id="intruder")
        with self.assertRaises(RegisterError):
            self.store.append_event(event_id="NOPE",idempotency_key="NOPE",aggregate_id="ENG-1",
                event_type="engagement.offered",effective_at=T,recorded_at=T,actor_id="auditor",
                authority_ref="NONE",payload={},expected_version=0)
        self.append("E1","engagement.offered",payload={"person_ref":"P1","activity_id":"x",
            "period":"P1","classification":"paid","consent_basis":"C1","planned_hours":"2"})
        with self.assertRaises(RegisterError):
            self.append("E2","engagement.accepted",payload={"accepted_hours":"1","consent_ref":"CONSENT-1"},version=0)

    def test_stopped_work_preserves_hours_and_settlement_correction_requires_adjustment(self):
        self.append("S1","engagement.offered",payload={"person_ref":"PSEUDO-2","activity_id":"repair",
            "period":"2026-W46","classification":"paid","consent_basis":"CONTRACT-2","planned_hours":"4"})
        self.append("S2","engagement.accepted",payload={"accepted_hours":"4","consent_ref":"CONSENT-2"},version=1)
        self.append("S3","engagement.scheduled",payload={"scheduled_hours":"4"},version=2)
        self.append("S4","engagement.started",version=3)
        with self.assertRaises(LabourRegisterError):
            self.append("S5-BAD","engagement.cancelled",payload={"reason":"unsafe"},version=4)
        self.append("S5","engagement.stopped",payload={"delivered_hours":"1.5","reason":"safety stop",
            "evidence_ref":"STOP-REPORT-2"},version=4)
        self.append("S6","engagement.verified",payload={"verification_ref":"VERIFY-2"},version=5)
        self.append("S7","engagement.settled",payload={"settled_hours":"1.5","settlement_ref":"PAYMENT-2"},version=6)
        with self.assertRaises(RegisterError):
            self.append("S8-BAD","hours.corrected",payload={"corrects_event_id":"S5","delta_hours":"-0.5",
                "reason":"settlement adjustment missing"},version=7)
        self.append("S8","hours.corrected",payload={"corrects_event_id":"S5","delta_hours":"-0.5",
            "reason":"duplicate time entry","settlement_adjustment_ref":"ADJUSTMENT-2"},version=7)
        state,version=self.store.state("ENG-1",principal_id="auditor")
        self.assertEqual((state["status"],state["delivered_hours"],state["settled_hours"],version),
                         ("SETTLED","1.0","1.0",8))

    def test_capability_history_is_person_skill_scoped(self):
        self.store.append_event(event_id="CAP1",idempotency_key="CAP1",aggregate_id="capability:PSEUDO-1:welder",
            event_type="capability.assessed",effective_at=T,recorded_at=T,actor_id="assessor",
            authority_ref="ASSESSMENT:AUTHORITY-1",payload={"person_ref":"PSEUDO-1","skill_id":"welder",
                "proficiency":"3.5","scale_max":"5","evidence_ref":"ASSESSMENT-1"},expected_version=0)
        state,version=self.store.state("capability:PSEUDO-1:welder",principal_id="auditor")
        self.assertEqual((state["proficiency"],version),("3.5",1))

    def test_time_allocation_rejects_overlap(self):
        with self.assertRaises(LabourRegisterError):
            self.append("T1","time.allocation.recorded",aggregate="time:P1:2026-W46",payload={
                "person_ref":"P1","period":"2026-W46","period_hours":"168",
                "intervals":[{"start_hour":"0","end_hour":"8","category":"rest"},
                             {"start_hour":"7","end_hour":"9","category":"work"}]})

    def test_idempotency_changed_content_rejected(self):
        payload={"person_ref":"P1","activity_id":"x","period":"P1","classification":"paid",
                 "consent_basis":"C1","planned_hours":"2"}
        self.append("E1","engagement.offered",payload=payload)
        self.assertFalse(self.append("E1","engagement.offered",payload=payload))
        payload["planned_hours"]="3"
        with self.assertRaises(RegisterError): self.append("E1","engagement.offered",payload=payload)


class DurableLegalRightsRegisterTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.store=LegalRightsRegister(Path(self.tmp.name)/"rights.sqlite3")
        self.store.bootstrap_admin(principal_id="root",authority_ref="BOOTSTRAP:POLICY-1",occurred_at=T)
        self.store.grant_access(event_id="ACL-RIGHTS-WRITER",idempotency_key="ACL-RIGHTS-WRITER",
            principal_id="registrar",permissions=["legal_rights:read","legal_rights:write","legal_rights:adjudicate"],
            actor_id="root",authority_ref="POLICY:REGISTRAR",occurred_at=T)
        self.store.grant_access(event_id="ACL-RIGHTS-READER",idempotency_key="ACL-RIGHTS-READER",
            principal_id="reader",permissions=["legal_rights:read"],actor_id="root",
            authority_ref="POLICY:READER",occurred_at=T)

    def tearDown(self): self.tmp.cleanup()

    def append(self,eid,typ,payload,version):
        return self.store.append_event(event_id=eid,idempotency_key=eid,aggregate_id="RIGHT-1",
            event_type=typ,effective_at=T,recorded_at=T,actor_id="registrar",
            authority_ref="LEGAL-INSTRUMENT:ROOT",payload=payload,expected_version=version)

    def test_full_claim_lifecycle_and_correction_lineage(self):
        self.append("R1","right.created",{"holder_id":"ORG-A","obligor_id":"ORG-B","right_type":"receivable",
            "scope":"invoice:100","jurisdiction":"KZ","legal_instrument_ref":"CONTRACT-100",
            "effective_from":T,"evidence_refs":["SIGNED-CONTRACT","DELIVERY-RECEIPT"]},0)
        self.append("R2","right.transferred",{"from_holder_id":"ORG-A","to_holder_id":"ORG-C",
            "transfer_instrument_ref":"ASSIGNMENT-1","evidence_ref":"NOTICE-1"},1)
        self.append("R3","right.encumbered",{"encumbrance_id":"ENC-1","beneficiary_id":"BANK-1",
            "scope":"invoice:100","priority":1,"instrument_ref":"PLEDGE-1","evidence_ref":"PLEDGE-EVIDENCE"},2)
        self.append("R4","right.released",{"encumbrance_id":"ENC-1","release_instrument_ref":"RELEASE-1",
            "evidence_ref":"RELEASE-EVIDENCE"},3)
        self.append("R5","right.disputed",{"dispute_ref":"CASE-1","forum_ref":"COURT-1","evidence_ref":"CLAIM-1"},4)
        self.append("R6","right.adjudicated",{"outcome":"upheld","decision_ref":"DECISION-1"},5)
        self.append("R7","right.corrected",{"corrects_event_id":"R1","reason":"Scope transcription correction",
            "evidence_ref":"CORRECTION-AUTHORITY-1","changes":{"scope":"invoice:100 plus accrued contractual interest"}},6)
        state,version=self.store.state("RIGHT-1",principal_id="reader")
        self.assertEqual(version,7)
        self.assertEqual(state["holder_id"],"ORG-C")
        self.assertEqual(state["status"],"ACTIVE")
        self.assertEqual(state["scope"],"invoice:100 plus accrued contractual interest")
        self.assertEqual(state["_event_ids"], ["R1","R2","R3","R4","R5","R6","R7"])
        self.assertTrue(self.store.verify())

    def test_title_right_can_exist_without_debtor_obligor(self):
        self.append("TITLE-1","right.created",{"holder_id":"ORG-A","right_type":"ownership_title",
            "scope":"asset:SERIAL-1","jurisdiction":"KZ","legal_instrument_ref":"TITLE-1",
            "effective_from":T,"evidence_refs":["REGISTRY-EXTRACT-1"]},0)
        state,version=self.store.state("RIGHT-1",principal_id="reader")
        self.assertEqual((state["obligor_id"],state["status"],version),(None,"ACTIVE",1))

    def test_invalid_transfer_and_acl_denial(self):
        self.append("R1","right.created",{"holder_id":"ORG-A","obligor_id":"ORG-B","right_type":"claim",
            "scope":"x","jurisdiction":"KZ","legal_instrument_ref":"CONTRACT-X","effective_from":T,
            "evidence_refs":["E1"]},0)
        with self.assertRaises(LegalRightsRegisterError):
            self.append("R2","right.transferred",{"from_holder_id":"WRONG","to_holder_id":"ORG-C",
                "transfer_instrument_ref":"A1","evidence_ref":"E2"},1)
        with self.assertRaises(RegisterError): self.store.state("RIGHT-1",principal_id="outsider")

    def test_immutable_event_rows_and_tamper_detection(self):
        self.append("R1","right.created",{"holder_id":"ORG-A","obligor_id":"ORG-B","right_type":"claim",
            "scope":"x","jurisdiction":"KZ","legal_instrument_ref":"CONTRACT-X","effective_from":T,
            "evidence_refs":["E1"]},0)
        with sqlite3.connect(self.store.path) as con:
            with self.assertRaises(sqlite3.DatabaseError): con.execute("UPDATE register_events SET payload_json='{}' WHERE event_id='R1'")
            con.execute("DROP TRIGGER register_events_no_update")
            con.execute("UPDATE register_events SET payload_json='{}' WHERE event_id='R1'")
        self.assertFalse(self.store.verify())


class NativeRegisterCoordinatorTests(unittest.TestCase):
    def test_prepared_authority_is_serialized_against_acl_changes_and_commit_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            store=LabourRegister(Path(tmp)/"labour.sqlite3")
            store.bootstrap_admin(principal_id="root",authority_ref="BOOTSTRAP",occurred_at=T)
            store.grant_access(event_id="ACL-W",idempotency_key="ACL-W",principal_id="writer",
                permissions=["labour:read","labour:write"],actor_id="root",authority_ref="POLICY",occurred_at=T)
            envelope={"event_type":"engagement.offered","effective_at":T,"recorded_at":T,
                "actor_id":"writer","authority_ref":"CONTRACT","idempotency_key":"NATIVE-ID-1",
                "payload":{"person_ref":"P1","activity_id":"work","period":"P1",
                    "classification":"paid","consent_basis":"C1","planned_hours":"2"}}
            operation={"stream_id":"ENG-1","native_event_id":"NATIVE-ID-1","payload":envelope,"expected_revision":0}
            token=store.prepare("TX-1",operation)
            with self.assertRaises(RegisterError):
                store.revoke_access(event_id="ACL-REVOKE-W",idempotency_key="ACL-REVOKE-W",principal_id="writer",
                    actor_id="root",authority_ref="POLICY-REVOKE",occurred_at=T)
            receipt=store.commit("TX-1",token)
            store.revoke_access(event_id="ACL-REVOKE-W",idempotency_key="ACL-REVOKE-W",principal_id="writer",
                actor_id="root",authority_ref="POLICY-REVOKE",occurred_at=T)
            self.assertEqual(store.commit("TX-1",token),receipt)
            self.assertEqual(receipt["revision"],1)
            state,version=store.state("ENG-1",principal_id="root")
            self.assertEqual((state["status"],version),("OFFERED",1))
            self.assertEqual(store.event_count("TX-1"),1)

    def test_coordinator_commits_to_native_labour_and_legal_registers(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
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
                "physical":SQLiteParticipant("physical",root/"physical.sqlite3"),
                "capital":SQLiteParticipant("capital",root/"capital.sqlite3"),
                "labour":labour,
                "product":SQLiteParticipant("product",root/"product.sqlite3"),
                "legal_rights":rights,
                "financial":SQLiteParticipant("financial",root/"financial.sqlite3"),
            }
            coordinator=CrossRegisterCoordinator(root/"coordinator.sqlite3",participants)
            operations={}
            for name in PARTICIPANTS:
                if name=="labour":
                    payload={"event_type":"engagement.offered","effective_at":T,"recorded_at":T,
                        "actor_id":"coordinator","authority_ref":"CONTRACT:L-1","idempotency_key":"TX-LABOUR-1",
                        "payload":{"person_ref":"PSEUDO-1","activity_id":"care","period":"P1",
                            "classification":"paid","consent_basis":"CONTRACT-L-1","planned_hours":"3"}}
                elif name=="legal_rights":
                    payload={"event_type":"right.created","effective_at":T,"recorded_at":T,
                        "actor_id":"coordinator","authority_ref":"CONTRACT:R-1","idempotency_key":"TX-RIGHTS-1",
                        "payload":{"holder_id":"ORG-A","obligor_id":"ORG-B","right_type":"claim",
                            "scope":"invoice:1","jurisdiction":"KZ","legal_instrument_ref":"CONTRACT-R-1",
                            "effective_from":T,"evidence_refs":["SIGNED-1"]}}
                else:
                    payload={"test_event":name,"transaction":"TX-NATIVE-1"}
                operations[name]={"stream_id":f"stream:{name}","native_event_id":f"native:{name}:1",
                    "payload":payload,"expected_revision":0}
            self.assertTrue(coordinator.submit("TX-NATIVE-1","SCENARIO-1","CAUSE-1",operations))
            self.assertEqual(coordinator.execute("TX-NATIVE-1"),"COMMITTED")
            self.assertTrue(coordinator.is_visible("TX-NATIVE-1"))
            event_group=coordinator.committed_event_group("TX-NATIVE-1")
            self.assertEqual(event_group["common_event_id"],"TX-NATIVE-1")
            self.assertEqual({x["register_id"] for x in event_group["events"]},set(PARTICIPANTS))
            self.assertTrue(all(x["common_event_id"] == "TX-NATIVE-1" for x in event_group["events"]))
            labour_state,labour_version=labour.state("stream:labour",principal_id="coordinator")
            rights_state,rights_version=rights.state("stream:legal_rights",principal_id="coordinator")
            self.assertEqual((labour_state["status"],labour_version),("OFFERED",1))
            self.assertEqual((rights_state["status"],rights_version),("ACTIVE",1))
            self.assertTrue(labour.verify()); self.assertTrue(rights.verify())


if __name__ == "__main__": unittest.main(verbosity=2)
