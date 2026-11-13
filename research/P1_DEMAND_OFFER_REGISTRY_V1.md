# P1 — Demand and Offer Registry

## Scope

The P1 registry stores consent-referenced demand signals and verified seller offers inside the existing `SQLiteEventRepository`. It does not create another event store, ledger, identity provider, CRM or payment service.

Each tenant is a separate canonical aggregate (`economic_marketplace_tenant`). Its state contains demand and offer projections. Every write goes through the repository's single-aggregate transaction, which commits the event, projection, immutable command receipt and outbox row atomically.

## Lead Radar adapter boundary

Lead Radar is an ingestion source, not a legal authority. An adapter may submit a demand only after it has verified the applicable legal basis/consent for the specific purpose `marketplace_matching`. The registry stores the opaque `consent_ref` and optional source references/fingerprint; it does not infer consent from a public page, scraped contact detail, or model score.

Do not store raw personal contact data, sensitive attributes, or source page contents in the registry. Store minimized normalized intent fields and evidence/consent references. A source reference is not itself proof of consent.

## Tenant isolation and deduplication

- The tenant ID selects the aggregate; a query always loads that tenant aggregate.
- Command and idempotency keys are deterministically namespaced by tenant.
- Cross-tenant matching remains forbidden by the matcher.
- Optional source fingerprints allow duplicate intent detection. A duplicate produces an audit event and returns the existing demand ID without creating a second demand.
- Duplicate demand/offer IDs are rejected.
- Same idempotency key + same request returns the original durable receipt; key reuse with different request conflicts.

## Durability and recovery

The repository's SQLite WAL, FULL synchronous mode, BEGIN IMMEDIATE, compare-and-swap aggregate version, immutable command receipts, canonical event log and transactional outbox remain the only persistence boundary. A restarted registry reconstructs state from the durable aggregate projection and can inspect pending outbox events. Outbox publication is at-least-once; downstream consumers must deduplicate by event ID.

This is a single-host SQLite boundary, not distributed consensus. Do not place its database on a network filesystem. Multi-host deployment requires an explicitly designed transactional database adapter and migration.

## Commands and events

Commands: `RegisterDemand`, `RegisterOffer`.  
Events: `marketplace.demand.registered`, `marketplace.demand.duplicate_detected`, `marketplace.offer.registered`.

All events include tenant scope and canonical event metadata. They do not authorize a contract, reserve capacity, establish ownership, or move funds.

## Remaining P1/P2 work

A production Lead Radar adapter still needs source-specific terms/consent adapters, authentication, rate limits, review queues, opt-out propagation and legal review. P2 adds a query/index service over the canonical registry and invokes the deterministic matcher; ranking never mutates demand or offers.
