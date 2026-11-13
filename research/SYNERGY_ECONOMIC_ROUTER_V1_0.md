# SYNERGY ECONOMIC ROUTER v1.0

**Status:** implementation baseline / review required  
**Canonical owner:** `Shtenco/synergistic_economics`  
**Spatial consumer:** `Shtenco/synergy_metaverse`  
**Protocol family:** `synergy.economic-router.*`

## 1. Purpose

The Economic Router discovers, qualifies, matches and coordinates lawful economic opportunities between buyers, sellers, service providers, producers, resource owners and authorized agents. It is an orchestration layer, not a replacement for the economic model, accounting system, identity provider, payment provider, legal registry or settlement authority.

The first production-shaped slice is deterministic demand-to-offer matching. Later slices add multi-party graphs, contracts, protected settlement, disputes, agent-to-agent commerce and cross-border routing.

## 2. Authority map — one fact, one authority

| Fact / operation | Authority | Router responsibility |
|---|---|---|
| Economic model, canonical events and accounting truth | This repository's economic core and its approved register adapters | Reference IDs and submit typed commands; never maintain a shadow ledger |
| Legal identity and permissions | Approved identity / authorization provider | Consume verified assertions and scopes |
| Offer and demand discovery | Lead Radar / marketplace ingestion | Normalize, deduplicate, qualify, expire |
| Match ranking | Economic Router | Deterministic candidate generation and explainable ranking |
| Contract formation | Contract service plus applicable legal process | Prepare a proposal; require explicit party acceptance |
| Payment custody and settlement | Licensed / authorized payment or escrow provider and canonical financial authority | Create payment intents and reconcile external receipts |
| Disputes and delivery verification | Contract-specific evidence and independent dispute process | Track states and evidence references; do not decide physical truth from an AI score |
| Spatial representation | Metaverse spatial registry | Display a reference to an economic object; no ownership or settlement authority |

No module may independently invent an authoritative balance, title, debt, revenue, delivery completion or payment finality.

## 3. Core domain objects

- `DemandSignal`: buyer intent, category, scope, quantity, jurisdiction, budget ceiling, currency/scale, required capabilities, evidence, consent/legal basis, expiry and status.
- `Offer`: seller identity reference, category, capabilities, quantity/capacity, price, currency/scale, jurisdiction, evidence, verification state and expiry.
- `MatchCandidate`: immutable references to demand and offer, explainable score, compatibility facts, timestamp and routing policy version. It is not a contract.
- `ContractProposal`: proposed parties, scope, deliverables, milestones, acceptance criteria, remedies, jurisdiction and payment schedule. Proposal is not binding until valid acceptance.
- `DealCase`: lifecycle projection over contract, evidence, dispute and settlement references; no parallel financial balance.
- `SettlementIntent` / `SettlementReceipt`: request and externally authoritative result; only canonical financial/payment services confirm settlement.
- `EconomicEdge`: typed, time-bounded, provenance-bearing relation between graph nodes. An edge never implies title unless it explicitly references a separately verified legal claim.

Money is represented as integer minor units plus ISO-like currency code and scale. Floating-point amounts are forbidden. Effective time and recorded time are distinct. IDs are opaque and tenant-scoped where required.

## 4. Matching v1

The v1 matcher is deliberately conservative:
1. Demand is open and not expired.
2. Offer is active, not expired and seller verification is explicitly `verified`.
3. Category and jurisdiction match exactly.
4. Currency and scale match exactly; no implicit FX.
5. Offer price does not exceed demand budget.
6. Capacity covers requested quantity.
7. Every required capability is present.
8. Ranking is deterministic and returns an explanation; duplicate offer IDs are ignored.

A match is a candidate only. It does not contact a party, reserve inventory, accept terms, transfer title, create a contract or move money. Human/authorized-agent approval is required for external side effects.

## 5. Deal lifecycle (target contract)

`DISCOVERED → QUALIFIED → MATCHED → PROPOSED → ACCEPTED → FUNDED → IN_PROGRESS → EVIDENCE_SUBMITTED → VERIFIED → SETTLED`

Alternative terminal / branch states: `EXPIRED`, `DECLINED`, `CANCELLED`, `DISPUTED`, `REFUNDED`, `FAILED`. Transitions must be explicit, authorized, version-checked and idempotent. A disputed deal pauses automatic release. Refunds and reversals are new events, never destructive edits.

For milestone deals, each milestone has its own acceptance predicate, evidence policy, dispute window and settlement instruction. Multi-party splits are derived from the accepted contract terms and validated by the settlement authority.

## 6. Deal protection protocol

- The Router creates a typed payment intent only after valid contract acceptance.
- Funds are held only by an authorized escrow/custody/payment provider; the Router never claims to custody money.
- Release requires the contract's specified evidence and acceptance rule.
- Buyer and seller can submit evidence and contest a milestone.
- Independent arbitration or a pre-agreed dispute process resolves contested facts.
- Provider receipts are reconciled idempotently against canonical payment and accounting events.
- A smart contract may enforce deterministic digital conditions, but cannot independently establish off-chain delivery, quality, legal title or legal enforceability.

## 7. Economic graph

Node classes: participant, organization, demand, offer, asset, capability, project, contract, resource, location, evidence, payment intent and settlement receipt.

Edge classes: `seeks`, `offers`, `capable_of`, `located_at`, `supplies`, `depends_on`, `contracts_with`, `performs`, `evidenced_by`, `funded_by`, `settled_by`. Every edge has source authority, provenance, effective interval, visibility policy and optional confidence. A confidence score is not legal proof.

Multi-party route discovery can propose supply-chain or resource combinations, but cannot atomically commit them until a future multi-aggregate command protocol has explicit transaction semantics. Existing cross-register coordinator and SQLite repository boundaries remain authoritative; do not create a second EventStore or financial ledger.

## 8. AI agent permissions

Agents may discover, normalize, classify, rank, draft and negotiate within explicit constraints. They may not silently:
- accept a contract or amend binding terms;
- move, custody or release funds;
- transfer legal title or rights;
- mark delivery complete based solely on model output;
- expose personal or confidential data beyond purpose and consent;
- bypass sanctions, KYC/AML, consumer, tax, privacy or licensing controls.

Every agent action carries actor identity, delegated authority reference, scope, expiry, correlation ID, idempotency key and audit evidence. Human approval is required for legally binding or irreversible actions unless a separately approved delegation policy explicitly permits the exact action.

## 9. Security, privacy and abuse controls

Tenant isolation; least privilege; purpose limitation; data minimization; consent/legal-basis checks; encrypted secrets; rate limits; bot and Sybil resistance; verified seller status; duplicate/fraud detection; replay protection; immutable audit records; deletion/retention policy; explainable ranking; appeal and correction; sanctions and restricted-goods screening where applicable. Public marketplace search must not leak private buyer intent or seller confidential pricing.

Lead Radar ingestion must obey source terms, privacy law, opt-out and contact rules. A scraped signal is not automatically consent to marketing or proof of purchase intent.

## 10. Phased delivery

- **P0 — Contract and authority baseline:** this specification, schemas, canonical ownership, lifecycle and threat model.
- **P1 — Demand/offer registry adapters:** ingest consented Lead Radar signals and verified seller offers; dedupe, expiry, tenant scope and evidence.
- **P2 — Matching and marketplace:** deterministic matcher, search indexes, explainable ranking, buyer/seller workspaces.
- **P3 — Contract and deal protection:** proposal/acceptance, milestones, escrow-provider adapter, receipts, disputes and refund protocol.
- **P4 — Economic graph:** typed temporal graph and multi-party opportunity discovery with no duplicate financial truth.
- **P5 — Agentic commerce:** scoped AI agents, approval gates, audit and safe negotiation.
- **P6 — Cross-border network:** jurisdiction adapters, currency conversion with explicit quotes, localization, tax and regulatory controls.

## 11. Acceptance gates

A phase is complete only when schemas are validated, unit/property/adversarial tests pass, migrations are explicit, replay/idempotency and tenant-isolation tests pass, authority boundaries are reviewed, exact-HEAD CI is green, and operational/legal acceptance is documented. No production readiness is inferred from a passing unit test.

## 12. Current implementation boundary

The initial code in `prototype/economic_router.py` is a pure deterministic candidate matcher. It is not a registry, persistence layer, contract engine, payment integration or production marketplace. Its outputs must be persisted only through the canonical event/command boundary after that boundary is selected and validated for the relevant aggregate.
