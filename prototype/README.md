# SYNERGY Economic Prototypes

Python 3.10+ research prototypes. Current implementations use the standard library only.

## Prototype 0 — Kernel

[synergy_kernel.py](synergy_kernel.py) contains the first small accounting/event/production kernel:
- balanced debit/credit journal entries;
- duplicate journal-entry and event-key protection;
- append-only ordered event log;
- bounded production, inventory and shipment checks;
- exact budget-balanced pool allocation;
- a simple inter-cell cash transfer.

## Prototype 1 — Seven-Cell Economy

- [seven_cell_economy.py](seven_cell_economy.py) — deterministic seven-cell simulation.
- [Model specification](SEVEN_CELL_ECONOMY.md) — state variables, production constraints, period sequence, accounting boundaries, scenarios, first results and limitations.
- [Scenario comparison JSON](results/seven_cell_scenario_comparison.json) — 24-period baseline and four deterministic stress scenarios.
- [test_seven_cell_economy.py](test_seven_cell_economy.py) — tests for production response, household budget, cash conservation, credit, defaults and journal integrity.

### Run Prototype 1

From this directory:

```bash
python seven_cell_economy.py --scenario baseline --periods 24
python seven_cell_economy.py --scenario compound_crisis --periods 24 --output results/compound_crisis.json
python -m unittest discover -s . -p 'test_*.py' -v
```

Scenarios: baseline, demand_collapse, energy_shock, resource_shock, compound_crisis.


## Prototype 2 — General Input-Output Economy

- [io_economy.py](io_economy.py) — data-driven multi-product, multi-firm simulation with multiple suppliers, input recipes, household baskets, product-level market clearing, adaptive prices, import offers, inventories and physical/cash conservation.
- [Model specification](GENERAL_IO_ECONOMY.md) — entities, production equations, market-clearing rule, accounting identities, scenario assumptions and explicit limitations.
- [test_io_economy.py](test_io_economy.py) — tests for deterministic execution, multiple suppliers, market and accounting invariants, shocks and flow/stock separation.

### Run Prototype 2

From the repository root:

```bash
python prototype/io_economy.py --scenario baseline --periods 12
python prototype/io_economy.py --scenario compound_shock --periods 12
python -m unittest discover -s prototype -p 'test_*.py' -v
```

Scenarios: baseline, demand_collapse, energy_import_shock, metals_shortage, compound_shock.

Prototype 2 currently uses immediate cash settlement. Trade credit, maturity schedules, defaults, capital accumulation and ecological constraints are explicitly deferred to separately testable modules; they are not simulated by this version.

## Prototype 3 — SCCE Cellular Coordination Kernel

- [cellular_coordination.py](cellular_coordination.py) — Stage-A local-neighbour matching protocol, including explicit request relay, offers, reservations and acceptances; consent-gated forwarding; packet batching across shared edges with record-level payload accounting; market, central min-cost-flow, cooperative-pool and cellular regimes. A cell's relay permission defaults to false; the synthetic benchmark opts its relay nodes in explicitly.
- [test_cellular_coordination.py](test_cellular_coordination.py) — invariants for supply/demand bounds, local hop limits, disconnected components, determinism, stress cases and paired Monte Carlo structure.
- [Model and experiment specification](../research/SCCE_CELLULAR_ENGINE_AND_COMPARATIVE_EXPERIMENT_V0_2.md) — cellular state transition, local messages, reservations, consent, fair comparison, outcome vector and research roadmap.
- [Preliminary Stage-A benchmark results](../research/SCCE_STAGE_A_PRELIMINARY_BENCHMARK_2026-11-10.md) — paired 100-seed results for baseline, compound, supply-crisis and demand-surge scenarios.

Run from the repository root:

```bash
python prototype/cellular_coordination.py --seed 1 --shock none --hops 1
python prototype/cellular_coordination.py --monte-carlo 100 --shock compound --hops 2
python prototype/cellular_coordination.py --monte-carlo 100 --shock compound --hops 2 --summary-only
python -m unittest discover -s prototype -p 'test_*.py' -v
```

This is a local allocation/coordination kernel, not yet a complete dynamic economy. Its service-value metrics are diagnostic and must not be interpreted as GDP or empirical welfare.

## Prototype 4 — Stage-B Dynamic SCCE Physical Economy

- [scc_dynamic_economy.py](scc_dynamic_economy.py) — seven-cell, multi-period physical economy with endogenous production plans, input recipes, local inventories, raw-resource regeneration, intermediate procurement, final consumption, explicit cellular message relay and packet/record-level coordination-cost accounting. Each cell's trade consent, relay consent and counterparty allowlist are carried from its CellSpec into the matching protocol.
- [test_scc_dynamic_economy.py](test_scc_dynamic_economy.py) — production, determinism, self-trade, resource stock-flow and paired-regime tests.
- [100-seed Stage-B results](../research/SCCE_STAGE_B_PRELIMINARY_RESULTS_2026-11-10.md) — paired baseline and compound-shock comparisons, confidence intervals hop-radius sensitivity and paired coordination-labour response curve.
- [Stage-B design and limitations](../research/SCCE_CELLULAR_ENGINE_AND_COMPARATIVE_EXPERIMENT_V0_2.md#part-iii--stage-a-kernel-and-its-scope)

Run from the repository root:

```bash
python prototype/scc_dynamic_economy.py --compare --shock none --periods 24 --hops 2
python prototype/scc_dynamic_economy.py --compare --shock compound --periods 24 --hops 2
python prototype/scc_dynamic_economy.py --monte-carlo 100 --shock none --periods 24 --hops 2 --summary-only
python prototype/scc_dynamic_economy.py --monte-carlo 100 --shock compound --periods 24 --hops 1 --summary-only
python prototype/scc_dynamic_economy.py --monte-carlo 100 --shock compound --periods 24 --hops 2 --summary-only
python prototype/scc_dynamic_economy.py --monte-carlo 100 --shock compound --periods 24 --hops 3 --summary-only
python prototype/scc_dynamic_economy.py --coordination-sensitivity --monte-carlo 20 --shock compound --periods 24 --hops 2
python prototype/scc_dynamic_economy.py --coordination-frontier --monte-carlo 20 --shock compound --periods 24 --hops 2
```

Stage B is a physical production-and-consumption layer. Its paired summaries also report post-hoc household cumulative essential/overall fulfilment, lower-decile and minimum household essential fulfilment, household fulfilment Gini, mean-period lower-tail metrics and worst-period minimum. The default reporting panel uses five synthetic households per cell with proportional rationing; it decomposes already-consumed cell quantities and does not feed back into production. Cellular production planning is isolated as a pure local transition over an immutable observation containing the cell's own state and only reachable, mutually trade-consenting neighbours' declared input demand; the local rule does not receive the global cell-state dictionary. Cellular requests are relayed neighbour by neighbour; forwarding consent is opt-in at the cell level and is distinct from consent to trade. Repeated request/offer/reservation/acceptance records on the same directed edge are bundled into packets, while packet count and payload-record count remain separately visible. A paired sensitivity comparison and six-level paired response frontier vary packet overhead and per-additional-record labour cost. The default synthetic cost is 0.01 labour-hours per packet plus 0.002 hours per additional payload record. Input-procurement coordination reduces current-period productive labour; final-goods coordination reduces next-period labour. The assumptions require calibration and sensitivity analysis; governance, failed bargaining beyond recorded relay requests, enforcement and dispute resolution remain incomplete. Stage B does not yet model money, credit, wages, ownership, capital investment, household income, or measured utility. Fixed-price output and consumption are transparent physical-value indices, not GDP or empirical welfare. The existing seven-cell financial prototype remains unchanged.

## Prototype 5 — Stage-C1 Household Physical Distribution

- [household_distribution.py](household_distribution.py) — distributes goods already available inside each cell among that cell's households; supports proportional, priority-weighted and floor-priority rationing, essential-first sequencing and household-level distribution metrics. The floor-priority rule reserves a declared fraction of each household's essential claim before priority-weighted allocation of the remainder; it cannot guarantee the floor when total stock is insufficient.
- [scc_household_bridge.py](scc_household_bridge.py) — creates reproducible synthetic household profiles from each Stage-B cell's declared demand and disaggregates the period's already-consumed physical quantities; it is explicitly post-hoc and does not create a second goods flow.
- [scc_household_experiment.py](scc_household_experiment.py) — period-by-period paired comparison of proportional, priority-weighted and floor-priority household rationing, preserving the timing of shortages.
The experiment uses a persistent synthetic household panel across all periods. It reports both cumulative-horizon household fulfilment and period-level lower-tail/worst-period metrics, so temporal shortages are not hidden by the cumulative totals.
- [test_household_distribution.py](test_household_distribution.py) and [test_scc_household_bridge.py](test_scc_household_bridge.py) — test stock conservation, household need bounds, no cross-cell pooling, lower-tail metrics, and exact reconciliation of household essential service to Stage-B consumption.
- [Stage-C1 design and limitations](../research/SCCE_STAGE_C_HOUSEHOLD_DISTRIBUTION_V0_1.md) — money-free household layer and integration boundary with Stage B.
- [Stage-C1 preliminary results](../research/SCCE_STAGE_C1_PRELIMINARY_RESULTS_2026-11-10.md) — 20-seed paired comparison of proportional, priority-weighted and floor-priority household allocation, including paired 25%, 50% and 75% essential-floor sensitivity and lower-tail effects.

Run the paired Stage-C1 experiment from the repository root:

```bash
python prototype/scc_household_experiment.py --runs 20 --shock compound --periods 24 --hops 2 --households-per-cell 10 --priority-dispersion 0.4 --essential-floor-fraction 0.5 --summary-only
```

The Stage-C1 kernel remains separate from Stage B's production and matching decisions. A tested post-hoc bridge reads Stage-B per-cell demand and consumption snapshots and decomposes the already-consumed quantities among synthetic household profiles. A paired experiment compares proportional, priority-weighted and floor-priority rationing using the same persistent households and physical quantities. It does not feed back into production or create a second delivery. A future endogenous integration must preserve the same no-double-counting boundary. Household income, wages, ownership, money and credit are not yet implemented.

### Stage C2-A1 — Household demand signals

- [scc_household_signals.py](scc_household_signals.py) — builds a persistent synthetic household panel from cell demand and publishes only aggregated cell/product request signals; individual identifiers and priority weights are not exposed to the production engine. Small groups are suppressed by a minimum-contributor rule.
- [test_scc_household_signals.py](test_scc_household_signals.py) — checks demand reconciliation, privacy-scoped payloads, fail-closed suppression and exact equivalence with the Stage-B physical baseline.
- [scc_endogenous_household_economy.py](scc_endogenous_household_economy.py) — C2-A2 in-loop household delivery: recurring food shortfalls are recorded as deprivation exposure, while only delayed care-service claims enter a bounded queue that feeds the household's own cell demand in the next period; physical deliveries are allocated to households and reconciled product-by-product.
- [care_service_queue.py](care_service_queue.py) — C2-A3 FIFO care-service queue with explicit age cohorts, expiry, retention/attrition and a hard per-household capacity; overflow is recorded rather than silently added to future demand.
- [test_care_service_queue.py](test_care_service_queue.py) — tests FIFO service, last-opportunity expiry, retention attrition and capacity overflow.
- [test_scc_endogenous_household_economy.py](test_scc_endogenous_household_economy.py) — checks zero-backlog equivalence to Stage B, household delivery reconciliation, care-queue caps, no food-demand carry-over and the effect of allocation and service-order rules on household outcomes.
- [scc_endogenous_household_experiment.py](scc_endogenous_household_experiment.py) — paired Monte Carlo runner for four economic regimes and three household allocation rules; reports household lower-tail outcomes, essential backlog and physical production/consumption, with paired backlog-versus-zero-backlog and current-first-versus-backlog-first service-order sensitivity modes.
- [test_scc_endogenous_household_experiment.py](test_scc_endogenous_household_experiment.py) — checks paired seed structure, regime contrasts and policy validation.
- [Stage-C2-A2 typed backlog results](../research/SCCE_STAGE_C2_A2_TYPED_BACKLOG_RESULTS_2026-11-10.md) — 20-seed paired comparison with in-loop household backlog, zero-backlog control and paired sensitivity intervals.
- [Stage-C2 research design](../research/SCCE_STAGE_C2_ENDOGENOUS_HOUSEHOLD_ECONOMY_V0_1.md) — specifies the remaining endogenous household–cell feedback, voluntary time, income/ownership interfaces and comparative welfare experiments.

C2-A1 is deliberately a controlled bridge: it makes household profiles the explicit source of cell demand but preserves aggregate demand and Stage-B physical outcomes exactly. C2-A2 adds an in-loop household delivery and bounded essential-backlog feedback into the next period's own-cell demand. This is still a synthetic physical model; household labour, income, ownership, money and credit remain unimplemented.

## Prototype 6 — Real Economy Integration (P6.0–P6.1)

- [real_economy_protocol.py](real_economy_protocol.py) — additive standard-library reference module: read-only SEC projection over canonical Claim, proposition-specific SPER evidence decisions, lot-level stock, owner/custodian separation, versioned reservations, expiry, partial movement into child lots, and idempotent command receipts. It does not create a second EventStore or financial ledger.
- [test_real_economy_protocol.py](test_real_economy_protocol.py) — focused tests for stock/reservation invariants, stale versions, authorization, idempotency, lot splitting, claim projection and evidence verification.
- [P6.0–P6.1 specification](../research/PROTOTYPE_6_REAL_ECONOMY_INTEGRATION_P6_0_P6_1_V0_1.md) — scope, canonical boundaries, lifecycle rules, known limitations and next implementation gates.
- [SEC/SPER architecture audit](../research/SEC_SPER_INTEGRATION_AUDIT_AND_CONTRACT_V0_1.md) — integration contract and cross-volume audit.

Run the focused tests from the repository root:

```bash
python -m unittest discover -s prototype -p 'test_real_economy_protocol.py' -v
```

Run the full regression suite:

```bash
python -m unittest discover -s prototype -p 'test_*.py' -v
```

P6.0–P6.1 are in-memory research primitives. They are not synchronized with Stage-B inventory, do not persist to the canonical EventStore, do not post journal entries, and do not implement production identity, cryptographic credential verification, title transfer, payment or durable atomicity. Passing these tests validates only the stated invariants.

## Validation

GitHub Actions runs the prototype test suite and both baseline and compound-crisis simulations when files under prototype/** or the prototype workflow change.

## Scope and limitations

These are research instruments, not production financial software or calibrated forecasts. They do not implement legal accounting standards, banking settlement, identity/access controls, durable transactional storage, concurrency safety, tax, full insolvency law, full national accounts, empirical parameter calibration or a complete institutional comparison.

The seven-cell model has a single representative household cash pool, one shared energy supplier, an external material supplier, fixed prices, simplified capital, a single renewable resource stock and a narrow insolvency trigger. See the model specification for the full limitations and next upgrades.

Passing software tests validates only the tested invariants. It does not validate the SYNERGY economic thesis.

Scenario outputs include a deterministic `event_log_digest` over the ordered event payload digests; it is an integrity checksum, not a cryptographic chain with previous-event linkage.


## Prototype 6 — Real-Economy Integration Primitives (P6.0–P6.2)

- [real_economy_protocol.py](real_economy_protocol.py) — isolated P6.0 read-only Claim projection and proposition-specific SPER evidence decision; P6.1 in-memory lot inventory, custody/ownership separation, versioned reservations, partial child-lot movement and idempotent commands.
- [test_real_economy_protocol.py](test_real_economy_protocol.py) — focused P6.0–P6.1 invariant tests.
- [SEC/SPER architecture audit](../research/SEC_SPER_INTEGRATION_AUDIT_AND_CONTRACT_V0_1.md) — entity boundaries, state dimensions, evidence semantics and integration constraints.
- [P6.0–P6.1 implementation contract](../research/PROTOTYPE_6_REAL_ECONOMY_INTEGRATION_P6_0_P6_1_V0_1.md) — implementation scope and explicit non-production limitations.
- [P6.2 canonical event bridge and transaction boundary](../research/PROTOTYPE_6_2_CANONICAL_EVENT_BRIDGE_AND_TRANSACTION_BOUNDARY_V0_1.md) — event mapping, aggregate versioning, idempotency, replay, atomicity, outbox/inbox and acceptance tests.

P6.1 remains an isolated in-memory reference and is not synchronized with Stage-B inventory. Do not append its returned events after mutating state as a production integration pattern: state and event persistence must share one transaction (or a deliberately selected event-sourced commit boundary). P6.2 is currently a design contract, not a durable implementation. No inventory-only event automatically posts to the financial ledger.

### P6.2a–P6.2b — Canonical event mapping and in-memory transaction reference

- [real_economy_event_bridge.py](real_economy_event_bridge.py) — validates and enriches P6.1 domain events into a versioned canonical envelope; preserves event/aggregate identity, aggregate version, actor, authority, command/correlation context, UTC timestamps and evidence references. Includes a test-only coordinator that stages candidate state, appends to the existing `synergy_kernel.EventStore`, and rolls back its in-memory event collections if append fails.
- [test_real_economy_event_bridge.py](test_real_economy_event_bridge.py) — contract tests for canonical payload digests, UTC/time validation, required authority, idempotency scope, stale aggregate versions, multi-event ordinals and rollback on injected append failure.

The coordinator is intentionally **single-process, single-writer and non-durable**. All writers must go through that coordinator; direct concurrent writes to the EventStore are outside its safety guarantee. It does not make the current P6.1 mutating `LotInventory` safe to adapt post hoc. Production still requires one durable transaction or an event-sourced commit boundary.


### P6.2c — Canonical event-log integrity audit

- [real_economy_event_replay.py](real_economy_event_replay.py) — audits canonical envelopes already stored in the existing EventStore: schema, identity agreement, payload digest, EventStore envelope digest, aggregate-version progression and per-command event ordinals. Legacy events without a canonical schema marker are counted and left uninterpreted; unknown declared schemas fail closed.
- [test_real_economy_event_replay.py](test_real_economy_event_replay.py) — covers legacy coexistence, valid single/multi-event commands, sequential aggregate versions, payload/envelope tampering, identity mismatch, version gaps, ordinal gaps and unknown schemas.

P6.2c is an integrity/replay audit, **not a business-state reducer**. It cannot reconstruct inventory or legal ownership until every lifecycle event contains a complete, versioned state-transition contract and a reducer is specified. The existing EventStore digest is recomputed for tamper detection but is not a previous-hash chain, authenticated signature, durable audit proof or evidence that an off-chain event actually occurred.


### P6.2d — Atomicity, retry and concurrency fault tests

- `real_economy_event_bridge.py` now rejects invalid aggregate `expected_version` values (including booleans, floats and negatives) and invalid fault-injection indices before executing the transition.
- `test_real_economy_event_bridge.py` adds multi-event rollback after the second append, retry after a failed attempt, transition-exception isolation, strict version/fault-index validation and a two-thread same-version race. The race contract is exactly one commit and one stale-version conflict.

These tests exercise only the in-process coordinator under its own lock. They do not establish cross-process safety, crash durability, or atomicity with an external database; direct EventStore writers remain outside the coordinator's lock and invalidate its single-writer assumption.


### P6.2e — Strict canonical replay-audit validation

- `real_economy_event_replay.py` now validates required actor/authority/correlation metadata, UTC timestamp syntax, positive aggregate versions, non-negative event ordinals, non-empty unique evidence references, globally unique canonical event IDs and idempotency keys, and command-ID consistency across aggregate/version metadata.
- `test_real_economy_event_replay.py` adds adversarial cases for blank actor metadata, non-UTC timestamps, duplicate idempotency keys, command-ID reuse and duplicate evidence references.
- This remains an integrity audit only. It does not reconstruct lot state, restore in-memory receipts, or provide crash recovery; those require a durable persistence boundary and fully specified lifecycle reducers.


## P6.3 — Durable recovery, snapshots and reconciliation contract

- [P6.3 recovery contract](../research/PROTOTYPE_6_3_DURABLE_RECOVERY_SNAPSHOT_AND_RECONCILIATION_CONTRACT_V0_1.md) — defines durable commit records, multi-aggregate version vectors, idempotency receipt recovery, snapshot validation, deterministic reducers, fail-closed recovery, reconciliation states and crash-test gates.
- This is an architecture/acceptance contract, not a persistence implementation. The current EventStore and P6.2 coordinator remain in-memory; no crash durability or state reconstruction is claimed.


### P6.3b — SQLite durable single-aggregate transaction boundary

- [sqlite_event_repository.py](sqlite_event_repository.py) — standard-library SQLite repository. A command commits its canonical P6.2 event envelopes, aggregate projection, immutable idempotency receipt and outbox rows in one `BEGIN IMMEDIATE` transaction. Uses WAL, FULL synchronous mode, foreign keys, busy timeout, uniqueness constraints, projection digests and a fail-closed repository audit.
- [test_sqlite_event_repository.py](test_sqlite_event_repository.py) — exception and real subprocess-termination injection after event/outbox insertion, after projection write, after receipt write, before commit, and after commit but before response; also checks same-key retry, stale versions, at-least-once outbox redelivery, database reopen and tampering.
- SQLite is deliberately scoped to a **single-host** transactional repository. It is not a distributed lock, network-filesystem database, authenticated event chain or broker. Outbox publication is at-least-once; consumers still need a transactional inbox/deduplication receipt.
- This is the first durable P6.3b slice, not completion of P6.3. It supports the existing one-aggregate P6.2 envelope only. P6.3a multi-aggregate inventory command v2, deterministic inventory reducers, genesis/snapshot replay and native adapters for canonical registers remain separate gates. The mutating P6.1 `LotInventory` API is intentionally not wrapped post hoc.

Run the focused durable repository tests:

```bash
python -m unittest discover -s prototype -p 'test_sqlite_event_repository.py' -v
```

### P6.3c — Durable native LotInventory adapter

- [sqlite_lot_inventory_adapter.py](sqlite_lot_inventory_adapter.py) executes the actual P6.1 `LotInventory` domain transitions against the P6.3b SQLite repository. It does not duplicate or weaken owner/authorized-actor checks, lot/reservation version checks, expiry, consume, release, quarantine or stock-reservation invariants.
- The adapter uses one `inventory-book` aggregate root. A consume command that changes the source lot, creates a moved lot and changes a reservation therefore commits all three state changes, the canonical event, command receipt and outbox row atomically.
- This is a deliberate single-root serialization boundary, not P6.3a multi-aggregate v2. It is single-host SQLite; cross-host consensus and independent broker exactly-once delivery are not claimed.
- The adapter persists canonical lot/reservation projections and rehydrates the P6.1 domain object on every command. A durable retry retrieves the original expected aggregate version, so a retry after later commands returns its original receipt rather than being misclassified as stale.
- Each command's final canonical event carries a complete, typed projection delta. Recovery and public reads independently replay those deltas from an empty inventory root, revalidate the stock/reservation invariants after every command and compare the rebuilt state with the persisted projection inside one verified SQLite read snapshot. A changed projection is rejected even if an attacker also rewrites its unkeyed projection digest.
- [test_sqlite_lot_inventory_adapter.py](test_sqlite_lot_inventory_adapter.py) exercises register → reserve → commit → consume → release → quarantine, restart recovery, delayed idempotent retry, unauthorized custodian rejection and rollback/retry after projection-write failure.

Run the focused native adapter tests:

```bash
python -m unittest discover -s prototype -p 'test_sqlite_lot_inventory_adapter.py' -v
```

### P6.3a — Inventory lifecycle event and multi-aggregate command contract

- [P6.3a contract](../research/PROTOTYPE_6_3A_INVENTORY_LIFECYCLE_EVENT_AND_COMMAND_CONTRACT_V0_1.md) defines typed lot/reservation aggregate identities, complete expected-version vectors, command-scoped idempotency, globally contiguous command event ordinals, immutable receipts, and exact event groups for register/reserve/commit/expiry/release/consume/quarantine.
- It explicitly documents why current P6.1 event descriptions are incomplete for replay: reserve/release/expiry/consume mutate multiple aggregates but omit one or more aggregate events; child-lot state is not fully encoded.
- P6.3a is a schema and acceptance contract only. It does not retrofit historical events, implement reducers or durable storage, or change P6.1 runtime behavior. Legacy P6.1 records require explicit migration/checkpoint treatment.


## Repository-wide system audit — 11 November 2026

- [Branch and system audit](../research/REPOSITORY_WIDE_BRANCH_AND_SYSTEM_AUDIT_2026-11-11.md) maps all six visible branches, PR targets, major accounting/event authorities, the unified state vector, cross-register equations, and source-level integration risks.
- It records two concrete source-level defects for remediation: the SFC opening verifier rejects negative positions despite the signed-opening contract/test, and the financial journal adapter accepts a duck-typed caller-supplied validator.
- The audit is explicitly in progress: no local archive/LZMA pass or full repository test run is claimed; exact-head CI remains required.
