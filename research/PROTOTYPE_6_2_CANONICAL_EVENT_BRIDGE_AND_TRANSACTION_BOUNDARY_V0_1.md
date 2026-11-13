# Prototype 6.2 — Canonical Event Bridge and Transaction Boundary

**Status:** design contract; not a production implementation  
**Date:** 11 November 2026  
**Depends on:** Prototype 6 P6.0–P6.1 and the existing `prototype/synergy_kernel.py`

## 1. Purpose

Define the only permitted bridge from P6 lot/claim/evidence domain transitions into the existing SYNERGY event authority. P6.2 must not create a second EventStore, second ledger, or shadow inventory authority.

This document is deliberately a design gate. The current P6.1 `LotInventory` is in-memory and mutates its state before returning event descriptions. It must not be connected to a durable or authoritative EventStore by a naïve "call command, then append returned events" adapter.

## 2. Existing canonical kernel contract

The current prototype kernel exposes:

- `EventStore.append(event_id, event_type, payload, idempotency_key)`
- `EventStore.replay()`
- `Event.sequence` as a global append sequence
- `Event.digest` computed as SHA-256 of `event_type + "|" + canonical_json(payload)`
- `DoubleEntryLedger.post(entry)` with duplicate entry-ID protection and per-currency balancing.

The EventStore is append-only in process memory and rejects duplicate event IDs and idempotency keys. Its current digest is an integrity checksum over event type and payload only. It does **not** bind event ID, sequence, aggregate version, actor, timestamps, evidence references, or a previous-event hash. It is not a hash chain, signed log, durable log, or proof of off-chain truth.

P6.1 currently returns event envelopes containing `event_id`, `event_type`, `aggregate_id`, `aggregate_version`, `idempotency_key`, and `payload`. The adapter must preserve these fields; it must not silently discard aggregate identity/version or reinterpret the P6 domain event as a financial posting.

## 3. Canonical authority map

| Concern | Authoritative owner | P6.2 rule |
|---|---|---|
| Lot quantity, reservation and custody state | One selected inventory aggregate/service | P6 is an adapter/projection until that authority is explicitly selected |
| Event history and replay order | Existing EventStore (prototype) / its future durable successor | Append once; never maintain a parallel P6 event log |
| Financial balances and journal entries | Existing DoubleEntryLedger | Inventory movement alone never posts a journal entry |
| Contractual authority and title | Canonical Contract / rights / asset model | An authorization reference is evidence to resolve, not proof by string presence |
| Evidence decision | SPER policy evaluation | Record decision and policy version; do not turn it into a legal conclusion |
| SEC | Canonical Claim projection | No separate claim registry |

Important unresolved boundary: Stage-B currently stores its own local physical inventories inside the simulation. P6.1 is not yet synchronized with them. Until a migration/adapter decision is approved, the two models must remain isolated and must never both be treated as authoritative for the same physical lot.

## 4. Event envelope v1

The adapter must map each P6 domain event to one canonical envelope with:

- `schema_version` — explicit and immutable for the event;
- `event_id` — stable ID generated once by the command boundary;
- `event_type` — namespaced, versioned domain event type;
- `aggregate_type`, `aggregate_id`, `aggregate_version`;
- `global_sequence` — assigned by the canonical EventStore at append time;
- `occurred_at` and `recorded_at` — timezone-aware UTC instants, distinct meanings;
- `actor_id` and `authority_ref` — authenticated actor and resolvable authority context;
- `idempotency_key` and `command_id`;
- `correlation_id` and optional `causation_id`;
- `payload` — domain facts only, with canonical quantity strings and explicit units;
- `evidence_refs` — immutable references plus the SPER decision/policy version where relevant;
- `payload_digest` — digest of canonical payload bytes, not a substitute for issuer authentication.

Do not put mutable display labels, localized descriptions, or floating-point quantities in the canonical event payload. Use stable identifiers, decimal strings, and explicit units/currencies. Schema evolution must be additive or explicitly versioned; replay of historical events must not depend on today's default values.

## 5. Aggregate version and ordering rules

1. Each successful lot command advances that lot's aggregate version exactly once per committed state transition.
2. A multi-event command may emit several events, but the event sequence and aggregate version semantics must be specified: either one version per event or one command version with an explicit event ordinal. Never leave this ambiguous.
3. The adapter rejects a stale expected aggregate version before committing.
4. The canonical EventStore assigns global sequence numbers; callers must not predict or locally allocate them.
5. Replay must be deterministic by global sequence, with aggregate versions strictly monotonic and no gaps except explicitly documented migration checkpoints.
6. A repeated command with the same idempotency key and identical canonical request fingerprint returns the original receipt and emits no new event.
7. Reuse of an idempotency key with a different request fingerprint is a hard conflict.
8. Event IDs must be stable across retry/recovery. Do not derive a new ID on every retry.

The current EventStore does not enforce per-aggregate versions or validate an event's expected previous version. Those checks belong in the transactional repository/service boundary until the canonical store itself supports them.

## 6. Transaction boundary — required before durable integration

For a durable implementation, one database transaction must atomically persist:

1. the new aggregate state (or append-only aggregate event, if event sourcing is selected);
2. all canonical domain events;
3. the command/idempotency receipt;
4. transactional outbox records for external delivery.

The transaction must enforce a unique constraint on `event_id`, `idempotency_key`, and (aggregate ID, aggregate version, event ordinal) as applicable.

External publication occurs only after commit, from the outbox. Delivery is at-least-once; consumers deduplicate by stable event ID and maintain an inbox/receipt. A message broker acknowledgement is not the source of truth for the inventory transaction.

### Why a post-hoc adapter is unsafe

Current P6.1 command methods update in-memory lot/reservation dictionaries before the caller persists the returned event. If persistence then fails, the state transition has already happened in memory but has no durable event. Retrying may produce a different error or state. Therefore the P6.1 API cannot be wrapped safely by simply doing:

```python
receipt = inventory.reserve(...)
for event in receipt.events:
    event_store.append(...)
```

That sequence is acceptable only as a disposable demonstration with no durability guarantee. It is forbidden as the production integration contract.

### Acceptable implementation strategies

Choose one strategy explicitly before coding:

- **Transactional repository:** move state mutation and event append behind one repository transaction; validate first, persist state + events + outbox atomically.
- **Event-sourced aggregate:** make the canonical event append the commit point; derive lot state by deterministic replay; snapshots are caches, not independent authorities.
- **Transactional in-memory reference:** for tests only, stage a candidate state, validate all event IDs/keys and append capacity, then atomically swap state and event collection under one lock. This does not solve process crashes or cross-process concurrency.

Do not implement a fake two-phase commit across unrelated stores. If inventory and EventStore cannot share a transaction, use a deliberate outbox/inbox or a single authoritative event log with projections.

## 7. Financial separation

The following inventory events do not by themselves create journal entries:

- lot registered;
- quantity reserved or released;
- lot quarantined or quality released;
- physical movement / child-lot creation;
- custody changed;
- evidence received or evaluated.

A financial journal entry requires a separately authorized accounting event and a defined recognition policy. Invoice issued is not payment; payment instruction is not settlement; shipment is not automatically revenue. If later settlement integration is added, it must use a separate settlement adapter and idempotent provider inbox.

## 8. Integrity and audit model

The current EventStore digest is not a cryptographic chain. P6.2 must not relabel it as one.

If tamper-evident chaining is required, introduce a separately versioned envelope digest over canonical serialization that binds at least:

- schema and hash algorithm versions;
- event ID, global sequence, aggregate ID/version and event type;
- actor, occurred/recorded timestamps;
- canonical payload digest and evidence references;
- previous event hash.

Specify key custody, signing, rotation, checkpointing, recovery and external anchoring before claiming tamper evidence. A hash chain detects certain alterations under its trust assumptions; it does not prove the truth of physical facts or prevent an authorized issuer from lying.

## 9. Required P6.2 tests

### Mapping and schema
- every P6.1 event maps to exactly one canonical event (or a documented multi-event mapping);
- stable event type, schema version, aggregate ID/version, actor and authority references;
- canonical decimal/unit representation;
- reject naive timestamps, missing actor, missing authority context and unsupported schema versions;
- payload digest changes when any canonical domain fact changes.

### Idempotency and replay
- same command/key/fingerprint returns same receipt and emits no second event;
- same key with different fingerprint is rejected;
- duplicate event ID is rejected;
- aggregate version advances exactly once;
- stale expected version is rejected;
- replay reconstructs exactly the committed lot and reservation state;
- replay is deterministic under fixed event ordering.

### Atomicity and crash recovery
- injected failure before persistence leaves state and event log unchanged;
- injected failure between state and event writes is impossible within the transaction;
- crash after commit but before publication is recovered by outbox;
- duplicate outbox delivery is harmless through consumer inbox;
- concurrent reservations against the same lot cannot oversubscribe quantity;
- process restart preserves idempotency receipts and aggregate versions.

### Accounting and regression
- no inventory-only event creates a journal entry;
- every financial journal entry remains balanced and idempotent;
- Stage-A/B/C2 baseline and compound-control outputs remain unchanged when P6 is disabled;
- Stage-B inventory is not double-counted with P6 lot stock.

## 10. Implementation sequence

**P6.2a — contract tests:** implement envelope validation and event mapping tests without changing Stage-A/B/C2.

**P6.2b — safe in-memory coordinator:** stage candidate aggregate state and canonical event together for deterministic unit tests; explicitly label it non-durable.

**P6.2c — persistence decision:** select a durable repository/database and transaction strategy; document ownership and migration from Stage-B inventory before implementation.

**P6.2d — outbox/inbox:** add crash-recoverable external publication and consumer deduplication.

**P6.2e — replay and reconciliation:** reconstruct inventory from canonical events and compare projections against stored state; fail closed on divergence.

No real payments, custody operations, title transfers or production inventory writes are authorized by this prototype stage.

## 11. Exit criteria

P6.2 is complete only when:

- no second EventStore or ledger exists;
- P6 event mapping preserves identity, aggregate version, actor, authority and evidence references;
- state + event + idempotency receipt commit atomically in the selected persistence boundary;
- replay reconstructs exact inventory and reservation balances;
- duplicate delivery and crash recovery are tested;
- concurrent reservations cannot oversubscribe;
- accounting remains separate and balanced;
- Stage-A/B/C2 controls pass unchanged;
- limitations and maturity are explicit.

**Decision:** P6.1 remains an isolated in-memory reference. P6.2 begins with the canonical event contract and transaction boundary; it must not connect the current mutating API to EventStore using a post-hoc append loop.


## 12. P6.2c/e implementation status — integrity audit boundary

The additive P6.2c/e prototype now audits canonical records in the existing in-memory EventStore. In addition to schema/identity/digest and aggregate-order checks, it rejects missing or blank actor, authority and correlation metadata; malformed/non-UTC timestamps; invalid aggregate versions and ordinals; duplicate or blank evidence references; duplicate canonical event IDs and idempotency keys; and reuse of a command ID with inconsistent aggregate/version or command metadata.

This is deliberately **not** the P6.2e state-recovery reducer described in the original roadmap. It does not rebuild inventory, restore command receipts or aggregate-version caches after process restart, reconcile materialized projections, or prove a crash-safe commit. The roadmap's state-reconstruction/reconciliation milestone remains blocked until the project selects a durable transaction boundary and defines complete versioned reducers for every inventory lifecycle event. The in-memory coordinator cannot satisfy that requirement.

The strict audit also treats the current command model as one aggregate/version per command. A future cross-aggregate command must use an explicitly versioned workflow/transaction envelope; it must not be silently accepted under this contract.


## 13. P6.3 durable recovery contract

The recovery, snapshot and reconciliation requirements are specified in [P6.3 Durable Recovery, Snapshot and Reconciliation Contract](PROTOTYPE_6_3_DURABLE_RECOVERY_SNAPSHOT_AND_RECONCILIATION_CONTRACT_V0_1.md). This is a design/acceptance gate only. It does not make the current in-memory EventStore or coordinator durable. In particular, a production reducer is blocked until P6 lifecycle event schemas fully encode reservation and lot transitions and the command boundary supports atomic multi-aggregate version vectors.
