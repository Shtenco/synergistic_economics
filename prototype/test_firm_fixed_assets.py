"""Tests for paid capex, physical delivery, commissioning and depreciation."""
import unittest
from decimal import Decimal as D

from firm_fixed_assets import (
    AssetCohort, FixedAssetError, FixedAssetLedger, InvestmentOrder,
)


def order(**overrides):
    values = dict(
        order_id="capex-1", credit_event_id="loan-1", payment_event_id="pay-1",
        borrower_id="farm-north", supplier_id="machine-works", asset_type="tractor",
        quantity=D("2"), unit_cost=D("1000"), order_period=1, delivery_period=2,
        commissioning_period=3, useful_life_periods=5,
        residual_value_per_unit=D("100"), service_capacity_per_unit=D("4"),
    )
    values.update(overrides)
    return InvestmentOrder(**values)


class FixedAssetLedgerTests(unittest.TestCase):
    def test_credit_order_is_not_capacity_before_delivery_and_commissioning(self):
        ledger = FixedAssetLedger()
        item = order()
        ledger.place_paid_order(item, payment_amount="2000", payment_currency="KZT",
                                order_currency="KZT", payment_evidence_ref="bank-payment:1")
        self.assertEqual(ledger.commissioned_capacity("farm-north", 1), D("0"))
        ledger.deliver(event_id="delivery-1", order_id=item.order_id, quantity="2",
                       period=2, evidence_ref="goods-receipt:1")
        self.assertEqual(ledger.commissioned_capacity("farm-north", 2), D("0"))
        self.assertEqual(ledger.commissioned_capacity("farm-north", 3), D("8"))
        self.assertEqual(ledger.carrying_value("farm-north", 3), D("2000"))

    def test_straight_line_depreciation_to_residual(self):
        ledger = FixedAssetLedger()
        item = order()
        ledger.place_paid_order(item, payment_amount="2000", payment_currency="KZT",
                                order_currency="KZT", payment_evidence_ref="payment:1")
        ledger.deliver(event_id="delivery-1", order_id=item.order_id, quantity="2",
                       period=2, evidence_ref="receipt:1")
        self.assertEqual(ledger.carrying_value("farm-north", 4), D("1640"))
        self.assertEqual(ledger.carrying_value("farm-north", 8), D("200"))

    def test_partial_delivery_does_not_create_full_cohort_or_capacity(self):
        ledger = FixedAssetLedger()
        item = order()
        ledger.place_paid_order(item, payment_amount="2000", payment_currency="KZT",
                                order_currency="KZT", payment_evidence_ref="payment:1")
        ledger.deliver(event_id="delivery-1", order_id=item.order_id, quantity="1",
                       period=2, evidence_ref="receipt:1")
        self.assertEqual(ledger.commissioned_capacity("farm-north", 2), D("0"))
        self.assertEqual(ledger.commissioned_capacity("farm-north", 3), D("4"))
        self.assertEqual(ledger.physical_reconciliation(item.order_id)["undelivered"], D("1"))

    def test_rejects_underpayment_currency_mismatch_and_overdelivery(self):
        ledger = FixedAssetLedger()
        with self.assertRaises(FixedAssetError):
            ledger.place_paid_order(order(), payment_amount="1999", payment_currency="KZT",
                                    order_currency="KZT", payment_evidence_ref="payment:1")
        with self.assertRaises(FixedAssetError):
            ledger.place_paid_order(order(), payment_amount="2000", payment_currency="USD",
                                    order_currency="KZT", payment_evidence_ref="payment:1")
        item = order()
        ledger.place_paid_order(item, payment_amount="2000", payment_currency="KZT",
                                order_currency="KZT", payment_evidence_ref="payment:1")
        with self.assertRaises(FixedAssetError):
            ledger.deliver(event_id="delivery-1", order_id=item.order_id, quantity="3",
                           period=2, evidence_ref="receipt:1")

    def test_retirement_reduces_physical_units_and_capacity(self):
        ledger = FixedAssetLedger()
        item = order()
        ledger.place_paid_order(item, payment_amount="2000", payment_currency="KZT",
                                order_currency="KZT", payment_evidence_ref="payment:1")
        ledger.deliver(event_id="delivery-1", order_id=item.order_id, quantity="2",
                       period=2, evidence_ref="receipt:1")
        ledger.retire(event_id="retire-1", cohort_id="cohort:capex-1:delivery-1", quantity="1",
                     period=4, evidence_ref="scrap-certificate:1")
        self.assertEqual(ledger.commissioned_capacity("farm-north", 4), D("4"))
        self.assertEqual(ledger.cohorts["cohort:capex-1:delivery-1"].active_quantity, D("1"))

    def test_capacity_expires_after_useful_life(self):
        ledger = FixedAssetLedger()
        item = order()
        ledger.place_paid_order(item, payment_amount="2000", payment_currency="KZT",
                                order_currency="KZT", payment_evidence_ref="payment:1")
        ledger.deliver(event_id="delivery-1", order_id=item.order_id, quantity="2",
                       period=2, evidence_ref="receipt:1")
        self.assertEqual(ledger.commissioned_capacity("farm-north", 7), D("8"))
        self.assertEqual(ledger.commissioned_capacity("farm-north", 8), D("0"))
        self.assertEqual(ledger.carrying_value("farm-north", 8), D("200"))

    def test_order_requires_explicit_credit_and_payment_identity(self):
        with self.assertRaises(FixedAssetError):
            order(credit_event_id="")
        with self.assertRaises(FixedAssetError):
            order(commissioning_period=1, delivery_period=2)


if __name__ == "__main__":
    unittest.main()
