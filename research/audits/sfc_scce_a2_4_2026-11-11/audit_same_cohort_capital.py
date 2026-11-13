"""Same-cohort executable control for A2.4.2.

Standard-library Decimal only. The input cohort records are the shared source
for physical quantity, service flow, gross/net valuation, CFC, disposals and
revaluation. This is a synthetic interface fixture, not a runtime integration
or empirical calibration.
"""
from decimal import Decimal as D


def dec(value):
    return value if isinstance(value, D) else D(str(value))


def run_capital_bridge(cohorts, additions, p0, p1, availability, utilization):
    p0, p1 = dec(p0), dec(p1)
    availability, utilization = dec(availability), dec(utilization)
    if p0 <= 0 or p1 <= 0:
        raise ValueError("replacement prices must be positive")
    if not (D("0") <= availability <= D("1")):
        raise ValueError("availability must be in [0, 1]")
    if not (D("0") <= utilization <= D("1")):
        raise ValueError("utilization must be in [0, 1]")

    opening_units = gross_open = net_open = cfc = D("0")
    service_open = D("0")
    gross_disposals = net_disposals = D("0")
    gross_revaluation = net_revaluation = D("0")
    closing_opening_units = gross_survivors = net_survivors = D("0")
    service_survivors = D("0")
    retired_units = D("0")

    for cohort in cohorts:
        qty = dec(cohort["quantity"])
        opening_factor = dec(cohort["net_factor_open"])
        closing_factor = dec(cohort["net_factor_after_cfc"])
        service_quality_open = dec(cohort["service_quality_open"])
        service_quality_close = dec(cohort["service_quality_close"])
        retired = dec(cohort.get("retired_quantity", "0"))
        if qty < 0 or retired < 0 or retired > qty:
            raise ValueError("invalid cohort or retirement quantity")
        if not (D("0") <= closing_factor <= opening_factor <= D("1")):
            raise ValueError("net factors must satisfy 0 <= close <= open <= 1")
        if service_quality_open < 0 or service_quality_close < 0:
            raise ValueError("service quality cannot be negative")

        opening_units += qty
        gross_open += qty * p0
        net_open += qty * opening_factor * p0
        cfc += qty * (opening_factor - closing_factor) * p0
        service_open += qty * service_quality_open * availability * utilization

        survivors = qty - retired
        closing_opening_units += survivors
        retired_units += retired
        gross_disposals += retired * p0
        net_disposals += retired * closing_factor * p0
        gross_survivors += survivors * p1
        net_survivors += survivors * closing_factor * p1
        gross_revaluation += survivors * (p1 - p0)
        net_revaluation += survivors * closing_factor * (p1 - p0)
        service_survivors += (
            survivors * service_quality_close * availability * utilization
        )

    additions_units = dec(additions["quantity"])
    additions_price = dec(additions.get("unit_price", p1))
    if additions_units < 0 or additions_price <= 0:
        raise ValueError("invalid additions")
    gross_acquisitions = additions_units * additions_price
    addition_net_value = gross_acquisitions
    addition_service = (
        additions_units * dec(additions.get("service_quality", "1"))
        * availability * utilization
    )

    physical_close = opening_units + additions_units - retired_units
    gross_close = (
        gross_open + gross_acquisitions - gross_disposals + gross_revaluation
    )
    net_close = (
        net_open + gross_acquisitions - cfc - net_disposals + net_revaluation
    )
    direct_gross = gross_survivors + gross_acquisitions
    direct_net = net_survivors + addition_net_value
    service_close = service_survivors + addition_service

    result = {
        "physical_open": opening_units,
        "physical_close": physical_close,
        "gross_open": gross_open,
        "gross_close": gross_close,
        "net_open": net_open,
        "net_close": net_close,
        "gross_acquisitions": gross_acquisitions,
        "gross_disposals": gross_disposals,
        "net_book_value_disposals": net_disposals,
        "cfc": cfc,
        "gross_revaluation": gross_revaluation,
        "net_revaluation": net_revaluation,
        "service_open": service_open,
        "service_close": service_close,
    }
    assert gross_close == direct_gross, (gross_close, direct_gross)
    assert net_close == direct_net, (net_close, direct_net)
    assert physical_close == closing_opening_units + additions_units
    return result


def main():
    cohorts = [
        {"cohort_id": "v0", "quantity": "10", "net_factor_open": "1.0",
         "net_factor_after_cfc": "0.9", "service_quality_open": "1.0",
         "service_quality_close": "0.95"},
        {"cohort_id": "v1", "quantity": "8", "net_factor_open": "0.9",
         "net_factor_after_cfc": "0.8", "service_quality_open": "0.95",
         "service_quality_close": "0.90"},
        {"cohort_id": "v2", "quantity": "6", "net_factor_open": "0.8",
         "net_factor_after_cfc": "0.7", "service_quality_open": "0.90",
         "service_quality_close": "0.85", "retired_quantity": "1"},
    ]
    r = run_capital_bridge(
        cohorts, {"quantity": "2", "unit_price": "105"}, "100", "105",
        "0.9", "0.8",
    )
    expected = {
        "physical_open": D("24"), "physical_close": D("25"),
        "gross_open": D("2400"), "gross_close": D("2625"),
        "net_open": D("2200.0"), "net_close": D("2194.5"),
        "gross_acquisitions": D("210"), "gross_disposals": D("100"),
        "net_book_value_disposals": D("70.0"), "cfc": D("240.0"),
        "gross_revaluation": D("115"), "net_revaluation": D("94.5"),
        "service_open": D("16.5600"), "service_close": D("16.5240"),
    }
    assert r == expected, (r, expected)
    print("A2.4.2 same-cohort integration fixture: PASS")
    for key, value in r.items():
        print(f"{key}={value}")


if __name__ == "__main__":
    main()
