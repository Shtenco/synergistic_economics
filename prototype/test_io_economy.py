import unittest
from decimal import Decimal as D

from io_economy import EconomyError, InputOutputEconomy, run_scenario


class InputOutputEconomyTests(unittest.TestCase):
    def test_baseline_conserves_money_and_physical_stocks(self):
        model = InputOutputEconomy()
        initial = model.initial_cash
        summary = model.run(12)
        self.assertEqual(D(summary["system_cash"]), initial)
        self.assertEqual(D(summary["cash_conservation_error"]), 0)
        self.assertEqual(D(summary["max_abs_physical_balance_error"]), 0)
        self.assertGreater(int(summary["event_count"]), 0)

    def test_production_plan_replenishes_output_inventory_toward_capacity(self):
        model = InputOutputEconomy()
        firm = model.firms["farm-north"]
        firm.inventory["grain"] = firm.config.output_capacity
        plans = model._plan_production()
        self.assertEqual(plans["farm-north"], 0)
        firm.inventory["grain"] = 0
        plans = model._plan_production()
        self.assertEqual(plans["farm-north"], firm.config.output_capacity)

    def test_multiple_suppliers_exist_for_same_product(self):
        model = InputOutputEconomy()
        grain_suppliers = [
            f.firm_id for f in model.firm_configs if f.output_product == "grain"
        ]
        energy_suppliers = [
            f.firm_id for f in model.firm_configs if f.output_product == "energy"
        ]
        self.assertGreaterEqual(len(grain_suppliers), 2)
        self.assertGreaterEqual(len(energy_suppliers), 2)

    def test_every_product_has_a_market_price_and_physical_identity(self):
        model = InputOutputEconomy()
        model.run(3)
        self.assertEqual(set(model.prices), set(model.product_by_id))
        for result in model.period_results:
            for error in result.physical_balance_error.values():
                self.assertEqual(D(str(error)), 0)

    def test_scenario_runs_are_deterministic(self):
        a = run_scenario("baseline", 4)["summary"]
        b = run_scenario("baseline", 4)["summary"]
        self.assertEqual(a, b)

    def test_demand_collapse_reduces_household_expenditure(self):
        baseline = run_scenario("baseline", 8)["summary"]
        shock = run_scenario("demand_collapse", 8)["summary"]
        self.assertLess(
            D(shock["cumulative_household_expenditure"]),
            D(baseline["cumulative_household_expenditure"])
        )

    def test_high_ask_imports_wait_for_bounded_price_discovery(self):
        from io_economy import FirmConfig, HouseholdConfig, Product
        model = InputOutputEconomy(
            products=[Product("test-good", "unit", D("1"), D("2"), D("10"))],
            firms=[FirmConfig(
                "idle-firm", "test-good", {}, D("1"), D("0"), D("0"),
                D("1"), D("1000"), {}
            )],
            households=[HouseholdConfig(
                "test-household", D("100"), {"test-good": D("5")}, D("1")
            )]
        )
        previous_price = model.prices["test-good"]
        first = model.step(1)
        first_price = D(first.prices["test-good"])
        self.assertEqual(D(first.imports["test-good"]), 0)
        self.assertLessEqual(first_price, previous_price * D("1.35"))
        self.assertEqual(D(first.household_consumption["test-good"]), 0)

        for period in range(2, 12):
            previous_price = model.prices["test-good"]
            result = model.step(period)
            current_price = model.prices["test-good"]
            self.assertLessEqual(current_price, previous_price * D("1.35"))
            self.assertGreaterEqual(current_price, previous_price * D("0.65"))
        imported = sum((D(r.imports["test-good"]) for r in model.period_results), D("0"))
        self.assertGreater(imported, 0)

    def test_invalid_market_parameters_are_rejected(self):
        with self.assertRaises(EconomyError):
            InputOutputEconomy(max_price_change=D("1.0"))
        with self.assertRaises(EconomyError):
            InputOutputEconomy(price_adjustment=D("-0.1"))
        with self.assertRaises(EconomyError):
            InputOutputEconomy(household_demand_multiplier=D("-1"))

    def test_import_shock_does_not_break_conservation(self):
        summary = run_scenario("energy_import_shock", 8)["summary"]
        self.assertEqual(D(summary["cash_conservation_error"]), 0)
        self.assertEqual(D(summary["max_abs_physical_balance_error"]), 0)

    def test_metals_shortage_is_a_valid_stress_scenario(self):
        summary = run_scenario("metals_shortage", 8)["summary"]
        self.assertIn("metals", summary["cumulative_shortages_by_product"])
        self.assertEqual(D(summary["cash_conservation_error"]), 0)

    def test_compound_shock_preserves_all_invariants(self):
        summary = run_scenario("compound_shock", 12)["summary"]
        self.assertEqual(D(summary["cash_conservation_error"]), 0)
        self.assertEqual(D(summary["max_abs_physical_balance_error"]), 0)

    def test_self_input_recipe_is_rejected_until_explicitly_modelled(self):
        products = InputOutputEconomy.default_products()
        firms = InputOutputEconomy.default_firms()
        base = firms[0]
        firms[0] = type(base)(
            base.firm_id, base.output_product, {"grain": D("0.1")},
            base.labour_per_unit, base.labour_capacity, base.output_capacity,
            base.wage_per_labour, base.initial_cash, base.initial_inventory,
            base.domestic_ask_markup
        )
        with self.assertRaises(EconomyError):
            InputOutputEconomy(products, firms, InputOutputEconomy.default_households())

    def test_invalid_product_reference_is_rejected(self):
        products = InputOutputEconomy.default_products()
        firms = InputOutputEconomy.default_firms()
        bad = firms[0]
        firms[0] = type(bad)(
            bad.firm_id, bad.output_product, {"unknown-good": D("1")},
            bad.labour_per_unit, bad.labour_capacity, bad.output_capacity,
            bad.wage_per_labour, bad.initial_cash, bad.initial_inventory,
            bad.domestic_ask_markup
        )
        with self.assertRaises(EconomyError):
            InputOutputEconomy(products, firms, InputOutputEconomy.default_households())

    def test_no_negative_cash_balances(self):
        model = InputOutputEconomy()
        model.run(12)
        self.assertTrue(all(f.cash >= 0 for f in model.firms.values()))
        self.assertTrue(all(h.cash >= 0 for h in model.households.values()))

    def test_household_spending_stays_within_opening_period_budget(self):
        model = InputOutputEconomy()
        opening_budgets = {
            household_id: state.cash * state.config.consumption_propensity
            for household_id, state in model.households.items()
        }
        model.step(1)
        for household_id, state in model.households.items():
            self.assertLessEqual(state.expenditure, opening_budgets[household_id])

    def test_household_expenditure_is_period_flow_not_cumulative_stock(self):
        model = InputOutputEconomy()
        model.run(3)
        values = [r.household_expenditure for r in model.period_results]
        self.assertTrue(all(v >= 0 for v in values))
        self.assertEqual(
            sum(values, D("0")),
            sum((h.expenditure for h in model.households.values()), D("0"))
        )

    def test_summary_reports_separate_physical_outputs_and_imports(self):
        summary = run_scenario("baseline", 2)["summary"]
        self.assertIn("cumulative_production_by_product", summary)
        self.assertIn("cumulative_imports_by_product", summary)
        self.assertIn("cumulative_shortages_by_product", summary)

    def test_default_wages_follow_firm_household_employment_shares(self):
        model = InputOutputEconomy()
        result = model.step(1)
        wage_income = {key: D(value) for key, value in result.household_wage_income.items()}
        labour_hours = {key: D(value) for key, value in result.household_labour_hours.items()}
        self.assertEqual(sum(wage_income.values(), D("0")), result.wages)
        self.assertEqual(
            sum(labour_hours.values(), D("0")),
            sum((state.production * state.config.labour_per_unit for state in model.firms.values()), D("0")),
        )
        self.assertTrue(all(value >= 0 for value in wage_income.values()))
        self.assertGreater(len({value for value in wage_income.values()}), 1)
        self.assertGreater(len({value for value in labour_hours.values()}), 1)
        production_events = [row for row in model.events if row["kind"] == "production"]
        self.assertTrue(production_events)
        for row in production_events:
            payload = row["payload"]
            self.assertEqual(
                sum((D(value) for value in payload["wage_by_household"].values()), D("0")),
                D(payload["wages"]),
            )
            self.assertEqual(
                sum((D(value) for value in payload["labour_hours_by_household"].values()), D("0")),
                D(payload["labour_hours"]),
            )

    def test_household_labour_supply_caps_hiring_and_reports_unemployment(self):
        from dataclasses import replace
        households = [
            replace(item, labour_supply_hours=D("2"))
            for item in InputOutputEconomy.default_households()
        ]
        model = InputOutputEconomy(households=households)
        result = model.step(1)
        for household_id, state in model.households.items():
            worked = D(result.household_labour_hours[household_id])
            supply = D(result.household_labour_supply_hours[household_id])
            unemployed = D(result.household_unemployment_hours[household_id])
            self.assertLessEqual(worked, supply)
            self.assertEqual(unemployed, supply - worked)
            self.assertEqual(
                D(result.household_employment_rate[household_id]),
                worked / supply,
            )
        self.assertGreater(sum((D(x) for x in result.household_unemployment_hours.values()), D("0")), 0)
        self.assertEqual(
            sum((D(x) for x in result.household_labour_hours.values()), D("0")),
            sum((state.production * state.config.labour_per_unit for state in model.firms.values()), D("0")),
        )

    def test_abundant_household_supply_does_not_constrain_firm_production(self):
        from dataclasses import replace
        households = [
            replace(item, labour_supply_hours=D("1000"))
            for item in InputOutputEconomy.default_households()
        ]
        model = InputOutputEconomy(households=households)
        result = model.step(1)
        worked = sum((D(x) for x in result.household_labour_hours.values()), D("0"))
        self.assertEqual(
            worked,
            sum((state.production * state.config.labour_per_unit for state in model.firms.values()), D("0")),
        )
        self.assertGreater(
            sum((D(x) for x in result.household_unemployment_hours.values()), D("0")),
            0,
        )
        self.assertTrue(all(D(result.household_labour_supply_hours[k]) >= D(result.household_labour_hours[k]) for k in model.households))

    def test_labour_supply_must_be_finite_and_nonnegative(self):
        from dataclasses import replace
        for value in (D("-1"), D("NaN")):
            households = [
                replace(item, labour_supply_hours=value)
                for item in InputOutputEconomy.default_households()
            ]
            with self.assertRaises(EconomyError):
                InputOutputEconomy(households=households)

    def test_labour_market_events_reconcile_household_worked_hours(self):
        model = InputOutputEconomy()
        result = model.step(1)
        events = [row for row in model.events if row["kind"] == "labour_market_clearing"]
        self.assertEqual(len(events), 1)
        payload = events[0]["payload"]
        self.assertEqual(
            sum((D(v) for v in payload["household_worked_hours"].values()), D("0")),
            sum((D(v) for v in result.household_labour_hours.values()), D("0")),
        )
        self.assertEqual(
            sum((D(v) for v in payload["household_unemployment_hours"].values()), D("0")),
            sum((D(v) for v in result.household_unemployment_hours.values()), D("0")),
        )

    def test_nonwage_income_sources_are_funded_and_separately_recorded(self):
        from io_economy import HouseholdIncomePayment, HouseholdConfig, FirmConfig, Product
        payments = [
            HouseholdIncomePayment(
                "DIVIDEND-1", "dividend", "firm", "firm-1", "household-1",
                D("30"), 1, "DIVIDEND-EVIDENCE",
            ),
            HouseholdIncomePayment(
                "PENSION-1", "pension", "income_fund", "pension-fund", "household-1",
                D("20"), 1, "PENSION-EVIDENCE",
            ),
            HouseholdIncomePayment(
                "INTEREST-1", "interest", "income_fund", "interest-fund", "household-1",
                D("5"), 1, "INTEREST-EVIDENCE",
            ),
        ]
        model = InputOutputEconomy(
            products=[Product("good", "unit", D("1"), D("1"), D("0"))],
            firms=[FirmConfig("firm-1", "good", {}, D("1"), D("0"), D("0"),
                              D("1"), D("100"), {})],
            households=[HouseholdConfig("household-1", D("0"), {}, D("0"), D("0"))],
            income_payments=payments,
            income_source_funds={"pension-fund": D("20"), "interest-fund": D("5")},
        )
        opening_cash = model.initial_cash
        result = model.step(1)
        self.assertEqual(result.household_income_by_source["household-1"], {
            "dividend": "30.00", "pension": "20.00", "interest": "5.00"
        })
        self.assertEqual(result.household_total_income["household-1"], "55.00")
        self.assertEqual(model.households["household-1"].cash, D("55.00"))
        self.assertEqual(model.firms["firm-1"].cash, D("70.00"))
        self.assertEqual(model.income_source_cash["pension-fund"], D("0.00"))
        self.assertEqual(model.income_source_cash["interest-fund"], D("0.00"))
        self.assertEqual(model._system_cash(), opening_cash)
        payment_events = [row for row in model.events if row["kind"] == "household_income_payment"]
        self.assertEqual(len(payment_events), 3)
        self.assertTrue(all(row["payload"]["evidence_ref"] for row in payment_events))

    def test_unfunded_household_income_carries_arrears_without_creating_cash(self):
        from io_economy import HouseholdIncomePayment, HouseholdConfig, FirmConfig, Product
        payment = HouseholdIncomePayment(
            "PENSION-ARREAR-1", "pension", "income_fund", "pension-fund",
            "household-1", D("10"), 1, "PENSION-ARREAR-EVIDENCE",
        )
        model = InputOutputEconomy(
            products=[Product("good", "unit", D("1"), D("1"), D("0"))],
            firms=[FirmConfig("firm-1", "good", {}, D("1"), D("0"), D("0"),
                              D("1"), D("0"), {})],
            households=[HouseholdConfig("household-1", D("0"), {}, D("0"), D("0"))],
            income_payments=[payment],
            income_source_funds={"pension-fund": D("4")},
        )
        opening_cash = model.initial_cash
        first = model.step(1)
        second = model.step(2)
        self.assertEqual(first.household_income_payment_arrears[payment.payment_id], "6.00")
        self.assertEqual(second.household_income_payment_arrears[payment.payment_id], "6.00")
        self.assertEqual(model.households["household-1"].cash, D("4.00"))
        self.assertEqual(model._system_cash(), opening_cash)

    def test_income_payments_reject_unknown_or_unfunded_payers(self):
        from io_economy import HouseholdIncomePayment, HouseholdConfig, FirmConfig, Product
        base = dict(
            payment_id="INCOME-1", source_type="pension", payer_kind="income_fund",
            payer_id="missing-fund", recipient_id="household-1", amount=D("1"),
            period=1, evidence_ref="INCOME-EVIDENCE",
        )
        with self.assertRaises(EconomyError):
            InputOutputEconomy(
                products=[Product("good", "unit", D("1"), D("1"), D("0"))],
                firms=[FirmConfig("firm-1", "good", {}, D("1"), D("0"), D("0"), D("1"), D("0"), {})],
                households=[HouseholdConfig("household-1", D("0"), {}, D("0"), D("0"))],
                income_payments=[HouseholdIncomePayment(**base)],
            )
        bad = dict(base, source_type="unknown", payer_id="fund")
        with self.assertRaises(EconomyError):
            InputOutputEconomy(
                products=[Product("good", "unit", D("1"), D("1"), D("0"))],
                firms=[FirmConfig("firm-1", "good", {}, D("1"), D("0"), D("0"), D("1"), D("0"), {})],
                households=[HouseholdConfig("household-1", D("0"), {}, D("0"), D("0"))],
                income_payments=[HouseholdIncomePayment(**bad)],
                income_source_funds={"fund": D("1")},
            )

    def test_invalid_explicit_household_labour_shares_are_rejected(self):
        firms = InputOutputEconomy.default_firms()
        base = firms[0]
        firms[0] = type(base)(
            base.firm_id, base.output_product, base.recipe, base.labour_per_unit,
            base.labour_capacity, base.output_capacity, base.wage_per_labour,
            base.initial_cash, base.initial_inventory, base.domestic_ask_markup,
            {"household-1": D("0.8")},
        )
        with self.assertRaises(EconomyError):
            InputOutputEconomy(
                InputOutputEconomy.default_products(), firms,
                InputOutputEconomy.default_households(),
            )


if __name__ == "__main__":
    unittest.main(verbosity=2)
