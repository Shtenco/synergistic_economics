"""A2.4.4 instrument-holder/issuer stock-flow reconciliation.

The fixture transcribes the opening/closing positions and sectoral financial
net lending from FULL_SIX_SECTOR_SFC_NUMERICAL_CLOSURE.md. It remains a
synthetic example, not a general production ledger.
"""
from dataclasses import dataclass
from decimal import Decimal as D


class ReconciliationError(ValueError):
    pass


@dataclass(frozen=True)
class Position:
    instrument: str
    holder: str
    issuer: str
    opening: D
    transactions: D
    revaluation: D
    other_volume: D
    closing: D


def position(instrument, holder, issuer, opening, transactions, closing,
             revaluation=0, other_volume=0):
    return Position(instrument, holder, issuer, D(str(opening)),
                    D(str(transactions)), D(str(revaluation)),
                    D(str(other_volume)), D(str(closing)))


def validate_stock_flow(positions):
    for p in positions:
        if min(p.opening, p.closing) < 0:
            raise ReconciliationError("negative gross instrument position")
        expected = (p.opening + p.transactions + p.revaluation
                    + p.other_volume)
        if expected != p.closing:
            raise ReconciliationError(
                f"stock-flow mismatch {p.instrument}/{p.holder}/{p.issuer}: "
                f"{expected} != {p.closing}")
    return True


def validate_mirrors(positions, issuer_liabilities):
    held = {}
    for p in positions:
        key = (p.instrument, p.issuer)
        held[key] = held.get(key, D("0")) + p.closing
    if held != issuer_liabilities:
        keys = set(held) | set(issuer_liabilities)
        diffs = {key: (held.get(key, D("0")),
                       issuer_liabilities.get(key, D("0")))
                 for key in keys
                 if held.get(key, D("0")) != issuer_liabilities.get(key, D("0"))}
        raise ReconciliationError(f"holder/issuer mirror mismatch: {diffs}")
    return True


def sector_financial_net_lending(positions):
    assets = {}
    liabilities = {}
    for p in positions:
        delta = p.closing - p.opening
        assets[p.holder] = assets.get(p.holder, D("0")) + delta
        liabilities[p.issuer] = liabilities.get(p.issuer, D("0")) + delta
    sectors = set(assets) | set(liabilities)
    return {s: assets.get(s, D("0")) - liabilities.get(s, D("0"))
            for s in sectors}


def main():
    # Opening/closing positions from the repository's six-sector SFC example.
    positions = [
        position("deposit", "H", "CB", 100, 7, 107),
        position("deposit", "ROW", "CB", 0, 8, 8),
        position("loan", "CB", "H", 30, 0, 30),
        position("loan", "CB", "NFC", 80, 19, 99),
        position("reserves", "CB", "CBank", 30, 0, 30),
        position("cash", "H", "CBank", 20, 0, 20),
        position("government_bond", "H", "GOV", 10, 0, 10),
        position("government_bond", "CBank", "GOV", 40, 0, 40),
        position("government_bond", "ROW", "GOV", 0, 15, 15),
        position("external_reserve_asset", "CBank", "ROW", 10, 0, 10),
    ]
    issuer_liabilities = {
        ("deposit", "CB"): D("115"),
        ("loan", "H"): D("30"),
        ("loan", "NFC"): D("99"),
        ("reserves", "CBank"): D("30"),
        ("cash", "CBank"): D("20"),
        ("government_bond", "GOV"): D("65"),
        ("external_reserve_asset", "ROW"): D("10"),
    }
    validate_stock_flow(positions)
    validate_mirrors(positions, issuer_liabilities)

    nl = sector_financial_net_lending(positions)
    expected_nl = {
        "H": D("7"), "NFC": D("-19"), "CB": D("4"),
        "CBank": D("0"), "GOV": D("-15"), "ROW": D("23"),
    }
    assert nl == expected_nl, (nl, expected_nl)
    assert sum(nl.values(), D("0")) == 0

    # A failed instrument roll-forward must not be hidden by a sectoral plug.
    broken = list(positions)
    broken[0] = Position(
        "deposit", "H", "CB", D("100"), D("7"), D("0"), D("0"), D("108"))
    try:
        validate_stock_flow(broken)
    except ReconciliationError:
        pass
    else:
        raise AssertionError("broken stock-flow position accepted")

    # A missing issuer liability must be visible even if total assets are unchanged.
    bad_liabilities = dict(issuer_liabilities)
    bad_liabilities[("deposit", "CB")] = D("114")
    try:
        validate_mirrors(positions, bad_liabilities)
    except ReconciliationError:
        pass
    else:
        raise AssertionError("unmatched issuer liability accepted")

    print("A2.4.4 instrument stock-flow reconciliation: PASS")
    print("10 holder/issuer positions; all stock-flow identities and mirrors close")
    print("sector financial net lending: H=7 NFC=-19 CB=4 CBank=0 GOV=-15 ROW=23")
    print("sum of sector financial net lending=0")
    print("broken position roll-forward and unmatched liability rejected")


if __name__ == "__main__":
    main()
