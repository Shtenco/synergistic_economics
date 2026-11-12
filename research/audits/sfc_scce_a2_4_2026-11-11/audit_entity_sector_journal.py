"""A2.4.4 entity/sector/issuer identity control.

This fixture separates stable entity identity from institutional-sector
membership and validates claim mirrors at entity level before sector
aggregation. All data are synthetic controls, not repository runtime postings.
"""
from dataclasses import dataclass, replace
from decimal import Decimal as D


SECTORS = {"H", "NFC", "CB", "CBank", "GOV", "ROW"}
CLAIM_ACCOUNTS = {
    "deposit_asset", "deposit_liability",
    "loan_asset", "loan_liability",
    "trade_receivable_asset", "trade_payable_liability",
    "interest_receivable_asset", "interest_payable_liability",
}
EVENT_TYPES = {
    "bank_loan_origination", "nonbank_loan_origination",
    "nonbank_deposit_transfer",
    "supplier_settlement", "principal_repayment",
    "interest_accrual", "interest_settlement",
    "creditor_writeoff", "legal_forgiveness",
}


class IdentityError(ValueError):
    pass


@dataclass(frozen=True)
class SectorMembership:
    entity_id: str
    sector: str
    effective_from: int
    effective_to: int | None = None


class EntityRegistry:
    def __init__(self, memberships):
        self.memberships = tuple(memberships)
        grouped = {}
        for row in self.memberships:
            if not isinstance(row, SectorMembership):
                raise IdentityError("registry rows must be SectorMembership values")
            if not isinstance(row.entity_id, str) or not row.entity_id.strip():
                raise IdentityError("entity_id must be a non-empty stable string")
            if not isinstance(row.sector, str) or row.sector not in SECTORS:
                raise IdentityError(f"unknown institutional sector: {row.sector}")
            if (not isinstance(row.effective_from, int)
                    or isinstance(row.effective_from, bool)
                    or row.effective_from < 0):
                raise IdentityError("effective_from must be a non-negative integer period")
            if row.effective_to is not None and (
                    not isinstance(row.effective_to, int)
                    or isinstance(row.effective_to, bool)
                    or row.effective_to <= row.effective_from):
                raise IdentityError("effective_to must be later than effective_from")
            grouped.setdefault(row.entity_id, []).append(row)

        self._by_entity = {}
        for entity_id, rows in grouped.items():
            rows.sort(key=lambda x: x.effective_from)
            for previous, current in zip(rows, rows[1:]):
                if previous.effective_to is None or current.effective_from < previous.effective_to:
                    raise IdentityError(
                        f"overlapping sector memberships for entity {entity_id}")
            self._by_entity[entity_id] = tuple(rows)

    def sector_of(self, entity_id, period):
        if not isinstance(entity_id, str) or not entity_id.strip():
            raise IdentityError("entity_id is required")
        if not isinstance(period, int) or isinstance(period, bool) or period < 0:
            raise IdentityError("effective period must be a non-negative integer")
        rows = self._by_entity.get(entity_id, ())
        matches = [
            row for row in rows
            if row.effective_from <= period
            and (row.effective_to is None or period < row.effective_to)
        ]
        if len(matches) != 1:
            raise IdentityError(
                f"entity {entity_id} has {len(matches)} sector memberships at period {period}")
        return matches[0].sector


@dataclass(frozen=True)
class JournalLine:
    account: str
    side: str
    amount: D
    entity_id: str
    institutional_sector: str
    counterparty_entity_id: str | None = None
    counterparty_sector: str | None = None
    issuer_entity_id: str | None = None
    issuer_sector: str | None = None
    instrument_id: str | None = None
    instrument_class: str | None = None
    currency: str | None = None
    maturity: str | None = None
    denomination: str | None = None
    valuation_basis: str | None = None


@dataclass(frozen=True)
class JournalEvent:
    event_id: str
    event_type: str
    effective_period: int
    lines: tuple[JournalLine, ...]


def make_line(registry, period, account, side, amount, entity_id,
              *, counterparty=None, issuer=None, instrument_id=None,
              instrument_class=None, currency=None, maturity=None,
              denomination=None, valuation_basis=None):
    sector = registry.sector_of(entity_id, period)
    counterparty_sector = registry.sector_of(counterparty, period) if counterparty else None
    issuer_sector = registry.sector_of(issuer, period) if issuer else None
    # Synthetic audit fixtures must still satisfy the complete instrument
    # identity contract; use explicit, deterministic fixture dimensions rather
    # than leaving claim fields absent.
    if account in CLAIM_ACCOUNTS:
        currency = currency or "LCU"
        denomination = denomination or "LCU"
        valuation_basis = valuation_basis or "NOMINAL"
        maturity = maturity or ("ON_DEMAND" if "deposit" in account else "2029-12-31")
        instrument_class = instrument_class or (
            "deposit" if "deposit" in account else
            "trade_credit" if "trade" in account else
            "interest" if "interest" in account else "loan"
        )
        if instrument_id is None:
            instrument_id = f"{account}:{entity_id}:{issuer or counterparty or 'external'}"
    return JournalLine(
        account, side, D(str(amount)), entity_id, sector,
        counterparty, counterparty_sector, issuer, issuer_sector,
        instrument_id, instrument_class, currency, maturity,
        denomination, valuation_basis)


def _claim_identity(line):
    fields = (
        line.instrument_id, line.instrument_class, line.currency,
        line.maturity, line.denomination, line.valuation_basis,
    )
    if not all(isinstance(value, str) and value.strip() for value in fields):
        raise IdentityError("financial claim requires complete instrument identity")
    return fields


def validate_journal_line(line, registry, period):
    if not isinstance(line, JournalLine):
        raise IdentityError("journal line has the wrong record type")
    if not isinstance(line.account, str) or not line.account:
        raise IdentityError("account is required")
    if not isinstance(line.side, str) or line.side not in {"D", "C"}:
        raise IdentityError("journal side must be D or C")
    if not isinstance(line.amount, D) or not line.amount.is_finite() or line.amount <= 0:
        raise IdentityError("journal amount must be a finite positive Decimal")
    expected_sector = registry.sector_of(line.entity_id, period)
    if line.institutional_sector != expected_sector:
        raise IdentityError(
            f"entity/sector mismatch for {line.entity_id}: "
            f"{line.institutional_sector} != {expected_sector}")

    if line.counterparty_entity_id:
        expected_counterparty_sector = registry.sector_of(
            line.counterparty_entity_id, period)
        if line.counterparty_sector != expected_counterparty_sector:
            raise IdentityError("counterparty entity/sector mismatch")
    elif line.counterparty_sector:
        raise IdentityError("counterparty sector without counterparty entity ID")

    if line.issuer_entity_id:
        expected_issuer_sector = registry.sector_of(line.issuer_entity_id, period)
        if line.issuer_sector != expected_issuer_sector:
            raise IdentityError("issuer entity/sector mismatch")
    elif line.issuer_sector:
        raise IdentityError("issuer sector without issuer entity ID")

    if line.account in CLAIM_ACCOUNTS:
        _claim_identity(line)
        if not line.issuer_entity_id:
            raise IdentityError("financial claim must identify its issuer entity")
        if line.account.endswith("_liability"):
            if (line.issuer_entity_id != line.entity_id
                    or not line.counterparty_entity_id):
                raise IdentityError(
                    "liability line must identify issuer as entity and holder as counterparty")
    return True


def claim_holder_issuer_deltas(event):
    """Mirror all recognized claim assets/liabilities by full entity-level key."""
    assets, liabilities = {}, {}
    for line in event.lines:
        if line.account.endswith("_asset"):
            delta = line.amount if line.side == "D" else -line.amount
            holder, issuer = line.entity_id, line.issuer_entity_id
            target = assets
        elif line.account.endswith("_liability"):
            delta = line.amount if line.side == "C" else -line.amount
            holder, issuer = line.counterparty_entity_id, line.entity_id
            target = liabilities
        else:
            continue
        key = (
            line.instrument_id, line.instrument_class, holder, issuer,
            line.currency, line.maturity, line.denomination, line.valuation_basis,
        )
        target[key] = target.get(key, D("0")) + delta
    assets = {key: value for key, value in assets.items() if value}
    liabilities = {key: value for key, value in liabilities.items() if value}
    if assets != liabilities:
        raise IdentityError(
            f"entity-level claim asset/liability mismatch: "
            f"assets={assets}, liabilities={liabilities}")
    return assets


def deposit_holder_issuer_deltas(event):
    assets, liabilities = {}, {}
    for line in event.lines:
        if line.account == "deposit_asset":
            delta = line.amount if line.side == "D" else -line.amount
            key = (
                line.instrument_id, line.entity_id, line.issuer_entity_id,
                line.currency, line.maturity, line.denomination,
                line.valuation_basis,
            )
            assets[key] = assets.get(key, D("0")) + delta
        elif line.account == "deposit_liability":
            delta = line.amount if line.side == "C" else -line.amount
            key = (
                line.instrument_id, line.counterparty_entity_id, line.entity_id,
                line.currency, line.maturity, line.denomination,
                line.valuation_basis,
            )
            liabilities[key] = liabilities.get(key, D("0")) + delta
    assets = {key: value for key, value in assets.items() if value}
    liabilities = {key: value for key, value in liabilities.items() if value}
    if assets != liabilities:
        raise IdentityError(
            f"entity-level deposit claim mismatch: assets={assets}, liabilities={liabilities}")
    return assets


class EntityJournal:
    def __init__(self, registry):
        self.registry = registry
        self.events = {}

    def post(self, event):
        if (not isinstance(event.event_id, str) or not event.event_id.strip()
                or event.event_id in self.events):
            raise IdentityError("missing or duplicate event ID")
        if (not isinstance(event.event_type, str)
                or event.event_type not in EVENT_TYPES):
            raise IdentityError(f"unknown or unsupported event type: {event.event_type}")
        if not isinstance(event.lines, tuple) or not event.lines:
            raise IdentityError("event lines must be a non-empty immutable tuple")

        debit = D("0")
        credit = D("0")
        posting_keys = set()
        for line in event.lines:
            validate_journal_line(line, self.registry, event.effective_period)
            if line.side == "D":
                debit += line.amount
            else:
                credit += line.amount
            if line.account in CLAIM_ACCOUNTS:
                key = (
                    line.account, line.entity_id, line.counterparty_entity_id,
                    line.issuer_entity_id, line.instrument_id, line.instrument_class,
                    line.currency, line.maturity, line.denomination, line.valuation_basis,
                )
                if key in posting_keys:
                    raise IdentityError(f"duplicate claim-side posting: {key}")
                posting_keys.add(key)

        if debit != credit:
            raise IdentityError(f"unbalanced event {event.event_id}: {debit} != {credit}")

        # Event labels carry economic meaning, not merely a descriptive tag.
        # In particular, a deposit transfer must never conceal creation of a
        # non-bank loan, and a loan origination must not silently create a
        # deposit unless the originator is a bank.
        by_account = {}
        for line in event.lines:
            by_account.setdefault(line.account, []).append(line)

        def exact_accounts(expected):
            if {name: len(by_account.get(name, ())) for name in expected} != expected or set(by_account) != set(expected):
                raise IdentityError(
                    f"{event.event_type} has an invalid account composition: "
                    f"{ {name: len(rows) for name, rows in by_account.items()} }")

        if event.event_type == "bank_loan_origination":
            exact_accounts({
                "loan_asset": 1, "loan_liability": 1,
                "deposit_asset": 1, "deposit_liability": 1,
            })
            loan_asset = by_account["loan_asset"][0]
            loan_liability = by_account["loan_liability"][0]
            deposit_asset = by_account["deposit_asset"][0]
            deposit_liability = by_account["deposit_liability"][0]
            if any(line.side != side for line, side in (
                    (loan_asset, "D"), (loan_liability, "C"),
                    (deposit_asset, "D"), (deposit_liability, "C"))):
                raise IdentityError("bank loan origination has invalid debit/credit sides")
            if len({line.amount for line in event.lines}) != 1:
                raise IdentityError("bank loan origination must match loan and deposit amounts")
            bank_id = loan_asset.entity_id
            borrower_id = loan_asset.issuer_entity_id
            if (registry.sector_of(bank_id, event.effective_period) != "CB"
                    or loan_liability.entity_id != borrower_id
                    or loan_liability.counterparty_entity_id != bank_id
                    or deposit_asset.entity_id != borrower_id
                    or deposit_asset.issuer_entity_id != bank_id
                    or deposit_liability.entity_id != bank_id
                    or deposit_liability.counterparty_entity_id != borrower_id):
                raise IdentityError("bank loan origination participant/issuer roles do not reconcile")

        elif event.event_type == "nonbank_loan_origination":
            exact_accounts({"loan_asset": 1, "loan_liability": 1})
            loan_asset = by_account["loan_asset"][0]
            loan_liability = by_account["loan_liability"][0]
            if (loan_asset.side != "D" or loan_liability.side != "C"
                    or loan_asset.amount != loan_liability.amount
                    or registry.sector_of(loan_asset.entity_id, event.effective_period) == "CB"
                    or loan_asset.issuer_entity_id != loan_liability.entity_id
                    or loan_liability.counterparty_entity_id != loan_asset.entity_id):
                raise IdentityError("non-bank loan origination must create one mirrored loan and no deposit")

        elif event.event_type == "nonbank_deposit_transfer":
            exact_accounts({"deposit_asset": 2, "deposit_liability": 2})
            asset_debit = [x for x in by_account["deposit_asset"] if x.side == "D"]
            asset_credit = [x for x in by_account["deposit_asset"] if x.side == "C"]
            liability_debit = [x for x in by_account["deposit_liability"] if x.side == "D"]
            liability_credit = [x for x in by_account["deposit_liability"] if x.side == "C"]
            if any(len(x) != 1 for x in (
                    asset_debit, asset_credit, liability_debit, liability_credit)):
                raise IdentityError("deposit transfer requires one payer and one recipient on both sides")
            recipient, payer = asset_debit[0], asset_credit[0]
            payer_liability, recipient_liability = liability_debit[0], liability_credit[0]
            bank_id = payer_liability.entity_id
            if (len({x.amount for x in event.lines}) != 1
                    or payer.entity_id == recipient.entity_id
                    or payer_liability.entity_id != recipient_liability.entity_id
                    or payer_liability.entity_id != bank_id
                    or payer.issuer_entity_id != bank_id
                    or recipient.issuer_entity_id != bank_id
                    or payer_liability.counterparty_entity_id != payer.entity_id
                    or recipient_liability.counterparty_entity_id != recipient.entity_id):
                raise IdentityError("deposit transfer must move existing deposits between two holders at one issuer")

        # A unilateral creditor write-off is a narrowly typed accounting
        # recognition event: one loan-asset credit against one loss-allowance
        # debit. It does not extinguish the debtor's legal claim. All other
        # recognized claim movements must have an entity-level mirror.
        if event.event_type == "creditor_writeoff":
            loan_credits = [
                line for line in event.lines
                if line.account == "loan_asset" and line.side == "C"
            ]
            allowance_debits = [
                line for line in event.lines
                if line.account == "loss_allowance" and line.side == "D"
            ]
            if (len(loan_credits) != 1 or len(allowance_debits) != 1
                    or len(event.lines) != 2
                    or loan_credits[0].amount != allowance_debits[0].amount
                    or loan_credits[0].entity_id != allowance_debits[0].entity_id):
                raise IdentityError(
                    "creditor write-off must be one loan-asset credit against "
                    "one equal loss-allowance debit; debtor obligation remains")
        else:
            claim_holder_issuer_deltas(event)
        if any(line.account in {"deposit_asset", "deposit_liability"}
               for line in event.lines):
            deposit_holder_issuer_deltas(event)
        self.events[event.event_id] = event
        return debit, credit


@dataclass(frozen=True)
class ClaimPosition:
    side: str
    entity_id: str
    institutional_sector: str
    counterparty_entity_id: str
    counterparty_sector: str
    issuer_entity_id: str
    issuer_sector: str
    instrument_id: str
    instrument_class: str
    currency: str
    maturity: str
    denomination: str
    valuation_basis: str
    effective_period: int
    opening: D
    transactions: D
    revaluation: D
    other_volume: D
    closing: D


def make_claim_position(registry, period, side, holder, issuer, instrument_id,
                        instrument_class, opening, transactions, closing,
                        revaluation=0, other_volume=0, currency="LCU",
                        maturity="unspecified", denomination="nominal",
                        valuation_basis="nominal"):
    if side == "holder_asset":
        entity_id, counterparty = holder, issuer
    elif side == "issuer_liability":
        entity_id, counterparty = issuer, holder
    else:
        raise IdentityError("claim side must be holder_asset or issuer_liability")
    return ClaimPosition(
        side, entity_id, registry.sector_of(entity_id, period),
        counterparty, registry.sector_of(counterparty, period),
        issuer, registry.sector_of(issuer, period),
        instrument_id, instrument_class, currency, maturity, denomination,
        valuation_basis, period, D(str(opening)), D(str(transactions)),
        D(str(revaluation)), D(str(other_volume)), D(str(closing)))


def claim_key(row):
    return (
        row.effective_period, row.instrument_id, row.instrument_class,
        row.entity_id if row.side == "holder_asset" else row.counterparty_entity_id,
        row.issuer_entity_id, row.currency, row.maturity,
        row.denomination, row.valuation_basis,
    )


def validate_claim_positions(holder_records, issuer_records, registry):
    held, issued = {}, {}
    for row in holder_records:
        if not all(isinstance(value, str) and value.strip() for value in (
                row.instrument_id, row.instrument_class, row.currency,
                row.maturity, row.denomination, row.valuation_basis)):
            raise IdentityError("holder claim has incomplete instrument identity")
        if row.side != "holder_asset":
            raise IdentityError("holder register contains a non-asset record")
        if registry.sector_of(row.entity_id, row.effective_period) != row.institutional_sector:
            raise IdentityError("holder entity/sector identity mismatch")
        if registry.sector_of(row.issuer_entity_id, row.effective_period) != row.issuer_sector:
            raise IdentityError("holder issuer entity/sector mismatch")
        if (row.counterparty_entity_id != row.issuer_entity_id
                or row.counterparty_sector != row.issuer_sector):
            raise IdentityError("holder-side counterparty must identify the claim issuer")
        values = (row.opening, row.transactions, row.revaluation,
                  row.other_volume, row.closing)
        if any(not isinstance(value, D) or not value.is_finite() for value in values):
            raise IdentityError("holder claim contains non-finite or non-Decimal values")
        if row.opening < 0 or row.closing < 0:
            raise IdentityError("negative holder claim position")
        if row.opening + row.transactions + row.revaluation + row.other_volume != row.closing:
            raise IdentityError("holder T/V/O stock-flow identity failed")
        key = claim_key(row)
        if key in held:
            raise IdentityError(f"duplicate holder claim record: {key}")
        held[key] = (
            row.opening, row.transactions, row.revaluation,
            row.other_volume, row.closing,
        )

    for row in issuer_records:
        if not all(isinstance(value, str) and value.strip() for value in (
                row.instrument_id, row.instrument_class, row.currency,
                row.maturity, row.denomination, row.valuation_basis)):
            raise IdentityError("issuer claim has incomplete instrument identity")
        if row.side != "issuer_liability":
            raise IdentityError("issuer register contains a non-liability record")
        if registry.sector_of(row.entity_id, row.effective_period) != row.institutional_sector:
            raise IdentityError("issuer entity/sector identity mismatch")
        if registry.sector_of(row.counterparty_entity_id, row.effective_period) != row.counterparty_sector:
            raise IdentityError("issuer holder entity/sector mismatch")
        if (row.issuer_entity_id != row.entity_id
                or row.issuer_sector != row.institutional_sector):
            raise IdentityError("issuer liability must identify its issuer entity")
        values = (row.opening, row.transactions, row.revaluation,
                  row.other_volume, row.closing)
        if any(not isinstance(value, D) or not value.is_finite() for value in values):
            raise IdentityError("issuer claim contains non-finite or non-Decimal values")
        if row.opening < 0 or row.closing < 0:
            raise IdentityError("negative issuer liability")
        if row.opening + row.transactions + row.revaluation + row.other_volume != row.closing:
            raise IdentityError("issuer T/V/O stock-flow identity failed")
        key = claim_key(row)
        if key in issued:
            raise IdentityError(f"duplicate issuer claim record: {key}")
        issued[key] = (
            row.opening, row.transactions, row.revaluation,
            row.other_volume, row.closing,
        )

    if held != issued:
        keys = set(held) | set(issued)
        mismatch = {
            key: {"holder": held.get(key), "issuer": issued.get(key)}
            for key in keys if held.get(key) != issued.get(key)
        }
        raise IdentityError(f"entity-level holder/issuer mirror mismatch: {mismatch}")
    return True


def sector_financial_net_lending(holder_records, registry, period=None):
    """Aggregate transaction flows for exactly one period, never across periods."""
    holder_records = tuple(holder_records)
    periods = {row.effective_period for row in holder_records}
    if period is None:
        if len(periods) > 1:
            raise IdentityError(
                "period is required when financial positions span multiple periods")
        period = next(iter(periods), 0)
    if not isinstance(period, int) or isinstance(period, bool) or period < 0:
        raise IdentityError("period must be a non-negative integer")
    assets, liabilities = {}, {}
    for row in holder_records:
        if row.effective_period != period:
            continue
        holder_sector = registry.sector_of(row.entity_id, row.effective_period)
        issuer_sector = registry.sector_of(row.issuer_entity_id, row.effective_period)
        assets[holder_sector] = assets.get(holder_sector, D("0")) + row.transactions
        liabilities[issuer_sector] = liabilities.get(issuer_sector, D("0")) + row.transactions
    return {
        sector: assets.get(sector, D("0")) - liabilities.get(sector, D("0"))
        for sector in SECTORS
    }


def main():
    registry = EntityRegistry((
        SectorMembership("bank-1", "CB", 0),
        SectorMembership("bank-2", "CB", 0),
        SectorMembership("household-1", "H", 0),
        SectorMembership("household-2", "H", 0),
        SectorMembership("company-1", "NFC", 0),
        SectorMembership("company-2", "NFC", 0),
        SectorMembership("supplier-1", "NFC", 0),
        SectorMembership("central-bank-1", "CBank", 0),
        SectorMembership("government-1", "GOV", 0),
        SectorMembership("row-1", "ROW", 0),
        SectorMembership("migrating-entity", "H", 0, 5),
        SectorMembership("migrating-entity", "NFC", 5),
    ))
    journal = EntityJournal(registry)
    p = 1

    # Bank loan origination creates a new deposit liability and matching asset.
    e1 = JournalEvent("E1", "bank_loan_origination", p, (
        make_line(registry, p, "loan_asset", "D", 19, "bank-1",
                  issuer="company-1", instrument_id="loan-company-1",
                  instrument_class="loan", maturity="2029"),
        make_line(registry, p, "deposit_liability", "C", 19, "bank-1",
                  counterparty="company-1", issuer="bank-1",
                  instrument_id="deposit-company-1",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_asset", "D", 19, "company-1",
                  issuer="bank-1", instrument_id="deposit-company-1",
                  instrument_class="deposit"),
        make_line(registry, p, "loan_liability", "C", 19, "company-1",
                  counterparty="bank-1", issuer="company-1",
                  instrument_id="loan-company-1", instrument_class="loan",
                  maturity="2029"),
    ))
    journal.post(e1)

    # Non-bank credit origination creates a loan claim/liability but no new
    # deposits. The subsequent transfer moves an existing deposit between
    # holders; it changes neither the banking-system deposit total nor its
    # issuer liability stock.
    e2 = JournalEvent("E2", "nonbank_loan_origination", p, (
        make_line(registry, p, "loan_asset", "D", 19, "household-1",
                  issuer="company-2", instrument_id="loan-household-company",
                  instrument_class="loan", maturity="2029"),
        make_line(registry, p, "loan_liability", "C", 19, "company-2",
                  counterparty="household-1", issuer="company-2",
                  instrument_id="loan-household-company",
                  instrument_class="loan", maturity="2029"),
    ))
    e2_transfer = JournalEvent("E2-TRANSFER", "nonbank_deposit_transfer", p, (
        make_line(registry, p, "deposit_asset", "C", 19, "household-1",
                  issuer="bank-1", instrument_id="deposit-household-1",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_liability", "D", 19, "bank-1",
                  counterparty="household-1", issuer="bank-1",
                  instrument_id="deposit-household-1",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_asset", "D", 19, "company-2",
                  issuer="bank-1", instrument_id="deposit-company-2",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_liability", "C", 19, "bank-1",
                  counterparty="company-2", issuer="bank-1",
                  instrument_id="deposit-company-2",
                  instrument_class="deposit"),
    ))
    journal.post(e2)
    journal.post(e2_transfer)
    assert deposit_holder_issuer_deltas(e1)
    assert deposit_holder_issuer_deltas(e2_transfer)

    def deposit_asset_delta(event):
        return sum((line.amount if line.side == "D" else -line.amount)
                   for line in event.lines if line.account == "deposit_asset")

    assert deposit_asset_delta(e1) == D("19")
    assert deposit_asset_delta(e2) == D("0")
    assert deposit_asset_delta(e2_transfer) == D("0")

    # The former mixed event (non-bank loan creation plus deposit transfer)
    # must no longer pass under the deposit-transfer label.
    try:
        EntityJournal(registry).post(JournalEvent(
            "BAD-MIXED-CREDIT-TRANSFER", "nonbank_deposit_transfer", p,
            e2.lines + e2_transfer.lines))
    except IdentityError:
        pass
    else:
        raise AssertionError("non-bank loan origination was hidden inside a deposit transfer")

    # A bank loan origination without the matching new deposit is incomplete.
    try:
        EntityJournal(registry).post(JournalEvent(
            "BAD-BANK-ORIGINATION", "bank_loan_origination", p,
            e1.lines[:2]))
    except IdentityError:
        pass
    else:
        raise AssertionError("bank loan origination without deposit creation accepted")

    # Supplier settlement retains distinct payer and supplier entity IDs.
    e3 = JournalEvent("E3", "supplier_settlement", p, (
        make_line(registry, p, "trade_payable_liability", "D", 7, "company-1",
                  counterparty="supplier-1", issuer="company-1",
                  instrument_id="trade-invoice-7", instrument_class="trade_credit"),
        make_line(registry, p, "deposit_asset", "C", 7, "company-1",
                  issuer="bank-1", instrument_id="deposit-company-1",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_liability", "D", 7, "bank-1",
                  counterparty="company-1", issuer="bank-1",
                  instrument_id="deposit-company-1",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_asset", "D", 7, "supplier-1",
                  issuer="bank-1", instrument_id="deposit-supplier-1",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_liability", "C", 7, "bank-1",
                  counterparty="supplier-1", issuer="bank-1",
                  instrument_id="deposit-supplier-1",
                  instrument_class="deposit"),
        make_line(registry, p, "trade_receivable_asset", "C", 7, "supplier-1",
                  issuer="company-1", instrument_id="trade-invoice-7",
                  instrument_class="trade_credit"),
    ))
    journal.post(e3)

    # Principal repayment changes both the bank asset and borrower liability,
    # while extinguishing the same holder's deposit asset and bank liability.
    principal = JournalEvent("E6", "principal_repayment", p, (
        make_line(registry, p, "loan_liability", "D", 5, "company-1",
                  counterparty="bank-1", issuer="company-1",
                  instrument_id="loan-company-1", instrument_class="loan",
                  maturity="2029"),
        make_line(registry, p, "deposit_asset", "C", 5, "company-1",
                  issuer="bank-1", instrument_id="deposit-company-1",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_liability", "D", 5, "bank-1",
                  counterparty="company-1", issuer="bank-1",
                  instrument_id="deposit-company-1",
                  instrument_class="deposit"),
        make_line(registry, p, "loan_asset", "C", 5, "bank-1",
                  issuer="company-1", instrument_id="loan-company-1",
                  instrument_class="loan", maturity="2029"),
    ))
    journal.post(principal)

    interest_accrual = JournalEvent("E7", "interest_accrual", p, (
        make_line(registry, p, "interest_expense", "D", 2, "company-1"),
        make_line(registry, p, "interest_payable_liability", "C", 2, "company-1",
                  counterparty="bank-1", issuer="company-1",
                  instrument_id="interest-company-1", instrument_class="interest"),
        make_line(registry, p, "interest_receivable_asset", "D", 2, "bank-1",
                  issuer="company-1", instrument_id="interest-company-1",
                  instrument_class="interest"),
        make_line(registry, p, "interest_income", "C", 2, "bank-1"),
    ))
    journal.post(interest_accrual)

    interest_settlement = JournalEvent("E8", "interest_settlement", p, (
        make_line(registry, p, "interest_payable_liability", "D", 2, "company-1",
                  counterparty="bank-1", issuer="company-1",
                  instrument_id="interest-company-1", instrument_class="interest"),
        make_line(registry, p, "deposit_asset", "C", 2, "company-1",
                  issuer="bank-1", instrument_id="deposit-company-1",
                  instrument_class="deposit"),
        make_line(registry, p, "deposit_liability", "D", 2, "bank-1",
                  counterparty="company-1", issuer="bank-1",
                  instrument_id="deposit-company-1",
                  instrument_class="deposit"),
        make_line(registry, p, "interest_receivable_asset", "C", 2, "bank-1",
                  issuer="company-1", instrument_id="interest-company-1",
                  instrument_class="interest"),
    ))
    journal.post(interest_settlement)

    # Creditor write-off and legal forgiveness are deliberately separate events.
    writeoff = JournalEvent("E4", "creditor_writeoff", p, (
        make_line(registry, p, "loss_allowance", "D", 3, "bank-1"),
        make_line(registry, p, "loan_asset", "C", 3, "bank-1",
                  issuer="company-1", instrument_id="loan-defaulted",
                  instrument_class="loan"),
    ))
    journal.post(writeoff)
    forgiveness = JournalEvent("E5", "legal_forgiveness", p, (
        make_line(registry, p, "loan_liability", "D", 3, "company-1",
                  counterparty="bank-1", issuer="company-1",
                  instrument_id="loan-forgiven", instrument_class="loan"),
        make_line(registry, p, "loan_asset", "C", 3, "bank-1",
                  issuer="company-1", instrument_id="loan-forgiven",
                  instrument_class="loan"),
    ))
    journal.post(forgiveness)
    assert not any(line.account == "loan_liability" for line in writeoff.lines)
    assert any(line.account == "loan_liability" for line in forgiveness.lines)

    # The write-off exception is narrow; it cannot be used to bypass
    # entity-level claim mirrors for arbitrary extra postings.
    malformed_writeoff = JournalEvent("BAD-WRITEOFF", "creditor_writeoff", p, (
        make_line(registry, p, "loss_allowance", "D", 3, "bank-1"),
        make_line(registry, p, "loan_asset", "C", 3, "bank-1",
                  issuer="company-1", instrument_id="loan-defaulted",
                  instrument_class="loan"),
        make_line(registry, p, "impairment_expense", "D", 3, "bank-1"),
        make_line(registry, p, "loan_liability", "C", 3, "company-1",
                  counterparty="bank-1", issuer="company-1",
                  instrument_id="loan-defaulted", instrument_class="loan"),
    ))
    try:
        EntityJournal(registry).post(malformed_writeoff)
    except IdentityError:
        pass
    else:
        raise AssertionError("overbroad creditor write-off exception accepted")
    try:
        EntityJournal(registry).post(
            JournalEvent("BAD-EVENT-TYPE", "magic_transfer", p, e1.lines))
    except IdentityError:
        pass
    else:
        raise AssertionError("unknown event type accepted")

    # Sector membership is effective-dated, not retroactively rewritten.
    assert registry.sector_of("migrating-entity", 4) == "H"
    assert registry.sector_of("migrating-entity", 5) == "NFC"
    try:
        validate_journal_line(
            make_line(registry, 4, "ordinary_expense", "D", 1,
                      "migrating-entity"),
            registry, 4)
    except IdentityError:
        raise AssertionError("registry helper should produce the effective sector")
    stale = replace(
        make_line(registry, 4, "ordinary_expense", "D", 1, "migrating-entity"),
        institutional_sector="NFC")
    try:
        validate_journal_line(stale, registry, 4)
    except IdentityError:
        pass
    else:
        raise AssertionError("retrospective sector reassignment accepted")

    # Entity-level claim positions, independently recorded on both sides.
    specs = (
        ("deposit-H", "deposit", "household-1", "bank-1", 100, 7, 107),
        ("deposit-ROW", "deposit", "row-1", "bank-1", 0, 8, 8),
        ("loan-H", "loan", "bank-1", "household-1", 30, 0, 30),
        ("loan-NFC", "loan", "bank-1", "company-1", 80, 19, 99),
        ("reserves-CB", "reserves", "bank-1", "central-bank-1", 30, 0, 30),
        ("cash-H", "cash", "household-1", "central-bank-1", 20, 0, 20),
        ("bond-H", "government_bond", "household-1", "government-1", 10, 0, 10),
        ("bond-CBank", "government_bond", "central-bank-1", "government-1", 40, 0, 40),
        ("bond-ROW", "government_bond", "row-1", "government-1", 0, 15, 15),
        ("external-ROW", "external_reserve_asset", "central-bank-1", "row-1", 10, 0, 10),
    )
    holders = []
    issuers = []
    for instrument_id, instrument_class, holder, issuer, opening, t, closing in specs:
        holders.append(make_claim_position(
            registry, p, "holder_asset", holder, issuer, instrument_id,
            instrument_class, opening, t, closing))
        issuers.append(make_claim_position(
            registry, p, "issuer_liability", holder, issuer, instrument_id,
            instrument_class, opening, t, closing))

    validate_claim_positions(holders, issuers, registry)

    # The same legal instrument must be representable in multiple periods.
    # Period is part of the mirror key; a holder record from period 1 cannot
    # be matched to an issuer liability from period 2.
    period2_holder = make_claim_position(
        registry, 2, "holder_asset", "household-1", "bank-1",
        "deposit-H", "deposit", 107, 3, 110)
    period2_issuer = make_claim_position(
        registry, 2, "issuer_liability", "household-1", "bank-1",
        "deposit-H", "deposit", 107, 3, 110)
    validate_claim_positions(
        holders + [period2_holder], issuers + [period2_issuer], registry)
    try:
        validate_claim_positions([holders[0]], [period2_issuer], registry)
    except IdentityError:
        pass
    else:
        raise AssertionError("holder and issuer positions from different periods matched")

    try:
        sector_financial_net_lending(
            holders + [period2_holder], registry)
    except IdentityError:
        pass
    else:
        raise AssertionError("financial net lending silently aggregated multiple periods")
    period2_nl = sector_financial_net_lending(
        holders + [period2_holder], registry, period=2)
    assert period2_nl == {
        "H": D("3"), "NFC": D("0"), "CB": D("-3"),
        "CBank": D("0"), "GOV": D("0"), "ROW": D("0"),
    }
    assert sector_financial_net_lending(
        (row for row in holders + [period2_holder]), registry, period=2
    ) == period2_nl

    sector_nl = sector_financial_net_lending(holders, registry)
    expected = {
        "H": D("7"), "NFC": D("-19"), "CB": D("4"),
        "CBank": D("0"), "GOV": D("-15"), "ROW": D("23"),
    }
    assert sector_nl == expected, (sector_nl, expected)
    assert sum(sector_nl.values(), D("0")) == 0

    # Same-sector wrong-holder substitution must fail at entity level.
    wrong_holder = list(holders)
    wrong_holder[0] = replace(
        wrong_holder[0], entity_id="household-2",
        counterparty_entity_id="bank-1")
    try:
        validate_claim_positions(wrong_holder, issuers, registry)
    except IdentityError:
        pass
    else:
        raise AssertionError("same-sector wrong holder entity accepted")

    # A wrong issuer entity in the holder claim must not match the original liability.
    wrong_issuer = list(holders)
    wrong_issuer[0] = replace(
        wrong_issuer[0], issuer_entity_id="bank-2",
        counterparty_entity_id="bank-2")
    try:
        validate_claim_positions(wrong_issuer, issuers, registry)
    except IdentityError:
        pass
    else:
        raise AssertionError("wrong issuer entity accepted")

    # Identity dimensions beyond nominal amount must all be mirror-critical.
    for field, value in (
        ("currency", "USD"),
        ("maturity", "2035"),
        ("denomination", "indexed"),
        ("valuation_basis", "market"),
    ):
        changed = list(holders)
        changed[0] = replace(changed[0], **{field: value})
        try:
            validate_claim_positions(changed, issuers, registry)
        except IdentityError:
            pass
        else:
            raise AssertionError(f"holder/issuer mismatch in {field} accepted")

    try:
        validate_claim_positions(holders + [holders[0]], issuers, registry)
    except IdentityError:
        pass
    else:
        raise AssertionError("duplicate holder claim record accepted")
    try:
        validate_claim_positions(holders, issuers[:-1], registry)
    except IdentityError:
        pass
    else:
        raise AssertionError("missing issuer claim record accepted")

    # Same closing stock but a different T/V split must fail on both sides.
    wrong_tvo = list(issuers)
    wrong_tvo[0] = replace(
        wrong_tvo[0], transactions=D("6"), revaluation=D("1"))
    try:
        validate_claim_positions(holders, wrong_tvo, registry)
    except IdentityError:
        pass
    else:
        raise AssertionError("entity-level T/V classification mismatch accepted")
    try:
        validate_claim_positions(holders, issuers + [issuers[0]], registry)
    except IdentityError:
        pass
    else:
        raise AssertionError("duplicate issuer claim record accepted")

    # Blank entity identity and unknown sector labels fail closed even when
    # the other field is populated.
    blank_entity = replace(
        e1.lines[0], entity_id="", institutional_sector="CB")
    try:
        validate_journal_line(blank_entity, registry, p)
    except IdentityError:
        pass
    else:
        raise AssertionError("blank entity ID with populated sector accepted")
    unknown_sector = replace(e1.lines[0], institutional_sector="UNKNOWN")
    try:
        validate_journal_line(unknown_sector, registry, p)
    except IdentityError:
        pass
    else:
        raise AssertionError("unknown institutional-sector code accepted")

    # Same-sector holder mismatch in a balanced deposit journal must fail.
    bad_e2_lines = tuple(
        replace(line, counterparty_entity_id="household-2",
                counterparty_sector="H")
        if line.account == "deposit_liability"
        and line.counterparty_entity_id == "household-1" else line
        for line in e2_transfer.lines
    )
    try:
        EntityJournal(registry).post(
            JournalEvent("BAD-HOLDER", "nonbank_deposit_transfer", p, bad_e2_lines))
    except IdentityError:
        pass
    else:
        raise AssertionError("same-sector wrong deposit holder accepted")

    # Different issuer with the same sector must not match a holder's asset.
    bad_issuer_lines = tuple(
        replace(line, issuer_entity_id="bank-2", issuer_sector="CB")
        if line.account == "deposit_asset" else line
        for line in e1.lines
    )
    try:
        EntityJournal(registry).post(
            JournalEvent("BAD-ISSUER", "bank_loan_origination", p, bad_issuer_lines))
    except IdentityError:
        pass
    else:
        raise AssertionError("wrong deposit issuer entity accepted")

    # A balanced event with a wrong loan instrument ID must fail the
    # entity-level asset/liability mirror even though the journal balances.
    wrong_loan_id_lines = tuple(
        replace(line, instrument_id="loan-company-2")
        if line.account == "loan_liability" else line
        for line in e1.lines
    )
    try:
        EntityJournal(registry).post(
            JournalEvent("BAD-LOAN-ID", "bank_loan_origination", p,
                         wrong_loan_id_lines))
    except IdentityError:
        pass
    else:
        raise AssertionError("wrong loan instrument identity accepted")

    # A globally balanced duplicate asset/liability pair is still a duplicate
    # claim-side posting and must not change a stock twice.
    duplicate_pair = e1.lines + (
        e1.lines[1], e1.lines[2],
    )
    try:
        EntityJournal(registry).post(
            JournalEvent("BAD-DUPLICATE", "bank_loan_origination", p, duplicate_pair))
    except IdentityError:
        pass
    else:
        raise AssertionError("duplicate claim-side posting accepted")

    try:
        EntityJournal(registry).post(e1)
        EntityJournal(registry).post(e1)
    except IdentityError:
        pass
    else:
        raise AssertionError("duplicate event ID accepted")

    try:
        EntityRegistry((
            SectorMembership("bad-sector", "UNKNOWN", 0),
        ))
    except IdentityError:
        pass
    else:
        raise AssertionError("unknown sector code accepted")
    try:
        EntityRegistry((
            SectorMembership("conflict", "H", 0, 10),
            SectorMembership("conflict", "NFC", 5),
        ))
    except IdentityError:
        pass
    else:
        raise AssertionError("overlapping entity-sector memberships accepted")

    print("A2.4.4 entity/sector/issuer identity journal: PASS")
    print("stable entity IDs are distinct from controlled six-sector membership")
    print("all recognized claim assets/liabilities mirror by entity and full instrument identity")
    print("deposit claim mirrors validate holder and issuer entities, not sector labels")
    print("bank loan origination, non-bank loan origination and existing-deposit transfer are distinct event types")
    print("entity-level supplier settlement, principal, interest, write-off and forgiveness events checked")
    print("10 holder claims and 10 issuer liabilities reconcile at entity level")
    print("sector financial NL derived only after claim reconciliation: H=7 NFC=-19 CB=4 CBank=0 GOV=-15 ROW=23")
    print("effective-dated sector changes, write-off versus legal forgiveness and T/V/O stock flow are distinguished")
    print("negative controls: blank/unknown identity, overlapping sectors, wrong holder/issuer/instrument, T/V mismatch, currency/maturity/denomination/valuation, duplicate claims/events rejected")


if __name__ == "__main__":
    main()
