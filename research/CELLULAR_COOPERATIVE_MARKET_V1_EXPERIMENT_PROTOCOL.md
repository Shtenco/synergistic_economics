# Cellular Cooperative Market v1 — Comparative Experiment Protocol

**Protocol ID:** SYNERGY-CCM-EXP-001  
**Version:** 1.0 — 24 November 2026  
**Status:** preregistration template; numerical parameters must be frozen before execution  
**Parent:** SYNERGY_CELLULAR_COOPERATIVE_MARKET_V1.md

## 1. Research question

Under which conditions does a network combining open markets, member cooperatives/artels, scoped consortia and polycentric DAO cells improve productive capacity, resilience and effective economic opportunity relative to feasible institutional alternatives?

This protocol does not presume that the hybrid wins. It is designed to identify the conditions in which it helps, has no material effect, or performs worse.

## 2. Experimental arms

| Arm | Institutional mechanism | Purpose |
|---|---|---|
| A | Decentralized bilateral market | Competitive discovery and voluntary exchange baseline |
| B | Conventional firm / hierarchy | Internal coordination and authority benchmark |
| C | Producer cooperative / artel | Member production and cooperative governance |
| D | Scoped consortium | Contractual cooperation among independent organizations |
| E | SCCE consortium-cell | Existing cellular coordination model |
| F | Cellular Cooperative Market | Hybrid of market, artel, consortium and bounded DAO-cell coordination |
| G | Centralized allocation benchmark | Explicit information/optimization benchmark; not a realistic public-administration model |

The arms must use identical production technology, endowments, demand, participant heterogeneity and shock sequences wherever the mechanism permits. If a mechanism requires extra coordination labour, legal services, monitoring, capital or information, those resources must be charged to that arm.

**Implementation status at protocol publication:** the existing Stage-A `prototype/cellular_coordination.py` and Stage-B `prototype/scc_dynamic_economy.py` currently implement four regimes: market, central allocation, cooperative allocation and SCCE cellular coordination. These are reusable baselines, not the complete seven-arm experiment. The central allocator is an optimization benchmark, not a conventional firm hierarchy. Cooperative allocation is a first approximation to member cooperative/artel production, not a complete legal cooperative. Dedicated firm-hierarchy, scoped-consortium and cellular-cooperative hybrid mechanisms still require implementation and validation. No seven-arm comparative result may be reported until those three mechanisms are implemented and the full protocol is executed.

## 3. Experimental unit and assignment

The primary unit is a simulated economic network over a fixed horizon. Each network contains multiple production organizations, households, resource suppliers, project opportunities and coordination relationships.

Use paired random seeds: each institutional arm receives the same seed-specific initial conditions and shocks. Record the random generator, seed, model version, policy version, configuration digest and software commit SHA.

The number of seeds, periods, network sizes and parameter ranges must be chosen before the confirmatory run. Exploratory runs must be labelled and must not be silently pooled with confirmatory results.

## 4. Primary outcome vector

Do not reduce performance to GDP, total trade, token value or a single fairness score. Report:

1. Physical output by product and quality.
2. Unmet demand and essential-needs fulfilment.
3. Productive capacity and capital-service availability.
4. Inventory shortages, waste and supply-chain concentration.
5. Coordination, contracting, monitoring and dispute-resolution costs.
6. Cash conservation, due obligations, arrears, default and solvency.
7. Lower-decile, median and upper-decile household outcomes.
8. Effective access to tools, training, finance and market opportunities.
9. Ownership, voting, agenda and network-power concentration.
10. Exit cost, portability and replacement of critical intermediaries.
11. Ecological stock-flow balances and externalized costs.
12. Unauthorized actions, rights violations, disputes and reversals.

Publish the full outcome vector and uncertainty intervals. Any composite score is secondary and must disclose its normative weights and sensitivity.

## 5. Core mechanisms to vary

- Cell size and nesting depth.
- Number of overlapping memberships per participant.
- Consortium size and contract completeness.
- Share of production organized by artels versus independent firms.
- Market search radius and matching/coordination cost.
- Governance quorum and approval thresholds.
- Member versus organization-delegate representation.
- Capital-return policy and separation of capital from voting rights.
- Contribution evidence quality and uncertainty.
- Common-pool prefunding, caps and replenishment.
- Exit costs and portability.
- AI recommendation quality and delegated action limits.

Do not tune every arm independently to its best observed outcome and then present the result as a fair comparison. Use a documented calibration phase, freeze parameters, then run confirmatory tests.

## 6. Stress scenarios

1. Ordinary demand and supply variation.
2. Demand collapse and demand surge.
3. Critical supplier failure.
4. Energy, water or raw-material shortage.
5. Logistics disruption and geographic isolation.
6. Capital and liquidity shock.
7. Member exit, artel dissolution and consortium withdrawal.
8. Strategic misreporting and contribution-score gaming.
9. Voting concentration, collusion and agenda capture.
10. Platform outage and operator insolvency.
11. Dispute backlog and delayed evidence verification.
12. Ecological regeneration constraint.
13. Correlated shocks and cascading defaults.
14. Cross-jurisdiction legal incompatibility.
15. AI recommendation error, stale mandate or unauthorized action.

## 7. Falsification criteria

The hybrid model must be rejected or materially revised for a given operating domain if it persistently:

- increases total coordination and administration costs without compensating outcome gains;
- worsens essential-needs fulfilment or lower-tail outcomes under comparable resources;
- increases concentration of effective control or creates unreviewable gatekeepers;
- raises default contagion or hidden contingent liabilities;
- makes exit materially less feasible than the comparison arms;
- produces worse physical or financial balance violations;
- increases ecological depletion or shifts costs to other cells/periods;
- requires more unauthorized actions or weakens due process;
- fails to outperform simpler alternatives after accounting for legal, monitoring and coordination costs.

A result that is positive only under perfect information, zero-cost governance or omniscient AI is not evidence for real-world superiority.

## 8. Reporting and evidence levels

Every result must be labelled as one of:

- **Software invariant:** a test confirms a coded property under specified inputs.
- **Synthetic simulation:** a model produces a result under stated assumptions.
- **Calibrated simulation:** parameters are fitted to identified data with uncertainty disclosed.
- **Pilot evidence:** real participants and transactions under a documented protocol.
- **Causal/empirical evidence:** a design supports a defensible causal interpretation.

These levels are not interchangeable. Passing tests does not prove the economic thesis. Synthetic paired seeds do not establish external validity.

## 9. Reproducibility package

A complete experiment release must include source SHA, configuration, seed list, input data provenance, environment, output files, statistical code, exclusions, deviations, negative results and a human-readable limitations report.

No result should be described as confirmatory unless the protocol and parameters were frozen before the confirmatory run.
