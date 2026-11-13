"""Deterministic, non-custodial economic demand-to-offer routing.

This module ranks compatible offers. It does not create contracts, authorize
payments, establish title, verify legal identity, or post accounting entries.
All amounts are integer minor units; floats are rejected.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Iterable


class RouterValidationError(ValueError):
    """A demand or offer violates the v1 routing contract."""


def _text(record: dict[str, Any], key: str) -> str:
    value = record.get(key)
    if not isinstance(value, str) or not value.strip():
        raise RouterValidationError(f"{key} must be non-empty text")
    return value.strip()


def _utc(value: Any, key: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise RouterValidationError(f"{key} must be an ISO-8601 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise RouterValidationError(f"{key} must be a valid ISO-8601 timestamp") from exc
    if parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise RouterValidationError(f"{key} must be UTC")
    return parsed


def _money(record: Any, key: str) -> tuple[int, str, int]:
    if not isinstance(record, dict):
        raise RouterValidationError(f"{key} must be an object")
    amount = record.get("amount_minor")
    scale = record.get("scale")
    currency = record.get("currency")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise RouterValidationError(f"{key}.amount_minor must be a non-negative integer")
    if isinstance(scale, bool) or not isinstance(scale, int) or not 0 <= scale <= 6:
        raise RouterValidationError(f"{key}.scale must be an integer from 0 to 6")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or currency.upper() != currency:
        raise RouterValidationError(f"{key}.currency must be a three-letter uppercase code")
    return amount, currency, scale


def validate_demand(demand: dict[str, Any]) -> None:
    if not isinstance(demand, dict):
        raise RouterValidationError("demand must be an object")
    if demand.get("schema_id") != "synergy.economic-router.demand" or isinstance(demand.get("schema_version"), bool) or demand.get("schema_version") != 1:
        raise RouterValidationError("unsupported demand schema")
    for key in ("demand_id", "buyer_id", "category", "jurisdiction", "tenant_id", "consent_ref"):
        _text(demand, key)
    if demand.get("status") != "open":
        raise RouterValidationError("demand.status must be open")
    requirements = demand.get("requirements", [])
    if not isinstance(requirements, list) or any(not isinstance(x, str) or not x.strip() for x in requirements):
        raise RouterValidationError("requirements must be a list of non-empty strings")
    quantity = demand.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise RouterValidationError("quantity must be a positive integer")
    _money(demand.get("budget"), "budget")
    _utc(demand.get("expires_at"), "expires_at")


def validate_offer(offer: dict[str, Any]) -> None:
    if not isinstance(offer, dict):
        raise RouterValidationError("offer must be an object")
    if offer.get("schema_id") != "synergy.economic-router.offer" or isinstance(offer.get("schema_version"), bool) or offer.get("schema_version") != 1:
        raise RouterValidationError("unsupported offer schema")
    for key in ("offer_id", "seller_id", "category", "jurisdiction", "tenant_id"):
        _text(offer, key)
    if offer.get("status") != "active":
        raise RouterValidationError("offer.status must be active")
    if offer.get("seller_verification") != "verified":
        raise RouterValidationError("seller_verification must be verified")
    capabilities = offer.get("capabilities", [])
    if not isinstance(capabilities, list) or any(not isinstance(x, str) or not x.strip() for x in capabilities):
        raise RouterValidationError("capabilities must be a list of non-empty strings")
    capacity = offer.get("capacity", 1)
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise RouterValidationError("capacity must be a positive integer")
    _money(offer.get("price"), "price")
    _utc(offer.get("expires_at"), "expires_at")
    evidence = offer.get("evidence_refs", [])
    if not isinstance(evidence, list) or any(not isinstance(x, str) or not x.strip() for x in evidence):
        raise RouterValidationError("evidence_refs must be a list of non-empty strings")


def _fingerprint(demand_id: str, offer_id: str) -> str:
    raw = json.dumps([demand_id, offer_id, "economic-router-match-v1"],
                     separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def score_offer(demand: dict[str, Any], offer: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any] | None:
    """Return a deterministic compatible match, or None for an incompatible offer."""
    validate_demand(demand)
    validate_offer(offer)
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise RouterValidationError("now must be timezone-aware")
    if _utc(demand["expires_at"], "demand.expires_at") <= now:
        return None
    if _utc(offer["expires_at"], "offer.expires_at") <= now:
        return None
    if demand["tenant_id"] != offer["tenant_id"]:
        return None
    if demand["category"] != offer["category"]:
        return None
    if demand["jurisdiction"] != offer["jurisdiction"]:
        return None
    budget, budget_currency, budget_scale = _money(demand["budget"], "budget")
    price, price_currency, price_scale = _money(offer["price"], "price")
    if (budget_currency, budget_scale) != (price_currency, price_scale) or price > budget:
        return None
    quantity = demand.get("quantity", 1)
    if offer.get("capacity", 1) < quantity:
        return None
    required = set(demand.get("requirements", []))
    available = set(offer.get("capabilities", []))
    if not required.issubset(available):
        return None
    # Score is intentionally explainable: capability coverage and budget fit.
    price_fit_bps = 10_000 if budget == 0 and price == 0 else (
        max(0, 10_000 - (price * 10_000 // max(budget, 1)))
    )
    score_bps = min(10_000, 7_000 + (len(required) * 300) + price_fit_bps // 5)
    return {
        "match_id": _fingerprint(demand["demand_id"], offer["offer_id"]),
        "demand_id": demand["demand_id"],
        "offer_id": offer["offer_id"],
        "buyer_id": demand["buyer_id"],
        "seller_id": offer["seller_id"],
        "score_bps": score_bps,
        "price": {"amount_minor": price, "currency": price_currency, "scale": price_scale},
        "matched_at": now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "decision": "candidate",
        "explanation": {
            "category_match": True,
            "jurisdiction_match": True,
            "currency_and_scale_match": True,
            "within_budget": True,
            "capacity_sufficient": True,
            "required_capabilities_covered": sorted(required),
        },
        "authority": "routing_only",
    }


def route_demand(demand: dict[str, Any], offers: Iterable[dict[str, Any]], *,
                 now: datetime | None = None, limit: int = 20) -> list[dict[str, Any]]:
    """Rank offers without side effects; callers persist commands through the canonical event boundary."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise RouterValidationError("limit must be a positive integer")
    validate_demand(demand)
    now = now or datetime.now(timezone.utc)
    if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
        raise RouterValidationError("now must be timezone-aware")
    matches = []
    seen_offers = set()
    for offer in offers:
        validate_offer(offer)
        if offer["offer_id"] in seen_offers:
            continue
        seen_offers.add(offer["offer_id"])
        match = score_offer(demand, offer, now=now)
        if match is not None:
            matches.append(match)
    matches.sort(key=lambda item: (-item["score_bps"], item["price"]["amount_minor"],
                                   item["seller_id"], item["offer_id"]))
    return matches[:limit]
