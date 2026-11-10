"""Typed product registry and monetary valuation adapter for A2.4.3.

Physical quantities remain in native units. Monetary valuation is a derived
view keyed by product, grade, period, basis and currency; it never changes the
physical register. Standard library only.
"""
from dataclasses import dataclass
from decimal import Decimal as D


@dataclass(frozen=True)
class ProductSpec:
    product_id: str
    grade_id: str
    dimension: str
    native_unit: str
    stockability: str
    time_basis: str


@dataclass(frozen=True)
class PhysicalQuantity:
    product_id: str
    grade_id: str
    quantity: D
    unit: str
    period: str
    boundary: str


@dataclass(frozen=True)
class UnitPrice:
    product_id: str
    grade_id: str
    price: D
    denominator_unit: str
    currency: str
    period: str
    valuation_basis: str
    source_id: str


@dataclass(frozen=True)
class Valuation:
    product_id: str
    grade_id: str
    quantity: D
    native_unit: str
    unit_price: D
    currency: str
    value: D
    period: str
    valuation_basis: str
    source_id: str


class ContractError(ValueError):
    pass


def validate_quantity(spec, quantity):
    if quantity.product_id != spec.product_id:
        raise ContractError("product_id mismatch")
    if quantity.grade_id != spec.grade_id:
        raise ContractError("grade_id mismatch")
    if quantity.unit != spec.native_unit:
        raise ContractError("native unit mismatch; explicit conversion required")
    if not quantity.period or not quantity.boundary:
        raise ContractError("period and system boundary are mandatory")
    if quantity.quantity < 0:
        raise ContractError("negative physical quantity is not allowed here")


def value_quantity(spec, quantity, price):
    validate_quantity(spec, quantity)
    if price.product_id != spec.product_id or price.grade_id != spec.grade_id:
        raise ContractError("price product/grade does not match physical quantity")
    if price.denominator_unit != spec.native_unit:
        raise ContractError("price denominator must equal the native unit")
    if price.period != quantity.period:
        raise ContractError("price and quantity periods differ")
    if not price.currency or not price.valuation_basis or not price.source_id:
        raise ContractError("currency, valuation basis and source are mandatory")
    if price.price < 0:
        raise ContractError("unit price cannot be negative")
    return Valuation(
        product_id=quantity.product_id,
        grade_id=quantity.grade_id,
        quantity=quantity.quantity,
        native_unit=quantity.unit,
        unit_price=price.price,
        currency=price.currency,
        value=quantity.quantity * price.price,
        period=quantity.period,
        valuation_basis=price.valuation_basis,
        source_id=price.source_id,
    )


def balance_product(spec, opening, output, imports, intermediate, final,
                    gfcf, exports, losses, closing):
    """Single-product/grade/node balance; unlike products cannot be combined."""
    values = [opening, output, imports, intermediate, final, gfcf,
              exports, losses, closing]
    if any(x.product_id != spec.product_id or x.grade_id != spec.grade_id
           or x.unit != spec.native_unit for x in values):
        raise ContractError("balance contains incompatible product/grade/unit")
    if len({x.period for x in values}) != 1:
        raise ContractError("balance spans multiple periods")
    if len({x.boundary for x in values}) != 1:
        raise ContractError("balance spans multiple system boundaries")
    lhs = opening.quantity + output.quantity + imports.quantity
    rhs = (intermediate.quantity + final.quantity + gfcf.quantity
           + exports.quantity + losses.quantity + closing.quantity)
    if lhs != rhs:
        raise ContractError(f"physical balance does not close: {lhs} != {rhs}")
    return lhs


def main():
    steel = ProductSpec("steel", "S235", "mass", "t", "stockable", "period_flow")
    q = PhysicalQuantity("steel", "S235", D("10"), "t", "P1", "plant_A")
    p2 = UnitPrice("steel", "S235", D("2"), "t", "D.E.", "P1",
                   "basic_price", "price-source-001")
    p3 = UnitPrice("steel", "S235", D("3"), "t", "D.E.", "P1",
                   "basic_price", "price-source-002")
    v2, v3 = value_quantity(steel, q, p2), value_quantity(steel, q, p3)
    assert v2.value == D("20") and v3.value == D("30")
    assert v2.quantity == v3.quantity == q.quantity == D("10")

    # A wrong unit price denominator and a cross-grade price must fail closed.
    try:
        value_quantity(steel, q, UnitPrice(
            "steel", "S235", D("2"), "kg", "D.E.", "P1",
            "basic_price", "bad-unit"))
    except ContractError:
        pass
    else:
        raise AssertionError("kg-denominated price was accepted for tonnes")
    try:
        value_quantity(steel, q, UnitPrice(
            "steel", "S355", D("2"), "t", "D.E.", "P1",
            "basic_price", "bad-grade"))
    except ContractError:
        pass
    else:
        raise AssertionError("cross-grade valuation was accepted")

    print("A2.4.3 typed product valuation adapter: PASS")
    print(f"physical quantity remains {q.quantity} {q.unit}")
    print(f"value changes only: {v2.value} -> {v3.value} {v2.currency}")


if __name__ == "__main__":
    main()
