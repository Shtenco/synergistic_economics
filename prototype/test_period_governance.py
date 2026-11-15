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
        ref = f"attestation:{name}:{period}:{generation}"
        att_digest = digest(attestation)
        manifests[ref] = (att_digest, attestation)
        references.append({
            "register_name": name,
            "attestation_ref": ref,
            "attestation_digest": att_digest,
        })
    references.sort(key=lambda item: item["register_name"])
    close_manifest = {
        "service_id": "synergy-sfc",
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
        attestation = dict(manifests[att_ref][1])
        attestation["closing_state_hash"] = digest({"register": name, "state": "changed"})
        att_digest = digest(attestation)
        manifests[att_ref] = (att_digest, attestation)
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
