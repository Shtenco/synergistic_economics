import unittest
from decimal import Decimal
from synergy_kernel import *

class KernelTests(unittest.TestCase):
    def test_balanced_transfer_preserves_total_cash(self):
        k=SynergyKernel()
        k.ledger.add_account("equity:cell_a"); k.ledger.add_account("equity:cell_b")
        k.ledger.post(JournalEntry("OA","UNIT","open a",(JournalLine("cash:cell_a",debit=money(100)),JournalLine("equity:cell_a",credit=money(100)))))
        k.ledger.post(JournalEntry("OB","UNIT","open b",(JournalLine("cash:cell_b",debit=money(25)),JournalLine("equity:cell_b",credit=money(25)))))
        before=k.ledger.balance("cash:cell_a")+k.ledger.balance("cash:cell_b")
        k.transfer_cash("cell_a","cell_b","12.50",idempotency_key="t-1")
        after=k.ledger.balance("cash:cell_a")+k.ledger.balance("cash:cell_b")
        self.assertEqual(before,after)
        self.assertEqual(k.ledger.balance("cash:cell_a"),Decimal("87.50"))
        self.assertEqual(k.ledger.balance("cash:cell_b"),Decimal("37.50"))
    def test_unbalanced_journal_rejected_without_posting(self):
        ledger=DoubleEntryLedger({"cash","equity"})
        bad=JournalEntry("BAD","UNIT","bad",(JournalLine("cash",debit=Decimal(10)),JournalLine("equity",credit=Decimal(9))))
        with self.assertRaises(KernelError): ledger.post(bad)
        self.assertEqual(ledger.entries,[])
    def test_duplicate_event_key_rejected(self):
        events=EventStore(); events.append("E1","created",{"x":1},"key-1")
        with self.assertRaises(KernelError): events.append("E2","again",{},"key-1")
    def test_production_bounded_by_materials(self):
        f=Firm("f",Decimal(10),Decimal(2),Decimal(8),Decimal(1),Decimal(100),Decimal(1),Decimal(50))
        self.assertEqual(f.produce(100),Decimal(8))
        self.assertEqual(f.materials,Decimal(0))
    def test_shipment_cannot_exceed_inventory(self):
        f=Firm("f",Decimal(2),Decimal(2),Decimal(10),Decimal(1),Decimal(10),Decimal(1),Decimal(10))
        f.produce(2)
        with self.assertRaises(KernelError): f.ship(3)
    def test_allocation_balances_exactly(self):
        out=allocate_pool("100.00",{"a":2,"b":1,"c":1})
        self.assertEqual(sum(out.values()),Decimal("100.00"))
        self.assertEqual(out["a"],Decimal("50.00"))
    def test_negative_pool_rejected(self):
        with self.assertRaises(KernelError): allocate_pool(-1,{"a":1})

if __name__ == "__main__": unittest.main()
