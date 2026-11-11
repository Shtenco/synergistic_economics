"""A2.4.4 holder/issuer T/V/O stock-flow reconciliation.

The fixture transcribes the six-sector synthetic SFC example. It is a
component control, not a production instrument ledger. Financial net lending
uses transactions only; holder and issuer sides must mirror every T/V/O
component, not merely the closing balance.
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
    instrument_id: str = ""
    currency: str = "LCU"
    maturity: str = "unspecified"
    denomination: str = "nominal"
    valuation_basis: str = "nominal"
    effective_period: int = 1


@dataclass(frozen=True)
class IssuerLiability:
    instrument: str
    issuer: str
    opening: D
    transactions: D
    revaluation: D
    other_volume: D
    closing: D
    instrument_id: str = ""
    currency: str = "LCU"
    maturity: str = "unspecified"
    denomination: str = "nominal"
    valuation_basis: str = "nominal"
    effective_period: int = 1


def position(instrument, holder, issuer, opening, transactions, closing,
             revaluation=0, other_volume=0, *, instrument_id=None,
             currency="LCU", maturity="unspecified", denomination="nominal",
             valuation_basis="nominal", effective_period=1):
    return Position(instrument, holder, issuer, D(str(opening)),
                    D(str(transactions)), D(str(revaluation)),
                    D(str(other_volume)), D(str(closing)),
                    instrument_id or instrument, currency, maturity,
                    denomination, valuation_basis, effective_period)


def liability(instrument, issuer, opening, transactions, closing,
              revaluation=0, other_volume=0, *, instrument_id=None,
              currency="LCU", maturity="unspecified", denomination="nominal",
              valuation_basis="nominal", effective_period=1):
    return IssuerLiability(instrument, issuer, D(str(opening)),
                           D(str(transactions)), D(str(revaluation)),
                           D(str(other_volume)), D(str(closing)),
                           instrument_id or instrument, currency, maturity,
                           denomination, valuation_basis, effective_period)


def _validate_period(period):
    if type(period) is not int or period < 1:
        raise ReconciliationError("effective_period must be a positive integer")


def validate_stock_flow(positions):
    for p in positions:
        _validate_period(p.effective_period)
        if min(p.opening, p.closing) < 0:
            raise ReconciliationError("negative gross instrument position")
        expected = (p.opening + p.transactions + p.revaluation
                    + p.other_volume)
        if expected != p.closing:
            raise ReconciliationError(
                f"holder stock-flow mismatch {p.instrument}/{p.holder}/{p.issuer}: "
                f"{expected} != {p.closing}")
    return True


def validate_issuer_stock_flow(liabilities):
    for p in liabilities:
        _validate_period(p.effective_period)
        if min(p.opening, p.closing) < 0:
            raise ReconciliationError("negative gross issuer liability")
        expected = (p.opening + p.transactions + p.revaluation
                    + p.other_volume)
        if expected != p.closing:
            raise ReconciliationError(
                f"issuer stock-flow mismatch {p.instrument}/{p.issuer}: "
                f"{expected} != {p.closing}")
    return True


def _components(p):
    return (p.opening, p.transactions, p.revaluation,
            p.other_volume, p.closing)


def _identity(p):
    _validate_period(p.effective_period)
    fields = (p.effective_period, p.instrument_id, p.instrument, p.issuer,
              p.currency, p.maturity, p.denomination, p.valuation_basis)
    if not all(fields):
        raise ReconciliationError("incomplete financial instrument identity")
    return fields


def validate_mirrors(positions, issuer_liabilities):
    """Aggregate holder records and compare every component to issuer records."""
    held = {}
    for p in positions:
        key = _identity(p)
        prior = held.get(key, (D("0"),) * 5)
        held[key] = tuple(a + b for a, b in zip(prior, _components(p)))

    issued = {}
    for p in issuer_liabilities:
        key = _identity(p)
        if key in issued:
            raise ReconciliationError(f"duplicate issuer liability record: {key}")
        issued[key] = _components(p)

    if held != issued:
        keys = set(held) | set(issued)
        diffs = {
            key: {"holder_aggregate": held.get(key),
                  "issuer_record": issued.get(key)}
            for key in keys if held.get(key) != issued.get(key)
        }
        raise ReconciliationError(
            f"holder/issuer T/V/O mirror mismatch: {diffs}")
    return True


def validate_period_continuity(records):
    """Require adjacent observed periods to roll closing stock into opening stock.

    Records are aggregated by full instrument identity (excluding period),
    so multiple holder positions reconcile to the issuer-level instrument.
    A missing period is rejected rather than silently bridged.
    """
    by_instrument = {}
    for p in records:
        _validate_period(p.effective_period)
        base = (p.instrument_id, p.instrument, p.issuer, p.currency,
                p.maturity, p.denomination, p.valuation_basis)
        row = by_instrument.setdefault(p.effective_period, {})
        values = row.get(base, (D("0"), D("0")))
        row[base] = (values[0] + p.opening, values[1] + p.closing)
    instruments = set().union(*(set(rows) for rows in by_instrument.values())) if by_instrument else set()
    for key in instruments:
        periods = sorted(period for period, rows in by_instrument.items() if key in rows)
        for prior, current in zip(periods, periods[1:]):
            if current != prior + 1:
                raise ReconciliationError(
                    f"missing effective period for instrument {key}: {prior} -> {current}")
            prior_closing = by_instrument[prior][key][1]
            current_opening = by_instrument[current][key][0]
            if prior_closing != current_opening:
                raise ReconciliationError(
                    f"closing/opening discontinuity for instrument {key} "
                    f"between periods {prior} and {current}: "
                    f"{prior_closing} != {current_opening}")
    return True


def sector_financial_net_lending(positions, period=None):
    """Financial NL uses transactions, never stocks; multiple periods require selection."""
    positions = list(positions)
    periods = {p.effective_period for p in positions}
    if period is None and len(periods) > 1:
        raise ReconciliationError("multiple effective periods require an explicit period selector")
    if period is not None:
        _validate_period(period)
        positions = [p for p in positions if p.effective_period == period]
        if not positions:
            raise ReconciliationError(f"no instrument positions for effective period {period}")
    assets, liabilities = {}, {}
    for p in positions:
        assets[p.holder] = assets.get(p.holder, D("0")) + p.transactions
        liabilities[p.issuer] = liabilities.get(p.issuer, D("0")) + p.transactions
    sectors = set(assets) | set(liabilities)
    return {s: assets.get(s, D("0")) - liabilities.get(s, D("0"))
            for s in sectors}


def main():
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
    issuer_liabilities = [
        liability("deposit", "CB", 100, 15, 115),
        liability("loan", "H", 30, 0, 30),
        liability("loan", "NFC", 80, 19, 99),
        liability("reserves", "CBank", 30, 0, 30),
        liability("cash", "CBank", 20, 0, 20),
        liability("government_bond", "GOV", 50, 15, 65),
        liability("external_reserve_asset", "ROW", 10, 0, 10),
    ]

    validate_stock_flow(positions)
    validate_issuer_stock_flow(issuer_liabilities)
    validate_mirrors(positions, issuer_liabilities)

    nl = sector_financial_net_lending(positions)
    expected_nl = {
        "H": D("7"), "NFC": D("-19"), "CB": D("4"),
        "CBank": D("0"), "GOV": D("-15"), "ROW": D("23"),
    }
    assert nl == expected_nl, (nl, expected_nl)
    assert sum(nl.values(), D("0")) == 0

    broken_holder = list(positions)
    broken_holder[0] = Position(
        "deposit", "H", "CB", D("100"), D("7"), D("0"), D("0"), D("108"))
    try:
        validate_stock_flow(broken_holder)
    except ReconciliationError:
        pass
    else:
        raise AssertionError("broken holder roll-forward accepted")

    # Same closing balance, wrong T/V classification on issuer side.
    bad_classification = list(issuer_liabilities)
    bad_classification[0] = liability(
        "deposit", "CB", 100, 14, 115, revaluation=1)
    validate_issuer_stock_flow(bad_classification)
    try:
        validate_mirrors(positions, bad_classification)
    except ReconciliationError:
        pass
    else:
        raise AssertionError("equal closing stock with mismatched T/V accepted")

    # A missing issuer record must be detected.
    try:
        validate_mirrors(positions, issuer_liabilities[:-1])
    except ReconciliationError:
        pass
    else:
        raise AssertionError("missing issuer liability record accepted")

    # Same nominal amount and issuer but different currency must not be netted
    # into the same instrument mirror. Identity dimensions are part of the key.
    wrong_currency_liability = list(issuer_liabilities)
    wrong_currency_liability[0] = liability(
        "deposit", "CB", 100, 15, 115, currency="USD")
    validate_issuer_stock_flow(wrong_currency_liability)
    try:
        validate_mirrors(positions, wrong_currency_liability)
    except ReconciliationError:
        pass
    else:
        raise AssertionError("same amount in wrong currency accepted as mirror")

    # A different instrument ID must not be silently netted into the same
    # holder/issuer mirror, even when class, issuer, currency and amounts match.
    wrong_id_liability = list(issuer_liabilities)
    wrong_id_liability[0] = liability(
        "deposit", "CB", 100, 15, 115, instrument_id="deposit:series-B")
    validate_issuer_stock_flow(wrong_id_liability)
    try:
        validate_mirrors(positions, wrong_id_liability)
    except ReconciliationError:
        pass
    else:
        raise AssertionError("different instrument ID accepted as mirror")

    # Duplicate issuer records are invalid, not an additive second liability.
    try:
        validate_mirrors(
            positions, issuer_liabilities + [issuer_liabilities[0]])
    except ReconciliationError:
        pass
    else:
        raise AssertionError("duplicate issuer liability record accepted")

    # Distinct same-class instruments remain distinct even with identical
    # nominal amounts and otherwise identical identity dimensions.
    series_positions = [
        position("government_bond", "H", "GOV", 0, 5, 5,
                 instrument_id="bond-series-A"),
        position("government_bond", "ROW", "GOV", 0, 5, 5,
                 instrument_id="bond-series-B"),
    ]
    series_liabilities = [
        liability("government_bond", "GOV", 0, 5, 5,
                  instrument_id="bond-series-A"),
        liability("government_bond", "GOV", 0, 5, 5,
                  instrument_id="bond-series-B"),
    ]
    validate_mirrors(series_positions, series_liabilities)
    try:
        validate_mirrors(series_positions, series_liabilities[:1])
    except ReconciliationError:
        pass
    else:
        raise AssertionError("missing distinct instrument series accepted")

    # An explicitly blank instrument ID is not a valid identity.
    incomplete = IssuerLiability(
        "deposit", "CB", D("100"), D("15"), D("0"), D("0"), D("115"),
        instrument_id="")
    try:
        validate_mirrors([], [incomplete])
    except ReconciliationError:
        pass
    else:
        raise AssertionError("blank instrument ID accepted")

    # Valuation-only change alters stocks, not financial net lending.
    valuation_only = [
        position("fx_deposit", "H", "CB", 100, 0, 113,
                 revaluation=10, other_volume=3)
    ]
    valuation_liability = [
        liability("fx_deposit", "CB", 100, 0, 113,
                  revaluation=10, other_volume=3)
    ]
    validate_stock_flow(valuation_only)
    validate_issuer_stock_flow(valuation_liability)
    validate_mirrors(valuation_only, valuation_liability)
    assert sector_financial_net_lending(valuation_only) == {
        "H": D("0"), "CB": D("0")}

    mixed = [
        position("fx_deposit", "H", "CB", 100, 7, 120,
                 revaluation=10, other_volume=3)
    ]
    mixed_liability = [
        liability("fx_deposit", "CB", 100, 7, 120,
                  revaluation=10, other_volume=3)
    ]
    validate_stock_flow(mixed)
    validate_issuer_stock_flow(mixed_liability)
    validate_mirrors(mixed, mixed_liability)
    assert sector_financial_net_lending(mixed) == {
        "H": D("7"), "CB": D("-7")}

    print("A2.4.4 holder/issuer T/V/O stock-flow reconciliation: PASS")
    print("10 holder positions and 7 independent issuer-liability records")
    print("opening, T, V, O and closing mirror component-by-component")
    print("sector financial NL: H=7 NFC=-19 CB=4 CBank=0 GOV=-15 ROW=23; sum=0")
    print("identity key includes instrument ID, currency, maturity, denomination and valuation basis")
    print("negative controls: wrong instrument ID, duplicate issuer record, blank ID and conflated series rejected")
    print("negative controls: broken roll-forward, missing issuer, T/V mismatch and wrong-currency mirror rejected")
    print("valuation-only V=10/O=3 yields zero financial NL; mixed T=7/V=10/O=3 yields +7/-7")


if __name__ == "__main__":
    main()
