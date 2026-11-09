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

## Prototype 3 — Unified Economic Balance (UEB)

- [unified_accounts.py](unified_accounts.py) — двойная запись, физические остатки, финансовые требования, консолидация, кредит, токен-обязательства и сверка запасов/потоков.
- [Спецификация UEB](UNIFIED_ECONOMIC_BALANCE.md) — контуры учета, тождества, правила консолидации, границы реализации и следующие этапы.
- [test_unified_accounts.py](test_unified_accounts.py) — тесты баланса проводок, кредита, токенов, физических запасов, требований и добавленной стоимости.

Запуск из корня репозитория:

```bash
python -m unittest prototype.test_unified_accounts -v
```

Первая версия — учетный каркас, а не полная система национальных счетов, юридического титула или финансовой отчетности. Полный перечень ограничений приведен в спецификации.

## Validation

GitHub Actions runs the prototype test suite and both baseline and compound-crisis simulations when files under prototype/** or the prototype workflow change.

## Scope and limitations

These are research instruments, not production financial software or calibrated forecasts. They do not implement legal accounting standards, banking settlement, identity/access controls, durable transactional storage, concurrency safety, tax, full insolvency law, full national accounts, empirical parameter calibration or a complete institutional comparison.

The seven-cell model has a single representative household cash pool, one shared energy supplier, an external material supplier, fixed prices, simplified capital, a single renewable resource stock and a narrow insolvency trigger. See the model specification for the full limitations and next upgrades.

Passing software tests validates only the tested invariants. It does not validate the SYNERGY economic thesis.

Scenario outputs include a deterministic `event_log_digest` over the ordered event payload digests; it is an integrity checksum, not a cryptographic chain with previous-event linkage.
