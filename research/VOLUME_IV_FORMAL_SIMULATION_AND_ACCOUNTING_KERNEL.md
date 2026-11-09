# VOLUME IV — FORMAL SIMULATION AND ACCOUNTING KERNEL
## A reproducible computational specification for consortium-cells, production networks, financial integrity and distributive mechanisms

**Research program:** SYNERGISTIC ECONOMICS  
**Document ID:** SYNERGY-ECON-V4-001  
**Version:** 0.1 — 9 November 2026  
**Status:** Technical target specification. The repository now contains a minimal accounting kernel and two partial economic simulation prototypes; they do not yet implement or validate the complete simulator specified in this volume.  
**Preceding volumes:** [Volume 0](VOLUME_0_SYNTHESIS_OF_ECONOMIC_SCHOOLS.md); [Volume 0A](VOLUME_0A_AXIOM_RECONCILIATION_AND_METHOD_AUDIT.md); [Volume I](VOLUME_I_FOUNDATIONS.md); [Volume II](VOLUME_II_MULTIDIMENSIONAL_VALUE_AND_PRODUCTION.md); [Volume III](VOLUME_III_CONTRIBUTION_OWNERSHIP_AND_DISTRIBUTION.md)  
**Institutional architecture:** [SYNERGY Cellular Consortium Economy](SYNERGY_CELLULAR_CONSORTIUM_ECONOMY.md)

---

## Abstract

This volume converts the conceptual architecture of SYNERGISTIC ECONOMICS into a formal simulation and accounting specification. It defines the model boundary, agent and institution classes, state variables, event types, accounting identities, production and network transitions, contribution evidence, ownership and claim registries, distributable-surplus calculations, governance permissions, policy-learning boundaries, experiment design and mandatory validation tests.

The central engineering principle is **event-sourced, double-entry, deterministic and auditable simulation**. Every state change must be explained by a typed event, every financial movement must reconcile across accounts, every cross-cell obligation must have a counterparty and settlement state, and every model-generated estimate must remain distinguishable from observed or legally established facts.

The simulator must not assume that token issuance creates wealth, that credit principal is income, that an internal transfer creates consolidated output, that an SCI score establishes ownership, or that an AI recommendation is an authorized transaction. It must model production, finance, distribution, governance and ecology as related but distinct layers.

This document is a specification for research software. It does not claim that a simulator has been built, that its parameters are calibrated, or that any policy has been empirically shown to outperform alternatives.

---

# Part I — Modeling contract

## 1. Purpose and non-purpose

### 1.1 Purpose

The simulator is intended to compare economic mechanisms under controlled assumptions and to test whether the SYNERGY architecture improves specified outcomes relative to credible baselines. It should support:
- heterogeneous agents and firms;
- production with complementary inputs;
- markets and contracts;
- voluntary consortium-cells and federations;
- shared and privately owned assets;
- double-entry accounting and financial claims;
- credit, liquidity, default and loss allocation;
- contribution evidence and alternative distribution rules;
- UEP and UOF access mechanisms;
- collective dividends and common assets;
- bounded AI recommendations and governance approval;
- ecological constraints and externalities;
- shocks, failures, exit and recovery;
- reproducible experiments and sensitivity analysis.

### 1.2 Non-purpose

The simulator is not:
- a universal oracle for justice;
- a replacement for legal, accounting or tax advice;
- a proof that the proposed economic system works in reality;
- a production payment processor;
- a substitute for a verified identity or legal registry;
- a mechanism for ranking human worth;
- an unconstrained AI agent with authority to change rules;
- a token-price maximization engine.

### 1.3 Evidence labels

Every output and claim must carry one of these labels:

| Label | Meaning |
|---|---|
| Conceptual | A proposed definition or mechanism |
| Analytical | A result derived from stated equations |
| Synthetic simulation | A result from assumed synthetic parameters |
| Calibrated simulation | A result using parameters estimated from empirical data |
| Historical replay | A model replay of a documented historical period |
| Controlled pilot | A real-world test with defined treatment and comparison |
| Operationally audited | Evidence independently audited in a live system |

A synthetic simulation must never be described as empirical proof.

## 2. Model boundaries and units

A simulation run must declare:
- geography and legal jurisdiction represented;
- sector and technology;
- start and end periods;
- time-step duration;
- currency and price basis;
- nominal or real accounting convention;
- production and asset boundaries;
- included and excluded externalities;
- population and agent-generation process;
- market and institutional mechanisms;
- policy versions and random seeds.

The minimum model should distinguish five units:

1. **Agent:** person, household, enterprise, investor, public body or community.
2. **Project:** bounded production or investment activity with defined participants and claims.
3. **Cell:** voluntary economic collective with governance, assets, treasury and obligations.
4. **Network:** graph of agents, projects, cells, markets and shared infrastructure.
5. **Economy:** consolidated boundary used to calculate aggregate output, income, wealth, liabilities and externalities.

The same agent may belong to multiple projects and cells. Membership must not imply exclusive ownership of the agent's identity, labour, data or other relationships.

---

# Part II — State model and entity schema

## 3. Canonical entity classes

The implementation should use stable identifiers and typed references. Names are display attributes, not primary keys.

| Entity | Core state | Required relationships |
|---|---|---|
| Person | skills, time, needs, capabilities, preferences, consent | household, employment, projects, cells |
| Household | members, resources, obligations, shared needs | persons, assets, public services |
| Enterprise | production capacity, contracts, assets, cash, debt | owners, workers, suppliers, customers, cells |
| Project | scope, milestones, budget, technology, participants | enterprise, persons, assets, contracts |
| Asset | title, condition, capacity, location, encumbrances | owners, operators, projects, liabilities |
| Cell | constitution, members, treasury, funds, governance | persons, enterprises, projects, cells |
| Federation | mandate, shared infrastructure, rules, reserves | member cells and external institutions |
| Market | goods, prices, bids, offers, matching rules | buyers, sellers, exchanges |
| Fund | mandate, capital, risk limits, allocation policy | sponsors, applicants, beneficiaries |
| Contract | parties, obligations, schedule, remedies, law | agents, projects, assets |
| Account | owner, currency, account type, balance | ledger transactions |
| Claim | claimant, debtor, amount, priority, status | contract, asset, court or registry |
| Ecological resource | stock, flow, regeneration, quality | users, geography, ecological boundary |
| Governance proposal | author, scope, parameters, votes, authority | cell, federation, constitution |

Each entity needs creation time, effective time, update time, status, provenance and version. Deletion should normally be represented by a tombstone or closure event, not by erasing history.

## 4. State vector

For agent or institution (i), define a state vector:

[
X_i(t)=
[R_i(t),K_i(t),H_i(t),L_i(t),O_i(t),C_i(t),G_i(t),E_i(t)]
]

where:
- (R_i): liquid resources and cash;
- (K_i): productive assets and capital services;
- (H_i): human capabilities, skills and available time;
- (L_i): liabilities and financial claims;
- (O_i): ownership and governance rights;
- (C_i): contracts, commitments and obligations;
- (G_i): network position and relationships;
- (E_i): ecological and externality exposure.

This vector is a modeling abstraction. It must not store a person's full private life or sensitive attributes merely because they might be predictive.

## 5. Typed state and provenance

Every field should declare:
- data type and unit;
- allowed range;
- whether it is observed, declared, contractual, estimated or simulated;
- source and verification method;
- effective period;
- confidence or quality indicator;
- access classification;
- correction and appeal route.

A missing value is not zero. An estimated value is not a verified fact. A forecast is not a commitment. A signed contract is not proof that performance occurred.

---

# Part III — Event-sourced transition architecture

## 6. Event model

All state changes are represented as immutable, typed events. An event minimally contains:

[
e=(id,type,actor,subject,object,time_{event},time_{recorded},payload,source,version)
]

Required fields:
- globally unique event identifier;
- event type;
- authorized initiator;
- affected entity identifiers;
- effective timestamp and recorded timestamp;
- payload with typed units;
- evidence or source reference;
- policy and schema version;
- idempotency key;
- status: proposed, authorized, executed, settled, disputed, reversed or expired.

Events should be append-only. Corrections are new events that reference and supersede or reverse the prior event. Never silently rewrite historical facts.

## 7. Minimum event catalogue

### 7.1 Economic events
- resource produced, consumed, transferred or lost;
- work assigned, accepted, rejected or corrected;
- product delivered and quality verified;
- service performed;
- asset acquired, leased, maintained, impaired or disposed;
- inventory received, transformed or shipped;
- price quote, order, match, cancellation and settlement.

### 7.2 Financial events
- capital contribution;
- loan origination;
- interest accrual;
- repayment;
- drawdown;
- fee charged;
- invoice issued;
- payable or receivable recognized;
- payment instruction;
- settlement confirmation;
- reserve allocation;
- impairment and write-off;
- default and recovery;
- dividend declared and paid;
- token minted, burned, locked or transferred.

### 7.3 Governance events
- proposal submitted;
- authority check passed or failed;
- vote cast;
- quorum reached or failed;
- decision approved, rejected or appealed;
- mandate changed;
- policy version activated;
- emergency pause and resumption.

### 7.4 Contribution and distribution events
- contribution evidence submitted;
- evidence independently verified;
- SCI calculated;
- SCI challenged;
- correction approved;
- distributable pool calculated;
- allocation proposed;
- allocation authorized;
- payment executed;
- payment disputed or reversed.

### 7.5 Ecological and social events
- resource extraction;
- regeneration or restoration;
- emission or waste release;
- safety incident;
- external harm report;
- remediation performed;
- access barrier identified;
- UEP or UOF service delivered.

## 8. Deterministic state transition

The transition engine is deterministic conditional on:
- prior state;
- ordered events;
- policy version;
- explicit random seed for stochastic modules.

[
X(t+1)=T(X(t),E_t,	heta_v,omega_t)
]

where (	heta_v) is the versioned parameter set and (omega_t) is the recorded random input. The simulator must be able to replay a run from its initial state and event stream and reproduce the same result.

Policy learning must not mutate the historical transition function. A learned policy is a candidate artifact with its own version and evaluation report.

## 9. Event ordering and concurrency

The simulator must define:
- event-time versus record-time semantics;
- deterministic ordering for simultaneous events;
- conflict resolution for competing resource claims;
- idempotent processing;
- duplicate detection;
- partial failure and retry behavior;
- rollback and compensating events;
- cross-cell event finality.

A transaction that is recorded twice must not settle twice. A payment instruction is not settlement. A settlement event requires evidence from the designated settlement mechanism.

---

# Part IV — Accounting and financial integrity

## 10. Double-entry ledger

Every financial transaction must generate balanced entries for each currency and accounting entity:

[
sum Debits_{a,c,t}=sum Credits_{a,c,t}
]

where (a) is the accounting entity and (c) the currency or unit of account.

Minimum account classes:
- cash and settlement assets;
- receivables;
- inventory;
- productive fixed assets;
- accumulated depreciation or impairment;
- payables;
- loans and other debt;
- equity or member capital;
- retained earnings;
- revenue;
- operating expense;
- financing expense;
- taxes;
- reserves and restricted funds;
- contingent liabilities and guarantees, tracked separately as required.

The implementation must specify whether each account is balance-sheet, income-statement, memorandum or statistical. A token balance should not be inserted into cash merely because it is denominated in a currency-like unit.

## 11. Conservation and reconciliation invariants

Mandatory tests:

1. Every journal transaction balances by entity and currency.
2. No account spends more available cash than its permitted balance or credit limit.
3. Every receivable has a debtor or recognized counterparty.
4. Every payable has a creditor and due date.
5. Every inter-cell transfer has equal and opposite counterpart entries.
6. Consolidation eliminates internal claims and transfers.
7. Debt principal is not recognized as operating income.
8. Repayment of principal reduces cash and debt; it is not a second expense.
9. Equity issuance changes financing/equity accounts, not production output by itself.
10. Token issuance does not create productive assets or income by itself.
11. Collateral is not counted simultaneously as unencumbered wealth and fully available liquidity.
12. Guarantees and contingent exposures are not omitted from risk reports.
13. A declared dividend cannot exceed the legally and financially distributable pool.
14. Reserves cannot be allocated twice.
15. Currency conversion records rate, timestamp, source and spread.

## 12. Entity-level and consolidated accounting

The system must produce both:
- entity-level statements, preserving obligations and legal boundaries;
- consolidated statements, eliminating internal transfers and claims within the selected perimeter.

A cell's receipt from another cell may be revenue for the receiving entity under a valid contract, but it is not automatically new consolidated output. The consolidated system must identify the underlying external sale, production or service.

## 13. Liquidity, solvency and maturity mismatch

Liquidity and solvency are distinct:
- liquidity: ability to meet payments when due;
- solvency: assets and expected realizable value sufficient relative to liabilities under the applicable accounting and legal basis.

Track maturity buckets, restricted cash, collateral, haircuts, contingent liabilities, concentration, correlated exposures and settlement delays. A profitable but illiquid entity may default. A liquid entity may still be insolvent.

## 14. Credit and mutual-credit facility

A credit facility requires:
- borrower and lender identity;
- principal, currency and schedule;
- interest or fee rule;
- maturity and grace period;
- collateral or guarantee if any;
- covenant and default triggers;
- loss allocation;
- legal enforceability;
- exposure cap;
- concentration and correlation controls.

Mutual credit can facilitate exchange but does not create external purchasing power by itself. The model must track the network's net positions, settlement assets, capacity to accept obligations, default correlations and limits. Negative balances are liabilities or credit exposure, not free money.

## 15. Loss waterfall

A project or fund must publish its loss waterfall before accepting capital. Candidate layers:
1. operating contingency and project reserve;
2. explicitly subordinated risk capital;
3. insurance or capped guarantee, if valid;
4. senior capital according to legal priority;
5. residual equity loss.

This is illustrative. Actual priority depends on law, contract, security, insolvency and fund structure. The simulator must never assume that losses can be reassigned to participants who did not agree to bear them.

---

# Part V — Production, markets and network economy

## 16. Production function module

Each enterprise or project may use a configurable production function:

[
Y=f(L,K,M,E,T,O)
]

where labour (L), capital services (K), materials (M), energy (E), technology (T) and organization (O) are inputs. The selected functional form and parameterization must be explicit.

Candidate families:
- Cobb–Douglas for tractable baseline;
- CES for variable substitution;
- Leontief for fixed-proportion bottlenecks;
- Translog for flexible local approximation;
- input-output production networks;
- agent-defined process recipes and capacity constraints.

Do not select Cobb–Douglas merely because it is convenient. Test sensitivity to functional form and compare against physical process constraints.

## 17. Capacity and inventory

Production is constrained by:
- installed capacity;
- labour availability and skills;
- equipment uptime;
- input inventory;
- energy and water;
- logistics;
- quality requirements;
- permits and legal limits;
- ecological carrying capacity.

Inventory obeys:

[
Inventory_{t+1}=Inventory_t+Receipts_t-Consumption_t-Shipments_t-Spoilage_t
]

Negative inventory is prohibited unless the model explicitly represents backorders or short positions.

## 18. Markets and prices

Market module options:
- posted prices;
- bilateral bargaining;
- double auction;
- order book;
- procurement tender;
- internal transfer pricing.

A price is an exchange term under a specific market structure, not a direct measure of total social value. Market power, liquidity, information, transaction costs, taxes and externalities affect observed prices.

The simulator should support both decentralized market allocation and institutional allocation so the alternatives can be compared rather than assumed.

## 19. Network representation

Represent the economic system as a typed, temporal, directed graph:

[
G_t=(V_t,E_t)
]

Nodes may be people, firms, cells, assets, projects, funds, markets or resources. Edges may represent ownership, employment, supply, credit, membership, governance, licence, dependency, settlement or ecological impact.

Every edge must carry:
- type;
- direction;
- validity period;
- quantity or limit where relevant;
- evidence;
- legal or contractual status;
- confidence and provenance.

Network effects must be modeled as potential benefits and costs. Increased connectivity can improve matching and knowledge diffusion but can also increase contagion, surveillance, concentration and systemic dependence.

---

# Part VI — Contribution, ownership and distribution kernel

## 20. Separate registries

The kernel must maintain separate, linked registries:

1. **Contribution registry:** evidence of work, care, maintenance, innovation, coordination and other inputs.
2. **Ownership registry:** legal or constitutional title, beneficial interest and transfer history.
3. **Contract registry:** payment, delivery, licence, debt, guarantee and service obligations.
4. **Governance registry:** voting, delegation, mandate and decision rights.
5. **Distribution registry:** approved pool, eligibility, formula, calculation, appeal and settlement.

No one registry may be used as a substitute for another.

## 21. SCI calculation service

Input:
- project and period;
- eligible participants and roles;
- indicator definitions and units;
- evidence references;
- pre-approved weights;
- normalization method;
- missing-data and uncertainty policy;
- audit and appeal status.

Output:
- raw indicator profile;
- normalized profile;
- weights and version;
- composite score, if permitted by the project constitution;
- confidence and data-quality flags;
- sensitivity range;
- audit trail.

The SCI service must not update ownership shares automatically. Any use of SCI in a reward formula must be authorized by a pre-existing project rule and remain appealable.

## 22. Distributable pool calculation

The kernel computes the distributable pool from recognized and available funds, not from gross activity or token balances.

[
S_{dist}=Cash_{available}-Claims_{due}-Taxes_{due}-Reserve_{required}-ApprovedReinvestment
]

The expression is a simplified control formula. The actual computation must follow the entity's accounting basis, applicable law, liquidity restrictions, covenants and distribution rules.

A non-cash accounting profit must not be paid out as if it were cash. A positive pool estimate must be rechecked at payment time.

## 23. Allocation engine

The allocation engine should support:
- contractual waterfall;
- equal member allocation;
- ownership-weighted allocation;
- contribution-weighted allocation;
- needs/access allocation;
- collective reinvestment;
- hybrid multi-pool distribution;
- externally computed bargaining or cooperative-game reference.

Every allocation result records:
- pool size and source;
- eligible set;
- excluded set and reason;
- formula and parameter version;
- input evidence;
- rounding method;
- unallocated remainder;
- review and appeal status;
- final settlement reference.

The engine must reject:
- negative pool;
- sum of allocations exceeding pool;
- duplicate recipient identity within the same pool;
- invalid or expired ownership claims;
- unresolved disputed claims where the constitution requires suspension;
- unapproved formula version;
- unauthorized retroactive changes.

## 24. Rounding and residual handling

Rounding is an economic allocation decision. Define:
- smallest settlement unit;
- deterministic rounding method;
- treatment of residual dust;
- whether dust is retained, donated or allocated by a disclosed tie-break rule.

Never allow the implementation order to determine who receives residual value accidentally.

---

# Part VII — UEP and UOF modules

## 25. UEP service

The UEP module tracks four distinct channels:
1. basic guarantees;
2. access to productive assets;
3. verified-contribution rewards;
4. collective results.

It must not merge them into one balance or imply that a person loses basic rights by failing to contribute to a project.

For every access programme, record:
- eligibility and lawful basis;
- offered service or asset;
- actual access and use;
- costs and funding source;
- barriers and accommodations;
- outcomes and additionality;
- complaint and appeal.

## 26. UOF portfolio engine

The UOF module must separate instrument classes:
- grant;
- loan;
- guarantee;
- lease;
- shared-asset access;
- equity or cooperative participation;
- procurement commitment;
- training or capability service.

A portfolio decision should consider additionality, feasibility, access barrier, expected impact, downside, correlated exposure and fund mandate. Do not use expected financial return as the sole criterion for a fund whose mandate includes capability or public-good outcomes.

## 27. UOF risk and impact accounting

Track:
- committed capital;
- disbursed capital;
- outstanding principal;
- repayments;
- realized loss;
- provision and expected loss;
- guarantees called;
- asset utilization;
- beneficiary outcomes;
- displacement or deadweight;
- administrative costs;
- concentration by sector, geography and counterparty.

A grant expense, a loan asset and a guarantee exposure are not the same accounting object.

---

# Part VIII — Governance, AI and constitutional control

## 28. Authority matrix

Every action must map to an authority class:

| Action | Proposal | Authorization | Execution | Audit |
|---|---|---|---|---|
| Forecast or recommendation | AI, member or analyst | Not applicable unless policy says otherwise | None | Model and data audit |
| Project budget | Project team | Authorized project body | Treasurer or system | Independent review |
| Credit approval | AI may assist | Authorized credit committee or mandate | Treasury/payment system | Credit and compliance audit |
| SCI weight change | Participant or analyst may propose | Project governance under constitution | Versioned calculation service | Bias and impact audit |
| Dividend declaration | Treasury or members may propose | Authorized governing body | Payment agent | Accounting audit |
| Constitutional change | Eligible members or body | Constitution-defined supermajority/process | Versioned governance system | Independent process audit |

The exact bodies vary by legal form. The matrix must be completed before live operation.

## 29. AI action boundary

AI components may:
- forecast demand and capacity;
- recommend matching and routing;
- detect anomalies;
- simulate policy alternatives;
- estimate risk and uncertainty;
- propose parameter changes within a defined mandate.

AI must not autonomously:
- change constitutional rights;
- mint unbacked claims;
- transfer funds outside approved authority;
- alter ownership title;
- impose debt;
- determine legal guilt;
- suppress appeals;
- rewrite historical records;
- expand its own permissions.

A model's recommendation, a governance authorization, an execution command and a settlement confirmation are separate events.

## 30. Policy-learning isolation

Separate:
- environment transition;
- policy proposal;
- offline training;
- evaluation;
- authorization;
- deployment;
- monitoring;
- rollback.

A candidate policy must be evaluated out of sample and against fixed baselines. It must not train on future information, leak test data or change the historical data-generating process during an experiment.

Use shadow mode before execution. Every deployed policy has a version, scope, owner, approval, start time, expiry or review date, performance envelope and rollback trigger.

---

# Part IX — Ecological and social constraints

## 31. Physical resource accounting

For each critical resource:

[
Stock_{t+1}=Stock_t+Regeneration_t+Restoration_t-Extraction_t-Degradation_t
]

The simulator must enforce physical bounds. Regeneration cannot exceed plausible ecological processes simply because a policy requires it. For non-renewable resources, extraction and depletion must be reported explicitly.

## 32. Externality ledger

Record costs and benefits that fall outside the immediate contracting parties:
- emissions;
- pollution;
- water and land pressure;
- health and safety harms;
- congestion;
- ecosystem degradation;
- knowledge spillovers;
- public infrastructure use;
- unpaid care and community burdens.

Externality estimates must be distinguished from cash liabilities. Monetization may be useful for some comparisons but should not erase non-substitutable ecological or rights constraints.

## 33. Constraint-first optimization

The model should optimize only within declared constraints. Examples:
- essential-service minimums;
- occupational safety;
- legal rights;
- ecological stock and flow limits;
- debt and liquidity caps;
- concentration limits;
- privacy and data minimization;
- minimum appeal and due-process requirements.

A high aggregate welfare estimate cannot compensate for a prohibited rights violation.

---

# Part X — Experiment framework and baselines

## 34. Required baseline mechanisms

Every claimed improvement must be compared with relevant baselines:
1. independent firms and bilateral contracts;
2. conventional market allocation;
3. centralized planner with the same information constraints;
4. cooperative enterprise;
5. federated cooperative network;
6. platform-mediated matching;
7. static rules without AI;
8. AI recommendations without authority to execute;
9. no UOF or UEP intervention;
10. simpler distribution mechanisms.

The baseline must be implemented fairly. A deliberately weak baseline invalidates the comparison.

## 35. Experiment matrix

Vary:
- cell size and network density;
- input complementarity;
- agent heterogeneity;
- market concentration;
- information quality;
- transaction and coordination costs;
- trust and default probability;
- access to capital and productive assets;
- shocks and volatility;
- ecological scarcity;
- governance participation;
- metric noise and strategic gaming;
- AI forecast quality and drift;
- externality intensity.

Use factorial or fractional-factorial designs where feasible. Record random seeds and parameter files.

## 36. Outcome vector

Report outcomes as a vector rather than an opaque single score:

[
Y=(Output,Productivity,MedianIncome,LowerQuantileIncome,WealthConcentration,
Access,Innovation,Resilience,Solvency,Ecology,Agency,ProceduralFairness)
]

Each element needs a definition, unit, time horizon and aggregation rule. If a composite index is used for a particular experiment, publish its normative weights and show the unweighted outcomes as well.

## 37. Statistical discipline

- Pre-register primary outcomes and hypotheses.
- Separate calibration data from evaluation data.
- Use repeated runs and uncertainty intervals.
- Report effect sizes, not only significance tests.
- Test sensitivity to initial conditions and parameter choices.
- Include negative controls and placebo tests.
- Report failures and adverse outcomes.
- Use out-of-sample evaluation for adaptive policies.
- Compare computational cost and data requirements.
- Avoid overclaiming external validity from synthetic agents.

---

# Part XI — Test suite and red-team requirements

## 38. Accounting tests

- double-entry balance for every transaction;
- consolidated elimination of internal transfers;
- no phantom cash or liquidity;
- no double-counted collateral;
- no duplicate debt or repayment;
- dividend limited by distributable funds;
- no principal counted as income;
- token issuance does not create real output;
- event replay reproduces identical balances.

## 39. Production and physical tests

- no negative inventory without backorder state;
- production cannot exceed capacity;
- input and output conservation;
- no impossible resource regeneration;
- quality failure affects accepted output;
- downtime reduces available capacity;
- logistics capacity and timing are enforced.

## 40. Rights and governance tests

- unauthorized actors cannot execute restricted actions;
- AI cannot expand its own permissions;
- expired mandate is rejected;
- appeal suspends only the disputed claim where required;
- no retroactive ownership change by SCI;
- exit preserves accrued lawful claims;
- private data is not exposed by public aggregation;
- a constitutional prohibition cannot be overridden by local policy.

## 41. Distribution tests

- allocation sums do not exceed pool;
- each recipient is eligible under the approved version;
- ownership and contribution registries remain distinct;
- missing SCI data is not treated as zero or maximum;
- weights sum to one where required;
- equal pool is allocated using the declared membership snapshot;
- rounding residual is handled deterministically;
- externalities and reserve needs are not silently ignored.

## 42. Adversarial tests

At minimum simulate:
- collusive SCI inflation;
- Sybil membership;
- false oracle data;
- insider treasury transfer;
- double-spend and duplicate event;
- delayed settlement;
- correlated defaults;
- asset-price collapse;
- governance capture;
- AI model drift;
- hostile parameter update;
- data breach;
- ecological shock;
- sudden exit of a major cell;
- false claim of token-backed ownership;
- strategic underinvestment in maintenance;
- transfer of losses to an unrepresented party.

Each test must specify attack preconditions, expected control, failure signal and severity.

---

# Part XII — Reference execution pipeline

## 43. One simulation step

A canonical step should execute in this order:

1. Load state snapshot and active policy versions.
2. Validate incoming events and authorization.
3. Apply exogenous shocks and declared constraints.
4. Update agent resources, skills, needs and availability.
5. Match markets, contracts and production inputs.
6. Execute production and logistics subject to capacity.
7. Record output, quality, inventory and resource flows.
8. Calculate financial accruals and post double-entry journals.
9. Update obligations, settlement, liquidity and default states.
10. Update contribution evidence without changing ownership.
11. Calculate candidate SCI profiles where scheduled.
12. Evaluate UEP and UOF access and outcome events.
13. Apply authorized distributions and collective reinvestment.
14. Update network and ecological state.
15. Run invariants, anomaly checks and audit summaries.
16. Persist event stream, state hash, random seed and run metadata.

A step must fail closed if a critical accounting or rights invariant is violated. The system may continue in a quarantined diagnostic mode, but it must not silently publish an invalid result as a valid economic outcome.

## 44. Reproducibility package

Each run must export:
- model version and code commit;
- schema version;
- parameter file;
- initial conditions;
- random seed;
- event stream or reproducible generator;
- policy versions;
- data provenance manifest;
- test results;
- summary metrics;
- warnings and failed invariants;
- environment and dependency manifest.

A result without this package is not a reproducible research result.

---

# Part XIII — Build roadmap

## 45. Implementation sequence

### Stage 1 — Pure accounting kernel
Implement accounts, journals, transaction validation, consolidation, receivables, payables, cash and debt. Do not begin with tokenomics or AI.

### Stage 2 — Event-sourced entities
Implement typed entities, stable IDs, immutable events, replay, idempotency and versioned schemas.

### Stage 3 — Production and inventory
Implement a small production network with capacity, inventories, quality, assets and resource constraints.

### Stage 4 — Contracts and markets
Implement orders, matching, contracts, delivery, invoicing and settlement.

### Stage 5 — Cells and governance
Implement membership, mandates, proposals, voting, treasury permissions, exit and appeal.

### Stage 6 — Contribution and distribution
Implement separate registries, shadow SCI, candidate allocation mechanisms, pool constraints and audit trail.

### Stage 7 — UEP and UOF
Implement access services, fund instruments, portfolio limits, additionality and impact tracking.

### Stage 8 — AI decision support
Add forecasts, matching and risk models in shadow mode, with evaluation and rollback.

### Stage 9 — Comparative simulation
Run baseline comparisons, stress tests, calibration and sensitivity analysis.

### Stage 10 — Controlled real-world pilot
Only after legal, security, accounting, governance and privacy review. Begin with non-custodial or low-risk workflows and limited financial exposure.

## 46. Minimum viable simulation

The first integrated prototype for the full target architecture should eventually contain:
- 7 heterogeneous cells;
- 30–100 agents across persons, enterprises and funders;
- 3–5 production sectors;
- at least 2 shared productive assets;
- one cross-cell supply chain;
- one market and one contract-based allocation channel;
- a double-entry ledger;
- a bounded credit facility;
- three ownership structures;
- four distribution mechanisms;
- SCI in shadow mode;
- a small UOF portfolio;
- ecological resource constraints;
- fixed-rule and AI-recommendation baselines;
- full event replay and invariant tests.

These are starting experiment dimensions, not empirically established optimal values. The prototype should be small enough to inspect and large enough to expose network interactions.

---

# Part XIV — Open technical decisions

Before implementation, resolve and document:

1. Discrete-time versus event-driven continuous-time simulation.
2. Base currency and multi-currency accounting.
3. Nominal versus real prices and deflators.
4. Legal entity and consolidation boundaries.
5. Exact event schema and canonical ID strategy.
6. Production function library and calibration approach.
7. Market matching mechanism for the first benchmark.
8. Contract default and insolvency representation.
9. Ownership and beneficial-interest data model.
10. SCI normalization and missing-data policy.
11. UOF portfolio mandate and loss waterfall.
12. Privacy architecture and data access controls.
13. Governance quorum and delegation model.
14. AI policy-evaluation and rollback thresholds.
15. Externality measurement and non-monetary constraints.
16. Experiment pre-registration and artifact publication.

No unresolved decision should be hidden in implementation defaults. Every default must be explicit, versioned and testable.

---

# Part XV — Selected methodological references

- Tesfatsion, L. (2003). “Agent-based computational economics: modeling economies as complex adaptive systems.” *Information Sciences*, 149(4), 262–268. https://doi.org/10.1016/S0020-0255(02)00280-3
- Ostrom, E. (2010). “Beyond Markets and States: Polycentric Governance of Complex Economic Systems.” *American Economic Review*, 100(3), 641–672. https://doi.org/10.1257/aer.100.3.641
- Stiglitz, J. E., Sen, A. & Fitoussi, J.-P. (2009). *Report by the Commission on the Measurement of Economic Performance and Social Progress*.
- OECD (2009). *Measuring Capital: OECD Manual*, Second Edition. https://doi.org/10.1787/9789264193260-en
- World Bank (2024). *The Changing Wealth of Nations 2024*.
- United Nations Statistics Division (2025). *System of National Accounts 2025*. https://unstats.un.org/unsd/econstats/national-accounts/sna2025
- Shapley, L. S. (1953). “A Value for n-Person Games.” In *Contributions to the Theory of Games II*.
- North, D. C. (1990). *Institutions, Institutional Change and Economic Performance*. Cambridge University Press.
- NIST. *Digital Twin Standardization*. https://www.nist.gov/digital-twins/digital-twin-standardization

---

# 16. Research status and limitations

This specification defines a target architecture and an integrated minimum research prototype. The repository now contains an executable accounting kernel, a seven-cell simulation, a general input-output simulation and an initial canonical schema. These are partial components, not a complete implementation of this specification. The schema remains subject to revision, and the integrated system has not passed independent security, accounting, legal or empirical validation.

The mathematical model and comparative simulation programme are developed in [Volume V — Executable Economic Model](VOLUME_V_EXECUTABLE_ECONOMIC_MODEL.md). The next implementation artifact should be a versioned technical package containing:
- JSON Schema or equivalent typed definitions for entities and events;
- a minimal double-entry ledger implementation;
- deterministic replay;
- unit and property-based tests for accounting invariants;
- a small synthetic production network;
- benchmark policies and experiment configuration;
- a reproducible run report.

**The kernel's governing rule is:** no state change without a typed event; no financial movement without balanced entries; no distribution without a valid pool and rights basis; no AI action without authority; no economic claim without a declared boundary and evidence standard.
