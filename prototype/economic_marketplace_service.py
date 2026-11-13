"""Read-only marketplace query service over the canonical demand/offer registry."""
from __future__ import annotations

from datetime import datetime

from economic_registry import EconomicMarketplaceRegistry
from economic_router import RouterValidationError, route_demand


class MarketplaceQueryError(ValueError):
    """Marketplace query is invalid or its demand is unavailable."""


class EconomicMarketplaceService:
    """Expose tenant-scoped candidate discovery without mutating economic state."""

    POLICY_VERSION = "economic-router-match-v1"
    MAX_LIMIT = 100

    def __init__(self, registry: EconomicMarketplaceRegistry):
        if not isinstance(registry, EconomicMarketplaceRegistry):
            raise TypeError("registry must be an EconomicMarketplaceRegistry")
        self.registry = registry

    def discover_matches(self, tenant_id: str, demand_id: str, *,
                         now: datetime | None = None, limit: int = 20) -> dict:
        if not isinstance(tenant_id, str) or not tenant_id.strip():
            raise MarketplaceQueryError("tenant_id is required")
        if not isinstance(demand_id, str) or not demand_id.strip():
            raise MarketplaceQueryError("demand_id is required")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= self.MAX_LIMIT:
            raise MarketplaceQueryError(f"limit must be between 1 and {self.MAX_LIMIT}")
        demand = self.registry.get_demand(tenant_id, demand_id)
        if demand is None:
            raise MarketplaceQueryError("demand not found in this tenant")
        offers = self.registry.list_active_offers(tenant_id)
        try:
            matches = route_demand(demand, offers, now=now, limit=limit)
        except RouterValidationError as exc:
            raise MarketplaceQueryError(str(exc)) from exc
        return {
            "tenant_id": tenant_id,
            "demand_id": demand_id,
            "policy_version": self.POLICY_VERSION,
            "candidate_count": len(matches),
            "matches": matches,
            "side_effects": "none",
            "authority": "routing_only",
        }
