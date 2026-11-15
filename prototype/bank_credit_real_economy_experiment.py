"""Controlled bank-credit allocation experiment over the physical IO economy.

Research harness, not a calibrated forecast or production banking system.
It compares equal principal issuance directed to productive working capital,
household consumption, or an external financial-asset purchase. Principal
repayment destroys deposit money; interest, defaults, collateral, reserves and
bank capital are deliberately outside v1.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json
from typing import Mapping

from io_economy import InputOutputEconomy, ZERO, D, CENT, cash


class CreditExperimentError(ValueError):
    pass


SCENARIOS = ("baseline", "productive", "consumption", "asset_purchase")


def _gini(values):
    values = [float(value) for value in values]
    if not values or sum(values) <= 0:
        return 0.0
    ordered = sorted(max(0.0, value) for value in values)
    total = sum(ordered)
    n = len(ordered)
    weighted = sum((index + 1) * value for index, value in enumerate(ordered))
    return max(0.0, min(1.0, (2.0 * weighted) / (n * total) - (n + 1) / n))


def _split(amount: Decimal, count: int) -> list[Decimal]:
    if count < 1:
        raise CreditExperimentError("credit allocation requires at least one borrower")
    each = (amount / D(count)).quantize(CENT, rounding=ROUND_HALF_UP)
    result = [each for _ in range(count)]
    result[-1] += amount - sum(result, ZERO)
    return result


class CreditEnabledInputOutputEconomy(InputOutputEconomy):
    """Adds explicitly tracked asset-market deposits to the IO cash perimeter."""

    def __init__(self, *args, **kwargs):
        self.asset_market_cash = ZERO
        super().__init__(*args, **kwargs)

    def _system_cash(self):
        return super()._system_cash() + self.asset_market_cash


@dataclass(frozen=True)
class CreditPeriodMetrics:
    period: int
    gross_value_added_proxy: str
    physical_output_by_product: dict
    employment_hours: str
    labour_productivity_proxy: str
    consumer_price_index: str
    asset_price_index: str
    outstanding_bank_loan_assets: str
    borrower_principal_liabilities: str
    net_new_deposit_money: str
    principal_repaid: str
    principal_due: str
    arrears: str
    borrower_cash: str
    debt_to_income_proxy: str
    debt_to_assets_proxy: str
    borrower_net_worth_proxy: str
    insolvent_borrower_count: int
    debt_service_liquidity_coverage: str | None
    household_essential_cash_coverage: str
    household_wage_income_gini: str
    physical_balance_error: str
    monetary_conservation_error: str


class BankCreditAllocationExperiment:
    """Run a matched baseline and three equal-volume credit-allocation cases."""

    ASSET_MARKET_DEPTH = D("100000")
    ASSET_PRICE_IMPACT = D("0.25")

    def __init__(self, *, credit_amount="50000", periods=12):
        try:
            amount = D(str(credit_amount))
        except Exception as exc:
            raise CreditExperimentError("credit_amount must be a decimal") from exc
        if not amount.is_finite() or amount <= 0:
            raise CreditExperimentError("credit_amount must be finite and positive")
        if not isinstance(periods, int) or isinstance(periods, bool) or periods < 1:
            raise CreditExperimentError("periods must be a positive integer")
        self.credit_amount = amount.quantize(CENT, rounding=ROUND_HALF_UP)
        if self.credit_amount <= 0:
            raise CreditExperimentError("credit_amount rounds to zero")
        self.periods = periods

    @staticmethod
    def _price_index(model):
        numerator = denominator = ZERO
        for household in model.households.values():
            for product_id, weight in household.config.basket.items():
                base = model.product_by_id[product_id].base_price
                numerator += weight * model.prices[product_id]
                denominator += weight * base
        return numerator / denominator if denominator > 0 else D("1")

    @staticmethod
    def _borrower_cash(model, borrower_kind, borrower_id):
        if borrower_kind == "firm":
            return model.firms[borrower_id].cash
        return model.households[borrower_id].cash

    @staticmethod
    def _set_borrower_cash(model, borrower_kind, borrower_id, value):
        if borrower_kind == "firm":
            model.firms[borrower_id].cash = value
        else:
            model.households[borrower_id].cash = value

    def _issue_credit(self, model, scenario):
        borrowers = []
        if scenario == "productive":
            borrowers = [("firm", key) for key in sorted(model.firms)]
        elif scenario in ("consumption", "asset_purchase"):
            borrowers = [("household", key) for key in sorted(model.households)]
        else:
            return {}, {}, D("1")

        allocations = _split(self.credit_amount, len(borrowers))
        debt = {}
        assets = {}
        for (kind, borrower_id), amount in zip(borrowers, allocations):
            cash_balance = self._borrower_cash(model, kind, borrower_id)
            self._set_borrower_cash(model, kind, borrower_id, cash_balance + amount)
            debt[(kind, borrower_id)] = amount
            assets[(kind, borrower_id)] = ZERO

        asset_price_index = ZERO
        if scenario == "asset_purchase":
            asset_price_index = D("1") + (
                self.ASSET_PRICE_IMPACT * self.credit_amount
                / (self.ASSET_MARKET_DEPTH + self.credit_amount)
            )
            for key, principal in debt.items():
                kind, borrower_id = key
                balance = self._borrower_cash(model, kind, borrower_id)
                self._set_borrower_cash(model, kind, borrower_id, balance - principal)
                assets[key] = principal / (D("100") * asset_price_index)
                model.asset_market_cash += principal
        else:
            asset_price_index = D("1")

        # A bank loan creates a matching deposit. No pre-existing cash is moved
        # into the economy: the perimeter expands by exactly the new principal.
        model.initial_cash = model._system_cash()
        return debt, assets, asset_price_index

    @staticmethod
    def _firm_inventory_value(model, firm):
        return sum((
            quantity * model.prices[product_id]
            for product_id, quantity in firm.inventory.items()
            if product_id in model.prices
        ), ZERO)

    def _metrics(self, model, scenario, period, result, debt, arrears,
                 asset_holdings, asset_price_index, original_cash,
                 total_repaid, total_due, total_destroyed):
        borrower_cash = sum((
            self._borrower_cash(model, kind, borrower_id)
            for kind, borrower_id in debt
        ), ZERO)
        debt_total = sum(debt.values(), ZERO)
        assets_total = ZERO
        net_worth_total = ZERO
        insolvent = 0
        borrower_income = ZERO
        for (kind, borrower_id), principal in debt.items():
            if kind == "firm":
                state = model.firms[borrower_id]
                asset_value = state.cash + self._firm_inventory_value(model, state)
                income = state.sales_revenue
            else:
                state = model.households[borrower_id]
                asset_value = state.cash + asset_holdings[(kind, borrower_id)] * D("100") * asset_price_index
                income = state.wage_income
            net_worth = asset_value - principal
            assets_total += asset_value
            net_worth_total += net_worth
            borrower_income += income
            if net_worth < 0:
                insolvent += 1

        labour_hours = sum((
            state.production * state.config.labour_per_unit
            for state in model.firms.values()
        ), ZERO)
        gva = result.gross_value_added_proxy
        productivity = gva / labour_hours if labour_hours > 0 else ZERO
        price_index = self._price_index(model)

        due_for_period = total_due
        liquidity = borrower_cash / due_for_period if due_for_period > 0 else None
        essential_need = ZERO
        household_cash = sum((h.cash for h in model.households.values()), ZERO)
        for household in model.households.values():
            essential_need += sum((
                quantity * model.prices[product_id]
                for product_id, quantity in household.config.basket.items()
            ), ZERO)
        household_coverage = household_cash / essential_need if essential_need > 0 else ZERO

        household_income = [h.wage_income for h in model.households.values()]
        income_gini = _gini(household_income)
        debt_income = debt_total / borrower_income if borrower_income > 0 else ZERO
        debt_assets = debt_total / assets_total if assets_total > 0 else ZERO
        expected_money = original_cash + self.credit_amount - total_destroyed
        actual_money = model._system_cash()
        money_error = actual_money - expected_money
        physical_error = max(
            (abs(value) for value in result.physical_balance_error.values()),
            default=ZERO,
        )
        if money_error != 0:
            raise CreditExperimentError(f"deposit-money conservation failed in period {period}: {money_error}")
        if physical_error > D("0.000001"):
            raise CreditExperimentError(f"physical stock balance failed in period {period}: {physical_error}")
        if any(f.cash < 0 for f in model.firms.values()) or any(h.cash < 0 for h in model.households.values()):
            raise CreditExperimentError("credit experiment produced a negative cash balance")

        return CreditPeriodMetrics(
            period=period,
            gross_value_added_proxy=str(gva),
            physical_output_by_product=result.production,
            employment_hours=str(labour_hours),
            labour_productivity_proxy=str(productivity),
            consumer_price_index=str(price_index),
            asset_price_index=str(asset_price_index),
            outstanding_bank_loan_assets=str(debt_total),
            borrower_principal_liabilities=str(debt_total),
            net_new_deposit_money=str(self.credit_amount - total_destroyed),
            principal_repaid=str(total_repaid),
            principal_due=str(due_for_period),
            arrears=str(sum(arrears.values(), ZERO)),
            borrower_cash=str(borrower_cash),
            debt_to_income_proxy=str(debt_income),
            debt_to_assets_proxy=str(debt_assets),
            borrower_net_worth_proxy=str(net_worth_total),
            insolvent_borrower_count=insolvent,
            debt_service_liquidity_coverage=None if liquidity is None else str(liquidity),
            household_essential_cash_coverage=str(household_coverage),
            household_wage_income_gini=str(income_gini),
            physical_balance_error=str(physical_error),
            monetary_conservation_error=str(money_error),
        )

    def run_case(self, scenario):
        if scenario not in SCENARIOS:
            raise CreditExperimentError("unknown credit allocation scenario")
        model = CreditEnabledInputOutputEconomy()
        original_cash = model._system_cash()
        debt, asset_holdings, asset_price_index = self._issue_credit(model, scenario)
        self._initial_debt = dict(debt)
        arrears = {key: ZERO for key in debt}
        destroyed = ZERO
        credit_events = [{
            "event": "credit_origination",
            "scenario": scenario,
            "principal": str(self.credit_amount if debt else ZERO),
            "borrowers": [list(key) for key in sorted(debt)],
        }]
        metrics = []
        for period in range(1, self.periods + 1):
            result = model.step(period)
            period_due = period_repaid = ZERO
            if period > 1:
                for key, outstanding in sorted(debt.items()):
                    if outstanding <= 0:
                        arrears[key] = ZERO
                        continue
                    initial = self._initial_debt[key]
                    instalments = max(1, self.periods - 1)
                    scheduled = (
                        outstanding + arrears[key]
                        if period == self.periods
                        else min(outstanding, (initial / D(instalments)).quantize(CENT, rounding=ROUND_HALF_UP) + arrears[key])
                    )
                    period_due += scheduled
                    available = self._borrower_cash(model, *key)
                    paid = min(available, scheduled, outstanding)
                    if paid > 0:
                        self._set_borrower_cash(model, *key, available - paid)
                        debt[key] = outstanding - paid
                        period_repaid += paid
                    arrears[key] = max(ZERO, scheduled - paid)
            destroyed += period_repaid
            model.initial_cash -= period_repaid
            if model._system_cash() != model.initial_cash:
                raise CreditExperimentError("cash perimeter differs from the post-repayment checkpoint")
            credit_events.append({
                "event": "principal_repayment",
                "period": period,
                "due": str(period_due),
                "paid": str(period_repaid),
                "arrears": str(sum(arrears.values(), ZERO)),
            })
            metrics.append(self._metrics(
                model, scenario, period, result, debt, arrears, asset_holdings,
                asset_price_index, original_cash, period_repaid, period_due, destroyed,
            ))

        event_digest = sha256(json.dumps(
            credit_events, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")).hexdigest()
        final = metrics[-1]
        return {
            "scenario": scenario,
            "credit_principal_issued": str(self.credit_amount if debt else ZERO),
            "credit_principal_outstanding": final.outstanding_bank_loan_assets,
            "deposit_money_created": str(self.credit_amount if debt else ZERO),
            "deposit_money_destroyed": str(destroyed),
            "net_new_deposit_money": final.net_new_deposit_money,
            "asset_market_cash": str(model.asset_market_cash),
            "summary": {
                "cumulative_gross_value_added_proxy": str(sum(
                    (D(item.gross_value_added_proxy) for item in metrics), ZERO
                )),
                "final_consumer_price_index": final.consumer_price_index,
                "final_asset_price_index": final.asset_price_index,
                "final_employment_hours": final.employment_hours,
                "final_labour_productivity_proxy": final.labour_productivity_proxy,
                "final_household_wage_income_gini": final.household_wage_income_gini,
                "final_borrower_net_worth_proxy": final.borrower_net_worth_proxy,
                "final_insolvent_borrower_count": final.insolvent_borrower_count,
                "final_debt_to_income_proxy": final.debt_to_income_proxy,
                "final_debt_to_assets_proxy": final.debt_to_assets_proxy,
                "final_household_essential_cash_coverage": final.household_essential_cash_coverage,
                "max_abs_physical_balance_error": str(max(
                    (D(item.physical_balance_error) for item in metrics), default=ZERO
                )),
                "max_abs_monetary_conservation_error": str(max(
                    (abs(D(item.monetary_conservation_error)) for item in metrics), default=ZERO
                )),
                "credit_event_digest": event_digest,
            },
            "periods": [item.__dict__ for item in metrics],
        }

    def run(self):
        return {
            "experiment": "equal-volume-bank-credit-allocation-v1",
            "credit_amount": str(self.credit_amount),
            "periods": self.periods,
            "assumptions": {
                "productive": "working capital distributed equally across firms",
                "consumption": "new deposits distributed equally across households",
                "asset_purchase": "household deposits immediately exchanged for an external financial asset",
                "principal_repayment": "equal principal schedule from period 2; cash-constrained, unpaid amounts become arrears",
                "excluded": ["interest", "defaults", "collateral", "bank reserves", "capital adequacy", "credit risk pricing"],
                "liquidity_metric": "borrower cash divided by scheduled principal due; not a regulatory liquidity ratio",
                "solvency_metric": "cash plus recorded inventory or modelled asset value less principal debt; narrow prototype proxy",
                "productivity_metric": "fixed-price gross-value-added proxy divided by labour hours",
                "asset_price_rule": "transparent illustrative inverse-depth rule; not an empirical asset valuation model",
            },
            "cases": {scenario: self.run_case(scenario) for scenario in SCENARIOS},
        }


def run_credit_allocation_experiment(*, credit_amount="50000", periods=12):
    return BankCreditAllocationExperiment(
        credit_amount=credit_amount, periods=periods
    ).run()


if __name__ == "__main__":
    print(json.dumps(
        run_credit_allocation_experiment(),
        indent=2,
        sort_keys=True,
    ))
