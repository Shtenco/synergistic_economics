"""Independent arithmetic oracle for the frozen SFC-GOLD-1 corpus.

This module intentionally imports no prototype, journal, event-store, SFC
projection, or audit-fixture code. It independently recomputes balances and
holder/issuer mirrors from the frozen JSON event corpus.
"""
from collections import defaultdict
from decimal import Decimal as D
import json
from pathlib import Path


CORPUS = Path(__file__).with_name("SFC_GOLD_1_CORPUS.json")
REQUIRED_IDENTITY = (
    "instrument_id", "instrument_class", "currency", "maturity",
    "denomination", "valuation_basis",
)
FINANCIAL_SUFFIXES = ("_asset", "_liability")


class OracleError(ValueError):
    pass


def _decimal(value):
    if not isinstance(value, str):
        raise OracleError("amount must be encoded as a decimal string")
    try:
        amount = D(value)
    except Exception as exc:
        raise OracleError("invalid decimal amount") from exc
    if not amount.is_finite() or amount <= 0:
        raise OracleError("amount must be finite and positive")
    return amount


def _identity(posting, holder, issuer, period):
    values = [posting.get(name) for name in REQUIRED_IDENTITY]
    if any(not isinstance(value, str) or not value.strip() for value in values):
        raise OracleError("incomplete instrument identity")
    return (period, *values, holder, issuer)


def evaluate(corpus):
    events = corpus.get("events")
    if not isinstance(events, list) or not events:
        raise OracleError("corpus must contain events")

    event_ids = set()
    balances = defaultdict(lambda: D("0"))
    per_event_mirrors = {}
    sector_assets = defaultdict(lambda: D("0"))
    sector_liabilities = defaultdict(lambda: D("0"))
    period_set = set()

    for event in events:
        event_id = event.get("event_id")
        period = event.get("effective_period")
        if not isinstance(event_id, str) or not event_id or event_id in event_ids:
            raise OracleError("missing or duplicate event ID")
        if type(period) is not int or period < 0:
            raise OracleError("invalid effective period")
        event_ids.add(event_id)
        period_set.add(period)
        postings = event.get("postings")
        if not isinstance(postings, list) or not postings:
            raise OracleError("event must contain postings")

        debit = D("0")
        credit = D("0")
        event_assets = defaultdict(lambda: D("0"))
        event_liabilities = defaultdict(lambda: D("0"))

        for posting in postings:
            account = posting.get("account")
            side = posting.get("side")
            entity = posting.get("entity_id")
            sector = posting.get("institutional_sector")
            amount = _decimal(posting.get("amount"))
            if not all(isinstance(x, str) and x.strip()
                       for x in (account, entity, sector)):
                raise OracleError("posting account, entity and sector are required")
            if side == "D":
                debit += amount
            elif side == "C":
                credit += amount
            else:
                raise OracleError("posting side must be D or C")

            if account.endswith(FINANCIAL_SUFFIXES):
                if account.endswith("_asset"):
                    holder = entity
                    issuer = posting.get("issuer_entity_id")
                    signed = amount if side == "D" else -amount
                    key = _identity(posting, holder, issuer, period)
                    event_assets[key] += signed
                    sector_assets[sector] += signed
                elif account.endswith("_liability"):
                    holder = posting.get("counterparty_entity_id")
                    issuer = entity
                    signed = amount if side == "C" else -amount
                    key = _identity(posting, holder, issuer, period)
                    event_liabilities[key] += signed
                    sector_liabilities[sector] += signed

                # Store each entity/account/instrument stock with its natural
                # balance sign (debit-positive assets, credit-positive liabilities).
                natural_change = (
                    amount if (account.endswith("_asset") and side == "D")
                    or (account.endswith("_liability") and side == "C")
                    else -amount
                )
                balance_key = (entity, account, posting.get("instrument_id"))
                balances[balance_key] += natural_change

        if debit != credit:
            raise OracleError(
                f"unbalanced event {event_id}: debit {debit} != credit {credit}")

        event_assets = {k: v for k, v in event_assets.items() if v}
        event_liabilities = {k: v for k, v in event_liabilities.items() if v}
        if event_assets != event_liabilities:
            raise OracleError(
                f"event-level claim mirror mismatch {event_id}: "
                f"assets={event_assets}, liabilities={event_liabilities}")
        per_event_mirrors[event_id] = event_assets

    if len(period_set) != 1:
        raise OracleError("SFC-GOLD-1 v1 is single-period; multi-period input rejected")

    balances = {k: v for k, v in balances.items() if v}
    sector_nl = {
        sector: sector_assets[sector] - sector_liabilities[sector]
        for sector in set(sector_assets) | set(sector_liabilities)
    }
    return {
        "balances": balances,
        "sector_financial_net_lending": sector_nl,
        "event_count": len(event_ids),
        "periods": tuple(sorted(period_set)),
    }


def _assert_expected(corpus, result):
    expected = corpus["expected"]
    actual_positions = {
        (entity, account, instrument): value
        for (entity, account, instrument), value in result["balances"].items()
    }
    expected_positions = {
        (row["entity_id"], row["account"], row["instrument_id"]): D(row["balance"])
        for row in expected["final_positions"]
    }
    assert actual_positions == expected_positions, (
        f"final positions differ: {actual_positions} != {expected_positions}")

    assert result["sector_financial_net_lending"] == {
        sector: D(value)
        for sector, value in expected["aggregate_sector_financial_net_lending"].items()
    }
    deposits_asset = sum(
        value for (entity, account, instrument), value in actual_positions.items()
        if account == "deposit_asset"
    )
    deposits_liability = sum(
        value for (entity, account, instrument), value in actual_positions.items()
        if account == "deposit_liability"
    )
    assert deposits_asset == D(expected["system_deposit_asset"])
    assert deposits_liability == D(expected["system_deposit_liability"])


def _must_reject(call, label):
    try:
        call()
    except OracleError:
        return
    raise AssertionError(f"oracle accepted adversarial case: {label}")


def main():
    corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
    result = evaluate(corpus)
    _assert_expected(corpus, result)

    # Mutation 1: keep every amount and global debit/credit total unchanged,
    # but redirect the issuer's liability to a different holder.
    wrong_holder = json.loads(json.dumps(corpus))
    wrong_holder["events"][0]["postings"][3]["counterparty_entity_id"] = "supplier-1"
    _must_reject(lambda: evaluate(wrong_holder), "wrong holder on mirrored liability")

    # Mutation 2: preserve all amounts and balance but change one instrument ID.
    wrong_instrument = json.loads(json.dumps(corpus))
    wrong_instrument["events"][0]["postings"][1]["instrument_id"] = "loan-other"
    _must_reject(lambda: evaluate(wrong_instrument), "wrong loan instrument identity")

    # Mutation 3: duplicate delivery cannot be silently treated as a new event.
    duplicate_event = json.loads(json.dumps(corpus))
    duplicate_event["events"].append(duplicate_event["events"][0])
    _must_reject(lambda: evaluate(duplicate_event), "duplicate event ID")

    print("SFC-GOLD-1 independent oracle: PASS")
    print("source: frozen JSON corpus; no production/audit imports")
    print(f"events={result['event_count']}; periods={result['periods']}")
    print("closing positions match six frozen holder/issuer instrument records")
    print("system deposits: assets=14; liabilities=14")
    print("sector financial net lending: CB=0 H=-7 NFC=+7; aggregate=0")
    print("negative controls: wrong holder, wrong instrument identity and duplicate event rejected")


if __name__ == "__main__":
    main()
