import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal as D
from hashlib import sha256

from real_economy_protocol import (
    ClaimProfile, EvidenceRecord, IdempotencyConflict, LotInventory,
    RealEconomyError, VerificationPolicy, evaluate_evidence,
)


NOW = datetime(2026, 11, 11, 12, 0, tzinfo=timezone.utc)


def inventory():
    stock = LotInventory()
    stock.register_lot(
        "lot-potato-001", "potato", "farm-a", "warehouse-a",
        "warehouse-a/bin-1", "100", "kg",
        authorized_actors=("operator-a",),
    )
    return stock


class LotInventoryTests(unittest.TestCase):
    def test_registration_and_available_stock(self):
        stock = inventory()
        lot = stock.get_lot("lot-potato-001")
        self.assertEqual(lot.quantity, D("100"))
        self.assertEqual(lot.available_quantity, D("100"))
        stock.assert_invariants()

    def test_custody_does_not_grant_reservation_authority(self):
        stock = LotInventory()
        stock.register_lot("lot-1", "grain", "owner", "warehouse",
                           "bin-1", 10, "kg")
        with self.assertRaises(RealEconomyError):
            stock.reserve("lot-1", "r-1", 2, "warehouse", "buyer",
                          "sale", NOW + timedelta(hours=1), "reserve-1", 1, NOW)
        self.assertEqual(stock.get_lot("lot-1").reserved_quantity, D("0"))

    def test_reservation_commit_requires_authorized_actor_and_contract_reference(self):
        stock = inventory()
        reserved = stock.reserve(
            "lot-potato-001", "r-1", 10, "operator-a", "buyer-a", "sale",
            NOW + timedelta(hours=1), "reserve-1", 1, NOW,
        ).result
        with self.assertRaises(RealEconomyError):
            stock.commit("r-1", "warehouse-a", "contract-1",
                         "commit-unauthorized", reserved.version, NOW)
        with self.assertRaises(RealEconomyError):
            stock.commit("r-1", "operator-a", "",
                         "commit-no-contract", reserved.version, NOW)

    def test_reservation_is_bounded_and_versioned(self):
        stock = inventory()
        receipt = stock.reserve(
            "lot-potato-001", "r-1", 30, "operator-a", "buyer-a", "sale",
            NOW + timedelta(hours=1), "reserve-1", 1, NOW,
        )
        self.assertEqual(receipt.result.remaining_quantity, D("30"))
        self.assertEqual(stock.get_lot("lot-potato-001").available_quantity, D("70"))
        with self.assertRaises(RealEconomyError):
            stock.reserve(
                "lot-potato-001", "r-2", 71, "farm-a", "buyer-b", "sale",
                NOW + timedelta(hours=1), "reserve-2", 2, NOW,
            )
        stock.assert_invariants()

    def test_idempotent_retry_returns_same_reservation_without_double_hold(self):
        stock = inventory()
        args = ("lot-potato-001", "r-1", 25, "operator-a", "buyer-a", "sale",
                NOW + timedelta(hours=1), "reserve-1", 1, NOW)
        first = stock.reserve(*args)
        second = stock.reserve(*args)
        self.assertEqual(first, second)
        self.assertEqual(stock.get_lot("lot-potato-001").reserved_quantity, D("25"))

    def test_idempotency_key_cannot_be_reused_for_different_command(self):
        stock = inventory()
        stock.reserve("lot-potato-001", "r-1", 25, "operator-a", "buyer-a",
                      "sale", NOW + timedelta(hours=1), "same-key", 1, NOW)
        with self.assertRaises(IdempotencyConflict):
            stock.reserve("lot-potato-001", "r-2", 20, "operator-a", "buyer-a",
                          "sale", NOW + timedelta(hours=1), "same-key", 2, NOW)

    def test_stale_lot_version_is_rejected(self):
        stock = inventory()
        stock.reserve("lot-potato-001", "r-1", 25, "operator-a", "buyer-a",
                      "sale", NOW + timedelta(hours=1), "reserve-1", 1, NOW)
        with self.assertRaises(RealEconomyError):
            stock.reserve("lot-potato-001", "r-2", 10, "operator-a", "buyer-b",
                          "sale", NOW + timedelta(hours=1), "reserve-2", 1, NOW)

    def test_partial_movement_splits_child_lot_and_preserves_source_location(self):
        stock = inventory()
        reserved = stock.reserve(
            "lot-potato-001", "r-1", 30, "operator-a", "buyer-a", "sale",
            NOW + timedelta(hours=1), "reserve-1", 1, NOW,
        ).result
        committed = stock.commit("r-1", "operator-a", "contract-1", "commit-1", reserved.version, NOW).result
        moved = stock.consume(
            "r-1", "operator-a", 10, "lot-shipment-001", "buyer-dock", "carrier-a",
            "consume-1", committed.version,
        )
        source = stock.get_lot("lot-potato-001")
        child = stock.get_lot("lot-shipment-001")
        self.assertEqual(source.quantity, D("90"))
        self.assertEqual(source.location_id, "warehouse-a/bin-1")
        self.assertEqual(source.reserved_quantity, D("20"))
        self.assertEqual(child.quantity, D("10"))
        self.assertEqual(child.location_id, "buyer-dock")
        self.assertEqual(child.owner_id, "farm-a")
        self.assertEqual(child.source_lot_id, "lot-potato-001")
        self.assertEqual(moved.result["reservation"].remaining_quantity, D("20"))
        self.assertEqual(source.quantity + child.quantity, D("100"))
        stock.assert_invariants()

    def test_release_returns_exact_reserved_quantity(self):
        stock = inventory()
        reserved = stock.reserve(
            "lot-potato-001", "r-1", 30, "operator-a", "buyer-a", "sale",
            NOW + timedelta(hours=1), "reserve-1", 1, NOW,
        ).result
        released = stock.release("r-1", "operator-a", "release-1", reserved.version)
        self.assertEqual(released.result.status, "RELEASED")
        self.assertEqual(stock.get_lot("lot-potato-001").available_quantity, D("100"))
        stock.assert_invariants()

    def test_expired_reservation_is_released_on_commit_attempt(self):
        stock = inventory()
        reserved = stock.reserve(
            "lot-potato-001", "r-1", 30, "operator-a", "buyer-a", "sale",
            NOW + timedelta(minutes=5), "reserve-1", 1, NOW,
        ).result
        result = stock.commit(
            "r-1", "operator-a", "contract-1", "commit-late", reserved.version, NOW + timedelta(minutes=6)
        )
        self.assertEqual(result.result.status, "EXPIRED")
        self.assertEqual(stock.get_lot("lot-potato-001").available_quantity, D("100"))
        stock.assert_invariants()

    def test_custodian_cannot_quarantine_without_owner_authorization(self):
        stock = inventory()
        with self.assertRaises(RealEconomyError):
            stock.quarantine(
                "lot-potato-001", "warehouse-a", "quarantine-1", 1, "quality hold"
            )
        self.assertEqual(stock.get_lot("lot-potato-001").quality_status, "RELEASED")

    def test_quarantine_blocks_availability_and_requires_no_active_reservations(self):
        stock = inventory()
        reserved = stock.reserve(
            "lot-potato-001", "r-1", 5, "operator-a", "buyer-a", "sale",
            NOW + timedelta(hours=1), "reserve-1", 1, NOW,
        ).result
        with self.assertRaises(RealEconomyError):
            stock.quarantine("lot-potato-001", "operator-a", "quarantine-1", 2, "quality hold")
        stock.release("r-1", "operator-a", "release-1", reserved.version)
        quarantined = stock.quarantine(
            "lot-potato-001", "farm-a", "quarantine-1", 3, "quality hold"
        )
        self.assertEqual(quarantined.result.available_quantity, D("0"))
        stock.assert_invariants()


class ClaimAndEvidenceTests(unittest.TestCase):
    def test_claim_profile_is_read_only_projection_and_defaults_non_transferable(self):
        claim = {
            "claim_id": "claim-1", "claimant_id": "buyer",
            "obligor_id": "farm", "contract_id": "contract-1",
            "obligation_id": "delivery-1", "claim_type": "DELIVERY",
            "status": "ACTIVE", "quantity": "30", "unit": "kg",
        }
        profile = ClaimProfile.from_canonical_claim(claim)
        self.assertEqual(profile.quantity, D("30"))
        self.assertFalse(profile.transferable)
        self.assertNotIn("transferable", claim)

    def test_monetary_claim_requires_currency(self):
        claim = {
            "claim_id": "claim-1", "claimant_id": "buyer",
            "obligor_id": "farm", "contract_id": "contract-1",
            "obligation_id": "payment-1", "claim_type": "PAYMENT",
            "status": "ACTIVE", "amount": "120.00",
        }
        with self.assertRaises(RealEconomyError):
            ClaimProfile.from_canonical_claim(claim)

    def test_evidence_requires_digest_and_authentication_before_acceptance(self):
        payload = b"warehouse inspection report"
        evidence = EvidenceRecord(
            "ev-1", "lot:lot-1", "LOT_LOCATION", "warehouse-a",
            "WAREHOUSE_SIGNED_RECORD", sha256(payload).hexdigest(),
            NOW - timedelta(minutes=5), NOW + timedelta(hours=1), "credential:1",
        )
        policy = VerificationPolicy(
            "policy-location", "1", "LOT_LOCATION",
            frozenset({"WAREHOUSE_SIGNED_RECORD"}),
            frozenset({"warehouse-a"}), timedelta(hours=1), True,
        )
        decision = evaluate_evidence(
            evidence, policy, NOW, "lot:lot-1", payload, issuer_verifier=lambda _: True
        )
        self.assertEqual(decision.result, "ACCEPTED")

    def test_credential_authentication_does_not_override_bad_payload_digest(self):
        evidence = EvidenceRecord(
            "ev-2", "lot:lot-1", "LOT_LOCATION", "warehouse-a",
            "WAREHOUSE_SIGNED_RECORD", "0" * 64,
            NOW - timedelta(minutes=5), None, "credential:2",
        )
        policy = VerificationPolicy(
            "policy-location", "1", "LOT_LOCATION",
            frozenset({"WAREHOUSE_SIGNED_RECORD"}),
            frozenset({"warehouse-a"}), timedelta(hours=1), True,
        )
        decision = evaluate_evidence(
            evidence, policy, NOW, "lot:lot-1", b"different bytes",
            issuer_verifier=lambda _: True,
        )
        self.assertEqual(decision.result, "REJECTED")
        self.assertIn("payload_digest_mismatch", decision.reasons)

    def test_evidence_for_another_subject_is_rejected(self):
        payload = b"valid bytes"
        evidence = EvidenceRecord(
            "ev-other", "lot:wrong-lot", "LOT_LOCATION", "warehouse-a",
            "WAREHOUSE_SIGNED_RECORD", sha256(payload).hexdigest(),
            NOW - timedelta(minutes=5),
        )
        policy = VerificationPolicy(
            "policy-location", "1", "LOT_LOCATION",
            frozenset({"WAREHOUSE_SIGNED_RECORD"}),
            frozenset({"warehouse-a"}), timedelta(hours=1), True,
        )
        decision = evaluate_evidence(
            evidence, policy, NOW, "lot:lot-1", payload,
            issuer_verifier=lambda _: True,
        )
        self.assertEqual(decision.result, "REJECTED")
        self.assertIn("subject_mismatch", decision.reasons)

    def test_missing_issuer_verifier_is_indeterminate_not_accepted(self):
        payload = b"valid bytes"
        evidence = EvidenceRecord(
            "ev-3", "lot:lot-1", "LOT_LOCATION", "warehouse-a",
            "WAREHOUSE_SIGNED_RECORD", sha256(payload).hexdigest(),
            NOW - timedelta(minutes=5),
        )
        policy = VerificationPolicy(
            "policy-location", "1", "LOT_LOCATION",
            frozenset({"WAREHOUSE_SIGNED_RECORD"}),
            frozenset({"warehouse-a"}), timedelta(hours=1), True,
        )
        decision = evaluate_evidence(evidence, policy, NOW, "lot:lot-1", payload)
        self.assertEqual(decision.result, "INDETERMINATE")
        self.assertIn("issuer_authentication_not_performed", decision.reasons)


if __name__ == "__main__":
    unittest.main(verbosity=2)
