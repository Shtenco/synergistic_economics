"""Unified Economic Balance (UEB) kernel for SYNERGY.

Research-grade accounting primitives. Standard library only.
Money, physical quantities, legal claims and ecological measures are kept
in separate ledgers; a ledger entry is evidence of a recorded assertion,
not proof that a delivery, title or legal event occurred.
"""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Iterable, List, Optional, Tuple

D = Decimal
ZERO = D("0")
CENT = D("0.01")
QTY = D("0.00000001")


class BalanceError(ValueError):
    """Raised when an accounting or stock-flow invariant is violated."""


def money(value) -> D:
    value = D(str(value))
    if not value.is_finite():
        raise BalanceError("money must be finite")
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def quantity(value) -> D:
    value = D(str(value))
    if not value.is_finite():
        raise BalanceError("quantity must be finite")
    return value.quantize(QTY, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Account:
    account_id: str
    owner: str
    kind: str  # asset, liability, equity, income, expense
    currency: str = "UNIT"


@dataclass(frozen=True)
class Posting:
    account_id: str
    debit: D = ZERO
    credit: D = ZERO


@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    description: str
    postings: Tuple[Posting, ...]


class DoubleEntryLedger:
    """Append-only, balanced journal with idempotent entry identifiers."""

    def __init__(self):
        self.accounts: Dict[str, Account] = {}
        self.entries: List[JournalEntry] = []
        self._entry_ids = set()
        self.balances: Dict[str, D] = {}

    def add_account(self, account: Account):
        if not account.account_id or account.account_id in self.accounts:
            raise BalanceError("account id must be non-empty and unique")
        if account.kind not in {"asset", "liability", "equity", "income", "expense"}:
            raise BalanceError("unsupported account kind")
        self.accounts[account.account_id] = account
        self.balances[account.account_id] = ZERO

    def post(self, entry: JournalEntry):
        if not entry.entry_id or entry.entry_id in self._entry_ids:
            raise BalanceError("duplicate or empty journal entry id")
        if len(entry.postings) < 2:
            raise BalanceError("journal entry needs at least two postings")
        total_debit = ZERO
        total_credit = ZERO
        currencies = set()
        for line in entry.postings:
            if line.account_id not in self.accounts:
                raise BalanceError(f"unknown account: {line.account_id}")
            currencies.add(self.accounts[line.account_id].currency)
            debit, credit = D(str(line.debit)), D(str(line.credit))
            if not debit.is_finite() or not credit.is_finite() or debit < 0 or credit < 0:
                raise BalanceError("posting amounts must be finite and non-negative")
            if debit and credit:
                raise BalanceError("one posting cannot contain both debit and credit")
            total_debit += debit
            total_credit += credit
        if len(currencies) != 1:
            raise BalanceError("a journal entry cannot mix currencies; use explicit FX clearing legs")
        if total_debit != total_credit:
            raise BalanceError("journal entry is not balanced")
        # Apply only after every validation passes.
        for line in entry.postings:
            account = self.accounts[line.account_id]
            # Debit-positive convention for assets/expenses; credit-positive
            # convention for liabilities/equity/income.
            sign = D("1") if account.kind in {"asset", "expense"} else D("-1")
            self.balances[line.account_id] += sign * (line.debit - line.credit)
        self.entries.append(entry)
        self._entry_ids.add(entry.entry_id)

    def balance(self, account_id: str) -> D:
        return self.balances[account_id]

    def trial_balance(self) -> D:
        """Convert normal balances back to debit-positive signed balances."""
        total = ZERO
        for account_id, balance in self.balances.items():
            kind = self.accounts[account_id].kind
            total += balance if kind in {"asset", "expense"} else -balance
        return total


@dataclass(frozen=True)
class PhysicalFlow:
    flow_id: str
    product_id: str
    source: str
    destination: str
    amount: D
    unit: str
    evidence_id: Optional[str] = None


@dataclass
class PhysicalStock:
    product_id: str
    unit: str
    opening: D
    inflows: D = ZERO
    outflows: D = ZERO
    closing: Optional[D] = None

    def reconcile(self) -> D:
        values = (self.opening, self.inflows, self.outflows)
        if any(not D(str(v)).is_finite() or D(str(v)) < 0 for v in values):
            raise BalanceError("physical stocks and flows must be finite and non-negative")
        expected = quantity(self.opening + self.inflows - self.outflows)
        if expected < 0:
            raise BalanceError("physical outflows exceed available stock")
        if self.closing is not None and quantity(self.closing) != expected:
            raise BalanceError(f"physical stock mismatch for {self.product_id}")
        self.closing = expected
        return expected


@dataclass(frozen=True)
class Claim:
    """One side of a bilateral financial claim, not a physical asset."""
    instrument_id: str
    creditor: str
    debtor: str
    amount: D
    claim_type: str = "loan"


def validate_claim_pairs(claims: Iterable[Claim]) -> Dict[str, D]:
    """Require exactly one positive, equal claim and obligation per instrument.

    Claims are entered once as creditor->debtor instruments. The returned
    map is the matched amount by instrument; consolidation eliminates both
    sides rather than treating the claim as additional system wealth.
    """
    grouped: Dict[str, List[Claim]] = {}
    claims = list(claims)
    for claim in claims:
        if not claim.instrument_id or not claim.creditor or not claim.debtor:
            raise BalanceError("claim parties and instrument id are required")
        amount = D(str(claim.amount))
        if not amount.is_finite() or amount <= 0 or claim.creditor == claim.debtor:
            raise BalanceError("claim amount must be positive and parties distinct")
        grouped.setdefault(claim.instrument_id, []).append(claim)
    result = {}
    for instrument_id, rows in grouped.items():
        if len(rows) != 1:
            raise BalanceError(f"duplicate instrument representation: {instrument_id}")
        result[instrument_id] = rows[0].amount
    return result


def consolidated_internal_claims(claims: Iterable[Claim], members: Iterable[str]) -> D:
    """Return zero for matched internal claims; external claims remain visible.

    The total internal claim and matching liability cancel on consolidation.
    This function reports the eliminated gross amount, not net wealth.
    """
    member_set = set(members)
    claims = list(claims)
    pairs = validate_claim_pairs(claims)
    return sum((amount for instrument_id, amount in pairs.items()
                if any(c.instrument_id == instrument_id and c.creditor in member_set
                       and c.debtor in member_set for c in claims)), ZERO)


def loan_origination(ledger: DoubleEntryLedger, *, lender_cash: str,
                     lender_receivable: str, borrower_cash: str,
                     borrower_payable: str, amount, entry_prefix: str):
    """Record both counterparties. Principal creates matched claims, not income."""
    amount = money(amount)
    if amount <= 0:
        raise BalanceError("loan principal must be positive")
    account_ids = (lender_cash, lender_receivable, borrower_cash, borrower_payable)
    if any(account_id not in ledger.accounts for account_id in account_ids):
        raise BalanceError("loan references an unknown account")
    lender_cash_account = ledger.accounts[lender_cash]
    lender_receivable_account = ledger.accounts[lender_receivable]
    borrower_cash_account = ledger.accounts[borrower_cash]
    borrower_payable_account = ledger.accounts[borrower_payable]
    if (lender_cash_account.owner != lender_receivable_account.owner
            or borrower_cash_account.owner != borrower_payable_account.owner
            or lender_cash_account.owner == borrower_cash_account.owner):
        raise BalanceError("loan accounts must belong to distinct lender and borrower entities")
    if (lender_cash_account.kind != "asset" or lender_receivable_account.kind != "asset"
            or borrower_cash_account.kind != "asset" or borrower_payable_account.kind != "liability"):
        raise BalanceError("loan requires lender cash/receivable assets and borrower cash/liability accounts")
    if len({a.currency for a in (lender_cash_account, lender_receivable_account,
                                  borrower_cash_account, borrower_payable_account)}) != 1:
        raise BalanceError("loan accounts must use one currency; model FX separately")
    ledger.post(JournalEntry(
        f"{entry_prefix}-L", "Loan disbursement — lender",
        (Posting(lender_receivable, debit=amount), Posting(lender_cash, credit=amount))))
    ledger.post(JournalEntry(
        f"{entry_prefix}-B", "Loan proceeds and liability — borrower",
        (Posting(borrower_cash, debit=amount), Posting(borrower_payable, credit=amount))))


def net_worth(assets, liabilities) -> D:
    """Net worth is assets less liabilities; token face value is not added twice."""
    a, l = money(assets), money(liabilities)
    if a < 0 or l < 0:
        raise BalanceError("assets and liabilities must be non-negative")
    return a - l


@dataclass
class StockFlow:
    """Generic opening stock + recognized flows = closing stock."""
    opening: D
    additions: D = ZERO
    reductions: D = ZERO
    closing: Optional[D] = None

    def reconcile(self) -> D:
        vals = (self.opening, self.additions, self.reductions)
        if any(not D(str(v)).is_finite() or D(str(v)) < 0 for v in vals):
            raise BalanceError("stock-flow values must be finite and non-negative")
        expected = money(self.opening + self.additions - self.reductions)
        if expected < 0:
            raise BalanceError("reductions exceed available stock")
        if self.closing is not None and money(self.closing) != expected:
            raise BalanceError("stock-flow identity failed")
        self.closing = expected
        return expected


def value_added(output_value, intermediate_consumption) -> D:
    """Gross value added; neither sales turnover nor profit nor cash creation."""
    output_value = money(output_value)
    intermediate_consumption = money(intermediate_consumption)
    if output_value < 0 or intermediate_consumption < 0:
        raise BalanceError("values must be non-negative")
    return output_value - intermediate_consumption


def token_issue_as_liability(ledger: DoubleEntryLedger, *, cash_account: str,
                             token_liability_account: str, amount, entry_id: str):
    """Issue a redeemable/payment token against cash: liability, not income."""
    amount = money(amount)
    if amount <= 0:
        raise BalanceError("issuance amount must be positive")
    if cash_account not in ledger.accounts or token_liability_account not in ledger.accounts:
        raise BalanceError("token issuance references an unknown account")
    cash = ledger.accounts[cash_account]
    liability = ledger.accounts[token_liability_account]
    if cash.kind != "asset" or liability.kind != "liability" or cash.owner != liability.owner:
        raise BalanceError("token issuance requires issuer-owned cash asset and token liability")
    if cash.currency != liability.currency:
        raise BalanceError("token backing and liability must use the same currency")
    ledger.post(JournalEntry(
        entry_id, "Token issuance against received cash",
        (Posting(cash_account, debit=amount),
         Posting(token_liability_account, credit=amount))))
