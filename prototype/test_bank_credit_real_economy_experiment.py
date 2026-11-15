"""Tests for equal-volume bank-credit allocation across the physical IO economy."""
import unittest
from decimal import Decimal as D

from bank_credit_real_economy_experiment import (
    BankCreditAllocationExperiment,
    run_credit_allocation_experiment,
)


class BankCreditRealEconomyExperimentTests(unittest.TestCase):
    def test_equal_principal_is_issued_in_each_credit_scenario(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=4)
        for scenario in ("productive", "consumption", "asset_purchase"):
            case = result["cases"][scenario]
            self.assertEqual(case["credit_principal_issued"], "12000.00")
            self.assertEqual(case["deposit_money_created"], "12000.00")
        self.assertEqual(result["cases"]["baseline"]["credit_principal_issued"], "0")

    def test_asset_purchase_does_not_directly_expand_real_production(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=4)
        baseline = D(result["cases"]["baseline"]["summary"]["cumulative_gross_value_added_proxy"])
        asset_case = D(result["cases"]["asset_purchase"]["summary"]["cumulative_gross_value_added_proxy"])
        self.assertEqual(asset_case, baseline)
        self.assertGreater(
            D(result["cases"]["asset_purchase"]["summary"]["final_asset_price_index"]),
            D("1"),
        )

    def test_money_and_physical_accounts_close_for_every_period(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=5)
        for case in result["cases"].values():
            for period in case["periods"]:
                self.assertEqual(D(period["physical_balance_error"]), D("0"))
                self.assertEqual(D(period["monetary_conservation_error"]), D("0"))

    def test_credit_repayment_reduces_deposit_money_and_loan_principal(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=5)
        for scenario in ("productive", "consumption", "asset_purchase"):
            case = result["cases"][scenario]
            destroyed = D(case["deposit_money_destroyed"])
            outstanding = D(case["credit_principal_outstanding"])
            self.assertEqual(D("12000.00") - destroyed, outstanding)
            self.assertGreaterEqual(destroyed, D("0"))

    def test_period_metrics_include_real_and_financial_indicators(self):
        case = BankCreditAllocationExperiment(credit_amount="10000", periods=3).run()["cases"]["productive"]
        row = case["periods"][-1]
        for key in (
            "gross_value_added_proxy", "employment_hours", "labour_productivity_proxy",
            "consumer_price_index", "outstanding_bank_loan_assets",
            "borrower_principal_liabilities", "borrower_net_worth_proxy",
            "debt_service_liquidity_coverage", "household_wage_income_gini",
        ):
            self.assertIn(key, row)


if __name__ == "__main__":
    unittest.main(verbosity=2)
