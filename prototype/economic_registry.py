"""Tenant-scoped demand and offer registry backed by the canonical SQLite event repository.

This is a projection/aggregate adapter, not a second event store. Each tenant's
marketplace registry is one aggregate in SQLiteEventRepository; all changes
therefore use its atomic event + projection + receipt + outbox transaction.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any

from real_economy_event_bridge import EventBridgeConflict
from sqlite_event_repository import SQLiteEventRepository
from economic_router import RouterValidationError, validate_demand, validate_offer


AGGREGATE_TYPE = "economic_marketplace_tenant"


class RegistryError(ValueError):
    """Marketplace registry validation or authority error."""


def _canonical(value: Any) -> str:
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RegistryError("registry data must be canonical JSON") from exc


def _required_text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise RegistryError(f"{field} must be trimmed non-empty text")
    return value


def _scope(tenant_id: str, value: str) -> str:
    return sha256((tenant_id + "\\0" + value).encode("utf-8")).hexdigest()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _registry_state() -> dict:
    return {"schema_id": "synergy.economic-router.registry-state",
            "schema_version": 1, "demands": {}, "offers": {}}


class EconomicMarketplaceRegistry:
    """Persist tenant-isolated demands/offers through SQLiteEventRepository."""

    def __init__(self, repository: SQLiteEventRepository):
        if not isinstance(repository, SQLiteEventRepository):
            raise TypeError("repository must be the canonical SQLiteEventRepository")
        self.repository = repository

    def ensure_tenant(self, tenant_id: str) -> None:
        tenant_id = _required_text(tenant_id, "tenant_id")
        try:
            self.repository.register_aggregate(AGGREGATE_TYPE, tenant_id, _registry_state())
        except EventBridgeConflict:
            # Existing tenant aggregate is the durable source of truth.
            version, state = self.repository.load_aggregate(AGGREGATE_TYPE, tenant_id)
            if (not isinstance(state, dict)
                    or state.get("schema_id") != "synergy.economic-router.registry-state"
                    or state.get("schema_version") != 1
                    or not isinstance(state.get("demands"), dict)
                    or not isinstance(state.get("offers"), dict)):
                raise RegistryError("tenant registry aggregate has an unsupported state schema")

    def _load(self, tenant_id: str):
        self.ensure_tenant(tenant_id)
        return self.repository.load_aggregate(AGGREGATE_TYPE, tenant_id)

    def _execute(self, *, tenant_id: str, command_id: str, idempotency_key: str,
                 request: dict, actor_id: str, authority_ref: str,
                 correlation_id: str, occurred_at: datetime | None = None):
        tenant_id = _required_text(tenant_id, "tenant_id")
        command_id = _required_text(command_id, "command_id")
        idempotency_key = _required_text(idempotency_key, "idempotency_key")
        actor_id = _required_text(actor_id, "actor_id")
        authority_ref = _required_text(authority_ref, "authority_ref")
        correlation_id = _required_text(correlation_id, "correlation_id")
        occurred_at = occurred_at or _utc_now()
        if (not isinstance(occurred_at, datetime) or occurred_at.tzinfo is None
                or occurred_at.utcoffset() is None or occurred_at.utcoffset().total_seconds() != 0):
            raise RegistryError("occurred_at must be timezone-aware UTC")
        self.ensure_tenant(tenant_id)
        scoped_key = "marketplace:" + _scope(tenant_id, idempotency_key)
        scoped_command = "marketplace:" + _scope(tenant_id, command_id)
        # A retry must reuse the original expected version even if later commands
        # have advanced this tenant aggregate.
        prior = self.repository.lookup_receipt(scoped_key)
        if prior is not None:
            expected_version = self.repository.command_expected_version(scoped_key)
        else:
            expected_version, _ = self.repository.load_aggregate(AGGREGATE_TYPE, tenant_id)
        request_fingerprint_payload = {"tenant_id": tenant_id, **request}

        def transition(state):
            candidate = deepcopy(state)
            event = request["event"]
            event_type = event["event_type"]
            entity = deepcopy(event["entity"])
            collection = event["collection"]
            entity_id = event["entity_id"]
            current = candidate[collection].get(entity_id)
            duplicate_source = None
            if (event_type == "marketplace.demand.registered"
                    and entity.get("source_fingerprint")):
                duplicate_source = next(
                    (item for item in candidate["demands"].values()
                     if item.get("source_fingerprint") == entity["source_fingerprint"]),
                    None,
                )
            if event_type == "marketplace.demand.registered" and duplicate_source is not None:
                event_type = "marketplace.demand.duplicate_detected"
                result = {"status": "duplicate", "existing_id": duplicate_source["demand_id"]}
                payload = {"tenant_id": tenant_id, "duplicate_of": duplicate_source["demand_id"],
                           "source_fingerprint": entity.get("source_fingerprint")}
            elif event_type.endswith(".registered") and current is not None:
                raise RegistryError(f"{collection[:-1]} already exists")
            elif event_type.endswith(".duplicate_detected"):
                # Duplicate source signal is recorded as a non-mutating audit event.
                existing_id = current.get("demand_id") if current else None
                if existing_id is None:
                    raise RegistryError("duplicate source target disappeared; retry against current state")
                result = {"status": "duplicate", "existing_id": existing_id}
                payload = {"tenant_id": tenant_id, "duplicate_of": existing_id,
                           "source_fingerprint": entity.get("source_fingerprint")}
            else:
                candidate[collection][entity_id] = entity
                result = {"status": "registered", "id": entity_id,
                          "tenant_id": tenant_id}
                payload = {"tenant_id": tenant_id, "entity": entity}
            raw = [{
                "event_id": sha256((scoped_key + ":" + event_type).encode()).hexdigest(),
                "event_type": event_type,
                "aggregate_id": tenant_id,
                "aggregate_version": expected_version + 1,
                "idempotency_key": scoped_key + ":" + event_type,
                "payload": payload,
            }]
            return candidate, result, raw

        receipt = self.repository.execute(
            command_id=scoped_command,
            idempotency_key=scoped_key,
            request=request_fingerprint_payload,
            aggregate_type=AGGREGATE_TYPE,
            aggregate_id=tenant_id,
            expected_version=expected_version,
            actor_id=actor_id,
            authority_ref=authority_ref,
            correlation_id=correlation_id,
            occurred_at=occurred_at,
            recorded_at=_utc_now(),
            transition=transition,
        )
        return receipt

    def register_demand(self, demand: dict, *, command_id: str, idempotency_key: str,
                        actor_id: str, authority_ref: str, correlation_id: str,
                        occurred_at: datetime | None = None):
        try:
            validate_demand(demand)
        except RouterValidationError as exc:
            raise RegistryError(str(exc)) from exc
        tenant_id = demand["tenant_id"]
        entity = deepcopy(demand)
        fingerprint = entity.get("source_fingerprint")
        version, state = self._load(tenant_id)
        duplicate = None
        if fingerprint:
            duplicate = next((item for item in state["demands"].values()
                              if item.get("source_fingerprint") == fingerprint), None)
        if duplicate:
            event = {"event_type": "marketplace.demand.duplicate_detected",
                     "collection": "demands", "entity_id": duplicate["demand_id"],
                     "entity": entity}
        else:
            event = {"event_type": "marketplace.demand.registered",
                     "collection": "demands", "entity_id": entity["demand_id"],
                     "entity": entity}
        request = {"event": event, "entity_type": "demand"}
        return self._execute(tenant_id=tenant_id, command_id=command_id,
                             idempotency_key=idempotency_key, request=request,
                             actor_id=actor_id, authority_ref=authority_ref,
                             correlation_id=correlation_id, occurred_at=occurred_at)

    def register_offer(self, offer: dict, *, command_id: str, idempotency_key: str,
                       actor_id: str, authority_ref: str, correlation_id: str,
                       occurred_at: datetime | None = None):
        try:
            validate_offer(offer)
        except RouterValidationError as exc:
            raise RegistryError(str(exc)) from exc
        tenant_id = offer["tenant_id"]
        entity = deepcopy(offer)
        request = {"event": {"event_type": "marketplace.offer.registered",
                             "collection": "offers", "entity_id": entity["offer_id"],
                             "entity": entity},
                   "entity_type": "offer"}
        return self._execute(tenant_id=tenant_id, command_id=command_id,
                             idempotency_key=idempotency_key, request=request,
                             actor_id=actor_id, authority_ref=authority_ref,
                             correlation_id=correlation_id, occurred_at=occurred_at)

    def get_demand(self, tenant_id: str, demand_id: str):
        tenant_id = _required_text(tenant_id, "tenant_id")
        demand_id = _required_text(demand_id, "demand_id")
        _, state = self._load(tenant_id)
        value = state["demands"].get(demand_id)
        return None if value is None else deepcopy(value)

    def get_offer(self, tenant_id: str, offer_id: str):
        tenant_id = _required_text(tenant_id, "tenant_id")
        offer_id = _required_text(offer_id, "offer_id")
        _, state = self._load(tenant_id)
        value = state["offers"].get(offer_id)
        return None if value is None else deepcopy(value)

    def list_open_demands(self, tenant_id: str):
        _, state = self._load(_required_text(tenant_id, "tenant_id"))
        return tuple(deepcopy(state["demands"][key]) for key in sorted(state["demands"])
                     if state["demands"][key].get("status") == "open")

    def list_active_offers(self, tenant_id: str):
        _, state = self._load(_required_text(tenant_id, "tenant_id"))
        return tuple(deepcopy(state["offers"][key]) for key in sorted(state["offers"])
                     if state["offers"][key].get("status") == "active")

    def tenant_version(self, tenant_id: str) -> int:
        version, _ = self._load(_required_text(tenant_id, "tenant_id"))
        return version
