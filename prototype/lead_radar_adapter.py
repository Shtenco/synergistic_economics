"""Consent-gated, data-minimizing Lead Radar adapter for marketplace demand.

The caller supplies a verifier backed by the applicable consent/authority
service. A public URL or scraped contact detail is never treated as consent.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import json
from typing import Callable

from economic_registry import EconomicMarketplaceRegistry, RegistryError


class LeadRadarError(ValueError):
    """Lead Radar source, consent or normalization failure."""


def _text(value, field):
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise LeadRadarError(f"{field} must be trimmed non-empty text")
    return value


def normalize_lead_signal(signal: dict, *, tenant_id: str, buyer_id: str,
                           jurisdiction: str, consent_ref: str,
                           source_system: str, source_ref: str,
                           demand_id: str, expires_at: str) -> dict:
    """Retain only normalized economic intent; never copy raw source/contact data."""
    if not isinstance(signal, dict):
        raise LeadRadarError("signal must be an object")
    allowed = {"category", "requirements", "quantity", "budget"}
    unknown = set(signal) - allowed
    if unknown:
        raise LeadRadarError("unapproved source fields: " + ", ".join(sorted(unknown)))
    for key, value in (("tenant_id", tenant_id), ("buyer_id", buyer_id),
                       ("jurisdiction", jurisdiction), ("consent_ref", consent_ref),
                       ("source_system", source_system), ("source_ref", source_ref),
                       ("demand_id", demand_id), ("expires_at", expires_at)):
        _text(value, key)
    category = _text(signal.get("category"), "category")
    requirements = signal.get("requirements", [])
    if (not isinstance(requirements, list)
            or any(not isinstance(item, str) or not item.strip() for item in requirements)):
        raise LeadRadarError("requirements must be a list of non-empty strings")
    quantity = signal.get("quantity", 1)
    if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity < 1:
        raise LeadRadarError("quantity must be a positive integer")
    budget = signal.get("budget")
    if not isinstance(budget, dict):
        raise LeadRadarError("budget must be an object")
    amount = budget.get("amount_minor")
    scale = budget.get("scale")
    currency = budget.get("currency")
    if isinstance(amount, bool) or not isinstance(amount, int) or amount < 0:
        raise LeadRadarError("budget.amount_minor must be a non-negative integer")
    if isinstance(scale, bool) or not isinstance(scale, int) or not 0 <= scale <= 6:
        raise LeadRadarError("budget.scale must be an integer from 0 to 6")
    if not isinstance(currency, str) or len(currency) != 3 or not currency.isalpha() or currency.upper() != currency:
        raise LeadRadarError("budget.currency must be a three-letter uppercase code")
    normalized = {
        "buyer_id": buyer_id, "category": category, "jurisdiction": jurisdiction,
        "requirements": sorted(set(item.strip() for item in requirements)),
        "quantity": quantity, "budget": {"amount_minor": amount, "currency": currency, "scale": scale},
    }
    fingerprint = sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":"),
                                    ensure_ascii=False, allow_nan=False).encode("utf-8")).hexdigest()
    return {
        "schema_id": "synergy.economic-router.demand", "schema_version": 1,
        "demand_id": demand_id, "buyer_id": buyer_id, "tenant_id": tenant_id,
        "category": category, "jurisdiction": jurisdiction, "status": "open",
        "requirements": normalized["requirements"], "quantity": quantity,
        "budget": normalized["budget"], "expires_at": expires_at,
        "consent_ref": consent_ref, "source_system": source_system,
        "source_ref": source_ref, "source_fingerprint": fingerprint,
    }


def ingest_lead_signal(registry: EconomicMarketplaceRegistry, signal: dict, *,
                       tenant_id: str, buyer_id: str, jurisdiction: str,
                       consent_ref: str, source_system: str, source_ref: str,
                       demand_id: str, expires_at: str, consent_verifier: Callable,
                       command_id: str, idempotency_key: str, actor_id: str,
                       authority_ref: str, correlation_id: str,
                       occurred_at: datetime | None = None):
    if not callable(consent_verifier):
        raise LeadRadarError("a consent verifier is required")
    if consent_verifier(consent_ref, tenant_id, "marketplace_matching") is not True:
        raise LeadRadarError("consent/authority check did not approve marketplace_matching")
    demand = normalize_lead_signal(
        signal, tenant_id=tenant_id, buyer_id=buyer_id,
        jurisdiction=jurisdiction, consent_ref=consent_ref,
        source_system=source_system, source_ref=source_ref,
        demand_id=demand_id, expires_at=expires_at,
    )
    try:
        return registry.register_demand(
            demand, command_id=command_id, idempotency_key=idempotency_key,
            actor_id=actor_id, authority_ref=authority_ref,
            correlation_id=correlation_id, occurred_at=occurred_at,
        )
    except RegistryError as exc:
        raise LeadRadarError(str(exc)) from exc
