# A2.4.4 — durable financial event store contract

## Finding

The entity/sector journal fixture validates event composition, balanced
postings, holder/issuer mirrors and several credit/deposit event distinctions.
Its event registry is nevertheless an in-memory dictionary. Its event-ID
uniqueness guarantee therefore ends when the Python process ends. A restart
followed by delivery of the same event can be accepted again by a new journal
instance. In addition, separate calls can persist an economic transaction's
loan and deposit-transfer legs independently, with no atomic group boundary.

A balanced journal is not sufficient protection against duplicate processing
or partial persistence. The event envelope, all postings belonging to it, and
all events in one declared transaction group need one durable commit boundary.

## Prototype implementation

`prototype/financial_event_store.py` adds a standard-library SQLite store:

- stable `group_id` identifies the atomic transaction group;
- optional `causation_id` records the upstream economic cause/agreement;
- event IDs are globally unique in the database, not only in one Python object;
- a canonical JSON envelope and SHA-256 digest bind group metadata, event
  order, event types, periods and complete posting payloads;
- event order is stored explicitly as `event_index` with a per-group unique
  constraint; integrity verification never relies on implicit SQLite rowid;
- schema version 2 migrates version-1 event rows in their original rowid order
  and assigns stable event indexes; it also detects the legacy v1 table layout
  if initialization was interrupted before the old code stamped user_version;
- each event and each posting is inserted under one `BEGIN IMMEDIATE`
  transaction;
- an identical group replay returns `False` without writing new rows;
- reuse of a group ID with changed content is rejected;
- reuse of an event ID by another group is rejected;
- event and posting rows are protected against UPDATE and DELETE by database
  triggers;
- SQLite WAL mode and `synchronous=FULL` are configured and verified on
  initialization; in-memory databases and non-finite/non-positive timeouts are
  rejected; the schema has an explicit version;
- `integrity_check()` verifies SQLite integrity, foreign keys, group/event
  payload hashes, event order, and the posting rows against the canonical
  event envelope.

The store intentionally accepts only decimal amounts encoded as strings.
Binary floating-point values are rejected before persistence.

## Adversarial controls

`audit_financial_event_store.py` is added to the existing prototype CI
unittest wrapper. It covers:

1. persistence across destruction/reconstruction of the store object;
2. identical replay across restart without duplicate rows;
3. changed-content replay under the same group ID;
4. global event-ID reuse across different groups;
5. rejection of binary floating-point amounts;
6. database-level rejection of updates/deletes to committed rows;
7. injected failure after the group and event rows have started writing,
   requiring complete rollback of group, event and posting rows;
8. rejection of in-memory configuration and non-finite lock timeouts;
9. concurrent identical group delivery (one insert, one replay);
10. concurrent cross-group event-ID collision (exactly one winner);
11. version-1 to version-2 migration preserving original group event order;
12. recovery of a v1 table layout whose user_version stamp was interrupted;
13. post-write SQLite and mirror integrity checks.

The fixture uses a non-bank loan origination and an existing-deposit transfer
inside one transaction group, with a shared causation ID. This establishes
mechanical linkage metadata and atomic storage; it does not itself assert that
every real-world non-bank credit contract must be settled by a deposit transfer.

## Strict limits — not production closure

This is a local, single-database, single-host prototype. SQLite durability
depends on the underlying filesystem and storage device honoring locking and
synchronization semantics. WAL must not be placed on a network filesystem.
SQLite documents a WAL-reset bug affecting releases through 3.51.2, fixed in
3.51.3 with backports in 3.50.7 and 3.44.6; the exact runtime SQLite library
version must be recorded and checked before enabling concurrent production
writers. It is not a distributed consensus service,
multi-region ledger, replicated event log, or protection against an attacker
who can rewrite the database and its hashes.

The store is deliberately downstream of accounting validation. It does not
replace `EntityJournal.post()`, does not independently validate the full
double-entry/account taxonomy, and must not be fed unvalidated caller payloads.
The present implementation atomically stores event envelopes and journal
postings, but **does not yet atomically update the SFC instrument-position
register or sector balance-sheet state**. Those projections must either be
written in the same database transaction or be rebuilt deterministically from
the immutable event log with a replay cursor and reconciliation barrier.

No production financial runtime is migrated to this store. The in-memory
`EntityJournal.events` remains non-durable until that integration occurs.
The new adapter preserves the complete entity, sector, counterparty, issuer
and instrument dimensions, but it does not itself apply the resulting postings
to an SFC position projection. The journal object is not made thread-safe by
this adapter; calls against one instance must currently be serialized.
No exact-head CI result is claimed until GitHub Actions runs and logs complete.

## Acceptance gates before production use

- [ ] Run the new audit script and the full existing 15-script A2.4 wrapper on
      the exact PR head; retain logs, interpreter version, exit status and
      artifact hashes.
- [ ] Add a typed adapter from validated `JournalEvent` objects to the store;
      prohibit bypassing `EntityJournal` validation.
- [ ] Prove transaction-group construction and causation semantics for bank
      origination, non-bank lending, payments and multi-leg settlement.
- [ ] Persist SFC instrument positions and journal postings atomically, or
      demonstrate deterministic projection rebuild after crash at every
      commit boundary.
- [ ] Add crash/restart tests around begin, event insertion, posting insertion,
      commit acknowledgement and projection update.
- [ ] Test concurrent writers, busy/timeout behavior, backup/restore,
      integrity recovery and schema migration. The runtime SQLite build must
      include the WAL-reset fix (SQLite 3.51.3+ or a patched backport such as
      3.50.7 / 3.44.6) before multi-connection production writes are enabled.
- [ ] Define operational ownership, access control, encryption, retention,
      audit export, key management and disaster-recovery objectives.
- [ ] Reconcile entity claims, issuer liabilities and sector accounts from the
      persisted log over multiple periods.

**Status:** component prototype added; exact-head execution pending; production
integration and A2.4.4 closure remain OPEN. A2.4.8 remains BLOCKED.


## Additional review — global replay order and projection recovery

A separate source-level review now distinguishes local group atomicity from
system-wide deterministic replay. Schema v2 stores `event_index` only within
each transaction group. It has no durable cross-group `commit_sequence` and
the public API has no ordered all-groups iterator. Consequently, a consumer
cannot yet identify a canonical durable log prefix across groups. Group-ID
sorting or implicit rowid order is not a defensible economic chronology.

The adapter also persists the validated group after journal validation but
does not atomically update SFC instrument positions, sector balance sheets,
or a projection cursor. A crash between durable append and projection update
therefore requires a replay protocol that is not implemented in the current
component.

The detailed design and acceptance contract is recorded in
`A2_4_4_EVENT_REPLAY_AND_PROJECTION_RECOVERY_GAP.md`. The required next
architecture separates effective accounting period from immutable commit
sequence, preserves event_index inside groups, and atomically couples event
append, projection deltas and the applied-through cursor in one database
transaction (or uses a separately specified idempotent inbox protocol).

**Gate status:** local append atomicity remains a prototype capability;
cross-group canonical order, durable SFC projections and crash-safe
projection cursor remain OPEN. No production replay or exactly-once effect
claim is made.


## Schema v4 — tamper-evident group-order chain

Schema v4 extends the global commit sequence with two fields on each event
group:
- `previous_group_hash`: the preceding committed group's chain hash, or a
  fixed genesis hash for the first group;
- `group_chain_hash`: SHA-256 over canonical JSON containing commit sequence,
  group ID, immutable group-payload hash and previous-group hash.

The chain is computed and persisted in the same `BEGIN IMMEDIATE` transaction
as the group, events and journal postings. `integrity_check()` walks groups
in commit order, verifies each predecessor link and recomputes every chain
hash before checking event and posting mirrors. This detects a permutation
of sequence numbers even when the resulting sequence set remains contiguous.

Migration from v3 is transactional: it drops the event-group update trigger
inside the migration transaction, adds the chain columns, seals the existing
sequence order, reinstates the append-only trigger and stamps schema v4.
If migration fails, SQLite rolls back the DDL, data updates and trigger
changes together. A v3 database whose version marker was not stamped is
recognized from its existing `commit_sequence` column and upgraded. An
unstamped v4 layout is recognized from `group_chain_hash`.

**Trust boundary:** this is a local tamper-evidence chain, not a cryptographic
external anchor. A privileged actor able to rewrite all rows and recompute
the complete chain can replace the history. Detecting full-database rewrite
requires independently retained signed checkpoints or external anchoring.
Migration seals the order visible at migration time; it cannot retrospectively
prove that pre-v4 history was never modified.

The audit fixture now covers sequence permutation with a still-contiguous
`{1, 2}` sequence set, v2-to-v4 migration, interrupted v3-to-v4 migration,
and interrupted v4 version stamping. These are source-level controls until
exact-head CI completes.
