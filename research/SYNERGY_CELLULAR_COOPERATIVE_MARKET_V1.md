# SYNERGY Cellular Cooperative Market v1.0

**Document ID:** SYNERGY-CCM-001  
**Version:** 1.0 — 24 November 2026  
**Status:** research architecture and executable domain-contract proposal; not a legal, accounting or production settlement system  
**Parent theory:** Volumes I, III, IV, V, VIII, IX, X, XI, XII, XIII, XIV and XV  
**Institutional predecessor:** SYNERGY CELLULAR CONSORTIUM ECONOMY (SCCE) v0.1

## Abstract

This specification extends the existing SYNERGY CELLULAR CONSORTIUM ECONOMY (SCCE). It does not replace the consortium-cell concept, SCCE cellular transition model, existing market router, contribution/ownership/distribution theory, UEP/UOF architecture, or accounting and event authorities.

A **cellular cooperative market** is a polycentric economic network in which autonomous people, households, firms, cooperatives, artels, project alliances and shared-infrastructure institutions interact through markets and voluntary cooperation. DAO cells provide bounded coordination and governance; artels provide a possible legal and productive form for joint work; consortia coordinate independent organizations around a defined project or shared resource; markets discover prices, demand, supply and exchange opportunities. These are complementary dimensions, not interchangeable entity types.

The central architectural correction is to separate five things often incorrectly collapsed:

1. **Legal form** — what a subject legally is in its jurisdiction.
2. **Coordination role** — what function it performs in the economic network.
3. **Membership and participation** — who participates, in what capacity, and under which consent.
4. **Decision authority** — who may decide which question, under what mandate.
5. **Economic rights** — who owns, uses, controls, receives income from, bears liability for, or may transfer an asset or claim.

A single organization may carry multiple coordination roles. A person may participate in several non-exclusive cells, artels and projects. A consortium may be a contract among independent organizations rather than a new legal person. A DAO is a governance and execution mechanism, not an automatic legal form. A market is an allocation mechanism, not an organization.

The objective is not equal outcomes by decree. It is **procedurally fair, rights-constrained, contestable and economically viable cooperation**, with voluntary exchange, plural ownership, transparent claims, bounded authority, competitive alternatives and measurable effects on broad prosperity.

## 1. Relationship to the existing SYNERGY theory

This is a derived institutional extension, not a new foundational axiom set.

- Volume I remains the canonical source of foundational axioms and design principles.
- Volume 0A remains the methodological and accounting-integrity control.
- Volume II retains distinctions among value, price, output, income, wealth, surplus and productive capacity.
- Volume III remains authoritative for contribution evidence, ownership as a bundle of rights, plural distribution mechanisms, SCI, UEP, UOF and collective dividends.
- Volumes IV and V remain the formal and executable economic-model foundations.
- Volumes VII–IX retain reproducible wealth, net synergy, network dynamics, positive and negative feedback, concentration and resilience.
- Volume X remains the institutional-design and polycentric-governance foundation.
- Volumes XI–XIII remain authoritative for money, credit, settlement, capital, labour, contribution and income.
- Volume XIV retains wellbeing, needs, capabilities and ecological limits.
- Volume XV remains the integrated conceptual architecture.

SCCE already defines the economic cell as a voluntary, bounded and accountable coordination unit; permits overlapping cells; separates membership, voting, ownership and contractual participation; and treats the cellular network as a typed multilayer graph. This document makes the legal-form / coordination-role distinction explicit and adds a market-facing institutional composition and testable prototype contract.

No claim is made that the architecture is empirically superior. That is a research hypothesis to be tested against market, firm, cooperative, hierarchical, centralized and hybrid alternatives under comparable conditions.

## 2. Canonical ontology: five orthogonal dimensions

### 2.1 Legal form

Legal form is jurisdiction-specific and must be resolved by an authoritative legal-entity source and applicable law. Examples may include a company, partnership, production cooperative, consumer cooperative, association, foundation, public body or contractual joint venture. Allowed forms and requirements are not universal protocol constants.

A legal-form adapter should carry jurisdiction, legal-form code, registration or constitutive-document reference where applicable, legal status, authorized representatives, liability regime and effective dates. The canonical economic-entity register establishes entity identity and sector classification; it does not by itself prove beneficial ownership, title, licence, authority to sign or enforceability of a particular contract.

### 2.2 Coordination role

Coordination roles describe functions, not legal personality. An organization may carry one or more roles:

- **ARTEL / PRODUCER COOPERATIVE:** members jointly organize production and may pool labour, capital or assets under applicable cooperative law and charter.
- **DAO CELL:** a bounded governance and coordination community with a defined participation perimeter, mandate, decision domains and appeal path. It may or may not coincide with a legal entity.
- **CONSORTIUM:** a scoped collaboration among two or more independent economic subjects. It may be contractual or separately incorporated; the chosen legal form must be explicit.
- **FEDERATION:** a coordination arrangement among cells, cooperatives or consortia for matters with cross-boundary effects. It does not automatically own or control its members.
- **ENTERPRISE / PRODUCER:** an organization that offers goods or services and bears its own commercial obligations.
- **PROJECT VEHICLE:** a scoped legal or contractual boundary for a defined project, asset or risk pool.
- **SHARED-INFRASTRUCTURE OPERATOR:** an entity entrusted with operating a common service under published access, cost, maintenance and accountability rules.

Roles can overlap. A registered production cooperative can operate as an artel, participate in a consortium and be represented in a regional federation. A DAO cell may coordinate members of several separate legal entities without absorbing them.

### 2.3 Membership and participation

Membership, employment, contracting, service use, investment, delegation and voting are distinct relationships. They must not be inferred from one another.

Participation is non-exclusive by default. The same person or organization may join multiple cells, cooperatives and projects unless a specific lawful contract imposes a disclosed, proportionate restriction. One membership must not grant access to unrelated personal data, assets or memberships.

Every participation record must specify subject, host organization/cell/project, capacity, consent or legal basis, rights granted, obligations accepted, effective interval, status, exit process and evidence reference.

### 2.4 Decision authority

Decision authority is scoped by subject, domain, action, amount/risk threshold, duration and delegation. It is not derived automatically from token balance, capital contribution, contribution score, reputation, compute power or network centrality.

### 2.5 Economic rights

Ownership and economic claims are bundles, not scalar scores. For every asset or claim, distinguish legal title, beneficial interest, possession/custody, use, exclusion, operational control, income, transfer, residual control, governance, maintenance duties, liability and dissolution rights. The Legal Rights Register and authoritative legal evidence remain the rights authority.

## 3. Network topology: overlapping cells, not a command pyramid

Represent the system as a time-indexed, typed, multilayer graph:

\[
\mathcal N_t=(V_t,E_t,\Lambda,\Pi_t)
\]

Nodes include persons, households, enterprises, cooperatives, artels, DAO cells, consortia, projects, assets and infrastructure. Edges include membership, contract, supply, service, ownership, use, delegation, federation, shared infrastructure and evidence links. The edge metadata contains permissions, capacity, cost, effective intervals and provenance.

The graph is **overlapping and typed**, not a strict tree. A cell may have multiple federation links; a consortium may include several artels and independent firms; an artel may sell on the open market and participate in more than one consortium. A parent-child edge must never be inferred from geographic proximity, a shared platform account or a DAO vote.

A network link creates no property right, guarantee, debt, agency relationship or authority unless a separate valid instrument explicitly creates it.

### 3.1 Three institutional dimensions

| Structure | Primary question | Main function | Does not automatically do |
|---|---|---|---|
| DAO cell | Who coordinates and decides this bounded matter? | Local governance, discovery, shared rules, mutual-aid proposals | Own member assets, compel labour, settle money, override contracts |
| Artel / cooperative | Who jointly produces and holds the relevant productive rights? | Production, member participation, cooperative assets and surplus | Control the whole market or other independent organizations |
| Consortium | Which independent subjects collaborate on this scoped project? | Combine capabilities, capacity, finance, logistics and risk by agreement | Absorb members, acquire their assets, create a universal hierarchy |

The **market** is a cross-cutting mechanism, not a fourth hierarchy layer. The market router discovers and ranks opportunities; parties negotiate and accept contracts; authorized financial and legal authorities govern settlement and rights.

## 4. Subsidiarity and decision jurisdiction

A decision belongs to the lowest competent level that can internalize its material effects and meet required legal, technical and risk constraints.

Candidate decision domains:

1. Personal: personal data, labour availability, voluntary membership and personal property.
2. Household: shared household resources, subject to each member's rights.
3. Work team / project: task allocation, delivery process and project execution within contract.
4. Artel / cooperative: member admission, production policy, cooperative assets and member distributions under its charter.
5. Consortium: only the shared project, shared asset or joint obligation defined by its agreement.
6. Regional / sector federation: cross-cell infrastructure, standards, externalities and network risks within a delegated mandate.
7. Platform / protocol: interoperability, security, common schemas and operator obligations.
8. Public authority: matters reserved to law and public institutions.

A higher-level body may coordinate, set compatible interfaces or resolve a conflict of competence. It may not assume a lower-level decision merely because it has more members, capital or computing resources.

### 4.1 Authority envelope

Every consequential automated or collective action must be bound to actor and principal identity; authority grant and delegator; subject and tenant scope; permitted action and decision domain; amount, quantity and risk limits; effective interval and expiry; expected aggregate versions; evidence and policy version; idempotency/correlation identifiers; and audit and appeal route.

Missing, expired, ambiguous or revoked authority fails closed. A proposal, vote or AI recommendation is not itself an executable command.

### 4.2 Reserved matters

Constitutional rights, involuntary member expulsion, legal title transfer, external payment release, new debt/guarantee, changes to existing claims, use of sensitive data, dissolution and emergency powers require explicit legal and procedural safeguards. They must not be executed solely because a generic DAO threshold was reached.

## 5. Market and cooperation are complementary

The market mechanism is used where prices, bids, offers, contracts and competition reveal dispersed information and provide an outside option. Cooperation is used where shared assets, indivisible projects, network effects, risk pooling, common infrastructure or repeated exchange justify joint rules.

A project must not presume that cooperation is always superior to market contracting, or that market exchange is always superior to joint ownership. For each task, compare feasible institutional alternatives.

The existing Economic Router remains the canonical opportunity-discovery and deterministic matching component. The cellular-cooperative layer consumes its typed references (DemandSignal, Offer, MatchCandidate) and adds organizational eligibility, cooperation topology and mandate checks. It must not introduce a shadow demand/offer registry, duplicate matching engine, second EventStore, financial ledger or payment authority.

A router match is a candidate, not a contract. Contract formation requires explicit party acceptance. Inventory reservation, title transfer, escrow, delivery verification and settlement remain with their respective authorized authorities.

The existing SYNERGY LEAGUES domain is the capability/work-order layer: evidence-backed skill profiles, opt-in discoverability, work-order application and assignment, delivery review, and settlement hand-off. The cooperative-market layer should consume its verified skill/evidence and accepted-work references rather than create a second skills or work-order registry. League membership is a capability/participation context, not a paid tier, legal cooperative membership, ownership share or governance vote. An accepted work order is not proof of payment; the authoritative financial/settlement service remains responsible for that transition.

### 5.1 Four exchange modes

- **Open market:** independent buyers and sellers transact under accepted terms.
- **Cooperative production:** members jointly organize inputs, work and output under a cooperative constitution.
- **Consortium project:** independent organizations commit specified capabilities, assets or finance to a scoped project agreement.
- **Common-pool / mutual aid:** participants voluntarily contribute or receive a defined common resource under eligibility, capacity, replenishment and loss-allocation rules.

A project may combine these modes, but every interface must be explicit. An artel may buy steel on the open market, join a consortium for a large contract, use a regional shared logistics service and contribute voluntarily to a common training fund.

## 6. Cooperative project constitution

Before work begins, a cooperative project or consortium must publish a versioned constitution/agreement containing:

1. parties and legal capacity;
2. scope, deliverables, time horizon and jurisdiction;
3. inputs, capacities, constraints and evidence;
4. ownership and permitted use of pre-existing assets;
5. ownership/licensing of newly created intellectual property;
6. labour, supplier, service and capital contracts;
7. decision domains and delegated authority;
8. risk, insurance, guarantees and loss allocation;
9. pricing and external-market obligations;
10. accounting boundary and authoritative registers;
11. verified distributable pool definition;
12. distribution pools and eligibility;
13. reserves, maintenance and reinvestment;
14. dispute, independent review and appeal;
15. withdrawal, substitution, portability and dissolution;
16. insolvency, default and treatment of unfinished work;
17. data access, confidentiality, privacy and retention;
18. amendments, versioning and non-retroactivity.

No participant should be asked to contribute labour, capital, IP or guarantees before the relevant rights, risks, compensation and exit conditions are disclosed.

## 7. Fairness architecture: separate the questions

The system must not reduce fairness to equal division, a contribution score, token voting or a single weighted index.

### 7.1 Five separate tests

**A. Rights and due process:** Are legal rights, consent, contract, privacy, safety and appeal protected?

**B. Voluntary participation:** Is there a real outside option? Are exit costs disclosed and proportionate? Are unrelated rights preserved on exit?

**C. Contribution and responsibility:** Are measurable contributions and accepted responsibilities evidenced without double counting? Are invisible work, maintenance, care, coordination and risk stewardship considered where relevant?

**D. Distribution and capability:** Who receives the gains, bears the losses and can effectively access opportunities, tools, markets and governance?

**E. System effects:** Does the arrangement improve net productive capacity and resilience without shifting costs to other cells, periods, people or ecosystems?

These tests are not interchangeable. A project cannot compensate for an unlawful title transfer with a high contribution score, or for an unbalanced journal with an equal dividend.

### 7.2 Distribution waterfall

Volume III remains authoritative. The system must first identify a valid accounting and causal boundary, then verified revenue and cash availability, then legal claims and obligations, then the residual pool. A generic design sequence is:

1. mandatory legal, tax and senior obligations;
2. due wages, suppliers and contractual fees;
3. debt service and secured claims according to law and contract;
4. agreed capital services and risk compensation;
5. required maintenance, resilience and replacement reserves;
6. approved reinvestment;
7. residual distribution under the pre-agreed project constitution;
8. collective dividends from the relevant collective asset under its own rules.

This is not a universal legal priority order. Insolvency law, employment law, security interests and contract may change it. The applicable authority decides.

### 7.3 Plural residual pools

A project may partition verified distributable residual surplus into separately governed pools:

\[
S = S_{equal}+S_{ownership}+S_{contribution}+S_{needs}+S_{usage}+S_{collective}+S_{retained}
\]

Each pool has its own eligible population and authority: equal membership uses valid membership rules; ownership uses verified ownership/claim records; contribution uses project-specific evidence and SCI profile; needs/access uses disclosed criteria with privacy safeguards; usage uses verified use of a shared asset/service; collective remains with the common asset; retained remains in reserves or undistributed surplus.

Pool weights are agreed before the measurement period, sum to no more than 100% of the relevant residual, and must not be retroactively changed to confiscate accrued claims. Zero denominators, disputed evidence, unavailable cash or failed solvency checks block or retain the affected pool under the pre-agreed rule.

### 7.4 SCI is evidence, not title or voting power

SCI remains project-specific, multidimensional, uncertainty-aware and appealable. It may inform a pre-agreed contribution-reward pool. It must never automatically create legal ownership, debt, voting power, basic access rights, creditworthiness or human-worth ranking.

Capital contribution, labour contribution, risk bearing, ownership and governance remain separate dimensions. The same input must not be counted twice as both returned principal and permanent ownership unless a valid contract expressly creates both claims.

### 7.5 Fairness dashboard

Do not publish one scalar fairness score as the truth. Publish a vector including distribution by recipient group and pool; lower-decile and median outcomes; unmet essential needs and effective access; contribution evidence coverage and uncertainty; ownership and voting concentration; exit cost and portability; dispute and reversal rates; unpaid/overdue obligations; risk and loss incidence; ecological and intergenerational effects; coordination and administration costs.

A composite index may be reported only as a secondary diagnostic with transparent weights and sensitivity analysis.

## 8. Anti-capture and market contestability

Measure and constrain concentration in ownership, voting, agenda control, platform access, data, capital, network centrality, supplier dependence, infrastructure, AI/compute and dispute resolution.

Safeguards include justified governance rules; separate capital-return rights from governance rights; concentration caps or graduated voting where lawful; conflict-of-interest disclosure and recusal; independent audit and appeal; open access criteria; transparent fees and related-party transactions; portable identities, records and interfaces; multiple providers for critical infrastructure where feasible; anti-collusion controls; protection of minority members and affected non-members; no self-audit by the operator; and no retroactive alteration of accepted contract terms.

Decentralization is not proof against capture. A large cell, validator coalition, platform operator or capital provider may still dominate. Capture is a measurable failure mode.

## 9. Mutual aid and common-pool mechanisms

Mutual aid is voluntary and bounded. A common pool must specify source and legal owner of funds/assets; contributor consent; eligible beneficiaries and triggers; cap per beneficiary and period; prefunding and liquidity; replenishment and withdrawal rules; loss allocation and default treatment; audit, privacy and appeal; and prohibition on implied guarantees.

No cell is automatically liable for another cell's debt. No reserve may be represented as available if pledged, restricted, illiquid or already committed. Internal transfers do not create consolidated income or net wealth.

## 10. AI and autonomous coordination

AI may forecast shortages, identify suppliers, compare institutional alternatives, estimate coordination costs, detect anomalies, propose matches, summarize evidence and simulate policy effects.

AI may not unilaterally create legal entities, admit or expel members, alter title, create debt or guarantees, set binding wages, release funds, determine contested facts, suppress appeals or amend constitutions.

Automated execution is permitted only for pre-authorized, reversible, bounded actions with policy version, expected-version checks, idempotency, monitoring, audit, rollback and kill switch. Consequential or irreversible actions require authorization prescribed by law and the project constitution.

## 11. Accounting, identity and event authority

The cooperative-market layer must integrate with existing canonical authorities rather than duplicating them:

| Domain | Canonical authority / boundary |
|---|---|
| Economic entity identity and institutional sector | Canonical Economic Entity Register; does not prove title |
| Legal title, claims, encumbrances and extinguishment | Legal Rights Register and authoritative legal evidence |
| Labour offers, consent, delivery and verification | Labour Register and verified evidence |
| Physical production, inventory and movement | Physical/product/capital registers and approved adapters |
| Financial claims, deposits, loans, payments and settlement | Operating Financial Register, approved payment/bank adapters and canonical journal |
| Cross-register transaction visibility | CrossRegisterCoordinator and native participant contracts |
| Stock-flow and sector projections | Typed SFC/GOLD projection pipeline |
| Demand/offer discovery and candidate matching | Economic Marketplace Registry and Economic Router |
| Skills, capability evidence and work orders | SYNERGY LEAGUES domain and its verified evidence references |
| Spatial representation | Spatial twin adapter; never title or settlement authority |

The existing implementation has explicit unfinished integration gates. The six-register coordinator still requires native authoritative adapters for all participants before a complete cross-register transaction can be claimed. Financial register history is not yet a live six-sector SFC projection merely because local stock-flow mappers exist. A spatial adapter validates references but does not post journals or settle money.

The new layer therefore uses references and proposed commands. It must not post a journal, mutate balances, settle payments, transfer title or reserve physical stock.

## 12. Economic state and performance

The system-level state extends the SCCE state vector without collapsing dimensions:

\[
X_t=(Q_t,K_t,S_t,M_t,F_t,R_t,H_t,E_t,P_t,G_t,C_t)
\]

The existing physical, capital, service, money, financial, rights, labour, ecological and projection dimensions are retained; G describes governance mandates and institutional state; C describes contracts, market opportunities and cooperation commitments.

Every state variable retains unit, scope, time, evidence, authority and uncertainty. No scalar cell-health measure may replace the vector.

### 12.1 Net synergy

For a declared outcome vector Y, a candidate net-synergy estimand is:

\[
\Delta_{syn}=Y_{cellular\ cooperative\ market}-Y_{counterfactual}
\]

The counterfactual must be a feasible alternative under comparable resources, information, shocks, legal conditions and participant composition. Outcomes should include productive capacity, transaction and coordination costs, resilience, wellbeing/capability, distribution, ecological effects and rights violations. Report the vector and uncertainty; do not compress all outcomes into one number without a declared normative weighting.

## 13. Testable hypotheses

- **H1 — Institutional fit:** assigning market, cooperative, consortium and federation mechanisms to tasks according to coordination characteristics reduces total coordination and failure costs relative to one universal mechanism.
- **H2 — Overlapping membership:** non-exclusive, portable membership increases capability matching and resilience without unacceptable privacy, conflict or coordination costs.
- **H3 — Artel productivity:** cooperative production improves some combinations of quality, retention, innovation or resilience when members have credible governance and enforceable rights; it may underperform where decision costs, free-riding or capital constraints dominate.
- **H4 — Consortium complementarity:** scoped consortia enable feasible projects that individual participants cannot execute, but increase contracting, monitoring and hold-up costs.
- **H5 — Polycentric subsidiarity:** local decisions improve use of dispersed knowledge when cross-cell externalities and shared infrastructure are adequately coordinated.
- **H6 — Plural distribution:** separating ownership, contribution, needs/access and collective pools reduces category errors and perceived arbitrariness compared with a single composite score.
- **H7 — Anti-capture:** contestable markets, exit, portable data, independent audit and separated authority reduce concentration of effective control.
- **H8 — Mutual aid:** prefunded, capped and voluntary mutual aid improves shock resilience without creating hidden contingent liabilities.
- **H9 — AI boundedness:** AI support inside a limited mandate reduces search and coordination costs without increasing unauthorized decisions, exclusion or unreviewable errors.
- **H10 — Complexity threshold:** additional governance layers improve outcomes only while marginal coordination benefit exceeds administration, delay and capture costs.

Each hypothesis requires pre-registered scenarios, explicit baselines, uncertainty analysis, adversarial cases and criteria for rejection. Synthetic simulation is not empirical validation.

## 14. Comparative experiment design

Minimum comparison arms:

1. decentralized bilateral market;
2. conventional firm / hierarchy;
3. member cooperative / artel;
4. scoped consortium;
5. SCCE consortium-cell;
6. cellular cooperative market (hybrid);
7. centralized allocation benchmark, explicitly labelled as an information/optimization benchmark rather than a realistic state.

Hold constant initial resources, production technology, demand, information access, legal constraints, shocks, participant heterogeneity and evaluation horizon. Where mechanisms require different information or administration, model those costs rather than giving one arm a free omniscient planner.

Stress scenarios: demand and supply shocks; supplier failure and logistics disruption; capital shortage and liquidity shock; member exit and consortium dissolution; strategic misreporting and contribution-score gaming; voting concentration and collusion; platform outage or operator insolvency; dispute backlog and delayed verification; ecological resource constraints; correlated failures and cascading defaults; cross-border legal incompatibility; AI recommendation or authorization failure.

Primary metrics: unmet demand, output and quality, productive capacity, transaction/coordination cost, cash and stock-flow consistency, insolvency/default, lower-decile wellbeing/access, concentration, exit cost, dispute resolution, ecological balance and unauthorized action rate.

## 15. Implementation phases

- **P0 — Ontology and authority map:** define legal form, coordination roles, membership, mandates, rights and canonical sources.
- **P1 — Structural registry contract:** validate organization, role, membership and typed relations without creating a new authoritative entity register.
- **P2 — Market bridge:** consume existing demand/offer/match references; no duplicate matcher or shadow registry.
- **P3 — Project constitution:** validate scoped participants, contributions, ownership references, risk and contract terms.
- **P4 — Governance gate:** validate authority envelopes and decision records; never execute legal/financial side effects.
- **P5 — Distribution-plan validator:** validate pool definitions and basis-point budgets; output proposals only, using evidence references from canonical sources.
- **P6 — SCCE experiment:** compare the hybrid with alternatives under paired seeds and preregistered metrics.
- **P7 — Legal and operational pilots:** jurisdiction-specific legal forms, accounting, data protection, dispute, security and payment integration.

## 16. Acceptance criteria for v1

A v1 implementation is accepted only if it distinguishes legal form from coordination role; permits overlapping, non-exclusive participation; prevents implicit hierarchy, ownership, guarantee or agency inference; enforces typed and time-bounded relationships; scopes governance authority; separates voting, contribution, ownership and economic entitlement; requires bilateral consent for market/cooperation commitments; validates project constitutions before work starts; validates distribution pools only against a verified residual input; uses exact integer minor units and basis points where money is referenced; never posts journals, settles funds, transfers title or reserves physical stock; references existing canonical authorities; supports audit, correction, appeal and exit; includes adversarial tests; and reports software evidence separately from empirical and legal validation.

## 17. Open questions

- Which legal forms are available and suitable in each jurisdiction, and which require direct member labour?
- When should an artel be a registered production cooperative versus a contractual production team or ordinary enterprise?
- Which consortia require a separate legal person, and which should remain contract networks?
- What is the appropriate cell size for different tasks? The 10+1 micro-cell and larger SCCE consortium-cell are distinct hypotheses, not a universal size.
- Which governance domains require one-member/one-vote, double-chamber representation, stakeholder representation or contractual consent?
- How should capital providers receive risk-adjusted returns without purchasing unbounded governance control?
- Which common assets should be collectively owned, held in trust, or provided by independent operators?
- What evidence and appeal process is proportionate for contribution and needs/access pools?
- What is the least costly way to make exit and portability real?
- Which market-power and cross-cell externality rules require public regulation rather than platform governance?

## Conclusion

The cellular cooperative market is not a new central institution above participants. It is a compatible protocol for composing autonomous actors and organizations.

DAO cells coordinate bounded decisions. Artels and cooperatives organize joint production and member rights. Consortia connect independent organizations around scoped projects. Firms and individuals remain free to trade and compete. Federations coordinate genuine cross-boundary problems. The market router discovers opportunities. Canonical legal, physical, labour and financial authorities remain the sources of truth for their respective domains.

The governing principle is **plural institutional forms under common rights, evidence, interoperability and accounting constraints**. Cooperation must remain voluntary, markets contestable, shared assets accountable, and every consequential authority bounded and appealable.

The model succeeds only if comparative evidence shows that it improves real productive capacity, resilience and effective opportunity without unacceptable increases in complexity, concentration, rights violations or hidden liabilities.
