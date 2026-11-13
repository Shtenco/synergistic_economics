# A2.4 continuation audit — remaining cross-register closure gaps

Date: 2026-11-11
Audited ref: `24a8d0b4e5c9f740857395b1c7b9f1044e05bf3f`
Scope: read-only source audit of the A2.4 SFC/SCCE branch and current PR/CI metadata.
This document records findings and acceptance criteria. It does not claim that any pending test passed or that a production ledger exists.

## 1. Snapshot and evidence boundary

- PR #4 is open and Draft; it is not merged.
- Audit branch: `audit/sfc-scce-a2-4-continuation-20261111`.
- Exact inspected HEAD: `24a8d0b4e5c9f740857395b1c7b9f1044e05bf3f`.
- PR metadata reports 184 commits and 34 changed files.
- Canonical `main` remains the target base and is not changed by this audit branch.
- Exact-head runs observed queued: Prototype validation `42926000574`, SCCE Stage-C2 `42926000400`, A2.4 audit controls `42925993756`. No completion conclusion or logs were available in this observation. Do not infer PASS.

## 2. New source-level finding: period identity is not yet uniform across financial controls

The entity/sector journal fixture has a period-aware claim identity, but
`research/audits/sfc_scce_a2_4_2026-11-11/audit_instrument_stock_flow.py`
still defines `Position` and `IssuerLiability` without an
`effective_period` field. Its `_identity()` key therefore cannot distinguish
otherwise identical positions in different periods.

This is a coverage/interface gap, not proof that the current single-period
fixture's arithmetic is wrong.

Required correction:
1. Add an explicit period to holder and issuer position records.
2. Include period in the mirror key and reject cross-period matches.
3. Require exactly one opening position per instrument/holder/issuer/period.
4. Enforce opening(t+1) = closing(t), except for explicitly typed boundary,
   correction, or restatement events.
5. Derive T/V/O from canonical event records; do not accept manually supplied
   totals as the only evidence.
6. Test one-pass iterables, duplicate period records, missing periods,
   reordered periods, and cross-period mirror substitution.

## 3. Financial event store and journal adapter: remaining authority gap

The SQLite event store is an append-only, single-host prototype. Its own module
states that accounting validation is upstream. The adapter calls a supplied
`journal.post()`; the source and PR description explicitly state that the
adapter does not independently establish the identity of an arbitrary
validator. The adapter also does not update SFC instrument positions or sector
balance sheets.

Consequences:
- Durable event persistence is not yet an atomic commit of the full economic
  state.
- A persisted event group can exist without corresponding derived SFC position
  updates because those updates are not in the same transaction boundary.
- The synthetic journal's in-memory registry is not a production authority
  boundary and is not thread-safe.
- Store-level shape checks must not be confused with accounting validation.

Acceptance criteria:
- One authoritative runtime command validates, persists and projects an event.
- The validator cannot be substituted by a caller-provided lookalike.
- Event group, postings, instrument-position deltas, sector-account deltas,
  idempotency key and projection cursor commit atomically or are recoverably
  replayed from one durable source of truth.
- Crash injection is tested after each boundary: validation, event insert,
  posting insert, position projection, sector projection and cursor advance.
- Rebuild from the event log reproduces byte-for-byte canonical projections.
- Concurrent duplicate commands produce one economic effect.
- Corrections are new compensating events; committed history is never edited.

## 4. Instrument stock-flow: accounting dimensions still missing

The current component fixture verifies holder/issuer T/V/O mirrors and
instrument identity dimensions. It is not a contract-level instrument ledger.

Required dimensions and events for SFC-GOLD-1/2:
- contract/agreement ID and instrument series ID;
- creditor, debtor, beneficial owner, legal issuer and servicing agent;
- currency, denomination, nominal amount, carrying amount and valuation basis;
- issue, effective, recognition, accrual, due, settlement and maturity dates;
- principal schedule, coupon/rate basis, day-count convention and accrued interest;
- FX source, FX fixing date, transaction-date rate and closing-date rate;
- collateral/guarantee references, valuation, haircut, priority and enforcement state;
- ownership shares and consolidation perimeter;
- impairment stage, gross carrying amount, loss allowance and net carrying amount;
- default, restructuring, write-off, legal forgiveness and cash settlement as
  distinct events.

Do not collapse legal principal, recognized gross asset/liability, accrued
interest, loss allowance, carrying value and cash paid into one balance.

## 5. Required SFC-GOLD-1 and SFC-GOLD-2 corpus properties

SFC-GOLD-1 must be a frozen, versioned event corpus. Initial positions must be
reconstructed from opening events or a signed opening snapshot whose hash and
provenance are fixed. Closing positions must be derived, never manually seeded.

Minimum adversarial cases:
- bank loan origination creates a borrower deposit and matching bank liability;
- non-bank lending transfers an existing deposit and does not create a second
  deposit;
- payment transfers deposits without creating new aggregate deposits;
- principal repayment extinguishes matching positions;
- interest accrual changes the relevant receivable/payable before cash settlement;
- FX revaluation changes carrying values but not transaction-based financial NL;
- write-off removes a creditor asset but does not itself legally forgive debtor
  principal;
- legal forgiveness is a separately evidenced event;
- impairment allowance changes net carrying value without silently changing
  contractual principal;
- collateral and guarantee are memorandum/contingent relationships unless
  recognition criteria are explicitly met;
- duplicate, late, backdated, reversed and out-of-order events are handled by
  explicit policy rather than silent overwrite.

SFC-GOLD-2 must replay these cases over multiple periods and reconcile:
opening + transactions + revaluations + other volume changes = closing,
for both holder assets and issuer liabilities, at the full instrument key.

## 6. B8.1 capital bridge: same cohort is necessary but not sufficient

The opt-in cohort adapter demonstrates a synthetic mapping of physical
service flow to the existing dimensionless SCCE capital multiplier. It is not
a monetary capital account and does not automatically advance/persist cohorts
inside the normal SCCE period loop.

Remaining requirements:
- consume actual B8.1 cohort and component/material passport records;
- preserve cohort, component, material, owner, rights, location and vintage IDs;
- distinguish repair, remanufacture, replacement, transfer, impairment,
  reclassification, physical loss and final retirement;
- link additions/disposals/CFC/revaluation to the same physical cohort IDs;
- separate physical quantity, productive capacity, service flow and monetary
  valuation in the data model;
- enforce period sequencing and durable replay barriers in the production
  lifecycle, not only the adapter contract;
- reconcile gross stock, net stock, CFC, disposals, revaluation and capital
  services independently;
- demonstrate rollback and restart recovery across the complete period update.

A dimensionless compatibility multiplier must never be presented as monetary
capital stock or as empirical calibration.

## 7. Product and physical-flow bridge

The current product and physical-flow fixtures are component controls.
Remaining end-to-end work:
- bind product/grade/unit identities to actual B2/B3 runtime records;
- use stable flow IDs with reciprocal sender/receiver endpoints;
- preserve native units and prohibit cross-grade or cross-unit aggregation;
- model inventory opening, production, transformation, imports, exports,
  deliveries, losses, waste and closing stock;
- reconcile process inputs and outputs with explicit conversion/yield/loss
  coefficients and provenance;
- tie monetary valuation to the exact physical flow, period, price basis,
  currency and price date;
- ensure consolidation eliminates internal transfers once and only once.

## 8. Labour, time, consent and rights

The labour fixture is not yet a complete rights-aware runtime register.
Required additions include:
- interval-level provenance and overlap controls across all activities;
- paid/unpaid classification and compensation/accrual/settlement separation;
- consent scope, expiry, withdrawal and re-consent;
- capability and service-quality transitions tied to observed delivery;
- safety limits, refusal, appeal and dispute workflows;
- privacy minimization and access/audit controls;
- no inference that a scheduled hour equals delivered service or consent.

## 9. Net-synergy and empirical evidence boundary

A2.4.6 source audit and an illustrative estimand do not constitute
preregistration. Before any comparative claim:
- freeze treatment and comparator from the actual regime code;
- freeze primary outcomes, horizon, seeds, exclusions, missing-data policy and
  statistical method;
- account for all incremental material, energy, labour, capital, time and
  coordination costs;
- use prospective preregistration before observing confirmatory outcomes;
- separate exploratory runs from confirmatory runs;
- report uncertainty, sensitivity and failed/negative results;
- prohibit claims of empirical net synergy from synthetic fixtures alone.

## 10. Gate order and stop conditions

1. Gate 0: exact-head CI, deterministic execution, artifact hashes and complete
   logs. No status-only PASS.
2. Gate 1: frozen SFC-GOLD-1/2 and independent arithmetic oracle.
3. Gate 2: same-event multi-period closure across physical, product, cohort,
   labour, financial and sector registers, with no balancing plugs.
4. Gate 3: prospective comparative preregistration and confirmatory execution.
5. Gate 4: external/empirical validation and uncertainty analysis.

A2.4.8 remains blocked until Gates 0–2 pass. A unified economic engine remains
out of scope until the contracts and authority boundaries above are proven.
PR #4 must remain Draft and unmerged while these conditions are open.

## 11. Immediate execution sequence

1. Poll the three exact-head CI runs and inspect job steps/logs; diagnose runner
   queue versus test failures without weakening assertions.
2. [SOURCE IMPLEMENTED — EXECUTION PENDING] Add period identity and cross-period continuity to the instrument
   stock-flow fixture. The implementation now carries `effective_period` on
   holder and issuer records, includes it in mirror identity, enforces
   adjacent-period closing/opening continuity, rejects skipped periods, and
   requires explicit period selection for multi-period financial net lending.
   Negative controls cover cross-period mirror substitution, discontinuity,
   skipped periods and one-pass period-scoped aggregation. This remains a
   synthetic component fixture; it is not event-store projection or runtime
   integration.
3. [SOURCE IMPLEMENTED — EXECUTION PENDING] Freeze the initial SFC-GOLD-1
   event schema and canonical expected outputs. The v1 corpus now covers bank
   loan origination, supplier payment and principal repayment, with frozen
   final instrument balances and sector financial net-lending outputs.
4. [SOURCE IMPLEMENTED — EXECUTION PENDING] Implement and wire an independent
   SFC-GOLD-1 arithmetic oracle. It imports no production journal, event store
   or projection code; it independently validates decimal amounts, entity/
   sector identity, event composition, double-entry, holder/issuer mirrors,
   closing positions and sector net lending. Adversarial mutations cover
   holder, instrument, sector, event-type and duplicate-event failures.
5. Add crash/replay tests for the event-store-to-position projection boundary.
6. Bind capital/product/physical-flow/labour fixtures to real runtime schemas.
7. Only then run the full multi-register replay and evaluate Gate 2.

## Audit conclusion

The branch has meaningful component-level controls and a durable event-store
prototype. The critical remaining problem is not a shortage of local assertions:
it is the absence of one authoritative, replayable, multi-period event-to-ledger
path and an independent gold oracle that proves all projections agree.

No PASS, production readiness, Gate 0 closure, A2.4.4 closure, A2.4.8 closure,
or empirical net-synergy result is claimed by this audit.


## 12. SFC-GOLD-1 implementation status

The initial frozen corpus and independent oracle are now present:
- `SFC_GOLD_1_CORPUS.json`;
- `SFC_GOLD_1_CONTRACT.md`;
- `audit_sfc_gold_oracle.py`.

The corpus is intentionally narrow and single-period. It is a baseline
control, not the full credit lifecycle. Exact-head CI execution remains
pending. Interest, FX revaluation, other-volume changes, impairment,
write-off, legal forgiveness, collateral/guarantees, multiple periods and
event-store projection are explicit future extensions. No Gate PASS or
A2.4.4/A2.4.8 closure is implied.


## 13. SFC-GOLD-1 semantic closure beyond local balance

A source review identified that debit/credit balance, per-instrument
holder/issuer mirroring and event account-side cardinality do not alone prove
that all legs belong to one coherent economic event. The independent
SFC-GOLD-1 oracle now checks cross-leg roles for bank loan origination,
supplier payment and principal repayment. It also ties account families to
instrument classes and enforces no-FX currency consistency in v1.

Two adversarial cases preserve local balance/mirroring while violating
cross-leg semantics: a new deposit is redirected to an entity other than the
loan borrower, and both mirrored loan records are relabelled as deposit
instruments. The oracle must reject both.

This is source implementation only. The exact-head CI jobs remain queued
without execution evidence; no PASS is claimed. Next extensions remain
interest accrual/settlement, FX and other-volume changes, impairment versus
write-off versus legal forgiveness, multi-period projections, and event-store
replay/crash recovery.


The SFC-GOLD-1 oracle now also binds the frozen v1 roles to CB/H/NFC sectors
and requires distinct loan/deposit and payer/supplier deposit instruments.
A coordinated bank-sector mutation that keeps all entity/sector labels
internally consistent is included as a negative control. These are fixture
scope constraints, not a general-purpose institutional-sector ontology.
Execution remains pending.


## 14. SFC-GOLD-1 sequential stock and event replay boundary

The independent oracle now validates the declared single period, requires
registered counterparties/issuers, enforces immutable instrument identity
across events, and checks running positions after each canonical event.
The frozen event-array order is the v1 replay order. Because v1 has no opening
stock or overdraft facility, negative intermediate positions are rejected.

New negative controls cover an over-sized balanced repayment, repayment before
origination, a changed maturity under a reused instrument ID, and an
undeclared period. These controls are source implemented, not yet execution
proven. The v1 no-negative-position assumption must not be generalized to
systems with overdrafts or opening balances.

The next genuine integration boundary remains durable event-store replay:
same ordered source events must rebuild instrument positions and sector
accounts after process restart, with crash injection and idempotent duplicate
delivery. A multi-period SFC-GOLD-2 corpus must separately model opening
snapshots and explicit overdraft/credit policy rather than inherit v1
assumptions.


## 15. New native Labour and Legal Rights participant implementation

The integration branch now contains two durable domain event stores rather than treating Labour and Legal Rights as only audit fixtures. Both use replay-derived state, per-aggregate optimistic versions, append-only ACL events, default-deny access, immutable correction lineage and a full-envelope SHA-256 chain. Their SQLite participant inbox is colocated with the native event log. Prepare reserves the aggregate and validates both authority and transition; outstanding prepares block ACL mutations; commit appends the domain event and then records an idempotent receipt, allowing recovery after a crash between those steps.

Labour preserves offered/accepted/scheduled/started/delivered/verified/disputed/settled distinctions, explicit consent references, actual delivered hours, stop/withdrawal, capability assessments and mutually exclusive time intervals. Legal Rights supports title without a debtor, claim holder/obligor, evidence, transfer, encumbrance/release, dispute/adjudication, correction and legal extinguishment. A creditor write-off is not represented as legal forgiveness.

A coordinator integration test uses these two native stores plus four existing SQLite protocol participants. Therefore only Labour and Legal Rights are now native participants. Physical, capital, product and financial adapters must still be bound to their authoritative stores before the six-register command can be certified.

The next acceptance gate is exact-HEAD CI for the new tests, followed by native adapters for the remaining four stores and a six-native-participant crash/restart matrix. The shared multi-period reconciliation kernel and remote WORM/KMS deployment are separate gates, not implied by these stores.


## 16. Common event group and period-reconciliation kernel

The coordinator now returns a canonical committed event group only after its six-participant visibility barrier. Each participant event carries the same common_event_id (the coordinator transaction ID), native event identity, aggregate version, payload digest and domain payload. Labour and Legal Rights persist the common ID in their own event-chain metadata; four other participants remain protocol conformance stores pending native adapters.

The new Decimal reconciliation kernel requires every participant to declare either explicit stock_flow_movements or a reasoned no_stock_flow_effect. It enforces position identity across register/position/measure/unit/currency/valuation-basis/holder/issuer/instrument, the T/V/O identity and adjacent-period carry-forward, plus equal holder/issuer or opposite sender/receiver mirrors. It is an executable contract, not yet wired to all actual source schemas. A missing physical, capital, product or financial mapper must fail closed rather than be replaced by synthetic values.

## 17. S3 Object Lock anchor adapter

The new S3 adapter requires bucket Object Lock and versioning, uses COMPLIANCE retention, conditional immutable object creation and a canonical external KMS key ARN, and verifies object version, retention, digest and encryption on reads. Per-service anchor records form a contiguous immutable hash chain. Tests use a mocked S3 client only. No live AWS bucket, IAM separation, KMS custody or disaster-recovery restore drill is available; deployment remains an explicit release gate.


## 18. Native physical, capital and product participant adapters

The coordinator can now bind directly to PhysicalFlowStore, CapitalCohortStore and ProductRegister. Each adapter uses the same database as its domain store for its prepared inbox and receipts, validates candidate operations against the current native revision/reducer, reserves the stream and invokes the store's idempotent append after the coordinator decision. Direct append operations are blocked while a prepare is outstanding. A mandatory external authorizer callback is injected; the adapter has no default allow policy.

Together with LabourRegister and LegalRightsRegister, this yields five native participants out of six. Financial remains protocol-conformance-only until the adapter can atomically use the validated journal and SFC projection store. The physical adapter covers the physical-flow register, not the P6 lot/reservation inventory lifecycle. The integration test proves one physical mirror reconciliation, not full six-register SFC/GOLD closure.


## 19. Native projection-aware financial participant

The financial coordinator participant now uses FinancialEventStore and the validated EntityJournal. It refuses registration unless the SFC opening snapshots and current projection replay verify. Prepare reconstructs canonical JournalEvent records, validates them in an independent EntityJournal and requires financial T/V/O movement metadata to match the SFC projection mapper. Commit invokes append_projected_group with the prepared transaction ID, so the event group, postings, instrument/control projections, coverage and cursor are committed in one native financial-store transaction.

The coordinator commits financial last, after physical, capital, labour, product and legal-rights participant receipts. This ordering prevents an SFC projection from becoming visible before the other five native stores have committed. The coordinator's global visibility barrier is still mandatory. It is a recoverable multi-database protocol, not a single cross-database transaction or distributed consensus system.

All six participants now target native stores. Remaining gaps: full lot/reservation inventory integration; actual T/V/O mappers for capital/product/labour/legal positions and financial control-only events; liability-side SFC mirrors in the common reconciler (the GOLD journal/oracle still validates these); cross-period six-register close/reopen/correction rebuild; and live remote WORM/KMS deployment.


## 21. Native append-before-receipt recovery

A deterministic fault-injection test terminates the participant operation after the native physical event append commits but before its receipt is persisted. A newly constructed participant retries the same prepare token; the native append is idempotent, the receipt completes and no duplicate flow is created. This covers the local native append/receipt crash window; full process-kill and multi-participant crash evidence remains in the coordinator crash matrix and exact-head CI.
