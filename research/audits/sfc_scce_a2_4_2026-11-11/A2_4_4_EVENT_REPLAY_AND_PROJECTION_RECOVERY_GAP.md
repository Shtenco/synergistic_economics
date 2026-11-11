# A2.4.4 — global event order and projection-recovery gap

## Status

**Finding confirmed from source review; design contract specified; no runtime
implementation or test PASS is claimed.** This document is an explicit
boundary between durable event persistence and deterministic SFC recovery.

## Evidence inspected

The current prototype at this branch revision contains:

- `event_groups(group_id, causation_id, payload_sha256, payload_json)`;
- `events(event_id, group_id, event_type, effective_period, event_index,
  payload_sha256, payload_json)`;
- `journal_lines(event_id, line_no, posting_json)`;
- a unique `event_index` only within each group;
- `get_group(group_id)`, `counts()` and `integrity_check()`, but no
  committed-group enumeration API or durable cross-group sequence;
- atomic `append_group()` under `BEGIN IMMEDIATE`, but no SFC position or
  sector projection tables in that transaction.

The current schema therefore preserves order *inside* a group but does not
persist a canonical total order *between* groups. Sorting group IDs is
deterministic serialization, not evidence of economic or commit chronology.
Sorting only by `effective_period` is also insufficient: multiple groups may
share a period, and late-arriving/backdated events can change the required
replay path. SQLite rowid must not be promoted to a public ordering contract.

## Finding A — missing cross-group replay order

A deterministic SFC replay requires a stable, immutable ordering key for every
committed transaction group, plus the existing event index inside each group.
The store currently has no such key and cannot enumerate all groups in a
canonical order through its public API.

Consequences:

1. A consumer cannot prove that two independent reconstructions apply groups
   in the same order.
2. A replay cursor cannot identify an unambiguous prefix of the durable log.
3. A final position match alone cannot prove that intermediate states were
   reconstructed along the same event path.
4. A group-level idempotency key prevents duplicate persistence, but does not
   by itself make downstream projection application exactly-once.

## Finding B — event persistence and projection state are not atomic

The adapter validates events through `EntityJournal` and then calls
`FinancialEventStore.append_group()`. The adapter rolls back its own newly
added in-memory journal entries when persistence fails. This is useful
failure containment, but the adapter does not write SFC instrument positions,
sector balance sheets, or a projection checkpoint.

A crash after durable append but before projection update leaves a durable
event group with stale or absent projections. A retry must not apply its
economic effect twice. A crash after projection update but before a durable
cursor/checkpoint can also cause duplicate application on restart.

## Required design contract before implementation

### 1. Separate economic time from log order

Persist two distinct concepts:

- `effective_period`: the economic/accounting period to which an event belongs;
- `commit_sequence`: a monotonically increasing, database-assigned sequence
  for the transaction group, allocated while holding the same write
  transaction that inserts the group.

Within a group, retain `event_index`. The canonical durable log order is
`(commit_sequence, event_index)`. Do not infer commit order from event IDs,
group IDs, timestamps, or rowid.

A late-arriving event with an earlier effective period remains later in
commit order. It must trigger an explicit period-reopen/rebuild or adjustment
policy; it must not silently be inserted into the historical log prefix.

### 2. Sequence allocation and migration

A future schema migration must:

- allocate a unique, immutable `commit_sequence` under `BEGIN IMMEDIATE`;
- enforce uniqueness and positive integer range in SQLite;
- commit sequence allocation, group envelope, events and journal lines in one
  transaction;
- expose read-only ordered group/event iteration;
- verify sequence uniqueness, continuity where required, event-index
  continuity and payload/hash mirrors in `integrity_check()`.

**Legacy migration warning:** schema v2 does not contain enough information
to reconstruct true historical cross-group commit order. A migration must
not claim that lexical group-ID order or rowid recovers it. Either require an
explicit operator-supplied sequence map for populated legacy stores, or mark
the reconstructed order as unverified and prohibit authoritative projection
replay until it is attested. Empty stores can be upgraded without this
ambiguity.

### 3. Exactly-once projection protocol

Preferred single-database protocol:

1. Validate typed journal events before persistence.
2. Begin one SQLite write transaction.
3. Resolve idempotency by group ID and immutable payload hash.
4. Insert the group, ordered events and postings.
5. Apply all affected instrument-position and sector-balance deltas.
6. Advance the projection's applied-through `commit_sequence`.
7. Commit once.

The event log, projections and applied-through cursor must share the same
SQLite transaction. A retry after an uncertain commit acknowledgement must
return the existing group result and must not reapply deltas.

If projections are maintained in a separate database/service, use an
at-least-once delivery protocol with a durable inbox/deduplication key and
projection cursor committed atomically with each projection update. Do not
call this exactly-once delivery; the defensible guarantee is exactly-once
*effect* under idempotent consumer state transitions.

### 4. Deterministic rebuild and reconciliation

A rebuild must:

- start from an explicit, versioned opening snapshot (or an explicitly
  declared zero opening state for a synthetic fixture);
- read immutable groups in canonical commit order and events in event_index
  order;
- apply account-normal-side-aware instrument deltas using Decimal values;
- retain per-event checkpoints, not only final balances;
- persist the rebuild cursor/checkpoint atomically with the rebuilt state;
- compare rebuilt positions, holder/issuer mirrors, sector totals and SFC
  identities against independent gold expectations;
- fail closed on sequence gaps, duplicate sequence, hash mismatch, unknown
  instrument identity, invalid period transition or negative positions where
  the selected opening/credit-facility contract prohibits them.

A rebuild of a live multi-period system must not assume zero opening stocks or
universal non-negative balances. Those are fixture-specific SFC-GOLD-1 v1
assumptions, not general ledger rules.

## Required adversarial tests

1. Two groups committed in order A then B replay in the same order after
   closing and reopening the store.
2. Concurrent writers receive unique, serializable commit sequences.
3. A duplicate group retry returns the original sequence and has no second
   projection effect.
4. Same group ID with changed content is rejected.
5. Same event ID across groups is rejected.
6. Crash/failure before group commit leaves no group, events, postings,
   projection delta or advanced cursor.
7. Crash after commit but before caller acknowledgement is recovered by
   idempotent retry with exactly one projection effect.
8. Crash during projection update rolls back both projection changes and
   cursor, or, for a separate projection database, leaves a replayable inbox
   item with no partial state.
9. A deliberate gap or tampering in commit_sequence is detected.
10. A backdated effective_period does not rewrite commit order silently; the
    configured reopen/rebuild policy is exercised.
11. Rebuild from opening snapshot produces the same per-event and closing
    positions as independent gold data.
12. A final-state-preserving intermediate mutation is rejected by checkpoint
    comparison.

## Non-goals and safety boundary

This design does not establish distributed consensus, multi-region ordering,
replication, external side-effect exactly-once semantics, legal finality,
period-close governance, or production operational security. SQLite remains a
single-host component with filesystem and runtime-version constraints already
documented in the durable event-store contract.

## Gate impact

- Durable group append and local atomicity: source prototype exists; execution
  evidence remains pending.
- Cross-group canonical durable group commit order: **SOURCE-IMPLEMENTED in schema v3; execution pending**.
  Projection replay remains incomplete until the SFC projections and applied-through cursor exist.
- Durable SFC position/sector projections: **OPEN — not implemented**.
- Crash-safe projection cursor and exactly-once effect: **OPEN — not
  implemented**.
- A2.4.4 closure: **OPEN**.
- A2.4.8: **BLOCKED** pending its upstream gates.

No claim of production readiness, completed crash testing, or empirical
validation follows from this design document.


## 11 November implementation update — schema v3 global commit sequence

The SQLite event store has advanced from schema v2 to schema v3. Each
new transaction group receives a database-assigned, positive, unique
commit_sequence while holding the same BEGIN IMMEDIATE write transaction
that inserts the group, event envelopes and journal postings. The sequence
is committed atomically with the group; an identical replay returns before
sequence allocation. iter_groups() exposes groups in ascending sequence
order while keeping the sequence outside the original hashed economic
envelope. The integrity checker requires the committed sequence to be
contiguous from 1 through N.

The sequence represents durable store commit order, not event effective
period, legal priority, causal order across independent upstream systems,
or a claim that late-arriving events are economically later. Consumers must
retain effective_period separately and define any domain-specific
restatement/replay policy.

### Legacy migration boundary

- Fresh stores start at schema v3.
- An empty v2 store can be upgraded safely.
- A populated v2 store with exactly one group can be upgraded with sequence 1:
  its sole group's position in cross-group chronology is unambiguous.
- A populated v2 store with more than one group is rejected. The old schema
  contains no cross-group order, so assigning one automatically would invent
  history. Recovery requires an explicit operator-attested sequence map and
  a controlled export/re-import procedure; no automatic mapping is inferred.
- The v1 migration path is likewise fail-closed when more than one group
  exists. A single group's within-group order is retained and its global
  sequence becomes 1.
- The failed migration is transactional and leaves the original v2 database
  at schema version 2.

### Adversarial controls added to source

The event-store audit now includes backdated effective periods, replay without
sequence consumption, concurrent independent writers, contiguous sequence
verification, out-of-band sequence tampering, and rejection of ambiguous
populated-v2 migration. These controls are committed source fixtures; they
are not a completed execution result until exact-head CI logs are inspected.

### Remaining open boundary

Schema v3 provides a deterministic order of durable group commits on this
single SQLite store. It does not yet provide atomic SFC position/sector
projection updates, an applied-through cursor, multi-process projection
recovery, or a distributed ordering protocol. Those remain separate open
gates; no exactly-once projection effect or A2.4.4 closure is claimed.


### Recovery hardening — unstamped schema-v2 initialization

The initializer now inspects the events-table layout when PRAGMA user_version
is zero. If event_index exists, it recognizes the database as an interrupted
v2 initialization and applies the same fail-closed v2-to-v3 migration policy;
it no longer treats that state as a fresh database. The audit fixture covers
both stamped and unstamped populated-v2 databases with multiple groups, plus
a populated one-group v2 migration that safely receives sequence 1.
