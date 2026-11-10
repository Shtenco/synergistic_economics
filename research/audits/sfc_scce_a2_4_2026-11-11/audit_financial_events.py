"""Minimal Decimal controls for A2.4.4 financial event distinctions.

The checks validate the synthetic event arithmetic only; they do not implement
a general ledger or a legal/accounting standard.
"""
from decimal import Decimal as D


def main():
    bank_loan = D("19")
    bank = {"loan_asset": bank_loan, "deposit_liability": bank_loan}
    borrower = {"deposit_asset": bank_loan, "loan_liability": bank_loan}
    assert bank["loan_asset"] == borrower["loan_liability"]
    assert bank["deposit_liability"] == borrower["deposit_asset"]
    assert bank["deposit_liability"] == D("19")

    transfer = D("19")
    lender = {"deposit_asset": -transfer, "loan_asset": transfer}
    borrower_transfer = {"deposit_asset": transfer, "loan_liability": transfer}
    system_deposit_change = lender["deposit_asset"] + borrower_transfer["deposit_asset"]
    assert system_deposit_change == 0
    assert lender["loan_asset"] == borrower_transfer["loan_liability"]

    # Payment transfers a deposit; it is not a second creation event.
    payment = D("7")
    payer_deposit_change, payee_deposit_change = -payment, payment
    assert payer_deposit_change + payee_deposit_change == 0

    # Principal repayment extinguishes matching bank loan/deposit positions.
    principal = D("5")
    borrower_deposit, borrower_loan_liability = -principal, -principal
    bank_loan_asset, bank_deposit_liability = -principal, -principal
    assert borrower_deposit == borrower_loan_liability
    assert bank_loan_asset == bank_deposit_liability

    # Six-sector interest/deposit control.
    delta_deposits = D("19") - D("6") + D("2")
    bank_equity_change = D("6") - D("2")
    assert delta_deposits == D("15")
    assert bank_equity_change == D("4")

    # Gross/net net-lending identity with consistent CFC treatment.
    gross_nl = D("49") - D("68")
    net_nl = (D("49") - D("8")) - (D("68") - D("8"))
    assert gross_nl == net_nl == D("-19")

    print("A2.4.4 financial event controls: PASS")
    print("bank-created deposits: +19; non-bank transfer: 0 system deposits")
    print("payment: deposit transfer only; principal repayment: matched reduction")
    print("six-sector deposits change: +15; bank equity change: +4")


if __name__ == "__main__":
    main()
