"""A2.4.5 time, consent, delivery and compensation control fixture."""
from dataclasses import dataclass
from decimal import Decimal as D


class LabourContractError(ValueError):
    pass


@dataclass(frozen=True)
class Interval:
    activity: str
    start: D
    end: D
    classification: str

    @property
    def hours(self):
        return self.end - self.start


def validate_time_budget(intervals, period_hours=D("168")):
    ordered = sorted(intervals, key=lambda x: (x.start, x.end))
    for item in ordered:
        if item.start < 0 or item.end <= item.start or item.end > period_hours:
            raise LabourContractError("invalid interval boundary")
    for left, right in zip(ordered, ordered[1:]):
        if right.start < left.end:
            raise LabourContractError("overlapping intervals double-count time")
    total = sum((x.hours for x in ordered), D("0"))
    if total > period_hours:
        raise LabourContractError("time budget exceeded")
    return total


def delivered_hours(offered, accepted, scheduled, delivered, consent_state,
                    safety_limit):
    vals = [D(str(x)) for x in (offered, accepted, scheduled, delivered, safety_limit)]
    offered, accepted, scheduled, delivered, safety_limit = vals
    if consent_state not in ("accepted", "started", "delivered", "verified"):
        if delivered != 0:
            raise LabourContractError("delivery cannot be inferred without active consent")
    if min(vals) < 0 or accepted > offered or scheduled > accepted:
        raise LabourContractError("invalid offer/acceptance/schedule quantities")
    if delivered > scheduled or delivered > safety_limit:
        raise LabourContractError("delivered hours exceed schedule or safety limit")
    return delivered


def capability_transition(opening, learning, obsolescence, verified_update):
    values = [D(str(x)) for x in (opening, learning, obsolescence, verified_update)]
    if min(values) < 0:
        raise LabourContractError("capability components must be non-negative")
    return values[0] + values[1] - values[2] + values[3]


def wage_journal(hours, rate, settled):
    hours, rate, settled = D(str(hours)), D(str(rate)), D(str(settled))
    if min(hours, rate, settled) < 0:
        raise LabourContractError("negative wage input")
    accrued = hours * rate
    if settled > accrued:
        raise LabourContractError("settlement exceeds accrued payable")
    # Accrual: expense debit / payable credit. Settlement: payable debit / cash credit.
    return {"wage_expense": accrued, "wage_payable_close": accrued - settled,
            "cash_settlement": settled}


def main():
    # Mutually exclusive weekly intervals; all other time is unallocated.
    intervals = [
        Interval("sleep_rest", D("0"), D("56"), "rest"),
        Interval("paid_work", D("56"), D("96"), "paid"),
        Interval("personal", D("96"), D("112"), "personal"),
        Interval("unpaid_care", D("112"), D("126"), "unpaid_care"),
        Interval("training", D("126"), D("134"), "training"),
        Interval("leisure", D("134"), D("154"), "leisure"),
    ]
    allocated = validate_time_budget(intervals)
    assert allocated == D("154")

    hours = delivered_hours(40, 36, 32, 30, "delivered", 32)
    assert hours == D("30")
    assert capability_transition(5, 1, 0.5, 0.25) == D("5.75")
    wages = wage_journal(hours, 20, 400)
    assert wages == {"wage_expense": D("600"), "wage_payable_close": D("200"),
                     "cash_settlement": D("400")}

    # Adversarial cases: overlap, no consent, over-delivery and double-counted wage.
    try:
        validate_time_budget([Interval("A", D("1"), D("5"), "paid"),
                              Interval("B", D("4"), D("6"), "care")])
    except LabourContractError:
        pass
    else:
        raise AssertionError("overlapping intervals accepted")
    try:
        delivered_hours(8, 8, 8, 1, "offered", 8)
    except LabourContractError:
        pass
    else:
        raise AssertionError("service delivered without consent")
    try:
        delivered_hours(8, 8, 8, 9, "accepted", 8)
    except LabourContractError:
        pass
    else:
        raise AssertionError("delivery beyond scheduled hours accepted")
    try:
        wage_journal(2, 10, 21)
    except LabourContractError:
        pass
    else:
        raise AssertionError("settlement above accrued wage accepted")

    print("A2.4.5 time/consent/labour fixture: PASS")
    print(f"allocated_hours={allocated}; delivered_paid_hours={hours}")
    print(f"wage_accrual={wages['wage_expense']}; settlement={wages['cash_settlement']}; "
          f"closing_payable={wages['wage_payable_close']}")
    print("overlap, absent consent, over-delivery and over-settlement rejected")


if __name__ == "__main__":
    main()
