# Spatial Economic Twin — implementation boundary

**Date:** 16 November 2026  
**Repository:** Shtenco/synergistic_economics  
**Status:** research prototype; no live map-to-ledger integration.

## Why a separate adapter

The current Stage-B SCCE module explicitly models a multi-period physical production-and-consumption economy while excluding money, credit, ownership and wages. The existing small kernel separately contains double-entry ledger and event-store primitives. The spatial adapter must not silently pretend these layers are already one integrated system.

## Implemented boundary in Prototype 6

The new standard-library-only module prototype/spatial_bridge.py defines:

- GeoPoint — validates WGS84 longitude/latitude bounds and only accepts EPSG:4326 for this initial event contract.
- PhysicalFlow — stores commodity, quantity, unit, origin/destination cell references and period; quantity is Decimal and must be finite and non-negative.
- FinancialPostingRef — stores a reference to a journal entry, debit/credit accounts, positive Decimal amount, currency and posting status. It does not create or settle the journal entry.
- SourceEvidence — requires source identity, version, license, evidence type and timezone-aware retrieval timestamp; optional confidence must be in [0, 1].
- SpatialEconomicEvent — binds the spatial/business context to a physical flow and/or financial posting; requires event IDs, idempotency key, region/cell identity and a source record.
- SpatialEventRegistry — an in-memory duplicate event/idempotency boundary with deterministic append order.

## Invariants

1. Physical quantities are not monetary amounts. Their values and units serialize under physicalFlow; currency amounts serialize under financialPosting.
2. The adapter validates a FinancialPostingRef but does not replace the double-entry ledger's balancing checks or settlement logic.
3. Duplicate event IDs and idempotency keys are rejected before registry mutation.
4. Geographic coordinates are bounds-checked and carry an explicit CRS.
5. Unknown source version or license is not accepted as a valid source record.
6. Observed, derived, simulated, forecast and demo evidence types remain distinct.
7. A scenario event can carry a scenario_run_id; simulated data must never be represented as observed data.
8. The registry is process-local and volatile. Durable storage, concurrent writers, cryptographic event chaining, signatures, authorization, schema-registry deployment and replay across services are not implemented here.

## Integration sequence

1. SYNERGY Maps resolves region/cell/facility IDs and produces a read-model projection.
2. Producers submit versioned geo-economic events with source evidence.
3. The boundary validates the event and idempotency key.
4. A physical-flow consumer applies quantity changes to the relevant physical stock/flow model and checks resource conservation.
5. A financial consumer independently validates and posts a balanced journal entry using the existing accounting kernel.
6. The event registry stores references linking the physical event, journal entry, contract/shipment and scenario run where available.
7. Map projections expose only permitted, classified and suitably aggregated data.

The order above does not mean that one successful step authorizes another. Financial settlement must be governed by the accounting/settlement subsystem; map display is not settlement authority.

## Tests and current result

The local standard-library unit test suite for this module passes 13 tests. GitHub Actions also discovers test files under prototype using unittest discovery, but remote CI for this branch must still run before the change can be called CI-green.

## Explicit non-goals

- No new money issuance or creation of financial claims.
- No assumption that a movement of money creates production or net synergy.
- No automatic inference of price, profit, ownership or GDP from a physical map feature.
- No direct write to the production economy or double-entry ledger.
- No storage of precise household coordinates or personal trails in public map layers.
- No claim of production readiness or legal/accounting compliance.

## Next stage

The next safe increment is a durable, append-only event store with transactional idempotency, schema validation in CI, access control, event versioning and reconciliation tests that prove physical stock conservation and double-entry financial balance independently.
