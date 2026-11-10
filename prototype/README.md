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

- [cellular_coordination.py](cellular_coordination.py) — Stage-A local-neighbour matching protocol with market, central benchmark, cooperative-pool and cellular regimes.
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

- [scc_dynamic_economy.py](scc_dynamic_economy.py) — seven-cell, multi-period physical economy with endogenous production plans, input recipes, local inventories, raw-resource regeneration, intermediate procurement, final consumption and four coordination regimes.
- [test_scc_dynamic_economy.py](test_scc_dynamic_economy.py) — production, determinism, self-trade, resource stock-flow and paired-regime tests.
- [Stage-B design and limitations](../research/SCCE_CELLULAR_ENGINE_AND_COMPARATIVE_EXPERIMENT_V0_2.md#part-iii--stage-a-kernel-and-its-scope)

Run from the repository root:

```bash
python prototype/scc_dynamic_economy.py --compare --shock none --periods 24 --hops 2
python prototype/scc_dynamic_economy.py --compare --shock compound --periods 24 --hops 2
python prototype/scc_dynamic_economy.py --monte-carlo 20 --shock compound --periods 24 --hops 2 --summary-only
```

Stage B is a physical production-and-consumption layer. It does not yet model money, credit, wages, ownership, capital investment, household income, or measured utility. Fixed-price output and consumption are transparent physical-value indices, not GDP or empirical welfare. The existing seven-cell financial prototype remains unchanged.

## Validation

GitHub Actions runs the prototype test suite and both baseline and compound-crisis simulations when files under prototype/** or the prototype workflow change.

## Scope and limitations

These are research instruments, not production financial software or calibrated forecasts. They do not implement legal accounting standards, banking settlement, identity/access controls, durable transactional storage, concurrency safety, tax, full insolvency law, full national accounts, empirical parameter calibration or a complete institutional comparison.

The seven-cell model has a single representative household cash pool, one shared energy supplier, an external material supplier, fixed prices, simplified capital, a single renewable resource stock and a narrow insolvency trigger. See the model specification for the full limitations and next upgrades.

Passing software tests validates only the tested invariants. It does not validate the SYNERGY economic thesis.

Scenario outputs include a deterministic `event_log_digest` over the ordered event payload digests; it is an integrity checksum, not a cryptographic chain with previous-event linkage.
