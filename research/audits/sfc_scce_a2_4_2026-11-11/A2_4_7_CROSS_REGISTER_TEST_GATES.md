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
