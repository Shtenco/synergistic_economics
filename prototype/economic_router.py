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
    if set(record) != {"amount_minor", "currency", "scale"}:
        raise RouterValidationError(f"{key} must contain only amount_minor, currency and scale")
    amount, scale, currency = record["amount_minor"], record["scale"], record["currency"]
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise RouterValidationError(f"{key}.amount_minor must be a non-negative integer")
    if isinstance(scale, bool) or not isinstance(scale, int) or not 0 <= scale <= 6:
        raise RouterValidationError(f"{key}.scale must be an integer from 0 to 6")
    if (not isinstance(currency, str) or len(currency) != 3 or not currency.isascii()
            or not currency.isalpha() or currency.upper() != currency):
        raise RouterValidationError(f"{key}.currency must be a three-letter uppercase code")
    return amount, currency, scale


def _unique_text_list(value: Any, key: str) -> list[str]:
    if (not isinstance(value, list)
            or any(not isinstance(item, str) or not item.strip() for item in value)
            or len(set(value)) != len(value)):
        raise RouterValidationError(f"{key} must be a list of unique non-empty strings")
    return value


def validate_demand(demand: dict[str, Any]) -> None:
    if not isinstance(demand, dict):
        raise RouterValidationError("demand must be an object")
    if (demand.get("schema_id") != "synergy.economic-router.demand"
            or isinstance(demand.get("schema_version"), bool)
            or demand.get("schema_version") != 1):
        raise RouterValidationError("unsupported demand schema")
    allowed = {
        "schema_id", "schema_version", "demand_id", "buyer_id", "tenant_id", "consent_ref",
        "category", "jurisdiction", "status", "requirements", "quantity", "budget",
        "expires_at", "evidence_refs", "source_system", "source_ref", "source_fingerprint",
    }
    unknown = set(demand) - allowed
    if unknown:
        raise RouterValidationError("unknown demand fields: " + ", ".join(sorted(unknown)))
    for key in ("demand_id", "buyer_id", "category", "jurisdiction", "tenant_id", "consent_ref"):
        _text(demand, key)
    if demand.get("status") != "open":
        raise RouterValidationError("demand.status must be open")
    _unique_text_list(demand.get("requirements", []), "requirements")
    _unique_text_list(demand.get("evidence_refs", []), "evidence_refs")
    quantity = demand.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise RouterValidationError("quantity must be a positive integer")
    _money(demand.get("budget"), "budget")
    _utc(demand.get("expires_at"), "expires_at")
    source_fields = {"source_system", "source_ref", "source_fingerprint"}
    if source_fields.intersection(demand) and not source_fields.issubset(demand):
        raise RouterValidationError("source_system, source_ref and source_fingerprint must be supplied together")
    if source_fields.issubset(demand):
        _text(demand, "source_system")
        _text(demand, "source_ref")
        fingerprint = demand["source_fingerprint"]
        if (not isinstance(fingerprint, str) or len(fingerprint) != 64
                or any(ch not in "0123456789abcdef" for ch in fingerprint)):
            raise RouterValidationError("source_fingerprint must be a lowercase SHA-256 hex digest")


def validate_offer(offer: dict[str, Any]) -> None:
    if not isinstance(offer, dict):
        raise RouterValidationError("offer must be an object")
    if (offer.get("schema_id") != "synergy.economic-router.offer"
            or isinstance(offer.get("schema_version"), bool)
            or offer.get("schema_version") != 1):
        raise RouterValidationError("unsupported offer schema")
    allowed = {
        "schema_id", "schema_version", "offer_id", "seller_id", "tenant_id", "category",
        "jurisdiction", "status", "seller_verification", "capabilities", "capacity",
        "price", "expires_at", "evidence_refs",
    }
    unknown = set(offer) - allowed
    if unknown:
        raise RouterValidationError("unknown offer fields: " + ", ".join(sorted(unknown)))
    for key in ("offer_id", "seller_id", "category", "jurisdiction", "tenant_id"):
        _text(offer, key)
    if offer.get("status") != "active":
        raise RouterValidationError("offer.status must be active")
    if offer.get("seller_verification") != "verified":
        raise RouterValidationError("seller_verification must be verified")
    _unique_text_list(offer.get("capabilities", []), "capabilities")
    _unique_text_list(offer.get("evidence_refs", []), "evidence_refs")
    capacity = offer.get("capacity", 1)
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise RouterValidationError("capacity must be a positive integer")
    _money(offer.get("price"), "price")
    _utc(offer.get("expires_at"), "expires_at")


def _fingerprint(tenant_id: str, demand_id: str, offer_id: str) -> str:
    raw = json.dumps([tenant_id, demand_id, offer_id, "economic-router-match-v1"],
                     separators=(",", ":"), ensure_ascii=False)
    return sha256(raw.encode("utf-8")).hexdigest()


def score_offer(demand: dict[str, Any], offer: dict[str, Any], *,
                now: datetime | None = None) -> dict[str, Any] | None:
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
    price_fit_bps = 10_000 if budget == 0 and price == 0 else (
        max(0, 10_000 - (price * 10_000 // max(budget, 1)))
    )
    score_bps = min(10_000, 7_000 + len(required) * 300 + price_fit_bps // 5)
    return {
        "match_id": _fingerprint(demand["tenant_id"], demand["demand_id"], offer["offer_id"]),
        "tenant_id": demand["tenant_id"],
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
    """Rank offers without side effects; persistence belongs to the canonical repository."""
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
