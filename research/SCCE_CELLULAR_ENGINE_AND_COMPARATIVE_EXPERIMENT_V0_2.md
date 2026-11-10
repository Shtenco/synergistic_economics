# SCCE Cellular Economic Engine and Comparative Experiment

**Document ID:** SCCE-ENGINE-EXP-002  
**Version:** 0.2 — 10 November 2026  
**Status:** Operational design specification; Stage-A local coordination kernel implemented; full dynamic economy and empirical validation remain pending.  
**Parent:** [SYNERGY CELLULAR CONSORTIUM ECONOMY](SYNERGY_CELLULAR_CONSORTIUM_ECONOMY.md)  
**Related prototypes:** [Seven-cell economy](../prototype/SEVEN_CELL_ECONOMY.md), [General input-output economy](../prototype/GENERAL_IO_ECONOMY.md), [Stage-A cellular coordination kernel](../prototype/cellular_coordination.py)

---

## Executive statement

The next central research object of SYNERGY is the **cellular economic mechanism**: a network of autonomous economic cells that observe their own conditions, exchange bounded signals with neighbours, discover mutually beneficial matches, negotiate voluntary commitments, and update their local states. Aggregate production, distribution, resilience and innovation are outcomes of these repeated interactions; they are not centrally assigned by assumption.

The present document turns the existing SCCE architecture into an operational research programme. It does not replace the seven-cell or input-output prototypes. It adds a separate coordination layer and a controlled comparison of institutional mechanisms.

The first implemented component is deliberately narrow: a Stage-A matching kernel compares four allocation regimes on the same seven-cell synthetic world. It is a mechanism test, not yet a complete macroeconomic cellular automaton. In particular, it does not yet simulate production recipes, labour, wages, investment, credit creation, ownership changes, ecological stocks or multi-period capital accumulation. Those remain in the existing economic prototypes and subsequent integration stages.

**No claim is made that SCCE currently outperforms markets, planning or cooperatives.** The purpose of the experiment is to make that claim testable and to make failure visible.

# Part I — What exactly is a cellular economy?

## 1. Economic cell, not merely a grid square

An SCCE cell is a bounded, voluntarily organized economic collective with:
- participants and defined membership/participation rights;
- production, services, projects or shared infrastructure;
- productive capacity, stocks, capabilities and resource constraints;
- a treasury and separately identified financial claims;
- local rules, decision mandates and dispute procedures;
- evidence-linked records and a digital twin;
- typed links to other cells.

A cell may be an enterprise consortium, cooperative, production cluster, community utility, research collective, logistics node, care network or temporary project alliance. It need not own every asset it uses. A person may participate in multiple cells. The cell is a unit of coordination, not a claim that society must be divided into exclusive territories.

The cellular automaton is therefore **networked and heterogeneous**, not necessarily a regular two-dimensional lattice. A geographic grid may be useful for spatial resources and externalities, but production, credit, knowledge, ownership and governance require different networks.

## 2. The multilayer economic graph

At time t:

\[
\mathcal G_t=(V_t,E_t,\Lambda,\Omega_t)
\]

- \(V_t\): people, households, firms, projects, assets, cells and federations;
- \(E_t\): typed relationships;
- \(\Lambda\): edge types;
- \(\Omega_t\): capacities, costs, lead times, permissions, evidence and validity intervals.

Required layers:
1. material and product supply;
2. energy, water and natural-resource dependence;
3. logistics and storage;
4. orders, contracts and service commitments;
5. payments, credit and settlement;
6. legal ownership, custody and control;
7. knowledge, technology and skills;
8. governance and shared services;
9. ecological externalities;
10. mutual aid and social support.

A graph edge is not automatically a legal contract. Discovery, negotiation, authorization, execution and settlement are distinct states.

## 3. Cell state vector

For cell i at epoch t:

\[
X_i(t)=
(P_i,H_i,A_i,F_i,R_i,G_i,W_i,E_i)
\]

where:
- \(P_i\): production plans, output, capacity, inventories, orders and work in progress;
- \(H_i\): skills, available time, labour commitments, safety and capability indicators;
- \(A_i\): productive assets, condition, title, custody and encumbrances;
- \(F_i\): cash, deposits, receivables, payables, debt, funds and reserves;
- \(R_i\): operational, financial, supply, cyber and ecological risks;
- \(G_i\): charter, mandates, votes, active proposals and rule versions;
- \(W_i\): essential-service access, quality of life, distribution and participation;
- \(E_i\): evidence, provenance, confidence, uncertainty and event references.

The vector is not collapsed into one scalar "cell health". Dashboards may display summaries, but decision rules must expose the underlying variables and the uncertainty of each.

## 4. Neighbourhood is typed and bounded

\(N_i(t)\) contains cells connected to i by eligible edges. Neighbourhood is not simply physical proximity. A cell may be a neighbour for energy but not for finance; a research partner but not a supplier; a downstream ecological stakeholder without a commercial contract.

Every edge carries at least:
- type and direction;
- available capacity;
- unit and quality standard;
- transport or communication cost;
- lead time;
- contractual permissions;
- reliability and evidence status;
- concentration and exposure limits.

A local algorithm may only use the information delivered through its authorized edges. It must not secretly query a global database and then be described as decentralized.

# Part II — Local economic transition

## 5. Observation and signal formation

Each cell estimates demand, usable stocks, committed stocks, spare capacity, delivery reliability and risk.

For product/service p:

\[
Shortage_{i,p}(t)=
\max(0,\widehat D_{i,p}(t)+Buffer_{i,p}(t)-Available_{i,p}(t))
\]

\[
Surplus_{i,p}(t)=
\max(0,Available_{i,p}(t)-Committed_{i,p}(t)-SafetyStock_{i,p}(t))
\]

\[
SpareCapacity_{i,p}(t)=
\max(0,Capacity_{i,p}(t)-PlannedUse_{i,p}(t))
\]

Forecast demand and verified orders must remain separate. A forecast is not a contract and cannot by itself authorize spending, borrowing or compulsory production.

A signal is a bounded request or offer, not an automatic transfer of property:

\[
s_i=(type,product,quantity,quality,window,terms,confidence,evidence)
\]

## 6. Local matching and negotiation

A cell can:
1. detect an unmet need or idle capacity;
2. publish a signed, time-limited request or offer to eligible neighbours;
3. receive offers and counteroffers;
4. rank options using delivered cost, reliability, lead time, quality, risk and concentration;
5. reserve the relevant stock or capacity provisionally;
6. obtain any required member or counterparty authorization;
7. execute the contract and record delivery;
8. settle payment or record an explicitly authorized credit claim;
9. reconcile the physical and financial consequences.

An illustrative candidate score is:

\[
Score_{ij,p}=
\alpha Q_{ij,p}
+\beta Reliability_{ij}
+\gamma Urgency_{i,p}
-\lambda DeliveredCost_{ij,p}
-\mu Risk_{ij}
-\nu Concentration_{ij}
\]

The weights are policy parameters to be tested, not universal constants. The score is a ranking aid; it does not override legal rights, contract terms, essential-service floors or consent.

A local proposal must specify quantity, unit, quality, delivery window, price or non-price exchange terms, transport responsibility, payment terms, evidence, expiry and cancellation rules.

## 7. Resource and commitment constraints

For each seller j and product p:

\[
\sum_i q_{ji,p}(t)
\leq FreeStock_{j,p}(t)+AuthorizedProductionCommitment_{j,p}(t)
\]

For each buyer i:

\[
\sum_j q_{ji,p}(t)\leq UnmetNeed_{i,p}(t)
\]

For each network edge e:

\[
Flow_{e,p}(t)\leq Capacity_{e,p}(t)
\]

Financial commitments must additionally satisfy liquidity, maturity, credit, collateral and mandate constraints. A promise to deliver cannot be counted as delivered output. A payment instruction cannot be counted as settled money. A token balance cannot substitute for a physical stock or legal title.

## 8. Conflict resolution and simultaneous updates

The cellular engine must prevent double allocation of the same stock or capacity. A period is divided into explicit phases:

1. **Snapshot:** each cell reads a versioned opening state.
2. **Signal:** cells publish requests/offers.
3. **Discovery:** eligible neighbours receive messages under the selected communication radius and delay.
4. **Proposal:** candidate matches and terms are generated.
5. **Reservation:** temporary holds are placed against available capacity.
6. **Consent:** the parties authorize commitments according to their mandates.
7. **Execution:** goods, services or resources move.
8. **Settlement:** financial entries are posted under the payment protocol.
9. **Reconciliation:** physical, financial, legal and event records are checked.
10. **Transition:** cells update their state and publish the next epoch's signals.

For simultaneous proposals, use deterministic reservation tokens or an explicit conflict-resolution rule. No cell may reserve more than its free stock. Duplicate messages must be idempotent. Stale-state proposals must be rejected or renegotiated.

The engine should support asynchronous events in live operation and deterministic epoch snapshots in reproducible experiments. These are different execution modes and must share the same authorization and accounting invariants.

## 9. Local autonomy and federation

The default rule is subsidiarity: the lowest competent level decides. Federation is triggered only where the decision materially crosses cell boundaries, affects shared infrastructure, creates systemic risk, requires common standards or cannot be resolved by feasible bilateral/small-coalition coordination.

Federation authority is enumerated and bounded. It may coordinate shared infrastructure, standards, inter-cell capacity and systemic-risk limits. It must not silently become a central allocator of all local production.

Cross-cell commitments require consent from every materially bound party. A federation may not compel labour, confiscate assets, rewrite ownership or override basic rights.

## 10. Learning is not the state transition

Cellular transition:

\[
X_i(t+1)=F_{\theta_i(t)}(X_i(t),M_i(t),D_i(t),Z_i(t),\varepsilon_i(t))
\]

Policy adaptation:

\[
\theta_i(t+1)=
\mathcal A(\theta_i(t),O_i(t),Q_i(t),C_i(t),V_i(t))
\]

The first changes the economic state. The second changes the rules or parameters. AI and reinforcement learning may propose adaptations, but cannot silently alter constitutional rights, property, debt, guarantees or material member entitlements. Significant adaptations require evaluation, authorization, versioning, rollback and audit.

# Part III — Stage-A kernel and its scope

## 11. What is implemented now

The file prototype/cellular_coordination.py implements a narrow local matching experiment:
- seven synthetic cells;
- three product classes (food, materials and energy);
- heterogeneous supply, demand and need priorities;
- a sparse inter-cell graph;
- shortest-path distance and logistics cost;
- four allocation regimes: market, central benchmark, cooperative pool and local cellular protocol;
- a configurable local communication/delivery radius;
- metrics for fulfilment, priority-weighted fulfilment, lower-cell fulfilment, inequality, logistics and coordination costs;
- deterministic seeds and stress variants.

The cellular protocol uses repeated local request rounds. A buyer contacts its nearest eligible supplier within the allowed hop radius. A supplier allocates available supply among the requests it receives using priority-weighted max-min rationing. Unfilled buyers may approach another supplier in a later round. The protocol does not compute a global optimal allocation.

## 12. What this kernel does not yet model

It is not yet a full dynamic economy. It currently omits:
- endogenous production from labour, capital and intermediate inputs;
- inventory carry-over and production planning across periods;
- household agents and heterogeneous income;
- cash budgets and actual payment settlement;
- credit, interest, maturity and default;
- ownership, profit, wages and distribution;
- capital formation and depreciation;
- environmental stocks and pollution;
- learning from realized outcomes;
- cell entry, exit, merger, split and federation governance.

The current "service value" is a diagnostic allocation metric, not GDP, profit, income, utility or measured social welfare. It must not be reported as empirical prosperity.

The existing seven-cell and general input-output prototypes remain intact. The cellular engine is an additional coordination layer intended to be integrated only after its local protocol and comparative design have been validated.

# Part IV — Fair comparative experiment

## 13. Institutional regimes

The first controlled comparison includes four regimes:

| Regime | Coordination rule | Information assumption |
|---|---|---|
| Market | Bilateral price/bid matching; buyers ranked by bid, sellers by delivered ask | Global market discovery in Stage A |
| Central benchmark | Global allocation by need priority and route cost | Full verified information; computational upper-bound reference |
| Cooperative | Common pool with priority-weighted max-min rationing | Collective pool sees declared needs and supply |
| Cellular SCCE | Repeated local request/offer and supplier response rounds | Only suppliers within the configured local hop radius |

A fifth hybrid regime should follow: local discovery and negotiation with market prices, plus voluntary federation routing when a local shortage persists. It must not be added until the four core arms are stable.

These regimes are intentionally different institutions. A single comparison cannot isolate every factor. Therefore, later experiments must cross coordination regime with information treatment, network density, communication delay and federation availability.

## 14. Equal initial conditions

Every regime must receive the same:
- cells, supply and demand;
- productive technology and input recipes;
- starting assets, cash and liabilities;
- product quality and prices or valuation rules;
- network topology and edge capacities;
- external shocks and random seeds;
- legal and ecological constraints;
- computational and coordination-cost accounting.

The central benchmark's full information is explicitly an upper-bound treatment, not an information-matched decentralized competitor. A second factorial experiment must give market, cooperative and cellular regimes the same local information radius and message delay. This prevents a hidden information advantage from being misattributed to institutional design.

All regimes must use the same objective weights in each matched run. The weights must be preregistered or varied in sensitivity analysis.

## 15. Outcome vector — no single score as the verdict

Report at least:

**Essential services**
- weighted and unweighted unmet essential demand;
- fulfilment by cell and by product;
- lower-decile and minimum cell fulfilment;
- quality-adjusted service and delay.

**Production**
- physical output by product (never add unlike units without an explicit index);
- value added net of intermediate inputs;
- idle capacity, bottlenecks and spoilage.

**Distribution**
- median and lower-decile household resources;
- service access inequality;
- cell-level fulfilment Gini;
- ownership and income concentration when those layers are implemented.

**Coordination**
- search, message, negotiation and governance cost;
- route distance, delivery delay and failed proposals;
- number and concentration of counterparties.

**Resilience**
- cumulative essential shortfall under shocks;
- time to recover to a declared service threshold;
- network fragmentation and cascade losses;
- liquidity failures and defaults when financial modules are integrated.

**Human and ecological outcomes**
- capability and time-autonomy indicators;
- safety and quality;
- energy, water and material intensity;
- emissions and ecological stock changes.

Show the vector first. A composite welfare index may be reported only as a secondary result with published weights, sensitivity ranges and distributional safeguards.

## 16. Statistical design

Use paired runs: each seed and shock realization is replayed under every regime. Compare paired differences, not unrelated averages.

Minimum procedure:
1. fix the scenario generator and initial-world seed;
2. run all regimes on the exact same world;
3. record all inputs, rule versions and event logs;
4. repeat over a preregistered seed range;
5. report means, medians, dispersion and confidence intervals;
6. run held-out network topologies and shocks;
7. conduct parameter sensitivity and ablation tests;
8. publish failures and adverse outcomes, not only successful cases.

The first kernel's deterministic comparison is a software/mechanism smoke test. It is not a calibrated experiment and does not establish statistical superiority.

## 17. Falsifiable hypotheses

- **H1 — Local matching:** under sufficiently connected networks and bounded search costs, local cellular matching reduces total search/coordination costs without materially increasing essential unmet demand.
- **H2 — Federation value:** adding voluntary multi-hop/federation routing reduces local dead ends and essential shortages enough to justify its governance and communication costs.
- **H3 — Resilience:** diversified inter-cell support lowers cumulative essential shortfall and recovery time under specified shocks after reserve, transport and financing costs.
- **H4 — Distribution:** need-sensitive allocation improves lower-decile service access without causing unsustainable production or liquidity losses.
- **H5 — Adaptation:** versioned local policy learning improves held-out performance versus fixed local rules without increasing rights violations, instability or concentration.
- **H6 — Failure boundary:** sparse or highly clustered networks, poor signals, high message delays and correlated shocks can make local cellular coordination inferior to global matching.

H6 is not an embarrassment; it identifies the conditions under which SCCE needs bridging links, federation, redundancy or another mechanism.

## 18. Predeclared failure conditions

The cellular mechanism must be revised or rejected in a tested domain if, across matched runs:
- essential unmet demand is persistently higher without compensating service-quality gains;
- coordination and governance costs erase the allocation gains;
- lower-decile service access deteriorates materially;
- local shortages persist despite unused reachable capacity elsewhere;
- network shocks create larger cascade losses than the baselines;
- policy adaptation increases volatility, capture, exclusion or rights violations;
- results depend on a narrow, hand-picked parameter region.

No single threshold is universal. Thresholds must be specified for each application before examining its test results.

# Part V — Research evidence and design cautions

## 19. What existing research warns us about

Agent-based research on local labour and goods matching finds that decentralized search can generate persistent coordination failures and underemployment even when a centralized matching system returns to full employment. This is a direct warning against assuming that locality automatically produces efficiency. See Guerini, Napoletano and Roventini, *No Man Is an Island: The Impact of Heterogeneity and Local Interactions on Macroeconomic Dynamics* (2018), [DOI: 10.1016/j.econmod.2017.10.003](https://doi.org/10.1016/j.econmod.2017.10.003).

COMMONSIM demonstrates a distinct bottom-up, needs-signalling and polycentric-network approach to coordinating production and social needs. It is a useful comparator, not proof that such a system is superior. See Gerdes et al., *COMMONSIM: Simulating the utopia of COMMONISM* (2023), [DOI: 10.1007/s43253-023-00110-0](https://doi.org/10.1007/s43253-023-00110-0).

Research on water trading with multi-agent cellular automata shows that information and transaction costs can materially reduce the surplus achievable by decentralized exchange. Therefore, the SCCE experiment must explicitly price communication, search, bargaining and enforcement rather than treating local matching as free. See Sapino et al., *A multi-agent cellular automata model to explore water trading potential under information transaction costs* (2023), [DOI: 10.1016/j.jhydrol.2023.129195](https://doi.org/10.1016/j.jhydrol.2023.129195).

A 2026 synthetic benchmark comparing centralized computational planning, agent-based markets and a hybrid mechanism reports planner advantages in its simulated settings, while explicitly discussing assumptions that may favour the planner. This is a useful methodological warning: benchmark architecture and information assumptions can predetermine the winner. See Fernández Salguero, *Testing Centralized and Polycentric Computational Planning* (2026), [arXiv:2606.19214](https://arxiv.org/abs/2606.19214).

## 20. Interpretation discipline

- A successful software test validates only the invariant tested.
- A synthetic scenario is not an empirical observation.
- A higher composite score is not proof of higher human welfare unless its components and weights are defensible.
- A global optimizer is an upper-bound benchmark, not a feasible institutional substitute.
- A market baseline must include realistic search, logistics, bargaining, market power and failure costs; it must not be deliberately weakened.
- A cooperative baseline must include realistic participation, governance, information and free-riding costs; it must not be idealized.
- A cellular baseline must include the real costs of messages, negotiation, network maintenance, federation and dispute resolution.
- Any regime must be allowed to fail.

# Part VI — Implementation roadmap

## 21. Staged implementation

**Stage A — local coordination kernel (current)**
- seven synthetic cells;
- local graph and request rounds;
- market, central and cooperative comparators;
- service and coordination metrics;
- invariant tests.

**Stage B — dynamic cellular state**
- connect the local protocol to the existing seven-cell production model;
- add per-cell opening/closing stocks and period-to-period inventory;
- add local production planning and supplier substitution;
- ensure physical balances after every transition;
- add event logs and deterministic replay.

**Stage C — household and distribution layer**
- heterogeneous household agents;
- multiple consumption baskets and essential floors;
- wage, service and ownership income;
- lower-decile welfare and exclusion measures.

**Stage D — financial and institutional layer**
- connect the six-sector SFC framework as the accounting interface;
- separate cash, deposits, reserves, credit and guarantees;
- add consent-based mutual credit, maturity and default resolution;
- add charters, voting mandates, appeals and exit.

**Stage E — ecological and resilience layer**
- multiple local resource stocks and regeneration;
- pollution, waste, transport and cross-cell externalities;
- network failure and recovery protocols.

**Stage F — learning and federation**
- local adaptation with bounded parameters;
- voluntary federation routing;
- versioned rules, canary rollout, rollback and adversarial tests.

**Stage G — scale and empirical calibration**
- 20, 50, 100 and 500 cells;
- empirical input-output and resource data;
- held-out regions and time periods;
- independent replication.

## 22. Immediate next tasks

1. Validate Stage-A algorithm and tests.
2. Run paired Monte Carlo sweeps over seeds, shocks and local hop radii.
3. Publish a transparent baseline comparison, including adverse results.
4. Add a message-delay and network-density experiment.
5. Only then connect the matching engine to the seven-cell production state transition.

The governing rule is simple: **build the local economic mechanism first; integrate finance as one subsystem; test the entire institutional arrangement against serious alternatives.**

---

**Status:** Stage-A local matching kernel and its unit tests are committed. The full dynamic SCCE cellular economy, financial integration, empirical calibration and superiority claims remain open research tasks.
