# A2.4.4 — SFC projection protocol specification

**Status:** design contract; implementation and execution pending.  
**Scope:** single-host SQLite prototype, explicit holder-position projection.  
**Does not establish:** production readiness, distributed exactly-once delivery, independent issuer reconciliation, or empirical SFC validity.

## 1. Journal entries are not stock-flow classifications

A balanced debit/credit journal is necessary but insufficient to infer a
financial-instrument stock change. Debit/credit normal sides depend on account
taxonomy; identical journal-side signs can have different meanings for
assets, liabilities, income, expense, valuation and clearing accounts.

The projection layer MUST NOT infer T/V/O changes by summing debit and credit
signs or guessing from account-name substrings. A validated upstream mapper
must explicitly classify each stock effect as T (transaction), V
(revaluation), or O (other change in volume). Income/expense postings and
non-financial events may have no direct instrument-stock effect. Such a group
must explicitly carry an empty delta list; missing projection data is not
equivalent to an empty list.

## 2. Full instrument identity

Every projected holder position is keyed by effective period, instrument ID,
instrument class, holder entity and sector, issuer entity and sector,
currency, maturity, denomination, and valuation basis. Aggregation must not
collapse distinct instruments, currencies, maturities, holders or issuers.

## 3. Explicit opening snapshot and delta contract

Projection activation is opt-in and occurs before the first event group. The
opening snapshot enumerates positions in scope and provides non-negative
finite decimal-string opening balances. Zero is never inferred from a missing
record.

Each projection delta contains event ID, matching effective period, the full
identity above, component T/V/O, signed finite decimal-string amount, and the
frozen opening balance for that identity and period. The projection payload
must be included in the canonical group hash. Same group ID with changed
projection economics is a content conflict.

Existing populated event stores cannot be retroactively declared projected.
A historical projection requires a separately designed, operator-attested
backfill/rebuild with explicit openings, per-event checkpoints and
independent reconciliation.

## 4. Atomic transaction boundary

After projection activation every committed group must declare projection
coverage. The following are one indivisible SQLite transaction:

1. immutable event-group envelope and commit sequence;
2. immutable event rows and journal postings;
3. immutable event-linked SFC T/V/O deltas;
4. materialized holder-position updates;
5. a coverage row for the group, including explicit zero-delta coverage;
6. applied-through cursor advancement.

The cursor denotes a contiguous prefix of fully projected groups. It may not
skip an unprojected group. A failure at any stage rolls back all six elements.
An acknowledgement lost after commit is handled by identical idempotent
retry; the retry must not apply a second projection effect.

## 5. Stock-flow and period invariants

For each holder/instrument/period identity:

    closing = opening + T + V + O

- Opening and closing gross positions are non-negative where the instrument
  contract prohibits overdrafts or negative positions.
- Amounts use Decimal semantics and canonical decimal strings, never floats.
- Next-period opening equals prior-period closing.
- A backdated delta that invalidates a later frozen opening is rejected and
  routed through explicit period-reopen/rebuild policy.
- A new instrument or newly observed identity needs an explicit opening
  balance; a missing position is not assumed to mean zero.
- Financial net lending uses T only; V and O do not create financial NL.

## 6. Independent issuer-side reconciliation

An issuer-liability aggregate computed by summing holder positions is a useful
derived view, but it is not an independent issuer-side register. It cannot
prove the holder/issuer mirror invariant because both sides originate from
the same records.

Acceptance requires a separately sourced issuer-liability projection or
independent register keyed by the same instrument identity, with
component-by-component comparison of opening, T, V, O and closing. Sector
totals must also be independently reconciled. Circular reconciliation is
prohibited.

## 7. Recovery and integrity

The integrity checker must replay immutable projection deltas from explicit
openings and compare every materialized holder-position row. It must verify
complete group coverage, contiguous coverage sequences, cursor position,
event-to-delta identity and period linkage, T/V/O totals, closing stock-flow
identity, period continuity, non-negative gross positions, and canonical
hash binding of events, postings and projection payloads.

A rebuild must create per-event checkpoints, not merely compare final totals.
A final-state-preserving intermediate corruption must fail.

## 8. Adversarial test matrix

1. Explicit non-zero opening stocks.
2. Explicit zero opening, never inferred.
3. T, V and O independently update only their own components.
4. Financial NL excludes V and O.
5. Missing projection field rejected after activation.
6. Explicit empty-delta group advances coverage without changing positions.
7. Projection payload tampering under same group ID rejected.
8. Wrong event ID or mismatched effective period rejected.
9. Changed opening balance for an existing period rejected.
10. Next-period opening mismatch rejected.
11. Negative gross closing stock rejected.
12. Failure after position update but before cursor update rolls back group,
    events, postings, deltas, position and cursor.
13. Commit-before-ack crash plus retry yields one effect.
14. Concurrent projected writers serialize sequence, state and cursor.
15. Tampered materialized T/V/O/closing state detected by independent replay.
16. Missing, duplicate or gapped coverage marker detected.
17. Multi-period NL requires explicit period selection.
18. Independently supplied issuer-side mirror mismatch rejected.

## 9. Migration and operational limits

Schema-v3 event stores may add projection tables with projection marked
uninitialized. Existing groups remain unprojected. Projection cannot be
activated over populated history without an explicit backfill/rebuild.
Never synthesize commit order or opening stocks during migration.

SQLite WAL remains a single-host facility. WAL on network filesystems and
unverified SQLite runtime versions are outside production acceptance.
Backup/restore, busy handling, filesystem durability, retention, access
control, encryption, key management and disaster recovery require separate
evidence.

## 10. Gate criteria

- Design specification: recorded.
- Schema-v4 projection implementation: OPEN.
- Explicit-opening migration/backfill: OPEN.
- Atomic projection/cursor implementation: OPEN.
- Independent issuer-side register and reconciliation: OPEN.
- Adversarial projection tests: OPEN.
- Exact-head CI execution: OPEN.
- Production runtime integration: OPEN.
- A2.4.4: OPEN.
- A2.4.8: BLOCKED pending upstream gates.
