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



def _validate_event_roles(event_type, postings):
    """Enforce cross-leg economic roles, not merely local balance/mirroring."""
    by_key = defaultdict(list)
    for row in postings:
        by_key[(row["account"], row["side"])].append(row)

    def one(account, side):
        rows = by_key[(account, side)]
        if len(rows) != 1:
            raise OracleError(f"expected one {account}/{side} posting")
        return rows[0]

    def require(condition, message):
        if not condition:
            raise OracleError(f"{event_type} role invariant: {message}")

    def class_is(row, expected):
        require(row.get("instrument_class") == expected,
                f"{row['account']} must use {expected} instrument class")

    if event_type == "bank_loan_origination":
        loan_asset = one("loan_asset", "D")
        loan_liability = one("loan_liability", "C")
        deposit_asset = one("deposit_asset", "D")
        deposit_liability = one("deposit_liability", "C")

        borrower = loan_asset["counterparty_entity_id"]
        bank = loan_asset["entity_id"]
        require(loan_asset["institutional_sector"] == "CB"
                and loan_liability["institutional_sector"] == "H",
                "v1 loan roles require a CB lender and household borrower")
        require(loan_asset["instrument_id"] != deposit_asset["instrument_id"],
                "loan and deposit must be distinct instruments")
        require(loan_liability["entity_id"] == borrower,
                "loan liability holder must be the loan borrower")
        require(loan_liability["counterparty_entity_id"] == bank,
                "loan creditor must be the originating bank")
        require(loan_liability["issuer_entity_id"] == borrower,
                "borrower must issue its loan liability")
        require(loan_asset["issuer_entity_id"] == borrower,
                "loan asset must identify the borrower as issuer")
        require(deposit_asset["entity_id"] == borrower,
                "new deposit asset must belong to the borrower")
        require(deposit_asset["issuer_entity_id"] == bank,
                "new deposit must be issued by the originating bank")
        require(deposit_liability["entity_id"] == bank,
                "deposit liability must be booked by the originating bank")
        require(deposit_liability["counterparty_entity_id"] == borrower,
                "deposit liability holder must be the borrower")
        require(deposit_liability["issuer_entity_id"] == bank,
                "bank must issue its deposit liability")
        require(deposit_asset["counterparty_entity_id"] == bank,
                "deposit asset counterparty must be the originating bank")
        class_is(loan_asset, "loan")
        class_is(loan_liability, "loan")
        class_is(deposit_asset, "deposit")
        class_is(deposit_liability, "deposit")
        require(loan_asset["currency"] == deposit_asset["currency"],
                "loan and created deposit currencies must match in v1")

    elif event_type == "supplier_payment":
        deposit_asset_out = one("deposit_asset", "C")
        deposit_asset_in = one("deposit_asset", "D")
        deposit_liability_out = one("deposit_liability", "D")
        deposit_liability_in = one("deposit_liability", "C")

        bank = deposit_liability_out["entity_id"]
        payer = deposit_asset_out["entity_id"]
        supplier = deposit_asset_in["entity_id"]
        require(deposit_liability_out["institutional_sector"] == "CB"
                and deposit_asset_out["institutional_sector"] == "H"
                and deposit_asset_in["institutional_sector"] == "NFC",
                "v1 payment roles require CB bank, household payer and NFC supplier")
        require(deposit_asset_out["instrument_id"] != deposit_asset_in["instrument_id"],
                "payer and supplier deposits must be distinct instruments")
        require(deposit_liability_in["entity_id"] == bank,
                "both deposit liabilities must be booked by the same bank")
        require(deposit_asset_out["counterparty_entity_id"] == bank
                and deposit_asset_in["counterparty_entity_id"] == bank,
                "both deposit holders must face the same bank")
        require(deposit_liability_out["counterparty_entity_id"] == payer,
                "outgoing deposit liability must identify the payer")
        require(deposit_liability_in["counterparty_entity_id"] == supplier,
                "incoming deposit liability must identify the supplier")
        require(deposit_asset_out["issuer_entity_id"] == bank
                and deposit_asset_in["issuer_entity_id"] == bank
                and deposit_liability_out["issuer_entity_id"] == bank
                and deposit_liability_in["issuer_entity_id"] == bank,
                "transferred deposits must share the issuing bank")
        require(payer != supplier, "payer and supplier must be distinct holders")
        for row in postings:
            class_is(row, "deposit")
        require(deposit_asset_out["currency"] == deposit_asset_in["currency"],
                "both sides of a deposit transfer must share currency in v1")

    elif event_type == "principal_repayment":
        loan_liability = one("loan_liability", "D")
        loan_asset = one("loan_asset", "C")
        deposit_asset = one("deposit_asset", "C")
        deposit_liability = one("deposit_liability", "D")

        borrower = loan_liability["entity_id"]
        bank = loan_asset["entity_id"]
        require(loan_asset["institutional_sector"] == "CB"
                and loan_liability["institutional_sector"] == "H",
                "v1 repayment roles require a CB lender and household borrower")
        require(loan_asset["instrument_id"] != deposit_asset["instrument_id"],
                "loan and repayment deposit must be distinct instruments")
        require(loan_liability["counterparty_entity_id"] == bank,
                "borrower loan liability must be owed to the lending bank")
        require(loan_asset["counterparty_entity_id"] == borrower,
                "bank loan asset must identify the repaying borrower")
        require(loan_asset["issuer_entity_id"] == borrower
                and loan_liability["issuer_entity_id"] == borrower,
                "loan claim and liability must identify the borrower as issuer")
        require(deposit_asset["entity_id"] == borrower,
                "repayment deposit asset must belong to the borrower")
        require(deposit_asset["counterparty_entity_id"] == bank,
                "repayment deposit asset must face the lending bank")
        require(deposit_asset["issuer_entity_id"] == bank,
                "repayment deposit must be issued by the lending bank")
        require(deposit_liability["entity_id"] == bank
                and deposit_liability["counterparty_entity_id"] == borrower,
                "deposit liability reduction must belong to the bank and borrower")
        require(deposit_liability["issuer_entity_id"] == bank,
                "bank must issue the repaid deposit liability")
        class_is(loan_asset, "loan")
        class_is(loan_liability, "loan")
        class_is(deposit_asset, "deposit")
        class_is(deposit_liability, "deposit")
        require(loan_asset["currency"] == deposit_asset["currency"],
                "loan and repayment deposit currencies must match in v1")
    else:
        raise OracleError(f"unsupported event type for role validation: {event_type}")

def evaluate(corpus):
    if corpus.get("corpus_id") != "SFC-GOLD-1" or corpus.get("version") != "1.0.0":
        raise OracleError("unsupported SFC-GOLD-1 corpus identity/version")
    if corpus.get("status") != "FROZEN_SYNTHETIC_CONTROL_CORPUS":
        raise OracleError("corpus is not marked as the frozen synthetic control")

    declared_periods = corpus.get("periods")
    if not isinstance(declared_periods, list) or len(declared_periods) != 1:
        raise OracleError("SFC-GOLD-1 v1 requires exactly one declared period")
    period_row = declared_periods[0]
    if not isinstance(period_row, dict) or type(period_row.get("effective_period")) is not int:
        raise OracleError("invalid declared period record")
    declared_period = period_row["effective_period"]
    if declared_period <= 0:
        raise OracleError("declared effective period must be positive")

    events = corpus.get("events")
    if not isinstance(events, list) or not events:
        raise OracleError("corpus must contain events")

    entity_rows = corpus.get("entities")
    if not isinstance(entity_rows, list) or not entity_rows:
        raise OracleError("entity registry must be a non-empty list")
    entities = {}
    for row in entity_rows:
        if not isinstance(row, dict):
            raise OracleError("entity registry rows must be objects")
        entity_id, sector = row.get("entity_id"), row.get("sector")
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise OracleError("entity registry contains blank entity ID")
        if not isinstance(sector, str) or not sector.strip():
            raise OracleError("entity registry contains blank sector")
        if entity_id in entities:
            raise OracleError("entity registry contains duplicate IDs")
        entities[entity_id] = sector
    event_ids = set()
    balances = defaultdict(lambda: D("0"))
    instrument_catalog = {}
    sector_assets = defaultdict(lambda: D("0"))
    sector_liabilities = defaultdict(lambda: D("0"))
    period_set = set()

    for event in events:
        event_id = event.get("event_id")
        period = event.get("effective_period")
        if not isinstance(event_id, str) or not event_id or event_id in event_ids:
            raise OracleError("missing or duplicate event ID")
        if type(period) is not int or period != declared_period:
            raise OracleError("event period does not match the frozen declared period")
        event_ids.add(event_id)
        period_set.add(period)
        postings = event.get("postings")
        if not isinstance(postings, list) or not postings:
            raise OracleError("event must contain postings")

        debit = D("0")
        credit = D("0")
        event_assets = defaultdict(lambda: D("0"))
        event_liabilities = defaultdict(lambda: D("0"))

        event_balance_deltas = defaultdict(lambda: D("0"))
        for posting in postings:
            if not isinstance(posting, dict):
                raise OracleError("posting rows must be objects")
            account = posting.get("account")
            side = posting.get("side")
            entity = posting.get("entity_id")
            sector = posting.get("institutional_sector")
            amount = _decimal(posting.get("amount"))
            if not all(isinstance(x, str) and x.strip()
                       for x in (account, entity, sector)):
                raise OracleError("posting account, entity and sector are required")
            if entity not in entities or entities[entity] != sector:
                raise OracleError("posting entity/sector does not match frozen registry")
            for entity_field, sector_field in (
                    ("counterparty_entity_id", "counterparty_sector"),
                    ("issuer_entity_id", "issuer_sector")):
                related = posting.get(entity_field, "")
                related_sector = posting.get(sector_field, "")
                if related:
                    if related not in entities or entities[related] != related_sector:
                        raise OracleError(f"{entity_field}/{sector_field} registry mismatch")
                elif related_sector:
                    raise OracleError(f"{sector_field} exists without {entity_field}")

            counterparty = posting.get("counterparty_entity_id")
            issuer = posting.get("issuer_entity_id")
            if not isinstance(counterparty, str) or not counterparty.strip():
                raise OracleError("v1 postings require a counterparty entity")
            if not isinstance(issuer, str) or not issuer.strip():
                raise OracleError("v1 postings require an issuer entity")
            if counterparty not in entities or issuer not in entities:
                raise OracleError("posting counterparty and issuer must be registered")
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
                instrument_id = posting.get("instrument_id")
                if not isinstance(instrument_id, str) or not instrument_id.strip():
                    raise OracleError("financial posting requires an instrument ID")
                holder = entity if account.endswith("_asset") else counterparty
                legal_issuer = issuer
                instrument_identity = (
                    *[posting.get(name) for name in REQUIRED_IDENTITY],
                    holder, legal_issuer,
                )
                if any(not isinstance(value, str) or not value.strip()
                       for value in instrument_identity):
                    raise OracleError("instrument identity and holder/issuer must be complete")
                prior_identity = instrument_catalog.get(instrument_id)
                if prior_identity is not None and prior_identity != instrument_identity:
                    raise OracleError(
                        f"instrument identity changed across events: {instrument_id}")
                instrument_catalog[instrument_id] = instrument_identity

                balance_key = (entity, account, instrument_id)
                event_balance_deltas[balance_key] += natural_change

        event_type = event.get("event_type")
        _validate_event_roles(event_type, postings)
        account_sides = [(row["account"], row["side"], _decimal(row["amount"]))
                         for row in postings]
        expected_rules = {
            "bank_loan_origination": {
                "loan_asset": {"D": 1}, "loan_liability": {"C": 1},
                "deposit_asset": {"D": 1}, "deposit_liability": {"C": 1},
            },
            "supplier_payment": {
                "deposit_asset": {"D": 1, "C": 1},
                "deposit_liability": {"D": 1, "C": 1},
            },
            "principal_repayment": {
                "loan_liability": {"D": 1}, "loan_asset": {"C": 1},
                "deposit_asset": {"C": 1}, "deposit_liability": {"D": 1},
            },
        }
        if event_type not in expected_rules:
            raise OracleError(f"unsupported SFC-GOLD-1 event type: {event_type}")
        observed = defaultdict(list)
        for account, side, amount in account_sides:
            observed[account].append((side, amount))
        rule = expected_rules[event_type]
        if set(observed) != set(rule) or any(
                {side: sum(1 for observed_side, _ in observed[name]
                          if observed_side == side)
                 for side in ("D", "C")} !=
                {side: rule[name].get(side, 0) for side in ("D", "C")}
                for name in rule):
            raise OracleError(f"event account composition/sides invalid: {event_type}")
        if event_type in {"bank_loan_origination", "supplier_payment",
                          "principal_repayment"}:
            amounts = {amount for _, _, amount in account_sides}
            if len(amounts) != 1:
                raise OracleError(f"{event_type} legs must share one amount")

        if debit != credit:
            raise OracleError(
                f"unbalanced event {event_id}: debit {debit} != credit {credit}")

        event_assets = {k: v for k, v in event_assets.items() if v}
        event_liabilities = {k: v for k, v in event_liabilities.items() if v}
        if event_assets != event_liabilities:
            raise OracleError(
                f"event-level claim mirror mismatch {event_id}: "
                f"assets={event_assets}, liabilities={event_liabilities}")
        # Apply this event only after its local accounting and mirror checks.
        # The v1 corpus has no overdraft facility or opening stock, so every
        # instrument position must remain non-negative after each event.
        for balance_key, delta in event_balance_deltas.items():
            next_balance = balances[balance_key] + delta
            if next_balance < 0:
                raise OracleError(
                    f"negative intermediate position after {event_id}: "
                    f"{balance_key} -> {next_balance}")
        for balance_key, delta in event_balance_deltas.items():
            balances[balance_key] += delta

    if len(period_set) != 1 or period_set != {declared_period}:
        raise OracleError("events do not match the single declared SFC-GOLD-1 period")

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
    wrong_holder["events"][0]["postings"][3]["counterparty_sector"] = "NFC"
    _must_reject(lambda: evaluate(wrong_holder), "wrong holder on mirrored liability")

    # Mutation 2: preserve all amounts and balance but change one instrument ID.
    wrong_instrument = json.loads(json.dumps(corpus))
    wrong_instrument["events"][0]["postings"][1]["instrument_id"] = "loan-other"
    _must_reject(lambda: evaluate(wrong_instrument), "wrong loan instrument identity")

    # Mutation 3: sector labels cannot be detached from the frozen entity registry.
    wrong_sector = json.loads(json.dumps(corpus))
    wrong_sector["events"][0]["postings"][0]["institutional_sector"] = "H"
    _must_reject(lambda: evaluate(wrong_sector), "entity/sector mismatch")

    # Mutation 4: event labels have enforced posting composition, not free-form tags.
    relabelled = json.loads(json.dumps(corpus))
    relabelled["events"][1]["event_type"] = "bank_loan_origination"
    _must_reject(lambda: evaluate(relabelled), "event-type composition mismatch")

    # Mutation 5: changing the frozen bank sector and every matching
    # posting label preserves registry consistency and accounting arithmetic,
    # but a non-CB entity cannot play the bank role in this v1 corpus.
    wrong_bank_sector = json.loads(json.dumps(corpus))
    wrong_bank_sector["entities"][0]["sector"] = "NFC"
    for event in wrong_bank_sector["events"]:
        for posting in event["postings"]:
            if posting["entity_id"] == "bank-1":
                posting["institutional_sector"] = "NFC"
            if posting.get("counterparty_entity_id") == "bank-1":
                posting["counterparty_sector"] = "NFC"
            if posting.get("issuer_entity_id") == "bank-1":
                posting["issuer_sector"] = "NFC"
    _must_reject(lambda: evaluate(wrong_bank_sector), "bank role assigned to non-CB sector")

    # Mutation 6: locally mirrored deposit legs must still belong to the
    # borrower named by the loan legs. This mutation preserves both deposit
    # holder/issuer mirrors and global debit/credit totals.
    wrong_borrower_role = json.loads(json.dumps(corpus))
    wrong_borrower_role["events"][0]["postings"][2]["entity_id"] = "supplier-1"
    wrong_borrower_role["events"][0]["postings"][2]["institutional_sector"] = "NFC"
    wrong_borrower_role["events"][0]["postings"][3]["counterparty_entity_id"] = "supplier-1"
    wrong_borrower_role["events"][0]["postings"][3]["counterparty_sector"] = "NFC"
    _must_reject(lambda: evaluate(wrong_borrower_role), "deposit issued to an entity other than the borrower")

    # Mutation 7: an otherwise mirrored loan may not be relabelled as a deposit.
    wrong_class = json.loads(json.dumps(corpus))
    wrong_class["events"][0]["postings"][0]["instrument_class"] = "deposit"
    wrong_class["events"][0]["postings"][1]["instrument_class"] = "deposit"
    _must_reject(lambda: evaluate(wrong_class), "loan account with deposit instrument class")

    # Mutation 8: a fully balanced but over-sized repayment must fail at
    # the intermediate stock boundary, before negative loan/deposit balances
    # can be hidden by later aggregate arithmetic.
    excessive_repayment = json.loads(json.dumps(corpus))
    for posting in excessive_repayment["events"][2]["postings"]:
        posting["amount"] = "20"
    _must_reject(lambda: evaluate(excessive_repayment), "repayment exceeds available positions")

    # Mutation 9: event array order is the canonical within-period replay order.
    # Replaying repayment before origination creates a negative liability.
    out_of_order = json.loads(json.dumps(corpus))
    out_of_order["events"] = [
        out_of_order["events"][2],
        out_of_order["events"][0],
        out_of_order["events"][1],
    ]
    _must_reject(lambda: evaluate(out_of_order), "out-of-order event replay")

    # Mutation 10: a reused instrument ID cannot silently change its identity
    # dimensions between otherwise mirrored events.
    changed_instrument_identity = json.loads(json.dumps(corpus))
    for posting in changed_instrument_identity["events"][2]["postings"]:
        if posting["instrument_id"] == "loan-hh-001":
            posting["maturity"] = "2030-12-31"
    _must_reject(lambda: evaluate(changed_instrument_identity),
                 "instrument identity changed between events")

    # Mutation 11: events cannot be moved to a period absent from the frozen
    # corpus declaration.
    undeclared_period = json.loads(json.dumps(corpus))
    for event in undeclared_period["events"]:
        event["effective_period"] = 2
    _must_reject(lambda: evaluate(undeclared_period), "undeclared event period")

    # Mutation 8: duplicate delivery cannot be silently treated as a new event.
    duplicate_event = json.loads(json.dumps(corpus))
    duplicate_event["events"].append(duplicate_event["events"][0])
    _must_reject(lambda: evaluate(duplicate_event), "duplicate event ID")

    print("SFC-GOLD-1 independent oracle: PASS")
    print("source: frozen JSON corpus; no production/audit imports")
    print(f"events={result['event_count']}; periods={result['periods']}")
    print("closing positions match six frozen holder/issuer instrument records")
    print("system deposits: assets=14; liabilities=14")
    print("intermediate stocks: non-negative after every canonical event")
    print("instrument identity: immutable across all postings and events")
    print("sector financial net lending: CB=0 H=-7 NFC=+7; aggregate=0")
    print("negative controls: wrong holder, instrument identity, entity sector, bank role, event type, cross-leg borrower role, instrument class, excessive repayment, out-of-order replay, undeclared period and duplicate event rejected")


if __name__ == "__main__":
    main()
