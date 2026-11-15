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

1. **Opening exports remain incomplete.** The durable register exports deposit
   and reserve opening evidence, but loan and refinancing opening positions in
   the multi-period fixture are caller-supplied synthetic snapshots. Every
   first-active-period opening needs a durable evidence reference and source
   checkpoint. Current reducers store origination principal and outstanding
   principal for post-opening advances, but do not distinguish an independently
   evidenced pre-existing opening principal.
2. **Signed period-close governance exists but is not production-connected.**
   `period_governance.py` verifies a signed global close checkpoint containing
   six independently authorized register attestations, each binding period,
   generation, source identity/cursor/hash, event count/root, explicit
   ACTIVITY/ZERO_ACTIVITY status, opening/closing hashes and reconciliation
   hash. Its tests use in-memory verifier fixtures and permissive authorization
   callbacks for deterministic contract testing. The six authoritative native
   source adapters, real signing-key authority, external rollback-resistant
   sequence store and production attestation publication path are not yet
   connected end-to-end. Absence of events is not evidence of zero activity.
3. **No complete capital account.** Financial net lending is transaction-mapped
   for supported financial instruments only. Capital transfers, non-financial
   investment acquisition/disposal, saving, capital-account counterpart flows
   and any governed statistical discrepancy are not yet integrated into one
   same-cohort six-sector reconciliation.
4. **Instrument lifecycle remains principal-only.** Rate metadata is not an
   interest engine. Interest accrual/payment, fees, arrears, maturity cashflows,
   impairment, default, restructuring, write-off and collateral valuation remain
   unsupported and must continue to fail closed until their contracts exist.
5. **Sector authority is split.** The adapter pins a versioned effective-dated
   sector registry, while write-side financial authorization still uses a
   constructor-supplied static sector map. Governance and sealed-period
   reclassification/reprojection rules remain necessary.
6. **Projection normalization remains incomplete.** The SQLite store persists a
   canonical immutable projection snapshot and checkpoint atomically, but does
   not yet expose independently queryable relational rows for each source event,
   movement, position and sector aggregate. Existing rollback failpoints do not
   prove process-kill recovery at every filesystem boundary.

## Required next implementation slice

Implement evidence-backed opening records for pre-existing loan and central-bank
refinancing principal, keeping them distinct from post-opening origination and
advance events. Each opening record must bind the instrument/facility identity,
holder and issuer, currency, exact principal, first active period, source
account reference, evidence reference and authority envelope. It must not
create a deposit or reserve transaction, and it must not be treated as a T
movement. Its opening principal must remain immutable after later repayments;
the live outstanding principal must continue to evolve independently.

The exporter must derive both reciprocal SFC identities from the opening event,
resolve effective-dated sectors and instrument terms, and produce evidence-backed
opening positions for both mirror sides. It must never infer a zero balance,
current outstanding amount, maturity, denomination or rate term. Duplicate
instrument openings, account/facility mismatches, missing evidence, unsupported
periods and incomplete mirror pairs must fail closed.

Add tests for opening -> later origination/repayment -> restart/replay, including
proof that the opening snapshot remains unchanged while outstanding principal
changes. Add negative tests for duplicate opening, wrong account/counterparty,
wrong currency/minor unit, missing evidence, non-initial period and an opening
record that attempts to create deposit/reserve money. Only after the financial
opening exporter is evidence-backed should period-close assembly bind
independently declared domain-register completeness and the capital-account
bridge. Do not fabricate events in physical, capital, labour, product or
legal-rights registers for a bank-only transaction.

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


## CI concurrency correction — 2026-11-15

The latest audit identified why otherwise valid CI runs were repeatedly
cancelled: both workflow files used the same concurrency key for `push` and
`pull_request` events on a branch. The group now includes
`${{ github.event_name }}`, so push and PR validation no longer cancel each
other. Newer runs of the same event type still supersede older runs, as intended.

Both workflows must be observed on the same final source HEAD before claiming
the complete validation gate. A cancelled run is not a test failure, but it is
also not a pass.


## Addendum — native durable projection pipeline (2026-11-15 continuation)

A subsequent source inspection found that the earlier statement “no durable native SFC projection store” is stale. The branch contains:

- `prototype/banking_sfc_projection_store.py`: versioned SQLite schema, immutable snapshot/checkpoint rows, one `BEGIN IMMEDIATE` transaction for snapshot plus checkpoint, idempotent same-cursor replay, stale/gap/version-drift rejection, and deterministic recovery comparison;
- `prototype/banking_sfc_projection_pipeline.py`: `project_and_persist()` and `rebuild_and_verify()`, which verify the financial-register chain, read the authorized aggregate history, rebuild through the native adapter, and append/recover the projection;
- `prototype/test_banking_sfc_projection_store.py` and `prototype/test_banking_sfc_projection_pipeline.py`: store rollback/idempotency/recovery and pipeline contract tests.

The remaining integration gap is narrower than this audit originally stated: the native financial register now has a durable projection/checkpoint path. It is still not a six-register period-close assembler, not a bridge into the legacy generic `SFCProjectionStore`, and not a complete capital-account reconciliation. The pipeline is single-host SQLite; its test failpoints cover rollback after snapshot/checkpoint writes, but do not establish process-kill testing at every filesystem boundary or distributed recovery. The current Prototype workflow run observed for the previous audited HEAD was cancelled; no green result is claimed for the latest changes until CI completes on the exact HEAD.


## Addendum — period/currency financial net-lending conservation (2026-11-15)

The native adapter now enforces a stronger invariant after mapping transaction assets and liabilities: the sum of sector financial net lending must equal zero **separately for every effective period and currency**. This prevents offsetting errors in different periods or currencies from cancelling in a grand total. The six-sector interbank/refinancing regression test now asserts this per-period/per-currency conservation as well as the aggregate fixture result.

This is a financial-instrument mirror invariant only. It does not replace the full SFC capital-account reconciliation, nor does it establish the completeness of non-financial transactions.
