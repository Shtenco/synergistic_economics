# SYNERGY ECONOMICS — repository consolidation record

**Date:** 13 November 2026  
**Integration branch:** `integration/economic-core-consolidation-2026-11-13`  
**Target:** `main`  
**Purpose:** consolidate the existing Prototype 2, UEB, A2.4/SFC-SCCE and Prototype 6 work without creating competing ledgers or overstating completion.

## Consolidation provenance

The integration commit has three source parents: the A2.4/SFC-SCCE branch, the P6 real-economy branch, and the UEB branch. This preserves Git ancestry while placing their source trees under one integration branch.

| Source line | Existing contribution | Consolidation treatment |
|---|---|---|
| `main` | Core repository and Prototype 0–5 work | Base for the target PR |
| `audit/sfc-scce-a2-4-continuation-20261111` | SFC/SCCE, GOLD-1/2A, financial event store, projections, physical/product/capital stores, governance, coordinator, crash/DR and external-checkpoint fixtures | Retained as integration base |
| `research/sec-sper-integration-audit-2026-11-11` | P6 canonical bridge/replay, SQLite event repository, durable lot-inventory adapter, contracts and tests | Added as a merge parent and copied into the consolidated tree |
| `unified-economic-balance` | UEB double-entry, physical stock-flow and claim primitives, specification and tests | Added as a merge parent and retained as a bounded research/accounting component |
| `audit-russian-readme` | Historical base of UEB | Ancestor of the UEB branch; no separate duplicate copy |
| `prototype-2-input-output` | Prototype 2 IO model | Already ancestral to `main`; no duplicate import |

The P6 and UEB README material is incorporated into the A2.4-updated prototype index. The later A2.4 household tests are retained rather than overwritten by the older P6 branch copy.

## Authority boundaries after consolidation

Consolidation does **not** mean that every subsystem is already one production-grade ledger. The following boundaries remain explicit:

1. **Canonical event format:** P6 canonical envelopes and A2.4 financial event groups are both present. A single repository-wide command/event schema and migration policy still need to be ratified.
2. **Atomic transaction:** P6 SQLite commits events, one aggregate projection, receipt and outbox in one local transaction. Its durable LotInventory adapter serializes lot/reservation state under one inventory-book root. A2.4 financial/SFC stores remain separate. There is not yet one atomic transaction spanning all six economic registers.
3. **Accounting authority:** UEB is retained as a research accounting kernel. It is not silently substituted for the typed EntityJournal/FinancialEventStore, and its sequential two-entry loan helper is not a cross-ledger atomic loan transaction.
4. **Domain registers:** physical flow, product, capital and financial components exist in durable or audited slices. Labour and legal-rights components still need their own authoritative durable stores, reducers, versioning, access policy and recovery tests. A bridge or evidence contract is not itself a register.
5. **SFC/GOLD:** sector and instrument oracles, projection replay and multi-period physical/capital fixtures exist. A single common event stream feeding all physical, labour, legal, capital, product and financial positions with period-close reconciliation is still an integration gate.
6. **Disaster recovery:** local SQLite crash tests, coordinator crash matrices, signed checkpoint fixtures and checkpoint storage code exist. External immutable/WORM custody, independently managed signing keys, restore drills across real domain stores and a production retention/rotation policy are not yet proven.

## Six-register target and current evidence

| Register | Present evidence | Remaining acceptance gate |
|---|---|---|
| Physical / inventory | P6 durable LotInventory SQLite adapter; A2.4 physical-flow store and crash/replay fixtures | One canonical command path; reconcile production, custody, stock and movement across all periods |
| Product / commodity | Typed product dimensions, valuation and durable product register | Connect actual production, shipment, inventory and valuation events without double counting |
| Capital | Cohort lifecycle, durable capital store and SCCE bridge | Periodic authoritative lifecycle from acquisition through service, depreciation, impairment and retirement |
| Labour / capability | Consent/time/capability contracts and audit fixtures | Durable authoritative Labour Register, consent revocation, time evidence, claims, correction lineage and recovery |
| Legal rights / claims | Claim projections, SEC/SPER evidence policy, entity journal claim identity | Durable Legal Rights Register, title/obligation state machine, evidence provenance, transfer/encumbrance and dispute lifecycle |
| Financial / monetary | EntityJournal, FinancialEventStore, journal adapter, UEB primitives and SFC projection stores | One idempotent atomic command boundary with all counterparties, receipts, projections and SFC effects |

The six labels describe target domains, not a claim that six production adapters have already been completed.

## Consolidated transaction and recovery target

The intended command path is:

`Command + authority + evidence + expected-version vector`
→ canonical event group
→ domain state transition
→ balanced financial postings where applicable
→ projection updates and coverage cursor
→ immutable idempotency receipt + outbox
→ independent replay and reconciliation.

The implementation must either commit all required effects in one database transaction or use a documented recoverable protocol with durable prepare/decision/receipt records. No adapter may publish a success receipt while one required register is missing the corresponding commit. Consumers of the outbox must use a transactional inbox/deduplication boundary.

Recovery acceptance must include process termination after every durable boundary, restart of all participants, idempotent retry, projection rebuild from canonical events, checkpoint verification, and exact comparison of restored state with the committed state vector. A replay audit that only validates hashes is not a state reconstruction test.

## Required merge gates

1. Run the full `prototype` unittest suite and all repository CI workflows on the exact consolidated HEAD.
2. Run the A2.4 GOLD-1 and GOLD-2A oracle fixtures and all six-sector/stock-flow identities.
3. Run the P6 SQLite repository and LotInventory lifecycle crash/restart tests.
4. Run coordinator prepare/receipt/commit/barrier crash matrix with all participants restarted.
5. Add cross-register tests proving that event, postings, physical/product/capital/labour/legal positions, SFC projections, cursor and receipt either all commit or all remain absent.
6. Run multi-period close/reopen/correction-generation tests with immutable prior-period lineage and dual approval.
7. Verify external checkpoint custody, key separation, restore and retention procedures before any production-readiness claim.

## Explicit non-claims

This consolidation record does not certify production readiness, legal validity of rights, factual truth of off-chain evidence, cross-host consensus, external WORM immutability, exactly-once broker delivery, or empirical superiority of the SYNERGY economic model. Passing software tests establishes only the tested invariants.

## Source branches and pull requests

- [PR #3 — Unified Economic Balance](https://github.com/Shtenco/synergistic_economics/pull/3)
- [PR #4 — A2.4 SFC/SCCE and GOLD](https://github.com/Shtenco/synergistic_economics/pull/4)
- [PR #5 — Prototype 6 real-economy integration](https://github.com/Shtenco/synergistic_economics/pull/5)
