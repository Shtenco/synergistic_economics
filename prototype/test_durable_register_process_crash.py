"""Hard-process-death recovery tests for the shared durable domain-register participant."""
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from labour_register import LabourRegister
from legal_rights_register import LegalRightsRegister

T = "2026-11-13T05:00:00Z"
ROOT = Path(__file__).resolve().parents[1]


def envelope(event_type, payload, event_id):
    return {
        "event_type": event_type,
        "effective_at": T,
        "recorded_at": T,
        "actor_id": "coordinator",
        "authority_ref": "AUTH:COORDINATOR",
        "idempotency_key": event_id,
        "payload": payload,
    }


class DurableRegisterProcessCrashTests(unittest.TestCase):
    def _exercise_crash_recovery(self, register_kind):
        with tempfile.TemporaryDirectory() as tmp:
            database = Path(tmp) / f"{register_kind}.sqlite3"
            if register_kind == "labour":
                register = LabourRegister(database)
                stream_id = "ENG-PROCESS-CRASH"
                native_event_id = "LABOUR-PROCESS-CRASH"
                txid = "TX-LABOUR-PROCESS-CRASH"
                domain_payload = {
                    "person_ref": "PSEUDO-CRASH",
                    "activity_id": "work",
                    "period": "P1",
                    "classification": "paid",
                    "consent_basis": "CONTRACT-CRASH",
                    "planned_hours": "2",
                }
                expected_status = "OFFERED"
                event_type = "engagement.offered"
            elif register_kind == "legal_rights":
                register = LegalRightsRegister(database)
                stream_id = "RIGHT-PROCESS-CRASH"
                native_event_id = "RIGHT-PROCESS-CRASH"
                txid = "TX-RIGHTS-PROCESS-CRASH"
                domain_payload = {
                    "holder_id": "ORG-HOLDER",
                    "obligor_id": "ORG-OBLIGOR",
                    "right_type": "claim",
                    "scope": "invoice:process-crash",
                    "jurisdiction": "KZ",
                    "legal_instrument_ref": "CONTRACT-CRASH",
                    "effective_from": T,
                    "evidence_refs": ["SIGNED-CRASH"],
                }
                expected_status = "ACTIVE"
                event_type = "right.created"
            else:
                self.fail(f"unsupported register kind: {register_kind}")

            register.bootstrap_admin(
                principal_id=f"{register_kind}-root",
                authority_ref=f"BOOTSTRAP:{register_kind}",
                occurred_at=T,
            )
            register.grant_access(
                event_id=f"{register_kind}-ACL-COORDINATOR",
                idempotency_key=f"{register_kind}-ACL-COORDINATOR",
                principal_id="coordinator",
                permissions=[
                    f"{register_kind}:read",
                    f"{register_kind}:write",
                ],
                actor_id=f"{register_kind}-root",
                authority_ref=f"POLICY:{register_kind}",
                occurred_at=T,
            )
            operation = {
                "stream_id": stream_id,
                "native_event_id": native_event_id,
                "expected_revision": 0,
                "payload": envelope(event_type, domain_payload, native_event_id),
            }
            token = register.prepare(txid, operation)

            # Crash the child only after the domain append transaction has committed,
            # but before DurableEventRegister.commit can write its participant receipt.
            child = """
import os, sys
from pathlib import Path
sys.path.insert(0, str(Path.cwd() / "prototype"))
kind, database, txid, token = sys.argv[1:]
if kind == "labour":
    from labour_register import LabourRegister as Register
else:
    from legal_rights_register import LegalRightsRegister as Register
register = Register(database)
append = register._append
def append_then_die(**kwargs):
    append(**kwargs)
    os._exit(73)
register._append = append_then_die
register.commit(txid, token)
raise SystemExit(74)
"""
            result = subprocess.run(
                [sys.executable, "-c", child, register_kind, str(database), txid, token],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=30,
            )
            self.assertEqual(result.returncode, 73, msg=result.stderr or result.stdout)

            # Reopen from disk: event is durable, inbox is still PREPARED, no receipt exists.
            if register_kind == "labour":
                restarted = LabourRegister(database)
            else:
                restarted = LegalRightsRegister(database)
            status = restarted.status(txid)
            self.assertEqual(status["state"], "PREPARED")
            self.assertIsNone(status["receipt_json"])
            self.assertEqual(restarted.event_count(txid), 1)
            self.assertIsNone(restarted.committed_event(txid))

            # Retrying the same commit must be idempotent and complete the receipt.
            receipt = restarted.commit(txid, token)
            self.assertEqual(restarted.status(txid)["state"], "COMMITTED")
            self.assertEqual(restarted.event_count(txid), 1)
            self.assertEqual(receipt["native_event_id"], native_event_id)
            state, revision = restarted.state(stream_id, principal_id="coordinator")
            self.assertEqual(state["status"], expected_status)
            self.assertEqual(revision, 1)
            self.assertEqual(restarted.total_event_count, 3)  # bootstrap, ACL grant, domain event
            self.assertTrue(restarted.verify())

    def test_labour_register_recovers_after_real_process_death_before_receipt(self):
        self._exercise_crash_recovery("labour")

    def test_legal_rights_register_recovers_after_real_process_death_before_receipt(self):
        self._exercise_crash_recovery("legal_rights")


if __name__ == "__main__":
    unittest.main(verbosity=2)
