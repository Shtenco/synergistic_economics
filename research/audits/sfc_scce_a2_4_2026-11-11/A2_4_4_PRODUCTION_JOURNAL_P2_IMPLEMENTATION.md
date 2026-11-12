# A2.4.4 — production EntityJournal, GOLD-2A and P2 projection implementation

**Implementation branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Status:** source committed; exact-head execution evidence pending; not production-certified.

## 1. Canonical EntityJournal

`prototype/entity_journal.py` is now the canonical typed journal boundary for
the frozen GOLD-2A event family. It declares exactly these event names:

- `bank_loan_origination`
- `interest_accrual`
- `interest_payment`
- `impairment_allowance_recognition`
- `principal_repayment`
- `creditor_write_off`
- `legal_debt_forgiveness`

Legacy aliases such as `interest_settlement`, `creditor_writeoff` and
`legal_forgiveness` are rejected. Each event must carry its canonical
component and legal-effect value. The validator checks period-aware entity and
sector identity, full holder/issuer/instrument identity, event-specific account
composition and sides, exact Decimal balance, and bilateral claim movement.
Write-off and forgiveness metadata are distinct. Forgiveness requires typed
legal evidence with authority, effective time, scope, parties and evidence ref.

The frozen GOLD-2A JSON corpus remains unchanged. Its forgiveness event does
not itself contain legal evidence; the adapter integration fixture supplies a
separate synthetic evidence object. Before live use, the source legal evidence
must be supplied by the originating legal workflow, not copied from this test.

## 2. Lossless adapter

`prototype/financial_journal_adapter.py` accepts only the production
`EntityJournal`, `JournalEvent` and `JournalLine` types. Duck-typed
validators and raw dictionaries cannot enter this boundary. It persists
component, legal effect, write-off delta, forgiven principal, legal evidence,
all declared entity/sector/counterparty/issuer/instrument dimensions and exact
Decimal strings. Missing optional dimensions remain absent; explicitly empty
strings are rejected rather than silently discarded.

## 3. Separate instrument and control positions

The P1 instrument opening snapshot remains the immutable ten-field
`SFCIdentity` register. Allowance and written-off legal-claim memorandum are
not financial instruments. `activate_control_openings()` therefore seals a
separate, independently hashed control-opening snapshot before the first
financial event is appended.

The GOLD-2A projection maps the recognized holder asset side once per
instrument identity. The matching issuer liability is validated by the
journal and represented as the other side of the same claim, avoiding
double-counting the same instrument as two positions. Allowance and
write-off memorandum have their own control-position table and do not acquire
synthetic instrument IDs.

## 4. P2 atomic append

`prototype/sfc_projection_store.py` implements
`append_projected_group()`. Under one SQLite `BEGIN IMMEDIATE` transaction
it commits:

1. schema-v4 event-group envelope, commit sequence and predecessor hash;
2. ordered event envelopes and normalized journal postings;
3. instrument T/V/O deltas and closing positions;
4. separate allowance and write-off memorandum T/V/O deltas and positions;
5. explicit per-event `mapped` / `no_stock_effect` coverage;
6. transaction-only sector asset/liability flows and net lending;
7. per-event checkpoints, per-group checkpoint and applied-through cursor.

The legacy `append_group()` remains blocked after P1 activation. There is no
fallback write path around the projection-aware append. Effective accounting
period remains separate from database commit sequence. Periods are carried
forward automatically; a backdated event is rejected pending an explicit
period-reopen/rebuild policy.

The mapper is versioned as `gold2a-entity-journal-mapper@1`. GOLD-2A
allowance and memorandum controls are separate from the instrument projection.
The T/V/O sector net-lending bridge excludes V and O and must sum to zero by
period.

## 5. Recovery and adversarial controls

`verify_projection_replay()` is read-only. It verifies the v4 group chain,
event/posting mirrors, both opening snapshots, event semantics, per-event
coverage, re-derives mapper deltas from immutable event envelopes, replays
instrument and control positions from explicit openings, checks event and
group checkpoints, rebuilds transaction-only sector flows and compares the
materialized positions and cursor.

The dedicated controls are:

- `audit_financial_journal_adapter.py` — seven canonical events, aliases,
  typed evidence, metadata preservation, idempotency and rollback;
- `audit_sfc_projection_store.py` — period carry-forward, final GOLD-2A
  balances, per-event coverage, cursor, restart idempotency, backdated-event
  rejection, injected transactional failure and projection tamper detection.

## 6. Unified cross-register fixture

`audit_unified_cross_register.py` composes the live seven-cell SCCE physical
engine with the cohort-to-service bridge, B3 physical-flow endpoints, typed
product valuation, labour/consent controls and the GOLD-2A P2 financial
projection. A common scenario provenance ID is carried through the register
records and financial causation ID. Physical tonnes and financial currency
remain separate dimensions.

This is a synthetic integration fixture, not a unified production runtime.
The physical, capital, labour, product and financial stores do not yet share
one cross-register transaction coordinator. The A2.4.7 Gate 2 runtime closure
therefore remains OPEN even if this fixture passes.

## 7. Remaining production gates

- Execute all controls on the exact current HEAD and inspect full logs.
- Persist authoritative entity/sector membership and legal evidence provenance.
- Integrate physical, capital, product, labour and rights events into a durable
  cross-register event envelope and transaction/recovery protocol.
- Add signed external checkpoints, backup/restore and operational key/access
  controls. The local SHA-256 chain is tamper-evident, not an external trust
  anchor.
- Complete multi-writer, SQLite-version/WAL, concurrency and crash-boundary
  tests before enabling live multi-process writes.
- Define correction/restatement and closed-period reopening governance.
- Keep P5 sidecar recovery separate and idempotent.

No empirical synergy claim, legal enforceability opinion, distributed
exactly-once guarantee or production readiness follows from this implementation.
