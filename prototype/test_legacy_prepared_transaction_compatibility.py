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
