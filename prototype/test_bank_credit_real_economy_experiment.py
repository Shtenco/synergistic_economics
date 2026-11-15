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
        for scenario in ("productive", "productive_capex", "consumption", "asset_purchase"):
            case = result["cases"][scenario]
            self.assertEqual(case["credit_principal_issued"], "12000.00")
            self.assertEqual(case["deposit_money_created"], "12000.00")
        self.assertEqual(result["cases"]["baseline"]["credit_principal_issued"], "0")

    def test_baseline_does_not_report_unissued_credit_as_new_deposit_money(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=4)
        baseline = result["cases"]["baseline"]
        self.assertEqual(baseline["deposit_money_created"], "0")
        self.assertEqual(baseline["net_new_deposit_money"], "0")
        for row in baseline["periods"]:
            self.assertEqual(D(row["net_new_deposit_money"]), D("0"))

    def test_net_new_deposit_money_tracks_origination_less_repayment(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=5)
        for scenario in ("productive", "productive_capex", "consumption", "asset_purchase"):
            case = result["cases"][scenario]
            for row in case["periods"]:
                self.assertEqual(
                    D(row["net_new_deposit_money"]),
                    D("12000.00") - sum(
                        (D(item["principal_repaid"]) for item in case["periods"][:row["period"]]),
                        D("0"),
                    ),
                )

    def test_asset_purchase_does_not_directly_expand_real_production(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=4)
        baseline_period_one = D(result["cases"]["baseline"]["periods"][0]["gross_value_added_proxy"])
        asset_period_one = D(result["cases"]["asset_purchase"]["periods"][0]["gross_value_added_proxy"])
        # Before the first principal instalment, the asset purchase only transfers
        # deposits into the asset market and cannot directly create physical output.
        self.assertEqual(asset_period_one, baseline_period_one)
        self.assertGreater(
            D(result["cases"]["asset_purchase"]["summary"]["final_asset_price_index"]),
            D("1"),
        )

    def test_money_and_physical_accounts_close_for_every_period(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=5)
        for case in result["cases"].values():
            for period in case["periods"]:
                self.assertLessEqual(abs(D(period["physical_balance_error"])), D("0.000001"))
                self.assertEqual(D(period["monetary_conservation_error"]), D("0"))

    def test_credit_repayment_reduces_deposit_money_and_loan_principal(self):
        result = run_credit_allocation_experiment(credit_amount="12000", periods=5)
        for scenario in ("productive", "productive_capex", "consumption", "asset_purchase"):
            case = result["cases"][scenario]
            destroyed = D(case["deposit_money_destroyed"])
            outstanding = D(case["credit_principal_outstanding"])
            self.assertEqual(D("12000.00") - destroyed, outstanding)
            self.assertGreaterEqual(destroyed, D("0"))

    def test_productive_capex_has_delivery_and_commissioning_lags(self):
        case = run_credit_allocation_experiment(credit_amount="12000", periods=5)["cases"]["productive_capex"]
        self.assertEqual(case["capex_order"]["delivery_period"], 2)
        self.assertEqual(case["capex_order"]["commissioning_period"], 3)
        periods = case["periods"]
        self.assertEqual(periods[0]["firm_commissioned_capacity_by_firm"]["farm-north"], "0")
        self.assertEqual(periods[1]["firm_commissioned_capacity_by_firm"]["farm-north"], "0")
        self.assertEqual(periods[2]["firm_commissioned_capacity_by_firm"]["farm-north"], "3")
        self.assertEqual(periods[1]["capital_formation_by_product"]["machinery"], "1")
        self.assertEqual(periods[2]["capital_formation_by_product"]["machinery"], "0")
        self.assertEqual(case["credit_principal_issued"], "12000.00")
        self.assertEqual(case["capex_order"]["credit_event_id"], "CREDIT-ORIGINATION-PRODUCTIVE-CAPEX")

    def test_ci_scale_credit_experiment_preserves_physical_stocks(self):
        # The CI scenario is intentionally larger than the small unit fixtures.
        # It exercises cash-cent rounding against eight-decimal physical quantities.
        result = run_credit_allocation_experiment(credit_amount="50000", periods=12)
        for case in result["cases"].values():
            for row in case["periods"]:
                self.assertLessEqual(
                    abs(D(row["physical_balance_error"])),
                    D("0.000001"),
                )

    def test_period_metrics_include_real_and_financial_indicators(self):
        case = BankCreditAllocationExperiment(credit_amount="10000", periods=3).run()["cases"]["productive"]
        row = case["periods"][-1]
        for key in (
            "gross_value_added_proxy", "employment_hours", "labour_productivity_proxy",
            "consumer_price_index", "outstanding_bank_loan_assets",
            "borrower_principal_liabilities", "borrower_net_worth_proxy",
            "debt_service_liquidity_coverage", "household_wage_income_gini",
            "household_wage_income", "household_labour_hours",
        ):
            self.assertIn(key, row)
        wage_income = {k: D(v) for k, v in row["household_wage_income"].items()}
        labour_hours = {k: D(v) for k, v in row["household_labour_hours"].items()}
        self.assertGreater(D(row["household_wage_income_gini"]), D("0"))
        self.assertGreater(len({v for v in wage_income.values()}), 1)
        self.assertGreater(len({v for v in labour_hours.values()}), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
