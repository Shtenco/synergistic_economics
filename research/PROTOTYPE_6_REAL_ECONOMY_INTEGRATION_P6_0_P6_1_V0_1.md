# Prototype 6 — Real Economy Integration: P6.0–P6.1
## Read-only claim/evidence adapters and lot-level physical inventory

**Document ID:** SYNERGY-RE-P6-001  
**Version:** 0.1 — 11 November 2026  
**Status:** Executable research reference and test specification; not production infrastructure  
**Branch:** `research/sec-sper-integration-audit-2026-11-11`  
**Dependencies:** Volume IV canonical entities, EventStore and DoubleEntryLedger; Volume III rights/contribution separation; SCCE Stage A/B/C2 physical boundaries.

---

## 1. Scope and non-goals

This increment implements two additive foundations:

- **P6.0:** a read-only typed projection of the canonical Claim and a proposition-specific SPER evidence evaluator.
- **P6.1:** a lot-level inventory reference model with owner/custodian separation, explicit authorization, versioned reservations, expiry, partial movement and quantity reconciliation.

It does not implement a new claim database, a second generic event store, a second financial ledger, a token, legal title transfer, external payment, EPCIS/VC network adapter, durable storage or a live multi-tenant service.

The existing `prototype/synergy_kernel.py`, Stage-A/B/C2 models and their outputs are not modified by this increment. The new module is isolated and uses only Python's standard library.

## 2. Canonical boundaries

| Concern | Authority |
|---|---|
| Canonical claim identity and legal basis | Existing Volume IV Claim / Contract / obligation |
| SEC | Read-only typed projection of a canonical Claim |
| Evidence bytes and provenance | Evidence storage/reference controlled by the integration host |
| SPER | Versioned proposition-specific verification decision |
| Physical stock | LotInventory for this P6.1 prototype boundary |
| Legal title | Existing Asset / ownership / rights model; not changed by physical movement |
| Financial consequences | Existing DoubleEntryLedger; this module emits no journal entries |
| Event history | Existing Volume IV EventStore; this module returns event descriptions, not a second event store |
| Durable transaction boundary | Future database adapter / transactional outbox |

The new `LotInventory` is the single in-memory stock authority **inside this isolated prototype**. It is not yet synchronized with Stage-B aggregate inventories. A future adapter must define one authoritative stock boundary and must not sum both representations.

## 3. P6.0 — SEC read-only projection

`ClaimProfile.from_canonical_claim(mapping)` validates and projects:

- claim, claimant and obligor identifiers;
- contract and obligation identifiers;
- claim type and status;
- optional quantity/unit;
- optional monetary amount/currency;
- explicit transferability.

Transferability defaults to false. Monetary amounts require a currency. The projection does not write a Claim, create a new right, validate the underlying contract or decide legal enforceability. The caller must load the canonical Claim and pass its authoritative record.

## 4. P6.0 — SPER proposition-specific verification

`evaluate_evidence` checks one evidence record against one versioned policy and an explicitly supplied expected subject.

The evaluator checks:
1. exact subject binding;
2. proposition type;
3. accepted evidence type;
4. trusted issuer allowlist;
5. timezone-aware observation and validity times;
6. freshness and expiry;
7. SHA-256 digest syntax and exact payload bytes;
8. issuer authentication through a supplied verifier callback when required.

Possible decisions are `ACCEPTED`, `REJECTED` and `INDETERMINATE`.

**Important boundary:** an accepted decision means the evidence passed the declared technical/policy checks. It does not prove a universal truth, legal title, absence of undisclosed liens, quality of an unsampled batch or payment finality. The verifier callback must implement actual signature, credential-status, issuer-key and revocation checks. If that callback is absent, required issuer authentication is indeterminate, never silently accepted.

No universal E1–E7 numeric evidence score is used. The policy is proposition-specific.

## 5. P6.1 — Lot state

A lot records:

- stable lot/product identifiers;
- owner and custodian separately;
- location;
- quantity and unit;
- quality release/quarantine state;
- reserved quantity;
- aggregate version;
- explicitly authorized actors;
- optional source-lot genealogy.

Available quantity is:

`available = on_hand - reserved`

when quality status is `RELEASED`; otherwise available quantity is zero.

A custodian is not automatically authorized to reserve, commit, release or consume stock. The owner or an explicitly authorized actor must perform these operations. This is a prototype authorization check, not a replacement for production identity, delegated mandate or contract verification.

## 6. Reservation lifecycle

`RESERVED → COMMITTED → CONSUMED`

Alternative terminal transitions:

- `RESERVED → RELEASED`;
- `RESERVED → EXPIRED`;
- `COMMITTED → RELEASED` for unconsumed remainder.

A reservation:
- uses an expected lot version to reject stale commands;
- requires a unique reservation ID and idempotency key;
- expires at a timezone-aware instant;
- reduces available quantity but does not change title or on-hand stock;
- can be committed only with an upstream-authorized contract/mandate reference;
- can be consumed only up to its remaining committed quantity.

The `authorization_ref` is recorded, but this in-memory module does not authenticate or adjudicate that contract. The integration host must validate authority before invoking commitment.

## 7. Partial physical movement and genealogy

Partial shipment must not change the location or custodian of the unshipped remainder.

When quantity q is consumed from a committed reservation:
- source lot on-hand quantity decreases by q;
- source lot reserved quantity decreases by q;
- a new child/moved lot is created with quantity q;
- child lot records the source lot ID;
- child lot inherits the current owner;
- child lot receives the destination location and new custodian;
- reservation remainder decreases by q.

Thus:

`source_closing + moved_quantity = source_opening`

and, at the combined genealogy boundary:

`source_remaining + sum(child_lot_quantities) = original_lot_quantity`

Physical movement does not transfer title. A title transfer must be separately authorized and recorded through the canonical rights/asset model.

## 8. Idempotency and concurrency boundary

The reference model:
- stores command fingerprints and receipts in process memory;
- returns the prior receipt for an identical retry;
- rejects reuse of an idempotency key for a different command;
- uses a process-local reentrant lock;
- uses aggregate versions to reject stale commands.

This protects deterministic single-process tests. It does **not** provide durable idempotency, cross-process concurrency, database isolation, crash recovery or transactional atomicity with the existing EventStore.

Methods return event descriptions. The integration adapter must persist the domain state, reservation changes, event append and outbox message within one durable database transaction. External provider calls require an outbox/inbox protocol. Do not claim production atomicity from this in-memory model.

## 9. Event and accounting boundary

Events returned by the module are descriptions for the host's canonical EventStore. They are not appended to a new event store here.

No journal entry is created by:
- lot registration;
- reservation;
- reservation commitment;
- physical movement;
- evidence receipt or verification;
- ClaimProfile projection.

Financial recognition must follow the contract, accounting policy and actual settlement evidence. Physical events alone do not create revenue or cash.

## 10. Test coverage

`test_real_economy_protocol.py` covers:

- positive lot registration and stock availability;
- custodian is not owner authority;
- bounded reservations and version checks;
- idempotent retry and conflicting key reuse;
- stale lot version rejection;
- partial shipment splitting into a child lot;
- preservation of source location and title;
- exact reservation release;
- expiry release;
- quarantine restriction;
- read-only Claim projection and non-transferable default;
- monetary claim currency requirement;
- subject-bound SPER acceptance;
- digest mismatch rejection despite successful issuer callback;
- missing issuer verifier producing indeterminate status.

Run from repository root:

```bash
python -m unittest discover -s prototype -p 'test_real_economy_protocol.py' -v
python -m unittest discover -s prototype -p 'test_*.py' -v
```

A successful new-module test run is not proof that the entire repository suite passed. Existing Stage-A/B/C2 regression results must be separately observed in CI or a local run.

## 11. Known limitations

1. In-memory state only; no durable repository.
2. Process-local lock only; no cross-process serializability.
3. No transactional outbox implementation.
4. No cryptographic signature/VC verifier implementation.
5. No EPCIS JSON-LD serializer or remote capture/query adapter.
6. No title transfer, lien registry, secured-credit priority or legal adjudication.
7. No batch sampling model, quality laboratory workflow or chain-of-custody adjudication.
8. No unit conversion registry; quantities must use a canonical unit per product/lot.
9. No return, spoilage, split/merge transformation, recall or reverse-logistics workflow yet.
10. No direct synchronization with Stage-B inventories.
11. No payment, invoice recognition or ledger posting.
12. No user identity, role-based access control or key management.

## 12. Next increments

- **P6.2:** canonical event adapter and EPCIS mapping with round-trip tests.
- **P6.3:** contract/obligation authorization adapter and Claim lifecycle transition validation.
- **P6.4:** credential verifier interface, revocation/status checks, evidence policy registry and dispute workflow.
- **P6.5:** transactional persistence, outbox/inbox, concurrent reservation tests and crash-injection tests.
- **P6.6:** settlement simulation adapter, keeping payment instruction distinct from final settlement.
- **P6.7:** labor and contribution events linked to contracts, with SCI kept analytically separate from entitlement.
- **P6.8:** controlled SCCE integration and paired baseline regression.

## 13. Acceptance gate

P6.0–P6.1 are ready for review only after the targeted tests pass and the repository's existing suite remains unchanged. They are not ready for operational deployment until durable persistence, authorization, external evidence verification, legal rights integration, physical audit procedures and financial settlement controls exist.

**Decision:** keep the module additive and isolated. SEC remains a view over Claim; SPER remains a policy evaluator; lot inventory is the sole stock authority only within this prototype boundary; EventStore and DoubleEntryLedger remain canonical for events and money.
