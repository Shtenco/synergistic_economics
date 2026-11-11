"""P6.2a/b canonical event bridge and transactional in-memory coordinator.

Research/test reference only. This module reuses the existing prototype EventStore;
it does not create a second event log or claim durability across process failure.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from threading import RLock
from typing import Callable, Mapping

from synergy_kernel import EventStore, KernelError


class EventBridgeError(ValueError):
    """Invalid P6 canonical event or transaction."""


class EventBridgeConflict(EventBridgeError):
    """Idempotency or aggregate-version conflict."""


def _required_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise EventBridgeError(f"{field} must be a non-empty string")
    return value


def _utc(value, field):
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise EventBridgeError(f"{field} must be timezone-aware")
    if value.utcoffset().total_seconds() != 0:
        raise EventBridgeError(f"{field} must be expressed in UTC")
    return value.isoformat().replace("+00:00", "Z")


def canonical_json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EventBridgeError("payload is not canonical-JSON serializable") from exc


@dataclass(frozen=True)
class CanonicalEvent:
    schema_version: str
    event_id: str
    event_type: str
    aggregate_type: str
    aggregate_id: str
    aggregate_version: int
    event_ordinal: int
    occurred_at: str
    recorded_at: str
    actor_id: str
    authority_ref: str
    idempotency_key: str
    command_id: str
    correlation_id: str
    causation_id: str | None
    payload: dict
    evidence_refs: tuple[str, ...]
    payload_digest: str

    def as_dict(self):
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "event_type": self.event_type,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "aggregate_version": self.aggregate_version,
            "event_ordinal": self.event_ordinal,
            "occurred_at": self.occurred_at,
            "recorded_at": self.recorded_at,
            "actor_id": self.actor_id,
            "authority_ref": self.authority_ref,
            "idempotency_key": self.idempotency_key,
            "command_id": self.command_id,
            "correlation_id": self.correlation_id,
            "causation_id": self.causation_id,
            "payload": deepcopy(self.payload),
            "evidence_refs": list(self.evidence_refs),
            "payload_digest": self.payload_digest,
        }


def map_domain_event(event: Mapping, *, aggregate_type: str, actor_id: str,
                     authority_ref: str, command_id: str, correlation_id: str,
                     occurred_at: datetime, recorded_at: datetime,
                     evidence_refs=(), causation_id=None, event_ordinal=0):
    """Validate and enrich one P6.1 domain event without dropping its identity."""
    if not isinstance(event, Mapping):
        raise EventBridgeError("domain event must be a mapping")
    schema_version = "synergy.event.v1"
    event_id = _required_text(event.get("event_id"), "event_id")
    event_type = _required_text(event.get("event_type"), "event_type")
    aggregate_id = _required_text(event.get("aggregate_id"), "aggregate_id")
    idempotency_key = _required_text(event.get("idempotency_key"), "idempotency_key")
    aggregate_version = event.get("aggregate_version")
    if isinstance(aggregate_version, bool) or not isinstance(aggregate_version, int) or aggregate_version < 1:
        raise EventBridgeError("aggregate_version must be a positive integer")
    if isinstance(event_ordinal, bool) or not isinstance(event_ordinal, int) or event_ordinal < 0:
        raise EventBridgeError("event_ordinal must be a non-negative integer")
    payload = event.get("payload")
    if not isinstance(payload, Mapping):
        raise EventBridgeError("payload must be a mapping")
    payload_copy = deepcopy(dict(payload))
    payload_digest = sha256(canonical_json(payload_copy).encode("utf-8")).hexdigest()
    refs = tuple(_required_text(x, "evidence_ref") for x in evidence_refs)
    if len(set(refs)) != len(refs):
        raise EventBridgeError("evidence_refs must be unique")
    return CanonicalEvent(
        schema_version=schema_version,
        event_id=event_id,
        event_type=event_type,
        aggregate_type=_required_text(aggregate_type, "aggregate_type"),
        aggregate_id=aggregate_id,
        aggregate_version=aggregate_version,
        event_ordinal=event_ordinal,
        occurred_at=_utc(occurred_at, "occurred_at"),
        recorded_at=_utc(recorded_at, "recorded_at"),
        actor_id=_required_text(actor_id, "actor_id"),
        authority_ref=_required_text(authority_ref, "authority_ref"),
        idempotency_key=idempotency_key,
        command_id=_required_text(command_id, "command_id"),
        correlation_id=_required_text(correlation_id, "correlation_id"),
        causation_id=None if causation_id is None else _required_text(causation_id, "causation_id"),
        payload=payload_copy,
        evidence_refs=refs,
        payload_digest=payload_digest,
    )


@dataclass(frozen=True)
class TransactionReceipt:
    command_id: str
    request_fingerprint: str
    result: object
    events: tuple[CanonicalEvent, ...]


class InMemoryAtomicCoordinator:
    """Atomic in-process coordinator for tests; not durable or cross-process safe.

    transition receives a deep-copied current state and returns
    (candidate_state, result, raw_domain_events). All events are validated and
    appended to the existing EventStore before the candidate state is published.
    If any append fails, the EventStore's in-memory collections are restored.
    All writers must use this coordinator's lock; direct EventStore writers
    invalidate the single-writer assumption.
    """

    def __init__(self, initial_state, event_store: EventStore | None = None):
        self._state = deepcopy(initial_state)
        self.event_store = event_store if event_store is not None else EventStore()
        self._receipts = {}
        self._aggregate_versions = {}
        self._lock = RLock()

    @property
    def state(self):
        with self._lock:
            return deepcopy(self._state)

    def aggregate_version(self, aggregate_type, aggregate_id):
        with self._lock:
            return self._aggregate_versions.get((aggregate_type, aggregate_id), 0)

    def execute(self, *, command_id, idempotency_key, request,
                aggregate_type, aggregate_id, expected_version, actor_id,
                authority_ref, correlation_id, occurred_at, recorded_at,
                transition: Callable, evidence_refs=(), causation_id=None,
                fail_after_event_append=None):
        command_id = _required_text(command_id, "command_id")
        idempotency_key = _required_text(idempotency_key, "idempotency_key")
        aggregate_type = _required_text(aggregate_type, "aggregate_type")
        aggregate_id = _required_text(aggregate_id, "aggregate_id")
        fingerprint_input = {
            "command_id": command_id, "request": request,
            "aggregate_type": aggregate_type, "aggregate_id": aggregate_id,
            "expected_version": expected_version, "actor_id": actor_id,
            "authority_ref": authority_ref, "correlation_id": correlation_id,
            "occurred_at": _utc(occurred_at, "occurred_at"),
            "recorded_at": _utc(recorded_at, "recorded_at"),
            "evidence_refs": list(evidence_refs),
            "causation_id": causation_id,
        }
        request_fingerprint = sha256(canonical_json(fingerprint_input).encode("utf-8")).hexdigest()
        receipt_key = idempotency_key
        with self._lock:
            prior = self._receipts.get(receipt_key)
            if prior is not None:
                if prior.request_fingerprint != request_fingerprint:
                    raise EventBridgeConflict("idempotency key reused with a different command or request")
                return prior
            current_version = self._aggregate_versions.get((aggregate_type, aggregate_id), 0)
            if expected_version != current_version:
                raise EventBridgeConflict(
                    f"stale aggregate version: expected {expected_version}, current {current_version}"
                )
            candidate_state, result, raw_events = transition(deepcopy(self._state))
            if not isinstance(raw_events, (list, tuple)) or not raw_events:
                raise EventBridgeError("a successful state transition must emit at least one event")
            mapped = tuple(
                map_domain_event(
                    raw, aggregate_type=aggregate_type, actor_id=actor_id,
                    authority_ref=authority_ref, command_id=command_id,
                    correlation_id=correlation_id, occurred_at=occurred_at,
                    recorded_at=recorded_at, evidence_refs=evidence_refs,
                    causation_id=causation_id, event_ordinal=i,
                ) for i, raw in enumerate(raw_events)
            )
            if any(e.aggregate_id != aggregate_id for e in mapped):
                raise EventBridgeError("event aggregate_id does not match command aggregate")
            if any(e.aggregate_version != current_version + 1 for e in mapped):
                raise EventBridgeError("all events in one command must share next aggregate version")
            if len({e.event_id for e in mapped}) != len(mapped):
                raise EventBridgeError("duplicate event_id inside command")
            if len({e.idempotency_key for e in mapped}) != len(mapped):
                raise EventBridgeError("duplicate event idempotency_key inside command")

            # Stage all canonical EventStore mutations; rollback on any failure.
            old_events = list(self.event_store.events)
            old_ids = set(self.event_store._ids)
            old_keys = set(self.event_store._keys)
            try:
                for index, event in enumerate(mapped, start=1):
                    payload = event.as_dict()
                    self.event_store.append(
                        event.event_id, event.event_type, payload, event.idempotency_key
                    )
                    if fail_after_event_append == index:
                        raise RuntimeError("injected failure after event append")
            except Exception:
                self.event_store.events[:] = old_events
                self.event_store._ids.clear()
                self.event_store._ids.update(old_ids)
                self.event_store._keys.clear()
                self.event_store._keys.update(old_keys)
                raise

            # Publish aggregate state and receipt only after all appends succeed.
            self._state = deepcopy(candidate_state)
            self._aggregate_versions[(aggregate_type, aggregate_id)] = current_version + 1
            receipt = TransactionReceipt(command_id, request_fingerprint, deepcopy(result), mapped)
            self._receipts[receipt_key] = receipt
            return receipt
