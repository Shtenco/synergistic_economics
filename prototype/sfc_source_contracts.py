"""Version-pinned source contracts for native banking-to-SFC projection.

This module deliberately does not mutate the financial register or the GOLD-2A
journal. It validates the metadata and opening-stock boundary an independent
banking SFC adapter must consume. Missing terms, sectors, or opening rows fail
closed; no maturity, denomination, sector, or zero balance is inferred.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from typing import Iterable, Mapping, Sequence

from sfc_projection_kernel import SFCIdentity, SFCProjectionError


class SFCSourceContractError(ValueError):
    """A source registry or opening-stock contract is incomplete or inconsistent."""


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SFCSourceContractError(f"{field} must be trimmed non-empty text")
    return value


def _period(value: object, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise SFCSourceContractError(f"{field} must be a positive integer")
    return value


def _end_period(value: object, field: str) -> int | None:
    if value is None:
        return None
    return _period(value, field)


def _balance(value: object) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise SFCSourceContractError("opening balance must be a trimmed decimal string")
    try:
        number = Decimal(value)
    except (InvalidOperation, ValueError) as exc:
        raise SFCSourceContractError("opening balance must be a decimal string") from exc
    if not number.is_finite():
        raise SFCSourceContractError("opening balance must be finite")
    if len(number.as_tuple().digits) > 1024 or abs(number.as_tuple().exponent) > 1024:
        raise SFCSourceContractError("opening balance exceeds exact-decimal bounds")
    if number.is_zero():
        return "0"
    fixed = format(number, "f")
    return fixed.rstrip("0").rstrip(".") if "." in fixed else fixed


def _canonical_digest(payload: object) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class InstrumentTerms:
    """Complete, explicit terms for one instrument over an effective period."""

    instrument_id: str
    instrument_class: str
    denomination: str
    currency: str
    valuation_basis: str
    maturity: str
    rate_type: str
    rate_reference: str
    rate_spread: str
    reset_frequency: str
    day_count_convention: str
    payment_frequency: str
    principal_repayment: str
    effective_from_period: int
    effective_to_period: int | None
    nonnegative_gross_position: bool

    def __post_init__(self) -> None:
        for field in (
            "instrument_id", "instrument_class", "denomination", "currency",
            "valuation_basis", "maturity", "rate_type", "rate_reference",
            "rate_spread", "reset_frequency", "day_count_convention",
            "payment_frequency", "principal_repayment",
        ):
            _text(getattr(self, field), f"instrument.{field}")
        start = _period(self.effective_from_period, "instrument.effective_from_period")
        end = _end_period(self.effective_to_period, "instrument.effective_to_period")
        if end is not None and end < start:
            raise SFCSourceContractError("instrument effective period ends before it starts")
        if not isinstance(self.nonnegative_gross_position, bool):
            raise SFCSourceContractError("instrument.nonnegative_gross_position must be boolean")

    def active(self, period: int) -> bool:
        return self.effective_from_period <= period and (
            self.effective_to_period is None or period <= self.effective_to_period
        )

    def canonical_record(self) -> dict:
        return {
            "instrument_id": self.instrument_id,
            "instrument_class": self.instrument_class,
            "denomination": self.denomination,
            "currency": self.currency,
            "valuation_basis": self.valuation_basis,
            "maturity": self.maturity,
            "rate_type": self.rate_type,
            "rate_reference": self.rate_reference,
            "rate_spread": self.rate_spread,
            "reset_frequency": self.reset_frequency,
            "day_count_convention": self.day_count_convention,
            "payment_frequency": self.payment_frequency,
            "principal_repayment": self.principal_repayment,
            "effective_from_period": self.effective_from_period,
            "effective_to_period": self.effective_to_period,
            "nonnegative_gross_position": self.nonnegative_gross_position,
        }


@dataclass(frozen=True)
class InstrumentTermsRegistry:
    version: str
    terms: tuple[InstrumentTerms, ...]

    def __post_init__(self) -> None:
        _text(self.version, "instrument registry version")
        if not isinstance(self.terms, tuple) or not self.terms:
            raise SFCSourceContractError("instrument registry requires a non-empty tuple of terms")
        if any(not isinstance(item, InstrumentTerms) for item in self.terms):
            raise SFCSourceContractError("instrument registry contains an invalid terms record")
        grouped: dict[str, list[InstrumentTerms]] = {}
        for item in self.terms:
            grouped.setdefault(item.instrument_id, []).append(item)
        for instrument_id, records in grouped.items():
            records.sort(key=lambda item: item.effective_from_period)
            for previous, current in zip(records, records[1:]):
                if previous.effective_to_period is None or current.effective_from_period <= previous.effective_to_period:
                    raise SFCSourceContractError(
                        f"overlapping instrument terms for {instrument_id}"
                    )

    @property
    def digest(self) -> str:
        records = [item.canonical_record() for item in sorted(
            self.terms, key=lambda item: (item.instrument_id, item.effective_from_period)
        )]
        return _canonical_digest({"version": self.version, "terms": records})

    def resolve(self, instrument_id: str, period: int) -> InstrumentTerms:
        _text(instrument_id, "instrument_id")
        _period(period, "period")
        matches = [item for item in self.terms
                   if item.instrument_id == instrument_id and item.active(period)]
        if len(matches) != 1:
            raise SFCSourceContractError(
                f"instrument terms are missing or ambiguous for {instrument_id} in period {period}"
            )
        return matches[0]


@dataclass(frozen=True)
class SectorMembership:
    entity_id: str
    sector_code: str
    effective_from_period: int
    effective_to_period: int | None

    def __post_init__(self) -> None:
        _text(self.entity_id, "sector.entity_id")
        _text(self.sector_code, "sector.sector_code")
        _period(self.effective_from_period, "sector.effective_from_period")
        end = _end_period(self.effective_to_period, "sector.effective_to_period")
        if end is not None and end < self.effective_from_period:
            raise SFCSourceContractError("sector membership ends before it starts")

    def active(self, period: int) -> bool:
        return self.effective_from_period <= period and (
            self.effective_to_period is None or period <= self.effective_to_period
        )


@dataclass(frozen=True)
class EffectiveDatedSectorRegistry:
    version: str
    allowed_sector_codes: frozenset[str]
    memberships: tuple[SectorMembership, ...]

    def __post_init__(self) -> None:
        _text(self.version, "sector registry version")
        if not isinstance(self.allowed_sector_codes, frozenset) or not self.allowed_sector_codes:
            raise SFCSourceContractError("allowed sector codes must be a non-empty frozenset")
        for code in self.allowed_sector_codes:
            _text(code, "allowed sector code")
        if not isinstance(self.memberships, tuple) or not self.memberships:
            raise SFCSourceContractError("sector registry requires a non-empty membership tuple")
        grouped: dict[str, list[SectorMembership]] = {}
        for membership in self.memberships:
            if not isinstance(membership, SectorMembership):
                raise SFCSourceContractError("sector registry contains an invalid membership")
            if membership.sector_code not in self.allowed_sector_codes:
                raise SFCSourceContractError(
                    f"unsupported sector code {membership.sector_code}"
                )
            grouped.setdefault(membership.entity_id, []).append(membership)
        for entity_id, records in grouped.items():
            records.sort(key=lambda item: item.effective_from_period)
            for previous, current in zip(records, records[1:]):
                if previous.effective_to_period is None or current.effective_from_period <= previous.effective_to_period:
                    raise SFCSourceContractError(
                        f"overlapping sector membership for {entity_id}"
                    )

    @property
    def digest(self) -> str:
        records = [{
            "entity_id": item.entity_id,
            "sector_code": item.sector_code,
            "effective_from_period": item.effective_from_period,
            "effective_to_period": item.effective_to_period,
        } for item in sorted(
            self.memberships,
            key=lambda item: (item.entity_id, item.effective_from_period),
        )]
        return _canonical_digest({
            "version": self.version,
            "allowed_sector_codes": sorted(self.allowed_sector_codes),
            "memberships": records,
        })

    def resolve(self, entity_id: str, period: int) -> str:
        _text(entity_id, "entity_id")
        _period(period, "period")
        matches = [item for item in self.memberships
                   if item.entity_id == entity_id and item.active(period)]
        if len(matches) != 1:
            raise SFCSourceContractError(
                f"sector membership is missing or ambiguous for {entity_id} in period {period}"
            )
        return matches[0].sector_code


@dataclass(frozen=True)
class OpeningPosition:
    identity: SFCIdentity
    balance: str
    evidence_ref: str
    source_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.identity, SFCIdentity):
            raise SFCSourceContractError("opening identity must be an SFCIdentity")
        object.__setattr__(self, "balance", _balance(self.balance))
        _text(self.evidence_ref, "opening.evidence_ref")
        _text(self.source_ref, "opening.source_ref")


@dataclass(frozen=True)
class OpeningStockSnapshot:
    """Complete opening rows for one period, pinned to both registry digests."""

    version: str
    period_index: int
    instrument_registry_version: str
    instrument_registry_digest: str
    sector_registry_version: str
    sector_registry_digest: str
    expected_identities: tuple[SFCIdentity, ...]
    positions: tuple[OpeningPosition, ...]
    source_register_id: str | None = None
    source_sequence: int | None = None
    source_chain_hash: str | None = None

    def __post_init__(self) -> None:
        _text(self.version, "opening snapshot version")
        _period(self.period_index, "opening period_index")
        for field in (
            "instrument_registry_version", "instrument_registry_digest",
            "sector_registry_version", "sector_registry_digest",
        ):
            _text(getattr(self, field), f"opening.{field}")
        provenance = (
            self.source_register_id, self.source_sequence, self.source_chain_hash,
        )
        if any(value is not None for value in provenance):
            if any(value is None for value in provenance):
                raise SFCSourceContractError(
                    "opening snapshot source checkpoint must include register ID, sequence and chain hash"
                )
            _text(self.source_register_id, "opening snapshot source_register_id")
            if (not isinstance(self.source_sequence, int) or isinstance(self.source_sequence, bool)
                    or self.source_sequence < 1):
                raise SFCSourceContractError(
                    "opening snapshot source_sequence must be a positive integer"
                )
            if (not isinstance(self.source_chain_hash, str) or len(self.source_chain_hash) != 64
                    or any(char not in "0123456789abcdef" for char in self.source_chain_hash)):
                raise SFCSourceContractError(
                    "opening snapshot source_chain_hash must be a lowercase SHA-256 digest"
                )
        if not isinstance(self.expected_identities, tuple) or not self.expected_identities:
            raise SFCSourceContractError("opening snapshot must declare expected identities")
        if not isinstance(self.positions, tuple):
            raise SFCSourceContractError("opening positions must be a tuple")
        if any(not isinstance(item, SFCIdentity) for item in self.expected_identities):
            raise SFCSourceContractError("expected opening identities must be SFCIdentity values")
        if any(not isinstance(item, OpeningPosition) for item in self.positions):
            raise SFCSourceContractError("opening positions contain an invalid row")
        expected = set(self.expected_identities)
        if len(expected) != len(self.expected_identities):
            raise SFCSourceContractError("duplicate expected opening identity")
        actual = [item.identity for item in self.positions]
        if len(set(actual)) != len(actual):
            raise SFCSourceContractError("duplicate opening position")
        if set(actual) != expected:
            missing = len(expected - set(actual))
            extra = len(set(actual) - expected)
            raise SFCSourceContractError(
                f"opening snapshot is incomplete (missing={missing}, extra={extra})"
            )
        balances = {item.identity: Decimal(item.balance) for item in self.positions}
        for identity, balance in balances.items():
            mirror = SFCIdentity(
                instrument_id=identity.instrument_id,
                instrument_class=identity.instrument_class,
                holder_entity_id=identity.issuer_entity_id,
                holder_sector=identity.issuer_sector,
                issuer_entity_id=identity.holder_entity_id,
                issuer_sector=identity.holder_sector,
                currency=identity.currency,
                maturity=identity.maturity,
                denomination=identity.denomination,
                valuation_basis=identity.valuation_basis,
            )
            if mirror not in balances:
                raise SFCSourceContractError(
                    f"opening position has no bilateral mirror: {identity.instrument_id}"
                )
            if balances[mirror] != balance:
                raise SFCSourceContractError(
                    f"opening bilateral mirror balances differ: {identity.instrument_id}"
                )

    @property
    def digest(self) -> str:
        rows = [{
            "identity": item.identity.__dict__,
            "balance": item.balance,
            "evidence_ref": item.evidence_ref,
            "source_ref": item.source_ref,
        } for item in sorted(self.positions, key=lambda row: row.identity)]
        return _canonical_digest({
            "version": self.version,
            "period_index": self.period_index,
            "instrument_registry_version": self.instrument_registry_version,
            "instrument_registry_digest": self.instrument_registry_digest,
            "sector_registry_version": self.sector_registry_version,
            "sector_registry_digest": self.sector_registry_digest,
            "source_checkpoint": (
                None if self.source_register_id is None else {
                    "source_register_id": self.source_register_id,
                    "source_sequence": self.source_sequence,
                    "source_chain_hash": self.source_chain_hash,
                }
            ),
            "rows": rows,
        })

    def as_projection_openings(self) -> dict[tuple[SFCIdentity, int], str]:
        return {(item.identity, self.period_index): item.balance for item in self.positions}

    def validate_against(
        self,
        instrument_registry: InstrumentTermsRegistry,
        sector_registry: EffectiveDatedSectorRegistry,
    ) -> None:
        if instrument_registry.version != self.instrument_registry_version:
            raise SFCSourceContractError("opening snapshot instrument registry version mismatch")
        if instrument_registry.digest != self.instrument_registry_digest:
            raise SFCSourceContractError("opening snapshot instrument registry digest mismatch")
        if sector_registry.version != self.sector_registry_version:
            raise SFCSourceContractError("opening snapshot sector registry version mismatch")
        if sector_registry.digest != self.sector_registry_digest:
            raise SFCSourceContractError("opening snapshot sector registry digest mismatch")
        for row in self.positions:
            identity = row.identity
            terms = instrument_registry.resolve(identity.instrument_id, self.period_index)
            if terms.nonnegative_gross_position and Decimal(row.balance) < 0:
                raise SFCSourceContractError(
                    f"negative opening balance prohibited by terms for {identity.instrument_id}"
                )
            if (
                identity.instrument_class != terms.instrument_class
                or identity.denomination != terms.denomination
                or identity.currency != terms.currency
                or identity.valuation_basis != terms.valuation_basis
                or identity.maturity != terms.maturity
            ):
                raise SFCSourceContractError(
                    f"opening identity does not match pinned terms for {identity.instrument_id}"
                )
            if sector_registry.resolve(identity.holder_entity_id, self.period_index) != identity.holder_sector:
                raise SFCSourceContractError(
                    f"opening holder sector mismatch for {identity.holder_entity_id}"
                )
            if sector_registry.resolve(identity.issuer_entity_id, self.period_index) != identity.issuer_sector:
                raise SFCSourceContractError(
                    f"opening issuer sector mismatch for {identity.issuer_entity_id}"
                )


__all__ = [
    "SFCSourceContractError",
    "InstrumentTerms",
    "InstrumentTermsRegistry",
    "SectorMembership",
    "EffectiveDatedSectorRegistry",
    "OpeningPosition",
    "OpeningStockSnapshot",
]
