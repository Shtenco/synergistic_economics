# Repository-wide branch and system audit — 11 November 2026

**Status:** source/metadata audit in progress; not a complete execution audit  
**Inspected refs:** `main`, `audit/sfc-scce-a2-4-continuation-20261111`, `research/sec-sper-integration-audit-2026-11-11`, `unified-economic-balance`, `audit-russian-readme`, `prototype-2-input-output`  
**Canonical main at inspection:** `7e9e5579ccb0835300b8336e1b675dcf5eaec4a9`  
**Audit branch at inspection:** `66939fbc0fa677eb631777f4b5ffa271a2bd1972`  
**P6 branch at inspection:** `972b9bae8db554af62b50a5428b7c32a3aeaeecb`

## 1. Scope and evidence boundary

GitHub branch metadata and recursive trees were retrieved for all six visible branches. All six tree responses reported `truncated=false`. The branch trees contain 142 distinct file paths in their union; the six branch snapshots account for approximately 10.4 MB of aggregate file sizes (not deduplicated).

This pass inspected the branch topology, unique-file inventories, principal runtime modules, financial persistence/projection modules, selected audit controls, and the PR/CI metadata. It is **not yet a line-by-line review of every byte of all 142 unique paths**, and it is not a complete runtime test execution.

A local repository archive could not be downloaded: the shell's GitHub DNS resolution fails (`Could not resolve host: github.com`). The GitHub connector can return UTF-8 source content but does not expose a local archive/file-writing path to the analysis runtime. Consequently, an actual LZMA archive was **not produced or decompressed** in this pass. No LZMA compression ratio or claim of whole-repository compressed inspection is made. The analysis instead uses Git tree/blob identities and compact source-level findings. This limitation must remain visible until an archive can be materialized in a local runner.

## 2. Branch topology and integration status

| Branch | HEAD | Blob count | Aggregate blob bytes | Role |
|---|---|---:|---:|---|
| `main` | `7e9e557` | 84 | 2,632,363 | Canonical baseline |
| `audit/sfc-scce-a2-4-continuation-20261111` | `66939fb` | 128 | 3,282,425 | SFC/SCCE and cross-register audit |
| `research/sec-sper-integration-audit-2026-11-11` | `972b9ba` | 95 | 2,804,892 | SEC/SPER and real-economy event/recovery prototype |
| `unified-economic-balance` | `8d36a76` | 34 | 804,818 | Separate UEB accounting kernel |
| `audit-russian-readme` | `62a2247` | 31 | 772,917 | Documentation lineage |
| `prototype-2-input-output` | `95c8a31` | 31 | 772,917 | Earlier IO prototype lineage |

PRs observed:
- PR #4: audit branch -> `main`, open, Draft.
- PR #5: P6 branch -> `main`, open, Draft.
- PR #3: `unified-economic-balance` -> `audit-russian-readme`, open, not Draft. Its target is not `main`.
- PRs #1 and #2 are closed.

Commit comparison reports:
- audit branch is ahead of main (286 commits in the current GitHub comparison response), with 44 changed paths;
- P6 branch is 26 commits ahead of main, with 12 changed paths at its latest inspected head;
- UEB branch is diverged from main (8 ahead, 450 behind) and targets the older documentation branch;
- `prototype-2-input-output` and `audit-russian-readme` are behind main in the current comparison.

**Integration consequence:** do not treat these branches as one already integrated codebase. PR #3's UEB kernel is not currently on the canonical main lineage. PR #4 and PR #5 add separate accounting/event abstractions. Any integration must be planned against a single canonical base and a single authority map.

PR #4's description contains HEAD/CI identifiers that do not match the currently observed branch head `66939fb...`; release metadata needs exact-SHA synchronization.

## 3. System-level state model

The repository is best represented as a vector of non-interchangeable state spaces:

```
X_t = (Q_t, K_t, S_t, M_t, F_t, R_t, H_t, E_t, P_t)
```

where:
- `Q`: physical quantities by product, grade, unit, node and period;
- `K`: capital cohorts and physical asset lifecycle;
- `S`: productive service flows derived from operating cohorts;
- `M`: money/deposits and payment settlement;
- `F`: financial instruments, holder assets and issuer liabilities;
- `R`: legal title, ownership, custody, mandates and other rights;
- `H`: labour time, capabilities, consent and service delivery;
- `E`: ecological stocks, regeneration, extraction, emissions and constraints;
- `P`: projections, event cursors, snapshots and reconciliation metadata.

A valid command is not merely a function that changes one Python object. It is a typed transition:
`X_{t+1} = T_v(X_t, command, evidence)`,
where `v` fixes the schema/policy/reducer versions and the transition must preserve all applicable constraints.

Core identities to preserve:

**Physical stock-flow by product/unit/node/period**
`Q_close = Q_open + production + imports + inflows - intermediate_use - final_use - exports - losses`.

**Capital physical stock**
`K_close = K_open + additions - physical_losses - final_retirements`.
Revaluation and depreciation/CFC are separate monetary/valuation components, not physical disappearance.

**Capital services**
`S_cell = Σ(quantity × service_capacity × availability × utilization × quality)`;
the SCCE compatibility multiplier is `S_cell / declared_baseline_service`, not monetary capital stock.

**Financial instrument stock-flow**
`position_close = position_open + T + V + O`,
with transaction (`T`), revaluation (`V`) and other-volume changes (`O`) distinct.

**Financial net lending**
`FNL = Σ(transaction asset changes) - Σ(transaction liability changes)`.
Revaluation and other-volume changes must not be included in transaction NL.

**Double-entry event**
`Σ debits = Σ credits` for each validated journal event; holder and issuer instrument positions must mirror by full identity.

**Consolidation**
Internal claims cancel only within the declared consolidation perimeter. A financial claim is not additional real wealth. Custody is not title; shipment is not settlement; token issuance is not income by default.

The system is not closed end-to-end until one immutable event/provenance chain connects the applicable state transitions and all cross-register balances reconcile at the same period boundary.

## 4. Confirmed source-level findings

### F-01 — SFC opening snapshot verifier contradicts its own signed-opening contract

**Severity: High; likely deterministic audit-test failure.**

Files:
- `prototype/sfc_projection_registry.py`, `verify_sfc_projection_openings()`;
- `research/audits/sfc_scce_a2_4_2026-11-11/audit_sfc_projection_registry.py`;
- `research/audits/sfc_scce_a2_4_2026-11-11/STATUS.md`.

The normalization path accepts any finite canonical decimal opening, including negative positions. The activation function then inserts the rows and immediately calls `verify_sfc_projection_openings()`. The verifier rejects every row for which `Decimal(amount) < 0`.

The committed audit fixture explicitly expects activation of a negative opening position to succeed, and STATUS says signed openings are permitted at the generic layer while nonnegative restrictions belong to instrument-specific policy. Those statements conflict with the verifier implementation.

Result: negative opening activation reaches the post-write verification and is rejected, contradicting the fixture and documented contract. This is a source-level proof from the control flow; no CI failure is claimed until the exact-head run executes.

**Correction direction:** generic snapshot integrity validation should check canonical finite decimal representation and digest only. Apply nonnegative constraints from an explicit versioned instrument policy during projection replay/contract validation. Add positive and negative opening snapshot tests and run the exact audit workflow.

### F-02 — Financial journal adapter does not authenticate the validator object

**Severity: High at the accounting trust boundary.**

File: `prototype/financial_journal_adapter.py`, `append_validated_group()`.

The adapter checks that `journal.post` is callable and that `journal.events` is a dict. It then accepts an event when the object appears in that dict and the returned pair is equal. It does not require the concrete `EntityJournal` implementation or a non-forgeable validator capability.

A caller can supply a lookalike object whose `post()` method registers arbitrary event objects and returns an equal pair. The adapter then serializes the event and writes it through `FinancialEventStore`. The existing negative fixture only proves that a raw dictionary passed directly as an event is rejected; it does not test a forged journal/validator.

**Correction direction:** move the canonical validator behind an unforgeable internal boundary (or have the adapter own construction of the trusted EntityJournal/registry); do not treat a duck-typed `post()` as proof of canonical validation. Add an adversarial fake-validator test.

### F-03 — Three incompatible event/accounting authorities coexist across branches

**Severity: Critical architectural integration risk.**

Observed implementations:
1. `main:prototype/synergy_kernel.py`: in-memory `EventStore` and `DoubleEntryLedger`.
2. `unified-economic-balance:prototype/unified_accounts.py`: a separate in-memory `DoubleEntryLedger`, plus physical stock and claim helpers.
3. `audit branch:prototype/financial_event_store.py`: SQLite WAL/FULL append-only event-group store with its own schema, event rows, journal-line mirrors and group hash chain; it stores postings but deliberately delegates accounting validation upstream.
4. `P6 branch:prototype/real_economy_event_bridge.py`: test-only in-memory coordinator over the existing `synergy_kernel.EventStore`, not the SQLite `FinancialEventStore`.

These are not drop-in implementations of one interface. Their event envelopes, idempotency scopes, persistence guarantees and journal semantics differ. P6's in-memory coordinator does not inherit the SQLite store's durability or chain. The SQLite store does not yet atomically update SFC projection positions, coverage and cursors.

**Correction direction:** publish one canonical authority matrix and integration interface. Select one durable commit authority for financial events and projections; do not introduce a fourth store or merge these ledgers by copying balances.

### F-04 — UEB loan origination can partially commit its bilateral journal operation

**Severity: Medium in the UEB prototype; high if reused as a command boundary.**

File: `unified-economic-balance/prototype/unified_accounts.py`, `loan_origination()`.

The function posts the lender-side journal entry and then posts the borrower-side entry as a second independent mutation. It does not preflight both generated entry IDs or stage both entries as one atomic transaction. If the lender entry ID is new but the borrower entry ID already exists, the first posting remains committed while the second raises a duplicate-ID error. The bilateral loan operation is then half-applied.

**Correction direction:** stage and validate both entries before mutating; commit both through one transaction/batch method with rollback. Add a negative test where only the second generated ID collides.

### F-05 — UEB duplicates the existing kernel ledger instead of adapting it

**Severity: High architectural duplication risk.**

The UEB branch defines a second `DoubleEntryLedger` and a different journal/account model from `main:prototype/synergy_kernel.py`. It is currently isolated on a diverged branch, which is safer than silently coexisting on main, but PR #3 is not a main-targeted integration. Its own specification describes substantial omissions: rights graph, maturity/default lifecycle, fixed assets/depreciation, ecological accounts, multi-currency consolidation and evidence-linked delivery.

**Correction direction:** do not merge the class as a competing canonical ledger. Extract the useful domain contracts and test vectors, then map them onto the selected canonical journal/event authority.

### F-06 — P6 and A2.4 financial persistence are not yet integrated

P6 uses the existing in-memory kernel EventStore. A2.4 introduces a SQLite event-group store and a separate projection kernel/registry. The P6.3 contract explicitly requires a single durable transaction or event-sourced commit point, complete multi-aggregate events, receipts and outbox. A2.4's own STATUS says SFC projection applied-through cursor, event coverage and issuer-side register remain unimplemented.

Therefore neither branch currently provides one end-to-end commit of:
`command -> canonical event group -> journal postings -> holder/issuer position deltas -> sector projections -> coverage/cursor -> receipt/outbox`.

This is an integration gap, not a defect in the isolated arithmetic kernel.

### F-07 — Capital cohort bridge is an opt-in adapter, not a canonical capital register

File: `prototype/capital_cohort_bridge.py`.

The bridge uses floating-point quantities and `math.isclose` conservation checks, and maps service flows into the SCCE's dimensionless scalar capital multiplier. It keeps cohort state immutable within the pure transition function and checks event IDs/period progression, but it is not connected to the default SCCE period loop or a durable canonical capital register. It does not itself establish monetary gross/net capital stock, title, rights, depreciation/CFC or complete B8.1 component/material passports.

This is acceptable as a bounded research adapter, not as the system's canonical physical capital authority. Any later production bridge must specify units/precision, persistence, provenance and cross-period transaction boundaries.

## 5. What is strong and should be preserved

- The SCCE audit branch explicitly distinguishes implemented controls from pending execution and refuses to equate synthetic arithmetic with empirical validation.
- `financial_event_store.py` uses SQLite WAL, FULL synchronous mode, `BEGIN IMMEDIATE`, unique identities, group sequence/hash chaining, and verification of normalized event/posting mirrors against immutable group envelopes.
- Verified reads use one explicit WAL snapshot, reducing time-of-check/time-of-use read skew.
- The SFC projection kernel is pure and deterministic, requires explicit openings, tracks T/V/O separately, checks per-event mapping coverage and uses exact Decimal accumulation.
- The P6 design preserves separation between Claim, evidence, inventory, rights/title and financial journal; it also explicitly refuses to infer title or settlement from physical movement.
- The repository's staged gate model correctly separates unit, component, integration, end-to-end, statistical and empirical validation.

These controls are valuable; the findings above concern their boundaries and integration, not a recommendation to discard them.

## 6. CI and execution evidence

At the inspection time:
- PR #4 exact-head Prototype validation, SCCE Stage-C2 and A2.4 audit-control jobs were queued; no completed conclusion/log was available.
- PR #5 exact-head Prototype validation was queued; no completed conclusion/log was available.
- Canonical main's latest surfaced Prototype and Stage-C2 runs included failures on earlier commits; no claim is made that the audit/P6 exact heads passed.
- The local shell could not clone the repository due DNS failure.

A queued job is not a pass. A test script committed to a branch is not execution evidence. A local microtest described in STATUS is not a full repository test run.

## 7. Required unified architecture equation and authority map

The target must have one authoritative write path per state domain:

```
Command + authority + evidence + expected-version vector
                         |
                         v
             Canonical transaction boundary
                         |
        +----------------+------------------+
        |                |                  |
        v                v                  v
  Canonical event   Journal postings   Aggregate changes
        |                |                  |
        +----------------+------------------+
                         |
                         v
              Commit receipt + outbox
                         |
                         v
      Deterministic projections (Q,K,S,F,R,H,E)
                         |
                         v
          Cross-register reconciliation gates
```

No projection may become a second write authority. The projection cursor must advance in the same durable boundary as the events/deltas it certifies, or be fully rebuildable from one canonical source. Corrections are new compensating events, not in-place history edits.

## 8. Prioritized remediation

1. **P0:** fix F-01 and add the signed-opening regression test; fix F-02 with a trusted validator boundary and adversarial fake-validator test.
2. **P0:** freeze the canonical authority map: event store, financial journal, SFC projection, inventory, capital cohorts, rights/title and physical-flow register.
3. **P1:** decide whether A2.4 SQLite event store becomes the selected durable event authority or whether a different transactional repository is chosen. Do not connect P6 by adapting the in-memory EventStore.
4. **P1:** define the canonical command/receipt schema across financial and inventory commands, including idempotency scope, expected-version vectors, command event ordinals and commit identity.
5. **P1:** implement one transaction covering event group, validated postings, SFC deltas, per-event coverage, materialized positions, applied-through cursor and receipt; otherwise define event-sourced replay with rebuildable projections.
6. **P2:** implement holder/issuer mirror replay, multi-period SFC closure, physical/capital/labour interfaces and snapshot/recovery only after the commit boundary is selected.
7. **P3:** run all branch-specific test suites on exact heads, inspect every job log, then run a frozen end-to-end scenario. Statistical and empirical gates remain separate.

## 9. Current audit conclusion

The repository contains substantial and useful independent research/prototype components, but it is **not yet one integrated economic engine**. Its strongest path is to preserve the existing physical/SCCE and accounting research while converging on one canonical event/transaction boundary and explicit typed projections.

The two confirmed source-level defects (negative-opening verification contradiction and forgeable journal-validator adapter) should be corrected before any financial projection integration is treated as trusted. UEB's independent ledger should remain isolated until its useful domain rules are reconciled with the canonical journal.

**No full-repository LZMA archive, whole-code local test run, all-branch line-by-line review, CI pass, empirical validation or production-readiness claim is made in this report.**


## 10. Additional source pass — physical IO transition safety

### F-08 — Input-output period transition is not failure-atomic

**Severity: Medium for the research simulator; High if reused as a command or accounting boundary.**

Files:
- `prototype/io_economy.py`, `InputOutputEconomy.step()` and `_clear_product()`;
- `prototype/test_io_economy.py`.

The period method mutates the live model as it proceeds: each product market immediately changes buyer cash, seller cash, inventory, household consumption, import cash and prices, and appends an event. Production then mutates input stocks, cash, output stocks and household income, and appends more events. Only after all of those mutations does the method check physical stock balances and total cash conservation.

If a later product clearing, production event, or closing invariant raises, the earlier mutations and events remain. There is no period-level snapshot/rollback, staged next-state object, or committed-period cursor. A retry of the same period can therefore start from a partially advanced state and may collide with already appended event keys. The tests cover successful deterministic scenarios and conservation after successful steps, but do not inject a failure after the first market has mutated state and assert rollback/retry safety.

This does not invalidate the simulator as a research model, but it means `step()` is not a safe atomic economic command and its event list is not a durable canonical event log.

**Correction direction:** either (a) explicitly document the simulator as non-transactional and never use it as a canonical write boundary, or (b) stage all period mutations in a detached candidate state, validate every product/cash/physical invariant, then publish state + event batch + period cursor atomically. Add fault injection after the first market, after production, and immediately before period close; assert byte-for-byte state/event equality after failure and successful same-period retry.

### Physical-model boundary clarification

The inspected `scc_dynamic_economy.py`, `cellular_coordination.py` and `household_distribution.py` intentionally use floating-point quantities and synthetic agents for deterministic physical/allocation experiments. Their module contracts explicitly exclude some combination of money, title, credit, wages, ownership or utility measurement. Float use in these bounded research kernels is not by itself a financial-ledger defect. The critical requirement is that no downstream canonical monetary, rights or stock-flow register silently treats those synthetic outputs as authoritative without a typed unit/period/provenance adapter and reconciliation.

## 11. Exact-head CI recheck

At 2026-11-11 15:18 UTC, GitHub returned these runs for the inspected exact commits:
- Audit branch `66939fbc0fa677eb631777f4b5ffa271a2bd1972`: Prototype validation run `42952568163` and SCCE Stage-C2 run `42952568228`, both still `queued`.
- P6 branch `f5d3e33c54b434739acd6fa86137db1891c40b97`: Prototype validation run `43046088140`, still `queued`.

No conclusion is available. Do not mark these gates passed until completed run/job results are inspected.
