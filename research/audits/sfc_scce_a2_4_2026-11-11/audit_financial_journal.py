"""Balanced journal fixture with per-holder deposit issuer mirrors.

Synthetic component control only; not a production ledger or legal opinion.
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
    counterparty: str = ""


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


def L(account, side, amount, sector, instrument, counterparty=""):
    return Line(account, side, D(str(amount)), sector, instrument, counterparty)


def event(event_id, kind, *lines):
    return Event(event_id, kind, tuple(lines))


def account_change(event_record, account, instrument, sector=None):
    """Signed stock change: debit increases assets/reduces liabilities."""
    if account.endswith("_asset"):
        debit_sign = 1
    elif account.endswith("_liability"):
        debit_sign = -1
    else:
        raise PostingError("account must explicitly identify asset or liability")
    total = D("0")
    for line in event_record.lines:
        if line.account != account or line.instrument != instrument:
            continue
        if sector is not None and line.sector != sector:
            continue
        total += debit_sign * line.amount if line.side == "D" else -debit_sign * line.amount
    return total


def deposit_holder_issuer_deltas(event_record):
    """Return holder asset and issuer liability changes keyed by deposit holder.

    Deposit-asset lines identify the holder by sector. Bank liability lines
    identify the same holder explicitly in counterparty. Aggregate zero is
    insufficient: every holder's asset must mirror that holder's liability.
    """
    assets, liabilities = {}, {}
    for line in event_record.lines:
        if line.instrument != "deposit":
            continue
        if line.account == "deposit_asset":
            delta = line.amount if line.side == "D" else -line.amount
            assets[line.sector] = assets.get(line.sector, D("0")) + delta
        elif line.account == "deposit_liability":
            if line.sector != "BANK" or not line.counterparty:
                raise PostingError("deposit liability must identify bank and holder")
            delta = line.amount if line.side == "C" else -line.amount
            holder = line.counterparty
            liabilities[holder] = liabilities.get(holder, D("0")) + delta
        else:
            raise PostingError(f"untyped deposit line: {line.account}")
    assets = {k: v for k, v in assets.items() if v}
    liabilities = {k: v for k, v in liabilities.items() if v}
    if assets != liabilities:
        raise PostingError(
            f"deposit holder/issuer mismatch in {event_record.event_id}: "
            f"assets={assets}, liabilities={liabilities}")
    return assets


def main():
    j = Journal()
    j.post(event("E1", "bank_loan_origination",
        L("loan_asset", "D", 19, "BANK", "loan"),
        L("deposit_liability", "C", 19, "BANK", "deposit", "BORROWER"),
        L("deposit_asset", "D", 19, "BORROWER", "deposit"),
        L("loan_liability", "C", 19, "BORROWER", "loan")))

    # Existing deposits move from LENDER to BORROWER2; bank liability holders move too.
    j.post(event("E2", "nonbank_loan_transfer",
        L("loan_asset", "D", 19, "LENDER", "loan"),
        L("deposit_asset", "C", 19, "LENDER", "deposit"),
        L("deposit_liability", "D", 19, "BANK", "deposit", "LENDER"),
        L("deposit_asset", "D", 19, "BORROWER2", "deposit"),
        L("deposit_liability", "C", 19, "BANK", "deposit", "BORROWER2"),
        L("loan_liability", "C", 19, "BORROWER2", "loan")))

    # Supplier payment transfers deposit claims and extinguishes payable/receivable.
    j.post(event("E3", "payment",
        L("trade_payable", "D", 7, "PAYER", "payable"),
        L("deposit_asset", "C", 7, "PAYER", "deposit"),
        L("deposit_liability", "D", 7, "BANK", "deposit", "PAYER"),
        L("deposit_asset", "D", 7, "SUPPLIER", "deposit"),
        L("deposit_liability", "C", 7, "BANK", "deposit", "SUPPLIER"),
        L("trade_receivable", "C", 7, "SUPPLIER", "receivable")))

    j.post(event("E4", "principal_repayment",
        L("loan_liability", "D", 5, "BORROWER", "loan"),
        L("deposit_asset", "C", 5, "BORROWER", "deposit"),
        L("deposit_liability", "D", 5, "BANK", "deposit", "BORROWER"),
        L("loan_asset", "C", 5, "BANK", "loan")))

    j.post(event("E5", "interest_accrual",
        L("interest_expense", "D", 2, "BORROWER", "income"),
        L("interest_payable", "C", 2, "BORROWER", "payable"),
        L("interest_receivable", "D", 2, "BANK", "receivable"),
        L("interest_income", "C", 2, "BANK", "income")))

    j.post(event("E6", "interest_settlement",
        L("interest_payable", "D", 2, "BORROWER", "payable"),
        L("deposit_asset", "C", 2, "BORROWER", "deposit"),
        L("deposit_liability", "D", 2, "BANK", "deposit", "BORROWER"),
        L("interest_receivable", "C", 2, "BANK", "receivable")))

    j.post(event("E7", "impairment",
        L("impairment_expense", "D", 3, "BANK", "income"),
        L("loss_allowance", "C", 3, "BANK", "loan_allowance")))
    j.post(event("E8", "creditor_writeoff",
        L("loss_allowance", "D", 3, "BANK", "loan_allowance"),
        L("loan_asset", "C", 3, "BANK", "loan")))

    assert len(j.events) == 8
    assert len(j.lines) == 32
    for e in j.events.values():
        d = sum((x.amount for x in e.lines if x.side == "D"), D("0"))
        c = sum((x.amount for x in e.lines if x.side == "C"), D("0"))
        assert d == c
        deposit_holder_issuer_deltas(e)

    try:
        j.post(j.events["E1"])
    except PostingError:
        pass
    else:
        raise AssertionError("duplicate event id accepted")

    e1, e2, e3, e4, e6 = (j.events[x] for x in ("E1", "E2", "E3", "E4", "E6"))
    assert account_change(e1, "deposit_asset", "deposit") == D("19")
    assert account_change(e1, "deposit_liability", "deposit") == D("19")
    assert account_change(e2, "deposit_asset", "deposit") == D("0")
    assert account_change(e2, "deposit_liability", "deposit") == D("0")
    assert account_change(e3, "deposit_asset", "deposit") == D("0")
    assert account_change(e3, "deposit_liability", "deposit") == D("0")
    assert account_change(e4, "deposit_asset", "deposit") == D("-5")
    assert account_change(e4, "deposit_liability", "deposit") == D("-5")
    assert account_change(e6, "deposit_asset", "deposit") == D("-2")
    assert account_change(e6, "deposit_liability", "deposit") == D("-2")
    assert deposit_holder_issuer_deltas(e1) == {"BORROWER": D("19")}
    assert deposit_holder_issuer_deltas(e2) == {
        "LENDER": D("-19"), "BORROWER2": D("19")}
    assert deposit_holder_issuer_deltas(e3) == {
        "PAYER": D("-7"), "SUPPLIER": D("7")}
    assert deposit_holder_issuer_deltas(e4) == {"BORROWER": D("-5")}
    assert deposit_holder_issuer_deltas(e6) == {"BORROWER": D("-2")}

    # Adversarial control: omit BOTH bank liability-holder movements from E2.
    # The journal remains globally balanced and aggregate deposits still change by zero.
    # The per-holder mirror must nevertheless reject the event.
    bad_e2 = Event("BAD-E2", "nonbank_loan_transfer", tuple(
        line for line in j.events["E2"].lines
        if line.account != "deposit_liability"))
    d = sum((x.amount for x in bad_e2.lines if x.side == "D"), D("0"))
    c = sum((x.amount for x in bad_e2.lines if x.side == "C"), D("0"))
    assert d == c, "negative control must remain globally balanced"
    try:
        deposit_holder_issuer_deltas(bad_e2)
    except PostingError:
        pass
    else:
        raise AssertionError("missing per-holder issuer liabilities accepted")

    print("A2.4.4 balanced event journal fixture: PASS")
    print(f"events={len(j.events)}; journal_lines={len(j.lines)}; all events balanced")
    print("per-holder deposit mirrors: origination, non-bank transfer, payment, principal and interest")
    print("negative control: globally balanced E2 without holder liabilities rejected")
    print("creditor write-off does not extinguish contractual borrower liability")


if __name__ == "__main__":
    main()
