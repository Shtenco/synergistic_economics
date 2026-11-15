import tempfile
import unittest
from decimal import Decimal as D
from pathlib import Path

from economic_stock_flow_reconciliation import (
    OpeningPosition, ClosingPosition, PositionIdentity,
    movements_from_event_groups, reconcile_periods,
)
from operating_financial_register import (
    OperatingFinancialRegister, OperatingFinancialRegisterError,
    central_bank_refinancing_movement_specs,
)


T = "2026-11-15T00:00:00Z"


class CentralBankRefinancingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "refinancing.sqlite3"
        self.register = OperatingFinancialRegister(
            self.path,
            sectors={"bank": "CB", "central-bank": "CBank"},
        )
        self.register.bootstrap_admin(
            principal_id="root", authority_ref="BOOTSTRAP", occurred_at=T,
        )
        self.register.open_bank_reserve_account(
            event_id="OPEN-RESERVE", bank_id="bank",
            central_bank_id="central-bank", currency="LCU",
            account_ref="BANK-RESERVE", opening_balance="500.00",
            evidence_ref="RESERVE-OPENING", actor_id="root",
            authority_ref="CB-OPENING", effective_at=T, recorded_at=T,
            expected_revision=0,
        )

    def tearDown(self):
        self.tmp.cleanup()

    def post(self, event_id, event_type, amount, period, revision, causation_id=None):
        return self.register.commit_central_bank_refinancing(
            event_id=event_id, event_type=event_type, facility_id="FACILITY-1",
            bank_id="bank", central_bank_id="central-bank", currency="LCU",
            amount=amount, period_index=period, evidence_ref=f"EVIDENCE:{event_id}",
            actor_id="root", authority_ref="CB-REFINANCING-POLICY",
            effective_at=T, recorded_at=T, expected_revision=revision,
            minor_unit="0.01", causation_id=causation_id,
        )

    def test_advance_and_principal_repayment_update_both_sides_of_sfc(self):
        self.post("REFI-ADVANCE", "central_bank.refinancing_advanced",
                  "100.00", 2, 1)
        self.assertEqual(
            self.register.bank_reserve_snapshot(
                "bank", "central-bank", "LCU", principal_id="root"
            )["reserve_balance"],
            D("600.00"),
        )
        self.post("REFI-REPAY", "central_bank.refinancing_principal_repaid",
                  "40.00", 3, 2, "REFI-ADVANCE")
        facility, revision = self.register.refinancing_state(
            "FACILITY-1", principal_id="root",
        )
        self.assertEqual(revision, 3)
        self.assertEqual(facility["outstanding_principal"], "60.00")
        self.assertEqual(facility["status"], "OUTSTANDING")
        self.assertEqual(
            self.register.bank_reserve_snapshot(
                "bank", "central-bank", "LCU", principal_id="root"
            )["reserve_balance"],
            D("560.00"),
        )
        self.assertTrue(self.register.verify())

    def test_refinancing_movements_are_two_mirrored_asset_liability_pairs(self):
        event = {
            "event_id": "REFI-ADVANCE",
            "event_type": "central_bank.refinancing_advanced",
            "facility_id": "FACILITY-1", "bank_id": "bank",
            "central_bank_id": "central-bank", "currency": "LCU",
            "amount": "100.00", "period_index": 2,
            "evidence_ref": "REFI-EVIDENCE",
        }
        movements = central_bank_refinancing_movement_specs(event)
        self.assertEqual(len(movements), 4)
        groups = {item["mirror_group_id"] for item in movements}
        self.assertEqual(groups, {
            "REFI-ADVANCE:LOAN", "REFI-ADVANCE:RESERVE",
        })
        for group in groups:
            pair = [item for item in movements if item["mirror_group_id"] == group]
            self.assertEqual(len(pair), 2)
            self.assertEqual(
                {item["mirror_side"] for item in pair},
                {"asset_holder", "liability_issuer"},
            )
            self.assertEqual(pair[0]["amount"], pair[1]["amount"])

    def test_advance_and_repayment_reconcile_bank_and_central_bank_positions(self):
        advance = {
            "event_id": "REFI-ADVANCE", "event_type": "central_bank.refinancing_advanced",
            "facility_id": "FACILITY-1", "bank_id": "bank",
            "central_bank_id": "central-bank", "currency": "LCU",
            "amount": "100.00", "period_index": 2, "evidence_ref": "ADVANCE",
        }
        repay = {
            "event_id": "REFI-REPAY", "event_type": "central_bank.refinancing_principal_repaid",
            "facility_id": "FACILITY-1", "bank_id": "bank",
            "central_bank_id": "central-bank", "currency": "LCU",
            "amount": "40.00", "period_index": 3, "evidence_ref": "REPAY",
        }
        groups = []
        for event in (advance, repay):
            specs = central_bank_refinancing_movement_specs(event)
            participants = []
            for name in ("physical", "capital", "labour", "product", "legal_rights", "financial"):
                payload = ({"stock_flow_movements": specs} if name == "financial"
                           else {"no_stock_flow_effect": f"not implicated: {name}"})
                participants.append({
                    "register_id": name, "common_event_id": event["event_id"],
                    "native_event_id": f'{event["event_id"]}:{name}',
                    "aggregate_version": 1, "payload": payload,
                })
            groups.append({
                "schema_version": 1, "transaction_id": event["event_id"],
                "common_event_id": event["event_id"], "events": tuple(participants),
            })
        movements = movements_from_event_groups(tuple(groups))
        identities = {movement.identity for movement in movements}
        opening_rows = self.register.reserve_opening_positions(
            period_index=1, principal_id="root",
        )
        initial = {row.identity: row.amount for row in opening_rows}
        reserve = "RESERVE:bank:central-bank:LCU"
        loan = "CBREFI:FACILITY-1"
        expected_positions = {
            f"{reserve}:ASSET": D("560.00"),
            f"{reserve}:LIABILITY": D("560.00"),
            f"{loan}:CB-ASSET": D("60.00"),
            f"{loan}:BANK-LIABILITY": D("60.00"),
        }
        openings, closings = [], []
        for identity in identities:
            balance = initial.get(identity, D("0"))
            openings.append(OpeningPosition(identity, 1, balance, f"OPEN:{identity.position_id}"))
            closings.append(ClosingPosition(identity, 1, balance, f"CLOSE:{identity.position_id}:1"))
            for period in (2, 3):
                openings.append(OpeningPosition(identity, period, balance, f"OPEN:{identity.position_id}:{period}"))
                balance += sum((
                    movement.amount for movement in movements
                    if movement.identity == identity and movement.period_index == period
                ), D("0"))
                closings.append(ClosingPosition(identity, period, balance, f"CLOSE:{identity.position_id}:{period}"))
        result = reconcile_periods(tuple(openings), movements, tuple(closings))
        self.assertEqual(result.event_count, 8)
        self.assertEqual(result.mirror_group_count, 4)
        closing = {
            row.identity.position_id: row.closing
            for row in result.periods if row.period_index == 3
        }
        self.assertEqual(closing, expected_positions)

    def test_wrong_central_bank_sector_is_rejected_without_posting(self):
        self.register.sectors["central-bank"] = "CB"
        with self.assertRaisesRegex(OperatingFinancialRegisterError, "central bank"):
            self.post("BAD-REFI", "central_bank.refinancing_advanced",
                      "100.00", 2, 1)
        self.register.sectors["central-bank"] = "CBank"
        self.assertIsNone(self.register.status("BAD-REFI"))
        self.assertEqual(
            self.register.bank_reserve_snapshot(
                "bank", "central-bank", "LCU", principal_id="root"
            )["reserve_balance"],
            D("500.00"),
        )
        self.assertTrue(self.register.verify())

    def test_over_repayment_is_rejected_without_any_partial_posting(self):
        self.post("REFI-ADVANCE", "central_bank.refinancing_advanced",
                  "100.00", 2, 1)
        before_reserves = self.register.bank_reserve_snapshot(
            "bank", "central-bank", "LCU", principal_id="root"
        )["reserve_balance"]
        before_facility, before_revision = self.register.refinancing_state(
            "FACILITY-1", principal_id="root",
        )
        with self.assertRaisesRegex(
            OperatingFinancialRegisterError, "exceeds outstanding principal"
        ):
            self.post("REFI-OVERPAY", "central_bank.refinancing_principal_repaid",
                      "100.01", 3, 2, "REFI-ADVANCE")
        self.assertIsNone(self.register.status("REFI-OVERPAY"))
        self.assertEqual(
            self.register.bank_reserve_snapshot(
                "bank", "central-bank", "LCU", principal_id="root"
            )["reserve_balance"],
            before_reserves,
        )
        after_facility, after_revision = self.register.refinancing_state(
            "FACILITY-1", principal_id="root",
        )
        self.assertEqual(after_facility, before_facility)
        self.assertEqual(after_revision, before_revision)
        self.assertTrue(self.register.verify())


if __name__ == "__main__":
    unittest.main(verbosity=2)
