# A2.4 SFC/SCCE audit status — 11 November 2026

## Boundary
- Canonical branch: `main`; unchanged by this audit.
- Audit branch: `audit/sfc-scce-a2-4-continuation-20261111`.
- No unified economic engine is assembled.
- No SFC financial layer is integrated into SCCE.
- The only prototype-path modification on the audit branch is a test-only deterministic SCCE fixture in `prototype/test_scc_endogenous_household_economy.py`; production model and queue implementation are unchanged. No production code or canonical `main` changes.

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
