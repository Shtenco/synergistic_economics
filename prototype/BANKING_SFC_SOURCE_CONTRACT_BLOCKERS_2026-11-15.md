# Banking-to-SFC integration: implementation status and remaining blockers

Audit date: 2026-11-15  
Scope: `research/bank-deposit-credit-audit-fix-20261115`, PR #13.  
Status: **partial native adapter implemented; full six-sector SFC and capital-account closure not complete.**

## Executive finding

The earlier source-contract gate has progressed: version-pinned instrument terms, effective-dated sector membership, explicit opening-stock snapshots and a separate native `operating_financial_sfc_adapter.py` now exist. The adapter consumes immutable operating-financial register history, checks the register hash chain when invoked through `from_register()`, validates exact event/movement coverage and reciprocal financial mirror pairs, replays explicit T/V/O positions, and computes transaction-based sector financial net lending.

The current implementation supports wage event groups, bank loan origination/principal repayment, interbank deposit transfers settled through central-bank reserves, and central-bank refinancing advances/repayments. A synthetic six-sector fixture exercises household, NFC, commercial-bank, central-bank, government and ROW membership over two consecutive periods, including interbank reserve redistribution and refinancing repayment.

This is a **working projection slice**, not a complete six-sector SFC. A durable financial-only projection store/checkpoint and a separate `period_governance.py` gate for six signed register-completeness attestations now exist. The governance gate requires externally verified checkpoints and per-register signer authorization, but production-native adapters do not yet issue and bind all six authoritative attestations into one live close. Full production-to-financial integration, complete capital-account flows, interest accrual, defaults/impairment, and a reconciled financial/capital account remain incomplete. A six-sector financial net-lending sum of zero in the synthetic fixture is a mapping/reconciliation test, not proof of macroeconomic closure or economic viability.

## Implemented source contracts and adapter

1. `prototype/sfc_source_contracts.py` defines versioned `InstrumentTermsRegistry`, effective-dated `EffectiveDatedSectorRegistry`, explicit `OpeningStockSnapshot` and `OpeningPosition` records. Registry versions and canonical digests can be pinned to a projection.
2. Instrument terms include instrument class, denomination, currency, valuation basis, maturity classification/date, rate type/reference/spread, reset frequency, day-count convention, payment frequency, repayment type and effective periods. Missing or ambiguous terms fail closed.
3. Sector membership resolves holder and issuer entities by movement period; overlapping, missing or unsupported membership fails closed.
4. `prototype/operating_financial_sfc_adapter.py` is a separate native adapter. It does not route operating-financial envelopes through GOLD-2A or `sfc_projection_store.py`.
5. The adapter covers five native opening-position families (deposits, reserves, loan principal, central-bank refinancing principal, and wage receivables/payables) plus movement events (wage event groups, bank credit, interbank payments, central-bank refinancing). It validates mirror pairs, event-to-movement assignment, source coverage, registry digests and explicit opening rows before replay.
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

Account-opening events now carry an explicit first-active period (defaulting to period 1 for backward-compatible callers). An account is omitted from earlier snapshots, its opening balance is included at its first-active period, and prior movements are replayed only from periods at or after that opening period. The exporter verifies the native register chain and envelope digest, but its digest is not a signed completeness attestation or a source-checkpoint binding. The five supported native opening families are now automatically composed into registry-resolved `OpeningStockSnapshot` objects, pinned to the exact durable financial source checkpoint. Pre-existing loan/refinancing principal is now represented by explicit stock-only native opening events and included in the five-family composed snapshot. Each event binds original/outstanding principal, historical origination period, first modeled opening period, durable deposit/reserve account reference, contract reference and contract-evidence reference. Reducers verify account identity, exact minor-unit bounds, origination/opening chronology and no-flow envelope semantics; later repayments remain causation-linked and reduce only subsequent period openings. The integration tests cover real durable history, no deposit/reserve issuance, period-to-period principal roll-forward and projection recovery.

The remaining limitation is authentication strength: contract/evidence/authority references are persisted and authorized by the native register but are not independently cryptographically verified signatures or issuer credentials. This does not cover unsupported financial instruments.

Next:
- preserve the backward-compatible rule that legacy account-opening events without a period are period-1 openings; do not retroactively reinterpret sealed legacy history;
- add issuer-key signature verification, revocation/expiry policy and externally governed evidence resolution for pre-history loan/refinancing contracts; keep unresolved evidence fail-closed;
- extend the composed snapshot only when additional financial instrument classes gain native lifecycle/opening exporters and versioned terms;
- retain exact checkpoint binding and mirror/identity checks; signed period-completeness declarations remain a separate six-register governance requirement, including explicit zero-activity declarations;
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

The cross-register coordinator separately implements a six-participant prepare/commit visibility barrier and an append-only committed event-group stream. It remains a protocol/conformance harness until authoritative native-domain adapters are connected. Separately, `period_governance.py` implements an append-only close/reopen gate that verifies one externally signed close checkpoint plus six independently authorized register attestations, including explicit zero-activity declarations, source cursors, event roots and opening/closing state hashes. Its tests use deterministic in-memory checkpoint/signature-verifier fixtures; this proves the governance contract, not live production signing or source completeness. The period gate is not yet fed by all six native production adapters, and there is still no capital-account reconciler.

Next:
- connect each authoritative source adapter to independently signed period attestations and the external trust/rollback-resistant sequence services;
- bind period bounds, source sequence/checkpoint, registry versions/digests, completeness scope and evidence references;
- retain the native financial snapshot/checkpoint as a separate projection until the six native source adapters and capital-account close are integrated;
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
3. **Done for five recorded native families; partial overall:** deposits, reserves, loan principal, refinancing principal and wage claims/payables are composed into registry-resolved, checkpoint-pinned `OpeningStockSnapshot` objects. Pre-history loan/refinancing principal and additional unsupported instruments still require native evidenced opening contracts/events; signed six-register completeness remains separate.
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

Still open: independent cryptographic issuer/contract attestation for the now-recorded pre-history loan/refinancing openings; any additional unsupported financial instrument exporters; live signed completeness declarations from all required registers; production integration with physical/capital/product/labour/legal-rights domains; a complete capital account and financial-vs-capital net-lending reconciliation; interest/fees/arrears/default/impairment/collateral lifecycle; and exact-HEAD green CI. Do not treat a six-sector financial projection or zero-sum synthetic fixture as proof of full SFC closure or solved liquidity scarcity.

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

**Historical note — superseded by the checkpoint-pinned opening addenda below:** at this stage, the exporters still emitted legacy `PositionIdentity` rows. The later builder now composes five native opening families into registry-resolved, checkpoint-pinned `OpeningStockSnapshot` objects. The remaining gap is not composition for recorded lifecycles; it is independently evidenced principal that predates the durable event history, unsupported instrument classes, and live signed period completeness.


## Addendum — period-pinned account openings and exact financial arithmetic (2026-11-15)

Deposit and reserve account-opening events now carry `period_index` (default 1 for backward-compatible legacy callers), and the reducer retains `opening_period_index`. Historical account-opening exports omit accounts before their first-active period, include the immutable opening balance at that boundary, and replay only prior-period movements. Backdated loan, interbank, refinancing and wage-payment movements that precede any affected account's opening period are rejected at the register boundary.

The financial reducer now executes accepted monetary arithmetic under a bounded high-precision Decimal context, rejects source decimals beyond the exact-decimal bounds, and uses exact summation for bank balance snapshots and historical opening reconstruction. A regression test uses a principal larger than 28 significant digits, repays a unit amount, and checks the exact remaining loan, deposit and aggregate bank balances.

These changes improve the financial register's period semantics and arithmetic. The later checkpoint-pinned builder addenda supersede the composition limitation stated here; six-register closure remains unproven. Exact-HEAD CI must confirm the current implementation.


## Addendum — durable source-instance and chain-tail checkpoint binding (2026-11-15)

The durable register metadata now persists a per-database `register_instance_id` (32 lowercase hexadecimal characters). Existing V2 register databases receive this identifier through an additive metadata-column migration; it is retained across process restarts. `source_checkpoint()` first verifies the complete event/hash chain, then returns the instance identifier, global event count and tail hash.

The banking SFC pipeline no longer trusts a caller-selected source identifier. It derives the checkpoint namespace from the verified financial register instance ID and principal scope, rejects a conflicting caller-supplied ID, and uses the global register event count rather than the last event in the filtered financial stream. The SQLite projection schema is versioned forward and persists the source-chain tail hash in both immutable snapshot and checkpoint rows; recovery compares both copies and the freshly verified tail hash. A changed tail at an unchanged cursor is rejected, while legitimate cursor advancement is allowed.

Regression tests now cover stable instance identity across restart, tail-hash advancement, caller-ID substitution, same-cursor source-tail changes, and checkpoint-copy verification. The metadata identifier is a durable local identity, not a cryptographic hardware identity or proof of independent custody; copying a database also copies its instance ID. The source hash chain and exact tail checkpoint detect changed history, but do not by themselves prove external issuer authority or signed period completeness.

The projection-store schema change intentionally rejects an older persisted store schema with an explicit-migration error rather than silently treating legacy checkpoints as source-tail-pinned. The opening-snapshot composition gap is now closed for the five supported native financial exporters and their checkpoint-pinned composition; signed six-register completeness remains a governance-side validation contract until all six native adapters produce their own independently signed declarations. Exact-HEAD CI is still required.


## Addendum — stable source snapshots and checkpoint ancestry (2026-11-15)

The durable register now exposes `history_with_checkpoint(aggregate_id, principal_id)`, which returns the authorized financial history and the global register instance/count/tail-hash checkpoint from one SQLite read transaction. The pipeline requires this atomic API; a source implementation that cannot provide it fails closed rather than risking a cursor newer than the projected history.

The durable register also exposes `chain_hash_at(global_sequence)`, which re-verifies the complete event chain before returning a historical ancestor hash. Before appending or recovering a projection, the pipeline compares the currently observed hash at the previously sealed cursor with the hash stored in the prior checkpoint. This rejects a copied-register fork that reuses the same instance ID but diverges after the last sealed cursor. Regression tests cover missing atomic history/checkpoint support and a forked source attempting to advance the checkpoint.

The financial opening builder now composes deposit, reserve, loan, central-bank refinancing, and bilateral wage receivable/payable opening positions through five native register exporters. It resolves each bilateral position against the effective-dated sector and instrument registries, rejects missing terms/sectors and duplicate identities, checks mirror equality, and embeds the exact source register ID, global event sequence and chain hash in each snapshot. The projection pipeline rejects any opening snapshot not pinned to the exact source checkpoint used for the transaction history. The builder also checks the checkpoint again after all native reducers finish; a concurrent append invalidates the complete build and requires a retry.

This closes the automatic financial opening composition and local snapshot-race gap for the currently supported financial instruments. It does not turn a copied local database into independently authenticated custody, nor does it supply signed external authority or period-completeness attestations. The current builder is limited to these five native financial opening exporters; it does not synthesize non-financial opening positions. Wage positions require their instrument terms and effective-dated sector memberships to be present in the caller-supplied registries.


## Addendum — checkpoint-pinned financial openings and signed close gate (2026-11-15)

The financial-only opening builder now composes all five native opening exporters: deposits, reserves, loans, central-bank refinancing and wage receivable/payable claims. It resolves each bilateral identity against the supplied version-pinned instrument and effective-dated sector registries, embeds the exact durable financial register ID/global sequence/tail hash into every snapshot digest, and rejects projection when the snapshot checkpoint differs from the atomically read transaction-history checkpoint. The builder fails closed if the source changes while any of the native opening reducers are running. Tests cover period-to-period roll-forward of deposits, reserves, loans, refinancing and unpaid wage claims, plus concurrent source mutation.

PeriodGovernance.close_period() and publish_generation() now require exactly six separately signed register-period completeness attestations. The main close checkpoint commits to the ordered six-attestation inventory; each declaration binds register, period, generation, durable source identity/cursor/hash, event count/root, activity status, opening/closing state hashes and reconciliation hash. Zero activity is explicit, must commit to the canonical empty event root, and must preserve the opening state. Attestations are persisted immutably and checked again on idempotent retries.

This implements the governance-side validation and storage contract, not the six native attestation producers. Physical, capital, labour, product, legal-rights and financial adapters still need to produce their own signed period declarations from authoritative sources. The new gate intentionally prevents a period from being closed with absent, inferred or fabricated zero-activity claims. It does not yet constitute a live six-register SFC close.
