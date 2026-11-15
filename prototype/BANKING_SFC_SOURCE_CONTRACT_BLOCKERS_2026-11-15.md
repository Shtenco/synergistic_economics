# Banking-to-SFC integration: implementation status and remaining blockers

Audit date: 2026-11-15  
Scope: `research/bank-deposit-credit-audit-fix-20261115`, PR #13.  
Status: **partial native adapter implemented; full six-sector SFC and capital-account closure not complete.**

## Executive finding

The earlier source-contract gate has progressed: version-pinned instrument terms, effective-dated sector membership, explicit opening-stock snapshots and a separate native `operating_financial_sfc_adapter.py` now exist. The adapter consumes immutable operating-financial register history, checks the register hash chain when invoked through `from_register()`, validates exact event/movement coverage and reciprocal financial mirror pairs, replays explicit T/V/O positions, and computes transaction-based sector financial net lending.

The current implementation supports wage event groups, bank loan origination/principal repayment, interbank deposit transfers settled through central-bank reserves, and central-bank refinancing advances/repayments. A synthetic six-sector fixture exercises household, NFC, commercial-bank, central-bank, government and ROW membership over two consecutive periods, including interbank reserve redistribution and refinancing repayment.

This is a **working projection slice**, not a complete six-sector SFC. It does not yet have a durable projection store/checkpoint, signed period-close completeness declarations for all six registers, full production-to-financial integration, complete capital-account flows, interest accrual, defaults/impairment, or a reconciled financial/capital account. A six-sector financial net-lending sum of zero in the synthetic fixture is a mapping/reconciliation test, not proof of macroeconomic closure or economic viability.

## Implemented source contracts and adapter

1. `prototype/sfc_source_contracts.py` defines versioned `InstrumentTermsRegistry`, effective-dated `EffectiveDatedSectorRegistry`, explicit `OpeningStockSnapshot` and `OpeningPosition` records. Registry versions and canonical digests can be pinned to a projection.
2. Instrument terms include instrument class, denomination, currency, valuation basis, maturity classification/date, rate type/reference/spread, reset frequency, day-count convention, payment frequency, repayment type and effective periods. Missing or ambiguous terms fail closed.
3. Sector membership resolves holder and issuer entities by movement period; overlapping, missing or unsupported membership fails closed.
4. `prototype/operating_financial_sfc_adapter.py` is a separate native adapter. It does not route operating-financial envelopes through GOLD-2A or `sfc_projection_store.py`.
5. The adapter covers the currently supported opening events (deposit and reserve account openings) and movement events (wage event groups, bank credit, interbank payments, central-bank refinancing). It validates mirror pairs, event-to-movement assignment, source coverage, registry digests and explicit opening rows before replay.
6. `from_register()` verifies the durable financial register hash chain before reading its immutable history. Direct `build()` tests exercise projection mapping independently with synthetic immutable history rows.
7. The projection reports source-event counts, mapped coverage, opening exclusions, position roll-forwards and sector financial net lending by period/sector/currency.

## Remaining blockers

### B1. Instrument lifecycle and interest

**Partially implemented.** Typed and effective-dated instrument terms exist, and principal-only loan/refinancing transactions can be projected. The financial register does not yet accrue or settle interest, fees, penalties, index resets, maturity cashflows, write-offs, impairments or restructurings. The presence of rate metadata in the registry must not be mistaken for an interest engine or maturity ladder.

Next:
- add interest accrual/payment event types and exact mirror movements;
- add maturity, refinancing, early repayment, arrears, default and write-off lifecycle events;
- prove nonnegative gross positions and maturity continuity across multiple periods;
- keep unsupported instrument classes rejected rather than inferring terms.

### B2. Effective-dated institutional sectors

**Implemented at the adapter boundary, not yet authoritative for every source.** The versioned sector registry resolves memberships by period and its digest is pinned to projection inputs. The operating financial register still has a constructor-supplied static sector map for its own write-side authorization checks. A governance/authority process for publishing, sealing and correcting sector registry versions remains to be formalized.

Next:
- bind write-side financial entities to an authoritative registry version;
- reject retroactive membership changes to sealed projection periods unless a versioned, reasoned reprojection is issued;
- test recovery against changed registry digests.

### B3. Opening-stock lifecycle

**Partially implemented.** The snapshot contract requires explicit expected identities and explicit positions, pins both registry versions/digests, and rejects missing or ambiguous openings. The durable register now reconstructs bilateral loan/refinancing principal openings from immutable originations and repayments, and reconstructs deposit/reserve openings by replaying all prior native transaction movements that touch those shared accounts. This includes bank-credit money creation/repayment, wage settlement, interbank deposit/reserve transfers and central-bank refinancing. Openings are period-boundary values: movements in the requested period are excluded, while earlier-period movements are included. The exporter's evidence digest binds the account-opening event and each prior affecting event-chain row.

Account-opening events now carry an explicit first-active period (defaulting to period 1 for backward-compatible callers). An account is omitted from earlier snapshots, its opening balance is included at its first-active period, and prior movements are replayed only from periods at or after that opening period. The exporter verifies the native register chain and envelope digest, but its digest is not a signed completeness attestation or a source-checkpoint binding. Complete OpeningStockSnapshot composition across every financial instrument is still not automatic.

Next:
- preserve the backward-compatible rule that legacy account-opening events without a period are period-1 openings; do not retroactively reinterpret sealed legacy history;
- compose loan, refinancing, deposit, reserve, wage claims/payables and all other supported positions into one complete SFC OpeningStockSnapshot with duplicate/mirror/currency checks and conversion to version-resolved SFCIdentity values;
- bind each snapshot to the exact durable register checkpoint (register identity, sequence and digest) and require signed period-completeness declarations, including explicit zero-activity declarations;
- test restart/recovery using composed snapshots derived from actual durable history.

### B4. Sector-flow mapping and mirror integrity

**Implemented for the supported movement types.** The adapter distinguishes asset-holder and liability-issuer sides, validates reciprocal identities and equal signed amounts, and computes sector financial net lending without a balancing plug. The current test fixture exercises all six sector codes and checks the aggregate transaction sum.

Still required:
- independently validate all sector results against hand-calculated account tables for every supported event type;
- test multiple currencies and valuation bases without cross-currency netting;
- add capital transfers, non-financial transactions and the capital-account counterpart before claiming full sectoral net-lending/capital-account reconciliation;
- treat any non-zero discrepancy as a diagnostic, not a reason to fabricate a plug.

### B5. Period-close completeness and durable projection

**Partially implemented — financial-only snapshot/checkpoint path exists; six-register close does not.** The native financial adapter can replay verified financial-register history, and `banking_sfc_projection_pipeline.py` persists a deterministic SQLite snapshot/checkpoint atomically and rebuilds it for recovery. Store tests cover idempotent replay, changed-content rejection, stale cursors, registry/opening digest drift, injected rollback at both snapshot/checkpoint write boundaries, immutable rows and deterministic recovery comparison. A real durable-register integration test now exercises the financial history → adapter → store → rebuild path.

The cross-register coordinator separately implements a six-participant prepare/commit visibility barrier and an append-only committed event-group stream. It remains a protocol/conformance harness: its source documentation explicitly requires authoritative native-domain adapters before production use. It does not yet provide signed period-close completeness declarations or a capital-account reconciler.

Next:
- require signed period-close declarations for each authoritative source register, including explicit zero-activity declarations;
- include period bounds, source sequence/checkpoint, registry versions/digests, completeness scope and evidence references;
- retain the native financial snapshot/checkpoint as a separate projection until a governed six-register close contract is defined;
- add source-event/movement coverage manifests and versioned reprojection rules;
- never fabricate physical, capital, labour, product or legal-rights participant events for a financial-only transaction.

## Current mandatory test coverage

- versioned instrument terms and effective-dated sector membership;
- rejection of missing/ambiguous instrument terms, sector membership and opening positions;
- reciprocal holder/issuer mirror checks and tamper rejection;
- loan origination and principal repayment roll-forward;
- durable register history verification through the adapter's `from_register()` path;
- interbank settlement movement mapping and reserve/deposit reconciliation in the dedicated register tests;
- central-bank refinancing advance/repayment and reserve/claim reconciliation in the dedicated register tests;
- synthetic six-sector projection with explicit opening rows and two-period reserve/refinancing roll-forward.

The durable-history integration test for interbank and refinancing events through the adapter is present and exercises a real register history across periods 3 and 4. Historical loan/refinancing and deposit/reserve opening exporters are also implemented and covered by dedicated tests. Remaining tests include broader multi-currency sector reporting, signed period-close completeness, normalized projection-row recovery, and process-kill/restart crash testing beyond the current SQLite transaction failpoints.

## Implementation sequence

1. **Done, partial scope:** versioned instrument terms and explicit financial position identity resolution.
2. **Done, partial scope:** effective-dated sector registry with digest pinning at projection.
3. **Partially done:** historical loan/refinancing and deposit/reserve opening exporters exist; composing all exports into a registry-resolved, checkpoint-pinned `OpeningStockSnapshot` with signed completeness remains.
4. **Done, supported events only:** separate native financial SFC adapter and movement mapper.
5. **Done, limited scope:** native financial SQLite projection snapshot/checkpoint with atomic persistence; normalized per-event/per-movement relational coverage tables remain future work.
6. **Partially done:** deterministic mapping/replay, hash-chain verification, real-register persistence/recovery integration and transaction failpoint tests; subprocess kill/restart testing at filesystem boundaries remains.
7. **Not done:** signed period-close assembler for all authoritative registers; do not synthesize six-register events for a financial-only source event.
8. **Not done:** integrated multi-period six-register SFC close, complete capital account and real-economy reconciliation.

## Definition of done

The banking-to-SFC integration is not complete until:
- every supported instrument has explicit typed terms and lifecycle events;
- source and registry versions are pinned and recoverable;
- every source event and movement is covered exactly once;
- every position has evidence-backed openings for each required period;
- roll-forwards close for multiple consecutive periods;
- mirror checks and sector aggregation pass without plugs;
- all required registers declare period completeness, including zero activity;
- durable projection checkpoints recover/replay identically after injected crashes;
- sector financial net lending is reconciled to capital-account net lending only after all relevant non-financial transactions, capital transfers and statistical-discrepancy rules are explicitly represented;
- the complete test suite passes on the exact resulting HEAD.

Even a fully closed SFC accounting model does not by itself prove sufficient liquidity, solvency, productive credit allocation, fairness or economic resilience. Those require separate empirical and scenario-based tests covering production, capacity, prices, income distribution, payment timing, maturities, arrears, defaults, bank capital and reserves.


## Addendum — corrected status after pipeline inspection (2026-11-15)

The earlier “Not implemented” wording for durable financial projection persistence is superseded. The branch already contains a native `banking_sfc_projection_store.py` and `banking_sfc_projection_pipeline.py`. Together they verify the financial register hash chain, project committed operating-financial history through `OperatingFinancialSFCAdapter`, persist a deterministic SQLite snapshot/checkpoint atomically, and independently rebuild/compare it during recovery. Existing tests cover same-cursor idempotency, changed-content rejection, cursor ordering, pinned digest drift, crash failpoints around the SQLite transaction, and recovery comparison.

A real-register integration test has now been added to ensure the durable `OperatingFinancialRegister` (not only a fake source) flows through `project_and_persist()` and `rebuild_and_verify()`. It asserts deterministic source replay and equality of the persisted/recovered projection digest. This test is committed but not yet confirmed by CI.

Still open: automatic composition of all historical opening exports into a registry-resolved, source-checkpoint-pinned SFC snapshot; signed completeness declarations for all required registers; production integration with physical/capital/product/labour/legal-rights domains; a complete capital account and financial-vs-capital net-lending reconciliation; interest/fees/arrears/default/impairment/collateral lifecycle; and exact-HEAD green CI. Do not treat a six-sector financial projection or zero-sum synthetic fixture as proof of full SFC closure or solved liquidity scarcity.

## Addendum — source-history cursor validation hardening (2026-11-15)

The pure `OperatingFinancialSFCAdapter.build()` boundary previously sorted supplied history rows before validating row type and commit cursor. A malformed row could therefore raise an incidental Python exception, and duplicate commit cursors were not rejected explicitly. The adapter now validates each row as a mapping, requires a positive non-boolean integer `commit_sequence`, rejects duplicate sequence values, and only then sorts deterministically. Global sequence gaps remain allowed; this check does not impose false contiguity on a shared register sequence.

Adversarial coverage now includes non-mapping rows, missing/null/zero/string/boolean cursors, duplicate cursors, and out-of-order input with unique cursors. Changes are committed in `90d235e7ad847f9a9a2946eb691a36e57a785f10` and `7e01bfe93d46e444342c6122d5de3134d15a5a88`.

These are source-contract hardening changes, not evidence of full SFC closure. At that point, evidence-backed loan/refinancing opening exporters had not yet been completed; they have since been added, together with historical deposit/reserve reconstruction. Signed per-register period completeness, native non-financial adapters, capital-account reconciliation, lifecycle cashflows and exact-HEAD green CI remain open.

## Addendum — origination-period state metadata (2026-11-15)

The durable financial reducer now retains `origination_period_index` explicitly in both loan and central-bank refinancing facility state, alongside the existing immutable source event history. This value is copied from the validated period field on the origination/advance event; it is not inferred from the latest state or wall-clock timestamps. Regression tests now assert that both a loan's origination period and a refinancing facility's advance period remain unchanged after later principal repayments.

This was a provenance prerequisite before the subsequent history-derived opening exporters were added. The later loan/refinancing exporter implementation is documented below; the remaining gaps are composition into registry-resolved SFC identities, source-checkpoint binding and signed completeness attestation.


## Addendum — history-derived debt opening positions (2026-11-15)

The native financial register now exposes `loan_opening_positions(period_index=...)` and `refinancing_opening_positions(period_index=...)`. Each method first verifies the durable register hash chain, then reconstructs principal balances from committed native history at the requested period boundary. Originations in the requested period produce explicit zero opening rows; originations in earlier periods contribute principal less repayments in strictly earlier periods. Repayments in the requested period do not reduce its opening balance. Instruments originated after the requested period are excluded. Both reciprocal holder/issuer positions are emitted, including zero balances for previously originated and fully repaid facilities.

Each emitted opening evidence reference is a deterministic digest over the contributing immutable event IDs, commit cursors, payload digests, chain hashes and original evidence references. This binds the opening calculation to verified source history; it is not a substitute for external legal evidence or a signed period-completeness attestation.

Regression coverage checks loan openings at origination, immediately before repayment, and after repayment; equivalent refinancing tests cover the advance and repayment boundaries.

**Remaining boundary:** loan/refinancing and deposit/reserve historical opening exporters now exist, including the shared deposit/reserve movements caused by prior loan, wage, interbank and refinancing transactions. They still emit legacy `PositionIdentity` rows rather than one composed, registry-resolved SFC `OpeningStockSnapshot`; they do not yet bind the composed snapshot to the persisted financial-register checkpoint or prove signed period completeness. End-to-end adapter replay from automatically composed snapshots remains open.


## Addendum — period-pinned account openings and exact financial arithmetic (2026-11-15)

Deposit and reserve account-opening events now carry `period_index` (default 1 for backward-compatible legacy callers), and the reducer retains `opening_period_index`. Historical account-opening exports omit accounts before their first-active period, include the immutable opening balance at that boundary, and replay only prior-period movements. Backdated loan, interbank, refinancing and wage-payment movements that precede any affected account's opening period are rejected at the register boundary.

The financial reducer now executes accepted monetary arithmetic under a bounded high-precision Decimal context, rejects source decimals beyond the exact-decimal bounds, and uses exact summation for bank balance snapshots and historical opening reconstruction. A regression test uses a principal larger than 28 significant digits, repays a unit amount, and checks the exact remaining loan, deposit and aggregate bank balances.

These changes improve the financial register's period semantics and arithmetic; they do not yet compose all exported rows into a source-checkpoint-pinned SFC snapshot or establish six-register closure. Exact-HEAD CI must confirm the current implementation.
