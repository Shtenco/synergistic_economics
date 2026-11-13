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
4. **Domain registers:** physical flow, product, capital and financial components exist in durable or audited slices. Labour and legal-rights now have independent authoritative SQLite event stores, replay reducers, aggregate versioning, append-only ACL and native coordinator participant methods. Their production deployment, privacy controls, external custody and full six-register cross-domain recovery remain open. A bridge or evidence contract is not itself a register.
5. **SFC/GOLD:** sector and instrument oracles, projection replay and multi-period physical/capital fixtures exist. A single common event stream feeding all physical, labour, legal, capital, product and financial positions with period-close reconciliation is still an integration gate.
6. **Disaster recovery:** local SQLite crash tests, coordinator crash matrices, signed checkpoint fixtures and checkpoint storage code exist. External immutable/WORM custody, independently managed signing keys, restore drills across real domain stores and a production retention/rotation policy are not yet proven.

## Six-register target and current evidence

| Register | Present evidence | Remaining acceptance gate |
|---|---|---|
| Physical / inventory | P6 durable LotInventory SQLite adapter; A2.4 physical-flow store and crash/replay fixtures | One canonical command path; reconcile production, custody, stock and movement across all periods |
| Product / commodity | Typed product dimensions, valuation and durable product register | Connect actual production, shipment, inventory and valuation events without double counting |
| Capital | Cohort lifecycle, durable capital store and SCCE bridge | Periodic authoritative lifecycle from acquisition through service, depreciation, impairment and retirement |
| Labour / capability | New LabourRegister: immutable event chain, consent/engagement lifecycle, capability assessments, non-overlapping time allocations, correction lineage, ACL and native coordinator prepare/commit | Bind actual identity/evidence providers; define privacy retention and compensation interfaces; run full six-register disaster recovery |
| Legal rights / claims | New LegalRightsRegister: immutable event chain, optional-obligor title/claim identity, evidence, transfer, encumbrance/release, dispute/adjudication, correction and extinguishment | Bind actual legal evidence/authority sources; define jurisdiction-specific controls and full six-register recovery |
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


## Implementation continuation — Labour/Legal native stores

The integration branch now adds durable_event_register.py, labour_register.py and legal_rights_register.py. Labour and Legal Rights implement the coordinator participant interface against their own authoritative event database; their participant inbox and event append are colocated. Prepared aggregates are reserved, authorization is checked before prepare, ACL mutations are serialized behind outstanding prepares, and commit retry repairs the event/receipt boundary idempotently. The event hash chain binds event identity, aggregate version, timestamps, actor, authority and payload digest.

A coordinator integration test composes these two native stores with four existing protocol conformance participants. This proves only the two native adapters; it does not complete the physical, capital, product and financial native adapters or certify six-register production atomicity. See prototype/DURABLE_LABOUR_LEGAL_REGISTERS.md.


## Implementation continuation — common event groups and checkpoint deployment adapter

The coordinator now exposes committed_event_group(txid), which assembles the six participant receipts only after the global visibility barrier and assigns one common_event_id. Labour and Legal Rights persist this identifier natively in their hash-chained event rows. The other four participant implementations still expose protocol receipts rather than native event rows with this metadata.

A typed Decimal SFC/GOLD stock-flow kernel now maps explicit movement declarations from committed six-register groups. It rejects silent participant omissions, missing native-unit identity, duplicate movements, T/V/O imbalance, mirror mismatch and broken opening(t+1)=closing(t) carry-forward. This is a tested integration contract, not yet a mapper from every existing production register schema; actual physical/capital/product/financial event mappings remain OPEN.

S3ObjectLockAnchor now implements the remote checkpoint anchor contract with conditional immutable writes, S3 versioning, COMPLIANCE retention, SSE-KMS key identity checks and a hash-chained contiguous per-service anchor history. Only mocked S3 contract tests are available. No AWS bucket, independent account, KMS key, IAM policy or live restore drill is configured, so external WORM deployment remains OPEN.


## Implementation continuation — five native coordinator participants

The integration branch now adapts the existing PhysicalFlowStore, CapitalCohortStore and ProductRegister through native_store_participants.py. Each adapter writes its prepare/receipt inbox into the same SQLite database as the domain register, validates against the current native revision and domain reducer, reserves the register stream, and invokes the store's idempotent native append after the coordinator's durable commit decision. Direct append paths reject writes while a coordinator prepare is outstanding. The adapter requires an explicit external authorizer; there is no permissive production default.

Together with the native LabourRegister and LegalRightsRegister, five of six coordinator participants now target authoritative domain stores. The financial participant is still a protocol-conformance store: its adapter must use the validated EntityJournal plus the projection-aware FinancialEventStore transaction, not a raw event append. The physical adapter currently binds the physical-flow store, not the full P6 lot-inventory lifecycle. Thus six-register production atomicity remains OPEN.

The six-participant test commits physical flow, capital period, product specification, labour offer and legal claim in one coordinator transaction, with a conformance financial participant, then assembles the common event group and reconciles the physical sender/receiver stock positions. This proves the new native adapters and physical mirror path only; it does not prove a complete financial GOLD or all-domain SFC period close.


## Implementation continuation — six native coordinator participants

The financial participant is now native as well. It requires an active, replay-verified SFC opening snapshot; validates canonical JournalEvent values against an EntityRegistry; derives financial instrument T/V/O movements through the same mapper used by SFC; and commits through append_projected_group. The financial database transaction includes event group, postings, instrument/control projections, coverage and cursor. Its prepare reservation is enforced at the projection-aware append boundary.

The coordinator now commits participants in the explicit order physical → capital → labour → product → legal_rights → financial. Financial is last: a visible SFC projection cannot precede durable commits of the other five participants. The global read barrier remains mandatory. This is a recoverable six-database prepare/commit protocol, not one cross-database SQL transaction or cross-host consensus.

All six coordinator participants now use native stores. The physical adapter still binds physical flows, not the complete lot/reservation inventory lifecycle. The current integrated SFC/GOLD movement test covers physical sender/receiver positions and financial instrument asset positions; liability mirrors are separately enforced by GOLD journal/oracle controls, while control-only and full labour/legal/capital/product period mappings remain open.
