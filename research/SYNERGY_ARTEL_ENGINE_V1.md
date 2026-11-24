# SYNERGY Artel Engine — Institutional and Production Contract v1.0

**Document ID:** SYNERGY-ARTEL-001  
**Version:** 1.0 — 25 November 2026  
**Status:** design specification; implementation and jurisdiction-specific legal review pending  
**Parent:** SYNERGY Cellular Cooperative Market v1.0 and SYNERGY Cellular Consortium Economy  
**Authority:** Volumes I, III, IV, X, XI, XII, XIII and XV remain canonical for their respective domains.

## 1. Purpose and scope

The Artel Engine specifies how a voluntary production collective is constituted, receives a bounded production mandate, organizes work, uses committed resources, records contribution evidence, proposes distribution and exits or dissolves.

An artel is a **production and cooperation role**, not a universal legal form. Its legal implementation is jurisdiction-specific: for example, a registered production cooperative, another lawful entity, or a contractual production arrangement where permitted. The role label `artel` does not create legal personality, title, employment status, tax status, membership, debt, guarantee or entitlement to profit.

The Artel Engine is an institutional coordination layer. It does not replace or duplicate:
- the Canonical Economic Entity Register;
- the Legal Rights Register and authoritative title/encumbrance evidence;
- the Labour Register and verified work/delivery evidence;
- physical inventory, production, product and capital registers;
- the Financial OS, canonical journal, payment and settlement authorities;
- the Economic Router / Marketplace Registry;
- the CrossRegisterCoordinator and native participant adapters.

It stores or carries references to these authorities and validates the shape and scope of proposed coordination. It does not become a second source of truth.

## 2. The five orthogonal dimensions

Every artel record must keep these dimensions separate:

1. **Legal identity:** which legal person or contractual parties exist, in which jurisdiction and under which instrument.
2. **Production role:** which activities the artel is authorized and equipped to coordinate.
3. **Participation:** who participates, in what capacity, with what consent, term and exit rights.
4. **Decision authority:** who can decide which bounded matter, under what mandate and threshold.
5. **Economic rights:** who owns, uses, controls, licenses, receives, owes, guarantees or bears losses under authoritative evidence.

No dimension may be inferred from another. In particular:
- a worker is not automatically a member;
- a member is not automatically an employee;
- an investor is not automatically a governor;
- a contribution score is not ownership;
- a governance vote is not a title transfer;
- use of an asset is not ownership of that asset;
- a production role is not a legal form.

## 3. Artel lifecycle

The lifecycle is a state machine with explicit, versioned transitions:

`PROPOSED → CONSTITUTED → ACTIVE → (SUSPENDED | WINDING_DOWN) → CLOSED`

A proposal may be rejected or withdrawn before constitution. A suspended artel may resume only after the suspension cause and required approvals are resolved. Winding-down permits only actions necessary to complete, transfer or safely terminate existing obligations. Closed is terminal; a successor requires a new identity and explicit transfer instruments.

### 3.1 Proposed

Required proposal fields:
- stable proposal ID, purpose, sector and jurisdiction;
- proposed legal form or explicit contractual basis;
- founders and evidence of capacity to constitute;
- intended production scope and target customers/beneficiaries;
- initial assets, labour, finance and infrastructure requirements;
- draft constitution, risk allocation and exit terms;
- feasibility, safety, environmental and regulatory review references.

No production, financial or title authority is implied by a proposal.

### 3.2 Constituted

Constitution requires:
- authoritative legal-entity or contract references appropriate to the jurisdiction;
- a versioned constitution and effective date;
- verified initial participation and consent references;
- governance policy and reserved-matter schedule;
- defined production boundary and project accounting perimeter;
- asset-use/title evidence and IP treatment;
- labour, supplier, safety and service arrangements;
- treasury/accounting authority references;
- dispute, appeal, suspension, exit and dissolution procedures.

A digital record cannot cure a defective legal constitution.

### 3.3 Active

An active artel may coordinate only work inside its approved scope, resources and authority envelope. Each production cycle or project must be bound to a work package or project agreement with explicit inputs, outputs, milestones, responsible parties, capacity, dates, safety constraints, costs, evidence requirements and change-control rules.

### 3.4 Suspended and winding down

Suspension blocks new commitments except explicitly permitted protective actions. Existing worker, supplier, customer, safety and legal obligations remain in force. Winding down must preserve records, protect personal data, account for work in progress, return or transfer third-party assets, settle or dispute claims through canonical authorities, and handle IP and customer deliverables under existing instruments.

## 4. Participation and membership

Participation is non-exclusive by default and represented by a unique, time-bounded record:
- participant subject and host artel;
- capacity: member, worker, contractor, apprentice, investor, asset provider, service provider, advisor or delegate;
- consent/legal-basis reference;
- rights and obligations reference;
- effective interval and status;
- scope of work or decision mandate, where applicable;
- portability, withdrawal and exit conditions.

Capacities may coexist only where contracts and law permit; conflicts must be disclosed. Membership, employment, contracting, investment and voting are distinct. A participant may belong to multiple artels and cells. One artel cannot silently claim exclusive rights over a person's identity, skills, data, labour or unrelated work.

Admission, suspension and expulsion require disclosed criteria, notice, reason, opportunity to respond, impartial review and appeal. Expulsion is a protected action and cannot be executed by a generic DAO vote alone. Exit must not erase accrued wages, valid claims, safety rights, privacy rights or obligations already accepted.

## 5. Production mandate and work packages

The artel's production boundary is defined by versioned mandates, not by a broad claim to coordinate all member resources.

A work package contains:
- work-package ID and parent project/agreement reference;
- scope, deliverables, quality and acceptance criteria;
- responsible organization/team and named accountable roles;
- input quantities and units, sources and availability evidence;
- committed capacity and delivery windows;
- work estimates and safety constraints;
- permitted subcontracting and substitution;
- budget ceiling and authorized procurement envelope;
- cost, risk and contingency allocation;
- completion evidence, reviewer and dispute path;
- version, expected state revisions and idempotency key.

A work package is a coordination object, not a payroll record, purchase order, inventory reservation, contract, journal or payment. Each of those transitions remains with its designated authority. Contract formation requires the legally required party acceptance.

## 6. Asset and infrastructure boundary

Every resource used by an artel must be classified as one of:
- artel-owned;
- member-owned and specifically committed for use;
- leased or rented;
- licensed or accessed as a service;
- consortium/shared-infrastructure resource;
- customer-owned or third-party property;
- uncommitted and unavailable.

For each committed asset, carry authoritative references for title/owner, custodian, permitted use, capacity, location, condition, encumbrances, insurance, maintenance, duration, return condition and liability. The Artel Engine must not infer title from possession, contribution, payment, maintenance or a digital twin.

No asset or capacity is available merely because its owner participates in the artel. Commitment must be explicit, scoped, time-bounded and revocable under its instrument. Shared use does not create joint ownership. Capital providers may receive only the rights established by the relevant investment and title instruments.

## 7. Labour, contribution and compensation

Labour is governed by applicable law and the relevant employment, membership, contractor or service agreement. The Artel Engine may reference:
- accepted work order and worker consent;
- skills/capability evidence;
- planned and actual time or output;
- delivery and quality verification;
- safety and training records;
- wage/fee/benefit contract references;
- approved contribution evidence and dispute status.

It must not infer employment status, set legally binding wages, or substitute SCI for payroll, collective bargaining or labour law.

Contribution evidence is multidimensional and project-specific. It may include labour, verified output, capital services, IP licensing, equipment use, maintenance, care, coordination, risk stewardship and other agreed inputs. The same economic input must not be counted twice. Estimates must expose uncertainty, missing evidence and attribution limits. Participants must be able to inspect and appeal their own contribution records.

SCI may inform a pre-agreed contribution pool only. It must not automatically create ownership, votes, creditworthiness, debt, basic access rights or a universal reputation score.

## 8. Intellectual property and knowledge

For pre-existing IP, record its verified owner, licence, field, territory, term, sublicensing, confidentiality and permitted use. For newly created IP, the project constitution must specify before work begins:
- creator/inventor attribution where applicable;
- ownership or assignment basis;
- licence scope and revenue rights;
- background/foreground IP separation;
- open-source or publication obligations;
- third-party and data rights;
- maintenance, patent and enforcement costs;
- exit, insolvency and project termination treatment.

A contribution score or payment does not itself transfer IP. Disputed authorship or ownership blocks the affected transfer or distribution until resolved by the appropriate legal process.

## 9. Governance and subsidiarity

Decisions are allocated to the lowest competent level:
- individual: personal consent, personal data and individually held rights;
- work team: reversible scheduling and execution inside an approved package;
- artel: internal operating rules, member services and pooled resources explicitly committed to it;
- project board: project scope, milestones and change orders within delegated limits;
- consortium: only shared commitments and cross-party matters in its agreement;
- federation/DAO cell: cross-cell infrastructure, standards and externalities within a ratified mandate.

Every mandate defines subject, domain, action allowlist, amount/quantity/risk caps, term, evidence, approver, expected revision, conflict policy and appeal route. Delegation is explicit, scoped, revocable and verified by the canonical authority source.

Reserved matters include legal title transfer, new debt/guarantees, external payment release, changing existing claims, expulsion, fundamental rights changes, sensitive-data use, dissolution and emergency powers. These require dedicated legal/authority workflows; a generic vote or AI recommendation is insufficient.

## 10. Risk, liability and mutual guarantees

Risk is assigned explicitly to the party that controls, causes, insures or contractually accepts it, subject to applicable law. Each project must disclose:
- operational, delivery, quality, safety and environmental risks;
- market, price, liquidity and counterparty risks;
- asset damage, IP infringement and cyber risks;
- insurance and mitigation measures;
- default, cure, substitution and step-in rights;
- loss waterfall and dispute process;
- member liability limits and any guarantees.

No member, artel, cell or consortium is liable for another party's debt by implication. A guarantee requires a separate lawful instrument, verified authority, explicit cap, term, beneficiary, trigger, consideration and accounting treatment. Mutual-credit pools require prefunding/liquidity rules, exposure limits, concentration limits, default provisioning, recovery and suspension thresholds. No AI or DAO process may silently mutualize losses.

## 11. Surplus and distribution

The system must distinguish revenue, cash receipts, accounting profit, distributable surplus, retained earnings, capital return, wages, fees, dividends and non-cash claims. They are not interchangeable.

A proposed distribution can be calculated only from an authoritative, verified residual pool after the applicable legal and contractual obligations and solvency/reserve tests. The generic sequence is a design checklist, not a universal insolvency priority:
1. mandatory legal and tax obligations;
2. due wages, suppliers and contractual fees;
3. debt and secured claims under applicable law and contract;
4. agreed capital services and risk compensation;
5. required maintenance, replacement and resilience reserves;
6. approved reinvestment;
7. residual pools under the constitution;
8. collective-asset dividends under their own rules.

The constitution may define distinct pools for equal membership, verified ownership, project contribution, verified usage, needs/access and retained collective surplus. Each pool has an eligible population, evidence rule, policy version and dispute process. The pool weights must be approved before the measurement period, sum to no more than 100% of the verified residual and cannot be retroactively changed to confiscate accrued claims.

No allocation is payable merely because a proposal exists. Cash availability, solvency, legal priority, recipient eligibility, tax and payment authority must be checked by canonical systems at execution time. The Artel Engine emits a proposal/reference only; Financial OS and settlement authorities decide whether and how it can be posted or paid.

## 12. Relationship to the other SYNERGY mechanisms

| Mechanism | Artel interface | What it must not do |
|---|---|---|
| Cellular automaton | Receives aggregate, privacy-safe capacity/shortage/production signals; sends bounded state-change proposals | Infer title, consent or individual rights from a cell state |
| DAO cell | Supplies scoped governance, shared-service coordination and appeal routes | Command every purchase, wage or production decision |
| Consortium | Accepts or provides project-specific commitments among independent parties | Absorb uncommitted assets or make members jointly liable by default |
| Market / Economic Router | Discovers demand, offers and match candidates for the artel | Treat a candidate as a contract, reservation or settlement |
| Production OS | Executes approved work packages and records physical events | Rewrite legal rights or financial books |
| Labour / LEAGUES | Supplies verified capability, consent, work-order and delivery references | Infer membership, ownership or payment from skills/work completion |
| Financial OS | Supplies authoritative claims, cash, journal, solvency and settlement references | Be duplicated by artel-local balances |
| Blockchain | Anchors selected evidence, hashes, signatures and event provenance | Become a second mutable financial ledger or source of legal title |
| AI | Forecasts, matches, audits anomalies and proposes bounded options | Unilaterally admit/expel, set wages, transfer title, incur debt or release funds |

An artel may participate in multiple cells and consortia, and one cell may coordinate multiple artels. These are typed many-to-many relationships, not a strict ownership hierarchy.

## 13. Required event envelope

Artel events are proposals or references until accepted by their canonical authority. A common envelope should include:
- event ID, event type and schema version;
- artel ID, project/work-package ID and tenant;
- actor, principal and authority reference;
- consent/participation reference;
- subject and domain;
- effective time and recorded time;
- expected aggregate revision;
- source evidence references and provenance;
- policy/constitution version;
- idempotency/correlation key;
- payload digest and signature/attestation reference where required;
- status: proposed, accepted, rejected, disputed, superseded or reversed;
- appeal and correction references.

Events are append-only. Corrections supersede or reverse prior events; they do not rewrite history. A timestamp or hash alone is not proof of authority or truth.

## 14. Core invariants and adversarial tests

1. No participation without a valid host, consent/legal-basis reference and effective interval.
2. No production package outside the active artel/project mandate.
3. No asset use without a specific, valid use commitment and capacity.
4. No inferred ownership from work, payment, custody, membership or score.
5. No double booking of committed capacity across overlapping time windows.
6. No work assignment beyond verified capacity, skill/safety constraints or accepted consent.
7. No payroll, wage or employment inference from a work-package event.
8. No IP transfer without the specified legal instrument and authority.
9. No guarantee, debt or liability propagation without a separate explicit instrument.
10. No distribution without a verified residual pool and valid recipient evidence.
11. No distribution weights above 10,000 basis points; no retroactive confiscation of accrued claims.
12. No duplicate event, replay or changed-content idempotency key.
13. No generic DAO vote for a protected action.
14. No AI action outside a bounded, reversible, pre-authorized mandate.
15. No closure while unresolved safety, worker, customer, supplier, tax, title, data-retention or legal obligations remain unhandled.
16. Exit does not erase accrued claims or authorize retention of unrelated personal data.
17. Internal transfers are not consolidated income; stock/flow and asset/claim boundaries remain intact.
18. Every consequential transition is reproducible from evidence, authority, policy version and event history.

Adversarial suites must cover expired/revoked consent, forged or mismatched authority, overlapping work commitments, unavailable/encumbered assets, duplicate work delivery, disputed IP, insolvency before distribution, currency/unit mismatch, partial cross-register commit, coordinator crash/replay, malicious delegate, quorum manipulation, collusion, discriminatory admission, privacy leakage and attempted retroactive policy changes.

## 15. Metrics: do not optimize a single score

Report a vector, not a universal artel-health number:
- output, quality, productivity and delivery reliability;
- capacity utilization, downtime and work-in-progress;
- worker safety, pay timeliness, workload and retention;
- distribution by pool and participant group;
- lower-decile access and essential-needs effects;
- contribution-evidence coverage and appeal/reversal rates;
- ownership, voting and agenda concentration;
- asset maintenance and replacement adequacy;
- default, liquidity, guarantee and loss concentration;
- coordination, management, compliance and dispute hours/costs;
- IP and data-rights compliance;
- ecological footprint and resource regeneration;
- exit portability and participant satisfaction.

Any composite metric is secondary, versioned, weight-transparent and subject to sensitivity analysis. The artel's performance must be compared with feasible market, firm, cooperative and consortium alternatives under equivalent constraints.

## 16. Implementation sequence

**A0 — Specification review:** reconcile this contract with Volumes III, X, XI, XII and XIII; legal review by target jurisdiction; freeze vocabulary and event semantics.

**A1 — Read-only artel contract:** add typed references for artel identity, constitution version, participation, production mandate, work package, asset-use commitment, IP disposition and distribution policy. No writes to canonical ledgers.

**A2 — Boundary validator:** validate references, dates, status, capacity, authority, scope, consent, units, non-overlap and idempotency. Fail closed on missing evidence.

**A3 — Artel lifecycle service:** append-only proposal/constitution/activation/suspension/winding-down/closure transitions with explicit expected revisions and replay protection.

**A4 — Production adapter:** consume accepted work orders and verified skills; emit proposed physical work events for authoritative Production OS/physical registers.

**A5 — Contribution and distribution adapter:** consume verified labour/asset/IP evidence and authoritative residual-pool references; emit explainable proposals, never payroll or payment.

**A6 — Cross-register integration:** only after native authoritative participant adapters, recovery and exact-head crash/replay tests are complete. No synthetic conformance store may be described as production integration.

**A7 — Comparative experiment:** add the producer-cooperative/artel arm to the seven-arm CCM protocol with management, coordination, legal, safety, monitoring and exit costs charged. Do not claim the current Stage-A/B cooperative allocator already represents a legal artel.

## 17. Acceptance gates

The Artel Engine is not ready for production until:
- the jurisdictional legal form and instruments are reviewed;
- all rights/authority references resolve to canonical sources;
- adversarial and property-based tests cover the invariants above;
- overlapping membership and asset/work commitments are safe;
- lifecycle and cross-register crash/recovery behavior is demonstrated;
- financial and physical reconciliations close without double counting;
- privacy, security, appeal and independent audit are operational;
- comparative evidence includes negative results and full coordination costs.

**Conclusion:** an artel is the productive collective inside SYNERGY, but it is neither the whole cell nor the whole consortium. It organizes people and committed resources to produce; the DAO governs only its mandate; the consortium coordinates independent parties; the cellular network adapts across economic relationships; markets preserve outside options; canonical legal, labour, physical and financial systems retain authority.
