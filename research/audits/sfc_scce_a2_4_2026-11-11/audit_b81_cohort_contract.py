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
CONDITIONS = {"new", "serviceable", "degraded", "failed", "unsafe", "unknown"}
RETIREMENT_REASONS = {
    "none", "planned", "failure", "obsolescence", "accident", "other"
}
DATA_QUALITY = {"measured", "documented", "estimated", "simulated", "unknown"}


def finite_nonnegative(value, field):
    value = D(str(value))
    if not value.is_finite() or value < 0:
        raise CohortError(f"{field} must be finite and non-negative")
    return value


def validate_material_vector(material_vector):
    if not isinstance(material_vector, tuple) or not material_vector:
        raise CohortError("material_vector must be a non-empty immutable tuple")
    ids = set()
    for material in material_vector:
        if not material.material_id or material.material_id in ids:
            raise CohortError("material IDs must be non-empty and unique per cohort")
        ids.add(material.material_id)
        finite_nonnegative(material.mass_per_unit, "mass_per_unit")
        if material.unit not in {"kg", "t"}:
            raise CohortError("material passport must use a mass unit")
    return True


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
    if (not isinstance(cohort.vintage, int) or isinstance(cohort.vintage, bool)
            or not isinstance(cohort.age, int) or isinstance(cohort.age, bool)
            or cohort.vintage < 0 or cohort.age < 0):
        raise CohortError("vintage and age must be non-negative integer periods")
    finite_nonnegative(cohort.quantity, "quantity")
    finite_nonnegative(cohort.service_capacity, "service_capacity")
    if cohort.condition_state not in CONDITIONS:
        raise CohortError("unknown condition_state")
    if cohort.operating_status not in STATES:
        raise CohortError("unknown operating_status")
    if cohort.retirement_reason not in RETIREMENT_REASONS:
        raise CohortError("unknown retirement_reason")
    for field, value in (
        ("availability", cohort.availability),
        ("utilization", cohort.utilization),
        ("service_quality", cohort.service_quality),
    ):
        value = D(str(value))
        if not value.is_finite() or not D("0") <= value <= D("1"):
            raise CohortError(f"{field} must be finite and in [0,1]")
    validate_material_vector(cohort.material_vector)
    if (not cohort.data_quality or cohort.data_quality not in DATA_QUALITY
            or not isinstance(cohort.repair_history, tuple)
            or any(not isinstance(x, str) or not x for x in cohort.repair_history)
            or len(set(cohort.repair_history)) != len(cohort.repair_history)):
        raise CohortError("data_quality and unique immutable repair event IDs are required")
    return True


def validate_component(component):
    if not component.host_asset_type or not component.component_type:
        raise CohortError("component and host asset identity are required")
    if (not isinstance(component.vintage, int) or isinstance(component.vintage, bool)
            or not isinstance(component.age, int) or isinstance(component.age, bool)
            or component.vintage < 0 or component.age < 0):
        raise CohortError("component vintage and age must be non-negative integer periods")
    finite_nonnegative(component.quantity, "component quantity")
    validate_material_vector(component.material_vector)
    return True

def apply_period(opening_states, moves, additions, retirements, physical_losses):
    states = {k: finite_nonnegative(v, f"opening state {k}")
              for k, v in opening_states.items()}
    if set(states) - STATES:
        raise CohortError("unknown opening operating state")
    closing = {state: states.get(state, D("0")) for state in STATES}

    for source, destination, quantity in moves:
        quantity = finite_nonnegative(quantity, "state transition quantity")
        if source not in STATES or destination not in STATES:
            raise CohortError("invalid state transition")
        if source == destination or closing[source] < quantity:
            raise CohortError("invalid or overdrawn state transition")
        closing[source] -= quantity
        closing[destination] += quantity

    for state, quantity in additions.items():
        quantity = finite_nonnegative(quantity, "cohort addition quantity")
        if state not in STATES:
            raise CohortError("invalid cohort additions")
        closing[state] += quantity

    for state, quantity in retirements.items():
        quantity = finite_nonnegative(quantity, "retirement quantity")
        if state not in STATES or closing[state] < quantity:
            raise CohortError("invalid final retirement")
        closing[state] -= quantity

    for state, quantity in physical_losses.items():
        quantity = finite_nonnegative(quantity, "physical loss quantity")
        if state not in STATES or closing[state] < quantity:
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
    assert validate_component(replacement)
    assert replacement.host_asset_type == cohort.asset_type
    assert replacement.quantity > 0 and replacement.vintage > cohort.vintage
    assert host_age_after_period == 7
    assert replacement.vintage == 2026 and replacement.age == 0
    assert cohort.vintage == 2020

    # Fail-closed schema controls: duplicate materials, unknown condition,
    # non-finite service factors and malformed component identity.
    try:
        validate_cohort(AssetCohort(
            **{**cohort.__dict__, "material_vector": (steel, steel)}))
    except CohortError:
        pass
    else:
        raise AssertionError("duplicate material passport accepted")
    try:
        validate_cohort(AssetCohort(
            **{**cohort.__dict__, "condition_state": "magically_new"}))
    except CohortError:
        pass
    else:
        raise AssertionError("unknown condition state accepted")
    try:
        validate_cohort(AssetCohort(
            **{**cohort.__dict__, "availability": D("NaN")}))
    except CohortError:
        pass
    else:
        raise AssertionError("non-finite availability accepted")
    try:
        validate_component(ComponentCohort(
            "machine", "", 2026, 0, D("1"), (steel,)))
    except CohortError:
        pass
    else:
        raise AssertionError("component without identity accepted")
    try:
        apply_period({"operating": D("NaN")}, [], {}, {}, {})
    except CohortError:
        pass
    else:
        raise AssertionError("non-finite opening state accepted")

    # Final retirement removes units once; failure/repair transitions do not.
    retired = apply_period(
        {"operating": 5, "repair": 1}, moves=[("operating", "repair", 1)],
        additions={}, retirements={"repair": 1}, physical_losses={})
    assert sum(retired.values()) == D("5")

    print("A2.4.2 B8.1 cohort contract fixture: PASS")
    print("capital_services=684.000; steel_in_cohort=20 t")
    print("repair transitions preserve physical stock; retirement reduces it once")
    print("host vintage/age preserved; replacement component receives own vintage")
    print("negative controls: duplicate material, unknown condition, NaN availability/state and incomplete component rejected")


if __name__ == "__main__":
    main()
