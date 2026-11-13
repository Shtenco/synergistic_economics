"""Adversarial tests for common-stream multi-period SFC/GOLD reconciliation."""
import unittest
from decimal import Decimal as D
from economic_stock_flow_reconciliation import (PositionIdentity,OpeningPosition,Movement,
    ClosingPosition,reconcile_periods,StockFlowError,movements_from_event_groups)


def pos(position_id,register="financial",holder="BANK",issuer="BORROWER",unit="LCU",currency="LCU",basis="NOMINAL"):
    return PositionIdentity(register,position_id,"monetary",unit,currency,basis,holder,issuer,position_id)


class StockFlowReconciliationTests(unittest.TestCase):
    def test_multi_period_gold_t_v_o_and_opening_carry_forward(self):
        asset=pos("LOAN-1",holder="BANK",issuer="BORROWER")
        liability=pos("LOAN-1",holder="BORROWER",issuer="BANK")
        openings=(OpeningPosition(asset,1,D("0"),"OPEN-1"),OpeningPosition(asset,2,D("80"),"OPEN-2"),
                  OpeningPosition(liability,1,D("0"),"OPEN-1"),OpeningPosition(liability,2,D("80"),"OPEN-2"))
        movements=(Movement("A-T1","TX-1",asset,1,"T",D("100"),"LOAN-ORIGINATION"),
                   Movement("A-T2","TX-2",asset,1,"T",D("-20"),"REPAYMENT"),
                   Movement("A-V1","TX-3",asset,2,"V",D("-5"),"IMPAIRMENT"),
                   Movement("A-O1","TX-4",asset,2,"O",D("-10"),"WRITEOFF"),
                   Movement("L-T1","TX-1",liability,1,"T",D("100"),"LOAN-ORIGINATION"),
                   Movement("L-T2","TX-2",liability,1,"T",D("-20"),"REPAYMENT"),
                   Movement("L-V1","TX-3",liability,2,"V",D("0"),"NO-LIABILITY-REVALUATION"),
                   Movement("L-O1","TX-4",liability,2,"O",D("0"),"WRITE-OFF-NOT-FORGIVEN"))
        closings=(ClosingPosition(asset,1,D("80"),"CLOSE-1"),ClosingPosition(asset,2,D("65"),"CLOSE-2"),
                  ClosingPosition(liability,1,D("80"),"CLOSE-1"),ClosingPosition(liability,2,D("80"),"CLOSE-2"))
        result=reconcile_periods(openings,movements,closings)
        self.assertEqual(result.event_count,8)
        self.assertEqual(result.periods[1].closing,D("65"))
        self.assertEqual(result.periods[3].closing,D("80"))

    def test_mirror_controls(self):
        sender=pos("STEEL",register="physical",holder="MINE",issuer="MILL",unit="t",currency="NA",basis="PHYSICAL")
        receiver=pos("STEEL",register="physical",holder="MILL",issuer="MINE",unit="t",currency="NA",basis="PHYSICAL")
        openings=(OpeningPosition(sender,1,D("0"),"O1"),OpeningPosition(receiver,1,D("0"),"O1"))
        movements=(Movement("OUT","TX-1",sender,1,"T",D("-5"),"SCALE-1",mirror_group_id="FLOW-1",mirror_side="sender",mirror_policy="opposite"),
                   Movement("IN","TX-1",receiver,1,"T",D("5"),"SCALE-1",mirror_group_id="FLOW-1",mirror_side="receiver",mirror_policy="opposite"))
        closings=(ClosingPosition(sender,1,D("-5"),"C1"),ClosingPosition(receiver,1,D("5"),"C1"))
        self.assertEqual(reconcile_periods(openings,movements,closings).mirror_group_count,1)

    def test_canonical_six_register_event_group_maps_to_stock_flow_movements(self):
        common="TX-GROUP-1"
        identity_asset={"register_id":"financial","position_id":"BANK-LOAN-1","measure":"monetary",
            "unit":"LCU","currency":"LCU","valuation_basis":"NOMINAL","holder_id":"BANK",
            "issuer_id":"BORROWER","instrument_id":"LOAN-1"}
        identity_liability={**identity_asset,"position_id":"BORROWER-LOAN-1","holder_id":"BORROWER","issuer_id":"BANK"}
        events=[]
        for register in ("physical","capital","labour","product","legal_rights","financial"):
            payload={"no_stock_flow_effect":"event has no stock or valuation consequence"}
            if register=="financial":
                payload={"stock_flow_movements":[
                    {"movement_id":"M-ASSET","identity":identity_asset,"period_index":1,
                     "movement_class":"T","amount":"100","evidence_ref":"LOAN-ORIGINATION",
                     "mirror_group_id":"LOAN-ORIGINATION","mirror_side":"holder","mirror_policy":"equal"},
                    {"movement_id":"M-LIABILITY","identity":identity_liability,"period_index":1,
                     "movement_class":"T","amount":"100","evidence_ref":"LOAN-ORIGINATION",
                     "mirror_group_id":"LOAN-ORIGINATION","mirror_side":"issuer","mirror_policy":"equal"}]}
            events.append({"register_id":register,"common_event_id":common,"native_event_id":f"E-{register}",
                "aggregate_version":1,"payload":payload})
        group={"schema_version":1,"transaction_id":common,"common_event_id":common,"events":tuple(events)}
        movements=movements_from_event_groups((group,))
        self.assertEqual(len(movements),2)
        asset=PositionIdentity(**identity_asset); liability=PositionIdentity(**identity_liability)
        openings=(OpeningPosition(asset,1,D("0"),"O-A"),OpeningPosition(liability,1,D("0"),"O-L"))
        closings=(ClosingPosition(asset,1,D("100"),"C-A"),ClosingPosition(liability,1,D("100"),"C-L"))
        result=reconcile_periods(openings,movements,closings)
        self.assertEqual(result.mirror_group_count,1)
        broken={**group,"events":tuple(events[:-1])}
        with self.assertRaises(StockFlowError): movements_from_event_groups((broken,))

    def test_rejects_unit_mixing_and_cross_period_mismatch(self):
        kg=pos("MASS",register="physical",unit="kg",currency="NA",basis="PHYSICAL")
        tonnes=pos("MASS",register="physical",unit="t",currency="NA",basis="PHYSICAL")
        openings=(OpeningPosition(kg,1,D("0"),"O"),)
        closings=(ClosingPosition(kg,1,D("1"),"C"),)
        movement=(Movement("E1","TX",tonnes,1,"T",D("1"),"E"),)
        with self.assertRaises(StockFlowError): reconcile_periods(openings,movement,closings)
        openings=(OpeningPosition(kg,1,D("0"),"O1"),OpeningPosition(kg,2,D("2"),"O2"))
        closings=(ClosingPosition(kg,1,D("1"),"C1"),ClosingPosition(kg,2,D("3"),"C2"))
        moves=(Movement("E1","TX1",kg,1,"T",D("1"),"E1"),Movement("E2","TX2",kg,2,"T",D("1"),"E2"))
        with self.assertRaises(StockFlowError): reconcile_periods(openings,moves,closings)

    def test_rejects_unbalanced_mirror_and_duplicate_events(self):
        a=pos("X",holder="A",issuer="B"); b=pos("X",holder="B",issuer="A")
        openings=(OpeningPosition(a,1,D("0"),"O"),OpeningPosition(b,1,D("0"),"O"))
        movements=(Movement("E1","TX",a,1,"T",D("10"),"E",mirror_group_id="M",mirror_side="holder",mirror_policy="equal"),
                   Movement("E2","TX",b,1,"T",D("9"),"E",mirror_group_id="M",mirror_side="issuer",mirror_policy="equal"))
        closings=(ClosingPosition(a,1,D("10"),"C"),ClosingPosition(b,1,D("9"),"C"))
        with self.assertRaises(StockFlowError): reconcile_periods(openings,movements,closings)
        duplicate=(movements[0],movements[0])
        with self.assertRaises(StockFlowError): reconcile_periods(openings,duplicate,closings)


if __name__=="__main__": unittest.main(verbosity=2)
