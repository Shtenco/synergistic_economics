# SEC / SPER Integration Audit and Contract
## Additive architecture for SYNERGY Real Economy Protocol

**Document ID:** SYNERGY-RE-SEC-SPER-001  
**Version:** 0.1 — 11 November 2026  
**Status:** Architecture audit and proposed integration contract; not an implementation or legal opinion  
**Branch:** `research/sec-sper-integration-audit-2026-11-11`  
**Scope:** Volume IV accounting/event kernel; Volume III contribution/ownership/distribution; Volume XI monetary, credit and settlement architecture; SCCE Stage A/B/C2; existing `prototype/synergy_kernel.py`.

---

## 1. Executive decision

The Real Economy Protocol must extend the existing SCCE and Volume IV architecture. It must not introduce a second accounting ledger, a second generic event store, or a second independent ownership/claim truth.

The proposed SEC (SYNERGY Economic Claim) is **not a new kind of money and not necessarily a token**. It is a typed profile/API over the existing Volume IV `Claim` entity and the contract/obligation records that create it. A claim may be represented by a token only if the underlying right is legally transferable, the relevant platform and instrument are permitted, and the token representation does not create duplicate rights.

SPER (Proof of Economic Reality) is **not a claim registry**. It is an evidence-verification policy and provenance layer attached to existing events, claims, assets, lots, contracts and deliveries.

The canonical separation is:

1. Physical stock and capacity are owned by the physical inventory/capacity subledger.
2. Legal title, control, encumbrances and contractual rights are represented by existing Asset, Contract and Claim concepts.
3. Evidence is attached to immutable events and typed subjects; verification decisions are separately recorded.
4. Financial consequences are posted through the existing double-entry ledger.
5. Cellular discovery and matching remain bounded by Stage-A/B graph, relay, consent, capacity and reservation rules.

This is the minimum design that avoids parallel truth.

## 2. Repository audit: confirmed baseline

The inspected repository files establish the following:

- Volume IV already defines canonical entities including Person, Household, Enterprise, Project, Asset, Cell, Federation, Market, Fund, Contract, Account and Claim.
- Volume IV already requires event-sourced state changes, append-only corrections, idempotency, deterministic replay, event ordering, double-entry accounting, entity-level and consolidated accounting, liquidity/solvency separation, credit controls and loss waterfalls.
- Volume III explicitly distinguishes contribution, causal effect, contractual claim, ownership, governance right, risk-bearing, income, wealth, surplus and human worth.
- SCCE Stage A/B already constrains matching by local observations, authorized edges, consent, relay permissions, stock/capacity limits, reservations and deterministic conflict resolution.
- Stage-C2 explicitly distinguishes needs, effective demand, requests/claims and actual fulfilment; it requires voluntary time, separate income/ownership/credit channels, and exact physical reconciliation.
- The minimal kernel implements balanced journal entries, duplicate entry/event/idempotency-key checks, an append-only ordered event list, a SHA-256 payload digest, bounded production/shipment, pool allocation and a simple inter-cell cash transfer.

### 2.1 Important limitations of the minimal kernel

These are scope gaps, not reasons to discard the prototype:

1. `EventStore` hashes `event_type + canonicalized payload`, but does not include a previous-event hash, event timestamp, schema version, actor, event ID or idempotency key in the digest. It is a content digest, not a hash-linked ledger.
2. `Event.payload` is a mutable dictionary even though the dataclass is frozen; nested payload objects are not deeply immutable.
3. `DoubleEntryLedger` checks debit/credit equality and known account names, but account names are untyped strings. There is no legal-entity dimension, account class, normal-balance rule, period lock or account-specific spending policy.
4. `JournalEntry` does not itself carry a contract, claim, event, source, legal entity, effective date, posting date, reversal reference or transaction-batch identifier.
5. `transfer_cash` performs useful prechecks, but the in-memory ledger post and event append are not a durable atomic database transaction. There is no concurrency lock or transactional outbox.
6. `Firm.produce` consumes material and energy and increases aggregate inventory, but labour is not represented as a separately evidenced time/contract event.
7. `Firm.ship` reduces an aggregate inventory number. It does not identify a lot, location, owner, custodian, reservation, shipment, carrier, recipient, proof of delivery or quality acceptance.
8. The current kernel is single-process and in-memory; it is a research prototype, not a production accounting or settlement service.

No test execution is claimed in this document. The findings above are based on source inspection of the current default-branch files.

## 3. Canonical integration map

| New capability | Canonical owner in existing architecture | Integration rule |
|---|---|---|
| Economic object identity | Existing Asset / Product / Project entities; new typed object profile only where necessary | Do not create duplicate entity identity |
| Physical lot and stock | Physical inventory subledger / Stage-B stock-flow state | Quantity and location have one authoritative stock owner |
| Capacity availability | Asset capacity and Stage-B capacity state | Reservations reduce available capacity, not total capacity |
| Legal title / control | Asset ownership and rights records | Distinguish owner, beneficial owner, custodian, operator and authorized disposer |
| Contract | Existing Contract entity | Contract creates obligations; it is not evidence of performance |
| Claim / SEC | Existing Volume IV Claim entity | SEC is a typed claim profile, not a second claim ledger |
| Work and contribution | Existing work/contribution events and Volume III attribution model | Contribution evidence does not automatically create ownership or payment entitlement |
| Evidence / SPER | Event evidence references and verification-decision events | Evidence verifies a proposition under a policy; it does not independently create a right |
| Invoice / payable / receivable | Existing financial event catalogue and accounts | Recognition follows contract and accounting policy |
| Payment instruction | Settlement workflow | Instruction is not cash movement or final settlement |
| Settlement | Existing payment/settlement event and ledger posting | Post only on authoritative settlement evidence |
| Distribution | Volume III distributable-pool and allocation rules | No distribution from gross sales, token issuance or unverified surplus |
| Cellular matching | SCCE Stage A/B | No global data bypass, no implicit consent, no unreserved double allocation |

## 4. SEC: typed profile over Claim

### 4.1 Definition

A SYNERGY Economic Claim (SEC) is a uniquely identified, evidence-linked and contractually or legally grounded claim by a claimant against a debtor or responsible obligor for a defined performance, payment, access right or other obligation.

An SEC record must reference the canonical Volume IV Claim and must not create a second independently balanceable right.

### 4.2 Minimum fields

- `claim_id`: stable canonical claim identifier.
- `claim_type`: `PAYMENT`, `DELIVERY`, `SERVICE`, `CAPACITY_ACCESS`, `REFUND`, `LICENSE`, or another versioned type.
- `claimant_id` and `obligor_id`: legal or institutional subjects.
- `contract_id` and `obligation_id`: source of the claim.
- `subject_refs`: asset, lot, project, service or capacity references.
- `quantity` and `unit`, where applicable; monetary amount and currency are separate fields.
- `terms_version`: the exact contract/specification version.
- `effective_at`, `due_at`, `expiry_at`.
- `transferability`: explicit status and legal basis; default false.
- `priority`, `security_refs`, `guarantee_refs`, if applicable.
- `evidence_refs`: evidence records supporting relevant propositions.
- `status`: lifecycle state.
- `dispute_ref`, `supersedes_claim_id`, `settlement_refs`, where applicable.

Do not use a single `value` field to represent quantity, price, face amount, fair value and expected recovery. They are different dimensions.

### 4.3 Claim lifecycle is not a single evidence lifecycle

Use separate state dimensions:

**Claim state:** `DRAFT → SUBMITTED → VALIDATED → AUTHORIZED → ACTIVE`, followed by `PARTIALLY_PERFORMED`, `SATISFIED`, `DISPUTED`, `CANCELLED`, `EXPIRED` or `VOID`, subject to explicit transition rules.

**Evidence state:** `RECEIVED → INTEGRITY_CHECKED → ISSUER_AUTHENTICATED → POLICY_EVALUATED → ACCEPTED/REJECTED`, with separate `REVOKED` or `SUPERSEDED` states.

**Fulfilment state:** `NOT_DUE → DUE → IN_PROGRESS → PARTIALLY_FULFILLED → FULFILLED`, or `FAILED` / `DISPUTED`.

A claim may be valid and active before performance begins. A delivery credential may be authentic while its factual assertion remains disputed. A payment may be settled while a separate quality claim remains open. Do not collapse these dimensions into one linear state machine.

### 4.4 Tokenization rule

Default representation: database/ledger claim record plus signed contract and evidence references. Token representation is an optional distribution/transfer interface, not the canonical source of legal truth.

A token must not be issued where:
- the underlying claim does not exist or is not yet legally established;
- transfer is prohibited or requires consent not obtained;
- the token would obscure the debtor, currency, maturity, priority or recourse;
- the same underlying claim is already represented by an active transferable instrument;
- the applicable jurisdiction/platform regime has not been satisfied.

## 5. SPER: evidence and verification contract

SPER evaluates evidence for a specific proposition. It must never output an unqualified “real” or “guaranteed” flag.

### 5.1 Evidence object

Minimum fields:

- `evidence_id`, `subject_ref`, `proposition_type`;
- `issuer_id`, `holder_id`, `verifier_id` (where roles apply);
- `evidence_type`, `media_type`, `content_digest`;
- `issued_at`, `observed_at`, `recorded_at`, `valid_until`;
- `source_uri` or protected storage reference;
- `signature_or_credential_ref`;
- `verification_policy_id` and `policy_version`;
- `verification_result`, `limitations`, `reviewer`;
- `revocation_or_supersession_ref`.

Store large documents, images, personal data and commercial secrets off-chain in access-controlled storage. Store only minimal commitments, digests, signatures or references in a public ledger, where appropriate.

### 5.2 Verification is proposition-specific

Examples:

- A warehouse operator's signed statement may support “lot L was recorded at warehouse W at time T”; it does not alone prove legal title or absence of liens.
- A calibrated scale record may support a measured mass; it does not prove ownership or grade.
- A laboratory certificate may support a quality proposition for a sampled batch; sampling scope and chain of custody remain relevant.
- GPS telemetry may support a route/location proposition; it does not prove delivery acceptance.
- A buyer's signature may support receipt/acceptance under a defined process; it does not necessarily prove payment.
- A payment-provider receipt may support settlement status; it does not prove physical delivery.

Verification policies must declare the proposition, accepted issuer classes, required evidence combination, freshness window, independence requirements, conflict handling and appeal route.

### 5.3 No universal evidence score

Do not sum E1–E7 evidence classes into a single numeric truth score. Evidence is not universally ordered: GPS is useful for location but weak for quality; a signed invoice is useful for a billing event but weak for physical stock. Use proposition-specific predicates and risk rules.

### 5.4 External interoperability

Adopt standards through adapters rather than redefining them:

- GS1 EPCIS 2.0 / CBV for supply-chain visibility events: what object was involved, what business step occurred, when, where and in what business context.
- W3C Verifiable Credentials Data Model 2.0 for issuer/holder/verifier credentials and selective disclosure where appropriate.
- UNECE UN Transparency Protocol Digital Traceability Events may be evaluated as an EPCIS event packaged as a verifiable credential.

A cryptographically valid credential proves integrity/authorship according to its mechanism; it does **not** prove that every factual claim inside it is true. The verifier must evaluate issuer, subject, evidence, freshness and its own business policy.

## 6. Physical stock, lots and capacity

### 6.1 Stock is authoritative and lot-based

The inventory subledger must track, at minimum:

- `lot_id`, `product_id`, owner, custodian, location;
- quantity and canonical unit;
- quality/specification and inspection scope;
- received, produced, transformed and expiry timestamps;
- reserved, pledged, quarantined and freely available quantities;
- source lot(s) and transformation genealogy;
- evidence and event references.

For each lot and unit:

`closing = opening + receipts + production_in - consumption - shipment - spoilage - other_loss`

Transfers between locations/cells must be represented as paired movement events and must cancel on consolidated physical stock. Transformation consumes input lots and creates output lots with explicit yield, scrap and loss.

### 6.2 Availability formula

`available = on_hand - reserved - pledged_unavailable - quarantined - other_restricted`

The exact treatment of pledged stock depends on the security agreement and control arrangements. Do not subtract an encumbrance mechanically if the owner retains permitted use; instead represent the specific restriction and calculate availability under the applicable policy.

### 6.3 Reservation protocol

A reservation is a temporary, expiring hold, not a transfer of title.

1. Read versioned stock/capacity snapshot.
2. Check availability and authority.
3. Create reservation with quantity, purpose, counterparty, expiry and idempotency key.
4. Atomically reduce available quantity.
5. On contract authorization, convert reservation to committed allocation.
6. On expiry/cancellation, release exactly once.
7. On shipment/use, consume the committed allocation and record movement.
8. Reject stale or competing reservations.

The same protocol applies to equipment time slots and service capacity, with units and time windows.

## 7. Event, accounting and settlement integration

### 7.1 One economic transaction envelope

Each operation should have a stable `transaction_id` linking:

- command/request;
- contract and obligation;
- physical stock/capacity reservations;
- domain events;
- evidence and verification decisions;
- journal entries;
- payment instruction;
- settlement receipt;
- dispute/correction events.

This envelope is a correlation boundary, not a new ledger.

### 7.2 Required event envelope

- event ID and event type;
- transaction ID and idempotency key;
- actor and authorization context;
- subject/object references;
- event time and record time;
- schema and policy versions;
- typed payload with units/currency;
- evidence references;
- causation ID and correlation ID;
- prior-event reference or aggregate version;
- event status and supersession/reversal references.

### 7.3 Atomicity

Within one authoritative database transaction, persist the domain state transition, reservation changes, journal postings and outbox message together. External payment providers, warehouse systems and identity registries cannot join the same local database transaction; use an outbox/inbox pattern with idempotent external commands and receipts.

Never report a remote payment as settled merely because the outbox message was sent. Only the designated settlement provider's authenticated final status can trigger settlement accounting.

### 7.4 Hash chain

If hash chaining is added, compute the digest over a canonical immutable envelope including at least schema version, event ID, sequence/aggregate version, event type, actor, event/record times, payload digest, evidence references and previous hash. Define canonical serialization, hash algorithm version, key/signature rotation, checkpoints and recovery.

A hash chain detects alteration of the committed sequence under its trust assumptions. It does not prove the truth of off-chain facts, prevent an authorized issuer from lying, or make a centralized event store decentralized.

### 7.5 Journal semantics

Keep physical movements and financial recognition separate.

Examples:
- Warehouse receipt: inventory/custody event; no automatic revenue.
- Shipment under a sale: stock movement plus contract performance event; revenue/receivable recognition follows accounting policy and contract terms.
- Invoice issued: billing event; not payment.
- Payment instruction: instruction event; not settlement.
- Final settlement: cash/settlement asset and receivable/payable postings.
- Loan drawdown: cash and debt increase; not operating income.
- Labour accepted: performance evidence; payable recognition follows contract and applicable accounting rules.
- Contribution score: analytical record; not automatically a payable or ownership change.

## 8. SCCE integration: preserve local autonomy

The Real Economy Protocol must not bypass Stage-A/B constraints.

- Discovery uses only authorized neighbour edges and relayed messages.
- Forecasts are signals, not orders or contracts.
- Offers are not commitments until accepted under the parties' authority rules.
- Reservations are local, versioned and idempotent.
- Cross-cell transactions require all materially bound counterparties' consent.
- Each cell sees only authorized household and commercial information.
- Federation can coordinate shared infrastructure and systemic risks only within its mandate.
- AI can rank and propose; it cannot mint claims, change ownership, create debt, guarantee another party or settle funds without explicit authority.
- Real-economy integration must preserve Stage-C2's exact physical reconciliation and privacy boundaries.

## 9. Accounting and anti-double-counting rules

1. A physical lot has one authoritative quantity balance at each stock boundary.
2. Ownership and custody are distinct; custody change does not necessarily transfer title.
3. A claim references its legal basis and cannot silently duplicate the same exclusive performance obligation.
4. Multiple rights over one asset may coexist if they are legally compatible; do not apply a simplistic “all claims sum below stock” rule to non-exclusive rights.
5. For exclusive delivery rights over a lot, aggregate active reserved/committed quantities cannot exceed the deliverable quantity after applicable restrictions.
6. Internal inter-cell transfers are eliminated on consolidated accounts.
7. Intermediate goods are not counted again as final output when incorporated into downstream products.
8. A token balance, forecast, order, invoice or credit limit is not physical stock, settled cash or recognized income.
9. Pledged collateral is not simultaneously reported as unencumbered liquidity.
10. A correction is a new compensating/superseding event; historical events are not silently overwritten.

## 10. Test plan before implementation

### 10.1 Contract/schema tests
- required fields, stable IDs, schema versioning;
- exact unit and currency handling;
- reject NaN, infinity, negative stock and ambiguous unit conversion;
- prohibit unknown claim types and illegal state transitions;
- validate authority and transferability separately.

### 10.2 Physical and reservation tests
- concurrent reservations against the same lot;
- partial shipment and partial release;
- stale snapshot rejection;
- expiry and duplicate release;
- lot transformation genealogy and mass/quantity balance;
- quarantine, spoilage, returns and quality rejection;
- capacity reservation overlap for time windows.

### 10.3 Claim and evidence tests
- no claim without contract/obligation or other accepted legal basis;
- evidence authenticity does not imply factual acceptance;
- revoked/expired credential rejection;
- conflicting evidence enters review/dispute;
- partial performance and partial settlement;
- one exclusive obligation cannot be settled twice;
- claim transfer preserves debtor, amount, priority and history;
- appeal and correction preserve the audit trail.

### 10.4 Accounting and integration tests
- balanced entries per entity and currency;
- transaction-level atomicity under injected failure;
- outbox retry without duplicate external payment;
- duplicate provider webhook idempotency;
- loan principal never enters operating revenue;
- invoice never enters cash before settlement;
- entity-level and consolidated ledgers reconcile;
- inter-cell transfer eliminates on consolidation;
- payment reversal/chargeback creates explicit compensating entries.

### 10.5 SCCE regression tests
- same Stage-A/B baseline results with Real Economy modules disabled;
- no global-state leakage into local cell transitions;
- no relay without consent;
- no cross-cell reservation without authorization;
- Stage-C2 household quantities reconcile exactly;
- privacy suppression and access controls remain intact;
- deterministic replay under fixed seeds and event ordering.

## 11. Additive implementation sequence

**R0 — Contract freeze:** approve entity boundaries, state dimensions, event envelope and accounting ownership. No code changes to legacy prototypes.

**R1 — Read-only adapters:** map existing entities/events into SEC/SPER views; prove there is no duplicate source of truth.

**R2 — Lot inventory extension:** add lot-level records and reservation protocol behind a feature flag; retain aggregate Stage-B interface as an adapter.

**R3 — Evidence policy engine:** attach evidence references and proposition-specific verification decisions; no automated legal conclusions.

**R4 — Contract/claim workflow:** bind existing Contract and Claim entities to obligations, fulfilment and dispute state.

**R5 — Settlement adapter:** simulate payment instructions and provider receipts; do not custody or move real client money in the research prototype.

**R6 — Labor and contribution bridge:** connect voluntary work offers, contracts, evidence, acceptance and payable recognition while keeping SCI analytically separate.

**R7 — Controlled experiment:** compare baseline and integrated branches with paired seeds; run all legacy tests and new invariant tests.

Each stage must be independently reversible. No existing prototype, result file, test, event history or specification is deleted or rewritten.

## 12. Acceptance criteria

The integration is not ready to merge until:

- every SEC references the canonical Claim and source obligation;
- SPER evidence decisions are separate from legal authority and claim status;
- lot and capacity balances reconcile exactly;
- reservations are concurrency-safe and idempotent;
- journal postings and local domain transitions have a durable atomic boundary;
- external settlement uses an outbox/inbox protocol;
- no double counting occurs across physical, legal, financial and consolidated views;
- Stage-A/B/C2 regressions pass unchanged;
- all outputs clearly distinguish conceptual, analytical, synthetic simulation, calibrated simulation, controlled pilot and operationally audited evidence.

## 13. External standards to evaluate through adapters

- ISO/IEC 19987:2024 defines EPCIS 2.0 as a standard for sharing visibility event data across applications and enterprises.
- W3C Verifiable Credentials Data Model 2.0 defines issuer/holder/verifier roles, credential evidence and selective disclosure. Its specification explicitly warns that cryptographic verification of a credential does not itself prove the truth of the claims.
- UNECE UN Transparency Protocol Digital Traceability Events packages EPCIS events as verifiable credentials and may provide a useful interoperability profile.

These are interoperability references, not a claim that SYNERGY is already conformant.

## 14. Open questions requiring explicit decisions

1. Which existing Volume IV Claim schema is canonical in code, and where is it implemented? The inspected minimal kernel does not yet contain a Claim class.
2. Is the current production event store intended only for deterministic simulation, or will a separate durable service be designed for live operation?
3. Which physical identifiers and units are canonical for the first Kazakhstan pilot?
4. Which evidence issuers are acceptable for each product/quality/location proposition?
5. Which legal entities and counterparties own each account and contract in the first pilot?
6. Which regulated partner performs payment, escrow, custody or any token issuance function?
7. What exact rights are intended to be transferable, and under what law and platform regime?

Until these questions are resolved, SEC/SPER remains a research architecture and must not be represented as a production-ready financial or legal instrument.

---

**Decision summary:** SEC is a typed view over the existing Claim/Contract model; SPER is a proposition-specific evidence and verification layer; physical stock remains in one authoritative inventory model; financial effects remain in the existing double-entry ledger; SCCE locality and consent remain binding. Implement through adapters and additive feature flags, not replacement.


## 15. Prototype 6 implementation status — 11 November 2026

An additive first implementation now exists in:

- `prototype/real_economy_protocol.py` — P6.0 read-only Claim projection, SPER proposition-specific evidence decision, and P6.1 in-memory lot/reservation reference model.
- `prototype/test_real_economy_protocol.py` — targeted invariant tests.
- `research/PROTOTYPE_6_REAL_ECONOMY_INTEGRATION_P6_0_P6_1_V0_1.md` — implementation contract and limitations.
- `prototype/README.md` — prototype index and run commands.

The implementation deliberately does not persist a second event store or create a second financial ledger. It returns event descriptions for the host integration adapter. The lot model is currently an isolated in-memory stock authority and is not synchronized with Stage-B inventories. Claim projection is read-only. Evidence authentication is delegated to a verifier callback; no W3C credential signature/status implementation is claimed.

A draft pull request is open for review: [PR #5 — Prototype 6 P6.0–P6.1](https://github.com/Shtenco/synergistic_economics/pull/5).

**Validation status at this document revision:** GitHub Actions runs have been observed in the queued state. No passing test result is claimed until the focused and full prototype workflows complete successfully. The local container has no network route to clone the repository, so a local run has not been performed in this session.

The next implementation gate is durable persistence and a transactional adapter that commits lot state, canonical EventStore events and outbox records together. Do not connect the in-memory reference model directly to live payment, custody or production inventory.


### 15.1. Normative references and maturity caveat

- GS1 EPCIS 2.0.1: https://ref.gs1.org/standards/epcis/2.0.1/ — event data model and capture/query interfaces for supply-chain visibility.
- W3C Verifiable Credentials Data Model 2.0: https://www.w3.org/TR/vc-data-model-2.0/ — W3C Recommendation published 15 May 2025. Credential verification does not itself establish the truth of the encoded claims; the verifier must apply its own policy to issuer, proof, subject and claims.
- UNECE UN Transparency Protocol Digital Traceability Events: https://untp.unece.org/docs/specification/DigitalTraceabilityEvents/ — currently marked Work in Progress and suitable for pre-production pilot implementations. It wraps GS1 EPCIS events in a W3C Verifiable Credential envelope; it must not be treated as a finalized UNTP 1.0 conformance target.

The implementation should pin exact specification versions and schemas in each adapter. Do not silently follow a moving “latest” specification in production.
