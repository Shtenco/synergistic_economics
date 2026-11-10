# A2.4 SFC/SCCE audit status — 11 November 2026

## Boundary
- Canonical branch: `main`; unchanged by this audit.
- Audit branch: `audit/sfc-scce-a2-4-continuation-20261111`.
- No unified economic engine is assembled.
- No SFC financial layer is integrated into SCCE.
- The audit branch adds test fixtures and an explicit opt-in adapter `prototype/capital_cohort_bridge.py`; it does not alter the existing SCCE production step, queue implementation or default scalar-capital path. Canonical `main` remains unchanged.

## Current position
- Six-sector synthetic SFC: arithmetic and mirror positions close under the source's stated assumptions.
- Three blockers remain: A2-44 state-space incompatibility; A2-46 capital stock/services/depreciation separation; A2-48 bank-created deposits versus transfer of existing deposits.
- A2.4.1–A2.4.5 now have audit specifications for typed transitions, capital/services, product dimensions/valuation, financial events and labour/capability/time/consent. These are paper contracts, not completed runtime integrations.
- A2.4.6 net-synergy estimand and A2.4.7 cross-register test/release gates are specified. Neither comparative preregistration nor full gate suite has passed.
- A2.4.8 end-to-end numerical interface experiment is the next control, not a mandate to build the runtime.

## Latest SCCE CI
- Prototype validation run 42810082229: failed one of 133 tests.
- C2 validation run 42810081975: failed the same test. Both logs confirm the same assertion failure (0.0 not greater than 0.0); all other 132 tests pass and downstream experiments are skipped.
- On the audit branch only, the seed-dependent expiry/overflow test was replaced with a controlled physical-delivery fixture. It retains the actual SCCE step, household allocator, FIFO queue, queue ageing and validation path. Period 1 admits a known unmet care quantity; period 2 delivers 25% of combined current-plus-backlog claims, which equals half of the old queue when the opening queue equals current need. The remaining half must expire. A separate capacity fixture admits 1% and records 99% as overflow.
- The changed test commit is `bea7d625087b7615f764bd97b2e5ce8ebc8c3070`. The commit has no reported status checks yet; this deterministic test is **not yet CI-verified**. Do not claim C2-A3 is green until both workflows run successfully.
- Queue primitive tests remain unchanged and independently cover FIFO expiry, retention and overflow.

## Artifacts
- `FINDINGS_001.md`: SFC arithmetic, interfaces, SCCE CI and A2.4.8 plan.
- `FINDINGS_002_CARE_QUEUE_INTEGRATION.md`: exact queue timing, failing test path and deterministic-fixture acceptance criteria.
- `A2_4_2_CAPITAL_STOCK_SERVICES_BRIDGE.md`: typed bridge across B8.1, B4 and SFC gross/net valuation; includes a same-cohort numerical example and explicitly separates gross acquisitions/disposals in replacement-cost stock equations from national-accounts net GFCF.
- `A2_4_3_PRODUCT_DIMENSIONAL_VALUATION_CONTRACT.md`: product-grade-native-unit registry, process balance and monetary valuation adapter.
- `A2_4_4_FINANCIAL_EVENT_BALANCE_BRIDGE.md`: immutable event envelope, double-entry posting families and credit-creation/transfer distinctions.
- `A2_4_5_LABOUR_CAPABILITY_TIME_CONSENT_BRIDGE.md`: time, capabilities, actual services, consent, compensation and rights boundaries.
- `A2_4_6_NET_SYNERGY_ESTIMAND.md`: counterfactual, incremental input/cost accounting and preregistered outcome vector.
- `A2_4_7_CROSS_REGISTER_TEST_GATES.md`: layered test architecture and release gates.
- `audit_sfc_six_sector.py`: standard-library Decimal control of the six-sector SFC example, credit event distinction and B2 physical balances.
- `audit_capital_bridge.py`: standard-library Decimal controls for physical quantity, gross/net stock, CFC, disposals, revaluation, capital services and gross/net SFC net lending.
- `audit_product_dimensions.py`: standard-library Decimal controls for B2 product balances, process conversions and price/quantity separation.
- `audit_financial_events.py`: standard-library Decimal controls for bank deposit creation, non-bank transfer, payments, principal and interest.

## Next sequence
1. Verify the deterministic SCCE fixture in CI; obtain both Prototype validation and Stage-C2 workflow logs. Until then C2-A3 is not validated.
2. Build the same-cohort A2.4.2 integration fixture from B8.1 records; test physical states, services, gross/net stock, CFC and revaluation together.
3. Implement the A2.4.3 product registry/valuation adapter and prove the B2 physical quantities reconcile to SFC values without cross-unit aggregation.
4. Implement A2.4.4 event posting fixtures including accrual/settlement, default, impairment and write-off; reconcile instrument mirrors and sector accounts.
5. Add A2.4.5 time/consent/compensation test fixtures and preserve the rights boundary.
6. Freeze A2.4.6 preregistration, then complete A2.4.7 CI coverage; execute A2.4.8 only when the entry conditions in `A2_4_7_CROSS_REGISTER_TEST_GATES.md` are met.
7. Only after Gate 2 and relevant comparative evidence pass, design the integrated economic engine boundary. Do not merge the ledgers prematurely.


## Continuation — three-task execution package

- Added `audit_same_cohort_capital.py`: one cohort input set drives physical
  count, capital services, gross/net stock, CFC, gross/NBV disposals and gross/net
  revaluation. It asserts direct cohort closing valuation against the stock-flow
  bridge. Synthetic expected values remain those in A2.4.2. **Committed; runtime
  execution still pending.**
- Added `audit_product_valuation_adapter.py`: immutable typed product/grade/unit
  records, exact native-unit price denominator, period and valuation-basis
  metadata, and a quantity-preserving monetary view. Negative controls reject
  wrong unit denominator and cross-grade price. **Committed; runtime execution
  still pending.**
- Expanded A2.4.7 with an operational gate matrix, explicit PENDING semantics,
  per-gate evidence requirements and exact-head CI evidence requirements.
  **Specification strengthened; A2.4.7 remains open.**

The new capital and product scripts are independent standard-library controls.
They do not yet consume live B8.1/B2 runtime objects, and they do not constitute
a full register integration. No claim of executed PASS is made here.

## Updated next actions

1. Trigger and inspect PR CI for the deterministic SCCE fixture; require both
   Prototype validation and Stage-C2 to pass on the exact audit head.
2. Execute `audit_same_cohort_capital.py` and
   `audit_product_valuation_adapter.py` on a controlled runner; record exact
   command, interpreter, output, exit code and file hashes.
3. Bind the generic capital fixture to the actual B8.1 cohort output schema;
   reject any field mapping that cannot preserve vintage, status, retirement
   timing, service availability or component identity.
4. Extend the product adapter from unit valuation to node-level flow IDs,
   sender/receiver mirrors, inventory movements, process conversion and
   valuation reconciliation with B2/B3.
5. Implement the missing A2.4.4 journal event fixtures and A2.4.5 labour/consent
   fixtures before Gate 1 can be considered.
6. Freeze A2.4.6 preregistration and complete all A2.4.7 gates before A2.4.8.


## Continuation — journal, labour and physical-flow controls

Added three component fixtures:
- `audit_financial_journal.py`: event-ID idempotency and balanced debit/credit postings for bank loan origination, non-bank transfer, payment, principal repayment, interest accrual/settlement, impairment and creditor write-off. The debtor's legal liability is not silently extinguished by creditor write-off.
- `audit_labour_consent.py`: weekly interval budget, overlap rejection, consent-state gate, scheduled/safety delivery bounds, capability transition and wage accrual/settlement separation.
- `audit_physical_flow_register.py`: one physical flow ID mirrored by sender/receiver, exact product/grade/unit/period/quantity match, duplicate rejection and one-time cancellation of internal transfer at consolidated boundary.

All three files are committed component fixtures. Their execution in a recorded Python runner remains pending; do not describe them as runtime-tested or CI-green.

### CI after opening Draft PR #4
- Prototype validation run `42901021739` (run 307): queued at last poll; job `130126684304`.
- SCCE Stage-C2 validation run `42901021866` (run 38): queued at last poll; job `130126683896`.
- No completed job conclusion or logs were available at the last poll. CI remains pending.

### Current remaining blockers
1. Execute all five new audit fixtures (same-cohort capital, product valuation, physical flow, financial journal, labour/consent) and record exact output/exit status/hash.
2. Wait for both PR CI workflows and inspect full job logs. If the deterministic fixture fails, debug the model/test interaction; do not weaken assertions.
3. Bind physical flow and capital fixtures to actual B2/B3/B8.1 runtime schemas.
4. Complete financial stock-flow positions, sector mirror accounts and default/forgiveness legal distinction.
5. Complete labour interval provenance, paid/unpaid classification, rights/appeal and privacy tests.
6. Freeze A2.4.6 comparator, treatment definitions, primary outcomes, seed count, horizon, exclusions and statistical method against the actual existing regime implementation. Do not invent these parameters from an illustrative protocol.
7. Only after Gates 0–2 pass, begin A2.4.8; only after Gate 3 may comparative claims be made. Gate 4 remains empirical validation.


## Additional continuation — physical-flow endpoint hardening and executable CI

- Physical flow fixture updated at commit `c00a8c5a61928fa2ee36f8225ef6ecd5581ff0e7`: distinct outflow/inflow postings, reciprocal counterparty validation, product/grade/quantity/unit/period mirror checks, duplicate-ID rejection, node-level net flow, explicit consolidation boundary, and external export retention.
- Added `.github/workflows/a2-4-audit-controls.yml` at commit `9364918390ec5913aff42902eb4ed55706ab475a`. It runs nine audit scripts with Python 3.12 and compiles the audit directory first.
- Branch comparison after these additions: 34 commits ahead of `main`, 0 behind. `main` remains unchanged. Draft PR #4 remains unmerged.
- At the latest poll, the new commit had no surfaced PR workflow runs and combined status returned an empty status list. The two older PR jobs from the preceding head were still queued when last checked. This is **not CI success**; the new branch-push workflow still requires a completed run and logs.
- Financial journal and labour/consent controls are implemented as component fixtures, not yet integrated institutional-sector ledgers or a legally complete rights engine.
- A2.4.7 remains open; A2.4.8 remains blocked pending actual B8.1/B2/SCCE schema integration, financial stock-flow reconciliation, preregistration and exact-head test evidence.


## Additional continuation — A2.4.4 instrument stock-flow reconciliation

- Added `audit_instrument_stock_flow.py` (commit `81086176619a9a4307a5a8ef017da90897e884e9`). It uses the exact opening/closing position table from the six-sector SFC numerical closure: ten holder/issuer positions, seven mirror groups, stock-flow equations and the sector financial net-lending vector H +7, NFC −19, CB +4, CBank 0, GOV −15, ROW +23.
- Independent Decimal arithmetic verification passed for all ten roll-forwards, all seven mirror groups and zero aggregate net lending. This is an independent check of the example values, not execution of the committed script.
- The audit CI workflow was extended to execute this fixture. The workflow now contains eleven audit-script commands. A completed run and exact-head logs remain unverified.
- A2.4.4 remains open: no general-purpose instrument ledger, full legal/account taxonomy, or live SFC runtime integration has been implemented.


## A2.4.6 source-code audit of actual comparative experiments

- Added `A2_4_6_EXISTING_EXPERIMENT_PROTOCOL_AUDIT.md` (commit `6cd5c1c64bee7aecabc4707dc567054a0bc892e1`), based on actual SCCE source and workflow configuration.
- Confirmed four economic regimes: market, central, cooperative, cellular; market is the paired benchmark. Confirmed three household allocation policies: proportional, priority_weighted, floor_priority.
- Recovered existing Stage-B Monte Carlo defaults (100 seeds, 24 periods, 2 hops) and Stage-C2-A2 CI configuration (20 seeds, 24 periods, compound shock, 2 hops, 10 households/cell, priority dispersion 0.4, floor 0.5, backlog retention 0.5, backlog capacity 1 period, queue age 3 periods, backlog-first; all default policy arms).
- Identified 21 existing C2-A2 metrics and the current interval calculation (mean ± 1.96 × sample SD / sqrt(n)); no primary/secondary endpoint hierarchy, minimum practically important effect, explicit exclusions, confirmatory seed set or complete incremental-input accounting is frozen.
- Decision: existing runs remain exploratory synthetic comparisons. No retrospective preregistration or empirical net-synergy claim. A2.4.6 remains open.


## A2.4.5 consent/capability hardening

- Updated `audit_labour_consent.py` (commit `0df3d2b488cf21523c38db85b846fa5ab5d39c65`) to reject unknown consent states, non-positive time-budget horizons, negative closing capability stock, and delivery without an active consent state, in addition to overlap, schedule, safety and wage-settlement checks.
- An independent local execution of the fixture logic passed the 154/168-hour time example, 30-hour delivery, capability value 5.75, wage accrual 600, settlement 400 and closing payable 200; seven adversarial cases were rejected.
- This is component-level verification only. The committed script remains pending execution in the branch CI workflow; person-level privacy, consent revocation chronology, jurisdiction-specific legal basis and SCCE runtime integration remain open.


## CI observability correction — 11 November 2026

The dedicated `.github/workflows/a2-4-audit-controls.yml` trigger was changed
in commit `d50215669baca7f86323f16380f8b8c14812aa92` to include both:
- `push` to the audit branch with audit-directory/workflow path filters;
- `pull_request` targeting `main` with the same path filters.

This makes the audit suite eligible for PR-triggered validation and avoids
depending on manual `workflow_dispatch` from a workflow file that exists only
on a non-default branch. GitHub's documented `workflow_dispatch` behavior
requires the workflow file to exist on the default branch for the UI/manual
trigger path; the branch-push and PR triggers are distinct alternatives.

At the last poll after the trigger change, the GitHub connector had not yet
surfaced a dedicated audit-workflow run ID. The connector's
`fetch_commit_workflow_runs` wrapper reports only PR-triggered runs and may
not expose branch-push runs. The two existing PR validation runs
`42904160933` (Prototype) and `42904160781` (Stage-C2) remained queued,
without job conclusions or logs. No CI PASS is claimed.


## A2.4.4 additional journal integrity correction

- Replaced tautological constant assertions in `audit_financial_journal.py` with derived signed-balance calculations over actual journal lines. The fixture now verifies deposit-asset and bank deposit-liability changes for loan origination, non-bank credit transfer, supplier payment, principal repayment and interest settlement.
- `audit_instrument_stock_flow.py` now explicitly computes sector financial net lending from transaction flows (T), excluding revaluation (V) and other-volume changes (O). Added valuation-only and mixed T/V/O negative/positive controls.
- These controls are committed but await execution in the exact-head audit workflow. No production financial runtime is claimed.


## CI integration correction — execute audit scripts through established PR workflow

The standalone A2.4 workflow remains **push-triggered only** on the audit branch.
A PR trigger was considered and removed: this workflow file is not present on
`main`, so it cannot be relied upon as the repository's established PR check
before merge.

To obtain observable PR validation without modifying `main`, added
`prototype/test_a2_4_audit_controls.py` (commit
`751bbe60ca6e059d560ea5d84089f30f12aa4a56`). The existing
`.github/workflows/prototype-validation.yml` on `main` already triggers for
PRs changing `prototype/**` and runs unittest discovery over
`prototype/test_*.py`. The wrapper adds eleven separate unittest cases; each
executes one exact committed A2.4 script in a subprocess, captures output,
requires exit code 0 and requires a PASS marker. This is the primary
PR-observable path for all eleven audit scripts.

At the first poll after adding the wrapper, the connector had not yet surfaced
new PR run IDs for the new head. The earlier Prototype and Stage-C2 runs
`42904160933` and `42904160781` remained queued. No execution result is
claimed until new exact-head runs complete and their job logs are inspected.


## 11 November continuation — per-holder deposit mirror defect and correction

A code review of the then-current `audit_financial_journal.py` found that
non-bank deposit transfer (E2) and supplier payment (E3) moved holder-side
deposit assets but omitted the corresponding bank-liability holder movements.
The aggregate bank-deposit-liability change was still asserted to be zero
because no liability lines were present. Thus the old check could pass an
incomplete journal.

The journal now records the bank liability reduction for the outgoing holder
and increase for the incoming holder. Every deposit liability line identifies
its holder in an explicit counterparty field. A per-event validator compares
the signed deposit asset movement and issuer-liability movement for each
holder, not merely the system aggregate.

A deliberately adversarial E2 removes both bank liability-holder postings.
The remaining journal is still globally debit/credit balanced and aggregate
deposit assets still net to zero; the per-holder mirror validator must reject
it. The corrected fixture is committed at
`3d3706b1816aa8379e0ae7f48a34955af668fbd4`.

This is still a synthetic component journal. It does not yet validate all
financial instrument mirrors, legal claims, full sector ledgers or multi-period
SFC closure.


## Latest PR CI observation — audit harness included

The new wrapper commit `751bbe60ca6e059d560ea5d84089f30f12aa4a56`
changed `prototype/**`, so the existing main-branch PR workflows were
triggered and surfaced through the GitHub connector:

- Prototype validation: run `42904924813`, job `130140308153`
  (`test-economic-prototypes`) — **QUEUED**.
- SCCE Stage-C2 validation: run `42904924818`, job `130140308848`
  (`validate-c2-household-feedback`) — **QUEUED**.

At the latest poll both jobs remained queued, with no conclusion, steps or
logs. This is the first surfaced PR run pair whose test snapshot includes the
11-script A2.4 unittest wrapper. Later commits `01c43c6f...` and
`31b12467...` changed only audit documentation/gate records, not the Python
test wrapper or audit scripts. Still, exact-head completion and log inspection
are required before marking any script PASS.

Current financial journal fixture includes per-holder deposit-asset /
deposit-liability mirror checks. It rejects a globally balanced non-bank
transfer if holder-level liability movements are omitted. The instrument
stock-flow fixture computes sector financial net lending from transactions
(T) only; revaluation (V) and other-volume changes (O) affect stocks
but do not generate financial net lending.


## 11 November continuation — independent issuer-side T/V/O control

`audit_instrument_stock_flow.py` now has seven independent issuer-liability
records in addition to ten holder positions. It checks both sides' own
stock-flow roll-forwards and compares opening, T, V, O and closing component
by component. A negative control preserves the closing total while moving one
unit from T to V; the mismatch is rejected. A second negative control removes
an issuer record.

A separate local Decimal check of this component logic passed. The committed
script still requires execution through the exact-head CI wrapper; no CI PASS
is claimed. Full SFC-A…G remains open because currency, maturity, legal
instrument subtypes, equity, trade credit and multi-period event linkage are
not yet fully represented.


## A2.4.1/B4 — real SCCE physical transition fixture

Added `audit_scce_physical_transition.py` and integrated it into both the
standalone audit workflow and the existing Prototype unittest wrapper. It
executes the actual `DynamicCellularEconomy` for eight periods under the
existing cellular/compound-shock regime, rather than a synthetic replacement.

For every period it reconstructs each of the seven cells' inventory change for
every product from opening stocks, bounded raw-resource regeneration,
production events, intermediate/final delivery transfers, recipe input use
and final consumption. It also checks unique event keys, contiguous event
sequence, event-period consistency, production-event coverage, production
totals against `PeriodResult.output_by_product`, and the engine's own
raw-resource stock-flow identity after each period.

The fixture is now included as a twelfth audit-script test in
`prototype/test_a2_4_audit_controls.py`. Its first exact test execution is
pending the GitHub Actions run; no PASS is claimed before CI logs are available.
This closes an important source-to-test interface for the existing SCCE
physical engine, but does not integrate B8.1 cohorts or SFC financial stocks
into that engine.


## 11 November continuation — instrument identity and SCCE event integrity

Two further review findings were converted into executable controls:

1. **Financial mirror identity.** The SFC holder/issuer mirror key now includes
   instrument ID, instrument class, issuer, currency, maturity, denomination
   and valuation basis. A negative control changes only the issuer-side
   currency while preserving all nominal amounts and closing totals; the
   mirror validator must reject it. The existing six-sector example still
   uses coarse fixture defaults (LCU, unspecified maturity, nominal basis).
   Therefore this is identity-key hardening, not proof that the repository
   contains a complete currency/maturity-resolved instrument register.

2. **SCCE physical event integrity.** The eight-period real-engine transition
   audit now rejects non-finite quantities/distances and requires delivery
   event keys to match the complete payload identity
   (event type, period, product, seller and buyer), rather than checking only
   the event-type prefix. The inventory reconstruction remains independent
   of the engine's aggregate validation for each cell/product stock.

The changes are committed on the audit branch:
- `24b34cc7e3f38939696e4a7a30394761dbb5e803` — full financial instrument
  identity in holder/issuer T/V/O mirrors;
- `4a8a8e472db0dae42bff2c66f13b393ac13bcba6` — SCCE event key/payload and
  finite-value checks.

The audit workflow for the financial identity commit was surfaced as run
`42905574430`, but remained **queued** at the last poll. The earlier
Prototype and Stage-C2 workflows also remained queued. These changes have
not been declared CI-verified. The exact latest HEAD must be tested, not an
earlier ancestor.

### Newly explicit limits

- The instrument identity fixture does not yet model principal schedules,
  contractual maturity ladders, coupon conventions, currency conversion
  dates, accrued interest, market-price versus nominal valuation, collateral
  IDs, guarantees, legal enforceability or ownership shares.
- The SCCE physical audit does not cover money, wages, ownership, finance,
  capital cohorts, water, emissions or a full environmental compartment
  ledger. It is a real-engine physical inventory transition check only.
- Neither component fixture establishes the A2.4.8 cross-register numerical
  closure or permits construction of the unified economic engine.


## 11 November continuation — B8.1 cohort contract hardening

The B8.1 adapter fixture now validates:
- non-negative integer vintage and age (rejecting booleans as integer impostors);
- finite non-negative quantity and service capacity;
- explicit condition, operating, retirement-reason and data-quality domains;
- finite availability, utilization and service-quality coefficients in [0,1];
- immutable material passports with unique material IDs and mass units;
- immutable, unique repair-event identifiers;
- component identity, vintage, age, quantity and material vector;
- finite opening states and finite non-negative transition/addition/retirement/loss quantities.

Adversarial controls reject duplicate material IDs, an unknown condition state,
NaN availability, incomplete component identity and NaN opening stock. This
hardens the specification adapter; it still does not consume a live B8.1
runtime object or prove cohort continuity across the repository's economic
prototype.

Committed at `e71829683744cb52ecee560e2df090988cea8532`. Exact-head audit
workflow run `42905853603` was queued at the last poll. No execution PASS is
claimed.

### Current exact-head state

- Audit branch HEAD: `e71829683744cb52ecee560e2df090988cea8532`.
- Draft PR #4: 85 commits ahead of `main`, 0 behind; 25 changed files.
- Exact-head A2.4 audit workflow run `42905853603`: queued.
- Prototype and Stage-C2 runs visible at the previous head
  `42faf56e895fd5a6c8f74cfaa747f0a2dd0c94ea`: queued.
- No completed exact-head CI logs are available. Do not mark Gate 0 as passed.


### Exact-head refresh after status update

The status note above was committed, producing audit branch HEAD
`a55a6ad66aa3726721945191497290a626f23ccc`. The latest visible CI runs
are attached to its parent code commit `59409a3654934fd7ec2893cdf4325cda090abc26`:
- A2.4 audit controls: `42905879020` — queued;
- Prototype validation: `42905887114` — queued;
- SCCE Stage-C2 validation: `42905887072` — queued.

The newest status-only commit does not alter test code, but exact-head
verification still requires confirming the workflow's tested checkout and
completed result. No PASS is claimed.


## 11 November continuation — A2.4.4 entity/sector identity gap

A source review of `audit_financial_journal.py` found that its `sector` field is overloaded: `BORROWER`, `LENDER` and `SUPPLIER` are participant identities, while `BANK` is an institution role. These are not the controlled six institutional-sector codes used by the SFC position table. The per-holder deposit mirror is a useful component control, but the journal does not yet provide a stable entity ID plus a separately typed institutional-sector membership and issuer/counterparty identity.

Added `A2_4_4_ENTITY_SECTOR_IDENTITY_GAP.md` (commit `b01edd585cff7b3f36d5dd9a5dcbfe31184b82f4`). It defines the minimum entity/sector/issuer/instrument identity contract, entity-level bilateral mirror key, adversarial controls, and the sequence for deriving sector financial net lending only after claim-level reconciliation. The six-sector oracle remains H +7, NFC −19, CB +4, CBank 0, GOV −15, ROW +23; source-unspecified transaction provenance must remain explicitly unresolved.

This is a documented audit finding, not an implemented correction. A2.4.4 remains OPEN; no SFC runtime integration or Gate 1 closure is claimed.

### Current exact-head snapshot

- Audit branch HEAD after the finding document: `b01edd585cff7b3f36d5dd9a5dcbfe31184b82f4`.
- Draft PR #4 remains open and unmerged; canonical `main` remains unchanged.
- Before the finding-document commit, the exact code-head workflow runs were all queued: A2.4 audit controls `42906220504`, Prototype validation `42906225088`, SCCE Stage-C2 `42906225115`. These runs target parent code HEAD `f14488b6a895d49425bc6be248e505ca757fc837`, not the new documentation HEAD.
- The finding document does not alter executable code. No exact-head CI PASS is claimed; current code still requires completed workflow evidence.


## 11 November continuation — cohort service adapter into SCCE

A2.4.2 now has a narrow runtime adapter, not merely a detached cohort
contract fixture:

- `prototype/capital_cohort_bridge.py` validates immutable cohort records,
  stable IDs, cell assignment, vintage/age, physical quantity, service
  capacity, operating state, availability, utilization and service quality.
- It separately aggregates non-retired physical units, operating units and
  capital-service flow for each SCCE cell.
- It maps service flow to the engine's existing dimensionless
  `CellState.capital` multiplier using an explicit per-cell positive baseline.
  It computes and validates every cell before mutating any engine state.
- It rejects zero-service cells because the present SCCE `validate()` requires
  `capital > 0`; it does not silently replace zero by an epsilon.
- `research/audits/.../audit_scce_capital_cohort_bridge.py` constructs
  synthetic cohorts, applies the adapter to an actual
  `DynamicCellularEconomy` instance, checks the production proposal response,
  and executes one real engine period.
- `prototype/test_a2_4_audit_controls.py` now includes this new audit script
  as a thirteenth subprocess test.

The adapter is explicitly a compatibility bridge. The engine still does not
own or evolve asset cohorts; acquisition, ageing, repair completion, component
replacement, retirement and physical-loss transitions are not yet persisted by
the SCCE runtime. The per-cell baseline is synthetic/declared, not empirically
calibrated. A2.4.2 therefore advances from specification-only to
**synthetic runtime-adapter integration**, but remains open.

The exact branch head after these changes is
`b2a3154fec713aa65139cabd813ea6e53926caee`, 98 commits ahead of `main`,
0 behind, with 25 changed files. The new exact-head CI run IDs have not yet
been surfaced by the commit-run query. The preceding exact-head PR runs
`42906225088` (Prototype) and `42906225115` (SCCE Stage-C2) were queued for
the prior code state; they do not verify this adapter. No PASS is claimed.


## 11 November continuation — cohort lifecycle contract and atomic SCCE mapping

A further review found that the first cohort adapter revision had conflated the B8.1 active operating-state vocabulary with final retirement. The adapter now distinguishes:
- active B8.1 states: operating, reserve, diagnostics, repair, remanufacturing and storage;
- a terminal `retired` audit record with a required reason, excluded from current physical stock and capital services.

The new `advance_cohort_period` contract preserves partial transitions by deterministic child-cohort IDs, treats physical loss and final retirement as separate quantity-reducing events, increments age once for surviving active cohorts, leaves new additions at age zero, and prevents reactivation or further events on a terminally retired cohort. A partial retirement fixture checks opening 10 units, retirement 3, closing physical stock 7, a 7-unit active remainder and a 3-unit terminal record. Retired records retain their age at retirement.

The SCCE mapping adapter now preflights every target cell and rolls back prior assignments if a later write fails. A negative control injects a second-cell write failure and verifies the first cell's original capital value is restored. The test also verifies that a cell with zero current service is rejected rather than assigned an epsilon multiplier, because the existing SCCE validator requires positive capital.

The dedicated audit workflow now explicitly executes `audit_scce_capital_cohort_bridge.py`; the existing Prototype unittest wrapper also includes it. This is still synthetic adapter-level integration: the SCCE engine does not yet persist cohort records or call `advance_cohort_period` as part of its normal lifecycle. The declared baseline service flow remains synthetic, and B8.1 material/ownership/component passports are not yet fully mapped into this service adapter.

**Execution status:** committed code and tests are present, but no exact-head CI PASS is claimed. The relevant workflows must complete on the latest branch head and their logs must be inspected. A2.4.2 remains OPEN; A2.4.4 entity/sector identity remains OPEN; Gate 0 is not closed.


### Exact-head CI snapshot — 11 November 2026

Latest branch HEAD at this status update: `9114daeddda6bf408f2e76fc17f5a932e52c1b77`.

The exact-head runs surfaced by GitHub are:
- Prototype validation `42909262122` — **QUEUED**;
- SCCE Stage-C2 validation `42909261882` — **QUEUED**;
- A2.4 audit control fixtures `42909252997` — **QUEUED**.

Each run has a queued job and no assigned runner, conclusion, execution steps or logs. Older runs target ancestor commits and cannot verify the latest changes. No code execution PASS is claimed. The A2.4 workflow now includes the live cohort-to-SCCE adapter script; its exact-head execution is still pending.


### Exact-head refresh — cohort lifecycle and adapter rollback control

Current branch HEAD: `34fc4f9cec9eede409aad1fccf1925a4b194d909`.
Compare with `main`: 117 commits ahead, 0 behind; 28 changed files.

The lifecycle adapter now distinguishes the six active B8.1 states from a
terminal retired audit record. Partial state transitions and retirement create
deterministic child cohort IDs; physical loss removes quantity without being
misclassified as ordinary retirement; active survivors age once; new additions
enter at age zero; terminal retired records are excluded from physical stock
and capital services and cannot be reactivated. The SCCE adapter validates all
cell mappings before mutation and rolls back earlier assignments if a later
cell write fails.

A further negative-control review caught that the initial synthetic rollback
test had used a baseline that generated multiplier 1.0, so its fake setter did
not actually reject a write. The fixture was corrected to generate multiplier
0.5 in both cells, ensuring the second-cell setter raises after the first cell
has changed; the test then checks that both cells return to their original
capital value. This is a test correction, not a production-model change.

Exact current-head PR CI:
- Prototype validation `42909450947` — QUEUED;
- SCCE Stage-C2 validation `42909450934` — QUEUED.

No completed logs are available; no PASS is claimed. The dedicated A2.4
branch-push workflow runs the capital-cohort adapter script, but its completed
exact-head result has not been verified. A2.4.2 remains OPEN and the adapter
remains opt-in; the SCCE period loop does not yet own the cohort register.


## 11 November continuation — entity/sector/issuer identity fixture

A2.4.4's previously documented identity gap now has a separate executable
synthetic control, `audit_entity_sector_journal.py`, wired into the
14-case Prototype wrapper and the branch-push A2.4 workflow.

The fixture:
- separates stable entity IDs from the controlled H/NFC/CB/CBank/GOV/ROW
  sector membership and resolves membership by effective period;
- validates entity, counterparty and issuer identities independently;
- checks entity-level deposit holder/issuer mirrors using the full instrument
  identity, not a sector label;
- validates ten holder claims against ten independently represented issuer
  liabilities, including each side's opening/T/V/O/closing roll-forward;
- derives the sector financial-NL vector only after entity-level mirrors close
  and reproduces H +7, NFC −19, CB +4, CBank 0, GOV −15, ROW +23;
- tests bank origination, existing-deposit transfer, supplier settlement,
  principal repayment, interest accrual/settlement, creditor write-off and
  separate legal forgiveness;
- rejects blank/unknown entity-sector identities, overlapping sector
  assignments, retrospective reassignment, same-sector wrong holder, wrong
  issuer, wrong currency/maturity/denomination/valuation, duplicate claim
  postings/events, missing claim-side records and duplicate holder records.

The write-off event does not extinguish the debtor's legal obligation; the
separate forgiveness event does. Sector totals are not reverse-engineered into
invented event provenance: the six-sector vector remains a separate
entity-level position oracle.

**Status:** the identity interface has a synthetic executable fixture, but
A2.4.4 remains OPEN. The existing journal fixture has not been migrated to this
schema, there is no authoritative entity registry in the economic runtime,
and financial events are not yet the sole source of SFC positions.

Current branch HEAD: `90826603ba4afb9ba3c0a86bdfa8fb4e2b618cb2`;
125 commits ahead of `main`, 0 behind; 29 changed files.

The latest PR CI runs attached to the preceding code commit
`c7b1b3fd6fb64585e581219fb49e5ef41fd60765` are:
- Prototype validation `42910141232` — QUEUED;
- SCCE Stage-C2 validation `42910141028` — QUEUED.

The subsequent commit updates only the finding document. Neither run has
completed or provided logs; no PASS is claimed. The dedicated A2.4 workflow's
exact-head execution also remains unverified.


### Entity-level claim mirror hardening

The A2.4.4 fixture now validates all recognized claim asset/liability pairs
(deposits, loans, trade credit and accrued interest) using the full entity and
instrument identity. A unilateral creditor write-off is the explicit
accounting exception: it changes the creditor's recognized asset but does not
legally extinguish the debtor's obligation. A separate legal-forgiveness event
reduces both sides.

Additional adversarial cases keep the journal globally balanced while
substituting a different loan instrument ID, and keep the closing stock equal
while reclassifying a transaction as revaluation. Both are rejected at the
entity-level claim mirror.

Latest code commit: `72ad94ad403463aededf59612f8bfd95a45e21bf`.
Exact-code-head CI:
- Prototype validation `42910370355` — QUEUED;
- SCCE Stage-C2 validation `42910370770` — QUEUED.

Latest documentation commit: `060462d1a0d186f7bdd13dc68a8eb00c06e7169f`.
No completed logs are available and no PASS is claimed. A2.4.4 remains OPEN;
the fixture is not yet the production financial ledger or authoritative entity
registry.


### Narrowed claim-mirror exception and final entity fixture controls

The entity journal now mirrors every recognized asset/liability claim pair
(deposit, loan, trade credit and accrued interest) by
`(instrument_id, instrument_class, holder_entity_id, issuer_entity_id,
currency, maturity, denomination, valuation_basis)`. The creditor-write-off
exception is tightly constrained to exactly one loan-asset credit and one
equal loss-allowance debit; it cannot be used to bypass mirrors for arbitrary
extra postings. Legal forgiveness remains a separate two-sided claim event.
Unsupported event types are rejected.

The fixture additionally rejects a balanced loan event with a substituted
instrument ID and a position mirror whose closing balance is unchanged but
whose transaction/revaluation split differs.

Latest code HEAD: `3b85dbf0f818f08b0efdb4a20b25f811ac6205ee`;
133 commits ahead of `main`, 0 behind; 29 changed files.

Exact-code-head PR CI:
- Prototype validation `42910616553` — QUEUED;
- SCCE Stage-C2 validation `42910616630` — QUEUED.

Neither job has completed or produced logs. No PASS is claimed. The entity
journal remains a synthetic fixture and A2.4.4 remains OPEN.


## 11 November continuation — durable cohort replay barrier

A code-level audit found that a partial `physical_loss` event was not represented
by a child cohort or persistent tombstone. Since the adapter only rejected
duplicate event IDs within one invocation, replaying the same partial loss in
a later period could subtract the same units again. The period function also
had no durable marker preventing a repeated or skipped period transition.

The cohort adapter now uses an immutable `CohortLedgerState` containing the
closing cohorts, last processed period and previously processed event IDs.
Every transition returns the next state; subsequent calls must consume that
state rather than a bare cohort tuple. Event IDs are unique across the retained
ledger history, and periods must advance exactly one step. Cohort vintages may
not lie after the current period, and additions must enter with the current
period as vintage and age zero. The synthetic integration fixture now checks
partial-loss replay, same-period replay, skipped-period rejection and a
consistent 2021 vintage/period example.

Code commits:
- `62a1873e8ebf062771879169c28462a49cf8b6c4` — durable ledger state and
  cross-period event-ID replay barrier;
- `bafa0f553f3a360f0f7c4fb5b8751d0a0602f007` — period chronology and vintage
  ordering validation;
- `0618d5f2d568313424920d9f796f861e867041a0` — replay and calendar-period
  integration controls;
- `9a5f54050653ab03c1ad68344c9c4c5532db19c0` — repeated/skipped-period
  negative controls.

The returned ledger state must be persisted in full. Saving only cohort rows
would discard the replay barrier. The in-memory state is a prototype contract,
not a crash-safe database or distributed idempotency service; production must
back event uniqueness with the authoritative append-only event store.

**Execution status:** implementation and negative-control source are committed,
but exact-head CI execution is still pending. The current branch's recent
GitHub Actions runs have remained queued without runner assignment or logs.
No PASS is claimed. The cohort adapter remains opt-in; the normal SCCE period
loop does not yet own or persist the ledger. Zero-service capital remains
unsupported by the current SCCE scalar-capital validator. A2.4.2 remains OPEN;
A2.4.8 remains BLOCKED. PR #4 remains Draft and unmerged; `main` is untouched.


## 11 November continuation — split credit creation from deposit transfer

A review of the A2.4.4 entity-journal fixture found that the former
`nonbank_deposit_transfer` example also posted a new non-bank loan asset and
borrower loan liability. Although the aggregate deposit total remained
unchanged, the event label hid a distinct credit-creation transaction. This
was an A2-48 semantic defect in the fixture: deposit neutrality does not imply
credit neutrality.

The fixture now separates the event sequence into:
1. `nonbank_loan_origination`: mirrored loan asset/liability only, with no new
   deposit;
2. `nonbank_deposit_transfer`: holder-to-holder transfer of existing deposits
   with reciprocal bank liability movements, no loan postings and zero net
   change in aggregate deposits;
3. `bank_loan_origination`: mirrored loan asset/liability plus borrower
   deposit asset and bank deposit liability creation for the same amount.

Event-specific checks now validate account composition, posting sides,
amounts, participant/issuer roles and bank-versus-nonbank originator sector
for these three event types. Negative controls reject a mixed non-bank
loan/transfer event and a bank loan origination without deposit creation.
The fixture separately asserts +19 deposit creation for bank origination and
zero deposit-aggregate change for both non-bank loan origination and transfer.

Commit sequence:
- `9136ef1c1c34352822e343bd39a291cc5d1fe40b` — split the E2 loan origination
  from the deposit transfer and enforce event-specific posting contracts;
- `b8d71e723fc1aecaafa5025ee2a16d81618e63be` — add mixed-event and incomplete
  bank-origination negative controls.

**Execution status:** code and controls are committed, but exact-head CI has
not completed. The fixture remains synthetic; the production financial
journal and SFC position register are not yet unified. Other event families
still require explicit posting templates and the entity journal is not yet
the authoritative source of financial positions. A2.4.4 remains OPEN and
A2.4.8 remains BLOCKED. PR #4 remains Draft; `main` remains untouched.


## 11 November continuation — durable A2.4.4 financial event groups

A further reliability review found that the entity journal's event-ID barrier
is scoped to one in-memory `EntityJournal` instance. It does not survive a
process restart. In addition, a multi-event economic transaction could be
persisted in separate calls without a single all-or-nothing storage boundary.

Added a standard-library SQLite prototype:
- `prototype/financial_event_store.py` persists immutable event groups,
  event envelopes and journal postings;
- a stable group ID and optional causation ID link related events;
- event IDs are globally unique within the database;
- identical group replay is idempotent, while changed content under the same
  group ID and event-ID reuse across groups are rejected;
- event envelope, event rows and all posting rows are committed in one
  `BEGIN IMMEDIATE` transaction;
- file-backed storage is required; SQLite WAL mode and
  `synchronous=FULL` are configured and verified; non-finite/non-positive
  lock timeouts are rejected;
- database triggers reject UPDATE/DELETE of committed group, event and
  posting rows;
- integrity verification checks SQLite structure, foreign keys, payload
  hashes, event ordering and the posting-row mirror against the envelope.

Added `audit_financial_event_store.py` and included it in the prototype CI
wrapper, which now executes fifteen separate A2.4 audit scripts. The wrapper
sets `PYTHONHASHSEED=0` and `PYTHONIOENCODING=utf-8` for deterministic,
stable subprocess logs. Negative controls cover restart replay, changed group
payload, global event-ID reuse, binary floating-point amount rejection,
in-memory database rejection, non-finite timeout rejection, immutable rows,
injected mid-write rollback and detection of out-of-band posting corruption.

Commits for this continuation:
- `578bf4ee96faca3a7d44b7a5fdb68e975dc4d2a3` — initial SQLite event store;
- `4ead17d3839edfd09801311b0ecd42eac442ded4` — durable-store adversarial fixture;
- `f187e8c004fb8e522623cc89927fb06c0d67fdf1` — wire store fixture into prototype CI;
- `8b82cf7bc76b38803afb5c40419520496497d66b` — per-connection FULL sync,
  append-only triggers and payload/posting integrity checks;
- `23c01a006264909da2ac116edad53d61a9655da8` — immutable-row negative controls;
- `bd8f823f567a64c4bd85be22cb73244e58c51f52` — durable-store contract and
  production acceptance gates;
- `f9cb598e290c625de87052d0da94d26f34ca9678` — fail-closed integrity handling;
- `ec58bdb52af01173232054effc02d1eef616956e` — out-of-band posting-corruption
  detection;
- `ef1058823a653a0d33a4e959e2c79fa9f5944fb8` — require file-backed SQLite,
  verify WAL/FULL mode and reject invalid timeout values;
- `66cd1fa827636751361b76bed3804ecf507fdb72b` — test invalid persistence
  configuration;
- `229ef9c32d235e9542f2e7400598616d5c778792` — document durability
  prerequisites and configuration controls;
- `0e9db5f1d3538094e3afe11ba29266b115ac5edf` — deterministic UTF-8 CI logs.

**Scope boundary:** the store is a single-host SQLite component prototype. It
is downstream of accounting validation and does not replace
`EntityJournal.post()`. It atomically persists event envelopes and postings,
but it does **not** yet update SFC instrument positions or sector balance
sheets in the same transaction, nor does it provide distributed replication,
production backup/restore, key management or operational controls. It must
not be represented as a production financial ledger.

**Execution status:** the code and CI wrapper are committed. Exact-head GitHub
Actions execution and logs remain pending; no PASS is claimed. A2.4.4 remains
OPEN, A2.4.7 remains OPEN, and A2.4.8 remains BLOCKED. PR #4 remains Draft and
unmerged; `main` remains untouched.
