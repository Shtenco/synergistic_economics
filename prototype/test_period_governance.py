"""Signed six-register period completeness gate tests."""
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from period_governance import PeriodGovernance, PeriodGovernanceError, REGISTERS


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode("utf-8")).hexdigest()


def make_checkpoint_bundle(*, period=3, generation=0, zero_status_override=None):
    manifests = {}
    references = []
    empty_root = digest([])
    for index, name in enumerate(REGISTERS):
        count = 0 if name != "financial" else 2
        activity = "ZERO_ACTIVITY" if count == 0 else "ACTIVITY"
        if zero_status_override == name:
            activity = "ACTIVITY" if count == 0 else "ZERO_ACTIVITY"
        opening = digest({"register": name, "state": "opening"})
        closing = opening if count == 0 else digest({"register": name, "state": "closing"})
        event_root = empty_root if count == 0 else digest([f"{name}-event-1", f"{name}-event-2"])
        attestation = {
            "service_id": "synergy-sfc",
            "declaration_type": "register_period_completeness",
            "register_name": name,
            "period": period,
            "projection_generation": generation,
            "complete": True,
            "source_register_id": f"{name}:instance-001",
            "source_sequence": index + 10,
            "source_chain_hash": digest({"register": name, "chain": "tail"}),
            "period_event_count": count,
            "period_event_root": event_root,
            "activity_status": activity,
            "opening_state_hash": opening,
            "closing_state_hash": closing,
            "reconciliation_hash": digest({"register": name, "reconciliation": True}),
        }
        signed_attestation_manifest = {
            "service_id": "synergy-sfc",
            "period": period,
            "projection_generation": generation,
            "period_closed": False,
            "commit_sequence": attestation["source_sequence"],
            "applied_through_cursor": attestation["source_sequence"],
            "event_count": count,
            "coverage_count": count,
            "event_log_root": event_root,
            "instrument_opening_hash": opening,
            "projection_state_hash": closing,
            "signer_key_id": f"{name}-independent-register-key",
            "register_declaration": attestation,
        }
        ref = f"attestation:{name}:{period}:{generation}"
        att_digest = digest(signed_attestation_manifest)
        manifests[ref] = (att_digest, signed_attestation_manifest)
        references.append({
            "register_name": name,
            "attestation_ref": ref,
            "attestation_digest": att_digest,
        })
    references.sort(key=lambda item: item["register_name"])
    close_manifest = {
        "service_id": "synergy-sfc",
        "signer_key_id": "global-period-close-key",
        "period": period,
        "projection_generation": generation,
        "period_closed": True,
        "register_completeness": references,
        "register_completeness_digest": digest(references),
    }
    close_ref = f"period-close:{period}:{generation}"
    close_digest = digest(close_manifest)
    manifests[close_ref] = (close_digest, close_manifest)
    return manifests, close_ref, close_digest


class PeriodGovernanceCompletenessTests(unittest.TestCase):
    def make_governance(self, root, manifests):
        def verifier(ref, supplied_digest):
            record = manifests.get(ref)
            if record is None or record[0] != supplied_digest:
                raise PeriodGovernanceError("external signed checkpoint verification failed")
            return record[1]

        return PeriodGovernance(
            Path(root) / "governance.sqlite3",
            checkpoint_verifier=verifier,
            service_id="synergy-sfc",
            authorization_verifier=lambda approver, role, context, evidence: True,
        )

    def test_period_close_requires_all_six_signed_register_attestations(self):
        manifests, ref, close_digest = make_checkpoint_bundle()
        with tempfile.TemporaryDirectory() as root:
            governance = self.make_governance(root, manifests)
            self.assertTrue(governance.close_period(3, 0, ref, close_digest, "period-controller"))
            self.assertEqual(governance.active_generation(3), 0)
            rows = governance.register_period_attestations(3, 0)
            self.assertEqual({row["register_name"] for row in rows}, set(REGISTERS))
            self.assertEqual(len(rows), 6)
            zero = [row for row in rows if row["activity_status"] == "ZERO_ACTIVITY"]
            self.assertEqual(len(zero), 5)
            self.assertTrue(all(row["period_event_count"] == 0 for row in zero))
            self.assertFalse(governance.close_period(3, 0, ref, close_digest, "period-controller"))

    def test_period_close_rejects_missing_register_declaration(self):
        manifests, ref, _ = make_checkpoint_bundle()
        close_manifest = dict(manifests[ref][1])
        close_manifest["register_completeness"] = close_manifest["register_completeness"][:-1]
        close_manifest["register_completeness_digest"] = digest(close_manifest["register_completeness"])
        manifests[ref] = (digest(close_manifest), close_manifest)
        with tempfile.TemporaryDirectory() as root:
            governance = self.make_governance(root, manifests)
            with self.assertRaisesRegex(PeriodGovernanceError, "exactly six register completeness"):
                governance.close_period(3, 0, ref, manifests[ref][0], "period-controller")
            self.assertIsNone(governance.active_generation(3))

    def test_zero_activity_must_be_explicit(self):
        manifests, ref, close_digest = make_checkpoint_bundle(zero_status_override="physical")
        with tempfile.TemporaryDirectory() as root:
            governance = self.make_governance(root, manifests)
            with self.assertRaisesRegex(PeriodGovernanceError, "activity status contradicts"):
                governance.close_period(3, 0, ref, close_digest, "period-controller")
            self.assertIsNone(governance.active_generation(3))

    def test_zero_activity_with_changed_stock_is_rejected(self):
        manifests, ref, _ = make_checkpoint_bundle()
        name = "physical"
        att_ref = f"attestation:{name}:3:0"
        signed_attestation = dict(manifests[att_ref][1])
        declaration = dict(signed_attestation["register_declaration"])
        declaration["closing_state_hash"] = digest({"register": name, "state": "changed"})
        signed_attestation["register_declaration"] = declaration
        signed_attestation["projection_state_hash"] = declaration["closing_state_hash"]
        att_digest = digest(signed_attestation)
        manifests[att_ref] = (att_digest, signed_attestation)
        close_manifest = dict(manifests[ref][1])
        refs = [dict(item) for item in close_manifest["register_completeness"]]
        for item in refs:
            if item["register_name"] == name:
                item["attestation_digest"] = att_digest
        close_manifest["register_completeness"] = refs
        close_manifest["register_completeness_digest"] = digest(refs)
        manifests[ref] = (digest(close_manifest), close_manifest)
        with tempfile.TemporaryDirectory() as root:
            governance = self.make_governance(root, manifests)
            with self.assertRaisesRegex(PeriodGovernanceError, "must preserve its opening state"):
                governance.close_period(3, 0, ref, manifests[ref][0], "period-controller")

    def test_reopened_generation_publication_requires_and_persists_new_attestations(self):
        manifests, initial_ref, initial_digest = make_checkpoint_bundle(period=3, generation=0)
        with tempfile.TemporaryDirectory() as root:
            governance = self.make_governance(root, manifests)
            governance.close_period(3, 0, initial_ref, initial_digest, "period-controller")
            governance.request_reopen(
                "REOPEN-3", 3, "audited correction", "CORRECTION-EVIDENCE",
                scope=list(REGISTERS),
                pre_reopen_checkpoint_ref=initial_ref,
                pre_reopen_checkpoint_digest=initial_digest,
            )
            governance.approve_reopen(
                "REOPEN-3", "owner-1", "period_owner", "OWNER-APPROVAL",
            )
            governance.approve_reopen(
                "REOPEN-3", "controller-1", "independent_controller",
                "CONTROLLER-APPROVAL",
            )
            source_root = digest({"event_log": "immutable-root"})
            receipts = []
            for index, name in enumerate(sorted(REGISTERS)):
                receipt = {
                    "register_name": name,
                    "old_generation": 0,
                    "new_generation": 1,
                    "source_event_root": source_root,
                    "event_count": 1,
                    "opening_state_hash": digest({"register": name, "opening": 0}),
                    "closing_state_hash": digest({"register": name, "closing": 1}),
                    "reconciliation_hash": digest({"register": name, "reconciled": True}),
                }
                receipts.append(receipt)
                governance.record_rebuild(
                    "REOPEN-3", name, source_root, 1,
                    receipt["opening_state_hash"], receipt["closing_state_hash"],
                    receipt["reconciliation_hash"],
                )
            global_reconciliation = digest(receipts)
            new_manifests, new_ref, _ = make_checkpoint_bundle(period=3, generation=1)
            new_manifest = dict(new_manifests[new_ref][1])
            new_manifest["event_log_root"] = source_root
            new_manifest["projection_state_hash"] = global_reconciliation
            new_digest = digest(new_manifest)
            new_manifests[new_ref] = (new_digest, new_manifest)
            manifests.update(new_manifests)
            self.assertTrue(governance.publish_generation(
                "REOPEN-3", global_reconciliation, new_ref, new_digest,
            ))
            self.assertEqual(governance.active_generation(3), 1)
            self.assertEqual(
                {row["register_name"] for row in governance.register_period_attestations(3, 1)},
                set(REGISTERS),
            )
            self.assertFalse(governance.publish_generation(
                "REOPEN-3", global_reconciliation, new_ref, new_digest,
            ))

    def test_close_retry_rejects_mutated_persisted_attestation_inventory(self):
        manifests, ref, close_digest = make_checkpoint_bundle()
        with tempfile.TemporaryDirectory() as root:
            governance = self.make_governance(root, manifests)
            governance.close_period(3, 0, ref, close_digest, "period-controller")
            with governance._connect() as con:
                con.execute("DROP TRIGGER register_period_attestations_no_update")
                con.execute(
                    "UPDATE register_period_attestations SET source_register_id='tampered' "
                    "WHERE period=3 AND generation=0 AND register_name='financial'"
                )
            with self.assertRaisesRegex(PeriodGovernanceError, "changed immutable register completeness"):
                governance.close_period(3, 0, ref, close_digest, "period-controller")


if __name__ == "__main__":
    unittest.main(verbosity=2)
