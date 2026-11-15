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

**Partially implemented.** The snapshot contract requires explicit expected identities and explicit positions, pins both registry versions/digests, and rejects missing or ambiguous openings. The adapter can replay multi-period balances when a complete opening snapshot is supplied for each period. The durable register exports deposit and reserve opening positions for period 1. It does not yet export a complete set of loan and refinancing opening positions from durable opening events; the multi-period six-sector test currently supplies an explicit synthetic snapshot for those instrument identities.

Next:
- add evidence-backed loan and refinancing opening-position exports;
- support first-active-period openings for newly introduced instruments;
- ensure every snapshot has a source checkpoint and attestation, not merely a caller-supplied row;
- test restart/recovery using snapshots derived from actual durable history.

### B4. Sector-flow mapping and mirror integrity

**Implemented for the supported movement types.** The adapter distinguishes asset-holder and liability-issuer sides, validates reciprocal identities and equal signed amounts, and computes sector financial net lending without a balancing plug. The current test fixture exercises all six sector codes and checks the aggregate transaction sum.

Still required:
- independently validate all sector results against hand-calculated account tables for every supported event type;
- test multiple currencies and valuation bases without cross-currency netting;
- add capital transfers, non-financial transactions and the capital-account counterpart before claiming full sectoral net-lending/capital-account reconciliation;
- treat any non-zero discrepancy as a diagnostic, not a reason to fabricate a plug.

### B5. Period-close completeness and durable projection

**Not implemented.** The adapter can replay a supplied history sequence, but the repository does not yet have signed period-close declarations from each required register, a six-register completeness assembler, or an atomic native SFC projection store with sealed checkpoints.

Next:
- require signed period-close declarations for each source register, including explicit zero-activity declarations;
- include period bounds, source sequence/checkpoint, registry versions/digests and evidence references;
- persist source-event coverage, movement coverage, opening snapshot digests, mapper version, roll-forward and sector aggregates atomically;
- add idempotent replay, crash injection, checkpoint recovery and versioned reprojection tests;
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

The remaining required tests include durable-history integration of interbank and refinancing events through the adapter, evidence-backed loan/refinancing opening exporters, multi-currency sector reporting, signed period-close completeness, native projection-store recovery, and crash-atomicity.

## Implementation sequence

1. **Done, partial scope:** versioned instrument terms and explicit financial position identity resolution.
2. **Done, partial scope:** effective-dated sector registry with digest pinning at projection.
3. **Partially done:** complete explicit opening snapshot contract; durable loan/refinancing opening exporters remain.
4. **Done, supported events only:** separate native financial SFC adapter and movement mapper.
5. **Not done:** native financial projection store/checkpoint and atomic persistence.
6. **Partially done:** deterministic mapping/replay and hash-chain verification; crash-injection and durable adapter recovery remain.
7. **Not done:** period-close assembler for all required registers; do not synthesize six-register events for a financial-only source event.
8. **Not done:** integrated multi-period sector financial accounts, complete capital account and real-economy reconciliation.

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

A new real-register integration test is being added to ensure the durable `OperatingFinancialRegister` (not only a fake source) flows through `project_and_persist()` and `rebuild_and_verify()`. This test is not yet confirmed by CI.

Still open: authoritative evidence-backed opening exports for all loan/refinancing positions; signed completeness declarations for all required registers; production integration with physical/capital/product/labour/legal-rights domains; a complete capital account and financial-vs-capital net-lending reconciliation; interest/fees/arrears/default/impairment/collateral lifecycle; and exact-HEAD green CI. Do not treat a six-sector financial projection or zero-sum synthetic fixture as proof of full SFC closure or solved liquidity scarcity.
