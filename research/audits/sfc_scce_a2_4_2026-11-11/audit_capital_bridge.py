"""Independent Decimal controls for the A2.4.2 capital bridge.

This script validates only the synthetic example documented alongside it.
It is not an economic engine, an empirical calibration, or a test of the
repository's runtime asset-cohort implementation.
"""
from decimal import Decimal as D


def main():
    p0, p1 = D("100"), D("105")
    opening = [(D("10"), D("1.0")), (D("8"), D("0.9")), (D("6"), D("0.8"))]

    gross_open = sum(n * p0 for n, _ in opening)
    net_open = sum(n * w * p0 for n, w in opening)
    additions = D("2")
    retired = D("1")
    gross_acquisitions = additions * p1
    cfc = sum(n * D("0.1") * p0 for n, _ in opening)
    gross_disposals = retired * p0
    net_disposals = retired * D("0.7") * p0

    gross_revaluation = (sum(n for n, _ in opening) - retired) * (p1 - p0)
    net_survivor_factor = (
        D("10") * D("0.9") + D("8") * D("0.8") + D("5") * D("0.7")
    )
    net_revaluation = net_survivor_factor * (p1 - p0)

    gross_close = (
        gross_open + gross_acquisitions - gross_disposals + gross_revaluation
    )
    net_close = (
        net_open + gross_acquisitions - cfc - net_disposals + net_revaluation
    )

    direct_gross = (D("10") + D("8") + D("5") + additions) * p1
    direct_net = (
        D("10") * D("0.9") + D("8") * D("0.8")
        + D("5") * D("0.7") + additions
    ) * p1

    physical_open = sum(n for n, _ in opening)
    physical_close = physical_open + additions - retired

    service_open = (
        D("10") * D("1.0") + D("8") * D("0.95") + D("6") * D("0.90")
    ) * D("0.9") * D("0.8")
    service_close = (
        D("10") * D("0.95") + D("8") * D("0.90")
        + D("5") * D("0.85") + additions
    ) * D("0.9") * D("0.8")

    assert gross_open == D("2400")
    assert net_open == D("2200.0")
    assert gross_acquisitions == D("210")
    assert cfc == D("240.0")
    assert gross_disposals == D("100")
    assert net_disposals == D("70.0")
    assert gross_revaluation == D("115")
    assert net_revaluation == D("94.5")
    assert gross_close == direct_gross == D("2625")
    assert net_close == direct_net == D("2194.5")
    assert physical_close == D("25")
    assert service_open == D("16.5600")
    assert service_close == D("16.5240")

    # Gross/net SFC net-lending identity: CFC must be deducted on both sides.
    gross_saving, gross_capital_formation, cfc_sector = D("49"), D("68"), D("8")
    gross_nl = gross_saving - gross_capital_formation
    net_nl = (gross_saving - cfc_sector) - (gross_capital_formation - cfc_sector)
    assert gross_nl == net_nl == D("-19")

    print("A2.4.2 capital bridge: PASS")
    print(f"physical units: {physical_open} -> {physical_close}")
    print(f"gross stock: {gross_open} -> {gross_close}")
    print(f"net stock: {net_open} -> {net_close}")
    print(f"gross acquisitions={gross_acquisitions}; CFC={cfc}; gross disposals={gross_disposals}; "
          f"net disposals={net_disposals}")
    print(f"revaluation gross={gross_revaluation}; net={net_revaluation}")
    print(f"capital services: {service_open} -> {service_close}")
    print(f"gross/net sectoral net lending: {gross_nl} / {net_nl}")


if __name__ == "__main__":
    main()
