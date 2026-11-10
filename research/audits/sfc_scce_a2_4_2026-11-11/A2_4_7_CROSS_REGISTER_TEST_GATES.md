# A2.4.7 — cross-register test and release-gate specification

**Date:** 11 November 2026  
**Branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Status:** acceptance matrix; not a claim that CI currently passes.

## 1. Test levels

| Level | Purpose | Evidence required |
|---|---|---|
| Unit | local formulas, validators and state transitions | deterministic tests, edge cases, dimensional rejection |
| Component | one register/module boundary | fixture with explicit inputs/outputs and invariants |
| Integration | cross-register event and stock-flow bridge | same event IDs, opening/closing states and mirrored postings |
| End-to-end | full frozen scenario/period | physical, production, financial and rights reconciliation |
| Statistical | comparative regime performance | matched seeds, uncertainty, sensitivity and frozen hashes |
| Empirical | fit/validity against real observations | provenance, calibration, external validation and identification |

Passing a lower level does not imply passing a higher level. Synthetic tests cannot be described as empirical validation.

## 2. Mandatory test groups

### A. Ontology and time types (A2.4.1 / A2-44)
- stocks, flows, rates, events, states, constraints, rights and outcomes are distinct types;
- period flows cannot be added to instant stocks;
- event time, recognition time and settlement time are separate;
- invalid state-space conversions fail closed;
- every transition declares preconditions, postconditions and reversibility.

### B. Physical product/process balances (A2.4.3)
- native-unit balance by product, grade, node and period;
- unique flow IDs and sender/receiver agreement;
- process component/energy/WIP closure;
- no unlike-unit aggregation;
- explicit waste, residues, losses, imports, exports and inventory;
- valuation changes do not mutate physical quantities.

### C. Capital and productive services (A2.4.2 / A2-46)
- cohort quantity and mutually exclusive status closure;
- repair does not reset age;
- component replacement does not reset host vintage;
- temporary failure does not reduce total physical stock;
- final retirement counted once;
- services use non-duplicated availability/utilization/quality;
- gross/net stock, CFC, disposals, revaluation and OVC reconcile independently;
- routine repair does not become GFCF without recognition criteria.

### D. Financial and SFC controls (A2.4.4 / A2-48)
- double-entry balance for every event;
- bank-created deposits versus transfer of existing deposits;
- payment, principal, interest accrual and settlement are distinct;
- default, impairment and write-off are distinct;
- instrument holder/issuer mirrors reconcile;
- stock-flow reconciliation and sectoral capital/financial net lending agree;
- total net lending closes across the full sector boundary.

### E. Labour, capability and rights (A2.4.5)
- time budget and interval overlap checks;
- capability is not hours or ownership;
- consent and delivery states are explicit;
- paid/unpaid work and training are distinguished;
- wages accrue separately from settlement;
- rights are not inferred from contribution;
- privacy/minimum disclosure constraints are enforced.

### F. Synergy estimand and experiment design (A2.4.6)
- credible comparator, common initial state and common shocks;
- matched seed pairing;
- pre-registered primary outcomes and costs;
- uncertainty and adverse effects reported;
- no scalar score hides hard constraints;
- synthetic/model effects are not labelled empirical.

### G. Reproducibility and provenance
- deterministic fixtures with exact expected quantities;
- fixed seeds and deterministic ordering;
- source, parameter, data and schema hashes;
- append-only correction lineage;
- duplicate event IDs rejected;
- CI artifacts contain machine-readable summaries and logs;
- independent Decimal or alternative implementation for key identities.

## 3. Release gates

**Gate 0 — local correctness:** all unit/component tests pass.

**Gate 1 — interface closure:** physical, capital, financial and labour interfaces pass their own cross-register fixtures; no undefined conversion or balancing plug remains.

**Gate 2 — end-to-end numerical control:** one frozen scenario/period closes all applicable registers and all instrument mirrors, with complete event IDs and stock-flow reconciliation.

**Gate 3 — comparative reproducibility:** paired SCCE/market/cooperative/central regimes run on identical initial states and seeds; preregistered outcomes, uncertainty and adverse effects are reported.

**Gate 4 — empirical validation:** calibration and held-out real-world validation are complete for the claims being made.

No gate can be skipped by adding more code or more scenarios. A failed test is investigated; assertions are not relaxed merely to obtain green CI.

## 4. Current CI blocker

At the latest inspected source state, Prototype validation run `42810082229` and SCCE Stage-C2 run `42810081975` each failed the same age-expiry integration assertion; 132/133 unit tests passed in both. The audit branch now contains a deterministic controlled-delivery test fixture, but its commit has no reported status checks in the inspected API response. It is **pending CI verification**, not a pass.

## 5. A2.4.8 entry conditions

A2.4.8 may begin as a paper/numerical integration experiment only after:
- A2.4.1–A2.4.7 contracts are frozen;
- the deterministic SCCE integration test and both CI workflows pass;
- B8.1 capital cohort records can be mapped to the A2.4.2 bridge without double counting;
- B2 product registry maps to A2.4.3 valuation basis;
- financial event IDs and instrument mirrors satisfy A2.4.4;
- labour/time/consent constraints satisfy A2.4.5;
- synergy estimand and comparator plan are preregistered.

The end-to-end test does not authorize an integrated runtime. The runtime boundary is a separate decision after Gate 2 and the relevant Gate 3 evidence.

**Current status:** test contract is specified, but the full suite and CI gate are not closed. A2.4.7 remains open.


## 6. Operational acceptance matrix (no implicit PASS)

A gate is PASS only when its evidence is present on the audit branch and the
relevant command/test has actually been executed against the committed source.
A specification, hand calculation, or script that has merely been written is
not execution evidence.

| Gate / workstream | Minimum executable evidence | Current disposition |
|---|---|---|
| G0-A: SCCE queue | deterministic expiry and overflow integration fixture; all primitive queue tests | **PENDING CI** — replacement fixture committed as `bea7d625`; both required workflows still need successful runs |
| G0-B: capital | same-cohort script, exact expected output, negative-input rejection | **IMPLEMENTED / EXECUTION PENDING** — `audit_same_cohort_capital.py` |
| G0-C: product | typed registry/valuation script; mismatched unit and grade rejected; quantity invariant under price change | **IMPLEMENTED / EXECUTION PENDING** — `audit_product_valuation_adapter.py` |
| G0-D: financial | balanced journal fixtures plus instrument-level stock-flow and holder/issuer mirrors | **IMPLEMENTED / EXECUTION PENDING** — `audit_financial_journal.py`, `audit_instrument_stock_flow.py`; synthetic component controls, not a general ledger/runtime |
| G0-E: labour/rights | interval-overlap, consent, delivery, compensation accrual/settlement and rights non-inference tests | **IMPLEMENTED / EXECUTION PENDING** — `audit_labour_consent.py`; component fixture, not a complete rights engine |
| G1: interface closure | all A2.4.1–A2.4.7 interfaces pass, typed conversions explicit, no balancing plug | **OPEN** |
| G2: end-to-end | one frozen period with linked physical, capital, labour and financial event IDs; all stock/flow and mirror identities close | **NOT STARTED** |
| G3: comparative | preregistered matched-seed regimes, paired outcomes, uncertainty, sensitivity and adverse effects | **NOT STARTED** |
| G4: empirical | provenance, calibration, held-out observations, identification and external validation for each claimed effect | **NOT STARTED** |

### 6.1 Required command evidence

For each executable control, record:
- exact commit SHA;
- interpreter/runtime version;
- exact command;
- exit code;
- stdout/stderr;
- source-file SHA-256;
- expected-output comparison;
- timestamp and runner identity.

For CI, record workflow run ID, workflow name, head SHA, conclusion, and links
to every job log. A green job on a different head SHA does not satisfy the gate.

### 6.2 Failure semantics

- Missing evidence is **PENDING**, not PASS.
- A script that is not invoked is **IMPLEMENTED / EXECUTION PENDING**.
- A failing required test blocks the gate even if unrelated tests pass.
- A test may be quarantined only with a documented defect, owner, impact boundary
  and explicit release exception; no silent skip or weakened assertion.
- A deterministic synthetic control proves arithmetic/contract behavior only.
  It does not establish model validity, causal synergy, or empirical fit.

### 6.3 Current three-task closure boundary

This continuation adds executable controls for (i) same-cohort capital
reconciliation and (ii) typed product valuation, and sharpens (iii) the release
evidence matrix. These additions do not close A2.4.2/A2.4.3 until executed,
and do not close A2.4.7 while the SCCE CI, financial, labour, full integration,
comparative and empirical gates remain open.


### 6.4 New A2.4.4/A2.4.5/A2.4.3 executable fixtures

| Workstream | Fixture | Negative/positive controls | Status |
|---|---|---|---|
| A2.4.3 node flows | `audit_physical_flow_register.py` | sender/receiver equality, unique flow ID, one-time consolidation | COMMITTED / EXECUTION PENDING |
| A2.4.4 journal | `audit_financial_journal.py` | balanced event postings; bank creation, non-bank transfer, payment, principal, accrual, settlement, impairment and write-off; duplicate ID rejection | COMMITTED / EXECUTION PENDING |
| A2.4.5 labour | `audit_labour_consent.py` | interval non-overlap, no delivery without consent, delivery <= schedule/safety, wage accrual vs settlement | COMMITTED / EXECUTION PENDING |

These fixtures are component controls. They do not yet constitute a complete
financial instrument registry, full institutional-sector SFC closure, live
SCCE integration, or a legally validated rights engine.


### 6.5 Executable audit workflow and physical-flow correction — 11 November 2026

A branch-scoped GitHub Actions workflow was added at
`.github/workflows/a2-4-audit-controls.yml`. It runs on pushes to this audit
branch and can be manually dispatched. It compiles the audit directory and
executes nine standard-library controls: six-sector SFC, capital bridge,
same-cohort capital, product dimensions, typed valuation, physical flow
endpoints, financial events, double-entry journal and labour/consent.

The physical-flow fixture was strengthened before execution: sender and
receiver are now distinct endpoint postings with reciprocal counterparty IDs
and opposite roles. Consolidation is calculated over an explicit node set;
an internal transfer cancels only when both nodes are inside that set, while
an external export remains visible as a domestic net outflow.

**Evidence status:** workflow configuration and fixture are committed, but
this document does not record a completed run, exit codes or logs. All nine
scripts remain **IMPLEMENTED / EXECUTION PENDING** until a completed workflow
on the exact commit SHA is inspected. An empty combined-status response is
not a pass.


### 6.6 Financial stock-flow component control — 11 November 2026

`audit_instrument_stock_flow.py` adds ten exact opening/closing positions from
the repository's six-sector SFC numerical example. It checks transaction,
revaluation and other-volume reconciliation, holder/issuer mirror equality,
and derives the six-sector financial net-lending vector. An independent
Decimal calculation of those values passed, but the committed script has not
yet been executed by a recorded runner. G0-D therefore remains **IMPLEMENTED /
EXECUTION PENDING**, and does not close A2.4.4.


### 6.7 A2.4.6 existing-experiment protocol audit

`A2_4_6_EXISTING_EXPERIMENT_PROTOCOL_AUDIT.md` records the actual four
economic regimes, market comparator, three household allocation policies,
seed loops, existing horizons/shocks and emitted metrics from the Python source
and CI workflow. It also identifies the current normal-approximation interval,
lack of primary/secondary endpoint hierarchy, incomplete incremental-input
accounting and absence of confirmatory exclusions/held-out seeds.

This closes source discovery for the existing exploratory experiment design,
not preregistration. Previously observed settings cannot be relabelled as
preregistered after the fact. A2.4.6 remains **OPEN** until a new confirmatory
protocol is frozen before results are generated.


### 6.8 Audit workflow trigger and observability

The dedicated audit workflow is configured for both audit-branch `push` and
PR-to-`main` changes affecting the audit directory/workflow. Manual
`workflow_dispatch` was removed because the workflow file is not present on
the default branch; GitHub documents that the manual dispatch path requires
the workflow file on the default branch. The PR trigger is intended to make
the dedicated suite appear among PR-associated checks.

At the latest poll, the connector had not surfaced a dedicated audit run ID.
Existing Prototype and Stage-C2 PR jobs remained queued without conclusions.
Until the exact-head audit job and both existing PR jobs complete and their
logs are inspected, Gate 0 remains pending. A missing surfaced run is not a
pass and is not, by itself, proof that the push-triggered run did not occur.


### 6.9 PR-observable execution of the eleven audit scripts

The standalone A2.4 workflow is retained for branch-push execution only. Its
PR trigger was removed because the workflow file is not in `main`; do not
assume a PR event will load a workflow definition introduced only by that PR.

Instead, `prototype/test_a2_4_audit_controls.py` adds eleven unittest cases
under the path already covered by the existing default-branch
`.github/workflows/prototype-validation.yml`. Each test launches the
corresponding committed audit script as a subprocess and asserts zero exit
status and a PASS marker. This reuses the established PR workflow without
changing `main`.

**Execution state:** wrapper committed; current-head PR run IDs and logs not
yet surfaced at the last poll. G0 remains pending until exact-head completion.


## 11 November continuation — exact workflow inventory and execution status

The current `.github/workflows/a2-4-audit-controls.yml` has a branch-push
trigger and a pull-request trigger. It does **not** declare
`workflow_dispatch`; the earlier statement that this workflow can be manually
dispatched was inaccurate and is corrected here.

The workflow compiles the audit directory and invokes eleven scripts:
six-sector SFC, capital bridge, same-cohort capital, B8.1 cohort contract,
product dimensions, product valuation, physical flow register, financial
event controls, financial journal, instrument stock-flow and labour/consent.

The GitHub Actions API surfaced multiple queued runs, including audit-control
run `42904711717` on head
`84958a1f448d7ab89bcddcfa0a5f4155862e52fe`. The latest branch head at the
time of this note is newer than some surfaced runs; a queued run on an older
head does not validate the latest head. No completed exact-head PASS is claimed.


### 6.10 Current surfaced PR jobs

The PR-observable A2.4 wrapper was added in commit
`751bbe60ca6e059d560ea5d84089f30f12aa4a56`. GitHub surfaced:

| Workflow | Run | Job | Latest state |
|---|---:|---:|---|
| Prototype validation | 42904924813 | 130140308153 | QUEUED |
| SCCE Stage-C2 validation | 42904924818 | 130140308848 | QUEUED |

Both jobs had no conclusion or logs at the latest poll. The test snapshot
includes the eleven-script wrapper and financial posting/mirror controls.
Subsequent commits `01c43c6f...` and `31b12467...` are documentation-only.
Gate 0 remains pending; no PASS is inferred from queued status.
