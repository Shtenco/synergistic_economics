"""Pure, deterministic SFC T/V/O projection kernel (no persistence layer)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Iterable, Mapping, Sequence


class SFCProjectionError(ValueError):
    """Raised when a projection contract or stock-flow invariant is invalid."""


@dataclass(frozen=True, order=True)
class SFCIdentity:
    instrument_id: str
    instrument_class: str
    holder_entity_id: str
    holder_sector: str
    issuer_entity_id: str
    issuer_sector: str
    currency: str
    maturity: str
    denomination: str
    valuation_basis: str

    def __post_init__(self) -> None:
        for field, value in self.__dict__.items():
            if not isinstance(value, str) or not value.strip() or value != value.strip():
                raise SFCProjectionError(f"identity.{field} must be trimmed non-empty text")


@dataclass(frozen=True)
class ProjectionDelta:
    event_id: str
    delta_index: int
    effective_period: int
    identity: SFCIdentity
    component: str
    amount: Decimal
    opening_balance: Decimal


@dataclass(frozen=True)
class PositionRollForward:
    opening: Decimal
    transactions: Decimal
    revaluations: Decimal
    other_volume_changes: Decimal
    closing: Decimal


_IDENTITY_FIELDS = tuple(SFCIdentity.__dataclass_fields__)
_COMPONENTS = frozenset(("T", "V", "O"))


def canonical_decimal(value: Any) -> str:
    """Parse a decimal string and return fixed-point canonical notation.

    Floats and JSON numeric values are intentionally rejected. Negative zero
    is canonicalized to zero; exponent notation is accepted as input but never
    emitted. No Decimal.normalize() call is used, avoiding context rounding.
    """
    if not isinstance(value, str) or not value or value != value.strip():
        raise SFCProjectionError("amount must be a trimmed decimal string")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise SFCProjectionError("amount is not a valid decimal string") from exc
    if not number.is_finite():
        raise SFCProjectionError("amount must be finite")
    if len(number.as_tuple().digits) > 1024 or abs(number.as_tuple().exponent) > 1024:
        raise SFCProjectionError("amount exceeds the supported exact-decimal bounds")
    if number.is_zero():
        return "0"
    fixed = format(number, "f")
    if "." in fixed:
        fixed = fixed.rstrip("0").rstrip(".")
    return fixed


def _exact_sum(values: Iterable[Decimal]) -> Decimal:
    """Add finite Decimals exactly without inheriting the ambient context."""
    numbers = tuple(values)
    if not numbers:
        return Decimal("0")
    parts = [number.as_tuple() for number in numbers]
    exponent = min(part.exponent for part in parts)
    total = 0
    for part in parts:
        coefficient = int("".join(str(digit) for digit in part.digits) or "0")
        if part.sign:
            coefficient = -coefficient
        total += coefficient * (10 ** (part.exponent - exponent))
    digits = tuple(int(char) for char in str(abs(total))) or (0,)
    return Decimal((1 if total < 0 else 0, digits, exponent))


def _decimal(value: Any, field: str) -> Decimal:
    try:
        return Decimal(canonical_decimal(value))
    except SFCProjectionError as exc:
        raise SFCProjectionError(f"{field}: {exc}") from exc


def _period(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise SFCProjectionError(f"{field} must be a non-negative integer")
    return value


def _identity(value: Any) -> SFCIdentity:
    if not isinstance(value, Mapping):
        raise SFCProjectionError("delta.identity must be a mapping")
    parts = {}
    for field in _IDENTITY_FIELDS:
        item = value.get(field)
        if not isinstance(item, str) or not item.strip() or item != item.strip():
            raise SFCProjectionError(f"identity.{field} must be trimmed non-empty text")
        parts[field] = item
    return SFCIdentity(**parts)


def validate_projection(
    events: Sequence[Mapping[str, Any]], projection: Mapping[str, Any]
) -> tuple[str, tuple[ProjectionDelta, ...]]:
    """Validate exact per-event coverage and return immutable typed deltas."""
    if not isinstance(events, (tuple, list)) or not events:
        raise SFCProjectionError("events must be a non-empty sequence")
    if not isinstance(projection, Mapping):
        raise SFCProjectionError("projection object is required")
    mapping_version = projection.get("mapping_version")
    if not isinstance(mapping_version, str) or not mapping_version.strip():
        raise SFCProjectionError("mapping_version is required")

    expected: dict[str, int] = {}
    for event in events:
        if not isinstance(event, Mapping):
            raise SFCProjectionError("each event must be a mapping")
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id.strip() or event_id in expected:
            raise SFCProjectionError("event IDs must be non-empty and unique")
        expected[event_id] = _period(event.get("effective_period"), "event.effective_period")

    results = projection.get("events")
    if not isinstance(results, (tuple, list)):
        raise SFCProjectionError("projection.events must explicitly cover every event")
    seen: set[str] = set()
    deltas: list[ProjectionDelta] = []
    indexes: dict[str, list[int]] = {}
    for result in results:
        if not isinstance(result, Mapping):
            raise SFCProjectionError("each event disposition must be a mapping")
        event_id = result.get("event_id")
        if not isinstance(event_id, str) or event_id not in expected or event_id in seen:
            raise SFCProjectionError("unknown or duplicate event disposition")
        seen.add(event_id)
        disposition = result.get("disposition")
        raw_deltas = result.get("deltas")
        if not isinstance(raw_deltas, (tuple, list)):
            raise SFCProjectionError("each event disposition requires a delta list")
        if disposition == "mapped" and not raw_deltas:
            raise SFCProjectionError("mapped disposition requires at least one delta")
        if disposition == "no_stock_effect" and raw_deltas:
            raise SFCProjectionError("no_stock_effect disposition requires an empty delta list")
        if disposition not in ("mapped", "no_stock_effect"):
            raise SFCProjectionError("unsupported event disposition")

        indexes[event_id] = []
        for raw in raw_deltas:
            if not isinstance(raw, Mapping):
                raise SFCProjectionError("each delta must be a mapping")
            if raw.get("event_id") != event_id:
                raise SFCProjectionError("delta event_id does not match its disposition")
            delta_index = raw.get("delta_index")
            if not isinstance(delta_index, int) or isinstance(delta_index, bool) or delta_index < 0:
                raise SFCProjectionError("delta_index must be a non-negative integer")
            indexes[event_id].append(delta_index)
            period = _period(raw.get("effective_period"), "delta.effective_period")
            if period != expected[event_id]:
                raise SFCProjectionError("delta effective period differs from its event")
            component = raw.get("component")
            if not isinstance(component, str) or component not in _COMPONENTS:
                raise SFCProjectionError("component must be T, V or O")
            deltas.append(ProjectionDelta(
                event_id=event_id,
                delta_index=delta_index,
                effective_period=period,
                identity=_identity(raw.get("identity")),
                component=component,
                amount=_decimal(raw.get("amount"), "delta.amount"),
                opening_balance=_decimal(raw.get("opening_balance"), "delta.opening_balance"),
            ))
        if indexes[event_id] != list(range(len(indexes[event_id]))):
            raise SFCProjectionError("delta indexes must be contiguous and ordered from zero")

    if seen != set(expected):
        raise SFCProjectionError("projection does not explicitly cover every event")
    return mapping_version, tuple(deltas)


def replay_positions(
    events: Sequence[Mapping[str, Any]],
    projection: Mapping[str, Any],
    openings: Mapping[tuple[SFCIdentity, int], Any],
    *,
    nonnegative_identities: set[SFCIdentity] | None = None,
) -> dict[tuple[SFCIdentity, int], PositionRollForward]:
    """Replay T/V/O deltas from explicit openings with period continuity.

    Missing openings are never treated as zero. Negative positions are only
    prohibited for identities explicitly listed by the instrument contract.
    """
    _, deltas = validate_projection(events, projection)
    parsed_openings: dict[tuple[SFCIdentity, int], Decimal] = {}
    for key, value in openings.items():
        if (not isinstance(key, tuple) or len(key) != 2
                or not isinstance(key[0], SFCIdentity)):
            raise SFCProjectionError("opening keys must be (SFCIdentity, period)")
        period = _period(key[1], "opening.period")
        parsed_openings[(key[0], period)] = _decimal(value, "opening.balance")

    terms: dict[tuple[SFCIdentity, int], dict[str, list[Decimal]]] = {}
    for delta in deltas:
        key = (delta.identity, delta.effective_period)
        if key not in parsed_openings:
            raise SFCProjectionError("delta has no explicit opening snapshot row")
        if delta.opening_balance != parsed_openings[key]:
            raise SFCProjectionError("delta frozen opening differs from opening snapshot")
        bucket = terms.setdefault(key, {c: [] for c in _COMPONENTS})
        bucket[delta.component].append(delta.amount)

    periods_by_identity: dict[SFCIdentity, list[int]] = {}
    for identity, period in parsed_openings:
        periods_by_identity.setdefault(identity, []).append(period)

    result: dict[tuple[SFCIdentity, int], PositionRollForward] = {}
    for identity in sorted(periods_by_identity):
        periods = sorted(periods_by_identity[identity])
        previous_period: int | None = None
        previous_closing: Decimal | None = None
        for period in periods:
            key = (identity, period)
            opening = parsed_openings[key]
            if previous_period is not None:
                if period != previous_period + 1:
                    raise SFCProjectionError("period sequence contains a gap")
                if opening != previous_closing:
                    raise SFCProjectionError("next-period opening differs from prior closing")
            bucket_terms = terms.get(key, {c: [] for c in _COMPONENTS})
            bucket = {component: _exact_sum(values)
                      for component, values in bucket_terms.items()}
            closing = _exact_sum((opening, bucket["T"], bucket["V"], bucket["O"]))
            if nonnegative_identities is not None and identity in nonnegative_identities and closing < 0:
                raise SFCProjectionError("instrument contract prohibits negative gross closing position")
            result[key] = PositionRollForward(
                opening, bucket["T"], bucket["V"], bucket["O"], closing
            )
            previous_period = period
            previous_closing = closing
    return result


def financial_net_lending(
    transaction_asset_changes: Iterable[Any],
    transaction_liability_changes: Iterable[Any],
) -> Decimal:
    """Compute transaction-only financial NL; V and O are not accepted here."""
    assets = tuple(_decimal(v, "transaction asset change") for v in transaction_asset_changes)
    liabilities = tuple(_decimal(v, "transaction liability change") for v in transaction_liability_changes)
    return _exact_sum((*assets, *(value.copy_negate() for value in liabilities)))
