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


## 11 November continuation — validated journal-to-store adapter

The durable event store previously accepted canonical-looking dictionaries but
did not provide a typed boundary from the validated synthetic entity journal.
That left a critical trust question: could a caller serialize a balanced-looking
payload without first passing the entity/sector/issuer and event-type rules?

Added `prototype/financial_journal_adapter.py`. Its
`append_validated_group()` accepts event objects and an
`EntityJournal`-compatible journal, invokes `journal.post(event)` for every
event before serialization, checks that the journal registered the exact
event and returned equal debit/credit totals, then converts every journal line
to a canonical decimal-string payload. The adapter preserves account, side,
amount, entity ID, institutional sector, counterparty ID/sector, issuer
ID/sector, instrument ID/class, currency, maturity, denomination and
valuation basis.

The adapter treats the batch as one storage group. If validation of a later
event fails, or the SQLite append fails, it removes only the exact event
entries newly added by this adapter call. It does not erase pre-existing
journal entries. The durable store remains responsible for atomic persistence
of the group, events and posting rows.

Added `audit_financial_journal_adapter.py` and a sixteenth case in the
prototype CI wrapper. The adversarial fixture covers:
- valid two-event non-bank credit + deposit-transfer group;
- preservation of entity/sector/issuer/instrument metadata;
- restart replay through a fresh journal object with no duplicate rows;
- rollback of the first in-memory event when the second event fails
  accounting validation;
- rollback of in-memory journal entries when durable posting insertion fails;
- rejection of untyped event dictionaries.

Commits:
- `18607ea5ba82c95b56516d63cdfda5ecfde093a2` — typed adapter;
- `03cdb9708484657930f7de7cd050bca1d6801697` — adversarial adapter fixture;
- `e510b6e57808c4a058041958a864530f848babfe` — add adapter fixture to CI;
- `6b6d84dee888e12a936d62e86f0b8ac5fd78a2bd` — restrict rollback to exact
  adapter-owned event entries;
- `ed3c0dd20db1d41bafbb9466735ba59e7dd508de` — document adapter scope and
  limitations.

**Important limitation:** the adapter invokes the supplied journal's
`post()` method; the prototype test binds it to the canonical synthetic
`EntityJournal`. The adapter does not independently prove the identity of an
arbitrary caller-supplied validator. Production must move the validator and
adapter into a shared runtime module with a non-bypassable call path. The
in-memory journal is not thread-safe; access to one instance must be
serialized. This adapter still does not update SFC instrument positions or
sector balance sheets.

**Execution status:** code and sixteenth CI wrapper case are committed. The
latest exact-head CI has not produced runner steps or logs; no PASS is claimed.
A2.4.4 remains OPEN, A2.4.7 remains OPEN and A2.4.8 remains BLOCKED. PR #4
remains Draft/unmerged; `main` remains untouched.


## 11 November continuation — event ordering and concurrent writer controls

A deeper review of the new durable store found that the first integrity checker
used SQLite `rowid` to reconstruct event order. Rowid is an implementation
detail, not a durable business-order key; a rebuild or VACUUM must not silently
change the canonical order of events inside a transaction group.

The store schema is now version 2:
- each event persists an explicit `event_index`;
- a unique constraint/index prevents duplicate positions within one group;
- integrity verification orders by `event_index` and requires contiguous
  indexes from zero;
- journal-line verification also checks contiguous `line_no` values;
- a transactional v1-to-v2 migration assigns explicit indexes in the
  pre-migration rowid order and restores the append-only update trigger.

The financial event-store audit now additionally tests:
- two concurrent connections delivering the same group: exactly one insert
  and one idempotent replay;
- two concurrent groups racing to claim the same event ID: exactly one
  succeeds and the other is rejected;
- migration from a synthetic version-1 database while preserving group event
  order and verifying the migrated envelope.

The contract also records the SQLite WAL-reset defect and its fixed releases:
production multi-connection writers must use SQLite 3.51.3+ or a patched
backport (3.50.7 / 3.44.6), and WAL must not be placed on a network filesystem.
The runtime SQLite version must be recorded before enabling concurrent
production writers.

Commits:
- `eb4db296df03cc5aee8dcaeb15910e966b745985` — concurrent replay and
  cross-group event-ID race controls;
- `13bd9db98ebb4885fcfd5cffbb79bd6ef53232e4` — explicit event order and
  schema-v2 migration;
- `285a118aa7f2f6923f7d53470318a2c15ef76b8d` — migration/order test fixture;
- `17a66974dd27e452f11b17af54c58457632b2aa2` and
  `bbf622988902b5b4beb7df34739e14683ed21a89` — integrity query corrections
  to use stable event indexes while preserving legacy migration order;
- `7cd1d156779685eba13b9e80084fe3bad3c8e007` and
  `f8026a40eec3bdedd7020bdb507cfd12e702093b` — contract updates for
  concurrency, SQLite WAL compatibility and schema migration.

**Execution status:** these controls are committed but have not been observed
running to completion. The latest GitHub jobs remain queued without runner
steps or logs; no PASS is claimed.


A final schema-initialization edge case was added to the same control: if an
older initializer created the version-1 `events` table but crashed before
writing `PRAGMA user_version=1`, the new initializer now inspects the actual
table columns and routes that database through the v1-to-v2 migration. The
audit fixture exercises both explicitly stamped v1 and unstamped v1-layout
databases. This prevents a partial old initialization from being mislabeled
as a fresh v2 database.


## 11 November continuation — period-scoped financial claim identity

A2.4.4 source review found that the synthetic entity-level claim key omitted
`effective_period`. That made repeated instrument positions across periods
ambiguous and could allow a holder record from one period to be compared with
an issuer record from another.

The claim key now includes the effective period. The entity-sector journal
fixture adds controls proving that:
- one instrument can have separate mirrored positions in successive periods;
- cross-period holder/issuer records do not match;
- sector financial net lending cannot silently sum transactions across
  multiple periods and requires an explicit period selector;
- period-scoped aggregation remains correct for one-pass iterables.

Code commits:
- `e541162c55c4bb15df1b4984164e644290118b1c` — add effective period to
  claim identity and add multi-period mirror controls;
- `3bf45c8fa446a086bc104a63ea27d1897da677ac` — make period-scoped net-lending
  aggregation safe for iterables and add a generator control.

**Limit:** this does not yet enforce closing-to-opening continuity between
successive periods, derive the positions from the durable event store, or
integrate with the SFC runtime. It is a synthetic fixture hardening only.
No exact-head execution PASS is claimed. A2.4.4 remains OPEN and A2.4.8
remains BLOCKED; PR #4 remains Draft/unmerged and canonical `main` untouched.


The dedicated A2.4 branch-push workflow has also been extended to execute
`audit_financial_event_store.py` and `audit_financial_journal_adapter.py`
directly. Previously those two new A2.4.4 controls were included in the
prototype PR wrapper but omitted from the dedicated branch-push audit job.
This is workflow wiring only; no execution result is inferred from the edit.


## 11 November continuation — remaining cross-register gap audit

Added `A2_4_REMAINING_CROSS_REGISTER_GAPS.md` after a source-level review of
the exact branch head `24a8d0b4e5c9f740857395b1c7b9f1044e05bf3f`.

New finding: the entity/sector claim fixture is period-aware, but the separate
instrument stock-flow `Position` / `IssuerLiability` records and mirror key
still lack `effective_period`. The component control therefore does not yet
prove period-scoped holder/issuer identity or closing-to-opening continuity
across successive periods.

The audit also records the remaining authority boundary between the durable
SQLite event store, the supplied synthetic journal validator, and SFC position
and sector-balance projections; the missing contract-level debt lifecycle;
the B8.1 production lifecycle and valuation gap; the B2/B3 runtime binding;
labour/consent rights controls; and the distinction between exploratory
synthetic experiments and prospective confirmatory evidence.

The new document specifies acceptance criteria for SFC-GOLD-1/2, an independent
oracle, crash/replay recovery, full multi-register period closure and Gate 0–4.
It does not claim that these controls are implemented or passed.

Exact-head CI at the time of audit:
- Prototype validation `42926000574` — QUEUED;
- SCCE Stage-C2 `42926000400` — QUEUED;
- A2.4 audit controls `42925993756` — QUEUED.

No completion logs or PASS evidence were available. PR #4 remains Draft and
unmerged; canonical `main` remains untouched. A2.4.4 and A2.4.7 remain OPEN;
A2.4.8 remains BLOCKED.


## 11 November continuation — period-scoped instrument stock-flow controls

A second A2.4.4 review found that the standalone instrument stock-flow
component still treated positions as timeless records, even after the
entity-sector claim fixture had become period-aware. This gap is now addressed
at the synthetic component-control level in
`audit_instrument_stock_flow.py`:

- `Position` and `IssuerLiability` carry a positive integer
  `effective_period`;
- the holder/issuer mirror key includes the effective period, preventing
  cross-period substitution;
- `validate_period_continuity` aggregates holder records by full instrument
  identity and requires the closing stock of each observed period to equal
  the opening stock of the immediately following period;
- a missing intervening period and a closing/opening discontinuity are
  rejected rather than silently bridged;
- financial net lending rejects implicit aggregation across multiple periods
  and requires an explicit period selector;
- negative controls cover cross-period mirror mismatch, continuity failure,
  skipped periods, zero/invalid period identity, multi-period aggregation and
  one-pass iterable selection.

Implementation commits:
- `10700ef008d429f21b42abf3c5c81fe66f7d264e` — add effective-period fields,
  period-scoped mirror identity, continuity validator and explicit NL period
  selection;
- `1e13fd0e935e9896aaabc64debd24f3453963cd9` — add multi-period continuity,
  mirror and aggregation controls;
- `67642fb6fa78c07f70d503e203e5caf41f92e855` — tighten the skipped-period
  negative control.

**Evidence boundary:** this closes the previously identified *source-level
gap in the isolated instrument stock-flow fixture only*. The records are still
synthetic inputs. The validator is not yet fed from the durable SQLite event
store, does not define typed boundary/restatement events, and is not wired into
the production SFC runtime or an atomic multi-register projection. The new
negative controls have not yet been observed completing in GitHub Actions.
No test PASS, A2.4.4 closure, Gate 0/1/2 closure, or production readiness is
claimed.

At the time of the latest poll, the three workflows on the previous exact
HEAD `b6360df9db51ba0681cf180201ff4df3706637da` were still queued:
- Prototype validation `42930563436`;
- SCCE Stage-C2 validation `42930563291`;
- A2.4 audit control fixtures `42930555633`.

Those runs predate the three implementation commits above and cannot validate
the new code. A fresh exact-HEAD run set is required. PR #4 remains Draft and
unmerged; canonical `main` remains untouched. A2.4.4 and A2.4.7 remain OPEN;
A2.4.8 remains BLOCKED.


A final fail-closed refinement in commit
`9e2edbe5f60a3b89e1dbfd4def2315c190378f86` makes the continuity validator
reuse the canonical full-instrument identity validation and validates every
period before financial-NL selection. This prevents malformed/blank identity
dimensions or invalid periods from bypassing the new checks. This is source
hardening only; execution remains pending.


## 11 November continuation — SFC-GOLD-1 frozen corpus and independent oracle

A first narrow SFC-GOLD-1 corpus is now committed as a data-only JSON fixture,
with a separate arithmetic oracle. The frozen case covers:
- bank loan origination creating matching loan and deposit positions;
- supplier payment transferring an existing deposit without increasing
  system-wide deposits;
- principal repayment reducing matching borrower/bank loan and deposit
  positions.

The expected final values are frozen in the corpus: bank loan asset 14,
household loan liability 14, household and supplier deposit assets 7 each,
matching bank deposit liabilities 7 each, system deposits 14 on both sides,
and sector financial net lending CB=0, H=-7, NFC=+7 (aggregate zero).

The independent oracle does not import EntityJournal, the SQLite event store,
the journal adapter, SFC runtime projections or other audit fixtures. It
independently checks decimal-string amounts, frozen entity/sector membership,
event-type account composition, double-entry equality, event-level
holder/issuer mirrors, closing instrument balances and sector financial net
lending. Negative controls mutate holder identity, instrument identity,
sector assignment and event type, and attempt duplicate event delivery.

Files:
- `SFC_GOLD_1_CORPUS.json` — frozen input and canonical expected output;
- `SFC_GOLD_1_CONTRACT.md` — scope, independence boundary, exclusions and
  acceptance criteria;
- `audit_sfc_gold_oracle.py` — standalone independent arithmetic oracle.

CI wiring:
- `prototype/test_a2_4_audit_controls.py` invokes the oracle as a subprocess;
- `.github/workflows/a2-4-audit-controls.yml` executes the oracle directly.

Implementation commits:
- `03127b356c287ed4130bc4bfeb9edee5440ae14b` — initial frozen corpus;
- `a648cb08dec7b583e960e75bc71d621a1f6db103` — corrected frozen sector
  net-lending vector;
- `4fd35589326357db969a2ee7b58a8ecc5ba037c5` — independent oracle;
- `c0fb004f9d5325c13ff69b1d7d6af4527f71272f` — oracle output correction;
- `70690751e2b1a19e88337831ac5712239b4148d1` — Prototype wrapper wiring;
- `01ac4a0f3fcfed8e6f82104d96badd8a57450ee3` — dedicated A2.4 workflow
  wiring;
- `560527cdc17cd13babf2ddbd66d02f00cae51eb7`,
  `30038ddf4f0002fd9de622bb74d0f0a7db4b6f11` and
  `64e43efe9b73ed5e2ab8c810fc66946188f262f1` — oracle hardening and
  negative-control corrections;
- `45861ff0d39cced16a2314fcdc40ad01d77a8a08` — SFC-GOLD-1 contract.

**Evidence boundary:** source and CI wiring are committed, but no execution
PASS is claimed until the exact-head workflows complete and their steps/logs
are reviewed. SFC-GOLD-1 v1 is intentionally single-period and excludes
interest, valuation, impairment, write-off, legal forgiveness, collateral,
guarantees and multi-period event-store projection. It is Gate 1 groundwork,
not closure of Gate 0/1/2, A2.4.4 or A2.4.8. PR #4 remains Draft/unmerged;
canonical `main` remains untouched.


## 11 November continuation — SFC-GOLD-1 cross-leg economic role hardening

A source review of the independent oracle found a semantic gap: the first
version enforced per-event debit/credit equality, full holder/issuer mirrors,
and event-specific account-side cardinality, but did not fully bind the
borrower, lending bank, deposit holder and deposit issuer across different
legs of the same event. Local balance and mirror equality alone are not
sufficient to prove that the event describes the intended economic operation.

The oracle now has independent cross-leg role invariants for all three v1
event types:

- **Bank loan origination:** the bank is the loan creditor and deposit issuer;
  the borrower is the loan-liability holder/issuer and new deposit holder;
  loan and deposit instrument classes are distinguished; loan/deposit
  currencies match within the no-FX v1 boundary.
- **Supplier payment:** payer and supplier are distinct deposit holders;
  both deposits and their mirrored bank liabilities belong to the same
  issuing bank; holder/counterparty directions are checked.
- **Principal repayment:** the borrower, lending bank, loan claim, borrower
  liability, borrower deposit and bank deposit liability are cross-linked;
  instrument classes and no-FX currency consistency are checked.

Two adversarial controls were added. The cross-leg borrower mutation changes
the deposit asset holder and mirrored liability holder together, preserving
the deposit mirror and event-wide debit/credit totals while making the
deposit recipient differ from the loan borrower. The instrument-class
mutation changes both mirrored loan legs together, preserving their mirror
while misclassifying loan accounts as deposits. Both must be rejected by the
role validator.

Implementation:
- `0ff4f68bba2214818b2dab6d2e7ec5f1beeb74c4` — cross-leg economic role
  invariants and two additional negative controls.

**Evidence boundary:** this is a source-level hardening change only. The
oracle has not yet been executed locally or in a completed CI job. The corpus
remains synthetic, single-period and intentionally excludes FX conversion,
interest, revaluation, impairment, write-off and legal forgiveness.

### Exact-head CI observation

At the time of this update, branch HEAD before the documentation commits was
`0ff4f68bba2214818b2dab6d2e7ec5f1beeb74c4`. The three latest runs observed
on the prior HEAD `5fc6211057cd0d908c3178461a57ecb8a1caaa8a` remained
`queued` with no runner steps or logs:

- Prototype validation: `42935841261`;
- SCCE Stage-C2 validation: `42935841192`;
- A2.4 audit control fixtures: `42935834629`.

These runs cannot validate the new oracle hardening commit. Earlier queued
runs on `55e523db2eb84297962272a7d35fddf2cc082309` are also stale. No PASS
is claimed. A fresh exact-HEAD run set and completed logs are required.
PR #4 remains Draft/unmerged; canonical `main` remains untouched.


### Follow-up hardening — frozen v1 sector roles and instrument separation

The role validator is tightened to the actual frozen SFC-GOLD-1 v1 scope:
- the bank role must be sector CB;
- the loan borrower and payment payer must be sector H;
- the supplier recipient must be sector NFC;
- loan and deposit instruments must be distinct;
- payer and supplier deposit instruments must be distinct.

A new adversarial mutation changes the bank entity's sector and every matching
posting/related-sector label consistently. This preserves the entity registry
mapping and balanced journal structure, but must fail because the v1 bank role
is constitutionally represented by the CB sector in this frozen corpus.

Source commit: `507a9d318d9b4218201359324d5713a7b0ce90da`.

This narrows the oracle to its declared fixture, rather than claiming a
general-purpose bank/household ontology. No execution PASS is claimed.


## 11 November continuation — repository checkpoint after role hardening

The current source sequence is:
- `0ff4f68bba2214818b2dab6d2e7ec5f1beeb74c4` — cross-leg economic role
  invariants and borrower/class negative controls;
- `507a9d318d9b4218201359324d5713a7b0ce90da` — frozen CB/H/NFC role
  constraints, distinct instrument checks and coordinated bank-sector
  mutation;
- `d4a074b44f675e18389e3487e1b753e822a9c71a` — adversarial-control comment
  numbering cleanup.

The branch was observed at `d4a074b44f675e18389e3487e1b753e822a9c71a`;
PR #4 metadata reports 214 commits, 38 changed files, Draft/Open/unmerged.
Canonical `main` was not modified. The PR description still contains older
embedded branch/commit counts; the live branch ref and PR head SHA are the
authoritative values.

The most recent complete three-workflow set observed was created on
`b2316f612428425279bc04d0d06c60c13ac927b0`:
- Prototype validation `42939243472`;
- SCCE Stage-C2 validation `42939243466`;
- A2.4 audit control fixtures `42939239075`.

All three runs and jobs were `queued`, with null conclusion, no start or
completion time, zero runner steps and no execution logs. A previous full
three-workflow set on source commit
`507a9d318d9b4218201359324d5713a7b0ce90da` is likewise queued:
Prototype `42939215258`, Stage-C2 `42939215333`, A2.4
`42939208541`. These runs do not validate the final branch HEAD. No PASS is
claimed; the current exact-head run set must be polled independently.

The queue pattern is now repeated across many successive commits and
workflows. It is evidence of a runner/dispatch backlog before job execution,
not evidence of test success or failure. The available job records do not
expose a root cause. Do not weaken tests or alter workflow semantics to make
the queue appear green.


## 11 November continuation — SFC-GOLD-1 sequential stock/replay hardening

A second semantic review found that event-local balance and mirror equality
could accept a set of individually valid events in an economically impossible
order, or an over-sized repayment whose final aggregate might conceal a
negative intermediate position. The independent oracle now adds a sequential
stock boundary for the deliberately narrow v1 corpus.

New source controls:
- validates corpus identity/version/status and its single declared positive
  effective period;
- requires every event to use that declared period;
- requires posting counterparties and issuers to be registered;
- maintains an instrument identity catalog keyed by instrument ID and rejects
  changes in class, currency, maturity, denomination, valuation basis,
  holder or issuer across events;
- applies each event's position deltas only after event balance and claim
  mirror checks;
- rejects any negative intermediate position after each event. This is an
  explicit v1 fixture assumption: no opening stock and no overdraft facility;
- treats the frozen event array order as the canonical replay order.

Four additional adversarial controls reject:
1. an over-sized but locally balanced principal repayment;
2. repayment replayed before loan origination;
3. reuse of an instrument ID with a changed maturity in later events;
4. moving events to a period absent from the frozen corpus declaration.

The existing event-level mirror, role, sector, class and duplicate-delivery
controls remain in place. This brings the independent oracle to twelve
adversarial mutation cases.

Implementation:
- `d39beab79ef988164ac544ea31964d5552c17d84` — sequential stock, declared
  period, instrument catalog and replay-order controls;
- `a458198e3d815764e916ea6ad659171671988b53` — final review of the new
  source and mutation paths;
- the following commit normalizes mutation numbering and output wording.

**Evidence boundary:** source review only. No local execution or completed
exact-head CI PASS is claimed. The no-negative-stock assumption is limited to
this synthetic v1 fixture and must not be generalized to overdraft-capable
deposit systems or ledgers with signed opening positions.


### Exact-head CI checkpoint after sequential replay hardening

At branch HEAD `59fb367f08e243d060ed2f3b8d9534e649dfe708`, all three
required workflows were present for the same exact SHA:
- Prototype validation `42940078569`;
- SCCE Stage-C2 validation `42940078414`;
- A2.4 audit control fixtures `42940074232`.

All three runs were `queued`; their jobs had no conclusion and zero executed
steps. No logs or artifacts existed at the time of inspection. This is a
complete exact-SHA *dispatch set*, not an execution result. No PASS is claimed.

The source was reviewed from the GitHub branch after commit. The oracle
contains twelve adversarial rejection calls, including sequential overpayment,
out-of-order replay, changed instrument identity and undeclared-period
mutations. The script has not been executed locally in this environment; CI
must execute it before its printed PASS line can be treated as evidence.


## 11 November continuation — SFC-GOLD-1 event-boundary replay checkpoints

A further independent arithmetic review identified a remaining weakness in
final-state-only gold assertions: locally balanced events and a correct final
position vector do not, by themselves, freeze the expected allocation after
each event. A later event could reverse an earlier misallocation and conceal
the intermediate defect.

The frozen corpus has therefore been advanced to **SFC-GOLD-1 v1.1.0** while
preserving the same three event semantics and single-period scope. It now
contains canonical expected position snapshots after:
- G1-E1 bank loan origination: loan 19 and household deposit 19;
- G1-E2 supplier payment: loan 19, household deposit 12, supplier deposit 7;
- G1-E3 principal repayment: loan 14, household deposit 7, supplier deposit 7.

The independent oracle records its running positions after every complete
event and compares each checkpoint to the corpus-authored expected positions.
It still separately checks debit/credit equality, cross-leg economic roles,
holder/issuer mirrors, instrument identity immutability, non-negative
intermediate stocks, final balances, system deposit equality and sector
financial net lending.

Files changed:
- `SFC_GOLD_1_CORPUS.json` — version 1.1.0 and three frozen replay snapshots;
- `audit_sfc_gold_oracle.py` — checkpoint capture and independent comparison;
- `SFC_GOLD_1_CONTRACT.md` — checkpoint semantics and limits.

Implementation commits:
- `efbf39726f8ad2b8a2677535318cf16191d1e239` — freeze v1.1.0 event
  checkpoints;
- `9c128837325e017fcf9fd90b92edc1f0e95d04ab` — compare every replay
  checkpoint in the independent oracle;
- the following documentation commit records this extension.

**Evidence boundary:** source and frozen expected-data review only. The oracle
has not been executed locally in this environment, and no completed exact-head
CI PASS is available. The v1.1.0 checkpoints are synthetic expectations, not
empirical observations or proof of production runtime integration. SFC-GOLD-1
remains single-period and excludes opening stocks, overdrafts, interest, FX,
valuation, impairment, write-off and legal forgiveness.

The three latest known CI runs on the preceding HEAD
`19e5a3abc3a955c62a6867ad524fd5d8be8cf096` were still queued with zero
executed steps and no logs. They do not validate the v1.1.0 changes. A fresh
exact-head dispatch set and completed logs are required. PR #4 remains
Draft/Open/unmerged; canonical `main` remains untouched. A2.4.4 remains OPEN
and A2.4.8 remains BLOCKED.


### Frozen expected-output integrity control

Added a thirteenth negative control to the independent oracle. Unlike the
twelve event-input mutations, this control corrupts a corpus-authored
intermediate replay expectation while leaving the event stream unchanged.
The expected-output comparison must reject it. This guards against a
checkpoint fixture that is present but accidentally not asserted.

The oracle now reports twelve event mutations plus one frozen-expectation
tamper control. Source review only; exact-head CI execution remains pending.


## 11 November continuation — SFC-GOLD-1 v1.1 and event-store replay boundary

### Frozen gold-corpus progress

The SFC-GOLD-1 corpus is now version 1.1.0. It retains the three-event
synthetic loan/payment/principal-repayment lifecycle and adds corpus-authored
expected position snapshots after each event boundary:
- G1-E1: four positions after loan origination;
- G1-E2: six positions after supplier payment;
- G1-E3: six closing positions after principal repayment.

The independent Decimal oracle now captures the running positions and
compares every checkpoint against those frozen expectations. It retains the
twelve adversarial event mutations and adds a thirteenth negative control
that corrupts a frozen intermediate expectation while leaving the event
stream unchanged. The control must be rejected by the independent expected
output comparison.

Relevant source commits:
- `efbf39726f8ad2b8a2677535318cf16191d1e239` — v1.1.0 corpus checkpoints;
- `9c128837325e017fcf9fd90b92edc1f0e95d04ab` — oracle checkpoint capture
  and comparison;
- `df30d7799a7c03adc442a5676b5bc28061a3cf2a` — frozen-expectation tamper
  negative control;
- `e26485ad554a13d411cdeefe81c833b08012889a` — documentation of the
  checkpoint/tamper control.

### Durable event-store review — new blocking finding

A source-level review of `prototype/financial_event_store.py`,
`prototype/financial_journal_adapter.py` and their audit fixtures confirms
that the prototype already implements valuable local controls:
- SQLite WAL with FULL synchronous mode;
- atomic append of one group, its events and postings;
- group-payload hash and immutable replay conflict checks;
- global event-ID uniqueness;
- explicit event_index within a group;
- append-only database triggers;
- same-group idempotent replay;
- rollback on injected mid-write failure;
- restart/reconstruction, concurrency and schema-v1 migration fixtures;
- typed journal adapter that validates before durable append and rolls back
  adapter-owned in-memory journal mutations on failure.

This is **not** yet deterministic system-wide replay. Schema v2 stores
`event_index` only within a group; it has no immutable cross-group
`commit_sequence`, and the public API has no ordered all-groups iterator.
Sorting group IDs, timestamps or implicit SQLite rowid would not establish
economic chronology. The current adapter also does not atomically update SFC
instrument positions, sector balance sheets or a projection cursor.

A new evidence-backed design/gap document was added:
`A2_4_4_EVENT_REPLAY_AND_PROJECTION_RECOVERY_GAP.md`.

It specifies:
1. separation of effective accounting period from database-assigned immutable
   commit_sequence;
2. canonical order `(commit_sequence, event_index)`;
3. explicit handling of populated v2 stores whose historical cross-group
   chronology cannot be recovered from existing fields;
4. a single-database transaction coupling event append, SFC projection deltas
   and applied-through cursor, or a separately specified idempotent inbox;
5. deterministic rebuild from explicit opening snapshots with per-event
   checkpoints and independent reconciliation;
6. twelve adversarial tests for ordering, concurrency, retry, crash boundaries,
   sequence tampering, backdated periods and rebuild equivalence.

The durable event-store contract was updated to link this finding.

**Gate state:** local group append is source-implemented; cross-group canonical
replay order is OPEN; durable SFC instrument/sector projections are OPEN;
crash-safe projection cursor and exactly-once effect are OPEN. A2.4.4 remains
OPEN and A2.4.8 remains BLOCKED.

### Exact-head CI observation

At prior HEAD `e26485ad554a13d411cdeefe81c833b08012889a`, the three required
workflows were dispatched on the same SHA:
- Prototype validation: `42940522884`;
- SCCE Stage-C2 validation: `42940522921`;
- A2.4 audit control fixtures: `42940516883`.

All three were queued, each job had zero executed steps, and no completion
logs or artifacts were available. These runs do not constitute PASS and do
not validate subsequent documentation commits. A fresh exact-head set and
completed job logs are required.

**Evidence boundary:** source review and frozen synthetic expectations only.
No local execution is claimed in this environment. No completed CI PASS,
production event-store integration, crash recovery, exactly-once projection
effect, empirical SFC evidence or production readiness is claimed. PR #4
remains Draft/Open/unmerged; canonical `main` remains untouched.


## 11 November continuation — SFC-GOLD-1 v1.2.0 identity-safe expectations

A deeper review of the new frozen expected-output assertions found a subtle
test-oracle weakness: dictionary construction could silently collapse
duplicate expected position keys, and the expected liability-holder metadata
was not compared against the oracle's instrument identity catalog. The event
input itself could be correct while the gold expectation's holder label was
tampered without detection.

The corpus has been advanced to **SFC-GOLD-1 v1.2.0**. Every final-position
and per-event checkpoint row now freezes both:
- `holder_entity_id`;
- `issuer_entity_id`.

The independent oracle now:
- returns its instrument identity catalog as an independently derived result;
- compares expected holder and issuer to the catalog for every frozen
  position;
- rejects duplicate keys in final-position and checkpoint lists rather than
  allowing dictionary overwrite;
- requires expected balances to be finite, positive decimal strings;
- requires the closing expected instrument set to match the oracle's
  instrument catalog for this deliberately narrow v1 fixture.

New expectation-integrity controls:
13. tampered intermediate checkpoint balance;
14. tampered expected deposit holder;
15. duplicate frozen final-position key;
16. duplicate frozen checkpoint-position key.

The oracle now has twelve adversarial event-input mutations plus four
frozen-expectation integrity controls. These are source-implemented controls,
not executed test results.

Relevant commits:
- `2fb1f0493d53815ac74c822850072cfb7721d9a6` — v1.2.0 frozen holder and
  issuer metadata on final and intermediate expected positions;
- `558ee1841eae2be9eae108802878032db371302f` — identity-aware expected
  position validation and additional negative controls;
- `d1157ff43e35e2e677312a4c25360f834c64680c` — strict decimal-string
  validation for frozen expected balances;
- accompanying contract and status commits record the changes.

**Evidence boundary:** source inspection only; no local oracle execution and
no completed exact-head CI PASS are claimed. The gold corpus remains
synthetic, one-period and narrow in instrument/event scope.


### Exact-head CI checkpoint after v1.2.0 identity hardening

At branch HEAD `f2c9411e6b57fa1a70d77c6576f86a1e6a52c46a`, all three
required workflow runs and check-runs were confirmed on that exact SHA:
- Prototype validation: `42941151969`;
- SCCE Stage-C2 validation: `42941152141`;
- A2.4 audit control fixtures: `42941144742`.

Each workflow job was still `queued`, with null conclusion and zero executed
steps. No execution logs or artifacts were available. This is an exact-SHA
dispatch set only; no PASS is claimed. A subsequent status-only commit will
change HEAD and therefore requires a new exact-head CI observation.


## 11 November continuation — schema v3 durable cross-group commit order

The financial event store now has a schema-v3 global ordering primitive:
event_groups.commit_sequence. The value is assigned under the same
BEGIN IMMEDIATE transaction as the group, events and postings; identical
replay does not consume a sequence. iter_groups() exposes canonical durable
group order. The integrity checker verifies a gap-free sequence 1..N.
effective_period remains independent and is not used as a commit-order key.

Legacy migration is fail-closed:
- empty v2 and single-group populated v2 stores can be upgraded;
- populated v2 stores with multiple groups are rejected because their
  historical cross-group order is not recoverable from schema v2;
- v1 migration is also rejected when multiple groups exist;
- a one-group legacy store receives sequence 1 without fabricating a
  multi-group chronology.

The audit source adds controls for backdated periods, idempotent replay
sequence stability, concurrent distinct group commits, sequence tampering,
and ambiguous populated-v2 migration rejection. Source controls are
implemented; exact-head execution remains pending.

**Gate update:** durable single-store cross-group commit ordering is now
source-implemented. Projection state, applied-through cursor, crash-safe
projection recovery and exactly-once projection effect remain OPEN. A2.4.4
remains OPEN; A2.4.8 remains BLOCKED. No production integration or empirical
economic validation is claimed.


### Additional migration recovery control

A final schema-initialization review found that the prior crash-recovery
detector recognized unstamped v1 layouts but not an unstamped v2 layout
(event_index present, user_version still zero). The initializer now identifies
that layout as v2 and applies the same ambiguity guard. Audit source now covers
stamped and unstamped multi-group v2 rejection and successful one-group v2
migration to sequence 1. Source implementation is committed; exact-head CI
execution is still pending.


## 11 November continuation — SFC projection protocol design

A dedicated specification was added:
A2_4_4_SFC_PROJECTION_PROTOCOL_SPEC.md.

The design prohibits inferring SFC stock changes from debit/credit signs
alone. A projection delta must name its event, effective period, complete
instrument identity, holder, issuer, sectors, currency, maturity,
denomination, valuation basis, T/V/O component, signed decimal-string amount
and frozen opening stock. Projection data must be bound into the immutable
group payload so a retry with changed projection economics is a conflict.

The target atomic unit is event group + journal postings + immutable
projection deltas + materialized holder positions + coverage marker +
applied-through cursor in one SQLite transaction. Projection activation
requires an explicit opening snapshot before the first event group; existing
histories cannot be silently backfilled. Empty delta lists explicitly cover
groups with no SFC stock effect; missing projection data blocks the prefix.

Issuer aggregates derived from holder positions are not an independent
issuer-liability register. Separate issuer-side evidence and reconciliation
remain mandatory.

**Implementation status:** protocol design recorded; schema-v4 projection
code and projection audit fixtures are NOT yet committed. This is a design
milestone, not implementation or execution PASS. A2.4.4 remains OPEN;
A2.4.8 remains BLOCKED.


### Additional schema-v3 interrupted-initialization control

A final migration-path inspection found that the zero-user_version recovery
branch distinguished v1 from later layouts by event_index but did not inspect
whether event_groups already had commit_sequence. A v3 store interrupted
before user_version stamping could therefore be misclassified as v2 and
attempt to add an already-existing column. The initializer now distinguishes
v2 and v3 by the event_groups column set. The audit fixture clones a migrated
v3 store, clears user_version, reopens it, and verifies sequence preservation,
integrity and schema version restoration. This is source-level implementation;
exact-head CI execution remains pending.


### Audit-fixture transaction durability correction

A source-level review found that several SQLite fixture setup/tampering blocks
used `contextlib.closing` without explicitly committing their writes.
`closing` closes the connection but does not commit an open transaction;
uncommitted DML is rolled back on close. This made legacy fixture population,
single-group v2 fixture pruning, and two out-of-band corruption injections
non-durable. In particular, the migration and integrity assertions could
otherwise run against empty or unmodified fixture state rather than the
intended adversarial database.

The audit fixture now explicitly commits:
- v1 legacy group/event/posting rows and their schema-version marker;
- the two populated v2 legacy groups;
- deletion of the second group when deriving the single-group v2 fixture;
- user_version reset on copied v2 and v3 stores;
- commit-sequence tampering after dropping the immutability trigger;
- the injected extra journal-line row used by the integrity checker control.

This is a correction to the test harness, not a change to event-store
production logic. It makes the existing migration and tamper assertions
exercise durable database state. The audit fixture has not yet been executed
on this revised HEAD; exact-head CI remains the required execution evidence.
A2.4.4 remains OPEN and A2.4.8 remains BLOCKED.


Correction commits:
- `fee6898457142e583f98bd9b29a740320b2bcb30` — explicit commits for v1/v2
  fixture setup, v2 pruning, tamper writes and injected posting corruption;
- `8b963340f401aac17c00e9d471263e2c37d1a429` — explicit commit for copied
  unstamped-v3 fixture metadata;
- `6ab4154de80fda017b79ade0261d9e4d3a7d28a1` — initial status record.


## 11 November continuation — schema v4 event-order hash chain

A further integrity review found that schema v3's gap-free sequence check
could not detect a permutation of existing sequence numbers: changing
`1,2` to `2,1` preserves the set `{1,2}`. The database triggers reject
ordinary updates, but the existing integrity checker did not detect this
out-of-band change if an operator disabled the trigger.

The event store is now source-updated to schema v4:
- Each group stores `previous_group_hash` and `group_chain_hash`.
- The group-chain hash binds commit sequence, group ID, immutable group
  payload hash and predecessor hash using canonical JSON and SHA-256.
- Chain metadata is appended in the same `BEGIN IMMEDIATE` transaction as
  the event group, events and journal postings.
- `integrity_check()` validates the genesis link, every predecessor and every
  recomputed chain hash, in addition to gap-free sequence and event/posting
  mirrors.
- The v2 migration now stamps schema v3 first, then applies the v3-to-v4
  chain migration; it does not skip directly to v4 without chain columns.
- The v3-to-v4 migration drops and reinstates the group update trigger inside
  one transaction so existing append-only protection does not block backfill.
- Recovery fixtures distinguish interrupted v3 migration from an unstamped
  v4 layout.
- A new adversarial fixture swaps two sequence numbers while preserving the
  contiguous set `{1,2}`; integrity must reject the reordered chain.

The dedicated A2.4 workflow now also triggers when any file under
`prototype/**` changes, so edits to production code exercised by the audit
scripts cannot silently bypass that workflow's path filter.

**Trust boundary:** the chain is local tamper evidence, not an external
cryptographic anchor. A privileged actor who rewrites the entire database and
recomputes all links can replace the history. External signed checkpoints or
independent anchoring are required to detect a full-database rewrite.
Migration seals the v3 order visible at migration time and cannot prove that
the legacy order was never changed before migration.

Implementation/test commits:
- `42f0df86ac570064074554107f6d94c65d07f62c` — initial schema-v4 chain
  implementation;
- `ea449e3ac514fcd9899c6861f9df939ac8fad3b1` — sequence-permutation
  negative control and migration assertions;
- `7a9457767d75b0f213c83cd298d0a9c0a1045839` — correct v2 migration
  staging through schema v3 before v4;
- `a6ae33cb017456d65685bf13c07cb39e74e38551` — preserve/reinstate
  append-only group trigger during v3-to-v4 migration;
- `b7e91dc3e530d9aa2a9d526ae4cebfc9bbd37ad2` — separate interrupted
  v3-to-v4 and unstamped-v4 recovery fixtures;
- `55242d9410eb0d0a13e58a22f5942c3885a242ae` — run A2.4 controls when
  prototype source changes;
- `fa65fbb3e6934359cf855ae4459bab59d275d272` and
  `6d256b64406a52f455261d23f097aa70e8cdcace` — update replay-gap and
  durable-store contracts.

**Evidence boundary:** source-level implementation and fixture review only.
No local execution is claimed. Exact-head CI on the final commit is required.
SFC projection, coverage and applied-through cursor remain unimplemented;
A2.4.4 remains OPEN and A2.4.8 remains BLOCKED.


### Additional fail-closed append control

The append path now verifies the existing group chain under the same
`BEGIN IMMEDIATE` lock before accepting a new group. A detected sequence gap,
permutation, broken predecessor link, stored-payload hash mismatch or
chain-hash mismatch blocks further writes. This prevents a new valid-looking
group from extending an already corrupted history. Audit controls assert
append refusal after both sequence-gap tampering and a permutation that
preserves the contiguous sequence set.

Implementation/test commits:
- `c3cf47c284e5b85efb1beec3b94244d99b2c2748` — verify existing chain
  under the writer transaction before append;
- `0f451cd612b357f871cd4f5649f7023b6929f2a5` — negative controls for
  fail-closed append after chain corruption;
- `2fe1c4a97fdc81ab2791fd97f5c0091632271f3a` — contract update.

These controls remain source-level until CI executes on the final exact HEAD.


### Legacy-chain migration preconditions

The v3-to-v4 migration now refuses to seal a legacy history unless:
- commit_sequence is exactly contiguous from 1 through N;
- each stored payload_sha256 matches the stored payload JSON;
- the payload JSON is canonical;
- the frozen group_id and causation_id agree with the envelope.

These checks run inside the migration transaction. An invalid v3 history
rolls back the added chain columns and leaves the prior schema/version marker
unchanged. A negative fixture creates a v3 sequence gap, requires migration
rejection, and verifies that no chain columns or version stamp survive.

Commits:
- `90f8790bdc444863fa540ab0d6bb927a93d623e6` — validate sequence and
  immutable group envelope before migration sealing;
- `a5020ca832121ba96d1f4ba60d0ad209e86a7648` — negative control for
  corrupt v3 migration rollback.

Execution remains pending on the final exact HEAD.


### Replay and append fail-closed boundary

The ordered `iter_groups()` API now validates the chain before returning any
replay prefix. It rejects corrupted ordering rather than returning a
deterministically sorted but untrusted history. The append path performs the
same chain verification under `BEGIN IMMEDIATE` before extending the log.
The verifier also checks canonical group JSON and that the payload's group
and causation identifiers match the indexed columns.

Additional controls require both append and ordered replay to reject a
sequence gap and a sequence permutation preserving `{1,2}`.

Commits:
- `1db4d8064df3f23ab1ccacc264845c9387c83f4b` — validate chain and
  envelope before ordered replay;
- `8cd7e030a7a399f877e29ccb8610b0303e97965b` — assert replay rejection
  after chain corruption.


### Consolidated schema-v4 source review and final controls

The final source pass confirmed these boundaries and controls:
- v1 migration now advances through v2, v3 and v4 in explicit version steps;
- populated multi-group v1/v2 histories without recoverable cross-group
  chronology remain fail-closed;
- v2 single-group migration reaches v4 and seals the one recoverable group;
- interrupted v3-to-v4 migration and unstamped-v4 recovery have separate
  fixtures;
- a corrupt v3 sequence is rejected before chain sealing, with migration DDL
  rolled back;
- append verifies the existing chain under `BEGIN IMMEDIATE` and refuses to
  extend a corrupt history;
- ordered replay verifies the chain and canonical group envelope before
  returning any groups;
- a sequence permutation preserving `{1,2}` is explicitly rejected.

The A2.4 workflow path filter now includes `prototype/**`, so prototype
changes exercised by its audit scripts trigger the dedicated workflow.

Latest implementation/control commits:
- `42f0df86ac570064074554107f6d94c65d07f62c` — initial v4 hash chain;
- `7a9457767d75b0f213c83cd298d0a9c0a1045839` — correct v2-to-v3 staging;
- `a6ae33cb017456d65685bf13c07cb39e74e38551` — migration trigger handling;
- `b7e91dc3e530d9aa2a9d526ae4cebfc9bbd37ad2` — interrupted v3/v4 fixtures;
- `55242d9410eb0d0a13e58a22f5942c3885a242ae` — A2.4 workflow prototype
  path trigger;
- `90f8790bdc444863fa540ab0d6bb927a93d623e6` — legacy sequence/payload
  preconditions;
- `a5020ca832121ba96d1f4ba60d0ad209e86a7648` — corrupt v3 rollback test;
- `c3cf47c284e5b85efb1beec3b94244d99b2c2748` — fail-closed append;
- `1db4d8064df3f23ab1ccacc264845c9387c83f4b` — fail-closed ordered replay;
- `8cd7e030a7a399f877e29ccb8610b0303e97965b` — ordered-replay rejection
  tests;
- `9d4bc4f71fbba48f8a2efce36e8c1cedd2653d1d` — explicit v4 audit output.

No local execution is claimed. The PR-triggered Prototype and Stage-C2
workflows have repeatedly remained queued without runner steps/logs.
The dedicated push-triggered A2.4 workflow is not exposed by the available
PR-only run-listing interface. A2.4.4 remains OPEN; SFC projection and cursor
remain unimplemented; A2.4.8 remains BLOCKED.


### 11 November continuation — normalized event/posting mirror fail-closed reads and writes

A deeper consistency review found a gap in schema-v4 protection: the local
hash chain authenticates the immutable group envelope, but the normalized
`events` and `journal_lines` tables are separate stored mirrors. Before this
change, `integrity_check()` detected a tampered mirror, but `append_group()`
could still append to that database, and `get_group()` could return a point
read without checking the chain or mirrors. `iter_groups()` checked the
chain but not the normalized mirrors.

The store now has a shared mirror verifier that checks foreign-key integrity,
group-envelope identity/hash, canonical event payloads, event order, event
hashes, and exact posting-line mirrors. It is invoked:
- under the writer transaction before any append or idempotent replay;
- before ordered group replay;
- before point reads by group ID.

A corrupted normalized mirror therefore blocks writes and all public group
read paths rather than allowing an apparently healthy append-only log to
continue over inconsistent projections of its own envelope.

A negative fixture tampers with a posting row while leaving the group hash
chain untouched. It requires `integrity_check()` to fail and append,
`iter_groups()`, and `get_group()` all to reject the database.

Commits:
- `eff0783093cff4bab1d2cb90f4cc994004125702` — shared mirror verifier and
  fail-closed append/replay/point-read paths;
- `695f259cb6e3d3b5a87273f29d43547a9a15ef1f` — adversarial posting-mirror
  corruption control.

**Execution boundary:** the environment has no repository checkout and
cannot resolve `github.com` from the local shell, so the complete repository
audit script has not been run locally. Two isolated local Python/SQLite
microtests were executed: (1) transactional DDL rollback and trigger
reinstatement for the v3-to-v4 migration pattern; (2) the new mirror-verifier
logic against a valid mirror and a tampered posting. Both microtests passed.
They are narrow mechanism checks, not a run of
`audit_financial_event_store.py`, not a full integration test, and not a
substitute for exact-HEAD CI.

Current source/test commits above are on the audit branch. Fresh PR-triggered
Prototype and Stage-C2 runs are queued on commit
`695f259cb6e3d3b5a87273f29d43547a9a15ef1f`; no runner steps or completed
logs are yet available. The dedicated push-triggered A2.4 workflow remains
outside the available PR-only run listing. A2.4.4 remains OPEN; SFC projection,
coverage and applied-through cursor remain unimplemented; A2.4.8 remains
BLOCKED. PR #4 remains Draft/Open/unmerged; canonical `main` remains
untouched.


### 11 November continuation — consistent read snapshots under concurrent WAL writers

A further concurrency review found a time-of-check/time-of-use window in
verified reads. The connection uses SQLite autocommit mode; without an
explicit read transaction, chain verification, mirror verification and the
final SELECT could observe different WAL snapshots if another writer commits
between those operations. A reader could therefore return rows that were not
part of the snapshot whose chain it had just verified. The same read-skew
risk applied to the multi-query `integrity_check()`.

The store now opens an explicit read transaction before:
- `iter_groups()` chain/mirror verification and final ordered SELECT;
- `get_group()` chain/mirror verification and point SELECT;
- the full `integrity_check()` sequence (SQLite structure, foreign keys,
  chain and normalized mirrors).

An adversarial concurrency fixture pauses the reader immediately after its
chain verification, commits a second group through a concurrent WAL writer,
then resumes the reader. The verified read must return only the original
snapshot; a subsequent read must see both groups.

Commits:
- `020bed51da3ad2a18c6bead864825dbf77fe9469` — explicit consistent read
  transactions for ordered replay, point reads and integrity checks;
- `8683156149f0123f80644d6e5a6da91ae120f2cb` — concurrent WAL
  read-snapshot regression control.

**Execution boundary:** a local SQLite WAL concurrency microtest passed:
a concurrent writer committed while a reader remained pinned to its original
snapshot. This validates SQLite snapshot semantics, not execution of the
repository audit script. The complete audit script still cannot be run
locally because no repository checkout is present and the local shell cannot
resolve `github.com`. Exact-head CI remains required.


### 11 November continuation — normalized event and posting mirror fail-closed controls

A separate integrity boundary was closed after reviewing the relationship
between the immutable group envelope and its normalized SQLite mirrors. The
local hash chain authenticates the group envelope, but it does not by itself
prove that the separately stored `events` and `journal_lines` rows still
match that envelope after privileged out-of-band database edits.

The event store now verifies the normalized mirrors against each canonical
immutable envelope. The verification is applied before append, ordered replay
and point reads, and the full integrity checker independently checks the same
relationship. A corrupted mirror therefore cannot be silently extended or
returned as trusted event data.

Adversarial fixtures now cover:
- posting-row mutation after disabling its update trigger;
- event-row metadata mutation after disabling its update trigger;
- deletion of a normalized event and its postings after disabling delete
  triggers;
- refusal of append, ordered replay and point reads after detected corruption
  (where applicable to the fixture).

Commits:
- `eff0783093cff4bab1d2cb90f4cc994004125702` — verify normalized event and
  posting mirrors before append, replay and point reads;
- `695f259cb6e3d3b5a87273f29d43547a9a15ef1f` — posting-mirror corruption
  negative controls;
- `be1a400af58769978b9647b0cae27da5428e3caa` — event-row mutation and
  missing-event negative controls.

**Local evidence boundary:** an isolated local SQLite microtest of the
mirror-verification algorithm passed four cases: valid mirror accepted,
posting mutation rejected, event metadata mutation rejected, and missing
normalized event rejected. This is a narrow independently reconstructed
mechanism test, not execution of the repository source or its audit script.
A full checkout could not be obtained in the local shell because DNS/network
resolution for `github.com` failed. Exact-head CI remains the required
execution evidence for the committed repository implementation.


## 11 November continuation — SFC projection source audit and implementation boundary

At branch commit `c026363aac6eeec3cc1254f5ba3c37435dc18ac6`, the source was re-inspected across `prototype/financial_event_store.py`, `prototype/financial_journal_adapter.py`, the event-store adversarial fixture, and the existing SFC projection/recovery contracts.

Confirmed source boundary:
- Schema v4 currently hashes/chains the event-group envelope containing group ID, causation ID and ordered events.
- Its atomic transaction currently persists group, event and journal-posting rows only.
- The validated adapter has no typed SFC mapper result and does not append projection deltas.
- No opening snapshot, materialized holder-position table, projection coverage table, applied-through cursor or independent issuer-side register exists.
- `audit_instrument_stock_flow.py` remains a synthetic arithmetic fixture; it does not replay event IDs from the durable store.

A new architecture artifact, `A2_4_4_SFC_PROJECTION_IMPLEMENTATION_BLUEPRINT.md`, was committed at `cb105bca27476f7cbea22a481eab2cae81b32513`. It converts the existing projection protocol into a staged implementation contract (P0–P5), specifies the logical schema and same-transaction write boundary, and extends the adversarial matrix from 18 to 38 controls.

Important refinement: projection coverage is specified per event, not merely per group. Every event must have exactly one explicit disposition: `mapped` with one or more deltas, or `no_stock_effect` with an explicit empty delta list. This prevents a mixed group from silently omitting an unprocessed event. The complete projection result, including mapper version and delta order, must be included in the immutable group hash.

Independent Decimal arithmetic was executed locally for a three-period example:
- period 1: 100 + 10 T + 5 V − 2 O = 113;
- period 2: 113 − 8 T − 3 V + 1 O = 103;
- period 3: 103 + 0 T + 7 V + 0 O = 110;
- cumulative transaction-only financial NL contribution = +2;
- total stock change = +10;
- matching holder/issuer transaction NL contributions sum to zero.
This independently demonstrates why stock change must not be substituted for transaction-based financial NL. It is a local arithmetic microtest, not execution of a repository script or runtime integration.

The complete repository audit script remains unexecuted locally because this shell has no checkout and cannot resolve `github.com`. Isolated calculations do not constitute full-source PASS. Exact-head CI remains pending and must be inspected after completion.

**Gate status:** P0 domain kernel not implemented; P1–P5 not implemented. SFC projection and A2.4.4 remain OPEN; A2.4.8 remains BLOCKED. PR #4 remains Draft/Open/unmerged; canonical `main` remains untouched.


## 11 November continuation — P0 pure SFC projection kernel

Implemented the first executable stage of the projection plan:
- `prototype/sfc_projection_kernel.py` defines a frozen full-identity value type, typed immutable T/V/O deltas, explicit per-event coverage validation and deterministic holder-position replay from explicit openings.
- The kernel rejects missing/duplicate/unknown event dispositions, mapped events without deltas, no-stock-effect events with deltas, mismatched event periods, incomplete identities, noncanonical/non-finite/float amounts, missing or mismatched frozen openings, delta-index gaps, period gaps and contract-forbidden negative closings.
- Decimal accumulation uses exact integer-scaled addition rather than the ambient Decimal context. This avoids silent rounding when the process changes `getcontext().prec`.
- Financial net lending is calculated from transaction asset changes less transaction liability changes only; V and O remain in the stock-flow roll-forward, not NL.
- The module is intentionally pure and has no SQLite writes, mapper inference, opening activation, coverage cursor or issuer register. It is P0 only; P1–P5 remain OPEN.

Added `audit_sfc_projection_kernel.py` to the dedicated A2.4 workflow and the Prototype PR test wrapper. Local execution on Python 3.13.5:
- `python -m py_compile /tmp/sfc_projection_kernel.py` — exit 0;
- `PYTHONPATH=/tmp python /tmp/audit_sfc_projection_kernel.py` — exit 0;
- positive checks: T/V/O roll-forward, three-period continuity, explicit no-stock-effect disposition, canonical decimal handling and transaction-only NL;
- 10 negative controls rejected;
- exact Decimal accumulation passed with ambient precision deliberately reduced to 8.

SHA-256:
- `sfc_projection_kernel.py`: `5731e9d9c085e09406fef30109f23f478d639ee02c90daa50c5ba9a7d8c43a5b`;
- `audit_sfc_projection_kernel.py`: `92a9f20b4b492221db38eff2659cf8528d8a6d199896cd1d40c0f808fcdd01a4`.

These are local tests of the exact P0 source/audit files staged for this commit, not a full repository run and not evidence of SQLite atomicity or end-to-end projection. The workflow must pass on the exact branch head before this component is marked CI-verified. A2.4.4 remains OPEN; A2.4.8 remains BLOCKED.


## 11 November continuation — P1 explicit SFC opening activation

Added `prototype/sfc_projection_registry.py` and `audit_sfc_projection_registry.py`.

P1 behavior:
- Activation is allowed only while the event store contains zero committed groups. Populated v4 histories are rejected; no opening balance is inferred and no historical event is silently backfilled.
- The opening snapshot must contain at least one explicit row. Each row has the complete ten-dimensional instrument/holder/issuer identity, period, canonical finite decimal-string amount (including explicit zero); signed openings are allowed at registry level and contract-specific negative-position rules belong to the projection kernel, and evidence reference.
- Duplicate identity-period rows, floats, malformed identity, negative/non-finite amounts and missing evidence are rejected.
- Rows are sorted canonically and sealed by a SHA-256 snapshot hash. The metadata records schema version, immutable mapper version, evidence reference and row count.
- Identical activation retry is idempotent. A changed snapshot/version/evidence reference conflicts.
- Opening and metadata tables are append-only/immutable and opening contents are verified against the frozen hash.
- Critical fail-closed boundary: after activation, the legacy `append_group()` API is blocked. Until P2 exists, the store cannot accept new unprojected events. Existing unactivated stores continue to use the legacy append path unchanged.

The P1 audit fixture is wired into both the dedicated A2.4 push workflow and Prototype PR wrapper. The fixture checks empty-store activation, explicit zero, idempotent retry, changed snapshot rejection, legacy-history rejection, opening tamper protection, snapshot verification and append blocking.

This remains P1 only. It does not yet atomically append event + T/V/O deltas + materialized positions + coverage + cursor. P2/P3/P4/P5 remain OPEN. The full repository cannot be cloned in the local shell due DNS/network failure; exact-source local execution status must be reported separately from CI.


P1 hardening follow-up:
- Removed `executescript()` from the activation transaction. Python sqlite3 can implicitly commit before `executescript()`; all activation DDL now uses individual `execute()` calls so `BEGIN IMMEDIATE` remains held across schema creation, the empty-history check, opening insertion and metadata sealing.
- Added a pre-seal-only opening INSERT trigger. Opening rows are inserted before the metadata seal; once metadata exists, no additional opening can be inserted. UPDATE/DELETE remain blocked.
- The P0 replay kernel and P1 registry both allow signed opening positions at the generic layer. Contract-specific nonnegative constraints are applied only when the identity is explicitly marked as nonnegative.
- Local isolated SQLite microtests passed: DDL preserves the active write transaction; partial activation rollback removes the newly created schema; opening INSERT/UPDATE/DELETE and metadata UPDATE are blocked after sealing. This is not a substitute for the exact committed Python audit script or CI.


P1 empty-history gate was tightened after source review: activation now requires all three durable tables (`event_groups`, `events`, `journal_lines`) to be empty, plus SQLite `integrity_check='ok'` and a clean foreign-key check. This rejects orphan normalized rows even if the group table is empty. The P1 audit now injects an orphan event row with foreign-key enforcement disabled and requires activation to refuse it.


## 12 November continuation — SFC-GOLD-2A and financial replay recovery package

A new four-artifact synthetic evidence package has been added on the A2.4 audit branch. Its scope is deliberately limited to debt principal, accrued interest, interest settlement, impairment allowance, creditor write-off and legally effective forgiveness. GOLD-2B remains FX; GOLD-2C remains collateral and guarantees.

### Four artifacts

1. `SFC_GOLD_2A_CORPUS.json` — frozen v1.0.0 corpus with two entities/sectors, three full instrument identities, period-0 opening rows, four period opening/closing snapshots, seven immutable events and seven after-event checkpoints. It freezes contractual principal 75, recognized gross loan asset 60, enforceable written-off claim memo 15, impairment allowance 5, net carrying amount 55, accrued interest 6/6 and deposit 76/76.
2. `audit_sfc_gold_2a_oracle.py` — independent standard-library Decimal oracle. It imports no production modules, journal, SQLite store, projection kernel or recovery code. It checks event posting composition, full identity consistency, debit/credit balance, T/V/O roll-forward, legal claim reconciliation, allowance bounds, interest/deposit mirrors, transaction-only sector financial net lending and eight negative controls.
3. `SFC_GOLD_2A_CONTRACT.md` — accounting/legal contract. It distinguishes impairment (valuation allowance only), creditor write-off (accounting derecognition with surviving legal claim in memorandum register), and legal forgiveness (legally effective bilateral extinguishment).
4. `audit_financial_replay_recovery.py` — read-only SQLite v4 event-group loader. It independently verifies the predecessor hash chain, commit sequence, canonical group envelopes, normalized event/posting mirrors, opening snapshot when persisted, reconstructs positions and compares event checkpoints with the independent oracle. `--self-test` creates a schema-compatible synthetic SQLite fixture and explicitly does not claim to test the production append path.

### Accounting classifications frozen in GOLD-2A

- Loan origination, principal repayment, accrued interest, interest payment and legal forgiveness: T.
- Impairment allowance recognition: V.
- Creditor write-off and allowance consumed by the write-off: O.
- FX is excluded and must not be smuggled into the 2A case.
- The frozen transaction-only sector financial NL values are P1 CB +10 / H -10; P2 0 / 0; P3 0 / 0; P4 CB -5 / H +5. Each period consolidates to zero. V and O do not enter transaction NL.

### Integration and proof boundaries

The oracle and recovery scripts are wired into both `prototype/test_a2_4_audit_controls.py` and the dedicated `a2-4-audit-controls.yml` workflow.

**Important current architecture blocker:** P1 opening activation requires an empty store and then blocks legacy `append_group()`; P2 projection-aware atomic append has not yet been implemented. The current public path therefore cannot yet create a database containing both a sealed P1 opening registry and subsequent event groups. The recovery self-test seeds a schema-compatible database directly to test the independent read/replay verifier. It does not bypass this limitation in production, and it does not prove an integrated event+projection commit.

The current store has no materialized position-snapshot table. The recovery audit reports `NO_PERSISTED_POSITION_SNAPSHOTS` and compares a full replay against the frozen checkpoints/oracle instead. Full replay is not described as snapshot-recovery implementation.

### Execution status

- Artifact files and CI wiring are committed on the audit branch.
- At the time of this status update, exact-head CI has not yet been inspected to completion. No PASS is claimed for GOLD-2A until the exact-head Prototype and A2.4 workflow logs are available and the oracle/recovery cases are green.
- No production financial runtime, live ledger, provider or user balance was changed.
- Corpus data is synthetic and does not certify IFRS, GAAP, SNA or any jurisdiction's legal treatment.


### P1 signed-opening verifier correction — 12 November

A previously recorded source-level contradiction was corrected in the audit branch:
- `verify_sfc_projection_openings()` had rejected every negative opening amount even though normalization, P1 activation contract and generic projection kernel permit signed positions and defer nonnegative restrictions to instrument policy.
- The verifier now checks canonical finite decimal representation and frozen snapshot hash without imposing a generic nonnegative rule.
- `audit_sfc_projection_registry.py` now explicitly reopens the negative-opening database and verifies its persisted snapshot after activation.

This fixes the generic snapshot-integrity contradiction only. It does not mean every instrument may have a negative balance: instrument-specific nonnegative/short-position rules remain the projection contract's responsibility. Exact-head execution is pending; no PASS is claimed for this correction until CI logs complete.


### Production journal + P2 projection implementation — 12 November 2026

The previous statement that P2 projection-aware append had not yet been implemented is superseded by the committed implementation below. This is a source-code milestone, not a verified PASS or production-readiness claim.

- Added prototype/entity_journal.py as the typed canonical GOLD-2A journal for the seven frozen event names. Old event aliases are rejected. It validates event-specific debit/credit composition, T/V/O, legal effect, effective-dated entity/sector identity, full instrument identity, write-off metadata and typed legal evidence.
- Replaced the adapter boundary with strict canonical EntityJournal/JournalEvent/JournalLine acceptance and lossless serialization of component, legal effect, writeoff_claim_delta, forgiven_principal and legal_evidence. Missing dimensions remain absent; empty optional strings are rejected.
- Added prototype/sfc_projection_store.py. append_projected_group commits the v4 group/event/posting log, instrument T/V/O positions, separate allowance and write-off memorandum control positions, per-event coverage, transaction-only sector flows, event/group checkpoints and applied-through cursor in one SQLite BEGIN IMMEDIATE transaction.
- Added a separately sealed, hashed control-opening registry. Each control owner must provide both allowance and write-off memorandum period-0 openings; these are not synthetic financial instruments.
- Closing-to-opening carry-forward is automatic. Backdated appends are rejected. The legacy append path remains blocked after P1 activation.
- Recovery re-derives event-to-position deltas from immutable event envelopes, revalidates canonical GOLD-2A semantics and legal evidence scope, invokes the pure SFC kernel for an independent instrument roll-forward, rebuilds control positions and sector transaction flows using exact Decimal arithmetic, and checks coverage, checkpoints, materialized positions and cursor.
- Added audit_financial_journal_adapter.py, audit_sfc_projection_store.py and audit_unified_cross_register.py; the dedicated A2.4 workflow invokes these new controls. The unified fixture links the SCCE engine event, cohort event, physical flow, product valuation, labour reference and financial causation under one scenario ID. It remains a synthetic fixture: there is no single production transaction coordinator across all registers.

The frozen GOLD-2A corpus is unchanged. Its legal-forgiveness event has no legal evidence payload, so the adapter test supplies synthetic evidence separately. Live use must receive authoritative evidence from the legal workflow.

Current branch HEAD: 3c999606a3a07ca8ee91791dfd7a4a08971d87f8. Exact-head Prototype validation run 43189796647 and A2.4 audit-control run 43189787395 are QUEUED; another Prototype run 43189787855 is also QUEUED. No conclusion, job steps or logs are available yet; no PASS is claimed. PR #4 remains Draft/Open and main is unchanged.

Remaining open gates: exact-head CI execution; a production cross-register transaction/recovery coordinator; P5 sidecar recovery; external signed checkpoints and operational multi-writer/crash testing; authoritative legal-evidence integration; closed-period correction/reopen governance. A2.4.7 Gate 2 and A2.4.8 remain OPEN/BLOCKED. No empirical synergy, legal enforceability or production-readiness claim follows from this implementation.


### Cross-register identity separation and CI queue control — 12 November

The unified integration fixture was tightened so that a scenario provenance root is no longer reused as every register's event identifier. The SCCE engine, physical flow, capital cohort, labour, product-price source and financial group now retain distinct record/event keys, while the shared scenario root is carried in each test envelope and as the financial group's causation ID. The test asserts six distinct register record IDs under one scenario root. This prevents a shared correlation identifier from being mistaken for six identical events.

The three relevant workflows now use a branch/workflow concurrency group with cancel-in-progress enabled. This is intended to supersede stale queued branch runs when a newer HEAD is pushed, rather than consuming runner capacity on intermediate revisions. Some earlier queued jobs remain visible while GitHub processes cancellation; this is not evidence that the newest code has executed.

At HEAD fde0e72189d2a18b231b40a565a243eec9ae8a87:
- A2.4 audit control fixtures: run 43191503973, QUEUED.
- Prototype validation: run 43191511330, QUEUED.
- SCCE Stage-C2 validation: run 43191511372, QUEUED.
- No exact-HEAD workflow conclusion or execution logs are available. No PASS is claimed.

PR #4 remains Draft/Open/unmerged. Main remains unchanged. The cross-register fixture remains synthetic and does not establish a single production transaction coordinator. P2's code-level atomic boundary is SQLite-local; it does not establish distributed atomicity across the physical, cohort, labour, product, rights and financial registers.

Next verification gate: wait for the exact HEAD workflows to leave QUEUED, inspect the A2.4 job logs step-by-step, repair any failures, and only then advance to crash/restart and cross-register recovery controls.


### P2 control-identity hardening — 12 November

A source audit found that impairment-allowance projection was assigning LCU/NOMINAL inside the mapper rather than requiring those dimensions on the source allowance posting. This would silently invent a control valuation identity outside the frozen corpus. The production journal now requires explicit currency and valuation basis on the impairment-allowance line; the synthetic corpus adapter supplies LCU/NOMINAL explicitly as test-fixture metadata; both the live mapper and independent recovery mapper now preserve those source fields without defaults. The adapter test rejects missing dimensions and checks a USD variant maps to USD rather than a hard-coded currency. The P2 test also asserts the final control-position currency and basis.

The allowance invariant no longer hard-codes instrument ID LOAN-001. It checks recognized gross loan assets by the same holder, currency and valuation basis as each allowance control. This keeps the contra-asset bound tied to the correct valuation identity when multiple loan instruments exist.

Latest code commit at the time of this note: 9109961119f747822e93bf6ec062e8e2b4a24de4. A2.4 run 43191870095 is PENDING/QUEUED; no test step has executed and no PASS is claimed. The branch remains separate from main; PR #4 remains Draft/Open/unmerged.


### Unified fixture identity and CI wiring — 12 November

The cross-register fixture now separates scenario correlation from each register's own record identity: SCCE event key, physical-flow ID, capital cohort event ID, labour event ID, product-price source ID and financial group ID are all distinct. The shared scenario root is carried in six register envelopes and remains the financial causation ID. The fixture also asserts that the cohort-derived capital multiplier is actually applied to the live SCCE cell before its period transition, and that the physical unit (tonnes) remains distinct from the LCU valuation.

The Prototype test wrapper now executes both the P2 atomic projection audit and the unified cross-register fixture. The dedicated A2.4 workflow compiles both prototype and audit source trees before running its controls. The three workflows have branch/workflow concurrency limits so stale revisions are canceled in favour of the newest pending run.

Latest reviewed code commit before this status update: 031e05b96ebd3392a1d88349eeea56036f698b91; subsequent workflow compile update: 7f4c57d60f99be938420f971787dc01e07f09554. At the latter HEAD, A2.4 run 43192091654, Prototype run 43192102537 and SCCE Stage-C2 run 43192102507 are QUEUED; their jobs have not started. No PASS is claimed. PR #4 remains Draft/Open/unmerged; main remains unchanged.


### P2 crash/restart, backup recovery and production coordinator gates — 12 November 2026

A targeted source audit found and fixed a recovery-verifier defect: the coverage query compared `c.group_id` with the immutable event's group ID but had not selected `c.group_id`, causing a fail-closed missing-key path. The query now selects the stored coverage group identity explicitly.

Added `audit_p2_crash_recovery.py`, a subprocess-based crash harness that terminates the process after each selected SQLite write boundary, including the final COMMIT. It checks rollback/no partial group before COMMIT, full recovery after COMMIT, idempotent retry, SQLite online backup integrity, independent projection replay, and restore from a verified backup after an invalid primary image. The A2.4 workflow invokes this audit. This is source/CI wiring only until the workflow actually executes; it is not a local PASS.

Expanded SCCE Stage-C2 workflow path filters so integrated prototype and A2.4 audit changes also schedule the Stage-C2 validation direction. The intended exact-HEAD gate is now all three workflows: A2.4 audit controls, Prototype validation, and SCCE Stage-C2 validation.

Added `A2_4_7_CROSS_REGISTER_COORDINATOR_AND_RECOVERY_PROTOCOL.md` specifying the durable participant prepare/commit contract, coordinator decision state machine, commit-barrier visibility, idempotent recovery, six register roles, closed-period correction/reopen governance, external asymmetric signed checkpoints, backup/restore drills and distributed crash matrix. This is a production acceptance contract, not an implementation claim. No real six-register participant adapters, durable distributed coordinator, signing service, or governed period-generation rebuild have been completed in this change.

Outstanding gates remain explicit:
- exact-HEAD execution and full logs for all three workflows;
- real process-kill test execution and subsequent repair of any failures;
- host/power-loss and storage durability tests beyond process termination;
- six real participant adapters and durable cross-register coordinator;
- external signature/key custody and independent checkpoint verification;
- formal closed-period correction/reopen implementation and dual-approval rebuild;
- operational disaster-recovery restore with approved RPO/RTO.

PR #4 remains Draft/Open/unmerged; main is unchanged. No production readiness or distributed exactly-once claim is made.


### Exact-head crash harness and CI fan-out — 12 November 2026

The crash/restart harness, recovery-query correction, backup/restore drill, and production coordinator/period-governance contract are now present on this branch. Prototype validation and SCCE Stage-C2 path filters were widened to include the A2.4 audit tree so the three independent validation directions can be scheduled against integrated changes rather than silently skipping unrelated audit commits. This status entry intentionally triggers the three path-filtered gates on the final source revision. The next accepted evidence is each workflow's run SHA, completed job steps, and logs; queued/cancelled attempts on older SHAs do not count.


The subprocess crash matrix was expanded to cover not only journal/projection deltas and checkpoints, but also initial and carried-forward instrument/control position inserts, runtime initialization/current-period advancement, materialized position updates, sector-flow writes, and the final COMMIT. Repeated insert statements use occurrence-specific fault points so the test can terminate during the first carried-forward period rather than repeatedly killing only the opening-snapshot initialization. Backup validation now includes both SQLite integrity and foreign-key checks.


### CI trigger integrity correction — 12 November 2026

The prior concurrency key combined push and pull_request runs for the same branch, so the two event types could cancel each other. Prototype and SCCE Stage-C2 now use the branch push trigger as the single source for this audit branch; A2.4 was already push-only. During removal of the duplicate pull_request blocks, duplicate `paths` keys were briefly introduced and immediately removed. The corrected workflow files now each have one push path filter (SCCE retains manual workflow_dispatch). The exact COMMIT fault-injection matcher was also tightened to require the normalized SQL statement to equal `COMMIT`, rather than matching a substring such as `commit_sequence`.

The next three CI runs must be generated by one documentation-path commit on this branch, then inspected for real job execution and logs. Any earlier malformed-workflow or event-cancelled runs are not validation evidence.


### Durable coordinator protocol and subprocess crash matrix — 12 November 2026

Implemented `prototype/cross_register_coordinator.py` as a durable protocol core with six separate SQLite participant stores. It persists canonical transaction envelopes, per-participant payload digests, expected revisions, prepare tokens, participant receipts, immutable event rows, coordinator state transitions and participant state transitions. The commit decision is persisted before any participant commit is sent and cannot transition to abort. Recovery aborts transactions that have not crossed the durable decision point and retries commit delivery for transactions that have.

A commit-barrier read check requires the coordinator state to be COMMITTED and all six participant receipts to match their participant-local durable receipts, transaction IDs, native event IDs, payload digests and prepare tokens.

Added `audit_cross_register_crash_matrix.py` and wired it into the A2.4 workflow and Prototype audit wrapper. The matrix creates fresh coordinator/participant databases and kills a child process at 25 boundaries: each participant prepare, each coordinator prepare receipt, each participant commit, each coordinator commit receipt, and final commit-barrier publication. Recovery checks no pre-decision effects, exactly one post-decision effect per participant, no partial visibility, idempotent repeated recovery, changed-content replay rejection, stale-revision rejection and immutable transition history.

**Evidence status:** source and CI wiring committed; the crash matrix has not yet completed on CI and was not locally executed in this session. No PASS is claimed.

**Production boundary:** the six SQLite participant stores are protocol conformance participants, not adapters to the authoritative domain stores. Physical, capital, labour, product, legal/rights and financial production adapters remain required. No distributed production atomicity claim is made. External asymmetric signed checkpoints/WORM publication, dual-approved closed-period reopening with generation rebuild, host-level disaster recovery and end-to-end multi-register restore remain OPEN.


### Closed-period governance and Ed25519 checkpoint controls — 12 November 2026

Added `prototype/period_governance.py` and `audit_period_governance.py`. The governance ledger requires a verified pre-reopen checkpoint, a reason/evidence/scope, two distinct approvers in separate period-owner and independent-controller roles, and six register rebuild receipts sharing one immutable event-log root. It switches the active generation only after all six receipts and a verified new checkpoint are present. Prior generation history and closed-period records are immutable. Late corrections are represented as new append-only correction events in an open period; backdated corrections at or before the latest closed period are rejected.

Added `prototype/external_checkpoints.py` and `audit_external_checkpoints.py`. The module uses Ed25519, canonical manifests, trusted public keys, key-revocation checks, monotonic checkpoint sequence verification, immutable object keys and backup artifact SHA-256 verification. The A2.4 workflow installs the cryptography dependency and executes the new audit; the Prototype wrapper also discovers it.

**Evidence status:** source and CI wiring committed; neither new audit has completed exact-HEAD CI in this session. No PASS is claimed.

**Production boundary:** the local SQLite anchor is a conformance fixture, not independently administered WORM/object-lock storage. Actual KMS/HSM key custody, external trust-root and revocation management, remote monotonic sequence anchoring, and real six-register rebuild execution remain open. The governance ledger records receipts and switches a generation pointer; it does not itself rebuild the authoritative domain stores.
