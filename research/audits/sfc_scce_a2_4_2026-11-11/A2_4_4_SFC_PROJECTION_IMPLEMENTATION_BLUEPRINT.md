# A2.4.4 — SFC projection implementation blueprint and source audit

**Date:** 11 November 2026  
**Branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Status:** source-level implementation blueprint; no projection runtime implementation or execution PASS is claimed.  
**Purpose:** turn the existing SFC projection protocol into a concrete, reviewable database/API contract before changing the schema-v4 event store.

## 1. Exact source boundary observed

The current source was inspected at branch HEAD `c026363aac6eeec3cc1254f5ba3c37435dc18ac6`.

### 1.1 Durable store

`prototype/financial_event_store.py` is schema v4. Its immutable group envelope currently contains:

- `group_id`;
- `causation_id`;
- ordered `events`.

The store hashes and chains that envelope, persists normalized event and journal-posting mirrors, and checks those mirrors before append, ordered replay and point reads. The write transaction currently covers the group, events, postings and group-chain metadata only.

There are no SFC opening, delta, materialized-position, coverage or projection-cursor tables. No SFC projection data is currently bound into the group payload hash. This is a real boundary, not merely missing reporting.

### 1.2 Validated adapter

`prototype/financial_journal_adapter.py` calls `EntityJournal.post(event)`, serializes the validated event and its postings, then calls `FinancialEventStore.append_group()`. It has no typed projection-mapper argument and no projection coverage object. Its in-memory rollback is useful but does not make a later SFC update atomic with the durable append.

### 1.3 Independent arithmetic fixture

`audit_instrument_stock_flow.py` checks a synthetic six-sector position set, stock-flow equations, holder/issuer mirror groups and transaction-only financial net lending. It does not replay event IDs from the durable store, and its positions are not materialized by `append_group()`.

**Conclusion:** the existing pieces are individually useful, but they are not yet one event-to-position pipeline. It would be incorrect to describe the current event store plus arithmetic fixture as an implemented SFC ledger.

## 2. Critical contract refinement: coverage must be per event

A group-level empty delta list is not enough to prove that every event was deliberately considered. A mixed group may contain:
- one event that changes a financial instrument stock;
- one event that is income-only or otherwise has no direct instrument-stock effect.

If the mapper simply omits the second event, the store cannot distinguish an intentional no-stock-effect decision from an unprocessed event.

Therefore the canonical projection object should contain an explicit result for **every event in the group**:

```python
projection = {
    "mapping_version": "mapper-id@version",
    "events": [
        {
            "event_id": "event-1",
            "disposition": "mapped",
            "deltas": [ ... ],
        },
        {
            "event_id": "event-2",
            "disposition": "no_stock_effect",
            "deltas": [],
        },
    ],
}
```

Rules:

1. The event-result list must cover the exact event-ID set in the group, once each; no missing, duplicate or unknown event IDs.
2. `mapped` requires one or more deltas. `no_stock_effect` requires an explicitly empty delta list.
3. A group with no instrument-stock effects still carries a projection object and explicit `no_stock_effect` results for every event.
4. Missing `projection` after activation is an error. It is not interpreted as an empty list.
5. The entire canonical projection object is included in the immutable group envelope and its hash. A retry with the same group ID but changed mapping version, disposition, identity, component, amount or delta order is a content conflict.
6. Mapping is performed upstream by a versioned, validated mapper. The projection kernel validates its output; it never infers T/V/O from debit/credit signs, account names or event-type substrings.

This refinement closes a silent-omission path while retaining an explicit representation for non-stock events.

## 3. Typed delta contract

Every delta has:

- `event_id` — must reference an event in this exact group;
- `delta_index` — stable zero-based order within that event's result;
- `effective_period` — exactly equal to the referenced event period;
- full instrument identity;
- `component` — exactly one of `T`, `V`, `O`;
- signed finite decimal-string `amount`;
- `opening_balance` — the explicit frozen opening for this identity and period.

The full identity is:

`(instrument_id, instrument_class, holder_entity_id, holder_sector, issuer_entity_id, issuer_sector, currency, maturity, denomination, valuation_basis)`.

Period is stored alongside the identity as the period key. The issuer-side register is a separate data source/table; the holder projection must not manufacture its own purportedly independent issuer evidence.

### Decimal canonical form

- Input must be a string, never a float or integer JSON number.
- Parse with `Decimal`; reject NaN and infinities.
- Serialize in fixed-point notation, without exponent notation.
- Normalize equivalent values before hashing (e.g. `"1.00"` and `"1"` must not create two economic encodings).
- Reject signed negative zero or canonicalize it to `"0"` consistently.
- Precision, quantization and rounding mode must be explicit at the instrument/valuation boundary; no implicit float conversion is permitted.

The delta amount is signed, unlike journal posting amounts, which are currently strictly positive and carry a separate D/C side. Reusing the posting validator for SFC deltas would be a category error.

## 4. Proposed schema boundary

The following is a logical schema contract, not a claim that these tables exist yet.

### 4.1 Activation and opening state

`sfc_projection_meta` — singleton:
- projection schema version;
- state: `uninitialized` or `active`;
- canonical opening-snapshot hash;
- mapper contract/version;
- activation timestamp and operator/evidence reference.

`sfc_openings` — one explicit row per identity and period:
- all identity dimensions;
- period;
- canonical signed opening amount (negative balances are governed by instrument contract policy);
- source/evidence reference;
- unique full identity + period key.

Activation is opt-in and, in the first implementation, must happen on an empty event store before the first group is appended. Do not silently activate over existing groups. Any populated-history activation requires a separately designed, operator-attested rebuild with explicit opening evidence and per-event checkpoints.

An explicit zero opening is a real row with amount `"0"`. Absence of a row is not zero.

### 4.2 Immutable event-linked projection

`sfc_projection_deltas`:
- `group_id`, `commit_sequence`, `event_id`, `delta_index`;
- effective period and all identity dimensions;
- T/V/O component;
- signed canonical amount;
- frozen opening balance;
- canonical delta payload/hash.

Unique key: `(event_id, delta_index)`. Foreign keys bind group and event to the already durable log. The canonical group envelope remains the source of immutable economics; normalized delta rows are verified mirrors, just as event and posting rows are today.

### 4.3 Materialized holder positions

`sfc_holder_positions`:
- full identity + period;
- opening;
- cumulative T, V and O;
- closing;
- last contributing commit sequence.

Invariant:

`closing = opening + T + V + O`.

The row is a materialized view, not the authority. Integrity checking must replay immutable deltas from explicit openings and compare the complete materialized row.

### 4.4 Coverage and cursor

`sfc_projection_coverage`:
- group ID;
- commit sequence;
- projection payload hash;
- event-result count;
- delta count, including zero;
- explicit completion marker.

`sfc_projection_cursor`:
- singleton cursor;
- applied-through commit sequence;
- projection version/hash.

The cursor means a **contiguous fully projected prefix**. For a new group with sequence N, coverage is inserted and cursor advances from N−1 to N in the same transaction. A missing group or coverage marker blocks advancement. An explicit zero-delta group still receives coverage and advances the cursor.

Do not maintain a cursor that merely records the largest sequence observed; that would hide holes.

## 5. Atomic append protocol

The first implementation should keep the event log and projection in the same SQLite database and one transaction:

1. Validate the journal events through the canonical journal validator.
2. Validate the mapper result against the exact event-ID set and full typed delta contract.
3. Canonicalize the complete event + projection envelope before writing.
4. Start `BEGIN IMMEDIATE`.
5. Verify the existing group hash chain, normalized event/posting mirrors, projection-delta mirrors, coverage continuity and cursor.
6. Resolve group-ID idempotency against the complete envelope hash. Identical replay returns the original sequence and has no second effect; changed projection economics conflict.
7. Verify every delta's opening row exists and its frozen opening equals the stored opening for that identity/period.
8. Validate event-period equality, identity completeness, decimal canonicality, duplicate delta keys and component vocabulary.
9. Apply deltas to holder positions using Decimal semantics; reject forbidden negative gross closing positions.
10. Validate period continuity. A period's opening must equal the previous period's closing for the same identity. New identities require explicit openings.
11. Insert immutable group/event/posting/delta rows, materialized position rows and one coverage row.
12. Advance the cursor by exactly one contiguous sequence.
13. Commit once.

Any exception at any step rolls back all of these: group, events, postings, deltas, materialized positions, coverage and cursor.

The group chain must bind the projection payload by hashing the complete envelope. Do not append projection data to a side table after the existing event commit.

## 6. Period and backdating policy

Commit sequence and effective period remain separate:

- commit sequence = durable append order;
- effective period = accounting/economic period;
- event index = order inside a transaction group.

A newly appended event for a closed earlier period cannot silently rewrite the old projection prefix. The initial policy should reject backdated deltas that would invalidate an already frozen later-period opening. A future period-reopen/rebuild operation must be explicit, authorized, checkpointed and auditable; it is not an ordinary append.

For each identity:
- all deltas for one period aggregate against one frozen opening;
- next-period opening equals prior-period closing;
- new instrument/holder/issuer/currency/maturity/valuation identity requires its own explicit opening;
- a zero balance must be explicitly represented when it is part of the opening snapshot.

Negative positions are not universally forbidden in every financial contract. The rule must be contract-specific: prohibit negative gross positions only where the instrument's legal/operational contract disallows overdrafts or short positions. The synthetic SFC fixture may use a stricter non-negative rule, but the general engine must not universalize that assumption.

## 7. Independent issuer-side register

Do not create an issuer liability by summing holder assets and call that an independent reconciliation. That is a derived mirror of the same source.

Acceptance requires an issuer-side register with separately sourced evidence and its own opening, T, V, O and closing. Reconciliation then compares holder-side and issuer-side positions by the full claim identity, component by component. Sector aggregates are derived only after entity-level claim matching. A mismatch must fail the gate, not be plugged into an unexplained residual.

The first SQLite projection increment may deliberately stop before this independent register, but its status must remain OPEN until the independent side is implemented and tested.

## 8. Required failure-injection points

The integration test must inject failure after each stage below and then reopen the database to prove that the entire group transaction is absent and the cursor/positions are unchanged:

1. after group envelope insert;
2. after event insert;
3. after journal-line insert;
4. after projection-delta insert;
5. after first materialized-position update;
6. after coverage insert;
7. immediately before cursor update;
8. immediately after cursor update but before COMMIT.

Also test the uncertain-acknowledgement case: commit succeeds, caller loses acknowledgement, identical retry returns the existing group without applying T/V/O twice.

Concurrency tests must race distinct groups affecting the same holder/instrument key, not merely different keys. The writer lock must serialize both commit sequence and position updates. A second reader must never observe a new group without its matching position/coverage/cursor state.

## 9. Adversarial matrix extension

In addition to the 18 cases in `A2_4_4_SFC_PROJECTION_PROTOCOL_SPEC.md`, require:

19. Mixed group with one mapped event and one explicit no-stock-effect event.
20. Missing event disposition rejected even when the group contains other valid deltas.
21. Duplicate event disposition rejected.
22. Unknown event ID in a projection result rejected.
23. `mapped` with empty deltas rejected.
24. `no_stock_effect` with a non-empty delta list rejected.
25. Duplicate `(event_id, delta_index)` rejected.
26. Same group ID with changed mapper version rejected.
27. Same group ID with changed delta order rejected.
28. Float, exponent-noncanonical, NaN, infinity and negative-zero encodings handled by explicit canonical policy.
29. Delta effective period differing from its event rejected.
30. Frozen opening mismatch rejected.
31. A missing explicit zero opening rejected (not silently treated as zero).
32. Concurrent groups touching one position produce one serialized final state.
33. Read snapshot cannot observe a group without its corresponding projection state.
34. Coverage gap blocks cursor advancement.
35. Cursor tampering or cursor ahead of coverage is detected by replay.
36. Final closing equality with an altered intermediate event checkpoint is rejected.
37. Backdated delta against an already frozen later opening is rejected.
38. Contract-forbidden negative gross position rejected while permitted negative position types follow explicit contract rules.

## 10. Worked Decimal control — stock change is not financial NL

A three-period holder asset example:

| Period | Opening | T | V | O | Closing |
|---:|---:|---:|---:|---:|---:|
| 1 | 100 | +10 | +5 | −2 | 113 |
| 2 | 113 | −8 | −3 | +1 | 103 |
| 3 | 103 | 0 | +7 | 0 | 110 |

Checks:
- each period satisfies closing = opening + T + V + O;
- period 2 opening equals period 1 closing;
- period 3 opening equals period 2 closing;
- cumulative transaction-only financial NL contribution for the holder asset is +2;
- total stock change is +10;
- the +8 difference is cumulative revaluation/other-volume change and must not be counted as transaction-based financial NL;
- the issuer's matching liability contributes −2 to sector financial NL, so the holder/issuer pair sums to zero.

This is a synthetic arithmetic control, not an empirical observation or a claim that the current repository runtime produced these values.

## 11. Gate and implementation sequencing

**Stage P0 — domain kernel:** typed identity/delta validation, canonical Decimal rules, explicit per-event dispositions, deterministic pure replay and per-event checkpoints. No database schema change.

**Stage P1 — database activation:** explicit opening snapshot and opt-in activation on empty stores; schema migration that leaves existing stores unprojected.

**Stage P2 — atomic append:** include projection in canonical group envelope and write deltas, materialized positions, coverage and cursor in the same transaction.

**Stage P3 — recovery:** replay-from-opening integrity checker, crash injection at all transaction boundaries, cursor/coverage tamper tests, same-key concurrency and snapshot isolation.

**Stage P4 — independent issuer register:** separate evidence source, component-level mirror and sector reconciliation.

**Stage P5 — runtime integration:** only after the above gates, route the validated journal adapter through a non-bypassable mapper/append path. Keep the existing economic engine and SFC ledger boundaries explicit until cross-register tests pass.

Current source status remains: durable event append and local chain/mirror checks exist; SFC projection, opening activation, projection deltas, materialized positions, coverage, cursor, replay checker and independent issuer-side register are **not implemented**. A2.4.4 remains OPEN; A2.4.8 remains BLOCKED.
