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
  and assigns stable event indexes;
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
12. post-write SQLite and mirror integrity checks.

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
