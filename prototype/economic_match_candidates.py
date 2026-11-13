"""Durable, tenant-scoped MatchCandidate lifecycle on the canonical event repository.

Candidates are routing suggestions only. This module never reserves inventory,
accepts an offer, creates a contract, transfers title, or moves funds.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json

from real_economy_event_bridge import EventBridgeConflict
from economic_registry import (
    AGGREGATE_TYPE, EconomicMarketplaceRegistry, RegistryError,
    _canonical, _required_text, _scope, _utc_now,
)
from economic_router import score_offer


POLICY_VERSION = "economic-router-match-v1"


def _fingerprint(value: dict) -> str:
    return sha256(_canonical(value).encode("utf-8")).hexdigest()


def _candidate_id(tenant_id: str, demand_id: str, offer_id: str) -> str:
    raw = json.dumps([tenant_id, demand_id, offer_id, POLICY_VERSION],
                     separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def _validate_time(value: datetime) -> datetime:
    if (not isinstance(value, datetime) or value.tzinfo is None
            or value.utcoffset() is None or value.utcoffset().total_seconds() != 0):
        raise RegistryError("occurred_at must be timezone-aware UTC")
    return value


class MatchCandidateStore:
    """Persist candidate lifecycle in the tenant's existing marketplace aggregate."""

    def __init__(self, registry: EconomicMarketplaceRegistry):
        if not isinstance(registry, EconomicMarketplaceRegistry):
            raise TypeError("registry must be an EconomicMarketplaceRegistry")
        self.registry = registry
        self.repository = registry.repository

    def _commit(self, *, tenant_id: str, candidate_id: str, event_type: str,
                command_id: str, idempotency_key: str, actor_id: str,
                authority_ref: str, correlation_id: str, occurred_at: datetime,
                expected_candidate: dict | None = None):
        tenant_id = _required_text(tenant_id, "tenant_id")
        candidate_id = _required_text(candidate_id, "candidate_id")
        command_id = _required_text(command_id, "command_id")
        idempotency_key = _required_text(idempotency_key, "idempotency_key")
        actor_id = _required_text(actor_id, "actor_id")
        authority_ref = _required_text(authority_ref, "authority_ref")
        correlation_id = _required_text(correlation_id, "correlation_id")
        occurred_at = _validate_time(occurred_at)
        self.registry.ensure_tenant(tenant_id)
        scoped_key = "marketplace:" + _scope(tenant_id, idempotency_key)
        scoped_command = "marketplace:" + _scope(tenant_id, command_id)
        prior = self.repository.lookup_receipt(scoped_key)
        if prior is not None:
            expected_version = self.repository.command_expected_version(scoped_key)
        else:
            expected_version, _ = self.repository.load_aggregate(AGGREGATE_TYPE, tenant_id)
        request = {
            "tenant_id": tenant_id, "candidate_id": candidate_id,
            "event_type": event_type, "candidate_identity": {
                "demand_id": (expected_candidate or {}).get("demand_id"),
                "offer_id": (expected_candidate or {}).get("offer_id"),
                "policy_version": (expected_candidate or {}).get("policy_version"),
                "demand_fingerprint": (expected_candidate or {}).get("demand_fingerprint"),
                "offer_fingerprint": (expected_candidate or {}).get("offer_fingerprint"),
            },
        }

        def transition(state):
            next_state = deepcopy(state)
            candidates = next_state.setdefault("candidates", {})
            current = candidates.get(candidate_id)
            if event_type == "marketplace.match_candidate.withdrawn":
                if current is None:
                    raise RegistryError("match candidate not found in this tenant")
                if current.get("status") == "withdrawn":
                    raise RegistryError("match candidate is already withdrawn")
                current["status"] = "withdrawn"
                current["updated_at"] = occurred_at.isoformat().replace("+00:00", "Z")
                entity = deepcopy(current)
                result_status = "withdrawn"
            elif event_type == "marketplace.match_candidate.staled":
                if current is None:
                    raise RegistryError("match candidate not found in this tenant")
                if current.get("status") != "active":
                    raise RegistryError("only active candidates can become stale")
                current["status"] = "stale"
                current["updated_at"] = occurred_at.isoformat().replace("+00:00", "Z")
                entity = deepcopy(current)
                result_status = "stale"
            else:
                candidate = deepcopy(expected_candidate)
                demand = next_state.get("demands", {}).get(candidate["demand_id"])
                offer = next_state.get("offers", {}).get(candidate["offer_id"])
                if demand is None or offer is None:
                    raise RegistryError("demand or offer disappeared before candidate commit")
                if demand.get("tenant_id") != tenant_id or offer.get("tenant_id") != tenant_id:
                    raise RegistryError("candidate sources must belong to the same tenant")
                if candidate["demand_fingerprint"] != _fingerprint(demand):
                    raise RegistryError("demand changed; rediscover matches before persisting")
                if candidate["offer_fingerprint"] != _fingerprint(offer):
                    raise RegistryError("offer changed; rediscover matches before persisting")
                match = score_offer(demand, offer, now=occurred_at)
                if match is None:
                    raise RegistryError("demand and offer are no longer compatible")
                candidate["match"] = match
                candidate["status"] = "active"
                candidate["updated_at"] = occurred_at.isoformat().replace("+00:00", "Z")
                candidate["last_seen_at"] = candidate["updated_at"]
                if current is not None:
                    candidate["created_at"] = current["created_at"]
                candidates[candidate_id] = candidate
                entity = deepcopy(candidate)
                result_status = "created" if current is None else "refreshed"
            raw = [{
                "event_id": sha256((scoped_key + ":" + event_type).encode()).hexdigest(),
                "event_type": event_type,
                "aggregate_id": tenant_id,
                "aggregate_version": expected_version + 1,
                "idempotency_key": scoped_key + ":" + event_type,
                "payload": {"tenant_id": tenant_id, "candidate": entity},
            }]
            return next_state, {"status": result_status, "candidate_id": candidate_id,
                                "tenant_id": tenant_id}, raw

        receipt = self.repository.execute(
            command_id=scoped_command, idempotency_key=scoped_key,
            request=request, aggregate_type=AGGREGATE_TYPE, aggregate_id=tenant_id,
            expected_version=expected_version, actor_id=actor_id,
            authority_ref=authority_ref, correlation_id=correlation_id,
            occurred_at=occurred_at, recorded_at=_utc_now(), transition=transition,
        )
        return receipt

    def persist_candidate(self, tenant_id: str, demand_id: str, offer_id: str, *,
                          command_id: str, idempotency_key: str, actor_id: str,
                          authority_ref: str, correlation_id: str,
                          occurred_at: datetime | None = None):
        tenant_id = _required_text(tenant_id, "tenant_id")
        demand_id = _required_text(demand_id, "demand_id")
        offer_id = _required_text(offer_id, "offer_id")
        occurred_at = _validate_time(occurred_at or _utc_now())
        _, state = self.registry._load(tenant_id)
        demand = state["demands"].get(demand_id)
        offer = state["offers"].get(offer_id)
        if demand is None or offer is None:
            raise RegistryError("demand or offer not found in this tenant")
        if demand.get("tenant_id") != tenant_id or offer.get("tenant_id") != tenant_id:
            raise RegistryError("candidate sources must belong to the same tenant")
        match = score_offer(demand, offer, now=occurred_at)
        if match is None:
            raise RegistryError("demand and offer are not currently compatible")
        candidate_id = _candidate_id(tenant_id, demand_id, offer_id)
        existing = state.get("candidates", {}).get(candidate_id)
        candidate = {
            "candidate_id": candidate_id, "tenant_id": tenant_id,
            "demand_id": demand_id, "offer_id": offer_id,
            "policy_version": POLICY_VERSION,
            "demand_fingerprint": _fingerprint(demand),
            "offer_fingerprint": _fingerprint(offer),
            "match": match, "status": "active",
            "created_at": (existing or {}).get("created_at",
                          occurred_at.isoformat().replace("+00:00", "Z")),
            "updated_at": occurred_at.isoformat().replace("+00:00", "Z"),
            "last_seen_at": occurred_at.isoformat().replace("+00:00", "Z"),
        }
        event_type = ("marketplace.match_candidate.refreshed" if existing
                      else "marketplace.match_candidate.created")
        return self._commit(
            tenant_id=tenant_id, candidate_id=candidate_id, event_type=event_type,
            command_id=command_id, idempotency_key=idempotency_key, actor_id=actor_id,
            authority_ref=authority_ref, correlation_id=correlation_id,
            occurred_at=occurred_at, expected_candidate=candidate,
        )

    def _lifecycle_command(self, tenant_id: str, candidate_id: str, action: str, *,
                           command_id: str, idempotency_key: str, actor_id: str,
                           authority_ref: str, correlation_id: str,
                           occurred_at: datetime | None = None):
        if action not in {"withdrawn", "staled"}:
            raise RegistryError("unsupported candidate lifecycle action")
        return self._commit(
            tenant_id=tenant_id, candidate_id=candidate_id,
            event_type=f"marketplace.match_candidate.{action}",
            command_id=command_id, idempotency_key=idempotency_key, actor_id=actor_id,
            authority_ref=authority_ref, correlation_id=correlation_id,
            occurred_at=_validate_time(occurred_at or _utc_now()),
        )

    def withdraw_candidate(self, tenant_id: str, candidate_id: str, **command):
        return self._lifecycle_command(tenant_id, candidate_id, "withdrawn", **command)

    def mark_stale(self, tenant_id: str, candidate_id: str, **command):
        return self._lifecycle_command(tenant_id, candidate_id, "staled", **command)

    def get_candidate(self, tenant_id: str, candidate_id: str):
        tenant_id = _required_text(tenant_id, "tenant_id")
        candidate_id = _required_text(candidate_id, "candidate_id")
        _, state = self.registry._load(tenant_id)
        candidate = state.get("candidates", {}).get(candidate_id)
        if candidate is None:
            return None
        result = deepcopy(candidate)
        demand = state.get("demands", {}).get(candidate["demand_id"])
        offer = state.get("offers", {}).get(candidate["offer_id"])
        sources_current = (
            demand is not None and offer is not None
            and _fingerprint(demand) == candidate["demand_fingerprint"]
            and _fingerprint(offer) == candidate["offer_fingerprint"]
        )
        currently_compatible = (
            sources_current and score_offer(demand, offer, now=_utc_now()) is not None
        )
        if not sources_current:
            result["freshness"] = "stale"
        elif not currently_compatible:
            result["freshness"] = "expired_or_incompatible"
        else:
            result["freshness"] = "current"
        if candidate.get("status") == "active" and not currently_compatible:
            result["effective_status"] = "stale"
        else:
            result["effective_status"] = candidate.get("status")
        return result

    def list_candidates(self, tenant_id: str, *, limit: int = 50):
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise RegistryError("limit must be between 1 and 100")
        tenant_id = _required_text(tenant_id, "tenant_id")
        _, state = self.registry._load(tenant_id)
        items = []
        for candidate_id in sorted(state.get("candidates", {})):
            item = self.get_candidate(tenant_id, candidate_id)
            if item is not None:
                items.append(item)
            if len(items) >= limit:
                break
        return tuple(items)
