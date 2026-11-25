# Cellular Cooperative Market v1 — Implementation Map and Simulation Gap

**Document ID:** SYNERGY-CCM-IMPL-001  
**Version:** 1.0 — 24 November 2026  
**Purpose:** prevent the research protocol from being mistaken for an already implemented seven-arm simulator.

## 1. Existing executable foundations

The repository already contains two relevant simulation layers.

### Stage A — prototype/cellular_coordination.py

Executable allocation regimes:

- market — decentralized buyer/seller matching with price and bilateral consent constraints.
- central — centralized allocation benchmark.
- cooperative — common-pool allocation with priority-weighted max-min rationing.
- cellular — local request/offer/acceptance protocol with relay consent, bounded hops and explicit communication traces.

Its output includes fulfilment, weighted fulfilment, lower-cell fulfilment, inequality diagnostics, logistics costs, coordination costs and message/route metrics.

It is a local allocation/coordination kernel, not a complete macroeconomy. It intentionally excludes production recipes, credit, ownership, wages, capital accumulation and ecological stocks.

### Stage B — prototype/scc_dynamic_economy.py

Executable physical-economy regimes:

- market
- central
- cooperative
- cellular

It models seven production cells, endogenous output, intermediate inputs, inventories, labour budgets, coordination messages and their labour cost, household/community consumption, ecological raw-resource stocks and stock-flow validation. It includes paired-seed comparisons, Monte Carlo summaries and coordination-labour sensitivity/frontier experiments.

Money, credit, legal ownership and wages remain outside this physical-layer experiment. Stage-C household experiments extend distribution and endogenous household feedback, but do not turn Stage B into a complete legal or financial settlement system.

## 2. Mapping from the seven-arm research protocol

| Target arm | Existing implementation | Status | Interpretation constraint |
|---|---|---|---|
| Decentralized bilateral market | Stage A/B market | Implemented baseline | Does not by itself model all market institutions or competition law |
| Conventional firm / hierarchy | None dedicated | Not implemented | Central is an allocation/optimization benchmark, not a firm |
| Producer cooperative / artel | Stage A/B cooperative | Partial proxy | Common-pool rationing is not a legal cooperative constitution, ownership model or member labour contract |
| Scoped consortium | None dedicated | Not implemented | Requires autonomous parties, project-specific commitments and explicit boundary/exit rules |
| SCCE consortium-cell | Stage A/B cellular | Partial proxy | Cellular local coordination is not yet the full legal/financial SCCE institutional stack |
| Cellular Cooperative Market hybrid | None dedicated | Not implemented | Requires market, cooperative and consortium mechanisms composed under typed mandates |
| Centralized allocation benchmark | Stage A/B central | Implemented benchmark | An information/optimization comparator, not a realistic state or enterprise model |

**No seven-arm experiment has yet been executed.** The current Stage-A/B/C test runs validate existing regimes and household mechanisms. They do not establish empirical or simulation superiority of the new hybrid.

## 3. Proposed operational definitions for missing regimes

The definitions below are design candidates to be frozen and tested, not claims about universal organizational forms.

### 3.1 Firm hierarchy

A firm arm should represent a legally and economically bounded enterprise that controls a declared production boundary under an internal authority structure. Its manager allocates inputs and capacity against a declared enterprise objective, such as contract fulfilment and risk-adjusted operating surplus, subject to wages, safety, legal obligations and resource constraints.

It must differ from the central planner benchmark:

- firm objective is bounded by its own contracts, assets, liabilities and residual claim;
- it cannot command unrelated independent firms or households;
- internal transfers are not external market transactions;
- enterprise overhead, monitoring, managerial information and internal agency costs are charged;
- external purchases/sales remain market contracts.

The simulator must not call a central planner a firm merely because both use centralized allocation.

### 3.2 Scoped consortium

A consortium arm consists of at least two autonomous organizations with a versioned project agreement. It combines only declared capacities, assets, deliverables and risk commitments. Each member retains its independent legal identity and property unless a separate instrument explicitly changes rights.

Required simulation inputs:

- participant identities and project roles;
- committed quantities/capacities and delivery windows;
- project-specific decision mandate;
- contribution and risk allocation;
- shared versus separately owned assets;
- default, substitution, exit and dissolution rules;
- coordination, monitoring and contract-enforcement costs.

A consortium is not modelled as a universal common pool. Uncommitted assets and capacity remain outside the project boundary.

### 3.3 Cellular Cooperative Market hybrid

The hybrid composes mechanisms by task and rights boundary:

- market discovery for contestable goods and independent supplier choice;
- cooperative production/allocation for voluntarily pooled member assets and agreed common resources;
- scoped consortium commitments for projects requiring complementary independent organizations;
- DAO cells for bounded governance and shared-service coordination;
- SCCE-style local routing where information is local and relay consent is explicit.

The composition must not allow a market match to become a contract automatically, a DAO vote to transfer title, or a cooperative pool to absorb assets not committed to it.

## 4. Required simulator architecture

Do not fork scc_dynamic_economy.py into a competing full economy. Extend the existing policy and experiment interfaces after the institutional schema is reviewed.

Recommended stages:

1. **Institutional topology adapter:** translate canonical organization, coordination-unit, participation, agreement and mandate references into a read-only experiment topology.
2. **Boundary validation:** prove that every simulated allocation is inside the declared ownership, consent, capacity and agreement boundary.
3. **Policy interface:** add separate policy strategies for firm hierarchy, scoped consortium and the hybrid; keep market, central, cooperative and cellular unchanged as baselines.
4. **Cost accounting:** charge legal/contract setup, management, monitoring, communication, coordination labour, dispute and exit costs to the regime that incurs them.
5. **State-flow integration:** preserve physical stocks, money, financial claims, labour and legal rights as separate ledgers. The physical Stage-B experiment must not silently create money or ownership.
6. **Paired experiment runner:** use the same initial world, random seed, demand, technology and shock schedule across all arms.
7. **Validation:** exact resource conservation, no double allocation, no out-of-boundary transfers, no unauthorized decisions, and reproducible event traces.
8. **Reporting:** output full metric vectors, paired differences, uncertainty and negative results. Keep software, synthetic simulation, calibrated simulation and pilot evidence separate.

## 5. Minimum invariants before adding new policy arms

- No product quantity may be allocated more than once.
- No seller may deliver more than available stock or committed capacity.
- No buyer may receive more than eligible demand.
- A non-member or non-party cannot receive member-only pool allocations.
- A consortium cannot allocate uncommitted capacity or assets.
- An organization cannot be charged for another organization's obligations without an explicit guarantee instrument.
- Internal transfers must not create consolidated income or net wealth.
- All coordination and contract costs must be counted.
- No central optimizer may observe information unavailable to the policy being simulated unless information acquisition is charged.
- Identical seeds must use identical exogenous shocks across arms.
- A passing simulation invariant is not evidence of real-world legal enforceability or economic superiority.

## 6. Immediate implementation sequence

**IM-1:** finalize and test the domain contract in cellular_cooperative_market.py, including host identity, non-exclusive participation, explicit organization delegates and action allowlists.

**IM-2:** add a read-only adapter from the canonical entity and legal-rights references to the experiment topology. Do not create another entity or rights registry.

**IM-3:** specify the firm, consortium and hybrid objective functions and cost boundaries in a short design review before coding.

**IM-4:** implement one missing arm at a time, beginning with the scoped consortium boundary because it can be defined as an explicit set of committed capacities and contracts without changing the underlying production technology.

**IM-5:** add invariant tests before comparative simulation; then run paired seeds and stress scenarios.

**IM-6:** only after all arms are implemented, freeze protocol parameters and run the confirmatory seven-arm experiment.

## Conclusion

The repository already has a mature four-regime physical allocation and coordination simulator plus Stage-C household extensions. The new Cellular Cooperative Market currently adds the institutional ontology, authority contract and research protocol; it does not yet add three missing simulation arms. The next engineering phase must extend the existing Stage-B experiment without duplicating its physical economy or confusing a centralized allocator with a firm, a common pool with a legal cooperative, or local cellular routing with a full consortium.
