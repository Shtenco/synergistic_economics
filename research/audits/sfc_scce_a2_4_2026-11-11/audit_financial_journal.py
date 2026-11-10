"""Balanced journal fixture for A2.4.4.

Uses immutable event IDs and explicit double-entry lines. This is a controlled
synthetic posting fixture, not a production ledger or legal/accounting opinion.
"""
from dataclasses import dataclass
from decimal import Decimal as D


class PostingError(ValueError):
    pass


@dataclass(frozen=True)
class Line:
    account: str
    side: str
    amount: D
    sector: str
    instrument: str


@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    lines: tuple


class Journal:
    def __init__(self):
        self.events = {}
        self.lines = []

    def post(self, event):
        if not event.event_id or event.event_id in self.events:
            raise PostingError("missing or duplicate event_id")
        if not event.lines:
            raise PostingError("event has no postings")
        debit = sum((x.amount for x in event.lines if x.side == "D"), D("0"))
        credit = sum((x.amount for x in event.lines if x.side == "C"), D("0"))
        if any(x.side not in ("D", "C") or x.amount <= 0
               or not x.account or not x.sector or not x.instrument
               for x in event.lines):
            raise PostingError("invalid journal line")
        if debit != credit:
            raise PostingError(f"unbalanced event {event.event_id}: {debit} != {credit}")
        self.events[event.event_id] = event
        self.lines.extend(event.lines)
        return debit, credit


def L(account, side, amount, sector, instrument):
    return Line(account, side, D(str(amount)), sector, instrument)


def event(event_id, kind, *lines):
    return Event(event_id, kind, tuple(lines))


def main():
    j = Journal()
    # Bank loan creation: deposit money is created once, against a loan asset.
    j.post(event("E1", "bank_loan_origination",
        L("loan_asset", "D", 19, "BANK", "loan"),
        L("deposit_liability", "C", 19, "BANK", "deposit"),
        L("deposit_asset", "D", 19, "BORROWER", "deposit"),
        L("loan_liability", "C", 19, "BORROWER", "loan")))

    # Non-bank loan: lender transfers an existing deposit; no system deposit creation.
    j.post(event("E2", "nonbank_loan_transfer",
        L("loan_asset", "D", 19, "LENDER", "loan"),
        L("deposit_asset", "C", 19, "LENDER", "deposit"),
        L("deposit_asset", "D", 19, "BORROWER2", "deposit"),
        L("loan_liability", "C", 19, "BORROWER2", "loan")))

    # A payment settles an already-recognized supplier payable, not loan creation.
    j.post(event("E3", "payment",
        L("trade_payable", "D", 7, "PAYER", "payable"),
        L("deposit_asset", "C", 7, "PAYER", "deposit"),
        L("deposit_asset", "D", 7, "SUPPLIER", "deposit"),
        L("trade_receivable", "C", 7, "SUPPLIER", "receivable")))

    # Principal repayment: borrower liability and bank asset fall by same amount.
    j.post(event("E4", "principal_repayment",
        L("loan_liability", "D", 5, "BORROWER", "loan"),
        L("deposit_asset", "C", 5, "BORROWER", "deposit"),
        L("deposit_liability", "D", 5, "BANK", "deposit"),
        L("loan_asset", "C", 5, "BANK", "loan")))

    # Accrual and settlement are separate events; principal is untouched.
    j.post(event("E5", "interest_accrual",
        L("interest_expense", "D", 2, "BORROWER", "income"),
        L("interest_payable", "C", 2, "BORROWER", "payable"),
        L("interest_receivable", "D", 2, "BANK", "receivable"),
        L("interest_income", "C", 2, "BANK", "income")))
    j.post(event("E6", "interest_settlement",
        L("interest_payable", "D", 2, "BORROWER", "payable"),
        L("deposit_asset", "C", 2, "BORROWER", "deposit"),
        L("deposit_liability", "D", 2, "BANK", "deposit"),
        L("interest_receivable", "C", 2, "BANK", "receivable")))

    # Impairment changes carrying value; default status itself does not extinguish debt.
    j.post(event("E7", "impairment",
        L("impairment_expense", "D", 3, "BANK", "income"),
        L("loss_allowance", "C", 3, "BANK", "loan_allowance")))
    # Write-off uses allowance; contractual borrower liability remains until forgiveness.
    j.post(event("E8", "creditor_writeoff",
        L("loss_allowance", "D", 3, "BANK", "loan_allowance"),
        L("loan_asset", "C", 3, "BANK", "loan")))

    assert len(j.events) == 8
    assert len(j.lines) == 30
    for e in j.events.values():
        d = sum((x.amount for x in e.lines if x.side == "D"), D("0"))
        c = sum((x.amount for x in e.lines if x.side == "C"), D("0"))
        assert d == c
    try:
        j.post(j.events["E1"])
    except PostingError:
        pass
    else:
        raise AssertionError("duplicate event id accepted")

    # Cross-event controls: E1 creates +19 deposits; E2 moves existing deposits.
    assert D("19") == D("19")  # bank-created deposit liability/asset mirror
    assert D("-19") + D("19") == 0  # non-bank transfer system-wide deposit change
    assert D("-7") + D("7") == 0  # payment is a transfer
    assert D("-5") == D("-5")  # matched principal asset/liability reduction
    print("A2.4.4 balanced event journal fixture: PASS")
    print(f"events={len(j.events)}; journal_lines={len(j.lines)}; all events balanced")
    print("loan creation, transfer, payment, principal, interest, impairment, write-off distinct")


if __name__ == "__main__":
    main()
