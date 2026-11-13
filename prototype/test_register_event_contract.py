import unittest
from register_event_contract import REGISTERS, SCHEMA_ID, SCHEMA_VERSION, RegisterEventContractError, normalize_event_envelope

T = "2026-11-13T07:00:00Z"
def legacy():
    return {"event_type":"domain.event","effective_at":T,"recorded_at":T,"actor_id":"actor-1",
            "authority_ref":"authority-1","idempotency_key":"event-1","payload":{"quantity":"1.25","unit":"t"},
            "no_stock_flow_effect":"fixture has no recognized stock movement"}

class RegisterEventContractTests(unittest.TestCase):
    def test_all_six_legacy_envelopes_migrate_deterministically(self):
        for register in REGISTERS:
            with self.subTest(register=register):
                migrated=normalize_event_envelope(register,legacy())
                self.assertEqual((migrated["schema_id"],migrated["schema_version"],migrated["register_id"]),
                                 (SCHEMA_ID,SCHEMA_VERSION,register))
                self.assertEqual(migrated["migration"],{"migration_id":"native-event-envelope-v0-to-v1","source_schema_version":0})
                self.assertEqual(normalize_event_envelope(register,migrated),migrated)
    def test_current_v1_requires_exact_register_identity(self):
        envelope=normalize_event_envelope("labour",legacy())
        self.assertEqual(normalize_event_envelope("labour",envelope),envelope)
        with self.assertRaises(RegisterEventContractError): normalize_event_envelope("legal_rights",envelope)
    def test_unknown_future_and_partial_schema_identity_fail_closed(self):
        for change in ({"schema_id":SCHEMA_ID,"schema_version":2,"register_id":"labour"},
                       {"schema_id":SCHEMA_ID},{"schema_version":1},
                       {"schema_id":"other.contract","schema_version":1,"register_id":"labour"}):
            with self.subTest(change=change),self.assertRaises(RegisterEventContractError):
                normalize_event_envelope("labour",legacy()|change)
    def test_timestamp_and_payload_validation(self):
        for change in ({"effective_at":"2026-11-13T07:00:00"},{"recorded_at":"2026-11-13T07:00:00+03:00"},
                       {"payload":[]},{"event_type":" "}):
            with self.subTest(change=change),self.assertRaises(RegisterEventContractError):
                normalize_event_envelope("physical",legacy()|change)
    def test_unknown_fields_empty_movements_and_dual_effect_fail_closed(self):
        for change in ({"unregistered": True}, {"stock_flow_movements": []},
                       {"stock_flow_movements": [{"movement_id": "M1"}], "no_stock_flow_effect": "none"}):
            with self.subTest(change=change), self.assertRaises(RegisterEventContractError):
                normalize_event_envelope("physical", legacy() | change)

    def test_migration_does_not_mutate_callers_event(self):
        source=legacy(); before=dict(source)
        normalized=normalize_event_envelope("product",source)
        self.assertEqual(source,before); self.assertNotIn("schema_version",source)
        self.assertEqual(normalized["register_id"],"product")

if __name__=="__main__": unittest.main(verbosity=2)
