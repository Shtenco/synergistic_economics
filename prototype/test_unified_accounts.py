import unittest
from decimal import Decimal as D

from unified_accounts import (
    Account, BalanceError, Claim, DoubleEntryLedger, JournalEntry, Posting,
    PhysicalStock, StockFlow, bank_loan_origination,
    bank_loan_principal_repayment, consolidated_internal_claims,
    loan_origination, money, net_worth, token_issue_as_liability, value_added,
)


def ledger_with_accounts():
    ledger = DoubleEntryLedger()
    for account in [
        Account("cash:lender", "lender", "asset"),
        Account("loan:lender", "lender", "asset"),
        Account("equity:lender", "lender", "equity"),
        Account("cash:borrower", "borrower", "asset"),
        Account("debt:borrower", "borrower", "liability"),
        Account("income:borrower", "borrower", "income"),
        Account("token:issuer", "issuer", "liability"),
        Account("cash:issuer", "issuer", "asset"),
    ]:
        ledger.add_account(account)
    ledger.post(JournalEntry("open-lender", "opening", (
        Posting("cash:lender", debit=money(100)),
        Posting("equity:lender", credit=money(100)),
    )))
    return ledger


class UnifiedBalanceTests(unittest.TestCase):
    def test_journal_requires_equal_debits_and_credits(self):
        ledger = ledger_with_accounts()
        with self.assertRaises(BalanceError):
            ledger.post(JournalEntry("bad", "unbalanced", (
                Posting("cash:borrower", debit=money(10)),
                Posting("debt:borrower", credit=money(9)),
            )))
        self.assertEqual(len(ledger.entries), 1)

    def test_journal_rejects_mixed_currencies(self):
        ledger = DoubleEntryLedger()
        ledger.add_account(Account("cash-usd", "a", "asset", "USD"))
        ledger.add_account(Account("cash-eur", "b", "asset", "EUR"))
        with self.assertRaises(BalanceError):
            ledger.post(JournalEntry("fx-implicit", "invalid implicit FX", (
                Posting("cash-usd", debit=money(10)),
                Posting("cash-eur", credit=money(10)),
            )))

    def test_loan_rejects_wrong_account_roles(self):
        ledger = ledger_with_accounts()
        with self.assertRaises(BalanceError):
            loan_origination(ledger, lender_cash="cash:lender",
                             lender_receivable="loan:lender",
                             borrower_cash="cash:borrower",
                             borrower_payable="income:borrower",
                             amount=10, entry_prefix="bad-loan")

    def test_loan_principal_is_not_income_and_does_not_create_net_worth(self):
        ledger = ledger_with_accounts()
        loan_origination(ledger, lender_cash="cash:lender",
                         lender_receivable="loan:lender",
                         borrower_cash="cash:borrower",
                         borrower_payable="debt:borrower",
                         amount=50, entry_prefix="loan-1")
        self.assertEqual(ledger.balance("cash:borrower"), D("50.00"))
        self.assertEqual(ledger.balance("debt:borrower"), D("50.00"))
        self.assertEqual(ledger.balance("income:borrower"), D("0"))
        self.assertEqual(net_worth(50, 50), D("0.00"))
        self.assertEqual(ledger.trial_balance(), D("0.00"))

    def test_token_issuance_is_liability_not_income(self):
        ledger = ledger_with_accounts()
        token_issue_as_liability(ledger, cash_account="cash:issuer",
                                 token_liability_account="token:issuer",
                                 amount=25, entry_id="token-1")
        self.assertEqual(ledger.balance("cash:issuer"), D("25.00"))
        self.assertEqual(ledger.balance("token:issuer"), D("25.00"))
        self.assertEqual(ledger.balance("income:borrower"), D("0"))
        self.assertEqual(ledger.trial_balance(), D("0.00"))

    def test_internal_claims_are_eliminated_on_consolidation(self):
        claims = [Claim("loan-7", "cell-a", "cell-b", D("80"))]
        self.assertEqual(consolidated_internal_claims(claims, {"cell-a", "cell-b"}), D("80"))
        self.assertEqual(consolidated_internal_claims(claims, {"cell-a"}), D("0"))

    def test_duplicate_claim_instrument_is_rejected(self):
        claims = [
            Claim("loan-7", "cell-a", "cell-b", D("80")),
            Claim("loan-7", "cell-a", "cell-b", D("80")),
        ]
        with self.assertRaises(BalanceError):
            consolidated_internal_claims(claims, {"cell-a", "cell-b"})

    def test_physical_stock_reconciles_independently_of_money(self):
        stock = PhysicalStock("grain", "tonne", D("10"), D("5"), D("12"))
        self.assertEqual(stock.reconcile(), D("3.00000000"))
        with self.assertRaises(BalanceError):
            PhysicalStock("grain", "tonne", D("10"), D("5"), D("12"), D("4")).reconcile()

    def test_stock_flow_identity(self):
        account = StockFlow(D("100"), D("25"), D("40"))
        self.assertEqual(account.reconcile(), D("85.00"))
        with self.assertRaises(BalanceError):
            StockFlow(D("100"), D("25"), D("40"), D("90")).reconcile()

    def test_value_added_is_not_turnover(self):
        self.assertEqual(value_added("150", "90"), D("60.00"))

    def test_no_negative_stock_or_nonfinite_values(self):
        with self.assertRaises(BalanceError):
            PhysicalStock("energy", "MWh", D("1"), D("0"), D("2")).reconcile()
        with self.assertRaises(BalanceError):
            money("NaN")


    def test_cash_funded_loan_cannot_overdraw_lender(self):
        ledger = ledger_with_accounts()
        before_entries = len(ledger.entries)
        with self.assertRaisesRegex(BalanceError, "lender cash balance is insufficient"):
            loan_origination(ledger, lender_cash="cash:lender",
                             lender_receivable="loan:lender",
                             borrower_cash="cash:borrower",
                             borrower_payable="debt:borrower",
                             amount=101, entry_prefix="overdraw")
        self.assertEqual(len(ledger.entries), before_entries)
        self.assertEqual(ledger.balance("cash:lender"), D("100.00"))
        self.assertEqual(ledger.balance("loan:lender"), D("0"))
        self.assertEqual(ledger.balance("cash:borrower"), D("0"))
        self.assertEqual(ledger.balance("debt:borrower"), D("0"))

    def test_cash_funded_loan_preflights_both_entry_ids_before_mutation(self):
        ledger = ledger_with_accounts()
        ledger.post(JournalEntry("atomic-B", "pre-existing ID", (
            Posting("cash:borrower", debit=money(1)),
            Posting("debt:borrower", credit=money(1)),
        )))
        before_entries = len(ledger.entries)
        with self.assertRaisesRegex(BalanceError, "entry IDs"):
            loan_origination(ledger, lender_cash="cash:lender",
                             lender_receivable="loan:lender",
                             borrower_cash="cash:borrower",
                             borrower_payable="debt:borrower",
                             amount=10, entry_prefix="atomic")
        self.assertEqual(len(ledger.entries), before_entries)
        self.assertEqual(ledger.balance("cash:lender"), D("100.00"))
        self.assertEqual(ledger.balance("loan:lender"), D("0"))
        self.assertEqual(ledger.balance("cash:borrower"), D("1.00"))
        self.assertEqual(ledger.balance("debt:borrower"), D("1.00"))

    def test_bank_loan_origination_creates_matching_deposit_and_debt(self):
        ledger = DoubleEntryLedger()
        for account in (
            Account("bank:loan", "bank", "asset"),
            Account("bank:deposits", "bank", "liability"),
            Account("borrower:deposit", "borrower", "asset"),
            Account("borrower:loan", "borrower", "liability"),
        ):
            ledger.add_account(account)
        bank_loan_origination(
            ledger, bank_loan_receivable="bank:loan",
            bank_deposit_liability="bank:deposits",
            borrower_deposit_asset="borrower:deposit",
            borrower_loan_payable="borrower:loan",
            amount=100, entry_id="bank-loan-1",
        )
        self.assertEqual(ledger.balance("bank:loan"), D("100.00"))
        self.assertEqual(ledger.balance("bank:deposits"), D("100.00"))
        self.assertEqual(ledger.balance("borrower:deposit"), D("100.00"))
        self.assertEqual(ledger.balance("borrower:loan"), D("100.00"))
        self.assertEqual(ledger.trial_balance(), D("0.00"))
        self.assertEqual(len(ledger.entries), 1)

    def test_bank_loan_principal_repayment_destroys_matching_deposit(self):
        ledger = DoubleEntryLedger()
        for account in (
            Account("bank:loan", "bank", "asset"),
            Account("bank:deposits", "bank", "liability"),
            Account("borrower:deposit", "borrower", "asset"),
            Account("borrower:loan", "borrower", "liability"),
        ):
            ledger.add_account(account)
        bank_loan_origination(
            ledger, bank_loan_receivable="bank:loan",
            bank_deposit_liability="bank:deposits",
            borrower_deposit_asset="borrower:deposit",
            borrower_loan_payable="borrower:loan",
            amount=100, entry_id="bank-loan-2",
        )
        bank_loan_principal_repayment(
            ledger, bank_loan_receivable="bank:loan",
            bank_deposit_liability="bank:deposits",
            borrower_deposit_asset="borrower:deposit",
            borrower_loan_payable="borrower:loan",
            amount=35, entry_id="bank-repay-1",
        )
        for account_id in ("bank:loan", "bank:deposits",
                           "borrower:deposit", "borrower:loan"):
            self.assertEqual(ledger.balance(account_id), D("65.00"))
        self.assertEqual(ledger.trial_balance(), D("0.00"))

    def test_bank_loan_repayment_cannot_overdraw_deposit_or_partially_post(self):
        ledger = DoubleEntryLedger()
        for account in (
            Account("bank:loan", "bank", "asset"),
            Account("bank:deposits", "bank", "liability"),
            Account("borrower:deposit", "borrower", "asset"),
            Account("borrower:loan", "borrower", "liability"),
        ):
            ledger.add_account(account)
        bank_loan_origination(
            ledger, bank_loan_receivable="bank:loan",
            bank_deposit_liability="bank:deposits",
            borrower_deposit_asset="borrower:deposit",
            borrower_loan_payable="borrower:loan",
            amount=100, entry_id="bank-loan-3",
        )
        before_entries = len(ledger.entries)
        with self.assertRaisesRegex(BalanceError, "borrower deposit balance"):
            bank_loan_principal_repayment(
                ledger, bank_loan_receivable="bank:loan",
                bank_deposit_liability="bank:deposits",
                borrower_deposit_asset="borrower:deposit",
                borrower_loan_payable="borrower:loan",
                amount=101, entry_id="bank-repay-too-much",
            )
        self.assertEqual(len(ledger.entries), before_entries)
        for account_id in ("bank:loan", "bank:deposits",
                           "borrower:deposit", "borrower:loan"):
            self.assertEqual(ledger.balance(account_id), D("100.00"))
        self.assertEqual(ledger.trial_balance(), D("0.00"))


if __name__ == "__main__":
    unittest.main()
