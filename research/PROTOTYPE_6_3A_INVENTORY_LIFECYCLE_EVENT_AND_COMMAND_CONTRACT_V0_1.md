# P6.3a — Inventory Lifecycle Event and Multi-Aggregate Command Contract

**Status:** schema/acceptance contract; no production reducer or durable repository is implemented  
**Date:** 11 November 2026  
**Parent:** P6.3 Durable Recovery, Snapshot and Reconciliation Contract  
**Compatibility rule:** this contract does not reinterpret or upgrade historical P6.1 events in place.

## 1. Purpose and hard boundary

P6.1 is a useful in-memory domain reference, but its returned event descriptions are not a complete event-sourced history. Several commands mutate more than one aggregate while returning only one event. A reducer must not infer the omitted writes.

P6.3a therefore specifies a new event contract for future commands. Historical P6.1 event names and payloads remain legacy input. They must be handled by an explicit migration/checkpoint procedure, not silently treated as complete v2 facts.

This contract preserves the existing authorities:
- one inventory projection/repository for lot and reservation state;
- the existing canonical EventStore as the selected event integration point only if the eventual persistence decision adopts it;
- canonical Claim, Contract and rights/title authorities remain separate;
- financial journal remains separate; inventory events never create journal entries;
- custody/location movement is not legal-title transfer or settlement.

## 2. Aggregate identities and versions

Aggregate keys are typed pairs, never bare IDs:

- `inventory_lot/<lot_id>`
- `inventory_reservation/<reservation_id>`

Versions are positive integers. A newly created aggregate starts at version 1. A command declares an **expected-version vector** containing exactly every aggregate it reads for a conditional transition and every existing aggregate it changes. Newly created aggregates are declared separately as `create` targets and must not already exist.

The repository validates the complete set under one transaction/commit boundary. Existing aggregate versions are compared with the caller's expected values. Each changed existing aggregate advances exactly once per command, regardless of how many events describe it. A created aggregate receives version 1. Unchanged aggregates do not advance.

The expected-version vector is canonicalized by sorting on (aggregate_type, aggregate_id). Missing, duplicate, extra or stale entries fail closed. A read-only dependency may be declared separately as a read guard; it must not be confused with a write target.

## 3. Command envelope v2

A command is the atomic unit of business intent and idempotency. Required fields:

| Field | Contract |
|---|---|
| schema | `synergy.inventory.command.v2` |
| command_id | Globally unique immutable identifier |
| command_type | Registered command name |
| idempotency_scope | Stable tenant/principal namespace; explicit even in single-tenant deployments |
| idempotency_key | One key per command, not one key per emitted event |
| request_fingerprint | Digest of canonical command intent; algorithm/version identified |
| actor_id | Authenticated acting principal |
| authority_ref | Contract/mandate/policy authorization reference appropriate to command |
| correlation_id | Required trace identifier |
| causation_id | Optional non-empty parent command/event identifier |
| occurred_at | UTC timestamp supplied by trusted command boundary |
| expected_versions | Sorted vector of existing aggregate versions |
| creates | Sorted set of aggregate identities expected not to exist |
| event_count | Exact positive count of events in committed command group |

The fingerprint covers command type, normalized business request, actor, authority, scope, expected-version vector, create set, and relevant immutable references. Transport retry metadata and server-generated recorded timestamps are excluded. Fingerprint algorithm version is persisted with the receipt.

The idempotency uniqueness key is (idempotency_scope, idempotency_key). Reusing it with the same fingerprint returns the original terminal receipt and event IDs. Reusing it with a different fingerprint is a hard conflict. A failed/aborted transaction leaves no committed receipt. If the caller cannot determine whether commit succeeded, it queries this key; it must not mint a replacement key and repeat blindly.

Event-level idempotency keys are not authoritative and are not required. Event IDs are unique identities inside the committed command result. This avoids the current ambiguity where one command key is copied onto multiple events but the event audit expects global event-key uniqueness.

## 4. Event envelope v2

Each event uses schema `synergy.inventory.event.v2` and includes:

- event_id, schema, event_type;
- command_id, command_event_ordinal (1..event_count), command_event_count;
- aggregate_type, aggregate_id, aggregate_version;
- actor_id, authority_ref, correlation_id, optional causation_id;
- occurred_at and recorded_at (UTC);
- payload with explicit units and exact decimal strings;
- evidence_refs (unique, stable references; empty list allowed);
- payload_digest and canonical envelope digest.

The command ordinal is global across the complete command, not per aggregate. Every ordinal from 1 through event_count must occur exactly once. Event order is deterministic and persisted; consumers must not reorder by aggregate ID or timestamp. Events for one aggregate in a command share that aggregate's resulting version. Different aggregates in the same command can and usually will have different resulting versions.

A command group is complete only when the durable receipt, exact event count, contiguous ordinals, all declared aggregate version transitions, and one commit identifier agree. No event group may be partially visible.

## 5. Lifecycle transition matrix

Notation: L = source lot; R = reservation; C = newly created child lot. All listed changes and events commit atomically as one command.

| Command | Aggregate version vector | Required event facts |
|---|---|---|
| Register lot | create L@1 | Full immutable lot opening state: product, owner, custodian, location, exact quantity, unit, quality status, authorized actor references, source-lot reference (null for root), and opening timestamp/reference |
| Reserve quantity | L@v -> v+1; create R@1 | L reserved quantity before/after and delta; complete R opening state including original and remaining quantity, unit, lot link, actor, counterparty, purpose, expiry, status and authorization reference |
| Commit before expiry | R@r -> r+1; L is read guard only | R status RESERVED -> COMMITTED; original and remaining quantities; actor/authority; effective timestamp. L reserved quantity is unchanged and L version does not advance |
| Commit at/after expiry | L@v -> v+1; R@r -> r+1 | R status RESERVED -> EXPIRED and remaining quantity -> 0; L reserved quantity before/after and released delta; expiry instant and command decision timestamp |
| Release RESERVED/COMMITTED | L@v -> v+1; R@r -> r+1 | R status -> RELEASED and remaining quantity -> 0; L reserved quantity before/after and released delta; actor/authority |
| Consume partial/full | L@v -> v+1; R@r -> r+1; create C@1 | Source lot quantity/reserved quantity before/after; R original/remaining quantity and status before/after; complete C opening state; source-child lineage; exact moved quantity/unit; source/destination location and custodian |
| Quarantine | L@v -> v+1 | Quality status before/after, reason code and evidence/authority references; precondition that active reserved quantity is zero under this contract version |

### 5.1 Reserve

Reservation creation is a real aggregate creation, not merely a field embedded in a lot event. The command emits at least two events: one describing the lot's reservation balance change and one describing the complete reservation creation. The two events share command ID and commit boundary.

### 5.2 Commit and expiry

A normal commit changes only reservation status; the lot's reserved quantity remains reserved until consume or release. Therefore it must not increment the lot version.

Expiry is a distinct business transition even if discovered while handling a commit request. At or after expiry, the command atomically closes the reservation and releases its remaining reserved quantity on the lot. A scheduled expiry worker may issue the same explicit expiry command, but it must use the same idempotency/version rules. A late commit request must never be represented as a successful commit.

### 5.3 Release

Release affects both the reservation and the lot's reserved balance. It is valid only for a reservation with positive remaining quantity and status RESERVED or COMMITTED. It emits one event per changed aggregate. A release after full consumption, expiry or prior release is rejected or returns the original receipt only when it is an exact idempotent retry.

### 5.4 Consume and child-lot creation

Consume affects three aggregate identities: source lot, reservation, and a new child lot. It emits a complete event for each changed aggregate. The child event contains a full deterministic opening snapshot; the reducer must not infer inherited fields from whatever the source lot happens to contain during replay.

Required conservation equations (exact decimal arithmetic, same unit):
- source_quantity_after = source_quantity_before - moved_quantity;
- child_quantity_after = moved_quantity;
- source_reserved_after = source_reserved_before - moved_quantity;
- reservation_remaining_after = reservation_remaining_before - moved_quantity;
- moved_quantity > 0 and not greater than either source available committed quantity or reservation remaining quantity.

Owner remains identical on source and child. Child custodian and location are explicitly supplied. This command records a physical/custody movement fact only; it does not transfer title, settle a contract, or post a financial journal entry.

### 5.5 Quarantine

Quarantine does not release reservations implicitly. Under this contract it is rejected while reserved quantity is non-zero. A separate authorized release/expiry operation must first resolve reservations. Any future policy allowing quarantine with active reservations requires a new event schema/command version and explicit reservation consequences.

## 6. Immutable result and receipt

The command receipt is a durable commit record, not a recomputed convenience response. It includes:

- schema `synergy.inventory.receipt.v2`;
- command ID, idempotency scope/key and request fingerprint/version;
- commit ID and global commit sequence/checkpoint;
- exact ordered event IDs and event count;
- aggregate version vector after commit;
- terminal status and canonical result payload;
- recorded timestamp.

The result payload records stable identifiers and exact resulting quantities/statuses needed to reproduce the caller-visible outcome. It must not contain secrets or mutable external objects. A retry returns this exact committed result, even if later commands have changed the aggregates.

## 7. Reducer obligations and event completeness

For every transition, golden test vectors must assert:
1. exact event count and global ordinals;
2. exact aggregate identity and resulting version for every event;
3. complete required payload fields and canonical decimal/unit representation;
4. deterministic projection bytes and digest after reduction;
5. aggregate invariants at command boundary;
6. exact receipt/event-ID replay on retry;
7. no state change if any member event or receipt fails validation.

Reducers consume only the declared event schema and event facts. They do not read current time, current authorization policy, external databases, network services, or mutable defaults. Authorization is decided at command time and represented by immutable authority references/decision facts; replay verifies recorded structure, not a fresh policy decision.

## 8. Legacy P6.1 treatment

P6.1 event records are not automatically convertible to v2 because some commands omitted changed aggregate events and some payloads omit complete reservation/child state. Migration must classify records as:
- **fully reconstructible** from independently authoritative, versioned source facts;
- **checkpoint-required**, where an authorized reconciliation establishes a new baseline snapshot with explicit provenance;
- **unreconstructible**, which blocks automatic projection recovery.

No synthetic historical event may be fabricated without a recorded migration command, actor, authority, source references and explicit uncertainty. A checkpoint does not claim that omitted historical events existed; it establishes a verified starting projection at a known sequence.

## 9. Acceptance vectors

The following minimum cases are normative:

| Case | Expected changed aggregates | Expected event count | Version outcome |
|---|---:|---:|---|
| Register L | L | 1 | L=1 |
| Reserve R from L | L, R | 2 | L+1, R=1 |
| Commit R before expiry | R | 1 | R+1; L unchanged |
| Expire R | L, R | 2 | L+1, R+1 |
| Release R | L, R | 2 | L+1, R+1 |
| Partial consume | L, R, C | 3 | L+1, R+1, C=1 |
| Full consume | L, R, C | 3 | L+1, R+1, C=1 |
| Quarantine L | L | 1 | L+1 |

Additional negative vectors:
- omitted/extra aggregate in expected-version vector;
- stale version on any one member aborts all members;
- duplicate or missing command ordinal;
- event count mismatch;
- child ID collision;
- insufficient committed remainder;
- quantity/unit mismatch;
- duplicate idempotency key with changed request fingerprint;
- same idempotent retry returns original receipt and event IDs;
- injected failure after any event append leaves no partial command visible;
- replay of legacy incomplete P6.1 movement cannot silently create a child lot.

## 10. Implementation sequence after P6.3a

1. Select durable repository and transaction isolation/CAS contract (P6.3b).
2. Implement command/event/receipt validators as pure schema code and golden vectors.
3. Implement one atomic multi-aggregate repository boundary.
4. Implement deterministic reducers only after schema and persistence selection.
5. Add snapshot/recovery and crash/outbox tests.
6. Keep P6.1 in-memory domain API as a research reference; do not retrofit persistence by appending its returned events after mutation.

**Decision:** P6.3a closes the event-semantics design gap. It does not make P6.1 replayable, does not implement persistence, and does not authorize production deployment.
