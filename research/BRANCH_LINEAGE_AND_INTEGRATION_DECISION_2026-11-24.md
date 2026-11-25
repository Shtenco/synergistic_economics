# Branch lineage and integration decision — 24 November 2026

**Repository:** Shtenco/synergistic_economics  
**Default branch:** main  
**Audit purpose:** select a safe research base for SYNERGY Cellular Cooperative Market v1.0  
**Evidence:** GitHub branch metadata, recursive Git trees, PR metadata/descriptions, selected source files, workflow definitions and commit comparisons.

## 1. Scope and limitations

At inspection time the repository exposed **19 branches including main**. Recursive tree metadata was retrieved for all 19 refs. The tree responses were complete (not truncated). All 17 pull requests returned by the repository's all-state PR listing were inspected at the metadata/description level.

This is a branch topology and architecture audit, not a claim that every source line in every branch has been manually reviewed or that every historical CI job has been rerun. The source review focused on the foundational theory, SCCE architecture, contribution/ownership/distribution, institutional design, Economic Router, canonical entity register, labour/legal registers, financial register, cross-register coordinator, SFC reconciliation and spatial bridge boundaries. Exact-head validation remains mandatory for the new branch.

## 2. Branch inventory

| Branch | Observed role / integration note |
|---|---|
| audit/sfc-scce-a2-4-continuation-20261111 | A2.4 SFC/SCCE, GOLD-1/2A, durable financial event/projection and cross-register audit work; PR #4 Draft to main |
| audit-russian-readme | Russian documentation lineage; PR #2 merged into prototype-2-input-output |
| feature/canonical-economic-entity-register-v1 | Earlier canonical entity register implementation; PR #15 closed/superseded |
| feature/canonical-economic-entity-register-v1-rebased-20261115 | Rebased iteration; PR #16 closed/superseded |
| feature/canonical-economic-entity-register-v1-rebased-20261115b | Current canonical entity, trust, settlement and economic core research head; PR #17 Draft |
| feature/economic-router-core-v1 | Demand/offer registry, deterministic matching and candidate lifecycle; PR #8 Draft |
| feature/synergy-leagues-phase-1 | Skills, work-order and payout-split domain; PR #7 Draft |
| integration/economic-core-consolidation-2026-11-13 | Consolidation attempt for A2.4, P6 and UEB; PR #6 Draft |
| main | Canonical default branch |
| prototype-2-input-output | Earlier general input-output model; PR #1 merged |
| research/authoritative-wage-deposits-v1 | Durable wage/deposit work; PR #12 Draft |
| research/bank-deposit-credit-audit-fix-20261115 | Bank-created deposit credit, principal lifecycle, reserve/interbank and SFC integration research; PR #13 Draft |
| research/financial-register-instance-provenance-v1 | Financial-register provenance research iteration; branch exists separately |
| research/household-liquidity-recycling-v1 | Experimental household liquidity recycling; PR #9 Draft |
| research/operating-wage-coordinator-v1 | Verified labour-to-wage cross-register coordinator; PR #11 Draft |
| research/sec-sper-integration-audit-2026-11-11 | SEC/SPER and P6 real-economy event/recovery lineage; PR #5 Draft |
| research/verified-wage-settlement-v1 | Earlier wage accrual/settlement ledger experiment; PR #10 Draft |
| unified-economic-balance | UEB accounting kernel; PR #3 open, targets audit-russian-readme rather than main |
| work/spatial-economic-bridge-20261116 | Spatial economic twin adapter; PR #18 Draft to main |

The all-state PR inventory also includes PR #18, #17, #16, #15, #13, #12, #11, #10, #9, #8, #7, #6, #5, #4, #3, #2 and #1. No PR #14 was present in the returned listing. Closed PRs #15 and #16 were explicitly marked superseded by the newer canonical-entity branch.

## 3. Important architectural findings

### 3.1 The repository is not one already-integrated engine

The branch history contains multiple layers that must not be merged by copying balances or duplicating authorities:

- the original in-memory kernel ledger;
- the separate UEB ledger;
- the durable SQLite financial event store and projection pipeline;
- the P6 in-memory real-economy bridge;
- the economic marketplace registry and deterministic router;
- durable labour and legal-rights registers;
- the canonical economic-entity register and Ed25519 authority evidence;
- the six-participant coordinator and SFC/GOLD reconciliation contracts.

The previous repository-wide audit identified integration risks involving duplicate financial authorities, partial UEB bilateral loan commits in the earlier UEB snapshot, the need for a trusted journal-validation boundary, and the absence of one complete authoritative transaction across all physical/capital/labour/product/legal/financial participants. Later branches remediate or extend some of these issues, but their release claims must be checked against exact current heads.

### 3.2 The market router is not a settlement authority

The Economic Router performs deterministic candidate discovery/ranking. A match candidate is not a contract, inventory reservation, title transfer, payment or settlement. The new layer must consume its references rather than create a second marketplace registry or matcher.

### 3.3 SCCE physical coordination is not the whole economy

The existing SCCE Stage-B model is a physical production/consumption and coordination model. It must not be treated as already containing money, credit, legal ownership, wages or settlement. The new cooperative-market layer must preserve the separate state spaces and canonical register boundaries.

### 3.4 Contribution is not ownership or governance

Volume III explicitly distinguishes value creation, contribution attribution, rights/obligations and value distribution. SCI is project-specific evidence, not a universal reputation, credit score, title register, wage substitute or automatic profit entitlement. The new model preserves this distinction.

### 3.5 Legal identity is not title

The canonical economic-entity register provides stable tenant-scoped entity identity, jurisdiction and effective institutional sector, backed by append-only signed evidence. It explicitly does not prove beneficial ownership, lease, control, encumbrance or dispute status. Those remain in the Legal Rights Register and authoritative evidence.

## 4. Commit comparison and selected base

The selected base is:

- branch: feature/canonical-economic-entity-register-v1-rebased-20261115b
- base SHA: efeb8e0a5b4cf0a96d29a8cb548c4c298133b14b
- relation to main: GitHub compare reported the branch as 1,065 commits ahead and 0 behind main at inspection.
- PR #17: open Draft; based on the bank-deposit-credit audit lineage; its exact-head prototype-validation and trust/settlement validation checks were reported successful. Its cross-repository contract remains deliberately blocked by the missing SYNERGY_CROSS_REPO_READ_TOKEN secret.

Reasons for selection:
1. It is descended from the current main lineage, not the divergent UEB documentation branch.
2. It contains the newer canonical economic-entity register and authority proof work.
3. It includes the economic router, durable marketplace registry/candidate lifecycle, operating financial register, wage/legal registers, cross-register coordinator, and SFC reconciliation contracts.
4. It has exact-head prototype and trust/settlement validation evidence, with the cross-repository limitation explicitly disclosed.

The integration/economic-core-consolidation branch was not selected because its comparison with the selected canonical branch showed divergence and an 11-commit lag. The separate UEB branch was not selected because it is an isolated accounting kernel and does not target main. The spatial branch was not merged automatically.

## 5. Spatial bridge decision

PR #18 adds a spatial event adapter and tests. It is based directly on main and is separate from the 1,065-commit canonical research branch. Commit comparison reported the spatial branch as five commits ahead and 1,065 behind the selected canonical branch, with main as the merge base.

The spatial adapter is relevant as a downstream digital-twin interface, but its stated boundary is intentionally narrow: it validates WGS84/provenance/event references and keeps physical-flow quantities separate from financial-posting references. It does not post journals, settle transfers or mutate production state.

Decision: retain the spatial bridge as a documented integration dependency. Do not merge its code into this research branch until a reviewed rebase/cherry-pick plan and exact-head tests are available.

## 6. New branch

The new research branch is created from the selected canonical research head:

- branch: research/cellular-cooperative-market-v1-20261124
- parent: feature/canonical-economic-entity-register-v1-rebased-20261115b
- parent SHA: efeb8e0a5b4cf0a96d29a8cb548c4c298133b14b

The new branch adds the Cellular Cooperative Market v1 research specification, a standard-library domain-contract prototype, tests and this lineage decision. It does not modify main or merge any existing Draft PR.

## 7. Remaining audit and release gates

1. Run the new prototype tests and the full existing prototype workflow on the exact new branch head.
2. Review the new module against the existing schemas and event/command conventions before persistence is introduced.
3. Add a formal schema only after the domain contract is reviewed; do not create a second canonical entity or rights registry.
4. Reconcile the new organizational/participation references with the canonical entity register and Legal Rights Register.
5. Keep project distribution proposals separate from actual financial postings and payment settlement.
6. Rebase or otherwise integrate the spatial bridge only through an explicit reviewed change.
7. Preserve the missing cross-repository token as a disclosed blocker; do not report private cross-repository E2E as passed.
8. Treat passing software tests as evidence of coded invariants, not empirical proof, legal validation or production readiness.

## Conclusion

The selected branch is the broadest current research base that remains directly descended from main and contains the newer identity, marketplace, financial and register foundations. The new model is an additive institutional layer. Its core rule is to compose existing legal and economic subjects through typed, voluntary and scoped relationships while preserving canonical authority for identity, rights, labour, physical flows, financial claims, accounting and settlement.


## 8. Exact-head CI evidence — PR #19

After opening PR #19 against its selected parent branch, GitHub Actions run **45424081523** completed for head commit `669aa52332acd93150432a7f44e7e9306c7aa877`.

- **Prototype validation job: success.** The complete repository prototype suite ran 494 unit tests successfully. The existing Stage-A coordination checks, Stage-B paired dynamic simulations, Stage-C1 household distribution runs and Stage-C2-A2 endogenous household feedback experiment all completed successfully.
- **Pinned cross-repository economic/spatial/payment contract: success.** The cross-repository token check, pinned Metaverse/Maps/HardNAV checkouts, signed integration-flow test and HardNAV accounting regressions completed successfully.
- **Additional global Maps viewer build: failure.** The step `Build and test global SYNERGY Maps viewer` failed during npm dependency handling with `Cannot read properties of null (reading 'edgesOut')`. The Maps Python ingestion tests, trust/spatial regressions, Cesium build, live Kazakhstan sample ingestion and HardNAV regressions completed successfully. This failure is recorded as an external Maps frontend build issue, not as a failure of the new cooperative-market prototype.
- **HardNAV historical replay job:** skipped by this workflow run.

The prototype-validation result is evidence for the exact tested commit only. Subsequent commits require a new exact-head CI run. The global Maps viewer failure remains open and should be investigated in the Maps repository or its pinned integration snapshot.
