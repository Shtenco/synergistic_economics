# SYNERGY LEAGUES — Phase 1 domain contract

**Status:** executable research prototype; not a production service  
**Version:** 0.1.0  
**Scope:** participant capability profiles, evidence-backed league membership, work-order matching, delivery review, and settlement hand-off.

## 1. Product model

The four leagues are capability and participation contexts, not paid access tiers:

| League | Primary capability |
|---|---|
| Starter | Entry-level tasks, guided work, and first verified deliveries |
| Expert | Professional services and specialist work |
| Business | Enterprise creation, supplier relationships, and project teams |
| Capital | Project evaluation and investment participation, subject to separate legal and suitability controls |

Membership is recorded with evidence references. A fee, token balance, referral count, or purchase is not evidence of competence and does not automatically promote a participant. A participant may hold multiple memberships where the relevant evidence and policy permit it.

## 2. Phase-1 workflow

1. A participant profile publishes only an explicit display name and evidence-backed skill codes; discoverability defaults to false.
2. A buyer creates a work order with required skills, budget, currency, creation time, and deadline.
3. A participant applies only when their profile contains verified evidence for every required skill.
4. The buyer assigns an applicant and records a payout split in integer basis points. The split must total exactly 10,000.
5. The assignee submits one or more immutable evidence references.
6. The buyer or another authorized reviewer accepts the delivery or requests a revision. The assignee cannot review their own work.
7. An accepted work order becomes settlement_ready; the domain returns a deterministic amount split for review by the authoritative settlement service.

## 3. Financial and authority boundaries

- budget is an agreed gross contract amount, not a participant balance, revenue recognition, or proof of payment.
- settlement_amounts() calculates a proposed split only. It does not debit, credit, mint, escrow, or settle funds.
- The authoritative accounting/settlement service must independently validate the contract, identities, evidence, authorization, currency, tax/legal treatment, available funds, and idempotency before posting.
- Reputation and skill evidence are not money, collateral, securities, or guaranteed future income.
- No return, income, job, promotion, or investment outcome is promised.
- Investment products, custody, pooled capital, brokerage, and management of third-party assets are outside this phase and require jurisdiction-specific legal review and authorization.

## 4. State machine

OPEN -> ASSIGNED -> SUBMITTED -> ACCEPTED

A reviewer may move SUBMITTED -> REVISION_REQUESTED; the assignee may then resubmit to SUBMITTED. Open or assigned work may be cancelled by an authorized party in a future persisted service. Every transition in this prototype requires the caller's expected aggregate version, preventing stale writes at the domain boundary.

Terminal states: ACCEPTED, CANCELLED.

## 5. Implemented in this phase

- Dependency-free Python domain types in prototype/synergy_leagues.py.
- Four canonical league identifiers.
- Evidence-backed skill and membership contracts.
- Work-order application and assignment.
- Verified-skill eligibility checks.
- Version-checked state transitions.
- Evidence-required delivery and buyer/reviewer acceptance.
- Exact 10,000-basis-point split validation and deterministic cent allocation.
- Unit tests for happy path, invalid evidence, stale versions, duplicate applications, self-review, unbalanced splits, and financial boundaries.

## 5A. Phase-2 persistence increment

The branch now also contains a file-backed SQLite work-order store in `prototype/league_store.py`:

- Composite `(security_domain, order_id)` keys prevent cross-domain reads.
- SQLite WAL mode and FULL synchronous durability are enabled.
- Commands use idempotency keys; identical replay is a no-op and changed-content reuse is a conflict.
- Work-order writes require an expected aggregate version and update the snapshot plus event atomically.
- Event history is append-only at the database layer.
- Canonical payload hashes, event-sequence checks, SQLite integrity checks, and foreign-key checks are exposed.
- Restart, tenant-isolation, stale-write, replay, and append-only behavior have dedicated tests.

The store's `security_domain` argument is a partition boundary, not authentication. A trusted service must derive it from a verified principal and enforce authorization before calling the store. Production backup/restore, power-loss, multi-process stress, KMS-backed evidence, and multi-host coordination remain release gates.

## 6. Explicitly not implemented

- Authentication, identity proofing, authorization/RBAC, and consent registry.
- Authenticated API, transactional outbox, production audit service, or distributed transaction. The phase-2 SQLite work-order snapshot/event store is implemented, but is not yet a complete production persistence service.
- Real escrow, payment execution, accounting journal postings, refunds, tax, or chargebacks.
- Dispute resolution, arbitration, sanctions, fraud controls, or service-level enforcement.
- Marketplace search/ranking, recommendation, messaging, and notifications.
- Automated promotion thresholds or AI-controlled economic decisions.
- Capital-market issuance, investment suitability, custody, or investor onboarding.

These are separate implementation gates, not implied capabilities.

## 7. Next phases

### Phase 2 — persistence and trust
Introduce a durable append-only work-order store, authenticated actor context, explicit permission checks, immutable evidence manifests, idempotent commands, audit history, and a transactional outbox. Add concurrency, restart, replay, and crash tests.

### Phase 3 — service marketplace
Add catalog/search, quote and contract acceptance, buyer/supplier organizations, team roles, cancellation/refund policy, dispute workflow, and service quality metrics. Keep ranking explainable and prevent paid placement from masquerading as quality.

### Phase 4 — business accelerator
Add venture/project records, founder and contributor agreements, milestones, IP provenance, business health metrics, and project governance. Separate ownership claims from contribution scores.

### Phase 5 — capital network
Only after legal architecture: permissioned project disclosure, investor eligibility/suitability, risk disclosures, authorization and regulated intermediaries. Do not represent an investment listing as a public offer by default.

### Phase 6 — economic/metaverse federation
Publish versioned, privacy-minimized events and read-only projections. The metaverse may display workspaces and public activity but cannot authoritatively change work-order, ownership, revenue, or settlement state.

## 8. Validation

Run from the repository root:

```bash
python -m unittest prototype.test_synergy_leagues -v
python -m unittest discover -s prototype -p 'test_*.py' -v
```

A passing unit test establishes only the tested domain invariants; it is not a security, legal, accounting, or production-readiness certification.
