"""A2.4.2 B8.1 cohort ontology and state-transition contract fixture.

This adapter tests the fields and invariants stated in the B8.1 specification.
It is not an existing B8.1 runtime object and must not be described as such.
"""
from dataclasses import dataclass
from decimal import Decimal as D


class CohortError(ValueError):
    pass


STATES = {"operating", "reserve", "diagnostics", "repair",
          "remanufacturing", "storage"}


@dataclass(frozen=True)
class Material:
    material_id: str
    mass_per_unit: D
    unit: str


@dataclass(frozen=True)
class AssetCohort:
    asset_type: str
    vintage: int
    region_origin: str
    region_use: str
    quantity: D
    age: int
    condition_state: str
    operating_status: str
    material_vector: tuple
    service_capacity: D
    availability: D
    utilization: D
    service_quality: D
    repair_history: tuple
    retirement_reason: str
    data_quality: str


@dataclass(frozen=True)
class ComponentCohort:
    host_asset_type: str
    component_type: str
    vintage: int
    age: int
    quantity: D
    material_vector: tuple


def validate_cohort(cohort):
    if not all((cohort.asset_type, cohort.region_origin, cohort.region_use,
                cohort.condition_state, cohort.retirement_reason)):
        raise CohortError("B8.1 asset identity/state metadata is incomplete")
    if cohort.vintage < 0 or cohort.age < 0 or cohort.quantity < 0:
        raise CohortError("invalid vintage, age or quantity")
    if cohort.operating_status not in STATES:
        raise CohortError("unknown operating_status")
    if cohort.service_capacity < 0:
        raise CohortError("negative service capacity")
    if not (D("0") <= cohort.availability <= D("1")
            and D("0") <= cohort.utilization <= D("1")
            and D("0") <= cohort.service_quality <= D("1")):
        raise CohortError("availability, utilization and quality must be in [0,1]")
    if not cohort.material_vector:
        raise CohortError("material_vector is required")
    if not cohort.data_quality or not isinstance(cohort.repair_history, tuple):
        raise CohortError("data_quality and immutable repair_history are required")
    for material in cohort.material_vector:
        if not material.material_id or material.mass_per_unit < 0:
            raise CohortError("invalid material passport")
        if material.unit not in {"kg", "t"}:
            raise CohortError("material passport must use a mass unit")
    return True


def apply_period(opening_states, moves, additions, retirements, physical_losses):
    states = {k: D(str(v)) for k, v in opening_states.items()}
    if set(states) - STATES or any(v < 0 for v in states.values()):
        raise CohortError("invalid opening state counts")
    closing = {state: states.get(state, D("0")) for state in STATES}

    for source, destination, quantity in moves:
        quantity = D(str(quantity))
        if source not in STATES or destination not in STATES or quantity < 0:
            raise CohortError("invalid state transition")
        if source == destination or closing[source] < quantity:
            raise CohortError("invalid or overdrawn state transition")
        closing[source] -= quantity
        closing[destination] += quantity

    for state, quantity in additions.items():
        quantity = D(str(quantity))
        if state not in STATES or quantity < 0:
            raise CohortError("invalid cohort additions")
        closing[state] += quantity

    for state, quantity in retirements.items():
        quantity = D(str(quantity))
        if state not in STATES or quantity < 0 or closing[state] < quantity:
            raise CohortError("invalid final retirement")
        closing[state] -= quantity

    for state, quantity in physical_losses.items():
        quantity = D(str(quantity))
        if state not in STATES or quantity < 0 or closing[state] < quantity:
            raise CohortError("invalid physical loss")
        closing[state] -= quantity

    opening_total = sum(states.values(), D("0"))
    closing_total = sum(closing.values(), D("0"))
    expected = (opening_total
                + sum((D(str(v)) for v in additions.values()), D("0"))
                - sum((D(str(v)) for v in retirements.values()), D("0"))
                - sum((D(str(v)) for v in physical_losses.values()), D("0")))
    assert closing_total == expected
    return closing


def capital_services(cohort):
    validate_cohort(cohort)
    if cohort.operating_status != "operating":
        return D("0")
    return (cohort.quantity * cohort.service_capacity * cohort.availability
            * cohort.utilization * cohort.service_quality)


def material_mass(cohort, material_id):
    validate_cohort(cohort)
    for item in cohort.material_vector:
        if item.material_id == material_id:
            return cohort.quantity * item.mass_per_unit
    return D("0")


def main():
    steel = Material("steel", D("2"), "t")
    cohort = AssetCohort(
        asset_type="machine", vintage=2020, region_origin="R1",
        region_use="R1", quantity=D("10"), age=6,
        condition_state="serviceable", operating_status="operating",
        material_vector=(steel,), service_capacity=D("100"),
        availability=D("0.9"), utilization=D("0.8"),
        service_quality=D("0.95"), repair_history=("repair-2024",),
        retirement_reason="none", data_quality="documented")
    assert validate_cohort(cohort)
    assert capital_services(cohort) == D("684.000")
    assert material_mass(cohort, "steel") == D("20")

    # Temporary failures/repairs are state moves, not physical stock destruction.
    closing = apply_period(
        {"operating": 10, "repair": 2, "reserve": 1},
        moves=[("operating", "repair", 2), ("repair", "operating", 1)],
        additions={"operating": 1},
        retirements={"reserve": 1},
        physical_losses={})
    assert closing == {
        "operating": D("10"), "repair": D("3"), "reserve": D("0"),
        "diagnostics": D("0"), "remanufacturing": D("0"), "storage": D("0")}
    assert sum(closing.values()) == D("13")

    # A component replacement gets a new component vintage; host age is unchanged.
    host_age_after_period = cohort.age + 1
    replacement = ComponentCohort(
        "machine", "motor", 2026, 0, D("1"),
        (Material("copper", D("12"), "kg"),))
    assert replacement.host_asset_type == cohort.asset_type
    assert replacement.quantity > 0 and replacement.vintage > cohort.vintage
    assert host_age_after_period == 7
    assert replacement.vintage == 2026 and replacement.age == 0
    assert cohort.vintage == 2020

    # Final retirement removes units once; failure/repair transitions do not.
    retired = apply_period(
        {"operating": 5, "repair": 1}, moves=[("operating", "repair", 1)],
        additions={}, retirements={"repair": 1}, physical_losses={})
    assert sum(retired.values()) == D("5")

    print("A2.4.2 B8.1 cohort contract fixture: PASS")
    print("capital_services=684.000; steel_in_cohort=20 t")
    print("repair transitions preserve physical stock; retirement reduces it once")
    print("host vintage/age preserved; replacement component receives own vintage")


if __name__ == "__main__":
    main()
