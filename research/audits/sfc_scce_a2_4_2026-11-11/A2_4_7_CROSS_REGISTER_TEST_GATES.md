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
| G0-D: financial | balanced journal fixtures for origination, transfer, payment, accrual, settlement, default, impairment and write-off | **SPECIFIED ONLY** — not implemented |
| G0-E: labour/rights | interval-overlap, consent, delivery, compensation accrual/settlement and rights non-inference tests | **SPECIFIED ONLY** — not implemented |
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
