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
- [scc_endogenous_household_economy.py](scc_endogenous_household_economy.py) — C2-A2 in-loop household delivery: current household needs plus a bounded essential backlog feed into each household's own cell demand in the next period; physical deliveries are allocated to households and reconciled product-by-product.
- [test_scc_endogenous_household_economy.py](test_scc_endogenous_household_economy.py) — checks zero-backlog equivalence to Stage B, household delivery reconciliation, backlog caps and the effect of allocation rules on household outcomes.
- [Stage-C2 research design](../research/SCCE_STAGE_C2_ENDOGENOUS_HOUSEHOLD_ECONOMY_V0_1.md) — specifies the remaining endogenous household–cell feedback, voluntary time, income/ownership interfaces and comparative welfare experiments.

C2-A1 is deliberately a controlled bridge: it makes household profiles the explicit source of cell demand but preserves aggregate demand and Stage-B physical outcomes exactly. C2-A2 adds an in-loop household delivery and bounded essential-backlog feedback into the next period's own-cell demand. This is still a synthetic physical model; household labour, income, ownership, money and credit remain unimplemented.

## Validation

GitHub Actions runs the prototype test suite and both baseline and compound-crisis simulations when files under prototype/** or the prototype workflow change.

## Scope and limitations

These are research instruments, not production financial software or calibrated forecasts. They do not implement legal accounting standards, banking settlement, identity/access controls, durable transactional storage, concurrency safety, tax, full insolvency law, full national accounts, empirical parameter calibration or a complete institutional comparison.

The seven-cell model has a single representative household cash pool, one shared energy supplier, an external material supplier, fixed prices, simplified capital, a single renewable resource stock and a narrow insolvency trigger. See the model specification for the full limitations and next upgrades.

Passing software tests validates only the tested invariants. It does not validate the SYNERGY economic thesis.

Scenario outputs include a deterministic `event_log_digest` over the ordered event payload digests; it is an integrity checksum, not a cryptographic chain with previous-event linkage.
