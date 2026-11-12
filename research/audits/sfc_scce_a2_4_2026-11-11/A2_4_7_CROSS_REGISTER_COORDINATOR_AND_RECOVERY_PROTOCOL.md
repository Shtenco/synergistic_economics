# A2.4.7 — cross-register coordinator, period governance and external recovery protocol

**Status:** architecture contract and acceptance plan; production coordinator is NOT implemented by the synthetic integration fixture.  
**Scope:** physical flows, capital/cohort stock, labour/time/consent, product quantities and valuation, legal/rights evidence, and GOLD-2A financial journal/projection.

## 1. Non-negotiable consistency model

A single SQLite transaction cannot atomically commit six independently owned register stores. The current P2 transaction remains the authoritative atomic boundary for the financial event log and its SFC projections only. A shared scenario/correlation ID is not a substitute for register-native event IDs and does not create distributed atomicity.

The production target is a durable coordinator using a participant prepare/commit protocol. It provides atomic *visibility* to readers through a coordinator commit barrier, not a claim that several database engines share one physical ACID transaction.

Every participant must implement a durable inbox/outbox and idempotent operations. A participant that cannot prepare durably and later commit or abort by token is not eligible for coordinated writes.

## 2. Canonical cross-register transaction envelope

Required immutable envelope fields:

- `transaction_id`: globally unique coordinator transaction ID;
- `scenario_id`: correlation root only;
- `causation_id` and optional `correlation_id`;
- `schema_version`, `mapping_version`, `created_at`;
- ordered participant descriptors with register name, native event/record ID, expected revision, payload hash and required evidence references;
- canonical payload digest and deterministic participant ordering.

Each register retains its own native identity. The six minimum participant roles are `physical`, `capital`, `labour`, `product`, `legal_rights`, and `financial`. One transaction may contain multiple native events per register, but IDs must remain unique in their own namespaces. Native quantities, units, currencies, valuation bases, time bases, consent states and legal evidence are never collapsed into a generic amount field.

## 3. Durable coordinator state machine

Allowed states:

1. `NEW` — immutable envelope accepted; no participant has prepared.
2. `PREPARING` — prepare requests are being issued in deterministic participant order.
3. `ABORT_DECIDED` — at least one prepare failed or timed out before the commit decision; abort every participant that prepared.
4. `PREPARED` — every participant returned a durable prepare token and matching payload digest.
5. `COMMIT_DECIDED` — coordinator durably records the irreversible global decision before sending any commit request.
6. `COMMITTING` — idempotent commit delivery and receipt collection.
7. `COMMITTED` — every participant's durable receipt matches transaction ID, native event IDs, payload digest and prepare token.
8. `RECOVERY_REQUIRED` — a participant is unavailable or reports a conflicting receipt; visibility remains blocked until reconciled.

A crash before `COMMIT_DECIDED` may resolve to abort after checking all participant prepare records. A crash after `COMMIT_DECIDED` must never silently roll back or switch to abort: recovery replays commit delivery until all durable receipts are present. A compensating business action is a new, linked event, not deletion of a committed event.

Readers that require a cross-register-consistent view must use a commit barrier: expose a transaction only when its coordinator state is `COMMITTED` and all participant receipts match. Register-local diagnostic readers may expose prepared state only when explicitly marked non-final.

## 4. Participant contract and idempotency

Each participant must persist:

- unique `(transaction_id, register_name, native_event_id)` inbox key;
- canonical payload digest and schema/mapping version;
- `prepare_token`, expected prior revision and resulting revision;
- prepared/committed/aborted state and immutable receipt;
- an outbox notification that can be delivered repeatedly.

`prepare`, `commit`, and `abort` must be idempotent. Reuse of a transaction/native-event key with a different digest is a hard conflict. A participant must reject stale expected revisions and must not expose prepared changes as committed. Prepare tokens must be durable across process restart. Coordinator and participant state transitions must be protected by database constraints and compare-and-swap revision checks.

Timeout is not proof of failure: the coordinator queries participant state before deciding whether an operation can be retried. Participant order is stable to reduce deadlock risk. Leases are not a replacement for durable prepare records.

## 5. Closed periods, corrections and formal reopening

Default rule: a closed accounting/economic period is immutable. New late-arriving information does not get silently inserted into the historical prefix.

Normal correction path:
- create a new event in the currently open period;
- reference the original native event, original period, reason code, authority and evidence;
- use explicit reversal/adjustment semantics and preserve original amounts and dimensions;
- link both events in the audit graph and disclose the restatement effect separately.

Formal reopen is exceptional and must require two-person approval (period owner plus independent controller), a reason, evidence, scope, affected registers, and a pre-reopen signed checkpoint. Reopen creates a new projection generation from the immutable event log under an explicit restatement policy. The prior generation and its close checkpoint remain retained. A generation switch is atomic at the coordinator/read-barrier level only after every affected register has rebuilt and reconciled. The process records old/new generation IDs, changed event set, opening/closing differences and approver identities.

The P2 append path currently rejects backdated events. It does not yet implement this governed rebuild protocol; this section defines the production acceptance contract rather than claiming that reopening is already available.

## 6. External signed checkpoints

A local SHA-256 chain stored only inside the same SQLite file is tamper-evident against accidental changes but cannot prove that the entire database was not rewritten.

At each period close and configured commit interval, produce a canonical checkpoint manifest containing:

- repository/service identity, database/schema version, mapper version and projection generation;
- commit sequence, event-group chain head, event count and immutable event-log root;
- instrument/control opening snapshot hashes;
- instrument/control projection state hashes, coverage count, applied-through cursor and period close state;
- canonical backup artifact digest and backup creation metadata;
- monotonic checkpoint sequence, UTC timestamp and signer key ID.

Sign the canonical manifest with an asymmetric key held outside the database trust domain (preferably KMS/HSM-backed Ed25519 or an equivalently reviewed signing service). Publish manifest, signature and backup digest to independently administered append-only/WORM storage. The trusted public-key registry and minimum accepted checkpoint sequence must also be external to the SQLite file. Verification rejects unknown/revoked keys, invalid signatures, rollback to an older sequence, mismatched backup hashes or replay state, and unexplained gaps.

Never store the only signing key, public trust root or latest checkpoint inside the database being protected. A signature proves origin and integrity of the signed manifest; it does not by itself prove that the source ledger was economically or legally correct.

## 7. Backup, corruption and restore drill

A production backup gate must:

1. create a consistent SQLite online backup (including WAL-consistent state);
2. run `PRAGMA integrity_check` and `PRAGMA foreign_key_check` on the backup;
3. run the independent event-chain and projection replay verifier;
4. compare the backup digest and replay roots with the latest externally signed checkpoint;
5. restore to a clean isolated path and repeat all checks;
6. measure and record RPO/RTO, then prove the restored service can accept an idempotent retry without duplicate effects.

Corrupt-primary recovery must quarantine the original database and its WAL/SHM files, restore only from a verified backup, replay any externally anchored committed tail, and preserve the corrupt artifact for forensic review. Never repair a corrupt primary in place and then treat it as trusted. The new P2 audit adds a synthetic invalid-file/verified-backup restore drill; this is not yet a full operational disaster-recovery exercise.

## 8. Required fault-injection matrix

The coordinator gate must terminate the process (not merely raise an exception) after each durable boundary:

- coordinator envelope insert;
- each participant prepare request and prepare receipt;
- durable `PREPARED` state;
- durable `COMMIT_DECIDED` state;
- each participant commit request and receipt;
- final `COMMITTED` barrier publication;
- signed checkpoint publication and backup artifact registration.

For every point, restart coordinator and all participants independently, replay outboxes, and assert exactly one native effect per event, no visible partial transaction, deterministic decision recovery, matching hashes and stable idempotency. Also test duplicate/reordered messages, participant timeout, disk-full, process kill, host restart, WAL recovery, stale revision, conflicting digest, key rotation/revocation and backup restore.

## 9. Exit criteria

This gate is not closed until all six real register adapters implement the durable participant contract; coordinator and participant state machines are persisted; crash/restart and duplicate-delivery tests pass on the exact same commit; signed checkpoints are independently verified; restore drills meet approved RPO/RTO; closed-period correction/reopen workflow has dual approval and generation rebuild; and the full three-workflow CI set is green on one HEAD.

Until then, A2.4.7 remains OPEN. The current cross-register fixture is valuable integration evidence but is not a production coordinator and must not be presented as distributed ACID or exactly-once delivery.


## 10. Coordinator protocol implementation — 12 November 2026

Added `prototype/cross_register_coordinator.py` with a durable coordinator state machine and six independent SQLite participant stores. The implementation provides:

- immutable canonical transaction envelope and per-participant payload digests;
- native event identity, expected stream revision and deterministic participant ordering;
- durable participant inbox/prepare token and revision compare-and-swap;
- participant-local immutable event rows and receipts;
- durable coordinator decision state, with `COMMIT_DECIDED` irreversible;
- abort recovery before the commit decision and commit replay after the decision;
- commit-barrier visibility only after six matching durable participant receipts;
- immutable coordinator and participant transition-history tables;
- idempotent prepare/commit/recovery and rejection of stale revisions or changed-content transaction-ID reuse.

Added `audit_cross_register_crash_matrix.py`. It launches a fresh subprocess for 25 termination points: after each of six participant prepares, each coordinator prepare receipt, each participant commit, each coordinator commit receipt, and after commit-barrier publication. It then reconstructs all seven database connections, recovers the transaction and checks that pre-decision crashes abort without effects, post-decision crashes commit exactly one effect per participant, partial state never crosses the visibility barrier, and repeated recovery does not duplicate events. Additional controls cover changed-content replay, stale revision rejection and immutable state-transition history. The audit is wired into the A2.4 workflow and the Prototype unittest wrapper.

**Strict implementation boundary:** these six SQLite participants are independent durable protocol conformance stores, not yet adapters to the authoritative domain stores. They prove the coordinator protocol mechanics only. The production gate still requires replacing each conformance participant with a domain adapter that durably prepares and commits its actual physical, capital, labour, product, legal/rights or financial records in that register's authoritative storage. In particular, this module does not make the current synthetic cross-register fixture distributed-atomic.

The new subprocess matrix is committed but has not yet been executed successfully in this session. Exact-HEAD CI completion and log inspection are required before marking it PASS. Host/power-loss testing, external signatures/WORM storage, period-generation reopening and full multi-register disaster recovery remain open.


## 11. Closed-period governance and signed checkpoint implementation — 12 November 2026

Added `prototype/period_governance.py`:
- closed-period correction records are append-only and must be posted in an open period; corrections at or before the latest closed period are rejected;
- reopening binds to the currently active generation's checkpoint, not the original close checkpoint;
- a reopen request requires all six registers in scope, a reason, evidence and the verified pre-reopen checkpoint;
- two distinct approvers are required in the separate `period_owner` and `independent_controller` roles;
- each of the six registers must submit a rebuild receipt with old/new generation, common immutable event-log root, event count, opening/closing state hashes and reconciliation hash;
- publication is refused until all six receipts agree on the same source root; the active generation pointer is switched in one governance-database transaction while prior generation history remains immutable.

Added `prototype/external_checkpoints.py` with Ed25519 signing/verification, a canonical manifest schema, an external trusted-key registry interface, key-revocation checks, monotonic checkpoint-sequence enforcement, immutable object-key semantics and backup-byte digest verification. The period-governance API requires an injected external checkpoint verifier for closure, reopening and generation publication.

**Strict deployment boundary:** `LocalImmutableAnchor` is only a SQLite conformance/test anchor. It is not independently administered WORM storage and its local latest pointer is not protected against an administrator rewriting the database. Production still needs a real external object-lock/WORM backend, KMS/HSM-backed key custody, independently administered trust-root/revocation state, key rotation/revocation operations and external monotonic-sequence protection. The period-governance ledger records rebuild attestations but does not itself execute six domain rebuilds; those must come from the real participant adapters. These audits are committed but awaiting exact-HEAD CI execution.
