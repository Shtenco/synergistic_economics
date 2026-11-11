# P6.3 — Durable Recovery, Snapshot and Reconciliation Contract

**Status:** architecture contract / implementation gate; no durable recovery implementation is claimed  
**Date:** 11 November 2026  
**Depends on:** P6.0–P6.2, the existing `synergy_kernel.EventStore`, canonical Claim/Contract/rights authorities and the P6.2 event envelope.

## 1. Executive decision

P6 recovery must not be implemented by serializing the current `InMemoryAtomicCoordinator` dictionaries and calling that a durable store. The current coordinator keeps aggregate state, receipts and aggregate versions only in process memory. The current EventStore also keeps events and its duplicate indexes only in memory.

The durable design must select **one commit authority** before implementation:

- a transactional repository in which aggregate state, canonical events, command receipt, aggregate version and outbox row commit in one database transaction; or
- an event-sourced repository in which canonical event append is the commit point and every materialized state is a rebuildable projection.

No two independent stores may each claim to be the commit authority. A snapshot is a rebuild accelerator, never a competing source of truth.

## 2. Current event semantics are not yet sufficient for production replay

The current P6.1 event set includes:

- `inventory_lot_registered`;
- `inventory_quantity_reserved`;
- `inventory_reservation_committed` and `inventory_reservation_expired`;
- `inventory_reservation_released`;
- `inventory_quantity_moved`;
- `inventory_lot_quarantined`.

The payloads are useful domain facts, but several are not complete reducer inputs:

1. `inventory_quantity_moved` records the source lot and moved child ID, but does not fully encode the resulting child-lot snapshot (including every inherited field and authorization set).
2. Reservation state transitions and lot state transitions can affect two aggregates. The present event representation may identify a reservation aggregate for one command and a lot aggregate for another; a production workflow needs explicit multi-aggregate transaction semantics.
3. The expiry path is currently triggered by a commit attempt after expiry. There is no independent expiry scheduler/command contract.
4. Event metadata is enriched by the bridge, but the in-memory coordinator currently requires all mapped events in a command to share one aggregate ID/version. That is too narrow for a true atomic lot-plus-reservation transition.
5. Existing P6.1 `_event` payloads do not contain a full authoritative before/after state, and some fields needed to rebuild reservations (for example full reservation purpose, actor, counterparty, expiry and immutable original quantity across every lifecycle transition) are not repeated on every event.

Therefore a deterministic reducer for all inventory state cannot be honestly delivered until the event contract is versioned and multi-aggregate semantics are selected. Do not infer missing fields from today's code defaults.

## 3. Required durable records

A transactional repository must persist these logical records, either as normalized tables or equivalent durable structures:

### 3.1 Aggregate event

- canonical envelope bytes and schema version;
- globally unique event ID;
- aggregate type and ID;
- aggregate version;
- event ordinal within command;
- global commit sequence / database commit ordering token;
- canonical payload digest and envelope digest;
- actor, authority reference, occurred/recorded timestamps;
- command, correlation and causation identifiers;
- evidence references;
- transaction/commit identifier.

Unique constraints: event ID; (aggregate type, aggregate ID, aggregate version, event ordinal); and idempotency identity as defined in section 3.2.

### 3.2 Command receipt

Persist, atomically with the event(s):

- idempotency key (scoped by tenant/principal if multi-tenant);
- canonical request fingerprint and fingerprint algorithm version;
- command ID and actor/principal;
- aggregate set and expected-version vector;
- committed result reference or canonical result payload;
- emitted event IDs in order;
- commit identifier and recorded timestamp;
- terminal status.

A retry with the same key and same fingerprint returns the stored result and original event IDs. A retry with the same key and a different fingerprint is a hard conflict. A failed transaction must leave neither a committed receipt nor committed events. If the transaction outcome is unknown to the caller, the caller must query by idempotency key; it must not generate a new key and blindly repeat a possibly committed operation.

### 3.3 Aggregate version head

Persist the latest committed version per aggregate. Update it with compare-and-swap / row locking in the same transaction as event insertion. A caller's expected-version vector must cover every aggregate affected by a command.

### 3.4 Outbox and inbox

Outbox rows are committed with domain events. Publication is at-least-once and occurs after commit. Consumers persist an inbox/deduplication receipt in the same transaction as their own side effect. Broker acknowledgement is not the source of truth.

## 4. Multi-aggregate command contract

Inventory commands can modify both a lot and a reservation. The command transaction must therefore declare a sorted, complete aggregate-version vector, for example:

- `inventory_lot/lot-17 -> expected version 8`;
- `inventory_reservation/res-42 -> expected version 2`.

The repository locks or compare-and-swaps all affected aggregate heads in deterministic key order, validates all expected versions, applies all changes, appends all events, stores the command receipt and outbox rows, and commits once. If any expected version is stale or any invariant fails, the entire command aborts.

Events in a multi-aggregate command share a command ID but carry their own aggregate identity/version and a command-wide ordinal. The event schema must specify whether ordinal is global across the command (recommended) or scoped per aggregate; it must not be ambiguous. One aggregate version advances once for each aggregate changed, not once for every event indiscriminately.

The current P6.2 in-memory coordinator's one-aggregate assumption must not be relaxed casually. Multi-aggregate atomicity requires a new coordinator/repository contract and tests, not a special-case bypass.

## 5. Snapshot format and validation

A snapshot is a deterministic serialization of a projection at a known committed global sequence and per-aggregate version vector. Minimum metadata:

- `snapshot_schema_version`;
- `projection_name` and `projection_version`;
- `created_at` (UTC);
- `last_global_sequence` and commit/checkpoint identifier;
- sorted aggregate-version vector;
- canonical serialized state and state digest;
- event schema versions included;
- reducer implementation/version identifier;
- optional previous snapshot digest for operational lineage.

For inventory, state serialization must include all lots and reservations, including closed reservations needed for idempotent/history semantics, exact decimal strings, units, owner/custodian/location, quality status, reserved quantities, lot/reservation versions, source-lot links, authorization references/sets and all lifecycle fields. Secrets or personal data must not be copied into a snapshot unless required and access-controlled; references are preferred.

A snapshot is accepted only if:
1. its schema and projection versions are supported;
2. canonical serialization reproduces its digest;
3. the checkpoint sequence exists in the canonical event history;
4. its aggregate-version vector agrees with the audited event prefix;
5. its reducer version is compatible with the event schemas;
6. the snapshot is not from a future or divergent history.

A checksum detects accidental/certain unauthorized modifications only under its trust assumptions. Without signatures, protected storage, key management and external anchoring, it is not proof of authorship or truth.

## 6. Recovery algorithm

Recovery is fail-closed and deterministic:

1. Open the selected durable repository in read-only recovery mode.
2. Verify schema migrations and durable commit metadata.
3. Run canonical envelope audit over the relevant event prefix. Reject unknown schemas, duplicate identities, invalid digests, invalid ordering, aggregate-version gaps, malformed metadata and incomplete command groups.
4. Select the newest snapshot whose schema, digest, checkpoint and aggregate-version vector validate against that prefix. If none is valid, rebuild from the genesis event only if every required event schema has a registered deterministic reducer; otherwise stop.
5. Load the snapshot into an isolated candidate projection, not the live write path.
6. Replay events strictly after the snapshot checkpoint, in canonical commit order, applying only version-pinned deterministic reducers. No network calls, wall-clock reads, random values, mutable external lookups or current policy defaults are permitted inside reducers.
7. Recompute aggregate invariants after every command boundary and at the end: lot quantity non-negative; reserved quantity non-negative and no greater than lot quantity; active reservation remainder reconciles to lot reserved quantity; closed reservations retain zero remainder; child-lot lineage and quantity conservation hold; owner/title is unchanged by physical movement.
8. Rebuild aggregate version heads, idempotency receipts and event-ID indexes from durable records. Receipts must be replayable as exact prior outcomes, not reconstructed from guesses.
9. Compare the rebuilt projection and version vector with persisted materialized state, if one exists. A mismatch is a reconciliation incident; do not overwrite either side automatically.
10. Only after all checks pass, atomically promote the recovered projection to serving state and enable writes.

If a command has only some of its expected events, a receipt has no matching commit, event ordinals are incomplete, or a transaction commit marker is ambiguous, recovery stops and quarantines that range. It must never silently skip an event and continue.

## 7. Deterministic reducer contract

Every event type must register a reducer with:

- exact event schema version;
- exact projection version(s) supported;
- pure function signature: (state, event) -> new_state;
- explicit validation of required payload fields and units;
- explicit decimal parsing and rounding policy (prefer no rounding for stock quantities);
- deterministic ordering and duplicate behavior;
- invariant checks;
- migration strategy for historical event versions;
- golden test vectors with expected serialized output and digest.

Reducers must not infer legal title from custody, infer settlement from shipment, create journal entries from inventory events, or call external evidence issuers during replay. SPER evidence decisions should be recorded as immutable, policy-versioned decision facts; replay must not re-evaluate old evidence under today's policy.

## 8. Reconciliation and operational states

Recovery should expose explicit states:

- `HEALTHY`: audit and projection reconciliation passed; writes may be enabled.
- `READ_ONLY`: history is readable but one or more projections/reducers are unavailable; no mutation.
- `QUARANTINED`: integrity, command grouping, version, snapshot or invariant failure; affected range is isolated.
- `RECOVERY_REQUIRED`: durable commit outcome or outbox delivery is unresolved; idempotency lookup required.
- `MIGRATION_REQUIRED`: an event/snapshot schema is known but no approved deterministic migration exists.

No operator override may convert a failed integrity check into `HEALTHY` without a separately recorded, authorized repair event and a new verified checkpoint.

## 9. Required test matrix before implementation exit

### Snapshot tests
- snapshot round-trip produces byte-identical canonical serialization;
- modified state or metadata invalidates digest;
- unsupported snapshot schema/reducer version fails closed;
- checkpoint not present in event history is rejected;
- aggregate-version vector mismatch is rejected;
- old valid snapshot plus later events equals full replay from genesis.

### Crash and transaction tests
- crash before commit leaves no state/event/receipt/outbox writes;
- crash after commit but before response is resolved by idempotency lookup;
- crash after commit but before publish is recovered from outbox;
- duplicate publication is harmless through inbox;
- partial multi-aggregate writes are impossible;
- concurrent commands competing for any shared aggregate version cannot oversubscribe stock.

### Inventory reducer tests
- lot registration then reservation;
- commit before expiry and commit-at/after-expiry;
- release after reserve and release after commit;
- partial and full consume, including child-lot creation;
- multiple reservations against one lot;
- quarantine with and without active reservations;
- exact source + child quantity conservation;
- owner remains unchanged after movement; custodian/location change independently;
- all historical reservations and idempotency outcomes remain queryable.

### Reconciliation tests
- snapshot + tail replay equals genesis replay;
- rebuilt receipts and aggregate versions equal durable indexes;
- projection mismatch is reported and not auto-repaired;
- legacy records are handled only through an explicit migration/checkpoint rule, never silently treated as canonical inventory events.

## 10. Implementation gates

**P6.3a — schema completion:** define versioned lot/reservation lifecycle events, multi-aggregate command envelope, command-wide ordinal and immutable result/receipt contract.

**P6.3b — persistence selection:** select and document the durable database/repository, isolation level, uniqueness constraints, locking/CAS semantics, backup and restore policy. No implementation should assume a database before selection.

**P6.3c — pure reducers:** implement reducers only after the complete event schemas exist; test every lifecycle transition and invariant from genesis.

**P6.3d — snapshots and recovery:** add snapshot writer/validator, recovery runner, receipt/index reconstruction and crash injection tests.

**P6.3e — outbox/inbox and reconciliation:** add transactional delivery, consumer deduplication, projection reconciliation and operational quarantine states.

## 11. Explicit non-goals and prohibitions

- No second EventStore, inventory authority or financial ledger.
- No automatic journal posting from stock movement, reservation, quarantine or evidence.
- No automatic transfer of legal title or settlement from physical movement.
- No post-hoc persistence of the mutating P6.1 API.
- No "best effort" replay that skips unknown events.
- No claim of durability, crash recovery, tamper-proofing or production readiness until the required tests pass on the selected durable implementation.

**Decision:** P6.2e remains a strict integrity audit. P6.3 defines the requirements for durable recovery; implementation is gated on schema completion and persistence selection.
