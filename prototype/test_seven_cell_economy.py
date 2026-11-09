import unittest
from decimal import Decimal as D
from seven_cell_economy import EconomyError, Entry, Line, SevenCellEconomy, run_scenario

class SevenCellTests(unittest.TestCase):
    def test_exactly_seven_unique_cells_required(self):
        with self.assertRaises(EconomyError): SevenCellEconomy(SevenCellEconomy.default_configs()[:-1])
    def test_baseline_24_periods_conserves_cash_and_balances_ledger(self):
        e=SevenCellEconomy(); initial=e.initial_system_cash; e.run(24)
        self.assertEqual(e.results[-1].system_cash,initial); self.assertEqual(e.results[-1].insolvent_cells,0)
        self.assertGreater(e.results[-1].non_energy_output,0); self.assertGreaterEqual(e.resource,0)
        e.ledger.assert_balanced()
    def test_scenario_is_deterministic(self):
        a=run_scenario("baseline"); b=run_scenario("baseline")
        self.assertEqual(a["summary"],b["summary"]); self.assertEqual(a["periods"],b["periods"])
    def test_demand_shock_reduces_non_energy_output_and_final_expenditure(self):
        a=run_scenario("baseline")["summary"]; b=run_scenario("demand_collapse")["summary"]
        self.assertLess(D(b["cumulative_non_energy_output_index"]),D(a["cumulative_non_energy_output_index"]))
        self.assertLess(D(b["cumulative_final_household_expenditure"]),D(a["cumulative_final_household_expenditure"]))
    def test_energy_shock_reduces_non_energy_output(self):
        a=run_scenario("baseline")["summary"]; b=run_scenario("energy_shock")["summary"]
        self.assertLess(D(b["cumulative_non_energy_output_index"]),D(a["cumulative_non_energy_output_index"]))
    def test_resource_shock_changes_output_and_preserves_resource_stock(self):
        a=run_scenario("baseline")["summary"]; b=run_scenario("resource_shock")["summary"]
        self.assertNotEqual(a["cumulative_non_energy_output_index"],b["cumulative_non_energy_output_index"])
        self.assertGreaterEqual(D(b["ending_resource_stock"]),0)
    def test_compound_crisis_conserves_cash(self):
        s=run_scenario("compound_crisis")["summary"]
        self.assertEqual(D(s["system_cash_conservation_error"]),0)
    def test_bilateral_credit_and_exact_creditor_repayment(self):
        e=SevenCellEconomy(); seller=e.cells["cell-3"]; buyer=e.cells["cell-1"]
        seller.inventory=D("10"); buyer.cash=D("0")
        q=e._trade(seller,buyer,D("10"),1)
        self.assertGreater(q,0); self.assertEqual(seller.receivables,buyer.payables)
        self.assertEqual(e.positions[("cell-1","cell-3")],buyer.payables)
        buyer.cash=D("5"); e._repay(2)
        self.assertEqual(buyer.payables,seller.receivables); self.assertEqual(e.positions[("cell-1","cell-3")],buyer.payables)
        e.ledger.assert_balanced()
    def test_credit_limit_uses_remaining_borrower_capacity(self):
        e=SevenCellEconomy(); seller=e.cells["cell-3"]; buyer=e.cells["cell-1"]
        seller.inventory=D("10"); buyer.cash=D("0"); buyer.payables=buyer.cfg.credit_limit*D(".8")
        self.assertEqual(e._trade(seller,buyer,D("10"),1),0)
    def test_default_trigger_requires_arrears_and_high_leverage(self):
        e=SevenCellEconomy(); debtor=e.cells["cell-1"]; creditor=e.cells["cell-2"]
        debtor.payables=D("30"); debtor.arrears=2; creditor.receivables=D("30"); e.positions[("cell-1","cell-2")]=D("30")
        e.ledger.post(Entry("test:credit","opening test credit",(Line("receivable:cell-2",debit=D("30")),Line("payable:cell-1",credit=D("30")))))
        e._assess_defaults(1); self.assertTrue(debtor.insolvent); self.assertEqual(debtor.defaults,D("30"))
    def test_internal_energy_sales_are_separate_from_final_household_spending(self):
        s=run_scenario("baseline")["summary"]
        self.assertGreater(D(s["cumulative_internal_intermediate_sales"]),0)
        self.assertGreater(D(s["cumulative_final_household_expenditure"]),D(s["cumulative_internal_intermediate_sales"]))
    def test_all_journal_entries_balance(self):
        e=SevenCellEconomy(); e.run(24); e.ledger.assert_balanced(); self.assertGreater(len(e.ledger.entries),100)

if __name__=="__main__": unittest.main(verbosity=2)
