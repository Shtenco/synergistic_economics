# VOLUME VI — BENCHMARK ECONOMIES AND EXPERIMENTAL PROTOCOLS
## A fair comparative research programme for testing SYNERGY against market, cooperative, platform, federated and centralized institutions

**Research program:** SYNERGISTIC ECONOMICS  
**Document ID:** SYNERGY-ECON-V6-001  
**Version:** 0.1 — 9 November 2026  
**Status:** Experimental protocol proposal; no experiments have yet been run or validated  
**Preceding volumes:** [Volume 0](VOLUME_0_SYNTHESIS_OF_ECONOMIC_SCHOOLS.md); [Volume 0A](VOLUME_0A_AXIOM_RECONCILIATION_AND_METHOD_AUDIT.md); [Volume I](VOLUME_I_FOUNDATIONS.md); [Volume II](VOLUME_II_MULTIDIMENSIONAL_VALUE_AND_PRODUCTION.md); [Volume III](VOLUME_III_CONTRIBUTION_OWNERSHIP_AND_DISTRIBUTION.md); [Volume IV](VOLUME_IV_FORMAL_SIMULATION_AND_ACCOUNTING_KERNEL.md); [Volume V](VOLUME_V_EXECUTABLE_ECONOMIC_MODEL.md)

---

## Abstract

This volume specifies how to test the SYNERGY economic model without building the conclusion into the experiment. It defines benchmark institutions, treatment arms, common initial conditions, scenario families, parameter calibration, outcome metrics, statistical methods, robustness tests, reporting standards and rejection criteria.

The central methodological rule is **institutional neutrality of the experiment**. SYNERGY must not receive better initial resources, superior information, more capable agents, weaker legal constraints or more favourable shocks than its comparators unless that difference is the explicit treatment under study. Conversely, a baseline must not be deliberately simplified or deprived of capabilities available in the real institution it represents.

The purpose is to identify conditional performance: which arrangement works better, for whom, in which sector, at what scale, under what information and shock conditions, and at what administrative, financial, social and ecological cost.

No single institutional model is expected to dominate universally. A result may support SYNERGY in one domain and reject it in another. Negative and null results are first-class research outcomes.

---

# Part I — Comparative design principles

## 1. What counts as a fair comparison

A comparison is credible only if the treatments share, as far as possible:
- the same agents and skill distributions;
- the same initial productive and financial endowments;
- the same technologies and production possibilities;
- the same demand and supply shocks;
- the same legal and ecological constraints;
- the same information available to equivalent decision-makers;
- the same time horizon and accounting basis;
- the same definitions of output, income, wealth, risk and welfare.

If a treatment changes access to capital, information, infrastructure or AI, this must be named as a treatment component and evaluated through a design capable of identifying its effect.

## 2. Treatment decomposition

The full SYNERGY architecture contains many interacting components. A single all-in comparison cannot identify which component caused a result.

Decompose treatment factors:
- **C:** cellular consortium organization;
- **F:** federation and subsidiarity;
- **S:** shared productive assets;
- **D:** plural distribution and ownership;
- **U:** UEP access architecture;
- **O:** UOF opportunity financing;
- **M:** mutual credit;
- **A:** AI recommendations;
- **G:** governance and contestability safeguards;
- **E:** ecological and lifecycle constraints.

Use factorial or staged experiments to estimate main effects and interactions. Do not attribute the result of a ten-component bundle to any one component without additional design.

## 3. Research estimands

Every experiment must define what it estimates:
- average treatment effect on output;
- effect on lower-quantile household income;
- effect on asset utilization;
- effect on default probability;
- effect on recovery time after shock;
- effect on access barriers;
- effect on ecological resource pressure;
- effect on governance participation;
- effect on total administrative and coordination cost.

The estimand must state the population, treatment, comparator, outcome, time horizon and aggregation rule.

## 4. Unit of randomization and interference

Economic agents interact. One cell's treatment may affect other cells through supply chains, prices, labour markets, credit and knowledge spillovers. Standard independent-treatment assumptions may fail.

Possible units:
- individual;
- project;
- enterprise;
- cell;
- region or network cluster.

Where spillovers are material, randomize clusters or explicitly model network exposure. Report direct, indirect and total effects. Do not treat connected cells as statistically independent without justification.

---

# Part II — Benchmark institutional models

## 5. Benchmark A: decentralized market economy

### Institutional rules
- independent firms and households;
- voluntary contracts and competitive markets;
- prices coordinate exchange;
- ownership and governance follow the selected legal form;
- firms may enter and exit;
- public institutions provide declared rules, infrastructure and constraints.

### Required capabilities
This baseline must include realistic market search, prices, contract enforcement assumptions, transaction costs, firm heterogeneity, entry and exit, market power where relevant and failure. It must not assume frictionless perfect competition unless that is the explicit benchmark.

### Failure modes to test
- market power;
- information asymmetry;
- under-provision of public goods;
- coordination failures;
- incomplete contracts;
- externalities;
- credit constraints;
- systemic concentration.

## 6. Benchmark B: cooperative enterprise network

### Institutional rules
- worker, consumer, producer or multi-stakeholder cooperatives;
- member governance;
- surplus allocation under cooperative rules;
- internal capital and external finance;
- federation or secondary cooperative services where included.

### Required capabilities
Model member participation costs, governance, capital formation, indivisible reserves, member exit, non-member transactions, professional management and democratic accountability. Do not assume cooperatives are perfectly democratic or free of agency costs.

### Failure modes
- undercapitalization;
- member heterogeneity and conflict;
- slow decision-making;
- insider control;
- weak external finance;
- free-riding;
- difficulty scaling federation.

## 7. Benchmark C: platform-mediated economy

### Institutional rules
- a platform matches providers and users;
- platform sets access, ranking, fee and data rules;
- providers may be independent or employed, depending on scenario;
- network effects and switching costs are modeled;
- platform may own infrastructure and data assets subject to law.

### Required capabilities
Include matching efficiency, search reduction, reputation, ranking, fees, dispute handling, lock-in, data advantages and market power. Include multi-homing and interoperability where feasible.

### Failure modes
- platform extraction;
- opaque ranking;
- worker precarity;
- network concentration;
- data asymmetry;
- dependency and unilateral rule changes.

## 8. Benchmark D: centralized allocation

### Institutional rules
- a central authority allocates selected resources using submitted information and an explicit objective;
- enterprises or units execute plans;
- prices may be administered, absent or used as accounting signals depending on scenario;
- authority and appeal structures are specified.

### Required capabilities
Do not grant the planner perfect information. Model reporting delay, local knowledge, bureaucratic cost, political incentives, plan revision and enforcement. Include competent optimization algorithms so that the benchmark is not a straw man.

### Failure modes
- information bottlenecks;
- target distortion;
- local incentive problems;
- bureaucratic delay;
- political capture;
- weak feedback;
- concentration of decision power.

## 9. Benchmark E: federated cooperative system

### Institutional rules
- autonomous cooperatives coordinate through a federation;
- federation mandate is limited to shared services and cross-unit externalities;
- members fund common assets and elect or delegate representatives;
- local and federation-level decisions are distinct.

### Required capabilities
This baseline is especially important because it shares institutional features with SYNERGY. Compare whether digital twins, explicit SCI, UEP/UOF, AI and cellular adaptation add measurable value beyond a competent federation.

### Failure modes
- federation capture;
- weak enforcement of shared commitments;
- local free-riding;
- costly coordination;
- unequal influence by large members.

## 10. Benchmark F: conventional hybrid economy

Represent firms, markets, public services, transfers, financial institutions, regulation and civil society. This baseline is often the most realistic comparator for a real-world pilot. It should include the institutions and protections that exist in the target jurisdiction rather than an abstract laissez-faire caricature.

## 11. SYNERGY treatment arms

Separate the full architecture into staged arms:

| Arm | Components | Main question |
|---|---|---|
| S0 | Cellular organization, no AI, basic ledger | Does cell organization add value? |
| S1 | S0 + shared productive assets | Does shared capacity improve utilization? |
| S2 | S1 + inter-cell federation | Do cross-cell services justify federation cost? |
| S3 | S2 + plural ownership/distribution | What changes in distribution and investment? |
| S4 | S3 + UEP access pathways | Does effective participation improve? |
| S5 | S4 + UOF instruments | Is additionality positive after defaults and admin cost? |
| S6 | S5 + capped mutual credit | Does liquidity improve without excess contagion? |
| S7 | S6 + AI recommendations in shadow mode | Does AI improve forecasts and matching? |
| S8 | S7 + authorized bounded adaptation | Does approved adaptation improve out-of-sample outcomes? |

Do not deploy all components simultaneously in the first experiment. Staging improves causal interpretation and operational safety.

---

# Part III — Common initial conditions and parameter control

## 12. Initial population

Generate the same initial population for each treatment:
- household size and composition;
- skills and experience;
- time availability and care obligations;
- income and wealth distribution;
- firm size and sector;
- ownership concentration;
- debt and liquidity;
- access to infrastructure;
- geographic and network position.

Use a shared random seed for paired comparisons where possible. This reduces noise from different initial draws.

## 13. Endowment parity

Initial resources must be identical across treatments, except where the treatment explicitly changes allocation or access. Track:
- cash and settlement assets;
- productive assets;
- inventories;
- human capabilities;
- land and natural resources;
- intellectual assets;
- public infrastructure;
- legal rights and permits.

Do not give SYNERGY free capital through an unrecorded UOF grant while charging the baseline for capital. If UOF support is the treatment, record its source, opportunity cost, loss and counterfactual.

## 14. Parameter registry

Every parameter must have:
- name and definition;
- unit;
- value or distribution;
- source or rationale;
- calibration status;
- uncertainty interval;
- applicable treatment;
- version and change history.

Separate:
- empirical parameters;
- accounting identities;
- engineering constraints;
- normative weights;
- scenario assumptions;
- policy controls.

A normative choice must not be presented as an estimated scientific constant.

## 15. Behavioural parity

If agents in one treatment use AI forecasts, the comparator must either receive an equivalent forecasting capability or the experiment must explicitly test the incremental effect of AI. Use factorial treatment assignment to distinguish institutional form from information advantage.

## 16. Legal and ecological parity

All treatments face the same applicable labour, consumer, competition, privacy, insolvency, financial and environmental constraints. The model may test alternative policy regimes, but these must be separate experiment factors.

---

# Part IV — Scenario library

## 17. Baseline steady growth

Moderate demand growth, stable input prices, low shock intensity and normal asset depreciation. Purpose: establish baseline productivity, distribution, utilization and administrative cost.

## 18. Demand collapse

A sudden decline in final demand, followed by gradual recovery. Measure employment, liquidity, inventory accumulation, firm failure, household income and recovery time.

## 19. Supply-chain disruption

A critical input supplier or transport corridor becomes unavailable. Vary network centrality, substitutability, inventories, mutual aid and shared procurement.

## 20. Credit tightening

Interest rates rise, refinancing becomes scarce and collateral haircuts increase. Measure defaults, investment, liquidity shortfalls, contagion and public or collective loss exposure.

## 21. Correlated default shock

Several connected borrowers fail simultaneously. Test whether mutual-credit networks, guarantees and inter-cell claims amplify or contain losses.

## 22. Energy and resource shock

Energy prices rise or physical availability falls. Measure output, substitution, resource efficiency, ecological pressure and distributional incidence.

## 23. Technology discontinuity

A new technology changes productivity and skill demand. Measure adoption, displacement, training, ownership of new assets and concentration of gains.

## 24. Platform concentration shock

A dominant platform changes fees, ranking or access terms. Compare interoperability, multi-homing, local matching and dependency.

## 25. Governance capture

A large member, investor, administrator or AI operator attempts to capture decision-making. Test checks, minority rights, audit, rotation, appeals and exit.

## 26. Contribution-metric gaming

Agents optimize measured SCI dimensions while neglecting unmeasured quality, care, maintenance or safety. Test Goodhart effects, independent audits and multi-dimensional reporting.

## 27. Ecological threshold

A resource stock approaches a critical threshold or regeneration slows. Measure whether institutional incentives maintain resource constraints under short-run pressure.

## 28. Multi-shock compound crisis

Combine demand, credit, energy and supply disruptions with correlated timing. This is essential for tail-risk evaluation; independent single shocks are insufficient.

---

# Part V — Outcomes and measurement

## 29. Production and productivity

Measure:
- real gross output;
- value added;
- capital services;
- labour input and hours;
- labour productivity;
- multifactor productivity with clearly stated method;
- capacity utilization;
- quality-adjusted output;
- inventory and waste;
- innovation adoption.

Do not equate revenue growth with real output growth. Deflate nominal values and disclose quality adjustments.

## 30. Household prosperity

Measure:
- disposable income;
- median and lower-quantile income;
- income volatility;
- consumption of essential services;
- time autonomy;
- access to education and health-related services where within scope;
- debt-service burden;
- net wealth;
- financial resilience.

Use distributional tables and quantiles. Averages can conceal large losses among vulnerable households.

## 31. Ownership and concentration

Measure:
- asset ownership by type;
- beneficial ownership concentration;
- voting power concentration;
- control over infrastructure and data;
- dividend distribution;
- entry and exit;
- concentration by cell, sector and network.

Do not infer broad ownership from token-holder counts if beneficial control remains concentrated.

## 32. Access and participation

Measure:
- eligible population;
- application rate;
- approval rate;
- actual access;
- utilization;
- time-to-access;
- barriers and accommodations;
- project participation;
- grievance and appeal outcomes;
- effective exit and portability.

The number of accounts or registered users is not evidence of effective participation.

## 33. Financial stability

Measure:
- leverage;
- maturity mismatch;
- liquidity coverage under the declared model;
- default probability;
- loss given default;
- exposure concentration;
- network contagion;
- reserve adequacy;
- payment delay;
- insolvency and recovery;
- guarantee calls.

## 34. Ecological and lifecycle outcomes

Measure physical flows first:
- energy;
- materials;
- water;
- land;
- emissions;
- pollution;
- waste;
- regeneration;
- biodiversity or ecosystem indicators where reliable.

Monetary valuation may supplement but must not replace physical reporting.

## 35. Governance quality

Measure:
- participation and turnout;
- representation;
- concentration of proposals and agenda control;
- decision time;
- reversals and appeals;
- conflicts of interest;
- audit findings;
- member understanding;
- retaliation and exit;
- constitutional violations.

A high vote count does not necessarily imply meaningful participation.

---

# Part VI — Statistical and computational protocol

## 36. Replication and randomization

Run multiple independent seeds. Use paired seeds across treatments for common shocks and initial conditions. Report the number of runs and the full distribution of results.

## 37. Power and minimum detectable effects

Before running experiments, define a meaningful minimum effect for each primary outcome. Estimate variance from pilot runs, then choose replication count. Do not choose the number of runs after seeing which result looks favourable.

## 38. Uncertainty reporting

Report:
- means and medians;
- quantiles;
- confidence or credible intervals, as appropriate;
- run-to-run variability;
- parameter uncertainty;
- sensitivity to assumptions;
- worst-case or stress outcomes.

Distinguish stochastic simulation uncertainty from uncertainty about the real-world model.

## 39. Multiple comparisons

A large scenario matrix creates false-positive risk. Pre-register primary outcomes and treatment contrasts. Treat exploratory findings as exploratory and validate them in a separate run or dataset.

## 40. Calibration and holdout

Use separate data for:
- calibration;
- model selection;
- validation;
- out-of-sample evaluation.

Do not tune parameters on the same outcomes used to claim superiority. Preserve a locked evaluation configuration.

## 41. Ablation

Remove one component at a time or use factorial designs:
- no shared assets;
- no federation;
- no UOF;
- no mutual credit;
- no SCI;
- no AI;
- no collective dividends;
- no adaptive policy.

Ablation identifies dependencies and whether complexity earns its cost.

## 42. Cost accounting

Count not only visible platform costs but:
- governance time;
- audit and verification;
- dispute resolution;
- integration;
- privacy and security;
- capital and reserve cost;
- training and onboarding;
- failed projects;
- defaults and recoveries;
- ecological remediation.

A mechanism that improves output by consuming much more uncounted administrative labour may not be superior.

---

# Part VII — Pre-registration template

## 43. Mandatory experiment record

Every experiment begins with a record containing:

| Field | Required declaration |
|---|---|
| Experiment ID | Stable identifier |
| Research question | One primary question |
| Hypothesis | Directional or non-directional and falsifiable |
| Treatment | Exact institutional components |
| Comparator | Fully specified baseline |
| Population | Agents, firms, cells, sector and geography |
| Initial conditions | Endowments and random seed procedure |
| Primary outcome | One or a small declared set |
| Secondary outcomes | Additional metrics |
| Time horizon | Number and duration of periods |
| Parameter source | Empirical, assumed or normative |
| Exclusions | Pre-specified |
| Statistical plan | Replication and uncertainty method |
| Failure criterion | What result rejects the hypothesis |
| Code and data version | Reproducible identifiers |
| Deviations | Logged with date and reason |

## 44. Example preregistration: shared productive assets

**Question:** Does shared ownership/access increase productive asset utilization without reducing maintenance quality or increasing coordination cost excessively?

**Treatment:** Cells may schedule shared assets under published access, fee, maintenance and dispute rules.

**Comparator:** Equivalent firms own or rent separate assets under the same capital and technology constraints.

**Primary outcome:** verified productive utilization net of downtime.

**Secondary outcomes:** output, quality, maintenance expenditure, scheduling delay, access distribution, asset lifecycle cost and dispute rate.

**Failure criterion:** utilization rises but lifecycle cost, quality failure or exclusion worsens beyond the predeclared tolerance.

This example is a template, not a reported result.

---

# Part VIII — Decision criteria and rejection rules

## 45. No universal winner score

A dashboard should show a vector of outcomes and trade-offs. If a decision body chooses weights to create a composite index, those weights are normative and must be published. Provide Pareto comparisons and identify dominated treatments where possible.

## 46. Conditions for a conditional SYNERGY advantage

A claim of advantage requires:
- reproducible improvement in a predeclared outcome;
- comparison with a competent baseline;
- robustness across plausible parameters;
- no hidden transfer of costs;
- no violation of rights, solvency or ecological constraints;
- acceptable administrative and governance cost;
- distributional reporting showing who benefits and who loses.

## 47. Conditions for rejection or redesign

Reject or materially revise a component if:
- it does not outperform a simpler mechanism after full costs;
- results depend on unrealistic information or perfect compliance;
- it increases financial contagion or hidden liabilities;
- it systematically concentrates ownership or governance;
- it reduces effective access or meaningful exit;
- it requires intrusive surveillance disproportionate to benefit;
- it violates ecological or legal constraints;
- it cannot be independently audited;
- its apparent benefit disappears under reasonable alternative assumptions.

A failed component does not automatically invalidate the whole programme. It identifies which mechanism should be removed, constrained or redesigned.

---

# Part IX — Reporting standard

## 48. Minimum publication package

Publish:
- research question and preregistration;
- model version and commit;
- treatment definitions;
- initial conditions;
- parameter registry;
- random seeds;
- data provenance;
- code and environment manifest;
- outcome definitions;
- full result distributions;
- robustness and sensitivity;
- failed tests and adverse events;
- deviations from protocol;
- limitations and external validity.

## 49. Visualizations

Every report should include, as appropriate:
- time-series paths with uncertainty bands;
- income and wealth distributions;
- ownership and voting concentration;
- network maps and contagion paths;
- resource stocks and flows;
- default and recovery distributions;
- Pareto frontiers;
- ablation comparisons;
- calibration and forecast diagnostics.

Charts must not hide uncertainty or use truncated axes to exaggerate differences.

---

# Part X — Research roadmap

## 50. Sequence

1. Implement a common synthetic economy and validate accounting.
2. Implement market and cooperative baselines.
3. Implement cell organization without additional finance or AI.
4. Add shared assets and federation.
5. Add plural distribution and ownership.
6. Add UEP access pathways.
7. Add UOF instruments with full portfolio accounting.
8. Add mutual credit and stress testing.
9. Add AI forecasts in shadow mode.
10. Test bounded adaptation only after shadow evaluation.
11. Run compound shocks and adversarial governance tests.
12. Publish null and negative results before any large-scale deployment claim.

## 51. Research status

This volume is an experimental protocol proposal. No performance result is claimed. Benchmark definitions require sectoral and jurisdictional refinement. Empirical calibration and controlled pilots remain future work.

**The governing rule:** SYNERGY must earn every claim of superiority through fair comparison, complete cost accounting, reproducibility, robustness and transparent reporting. The model must be allowed to fail.
