"""Dependency-free spatial event boundary for the SYNERGY economic model.

This adapter validates provenance and keeps physical quantities separate from
financial posting references. It does not post journals or mutate economic state.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
import math
from typing import Any


class SpatialBridgeError(ValueError):
    """Raised when a spatial/economic event violates its contract."""


def _required_text(value: str, field_name: str, max_length: int = 256) -> str:
    if not isinstance(value, str):
        raise SpatialBridgeError(f"{field_name} must be text")
    value = value.strip()
    if not value or len(value) > max_length:
        raise SpatialBridgeError(f"{field_name} is required and must be <= {max_length} characters")
    return value


def _finite_decimal(value: Any, field_name: str) -> Decimal:
    if isinstance(value, bool):
        raise SpatialBridgeError(f"{field_name} must be numeric, not boolean")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise SpatialBridgeError(f"{field_name} must be a finite decimal") from exc
    if not parsed.is_finite():
        raise SpatialBridgeError(f"{field_name} must be finite")
    return parsed


def _aware_datetime(value: str) -> str:
    value = _required_text(value, "occurred_at", 64)
    candidate = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError as exc:
        raise SpatialBridgeError("occurred_at must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SpatialBridgeError("occurred_at must include a timezone")
    return value


@dataclass(frozen=True)
class GeoPoint:
    longitude: float
    latitude: float
    crs: str = "EPSG:4326"
    altitude_m: float | None = None

    def __post_init__(self) -> None:
        if self.crs != "EPSG:4326":
            raise SpatialBridgeError("GeoPoint currently accepts EPSG:4326 only")
        for name, value, lower, upper in (
            ("longitude", self.longitude, -180.0, 180.0),
            ("latitude", self.latitude, -90.0, 90.0),
        ):
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise SpatialBridgeError(f"{name} must be numeric")
            if not math.isfinite(float(value)) or not lower <= float(value) <= upper:
                raise SpatialBridgeError(f"{name} is outside EPSG:4326 bounds")
        if self.altitude_m is not None:
            if isinstance(self.altitude_m, bool) or not isinstance(self.altitude_m, (int, float)):
                raise SpatialBridgeError("altitude_m must be numeric or None")
            if not math.isfinite(float(self.altitude_m)):
                raise SpatialBridgeError("altitude_m must be finite")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "longitude": float(self.longitude),
            "latitude": float(self.latitude),
            "crs": self.crs,
        }
        if self.altitude_m is not None:
            result["altitudeM"] = float(self.altitude_m)
        return result


@dataclass(frozen=True)
class PhysicalFlow:
    flow_id: str
    commodity: str
    quantity: Decimal
    unit: str
    origin_cell_id: str | None = None
    destination_cell_id: str | None = None
    period: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "flow_id", _required_text(self.flow_id, "flow_id"))
        object.__setattr__(self, "commodity", _required_text(self.commodity, "commodity"))
        object.__setattr__(self, "unit", _required_text(self.unit, "unit", 64))
        quantity = _finite_decimal(self.quantity, "quantity")
        if quantity < 0:
            raise SpatialBridgeError("quantity cannot be negative")
        object.__setattr__(self, "quantity", quantity)
        if self.origin_cell_id is not None:
            object.__setattr__(self, "origin_cell_id", _required_text(self.origin_cell_id, "origin_cell_id"))
        if self.destination_cell_id is not None:
            object.__setattr__(self, "destination_cell_id", _required_text(self.destination_cell_id, "destination_cell_id"))
        if self.origin_cell_id is None and self.destination_cell_id is None:
            raise SpatialBridgeError("physical flow requires an origin or destination cell")
        if self.period is not None:
            object.__setattr__(self, "period", _required_text(self.period, "period", 64))

    def to_dict(self) -> dict[str, Any]:
        return {
            "flowId": self.flow_id,
            "commodity": self.commodity,
            "quantity": str(self.quantity),
            "unit": self.unit,
            "originCellId": self.origin_cell_id,
            "destinationCellId": self.destination_cell_id,
            "period": self.period,
        }


@dataclass(frozen=True)
class FinancialPostingRef:
    journal_entry_id: str
    debit_account: str
    credit_account: str
    amount: Decimal
    currency: str
    status: str = "pending"

    def __post_init__(self) -> None:
        for name in ("journal_entry_id", "debit_account", "credit_account"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if self.debit_account == self.credit_account:
            raise SpatialBridgeError("debit_account and credit_account must differ")
        amount = _finite_decimal(self.amount, "financial amount")
        if amount <= 0:
            raise SpatialBridgeError("financial amount must be positive")
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", _required_text(self.currency, "currency", 12).upper())
        if self.status not in {"pending", "settled", "reversed"}:
            raise SpatialBridgeError("financial posting status is invalid")

    def to_dict(self) -> dict[str, str]:
        return {
            "journalEntryId": self.journal_entry_id,
            "debitAccount": self.debit_account,
            "creditAccount": self.credit_account,
            "amount": str(self.amount),
            "currency": self.currency,
            "status": self.status,
        }


@dataclass(frozen=True)
class SourceEvidence:
    source_id: str
    source_name: str
    source_version: str
    license: str
    evidence_type: str
    retrieved_at: str
    source_url: str | None = None
    attribution_text: str = ""
    confidence: float | None = None

    def __post_init__(self) -> None:
        for name in ("source_id", "source_name", "source_version", "license"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        if self.evidence_type not in {"observed", "derived", "simulated", "forecast", "demo"}:
            raise SpatialBridgeError("evidence_type is invalid")
        object.__setattr__(self, "retrieved_at", _aware_datetime(self.retrieved_at))
        if self.source_url is not None:
            object.__setattr__(self, "source_url", _required_text(self.source_url, "source_url", 2048))
        if not isinstance(self.attribution_text, str):
            raise SpatialBridgeError("attribution_text must be text")
        if self.confidence is not None:
            if isinstance(self.confidence, bool) or not isinstance(self.confidence, (int, float)):
                raise SpatialBridgeError("confidence must be numeric or None")
            if not math.isfinite(float(self.confidence)) or not 0 <= float(self.confidence) <= 1:
                raise SpatialBridgeError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "sourceId": self.source_id,
            "sourceName": self.source_name,
            "sourceVersion": self.source_version,
            "license": self.license,
            "evidenceType": self.evidence_type,
            "retrievedAt": self.retrieved_at,
            "attributionText": self.attribution_text,
        }
        if self.source_url is not None:
            result["sourceUrl"] = self.source_url
        if self.confidence is not None:
            result["confidence"] = float(self.confidence)
        return result


@dataclass(frozen=True)
class SpatialEconomicEvent:
    event_id: str
    idempotency_key: str
    event_type: str
    occurred_at: str
    region_id: str
    cell_id: str
    source: SourceEvidence
    data_classification: str
    physical_flow: PhysicalFlow | None = None
    financial_posting: FinancialPostingRef | None = None
    facility_id: str | None = None
    location: GeoPoint | None = None
    scenario_run_id: str | None = None
    related_event_ids: tuple[str, ...] = ()
    schema_version: str = "1.0"

    ALLOWED_EVENT_TYPES = frozenset({
        "production.completed", "shipment.dispatched", "inventory.adjusted",
        "resource.consumed", "service.delivered", "investment.committed", "price.observed",
    })
    ALLOWED_CLASSIFICATIONS = frozenset({"public", "aggregate", "confidential"})

    def __post_init__(self) -> None:
        for name in ("event_id", "idempotency_key", "region_id", "cell_id"):
            object.__setattr__(self, name, _required_text(getattr(self, name), name))
        object.__setattr__(self, "occurred_at", _aware_datetime(self.occurred_at))
        if self.schema_version != "1.0":
            raise SpatialBridgeError("unsupported schema_version")
        if self.event_type not in self.ALLOWED_EVENT_TYPES:
            raise SpatialBridgeError("event_type is invalid")
        if self.data_classification not in self.ALLOWED_CLASSIFICATIONS:
            raise SpatialBridgeError("data_classification is invalid")
        if not isinstance(self.source, SourceEvidence):
            raise SpatialBridgeError("source must be SourceEvidence")
        if self.physical_flow is not None and not isinstance(self.physical_flow, PhysicalFlow):
            raise SpatialBridgeError("physical_flow must be PhysicalFlow or None")
        if self.financial_posting is not None and not isinstance(self.financial_posting, FinancialPostingRef):
            raise SpatialBridgeError("financial_posting must be FinancialPostingRef or None")
        if self.location is not None and not isinstance(self.location, GeoPoint):
            raise SpatialBridgeError("location must be GeoPoint or None")
        if self.physical_flow is None and self.financial_posting is None:
            raise SpatialBridgeError("event must contain a physical flow and/or financial posting")
        if self.facility_id is not None:
            object.__setattr__(self, "facility_id", _required_text(self.facility_id, "facility_id"))
        if self.scenario_run_id is not None:
            object.__setattr__(self, "scenario_run_id", _required_text(self.scenario_run_id, "scenario_run_id"))
        normalized = tuple(_required_text(x, "related_event_id") for x in self.related_event_ids)
        if len(set(normalized)) != len(normalized):
            raise SpatialBridgeError("related_event_ids must be unique")
        object.__setattr__(self, "related_event_ids", normalized)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "schemaVersion": self.schema_version,
            "eventId": self.event_id,
            "idempotencyKey": self.idempotency_key,
            "eventType": self.event_type,
            "occurredAt": self.occurred_at,
            "regionId": self.region_id,
            "cellId": self.cell_id,
            "source": self.source.to_dict(),
            "dataClassification": self.data_classification,
            "relatedEventIds": list(self.related_event_ids),
        }
        if self.physical_flow is not None:
            result["physicalFlow"] = self.physical_flow.to_dict()
        if self.financial_posting is not None:
            result["financialPosting"] = self.financial_posting.to_dict()
        if self.facility_id is not None:
            result["facilityId"] = self.facility_id
        if self.location is not None:
            result["location"] = self.location.to_dict()
        if self.scenario_run_id is not None:
            result["scenarioRunId"] = self.scenario_run_id
        return result


class SpatialEventRegistry:
    """In-memory idempotency boundary; not a persistent event store."""

    def __init__(self) -> None:
        self._events: list[SpatialEconomicEvent] = []
        self._event_ids: set[str] = set()
        self._idempotency_keys: set[str] = set()

    def append(self, event: SpatialEconomicEvent) -> SpatialEconomicEvent:
        if not isinstance(event, SpatialEconomicEvent):
            raise SpatialBridgeError("event must be a SpatialEconomicEvent")
        if event.event_id in self._event_ids:
            raise SpatialBridgeError("duplicate event_id")
        if event.idempotency_key in self._idempotency_keys:
            raise SpatialBridgeError("duplicate idempotency_key")
        self._events.append(event)
        self._event_ids.add(event.event_id)
        self._idempotency_keys.add(event.idempotency_key)
        return event

    def replay(self) -> tuple[SpatialEconomicEvent, ...]:
        return tuple(self._events)

    def __len__(self) -> int:
        return len(self._events)
