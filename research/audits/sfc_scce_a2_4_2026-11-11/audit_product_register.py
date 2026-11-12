"""Typed product register: catalog, native-unit stock flow, price and valuation replay."""
from contextlib import closing
from decimal import Decimal as D
from pathlib import Path
import sqlite3,sys,tempfile

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"prototype"))
from product_register import (
    ProductSpec,ProductBalance,PriceQuote,ValuationRecord,
    ProductRegister,ProductRegisterError,
)


def main():
    spec=ProductSpec("steel","S235","mass","t","stockable","period_flow","SPEC:EVIDENCE-1")
    p1=ProductBalance("BAL-P1","steel","S235","P1",0,"plant-A","t",
        D("0"),D("10"),D("2"),D("3"),D("4"),D("0"),D("2"),D("1"),D("2"),"BAL:E1")
    p2=ProductBalance("BAL-P2","steel","S235","P2",1,"plant-A","t",
        D("2"),D("5"),D("0"),D("2"),D("2"),D("1"),D("1"),D("0"),D("1"),"BAL:E2")
    price=PriceQuote("PRICE-P1","steel","S235",D("2"),"t","LCU","P1","basic_price","SOURCE-1","PRICE:E1")
    valuation=ValuationRecord("VAL-P1-OUTPUT","BAL-P1","PRICE-P1","output",D("20"),"VAL:E1")
    with tempfile.TemporaryDirectory() as tmp:
        db=Path(tmp)/"products.sqlite3"
        store=ProductRegister(db)
        assert store.register_product(spec) is True
        assert store.record_balance(p1) is True
        assert store.record_balance(p2) is True
        assert store.record_price(price) is True
        assert store.record_valuation(valuation) is True
        assert store.verify()
        assert store.valuation("VAL-P1-OUTPUT")==valuation
        restarted=ProductRegister(db)
        assert restarted.record_balance(p2) is False
        assert restarted.record_valuation(valuation) is False
        assert restarted.verify()
        try:
            restarted.record_balance(ProductBalance(
                "BAL-P2","steel","S235","P2",1,"plant-A","t",
                D("2"),D("5"),D("0"),D("2"),D("2"),D("1"),D("1"),D("0"),D("2"),"BAL:E2"))
        except ProductRegisterError:
            pass
        else:
            raise AssertionError("changed immutable balance was accepted")
        wrong_price=PriceQuote("PRICE-BAD","steel","S235",D("2"),"kg","LCU","P1","basic_price","SOURCE-2","PRICE:E2")
        try:
            restarted.record_price(wrong_price)
        except ProductRegisterError:
            pass
        else:
            raise AssertionError("price denominator incompatible with native unit was accepted")
        wrong_value=ValuationRecord("VAL-BAD","BAL-P1","PRICE-P1","output",D("21"),"VAL:E2")
        try:
            restarted.record_valuation(wrong_value)
        except ProductRegisterError:
            pass
        else:
            raise AssertionError("valuation inconsistent with referenced balance was accepted")
        with closing(sqlite3.connect(db)) as con:
            con.execute("DROP TRIGGER product_events_no_update")
            con.execute("UPDATE product_events SET payload_json='{}' WHERE event_id='BAL-P1'")
        assert restarted.verify() is False
    print("A2.4 typed durable product register: PASS")
    print("catalog identity, native-unit balance, closing-to-opening carry-forward and price denominator verified")
    print("valuation is bound to a stored balance component and signed price evidence")
    print("immutable retries, conflicting revisions, invalid unit/value and tampered replay rejected")


if __name__=="__main__":
    main()
