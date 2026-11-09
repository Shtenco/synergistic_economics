# VOLUME V — EXECUTABLE ECONOMIC MODEL
## Mathematical architecture, dynamic equations and comparative simulation programme for SYNERGISTIC ECONOMICS

**Research program:** SYNERGISTIC ECONOMICS  
**Document ID:** SYNERGY-ECON-V5-001  
**Version:** 0.1 — 9 November 2026  
**Status:** Formal research model and implementation blueprint; not yet calibrated, executed or empirically validated  
**Preceding volumes:** [Volume 0](VOLUME_0_SYNTHESIS_OF_ECONOMIC_SCHOOLS.md); [Volume 0A](VOLUME_0A_AXIOM_RECONCILIATION_AND_METHOD_AUDIT.md); [Volume I](VOLUME_I_FOUNDATIONS.md); [Volume II](VOLUME_II_MULTIDIMENSIONAL_VALUE_AND_PRODUCTION.md); [Volume III](VOLUME_III_CONTRIBUTION_OWNERSHIP_AND_DISTRIBUTION.md); [Volume IV](VOLUME_IV_FORMAL_SIMULATION_AND_ACCOUNTING_KERNEL.md)  
**Institutional architecture:** [SYNERGY Cellular Consortium Economy](SYNERGY_CELLULAR_CONSORTIUM_ECONOMY.md)

---

## Executive summary

This volume defines a mathematical architecture for an executable, multi-agent model of a SYNERGY economy. It connects households, workers, enterprises, projects, consortium-cells, federations, markets, funds, financial intermediaries and ecological resources inside one reproducible simulation environment.

The objective is not to prove that a preferred institutional design is superior by construction. It is to create a model in which alternative institutional arrangements face the same agents, technologies, initial endowments, information limits, shocks and accounting rules. The SYNERGY configuration must compete against market, cooperative, platform, federated and centralized baselines.

The model is modular. It separates:
1. physical production and resource flows;
2. household needs, labour supply and consumption;
3. enterprise investment, production and pricing;
4. markets and matching;
5. finance, money, credit and settlement;
6. consortium-cell coordination and shared assets;
7. ownership, contribution and distribution;
8. governance and bounded AI policy;
9. ecological constraints and externalities;
10. welfare, resilience and distributional measurement.

A single aggregate score is not the objective. Results are reported as a vector of output, productivity, income, wealth, access, agency, resilience, solvency, ecological pressure and procedural legitimacy. If decision-makers choose a composite score, its normative weights must be explicit and sensitivity-tested.

---

# Part I — Modeling principles and formal boundary

## 1. Research questions

The executable model is designed to answer six families of questions.

### 1.1 Production and coordination
Under which conditions do autonomous cells, shared infrastructure and inter-cell networks improve output, utilization, innovation or resilience after accounting for coordination and governance costs?

### 1.2 Distribution and ownership
Which combinations of wages, ownership claims, collective dividends, contribution rewards and opportunity access improve distributional outcomes without undermining investment, incentives or solvency?

### 1.3 Finance and monetary stability
Can bounded mutual credit and shared funds ease working-capital constraints without generating excessive leverage, correlated defaults, hidden subsidies or systemic contagion?

### 1.4 AI and institutional adaptation
Can AI-assisted matching, forecasting and policy proposals improve performance out of sample while preserving human authority, contestability, privacy and constitutional constraints?

### 1.5 Ecological and social reproduction
Can the system maintain productive assets, human capabilities and natural resources rather than maximizing short-run output by shifting costs to future periods or unrepresented parties?

### 1.6 Comparative institutional performance
Do any advantages persist when SYNERGY is compared against well-designed alternatives with identical information, resources, legal constraints and technology?

## 2. Model classes

Use a hybrid architecture rather than forcing all dynamics into one method:

- **Agent-based model (ABM):** heterogeneous agents with bounded rationality, diverse objectives and local information.
- **Stock-flow consistent accounting (SFC):** balance-sheet, transaction-flow and sectoral consistency.
- **Production-network model:** input-output dependencies, capacity constraints, inventories and logistics.
- **Market microstructure module:** prices, bids, matching, bargaining and market power.
- **Institutional state machine:** membership, contracts, governance, authority and appeals.
- **Ecological stock-flow module:** resource stocks, regeneration, extraction and damage.
- **Policy-learning module:** forecasts and candidate policies evaluated separately from execution.

Each module has an explicit interface and validation tests. A model result is invalid if one module creates an unrecorded transfer or violates a physical, accounting or constitutional invariant.

## 3. Time and event structure

The reference implementation uses discrete periods (t=0,1,ldots,T), with a configurable period (for example, one week or one month). Within each period, events are processed in a deterministic sequence. High-frequency markets may use substeps, but all substeps reconcile to the period ledger.

A period is not necessarily a calendar month. Every experiment declares:
- period length;
- discounting convention;
- payment and settlement lag;
- production and inventory timing;
- labour and capital adjustment speed;
- contract maturity conventions;
- price basis and inflation treatment.

## 4. System boundary and conservation

Let the economy contain (N_H) households, (N_F) firms, (N_C) cells, (N_P) projects, (N_M) markets and (N_R) ecological resources. The population and network can evolve through entry, exit, merger, split and failure.

For every conserved physical or financial quantity, define:
- stocks at the beginning and end of period;
- inflows;
- outflows;
- losses or transformations;
- boundary-crossing flows.

No aggregate gain may be created merely by relabelling a claim, moving it between cells or changing the ownership register.

---

# Part II — Agents, objectives and bounded behaviour

## 5. Household and person agents

A household (h) contains members (i), a shared budget where relevant, and explicit member-level rights and privacy boundaries. A person agent has:
- available time;
- skills and capability vector;
- labour preferences and constraints;
- care and household obligations;
- liquid resources and assets;
- debt and contractual commitments;
- access to productive assets;
- participation in projects and cells;
- declared preferences and consent settings.

Do not assume a single representative household. Heterogeneity is essential for testing distribution and access.

### 5.1 Time constraint

For person (i):

[
T_i = L_i + C_i + E_i + R_i + S_i
]

where (L_i) is paid labour, (C_i) care and household work, (E_i) education and training, (R_i) rest and recovery, and (S_i) other activity. The categories must be mutually exclusive under the chosen time-use convention. Care is not treated as zero contribution merely because it is unpaid.

### 5.2 Household budget constraint

A simplified cash budget:

[
A^h_{t+1}=A^h_t+W^h_t+TR^h_t+DIV^h_t+Y^{other}_t
-C^h_t-TAX^h_t-DEBT^h_t
]

where (A^h) is liquid financial assets, (W) wages, (TR) transfers, (DIV) dividends, (Y^{other}) other receipts, (C) consumption, (TAX) taxes and (DEBT) debt service. This is a cash-flow identity, not a complete wealth equation. New borrowing, asset sales, capital gains and non-cash transfers require separate entries.

### 5.3 Consumption and needs

A candidate utility representation is:

[
U_h = u(c_{h,1},ldots,c_{h,K},q_h,a_h,ell_h)
]

where (c) are goods and services, (q) quality or essential-service access, (a) agency/capability and (ell) leisure or time autonomy. Utility is not directly observable and should not be treated as a precise interpersonal measure.

For rights-based essential services, model minimum service constraints separately from preference maximization. A household should not lose an essential floor because an optimization routine assigns it a low marginal utility.

## 6. Worker and specialist agents

Labour is heterogeneous. Represent skills as a vector (s_i), not a single productivity number. A task (j) has skill requirements (r_j), working conditions, time requirement, quality standard and risk profile.

Matching can use a compatibility function:

[
m_{ij}=g(s_i,r_j,	ext{availability}_i,	ext{access}_i,	ext{consent}_i)
]

The compatibility score is advisory. It cannot override consent, labour law, safety requirements or anti-discrimination constraints. A model must not infer protected attributes or use proxies to deny lawful opportunity.

Wages may be hourly, piece-rate, salaried, milestone-based or mixed. The model must preserve minimum wage, overtime, leave and other jurisdiction-specific rules as constraints rather than optional optimization parameters.

## 7. Enterprise agents

Firm (f) has:
- technology and production recipe;
- capacity and utilization;
- inventory and work in progress;
- labour and skill requirements;
- capital stock and capital services;
- suppliers and customers;
- pricing and procurement policy;
- cash, receivables, payables and debt;
- ownership and governance;
- risk limits and expected demand.

A firm may be privately owned, cooperative, publicly owned, member-owned or jointly governed. The organizational form is an experimental treatment, not a guarantee of performance.

### 7.1 Firm objective

A baseline profit-seeking firm may maximize expected discounted residual cash flow subject to law, contracts and solvency:

[
max_{pi_f} mathbb{E}left[sum_{t=0}^{T}eta_f^t , CF^{res}_{f,t}ight]
]

where (pi_f) is its policy and (eta_f) a discount factor. A cooperative may use a different objective including member income, employment stability, service quality or shared surplus. A public-purpose enterprise may have explicit service and ecological constraints.

Do not assume that all firms maximize short-term accounting profit or that all cooperatives maximize equality. State each objective and its governance basis.

## 8. Consortium-cell agents

Cell (c) is a voluntary institution with:
- membership and admission rules;
- constitution and governance;
- shared assets and service capacity;
- treasury, funds and liabilities;
- projects and contracts;
- contribution and ownership registries;
- neighbouring cells and federation links;
- exit, dispute and dissolution rules.

A cell's objective may combine:
- member capability and income;
- enterprise survival and productivity;
- shared asset utilization;
- service quality;
- resilience;
- ecological constraints;
- distributional commitments.

These objectives are not automatically commensurable. A cell constitution must state priority rules and hard constraints.

## 9. Bounded rationality and learning

Agents do not have perfect information or unlimited computation. Candidate behaviour models include:
- adaptive expectations;
- bounded search;
- satisficing;
- imitation with exploration;
- reinforcement learning under constrained action spaces;
- rule-based heuristics;
- contractual commitments.

The experiment must compare the same behavioural sophistication across institutional treatments where possible. Giving only the SYNERGY treatment an intelligent AI while leaving baselines artificially primitive would bias the result.

---

# Part III — Production, capital and innovation

## 10. Production technology

For enterprise (f), sector (s) and period (t):

[
Y_{f,t}=min{D_{f,t},,F_s(L_{f,t},K^S_{f,t},M_{f,t},E_{f,t},A_{f,t})}
]

where:
- (D) is demand or orders;
- (L) is effective labour input;
- (K^S) is capital services;
- (M) is intermediate materials;
- (E) is energy;
- (A) is organizational/technology capability.

The minimum operator captures the demand/capacity ceiling in a simple benchmark. More detailed production modules may include work-in-progress and multi-stage processing.

### 10.1 Cobb–Douglas benchmark

[
Y=A L^{alpha}K^{eta}M^{mu}E^{
u}
]

Use only as a benchmark. Returns to scale depend on the exponent sum; parameters must be calibrated or varied. The model should not infer that a fitted residual is pure technology.

### 10.2 CES benchmark

[
Y=Aleft(sum_j delta_j X_j^{ho}ight)^{1/ho}
]

with elasticity of substitution (sigma=1/(1-ho)) for the standard parameterization. This allows substitution patterns to vary, but the CES form still imposes structure.

### 10.3 Leontief bottleneck

[
Y=min_jleft(rac{X_j}{a_j}ight)
]

Useful for fixed-proportion processes, bottleneck analysis and supply disruptions.

### 10.4 Network production

For multi-stage production, each sector uses intermediate goods from other sectors. Let (A_{ij}) be input of good (i) per unit of output (j). A basic input-output relation is:

[
x=Ax+y
quadRightarrowquad
x=(I-A)^{-1}y
]

where (x) is gross output and (y) final demand, where the inverse exists and the system is productive. Capacity, inventories, prices, substitution and time lags require extensions beyond this static relation.

## 11. Capital accumulation

Productive capital evolves as:

[
K_{f,t+1}=(1-delta_f)K_{f,t}+I_{f,t}-DISP_{f,t}
]

where (delta) is depreciation, (I) gross investment and (DISP) disposals. Capital services are not identical to the market value of the asset. Utilization, age, quality, downtime and maintenance determine productive services.

Investment is constrained by cash, credit, expected demand, capacity and authorization:

[
I_{f,t}leq min{I^{desired}_{f,t},,I^{funded}_{f,t},,I^{authorized}_{f,t}}
]

No AI forecast may bypass the authorization or funding limit.

## 12. Innovation and learning-by-doing

Technology may evolve through:
- internal R&D;
- worker and user learning;
- inter-firm knowledge diffusion;
- public research;
- licensing;
- open standards;
- equipment upgrades.

A candidate productivity evolution:

[
ln A_{f,t+1}=ln A_{f,t}+eta_{R}R&D_{f,t}+eta_{L}Learn_{f,t}
+eta_{N}Network_{f,t}-eta_{D}Disruption_{f,t}+epsilon_{f,t}
]

All coefficients are uncertain and context-dependent. Network diffusion can be positive or negative; adoption requires skills, integration, trust, maintenance and complementary investment.

---

# Part IV — Markets, prices and allocation

## 13. Demand and supply

Demand depends on prices, income, preferences, availability and substitution. A simple demand system may be:

[
Q^d_{g,t}=D_g(P_t,Y_t,N_t,mathbf{q}_t,mathbf{a}_t)
]

Supply depends on marginal cost, capacity, inventories, expectations and market structure:

[
Q^s_{g,t}=S_g(P_t,mathbf{MC}_t,K_t,Inv_t,mathbb{E}_t)
]

The first implementation should support at least:
- posted-price market;
- bilateral contract;
- double auction or order-book matching;
- cooperative procurement;
- internal transfer with explicit transfer-pricing policy.

## 14. Price formation

For a competitive benchmark, price may adjust to excess demand:

[
P_{g,t+1}=max(P_{min},P_{g,t}+lambda_g(Q^d_{g,t}-Q^s_{g,t})+epsilon_{g,t})
]

This is a tâtonnement-style adjustment rule, not a universal law of price formation. It can be unstable under poorly chosen (lambda), delays or strategic agents. Test convergence and market power.

For market power, allow markup pricing:

[
P_{f,g,t}=(1+mu_{f,g,t})MC_{f,g,t}
]

where markup (mu) depends on concentration, elasticity, regulation and bargaining position. Do not treat price-cost margin as pure profit without accounting for fixed costs and risk.

## 15. Matching and coordination

A matching engine connects orders, tasks, resources and participants. The objective may minimize:
- delivery cost;
- delay;
- mismatch;
- risk;
- quality failure;
- carbon or resource intensity.

A candidate assignment objective:

[
min_{x_{ij}}sum_{i,j}x_{ij}
(c^{price}_{ij}+c^{transport}_{ij}+c^{delay}_{ij}+c^{risk}_{ij}+c^{external}_{ij})
]

subject to capacity, compatibility, consent, contract and legal constraints. The engine should expose trade-offs and allow alternative objectives to be tested.

## 16. Competition, concentration and entry

Track market shares, concentration indices, entry and exit, switching costs, network lock-in, interoperability and platform dependence. A high network effect may improve service quality while also increasing concentration and extraction power. Report both.

---

# Part V — Money, credit and financial dynamics

## 17. Monetary layers

The model distinguishes:
1. **unit of account:** denomination used to price and record obligations;
2. **payment instrument:** mechanism for transferring claims;
3. **settlement asset:** asset that discharges an obligation under the relevant system;
4. **credit:** a liability/asset relationship with repayment terms;
5. **equity:** residual ownership claim;
6. **token:** a technical representation whose legal and economic rights must be specified.

A token can represent a payment claim, membership, access, governance, a security or a utility right, but the label alone does not determine its legal or accounting status.

## 18. Money and deposits

The simulator must define which institutions issue which liabilities and which assets back or settle them. Bank deposits, central-bank money, e-money, mutual-credit balances and project tokens are not interchangeable.

For a deposit-creating loan, the lender records a loan asset and a deposit liability. The borrower records a deposit asset and a loan liability. The transaction creates purchasing power and debt simultaneously; it does not create net financial wealth for the consolidated private sector merely by double entry.

## 19. Credit dynamics

For borrower (i):

[
Debt_{i,t+1}=Debt_{i,t}+NewCredit_{i,t}+AccruedInterest_{i,t}-PrincipalPaid_{i,t}-Writeoff_{i,t}
]

Debt service capacity should be estimated from cash flow and risk, not only collateral value. Model:
- maturity mismatch;
- refinancing risk;
- interest-rate changes;
- collateral haircuts;
- default correlation;
- recovery delays;
- bankruptcy costs;
- guarantee calls.

A credit expansion scenario must be stress-tested under lower revenue, higher rates, delayed settlement and falling collateral values.

## 20. Mutual credit and network exposure

Let (b_{i,t}) be a participant's net mutual-credit position, positive for net creditor and negative for net debtor under the declared convention. Track:

[
sum_i b_{i,t}=0
]

only for a closed, fully recorded mutual-credit ledger with no external settlement leakage and consistent valuation. If the network has an external reserve, fees, write-offs or currency conversion, those flows must appear explicitly.

Set borrower and network-level limits:
- maximum negative balance;
- exposure by counterparty;
- aggregate credit capacity;
- maturity and velocity;
- default fund and loss waterfall;
- correlated exposure;
- external settlement needs.

A mutual-credit network can ease exchange constraints but cannot guarantee that every credit balance is accepted or convertible into external settlement assets.

## 21. Liquidity and payment finality

For each entity:

[
Cash_{t+1}=Cash_t+SettledInflows_t-SettledOutflows_t
]

Payment instructions, pending payments and settled payments are distinct states. Track settlement time, failure and reversals. A solvent entity may be illiquid; a liquid entity may be insolvent.

---

# Part VI — Cellular consortium economy

## 22. Cell state and balance sheet

For cell (c), define:

[
Z_{c,t}=(Members,Assets,Liabilities,Projects,Funds,Capabilities,Governance,Network)
]

The cell has separate accounts for:
- operating cash;
- productive assets;
- reserve;
- opportunity and access funds;
- mutual-credit exposure;
- restricted grants;
- project-specific funds;
- member capital and collective equity.

The cell is not automatically the legal owner of every member asset. Legal entity boundaries and beneficial ownership must be explicit.

## 23. Cell formation, joining and exit

Cell formation depends on a charter, consent, defined purpose and governance. Entry and exit may be costly but must not be arbitrary.

Model:
- member discovery and invitation;
- application and eligibility;
- informed consent;
- contribution and capital commitments;
- onboarding and capability support;
- voluntary exit;
- accrued claims;
- asset redemption or transfer;
- dissolution and insolvency.

Membership in one cell must not automatically imply exclusivity over a person's labour, identity or data.

## 24. Cell coordination benefit and cost

Let gross coordination benefit be (B_c), and costs be:

[
C_c=C_{search}+C_{governance}+C_{integration}+C_{monitoring}+C_{dispute}+C_{privacy}+C_{failure}
]

Net coordination effect:

[
NCE_c=B_c-C_c
]

This is a project-level analytical measure, not necessarily cash profit. It should be estimated against a counterfactual in which the same agents and resources coordinate through another institution.

## 25. Inter-cell cooperation

Inter-cell relationships are typed:
- supply;
- service;
- shared asset;
- knowledge licence;
- mutual aid;
- credit;
- procurement;
- governance federation;
- ecological stewardship.

Each relationship has contract, quantity, timing, price or non-price obligation, counterparty, dispute path and settlement status. A cell cannot unilaterally spend another cell's treasury or transfer its members' rights.

## 26. Federation subsidiarity

A federation acts only where cross-cell effects justify it. Define a mandate scope (M_F), decision rights and sunset/review. Compare:
- local-only coordination;
- bilateral contracts;
- narrow federation;
- broad centralized coordination.

A federation's net contribution is:

[
NF=CrossCellBenefit-CentralCoordinationCost-AgencyCost-CaptureRisk
]

A positive result must be demonstrated, not assumed.

---

# Part VII — Contribution, ownership and distribution dynamics

## 27. Separate the four ledgers

Maintain:
- contribution evidence;
- ownership rights;
- contractual claims;
- distributions and settlements.

A contribution score cannot silently alter ownership or governance. Ownership may change only through a valid transfer, vesting event or lawful institutional process.

## 28. SCI as a bounded measurement service

For participant (i) in project (p) and period (t):

[
SCI_{i,p,t}=sum_{j=1}^{7}w_{j,p,t}z_{i,j,p,t}
]

The seven dimensions are output, quality, efficiency, innovation, cooperation, reliability and risk stewardship. The model must retain the component vector and evidence quality. The composite is optional and project-specific.

For uncertain contributions, represent:

[
z_{i,j,p,t}sim P_{i,j,p,t}
]

or as an interval when probabilistic assumptions are not justified. Run sensitivity tests on resulting rewards. If modest measurement changes cause large allocation shifts, cap the impact or use a negotiated rule.

## 29. Distributable surplus

A simplified financial pool:

[
S^{cash}_{p,t}=CashAvailable-ClaimsDue-TaxesDue-RequiredReserves-ApprovedReinvestment
]

A distinct economic surplus estimate may include non-cash production and externalities. Never merge the economic surplus estimate with the cash pool available for payment.

## 30. Multi-pool distribution

Partition the approved distributable amount:

[
S=S_E+S_O+S_C+S_N+S_K
]

where equal membership, ownership, contribution, needs/access and collective reinvestment pools are separately governed. The model records eligibility sets, calculation, appeal and payment.

Do not assume that a hybrid formula always performs better. It may increase fairness or legitimacy while increasing administrative cost, delay and gaming surface.

## 31. Collective dividends

A dividend can be generated only by a defined collective asset or revenue stream with valid rights. Model:
- realized cash flow;
- operating and lifecycle cost;
- tax and senior obligations;
- reserves;
- eligible ownership or membership snapshot;
- approved allocation rule;
- payment and tax treatment.

Usage rebates, ownership dividends, public transfers and social-impact budgets remain separate categories.

---

# Part VIII — UEP and UOF dynamic models

## 32. Universal Economic Participation

UEP is represented by four channels:
1. basic guarantees;
2. access to productive assets;
3. verified contribution rewards;
4. collective results.

The model must track nominal availability and effective access separately. A resource offered is not a resource successfully accessed. Measure application friction, geographic access, accessibility, training, time constraints, digital access and actual utilization.

## 33. Universal Opportunity Fund

UOF operates as a portfolio of grants, loans, guarantees, leases, shared assets, equity and capability services. These instruments must have separate accounting and risk models.

For project (k), a candidate decision vector is:

[
Q_k=(Need_k,Additionality_k,Feasibility_k,Downside_k,CapabilityImpact_k,EcologicalImpact_k)
]

Do not collapse this into an unreviewable score. Use mandate eligibility gates, risk limits, portfolio diversification and documented human authorization.

## 34. Additionality and counterfactual

Estimate:

[
Additionality_k=Outcome^{with support}_k-Outcome^{credible alternative}_k
]

The alternative must be plausible: private financing, self-financing, delayed project, different scale or no project. Correct for displacement, deadweight, substitution and costs shifted to other actors. Additionality is an estimate with uncertainty, not a directly observed fact.

---

# Part IX — Ecological constraints and long-term reproduction

## 35. Resource stock-flow

For renewable resource (r):

[
R_{r,t+1}=R_{r,t}+G_r(R_{r,t},Climate_t)-X_{r,t}-D_{r,t}
]

where (G) is regeneration, (X) extraction and (D) degradation. The model must enforce physically plausible bounds and uncertainty.

For non-renewable resources, report extraction, remaining stock, recycling and substitution. Recycling is not assumed to be lossless or costless.

## 36. Externality dynamics

Track emissions, pollution, waste, land and water pressure, ecosystem damage, health and safety harms, congestion, unpaid care burdens and positive knowledge spillovers. Monetary valuation may be used for some analysis but cannot replace hard constraints or non-monetary reporting.

## 37. Maintenance and resilience

Capital and infrastructure require maintenance. Underinvestment may increase short-run cash but reduce uptime, safety and asset life.

A maintenance state may evolve:

[
Condition_{a,t+1}=Condition_{a,t}+Repair_{a,t}-Wear_{a,t}-ShockDamage_{a,t}
]

Maintenance investment should be evaluated over lifecycle horizons, not just current-period expense.

---

# Part X — AI, policy adaptation and institutional safety

## 38. AI service boundaries

AI may forecast demand, match resources, estimate risk, detect anomalies, simulate alternatives and propose bounded parameter changes. It cannot autonomously:
- amend constitutional rights;
- issue unapproved liabilities;
- change ownership;
- transfer funds beyond mandate;
- impose debt;
- suppress appeals;
- rewrite history;
- expand its own permissions.

## 39. Policy candidate lifecycle

Every candidate policy passes:
1. proposal;
2. offline training;
3. out-of-sample evaluation;
4. stress and adversarial tests;
5. independent review;
6. authorized approval;
7. shadow deployment;
8. bounded rollout;
9. monitoring;
10. rollback or expiry.

A policy that improves average output but violates a rights, solvency or ecological constraint is rejected.

## 40. Learning under distribution shift

The environment may change after deployment. Track:
- forecast error;
- calibration;
- input distribution drift;
- policy performance by subgroup and task;
- adverse events;
- data quality;
- feedback loops;
- model uncertainty.

A model's own recommendations can change the data it later observes. This policy-induced distribution shift must be represented in evaluation.

---

# Part XI — Comparative institutional experiments

## 41. Treatments and baselines

At minimum compare:

A. decentralized market economy with independent firms;  
B. cooperative enterprise network;  
C. platform-mediated allocation;  
D. centralized allocation under the same information constraints;  
E. federated cooperative system;  
F. SYNERGY cells with no AI;  
G. SYNERGY cells with AI recommendations in shadow mode;  
H. SYNERGY cells with authorized bounded adaptation;  
I. hybrid market/cooperative system without UOF;  
J. hybrid system with UEP/UOF and plural distribution.

All treatments must share the same initial agents, skills, resources, production technology, shock sequences and external constraints. If a treatment receives extra capital or better information, that difference must be reported as part of the treatment rather than attributed to governance.

## 42. Experimental factors

Vary:
- cell size and overlap;
- network density and modularity;
- production complementarity;
- market concentration;
- bargaining power;
- access to capital;
- skill heterogeneity;
- coordination and verification costs;
- trust and default;
- information quality;
- AI forecast accuracy and drift;
- governance participation;
- ownership concentration;
- externality intensity;
- ecological scarcity;
- shock frequency and correlation;
- participant exit and entry;
- contribution metric noise and gaming.

Use designed experiments, not one attractive hand-picked scenario.

## 43. Outcome vector

Report:

[
mathbf{Y}=(GDP^{real},ValueAdded,Productivity,MedianIncome,BottomQuantileIncome,
WealthConcentration,AssetAccess,Innovation,Resilience,Solvency,Ecology,Agency,Fairness)
]

These measures are not interchangeable. GDP is a production measure, not a complete welfare measure. Wealth concentration is not income inequality. Productivity growth does not prove that gains are broadly distributed.

## 44. Resilience metrics

Measure:
- unmet essential demand;
- default rate and loss given default;
- recovery time;
- production shortfall;
- asset downtime;
- liquidity shortfall;
- supply-chain propagation;
- cell exit and dissolution;
- concentration after shock;
- ecological recovery.

A system may have higher average output but worse tail risk. Report distributions and worst-decile outcomes, not only means.

## 45. Distribution and access metrics

Measure:
- median and lower-quantile disposable income;
- income volatility;
- net wealth and ownership concentration;
- access to productive assets;
- share of participants receiving collective dividends;
- effective access after eligibility and application friction;
- unpaid care and maintenance recognition;
- grievance and appeal outcomes;
- regional and sectoral differences.

Do not infer fairness from a single inequality index. Report incidence, procedural outcomes and opportunity access.

## 46. Hypotheses

- **H5-1 — Coordination threshold:** cellular coordination improves net outcomes only when complementarities and shared-resource benefits exceed governance, integration and monitoring costs.
- **H5-2 — Cell size:** performance follows a non-linear relationship with cell size; larger cells can gain scale but lose participation quality and increase agency costs.
- **H5-3 — Network modularity:** modular networks may contain contagion while preserving cross-cell cooperation, but excessive modularity may reduce knowledge diffusion and matching.
- **H5-4 — Shared assets:** shared productive assets raise utilization when access rules, maintenance incentives and scheduling costs are well designed.
- **H5-5 — Hybrid distribution:** multi-pool distribution may improve legitimacy or lower-quantile outcomes in some contexts, but may be dominated by simpler rules where measurement costs are high.
- **H5-6 — UOF additionality:** opportunity funding improves outcomes only where it addresses binding constraints and does not mainly displace other finance.
- **H5-7 — Mutual credit:** capped mutual credit can reduce working-capital constraints but increases losses when exposures are concentrated or shocks correlated.
- **H5-8 — Bounded AI:** AI recommendations improve performance only when forecasts are calibrated, data quality is adequate and human governance catches model error.
- **H5-9 — Ownership breadth:** broader productive ownership can improve participation and resilience under some governance conditions, but can also increase decision costs or undercapitalization.
- **H5-10 — Ecological limits:** short-run output gains that breach resource constraints reduce long-run welfare and may create irreversible losses.
- **H5-11 — Institutional competition:** no one institutional form dominates across all sectors, technologies, scales and shock environments.
- **H5-12 — Synergy measurement:** estimated net synergy is highly sensitive to counterfactual specification and should be reported with uncertainty and alternative baselines.

Every hypothesis must be preregistered with population, treatment, comparator, outcome, measurement period, minimum detectable effect and failure criterion.

---

# Part XII — Net synergy and system-level accounting

## 47. Counterfactual net synergy

For a defined set of agents and resources, compare observed joint outcome with a credible alternative:

[
S_{net}=Delta Y_{joint}-Delta Y_{extra inputs}-C_{coord}-C_{integration}-C_{external}-C_{risk}
]

Where:
- (Delta Y_{joint}): change in jointly produced outcome;
- (Delta Y_{extra inputs}): incremental labour, capital, energy and materials not present in baseline;
- (C_{coord}): governance and coordination costs;
- (C_{integration}): interoperability and transition costs;
- (C_{external}): external costs not included in direct accounting;
- (C_{risk}): expected or realized risk cost under the declared method.

Do not add this counterfactual estimate to financial accounts as cash. Report monetary and non-monetary dimensions separately. The baseline must hold fixed the same agents, resource endowment and exogenous shocks where possible.

## 48. Avoiding double counting

Do not count the same benefit as:
- revenue and value added;
- an asset's market price and its underlying future income stream;
- a cell transfer and consolidated external revenue;
- a token issuance and productive capital formation;
- a contribution score and ownership claim;
- a network effect for every connected pair without accounting for overlap;
- a social outcome and the same outcome again as a financial return.

Use a value-flow map and consolidation boundary for every reported aggregate.

---

# Part XIII — Calibration, identification and robustness

## 49. Parameter classes

Classify parameters as:
- physical/engineering constants;
- observed institutional rules;
- estimated behavioural parameters;
- accounting identities;
- normative choices;
- scenario assumptions;
- policy controls.

Never fit normative weights as if they were objective empirical parameters.

## 50. Calibration sequence

1. Validate accounting and physical identities with synthetic data.
2. Calibrate sector technologies using suitable production and input data.
3. Calibrate household income, consumption and time-use distributions.
4. Calibrate firm entry, exit, pricing and investment behaviour.
5. Calibrate credit, default and payment delays.
6. Calibrate network and coordination costs.
7. Validate against held-out periods or external benchmarks.
8. Perform sensitivity and uncertainty analysis.
9. Re-run institutional comparisons with shared calibrated parameters.
10. Publish parameter provenance and uncertainty.

## 51. Identification limits

Many macro-level observations are consistent with different micro-level mechanisms. A good fit does not prove the model's causal story. Distinguish:
- parameter fit;
- predictive accuracy;
- causal identification;
- institutional mechanism validation;
- external validity.

If multiple parameter sets produce similar outputs, report an identified set or uncertainty range rather than a single precise estimate.

## 52. Robustness tests

- alternative production functions;
- alternative behavioural rules;
- different initial wealth distributions;
- varying shock correlation;
- measurement error;
- missing data;
- strategic manipulation;
- alternative price adjustment rules;
- different discount factors;
- alternative ecological valuation;
- different cell boundaries;
- alternative distribution weights;
- policy-induced distribution shift.

A claimed result that disappears under modest plausible parameter changes is fragile.

---

# Part XIV — Implementation blueprint

## 53. Software modules

Recommended logical package structure:

```text
synergy_model/
  core/
    entities
    events
    time
    random
    state_transition
  accounting/
    chart_of_accounts
    journal
    consolidation
    reconciliation
  agents/
    households
    persons
    firms
    cells
    funds
  production/
    technologies
    inventory
    capital
    logistics
  markets/
    demand
    supply
    pricing
    matching
  finance/
    money
    credit
    settlement
    default
  institutions/
    contracts
    ownership
    governance
    appeals
  distribution/
    contribution
    sci
    allocation
    dividends
  opportunity/
    uep
    uof
  ecology/
    resources
    externalities
    lifecycle
  ai/
    forecasting
    recommendation
    evaluation
    rollback
  experiments/
    baselines
    scenarios
    metrics
    reports
  tests/
    accounting
    physical
    rights
    adversarial
```

This is a logical decomposition, not a claim that code files already exist.

## 54. Core interfaces

Every module should expose:
- typed input state;
- typed events;
- deterministic transition function;
- validation errors;
- metrics and diagnostics;
- version and provenance;
- tests.

Avoid hidden global state. Randomness must be injected through an explicit seeded generator. Module execution order must be documented and reproducible.

## 55. Minimal prototype stages

**Prototype 0 — Accounting kernel:** accounts, journal, balanced entries, consolidation and replay.

**Prototype 1 — Production network:** households, firms, input-output production, inventories, labour, capital and market orders.

**Prototype 2 — Cells:** membership, shared assets, treasury, governance, contracts and inter-cell obligations.

**Prototype 3 — Distribution:** ownership registry, shadow SCI, multiple allocation mechanisms, dividends and appeals.

**Prototype 4 — UEP/UOF:** access pathways, fund instruments, additionality and portfolio risk.

**Prototype 5 — AI shadow mode:** forecasts and matching recommendations, with no direct financial authority.

**Prototype 6 — Comparative experiments:** identical initial conditions, multiple baselines, shocks and reproducible reports.

## 56. Acceptance criteria

The first release is not accepted until:
- all accounting invariants pass;
- physical production and inventory reconcile;
- event replay is deterministic;
- no unauthorized action succeeds;
- no SCI calculation changes title;
- no distribution exceeds the valid pool;
- internal transfers eliminate on consolidation;
- all random seeds and parameters are saved;
- baseline and SYNERGY treatments use comparable assumptions;
- adverse results and failed tests are reported.

---

# Part XV — Research governance and decision gates

## 57. Decision gates

**Gate A — Formal consistency:** equations, units, boundaries and accounting identities reviewed.

**Gate B — Synthetic correctness:** deterministic tests and conservation tests pass.

**Gate C — Calibration readiness:** empirical datasets and parameter provenance documented.

**Gate D — Comparative validity:** baselines implemented fairly and experiments preregistered.

**Gate E — Institutional feasibility:** legal, governance, privacy and operational review completed.

**Gate F — Pilot readiness:** limited real-world pilot with capped exposure, human fallback and independent audit.

Passing a technical gate does not imply passing a legal or ethical gate.

## 58. Stop conditions

Pause or reject a design if:
- it systematically violates rights or consent;
- financial balances cannot be reconciled;
- losses are hidden or shifted to unrepresented parties;
- model performance depends on look-ahead leakage;
- a baseline is intentionally weakened;
- ecological limits are exceeded;
- governance power becomes unaccountable;
- AI actions cannot be audited or rolled back;
- distribution outcomes are driven by uncorrectable measurement bias;
- claimed benefits cannot be reproduced.

---

# Part XVI — Open questions and next research artifacts

## 59. Decisions still to be made

1. Which time step best fits the first sectoral pilot?
2. Which currency and settlement asset boundaries are modeled first?
3. Which production sectors provide the best test of complementary inputs?
4. Which market mechanism is the baseline for each sector?
5. What household heterogeneity is essential and what is privacy-invasive?
6. How should informal and unpaid production be represented without double counting?
7. Which cell legal forms are feasible in the target jurisdiction?
8. What credit instrument and loss waterfall are safe for the first prototype?
9. Which UOF instrument has the strongest measurable additionality?
10. Which ecological constraints are binding in the selected sector?
11. What minimum governance participation and appeal standards are required?
12. Which model results would cause the SYNERGY design to be rejected or materially revised?

## 60. Next artifacts

The next implementation sequence should be:

- [**Volume VI — Benchmark Economies and Experimental Protocols**](VOLUME_VI_BENCHMARK_ECONOMIES_AND_EXPERIMENTAL_PROTOCOLS.md): baseline models, initial conditions, scenario matrix, preregistration templates and comparison rules.
- **Technical Specification V5.1 — Canonical Entity and Event Schemas:** machine-readable schemas for agents, cells, assets, accounts, contracts, events and policy versions.
- **Prototype 0 — Double-entry Accounting Kernel:** executable code with tests and deterministic replay.
- **Prototype 1 — Seven-cell Production Economy:** a small synthetic economy to exercise production, exchange, credit, shared assets and distribution.

These are separate deliverables. The existence of this document does not imply that any of those artifacts have already been implemented.

---

## 61. Selected methodological foundations

- Tesfatsion, L. (2003). “Agent-based computational economics: modeling economies as complex adaptive systems.” *Information Sciences*, 149(4), 262–268. https://doi.org/10.1016/S0020-0255(02)00280-3
- Ostrom, E. (2010). “Beyond Markets and States: Polycentric Governance of Complex Economic Systems.” *American Economic Review*, 100(3), 641–672. https://doi.org/10.1257/aer.100.3.641
- Godley, W. & Lavoie, M. (2007). *Monetary Economics: An Integrated Approach to Credit, Money, Income, Production and Wealth*. Palgrave Macmillan.
- Leontief, W. (1936). “Quantitative Input and Output Relations in the Economic Systems of the United States.” *Review of Economics and Statistics*, 18(3), 105–125.
- Aoki, M. (2001). *Toward a Comparative Institutional Analysis*. MIT Press.
- OECD (2009). *Measuring Capital: OECD Manual*, Second Edition. https://doi.org/10.1787/9789264193260-en
- World Bank (2024). *The Changing Wealth of Nations 2024*.
- United Nations Statistics Division (2025). *System of National Accounts 2025*. https://unstats.un.org/unsd/econstats/national-accounts/sna2025

---

## 62. Research status and limitations

This volume defines a candidate executable model, not a calibrated forecast of a real economy. Equations are selected as transparent starting points and must be compared against alternative specifications. Normative objectives are not inferred from data. No claim is made that cellular organization, hybrid distribution, mutual credit or AI coordination is universally superior.

A valid implementation must preserve the distinction between:
- accounting identity and behavioural hypothesis;
- physical production and financial claims;
- observed data and model estimate;
- contribution and ownership;
- cash distribution and non-monetary welfare;
- AI recommendation and authorized action;
- simulation result and empirical evidence.

**The governing principle:** build the smallest model that preserves the essential economic distinctions, validate it against invariants, compare it against strong baselines, expose uncertainty and allow the evidence to change the design.
