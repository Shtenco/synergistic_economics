# SYNERGY Cooperative Production Network v1.0

**Document ID:** SYNERGY-CPN-001  
**Version:** 1.0 — 25 November 2026  
**Status:** Research architecture and non-authoritative executable domain contract  
**Parent:** SYNERGY Cellular Cooperative Market v1.0 and Artel Engine v1.0

## 1. Purpose

The Cooperative Production Network (CPN) coordinates production across autonomous artels, cooperatives, enterprises, project vehicles, consortia and shared-infrastructure operators. It enables a network to discover complementary capacity and assemble multi-party production without converting participants into subsidiaries of a central corporation.

CPN is a coordination protocol, not a new legal entity, marketplace, inventory system, labour registry, asset registry, contract authority, financial ledger or settlement rail.

## 2. Architectural composition

CPN composes existing canonical components:

| Concern | Canonical authority | CPN responsibility |
|---|---|---|
| Legal identity and organizational roles | Economic entity register / `EconomicOrganization` | Check active counterparty references and declared roles |
| Demand, offers and deterministic candidate ranking | Economic Router | Consume demand, offer and match IDs; do not duplicate matching |
| Artel mandate and bounded work package | Artel Engine | Link a production order to an authorized artel scope |
| Skills, work eligibility and labour contracts | Canonical labour / skills / work-order services | Consume verified eligibility and accepted-work references |
| Asset title, availability and reservations | Asset / physical inventory authority | Consume capability and reservation evidence; never book assets itself |
| Contract formation and amendments | Legal / contract authority | Track proposal and acceptance references |
| Delivery and quality | Delivery / quality authority | Consume verified evidence |
| Accounting and payment | Financial ledger / settlement authority | Track settlement hand-off only |

A router match is only a ranked candidate. A CPN proposal is only a proposed production arrangement. Neither creates a contract, reserves capacity or obliges a person or organization to perform work.

## 3. Core domain objects

### 3.1 Production capability

A provider may publish a time-bounded capability declaration containing:
- provider organization ID;
- canonical Economic Router offer ID;
- canonical resource/asset reference;
- capability references and unit of measure;
- declared capacity and availability interval;
- asset-authority and evidence references;
- revision and status.

A capability declaration is not proof of ownership, exclusive control, safety certification or free capacity. Those facts must be resolved by the authoritative asset, licence, maintenance, safety and inventory systems. Availability is a discovery assertion; only an authoritative reservation creates a booking.

### 3.2 Production order

A production order extends, but does not replace, a canonical Economic Router demand. It binds:
- requester organization;
- router demand ID;
- bounded production scope and deliverable;
- required capabilities, quantity and unit;
- delivery window and quality criteria;
- contract-terms reference;
- expected revision and idempotency key.

Labour, subcontracting, IP, materials, logistics, insurance, risk allocation, acceptance criteria and payment milestones must be explicit in the governing contract. A production order does not itself authorize labour or expenditure.

### 3.3 Match proposal

A match proposal links one order, one router candidate, one canonical offer and one capability declaration. It includes counterparties, quantity, schedule, cost evidence, schedule evidence, terms reference and expected order/capability revisions.

Validation checks identity consistency, active organizations, capability coverage, unit and quantity compatibility, time-window intersection, evidence resolution and optimistic revision consistency. It does not recompute or override Economic Router ranking. When the provider carries the artel coordination role, the proposal must additionally bind a resolver-verified Artel Production Mandate and Artel Engine work-package reference; enterprise providers that are not acting as an artel are not forced into that mandate model.

Complex products are represented as a dependency graph of bounded work packages. Each node has inputs, outputs, acceptance criteria, predecessor references, responsible organizations and versioned evidence. Cycles must be rejected unless explicitly modeled as iterative processes with bounded convergence/termination criteria. Cross-artel collaboration is a graph of independent contractual commitments, not a parent-child ownership tree.

## 4. Work-order lifecycle

The reference lifecycle is:

`draft → published → matched → proposed → accepted → reserved → in_progress → delivered → verified → settled`

Branches:
- `published/matched/proposed → cancelled | expired`;
- `proposed → rejected`;
- `proposed/accepted/reserved/in_progress/delivered/verified → disputed`;
- `disputed → cancelled | delivered | verified` only through an explicit dispute-resolution authority.

Each transition is a versioned event with actor, authority domain, authority reference, timestamp and idempotency key. Every write must use compare-and-swap against the expected revision. The persistence layer must atomically enforce both revision checks and global idempotency uniqueness.

The authority domain is state-specific:
- publication/cancellation/expiry: workflow authority;
- match: Economic Router;
- acceptance/rejection: contract authority;
- reservation: physical inventory/asset authority;
- execution start: production mandate/execution authority;
- delivery: delivery authority;
- verification: quality authority;
- settlement: financial settlement authority;
- dispute: dispute-resolution authority.

The prototype accepts only references supplied by a canonical resolver. It does not validate signatures, legal capacity, revocation, tenant isolation, transaction atomicity or the truth of physical evidence; those remain resolver and deployment responsibilities.

## 5. Multi-party production and resource sharing

A complex product can be decomposed into work packages and joined through a directed acyclic dependency graph. Organizations retain their legal identity, assets, employees, contracts, liabilities and exit rights. The consortium agreement defines the shared scope and risk envelope. An artel's production mandate constrains only that artel's authorized work.

Shared equipment requires an explicit access/use agreement and a reservation from the asset authority. A provider may publish spare capacity without granting access. Temporary production teams are formed from opt-in, time-bounded participation and accepted labour/service contracts. CPN cannot infer worker consent, employment status, professional qualification, insurance, immigration eligibility or permission to use IP from an account, role or capability score.

Capacity aggregation must avoid double booking. CPN may display availability snapshots with source timestamp and revision, but the authoritative inventory/asset service must atomically reject overlapping reservations and stale revisions. Capacity advertised by several brokers or cells must be deduplicated by canonical resource identity.

## 6. Cost, schedule and risk evidence

Cost proposals must disclose currency, unit, quantity basis, included/excluded inputs, taxes/fees, transport, energy, tooling, labour, insurance, contingency and validity interval. Schedule evidence must identify resource calendars, lead times, dependencies, setup/changeover, maintenance and buffers. Quality evidence must define measurable acceptance tests, sampling, tolerances, traceability and independent review where needed.

Risk allocation must be explicit and proportional to control and ability to mitigate. Separate:
- input price and availability risk;
- capacity, downtime and maintenance risk;
- quality, rework and warranty risk;
- logistics, customs and force-majeure risk;
- labour safety and legal-compliance risk;
- IP, confidentiality and data risk;
- counterparty default and insolvency risk;
- currency, credit and settlement risk.

No risk is silently pooled across the network. Guarantees, insurance, collateral, debt and indemnities require separate valid instruments and authority.

## 7. Security, privacy and resilience invariants

1. Fail closed on missing, stale, ambiguous, revoked or mismatched authority/evidence.
2. Tenant and jurisdiction boundaries are enforced by canonical services; identifiers alone are not authorization.
3. Least disclosure: reveal only the capability and evidence necessary for a specific proposal.
4. Do not expose personal labour availability or sensitive production data without opt-in and purpose limitation.
5. Do not treat AI recommendations, rankings or forecasts as consent or commands.
6. Prevent replay, duplicate commitments and double booking through durable idempotency and authoritative atomic reservation.
7. Use immutable, append-only audit events with explicit corrections rather than silent mutation.
8. Support withdrawal before contract acceptance and contractually defined cancellation after acceptance.
9. Keep independent exit, appeal and dispute routes; do not let a platform operator adjudicate its own contested authority.
10. Never infer title, employment, debt, payment, ownership, profit share or legal agency from a match, proposal, reservation, delivery or score.

## 8. Cooperative Economic Intelligence interface

The intelligence layer may recommend:
- underutilized capacity and complementary demand;
- bottleneck resources and alternative suppliers;
- regional or cross-border production paths;
- candidate consortium compositions;
- make/buy/co-produce comparisons;
- resilience and concentration scenarios.

Every recommendation should carry source snapshots, freshness, confidence, assumptions, constraints, alternatives, distributional impacts and reasons for exclusion. Recommendations are advisory. Participants choose whether to publish capacity, reveal information, negotiate or accept a proposal. The AI has no authority to reserve assets, assign people, sign contracts or move funds.

## 9. Reference implementation and acceptance gates

`prototype/cooperative_production_network.py` provides immutable value objects for production capabilities, orders and match proposals, plus a guarded work-order transition function. It consumes organization references and resolver-supplied evidence sets; it does not persist state or call external authorities.

The initial test suite must cover valid matching; inactive or mismatched organizations; stale revisions; capability, quantity, unit and schedule mismatches; unverified evidence; invalid transitions; missing authority; wrong authority domain; stale compare-and-swap revisions; and idempotency replay.

Before production use, require: authenticated resolver adapters; tenant-scoped authorization; signed and revocable evidence; durable event store; atomic compare-and-swap and idempotency; authoritative inventory reservation; contract signing and legal review; labour/safety/IP adapters; delivery/quality attestation; settlement integration; independent audit; threat model; privacy impact assessment; and jurisdiction-specific legal review.

## 10. Research hypotheses

- H1: CPN can increase utilization of complementary capacity without materially increasing coordination overhead.
- H2: Multi-artel production graphs can reduce lead time for complex products relative to single-firm and spot-market baselines.
- H3: Network-level discovery improves resilience only when concentration, common-mode failure and transport constraints are measured.
- H4: AI-assisted matching improves candidate quality without reducing participant autonomy or privacy.
- H5: Governance and coordination costs may outweigh utilization gains at low transaction density; this must be measured, not assumed away.

The benchmark must compare open-market procurement, bilateral contracting, vertically integrated production, consortium production and CPN coordination under identical demand, resource, quality, transport, labour and shock conditions. Report utilization, lead time, defect/rework, total landed cost, coordination hours, cancellation/default, concentration, worker outcomes and ecological burden. No superiority claim is justified before preregistered, reproducible comparisons.
