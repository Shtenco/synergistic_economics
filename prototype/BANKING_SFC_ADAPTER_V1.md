# Native banking SFC adapter v1 — implementation contract

Status: partially implemented native financial projection contract. The financial adapter, historical financial opening exporters, SQLite snapshot/checkpoint persistence and recovery path exist on this branch. This document records the remaining production and cross-register requirements; it does not claim six-sector closure.

## 1. Purpose and boundary

Connect the append-only `OperatingFinancialRegister` history to a native multi-period SFC projection without routing bank-only events through the wage-oriented six-participant coordinator and without manufacturing physical, labour, product, capital or legal events.

The source of truth remains the immutable financial register. This adapter is a deterministic projection, not a second ledger and not an authority to create, amend or settle financial events.

The existing `SFCProjectionStore` is currently coupled to the `FinancialEventStore` / `EntityJournal` event schema and its `gold2a-entity-journal-mapper@1`. Do not pass financial-register envelopes to that mapper or weaken its schema checks. Reuse the pure T/V/O projection invariants where possible; provide a native financial projection adapter/store boundary with its own mapper version and recovery checks.

## 2. Source event contract

Read the authorized `OperatingFinancialRegister.history("operating-financial", principal_id=...)` stream. Each history row carries the immutable register event identity and decoded normalized envelope. The adapter must retain, at minimum:

- source `event_id`, `idempotency_key`, `common_event_id`, `aggregate_version`;
- `event_type`, `effective_at`, `recorded_at`, `authority_ref`;
- normalized envelope payload and canonical `stock_flow_movements`;
- the source payload digest / chain position where exposed by the register.

Never rebuild a source event ID from a movement ID. Movement IDs are deterministic children of the source event and must retain a direct source-event reference.

Supported financial event families in the current register:

- `bank.loan_originated`, `bank.loan_principal_repaid`;
- `bank.interbank_payment_settled`;
- `central_bank.refinancing_advanced`, `central_bank.refinancing_principal_repaid`;
- `wage.event_group_committed` (including its native wage subevents);
- `deposit.account_opened`, `bank.reserve_account_opened` as opening-stock evidence, not transaction movements.

Unknown event types, absent period indices, missing canonical movements, or unsupported movement classes fail closed. Do not infer a missing movement as zero.

## 3. Identity and mirror semantics

The native register's `stock_flow_movements` use `PositionIdentity` fields and a `mirror_side` marker. For this contract:

- `mirror_side=asset_holder` means the position owner carries an asset;
- `mirror_side=liability_issuer` means the position owner carries a liability;
- `identity.holder_id` is the accounting position owner on either side; `identity.issuer_id` is its counterparty;
- the sector of the position owner is resolved from the explicit, versioned institutional-sector registry;
- the counterparty sector is also resolved and retained for bilateral validation, but must not be used to reclassify the position owner's asset/liability side.

Do not infer asset/liability semantics from the words `holder_id` or `issuer_id` alone. The existing financial movement specs intentionally represent the asset and liability sides as separate position identities.

For every mirror group, require exactly two distinct sides, one `asset_holder` and one `liability_issuer`, with matching register, instrument, currency, valuation basis, period and event provenance. Apply the declared mirror policy (`equal` or `opposite`) exactly. Reject duplicate sides, extra sides, mismatched amounts, missing counterparties and sector-map drift.

## 4. Sector flow accounting

Compute transaction assets and liabilities separately, grouped by the sector of the accounting position owner:

`financial_NL[sector, period] = transaction_assets[sector, period] - transaction_liabilities[sector, period]`

Use `mirror_side` to select the relevant accumulator. Do not count both sides of a mirror as assets, and do not count a liability-side position as an asset merely because it has a position identity.

The six-sector vocabulary is fixed and shared with the normative SFC documents:

- `H`: households;
- `NFC`: non-financial corporations;
- `CB`: commercial banks;
- `CBank`: central bank;
- `GOV`: government;
- `ROW`: rest of world.

For each period and currency/valuation basis, the sum of sector financial net lending must be zero for the closed domestic-plus-rest-of-world financial instrument universe, subject only to explicitly modelled statistical discrepancy (which must never be inserted automatically). Report missing sectors and unclassified counterparties; do not manufacture balancing entries.

## 5. Opening stocks and period replay

Historical loan/refinancing and deposit/reserve opening exporters now reconstruct period-boundary positions from verified native register history. Loan/refinancing exporters replay originations and prior principal repayments; deposit/reserve exporters replay all prior native transaction movements touching those shared accounts. A complete SFC snapshot must still compose these exports with wage claims/payables and every other supported financial instrument into registry-resolved identities:

- customer deposit asset and issuing-bank deposit liability;
- bank reserve asset and central-bank reserve liability;
- bank loan asset and borrower loan liability;
- central-bank refinancing claim and commercial-bank refinancing liability;
- wage receivable/payable and any other supported financial instruments.

For a newly originated instrument, a zero opening may be used only when the adapter records an explicit opening row with a source event/evidence reference proving that the instrument did not exist before its first origination. Never rely on a missing-row-to-zero default.

For adjacent periods enforce:

`closing(p) = opening(p) + T(p) + V(p) + O(p)`
and
`opening(p+1) = closing(p)`.

Only explicit revaluation events may enter V; only explicit other-volume-change events (write-off, reclassification, instrument extinction not represented as a transaction, etc.) may enter O. Current loan principal/refinancing lifecycle events are T. Do not classify interest, impairment, collateral valuation or default effects until their own event contracts and accounting rules exist.

The adapter must derive the full position identity from the immutable event and a versioned sector/account registry. It must preserve currency and valuation basis and must not net positions across currencies.

## 6. Financial-only events and cross-register closure

A bank-only transaction is natively committed in the financial register. It is not a six-register common event and must not be wrapped in fabricated participant envelopes.

Introduce a period assembler that consumes independently committed native event batches from each domain register. The existing six-participant coordinator remains appropriate only for transactions that genuinely require its atomic visibility barrier. The assembler must distinguish:
- a native single-register event;
- a genuine cross-register coordinated event;
- an explicit register-period declaration with no activity.

A register's absence of events is not automatically proof of zero activity. Period completeness must be declared and evidenced by the domain register or close protocol.

## 7. Atomicity, idempotency and recovery

The implemented financial-only SQLite projection store atomically persists a deterministic projection snapshot and source checkpoint, pins registry/opening digests, and binds both snapshot and checkpoint rows to the verified source-chain tail hash. The durable register persists a per-database instance ID and exposes it with the global event count and verified tail hash. The pipeline derives its source namespace from that identity and principal scope, rejects caller-ID substitution, checks that the source did not change during the history read, and verifies that the previously sealed cursor remains an ancestor of the current chain before advancing or recovering. The new `build_opening_snapshots_from_register()` composes deposit, reserve, loan, central-bank refinancing, and bilateral wage receivable/payable positions from five native opening exporters, resolves every position against the pinned instrument and effective-dated sector registries, verifies bilateral mirrors, and embeds the exact source register ID, global sequence and chain hash in the snapshot digest. Wage openings are included only when their instrument terms and effective-dated sector memberships resolve in the supplied registries. The production projection pipeline now rejects snapshots not pinned to the exact same source checkpoint as the history being projected. This is a single-host persistence boundary, not a distributed close protocol. Remaining requirements for the broader system are:
- canonical movement coverage;
- projected positions and T/V/O totals;
- sector transaction asset/liability totals and financial net lending;
- applied-through source sequence and mapper version.

Use source event identity plus movement identity as unique keys. Replaying the same source history must be idempotent. A changed mapper version requires an explicit rebuild/reprojection path; never silently reinterpret already projected history.

The current financial-only recovery path re-reads and verifies source history and the source-chain tail, deterministically rebuilds the projection, and compares the persisted checkpoint, registry digests and opening-snapshot digest. The broader exit criteria below still require signed period completeness and native non-financial registers. Any mismatch must fail closed without partially advancing the projection cursor.

SQLite atomicity is a single-host persistence guarantee only; do not describe it as distributed consensus or production-grade multi-node durability.

## 8. Required adversarial tests

1. Every supported event type maps to the expected positions and exact sector asset/liability deltas.
2. Loan origination creates bank loan asset + borrower liability and borrower deposit asset + bank deposit liability; principal repayment reverses all four.
3. Interbank settlement reallocates customer deposits and bank reserves; aggregate system reserves do not change.
4. Central-bank refinancing increases bank reserves and central-bank reserve liabilities together with the refinancing claim/liability; repayment reverses all four positions.
5. Mirror pair missing, duplicate, wrong side, wrong currency, wrong period, wrong instrument, wrong amount or wrong counterparty is rejected.
6. Sector-map changes between projection and recovery are detected by a pinned registry version/digest.
7. Duplicate source event, duplicate movement, replayed batch, stale cursor and concurrent append do not create duplicate positions or partial writes.
8. Missing opening, implicit-zero opening, period gap, discontinuous opening, currency netting and unexplained balance adjustment all fail.
9. V/O cannot be supplied for an event family whose contract only permits T.
10. Crash injection before and after each transactional write proves atomic rollback or deterministic recovery.
11. Financial-only events project without fake events in other registers.
12. Period assembler refuses to close while any required register has not declared its period complete.
13. All six sectors' net lending sum to zero by period and currency, with no hidden balancing posting.
14. Projection output is deterministic across restart and independent of input row ordering where source sequence is unchanged.

## 9. Exit criteria

This work is complete only when the native adapter, projection persistence, recovery, period assembler and adversarial tests are implemented; the full repository suite is green on the exact resulting HEAD; and a multi-period fixture demonstrates all six sectors, all supported bank instruments, sector financial net lending, capital-account reconciliation and the absence of synthetic balancing events.

A green unit suite for the financial register alone is not evidence of six-sector macroeconomic closure or elimination of an economy-wide liquidity shortage.
