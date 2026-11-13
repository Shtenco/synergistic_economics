#!/usr/bin/env python3
"""Independent Decimal audit of the six-sector synthetic SFC closure.

Frozen inputs are transcribed from:
research/FULL_SIX_SECTOR_SFC_NUMERICAL_CLOSURE.md (10 Nov 2026).

This script checks arithmetic and mirror positions only. It does not calibrate
or validate behavioural equations, institutional realism, or empirical data.
Standard library only.
"""
from decimal import Decimal as D

SECTORS = ("H", "NFC", "CB", "CBank", "GOV", "ROW")


def eq(name, lhs, rhs):
    lhs, rhs = D(str(lhs)), D(str(rhs))
    delta = lhs - rhs
    assert delta == 0, f"{name}: {lhs} != {rhs}; residual={delta}"
    print(f"PASS {name}: {lhs} = {rhs}")


def main():
    # Product balance and three GDP approaches.
    eq("product supply/use", 149 + 30, 30 + 55 + 19 + 68 + 7)
    gdp_prod = D(149) - D(30)
    gdp_income = D(60) + D(4) + D(55)
    gdp_expenditure = D(55) + D(19) + D(68) + D(7) - D(30)
    eq("GDP production/income", gdp_prod, gdp_income)
    eq("GDP production/expenditure", gdp_prod, gdp_expenditure)

    # Sectoral capital-account net lending.
    saving = {
        "H": D(7), "NFC": D(49), "CB": D(4),
        "CBank": D(0), "GOV": D(-15), "ROW": D(23),
    }
    gcf = {"H": D(0), "NFC": D(68), "CB": D(0),
           "CBank": D(0), "GOV": D(0), "ROW": D(0)}
    capital_nl = {s: saving[s] - gcf[s] for s in SECTORS}
    expected_nl = {
        "H": D(7), "NFC": D(-19), "CB": D(4),
        "CBank": D(0), "GOV": D(-15), "ROW": D(23),
    }
    for s in SECTORS:
        eq(f"capital net lending {s}", capital_nl[s], expected_nl[s])
    eq("sum sectoral net lending", sum(capital_nl.values()), 0)

    # Financial-account transaction deltas, separated by instruments.
    net_acquisition_fa = {
        "H": D(7), "NFC": D(0), "CB": D(19),
        "CBank": D(0), "GOV": D(0), "ROW": D(23),
    }
    net_incurrence_fl = {
        "H": D(0), "NFC": D(19), "CB": D(15),
        "CBank": D(0), "GOV": D(15), "ROW": D(0),
    }
    financial_nl = {
        s: net_acquisition_fa[s] - net_incurrence_fl[s] for s in SECTORS
    }
    for s in SECTORS:
        eq(f"capital-financial bridge {s}", capital_nl[s], financial_nl[s])
    eq("financial account total assets", sum(net_acquisition_fa.values()), 49)
    eq("financial account total liabilities", sum(net_incurrence_fl.values()), 49)

    # Instrument-by-instrument mirror positions, opening and closing.
    mirrors = {
        "H+ROW deposits / CB deposit liabilities": (107 + 8, 115),
        "CB loan assets / H+NFC loan liabilities": (30 + 99, 129),
        "CB reserve assets / CBank reserve liabilities": (30, 30),
        "H+CBank+ROW bonds / GOV bond liabilities": (10 + 40 + 15, 65),
        "CBank external reserve asset / ROW liability": (10, 10),
    }
    for name, (lhs, rhs) in mirrors.items():
        eq(f"mirror {name}", lhs, rhs)

    # Balance-sheet identities and net-worth bridge.
    opening_nw = {"H": 100, "NFC": 120, "CB": 40,
                  "CBank": 0, "GOV": 50, "ROW": -10}
    closing_nw = {"H": 107, "NFC": 169, "CB": 44,
                  "CBank": 0, "GOV": 35, "ROW": 13}
    for s in SECTORS:
        eq(f"net worth change {s}",
           closing_nw[s] - opening_nw[s], capital_nl[s] + gcf[s])
    eq("global net worth change", sum(closing_nw.values()) -
       sum(opening_nw.values()), 68)
    eq("NFC produced capital increase", 268 - 200, 68)

    # Bank deposit creation vs non-bank transfer: two distinct event types.
    # Bank loan origination creates both a loan asset and a deposit liability.
    bank_loan = {"bank_loan_asset": D(19), "deposit_liability": D(19)}
    eq("bank loan creation asset/liability", bank_loan["bank_loan_asset"],
       bank_loan["deposit_liability"])
    # A non-bank lender transfers an existing deposit; system-wide deposits do not grow.
    nonbank_transfer = {
        "lender_deposit_change": D(-19),
        "borrower_deposit_change": D(19),
        "loan_asset_change": D(19),
        "borrower_loan_liability_change": D(19),
    }
    eq("non-bank transfer net deposits",
       nonbank_transfer["lender_deposit_change"] +
       nonbank_transfer["borrower_deposit_change"], 0)
    eq("non-bank transfer mirrored loan",
       nonbank_transfer["loan_asset_change"],
       nonbank_transfer["borrower_loan_liability_change"])

    # Bank interest margin in the six-sector example:
    # NFC interest payment extinguishes its deposit; household interest adds deposit.
    eq("bank interest margin", 6 - 2, 4)
    eq("deposit change after loan and net interest", 19 - 6 + 2, 15)
    eq("bank equity retained earnings", 6 - 2, 4)

    # B2 multicommodity physical controls. Keep unlike units separate.
    eq("steel balance tonnes", 5 + 10 + 2, 8 + 3 + 1 + 1 + 4)
    eq("grain balance tonnes", 20 + 30 + 5, 5 + 35 + 5 + 5 + 5)
    eq("electricity balance MWh", 100 + 10, 60 + 40 + 5 + 5)
    eq("scrap balance tonnes", 12, 12)
    eq("equipment balance units", 2, 2)
    eq("fuel balance GJ", 1000 + 500, 500 + 1000)
    eq("scrap conversion mass tonnes", 12, 10 + 2)
    eq("equipment assembly steel tonnes", 4, 2 * 2)
    eq("power conversion energy GJ", 500, 100 * D("3.6") + 140)

    print("ALL INDEPENDENT SFC/B2 ARITHMETIC CHECKS PASSED")
    print("LIMIT: no price/unit bridge currently maps B2 natural units into SFC D.E.")


if __name__ == "__main__":
    main()
