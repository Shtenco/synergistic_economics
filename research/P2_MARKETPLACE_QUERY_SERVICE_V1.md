# P2 — Read-only Marketplace Query Service

## Purpose

Expose tenant-scoped discovery over the P1 canonical Demand/Offer Registry. This service composes the deterministic matcher; it does not create or mutate demands, offers, contracts, inventory reservations, payments or financial records.

## Query

`EconomicMarketplaceService.discover_matches(tenant_id, demand_id, now, limit)`:
1. Resolves the demand only inside the requested tenant aggregate.
2. Reads active offers from that same tenant aggregate.
3. Runs the versioned deterministic matching policy.
4. Returns ranked `MatchCandidate` records with compatibility explanations.
5. Reports `side_effects=none` and `authority=routing_only`.

The result is a transient query response, not a contract or a reservation. Candidate persistence and lifecycle commands are deliberately deferred until a separate decision/event contract is reviewed.

## Limits and invariants

- Tenant is mandatory and cannot be inferred from a demand ID.
- Query limit is bounded to 1–100.
- Expired, paused, unverified, over-budget, wrong-jurisdiction, wrong-currency/scale, under-capacity or capability-incomplete offers do not match.
- Search never writes to the canonical event repository.
- Ranking policy version is included in every response for reproducibility.
- No automatic FX, no floats, no external contact and no side effects.

## Acceptance

Tests cover ranking, tenant isolation, expiry, bounded limits and read-only behavior. Production HTTP/API exposure requires authentication, authorization, rate limiting, audit policy and an API contract; this module is the service layer, not an internet-facing server.
