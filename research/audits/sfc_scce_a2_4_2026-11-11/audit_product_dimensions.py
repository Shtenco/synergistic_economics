"""Decimal arithmetic controls for the A2.4.3 B2 product-dimension contract.

These assertions reproduce the frozen synthetic B2 rows. They do not calibrate
prices or prove empirical conservation in a real production network.
"""
from decimal import Decimal as D


def close(lhs, rhs, label):
    assert lhs == rhs, f"{label}: {lhs} != {rhs}"


def main():
    # Separate native-unit balances.
    close(D("5") + D("10") + D("2"), D("8") + D("3") + D("1") + D("1") + D("4"), "steel t")
    close(D("20") + D("30") + D("5"), D("5") + D("35") + D("5") + D("5") + D("5"), "grain t")
    close(D("100") + D("10"), D("60") + D("40") + D("5") + D("5"), "electricity MWh")
    close(D("12"), D("12") + D("0"), "scrap t")
    close(D("0") + D("2"), D("2") + D("0"), "equipment units")

    # Process transformations and explicit energy conversion.
    close(D("12"), D("10") + D("2"), "scrap processing mass t")
    close(D("500"), D("100") * D("3.6") + D("140"), "fuel-energy conversion GJ")

    # Suballocations must reconcile to, not be added on top of, intermediate electricity.
    close(D("20") + D("4") + D("36"), D("60"), "intermediate electricity allocation MWh")

    # A valuation change cannot change the underlying physical quantity.
    quantity_t = D("10")
    value_at_2 = quantity_t * D("2")
    value_at_3 = quantity_t * D("3")
    close(quantity_t, D("10"), "physical quantity invariant")
    close(value_at_2, D("20"), "value at price 2")
    close(value_at_3, D("30"), "value at price 3")
    close(value_at_3 - value_at_2, quantity_t * (D("3") - D("2")), "pure price effect")

    print("A2.4.3 B2 dimensional controls: PASS")
    print("steel=17 t; grain=55 t; electricity=110 MWh; scrap=12 t; equipment=2 units")
    print("process mass and energy conversions: PASS")
    print("intermediate electricity suballocation: 60 MWh exactly")
    print("price variation changes value only, not native quantity")


if __name__ == "__main__":
    main()
