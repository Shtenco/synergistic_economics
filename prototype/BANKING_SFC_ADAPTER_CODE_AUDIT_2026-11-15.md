# Banking SFC adapter code audit — 2026-11-15

Scope: PR #13, branch `research/bank-deposit-credit-audit-fix-20261115`.
Reviewed source: `operating_financial_sfc_adapter.py`, `sfc_source_contracts.py`,
`durable_event_register.py`, `sfc_projection_kernel.py`, and the adapter/source-contract tests.

## Confirmed implementation

- The native adapter is deliberately separate from GOLD-2A and the legacy
  `SFCProjectionStore`; it consumes committed `OperatingFinancialRegister`
  history rather than weakening the EntityJournal mapper.
- `from_register()` calls the financial register's hash-chain verifier before
  reading authorized history. The adapter also validates immutable native
  envelope digests when those envelope fields are present.
- Source events and movement IDs are checked for duplicates; movements require
  explicit evidence, explicit opening rows, a supported T classification,
  version-pinned instrument terms, effective-dated sector membership and
  reciprocal asset/liability mirror sides.
- The pure projection kernel enforces explicit openings, exact Decimal
  roll-forward, consecutive-period continuity and configured non-negative
  gross positions.
- The adapter computes transaction-only financial net lending by position
  owner sector, currency and period. It does not insert a balancing plug.
- Importantly, the test
  `test_from_register_replays_interbank_and_refinancing_history` already
  exercises a real durable financial-register history containing interbank
  settlement and central-bank refinancing advance/repayment, then projects
  it across periods 3 and 4. The earlier blockers note incorrectly listed
  durable-history integration of these two event families as still missing.
  That item is therefore covered at the adapter integration-test level.

## Remaining blockers — still release-blocking

1. **No durable native SFC projection store.** The adapter returns an in-memory
   `BankingSFCProjection`. There is no atomic persisted transaction spanning
   source cursor, source-event coverage, movement coverage, openings,
   roll-forward rows, sector aggregates and mapper version.
2. **No durable adapter checkpoint/recovery.** There is no restart path that
   reloads a sealed projection, re-verifies the source history and registries,
   independently re-derives every movement, and compares the persisted
   projection before advancing an applied-through cursor.
3. **No signed period-close assembler.** No complete six-register close protocol
   requires each domain register to attest its period boundary, source sequence,
   checkpoint, registry versions and either activity or an explicit
   zero-activity declaration. Absence of events is not evidence of zero activity.
4. **Opening exports remain incomplete.** The durable register exports deposit
   and reserve opening evidence, but loan and refinancing opening positions in
   the multi-period fixture are caller-supplied synthetic snapshots. Every
   first-active-period opening needs a durable evidence reference and source
   checkpoint.
5. **No complete capital account.** Financial net lending is transaction-mapped
   for supported financial instruments only. Capital transfers, non-financial
   investment acquisition/disposal, saving, capital-account counterpart flows
   and any governed statistical discrepancy are not yet integrated into one
   same-cohort six-sector reconciliation.
6. **Instrument lifecycle remains principal-only.** Rate metadata is not an
   interest engine. Interest accrual/payment, fees, arrears, maturity cashflows,
   impairment, default, restructuring, write-off and collateral valuation remain
   unsupported and must continue to fail closed until their contracts exist.
7. **Sector authority is split.** The adapter pins a versioned effective-dated
   sector registry, while write-side financial authorization still uses a
   constructor-supplied static sector map. Governance and sealed-period
   reclassification/reprojection rules remain necessary.

## Required next implementation slice

Implement a native SQLite projection store with an explicit schema/version and
one atomic append operation. The transaction must persist:

- pinned mapper version, instrument-registry digest, sector-registry digest and
  ordered opening-snapshot digests;
- source register identity, source event IDs, idempotency keys, aggregate
  revisions, commit sequence, source payload/envelope digests and chain cursor;
- one-to-one source-event and movement coverage;
- canonical position identity, period, T/V/O components, opening and closing;
- sector transaction asset/liability totals and financial net lending;
- an immutable checkpoint containing the applied-through source sequence and
  deterministic projection digest.

The append path must reject stale cursors, duplicate or changed-content source
events, changed mapper/registry versions, incomplete openings, missing mirror
sides and non-contiguous periods before commit. Replaying identical source
history must be idempotent. Reusing an event ID with changed bytes must fail.

Recovery must verify the source register, load the pinned registries and
openings, rebuild the expected projection through the pure adapter/kernel,
compare every persisted coverage/position/sector/checkpoint row, and fail closed
without mutating the cursor on any mismatch. Add subprocess crash injection at
each SQLite write boundary and verify both pre-COMMIT rollback and post-COMMIT
restart/replay. This is a single-host SQLite guarantee, not distributed
consensus or external disaster recovery.

Only after this financial projection slice is durable should the period-close
assembler bind independently declared domain-register completeness and the
capital-account bridge. Do not fabricate events in physical, capital, labour,
product or legal-rights registers for a bank-only transaction.

## Validation status

This file records source inspection only. No tests are claimed as executed by
this audit note. The most recent observed commit in this continuation was
`e824a669602b3c61f0c68b319b7637d199224f8e`; its associated Prototype workflow
run `43707978636` was cancelled. A new exact-HEAD green run is required after
subsequent changes. Keep PR #13 Draft and unmerged until the complete suite and
the relevant long-running validation gates pass on one unchanged HEAD.


## Follow-up implementation — durable projection snapshot v1

Implemented on the PR branch after the source audit:

- `banking_sfc_projection_store.py` adds a schema-versioned SQLite store with
  immutable snapshot and checkpoint tables, SHA-256 projection/checkpoint
  digests, explicit source-register identity and applied-through global commit
  sequence, pinned instrument/sector/opening digests, and one transaction for
  snapshot plus checkpoint.
- `banking_sfc_projection_pipeline.py` verifies the native financial register
  hash chain, reads the authorized aggregate history, checks ordered unique
  commit-sequence metadata, rebuilds through the pure adapter, and persists or
  independently recovers the projection.
- Store tests cover deterministic idempotent replay, changed content at the
  same cursor, stale cursors, allowed gaps in the global register sequence
  (other aggregate events may occupy sequence numbers), registry/opening drift,
  deterministic recovery mismatch, transaction rollback after each database
  write boundary, and immutable persisted rows.
- Pipeline tests cover source verification before persistence and a full
  deterministic project/persist/rebuild/recover pass.

The source cursor is a global register commit sequence, not an aggregate-local
counter; therefore monotonicity is required, but consecutive integer values
are not. This avoids rejecting valid histories containing unrelated register
events between financial aggregate events.

### Exact current implementation boundary

This is a durable **single-host projection snapshot/checkpoint**, not yet the
complete release gate specified above. The store currently persists the
projection's complete deterministic canonical JSON as one immutable snapshot;
it does not yet normalize every source event, movement, position, sector
aggregate and source cursor into independently queryable relational coverage
tables. Recovery compares the whole canonical snapshot and checkpoint digest
against a fresh projection; it does not yet independently compare separately
stored per-row tables because those tables do not exist.

The pipeline's `source_register_id` is an explicit caller-supplied stable
identity. The adapter still needs a first-class source-register identity
contract, key/authority governance, signed multi-register period-close
assembler, complete loan/refinancing opening exporters, capital-account
integration, and instrument lifecycle events for interest, arrears, impairment,
default, restructuring and write-off. No distributed consensus or off-host
disaster recovery is claimed.

### Validation status after this follow-up

The repository workflow is configured to run all `prototype/test_*.py` tests,
including the new store and pipeline tests. At the time this note was updated,
the connector had not returned a workflow run or combined status for the new
HEAD; no test pass is claimed here. A green run on the exact final HEAD remains
mandatory.
