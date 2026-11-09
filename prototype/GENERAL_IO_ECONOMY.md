# Prototype 2 — General Input-Output Economy

**Status:** executable research prototype, first implementation  
**Version:** 0.2.0-alpha  
**Implementation:** `io_economy.py`  
**Tests:** `test_io_economy.py`  
**Scope:** multi-product production network, multiple suppliers, household demand, product-level price adjustment, inventories, imports and exact conservation checks.

## 1. Why Prototype 2 exists

Prototype 1 models seven economic cells and a shared energy hub. That is useful as a controlled baseline, but it hard-codes much of the production topology. Prototype 2 generalizes the production network:

- any number of products;
- any number of firms;
- multiple domestic suppliers of the same product;
- each firm produces one principal product and can use any declared input bundle;
- firms and households submit orders to product markets;
- imports are explicit external supply, not domestic production;
- unsatisfied orders remain shortages rather than being silently created;
- prices respond to product-level excess demand and supply;
- all money and physical stocks are reconciled after every period.

Prototype 1 remains unchanged and is still the canonical seven-cell benchmark. Prototype 2 is additive and is intended to run beside it.

## 2. Core entities and data contract

### Product

A product has:
- stable `product_id`;
- physical unit;
- base/reference price;
- import offer price;
- period import capacity;
- demand weight reserved for future priority/rationing experiments.

Prices are monetary per physical unit. A tonne of grain, an MWh of energy and a unit of care are not physically additive.

### Firm

A firm has:
- one principal output product;
- a recipe: input product → physical input coefficient per output unit;
- labour requirement per output unit;
- labour capacity and output capacity;
- wage per labour unit;
- opening cash and product-specific inventories;
- a domestic offer markup relative to the current reference price.

A firm can be a supplier in its output market and a buyer in several input markets. Its input stocks and output stocks coexist in one product-keyed inventory.

### Household

A household has:
- opening cash;
- a basket of desired product quantities;
- a consumption propensity, which limits the budget submitted to markets;
- wage income, consumption and expenditure records.

Households are separate agents rather than one representative pooled account. The initial model still uses a simple equal split of each firm's wage bill across the three synthetic households. This is a placeholder, not a claim about actual employment relationships or fair distribution.

## 3. Production network

Let:
- (f) denote a firm;
- (p(f)) denote its output product;
- (a_{if}) denote units of input product (i) needed per unit of firm (f)'s output;
- (L_f) denote labour capacity;
- (ell_f) denote labour per unit of output;
- (K_f) denote output capacity.

The initial production plan is inventory-targeted: the firm replenishes its own output stock toward a target equal to one period of its configured output capacity, rather than producing at full capacity indefinitely. This is a deliberately simple stock-control rule; it prevents unsold output from accumulating without bound.

```text
planned_output = min(
    output_capacity,
    labour_capacity / labour_per_unit,
    max(0, output_capacity - opening_output_inventory)
)
```

After input markets clear, actual production is limited by available input stocks and the firm's cash available for wages:

```text
actual_output = min(
    planned_output,
    min(input_inventory[i] / recipe_coefficient[i] for each required input i),
    firm_cash / (labour_per_unit * wage_per_labour)
)
```

Here, `input_inventory[i]` is the firm's available stock of input `i`. Actual output is rounded to the model's declared quantity precision.

Inputs are consumed when production occurs. Newly produced goods enter inventories after the current market-clearing round and are therefore offered in the next period. This avoids selling the same physical unit twice within one period.

## 4. Product markets and price formation

For each product, firms submit input orders and households submit consumption orders. The order book is scaled by each buyer's budget so the sum of its orders at reference prices does not exceed its configured spending budget.

Domestic firms offer their opening inventory. The external supplier offers up to the product's import capacity at its import offer price.

For product `i`:

- `D_i`: total requested quantity;
- `S_i(P_i)`: quantity offered at or below the current reference price; higher-ask supply is not treated as immediately available;
- `P_i`: previous reference price;
- `eta`: price adjustment coefficient.

The imbalance signal is based on supply currently offered at or below the reference price. An import offer above that price does not suppress the shortage signal merely because its capacity exists. As the price adjusts upward and reaches the import ask, that import capacity becomes eligible. This avoids the false signal that expensive, currently ineligible supply has already cleared the market.

```text
z_i = clip((D_i - S_i(P_i)) / max(S_i(P_i), epsilon), -1, 1)
proposed_price = P_i * (1 + eta * z_i)
```

The clearing price uses the lowest eligible ask as a floor and a buyer bid ceiling as a cap. Sellers are allocated in ascending ask-price order (merit order); eligible buyers are rationed pro rata if supply is insufficient. The model does not distribute scarce supply pro rata among sellers with different asks.

The price is additionally bounded by the configured maximum one-period price movement, the lowest currently available seller ask and the buyer bid ceiling. All eligible trades for one product execute at one uniform clearing price in this first mechanism.

If offered supply is insufficient, eligible buyers receive pro-rata allocations. Suppliers are used in ascending ask-price order. If a seller cannot offer at the resulting price, its stock remains in inventory. A shortage is reported as desired demand minus actual traded quantity.

**Important:** this is one explicit price-discovery rule, not a universal market law. It is intentionally replaceable. Later experiments should compare auction clearing, continuous double auction, posted prices, bargaining, administered prices, cooperative allocation and hybrid mechanisms under identical initial conditions.

## 5. Accounting identities and invariants

### 5.1 Physical balance by product

```text
opening_stock[i]
+ imports_sold[i]
+ production[i]
= intermediate_inputs_consumed[i]
+ household_consumption[i]
+ closing_stock[i]
```

Intermediate use means physical inputs actually consumed in production, not merely purchases or transfers between firms. Purchased but unused inputs remain in closing inventory.

The model checks this identity for every product after each period. A mismatch raises an exception and stops the simulation.

### 5.2 Cash conservation

The current monetary perimeter is firms + households + the external import supplier. All domestic market payments and wage payments are transfers inside this perimeter; import payments move cash to the external supplier, which is still explicitly included in the consolidated perimeter.

```text
sum(firm_cash)
+ sum(household_cash)
+ external_import_supplier_cash
= initial_system_cash
```

No money is minted in this prototype. No credit principal is created. No unpaid invoice is silently treated as paid. Market purchases settle immediately in cash.

Cent-rounding residuals are allocated to an actual seller in the market settlement, rather than hidden in a synthetic income or issuance line.

### 5.3 No negative cash

A firm or household cannot spend more cash than it holds. The model checks non-negative cash balances after every period.

### 5.4 Internal flows are not new final output

An intermediate sale from one firm to another is not counted as household final consumption. Internal turnover, imports, physical output, household consumption and value-added proxy are reported separately.

## 6. Value-added proxy: strict interpretation

```text
gross_value_added_proxy =
    sum_over_firms(
        output_price * actual_output
        - sum_over_inputs(input_price * input_quantity_consumed)
    )
```

This is an illustrative gross-value-added proxy using current model prices and input quantities consumed. It is **not GDP**, not profit, not household income and not a complete national-accounts measure. It does not yet reconcile taxes, subsidies, inventories at transaction-time prices, capital consumption, mixed income, net operating surplus, own-account production, government and non-market output, or all valuation adjustments.

The result is kept separate from physical output and cash balances.

## 7. Initial synthetic economy

The default network contains seven products:

1. grain;
2. energy;
3. metals;
4. machinery;
5. logistics;
6. food;
7. care.

It contains nine firms, including two grain suppliers and two energy suppliers, and three heterogeneous household cash accounts. Recipes create a connected production graph: farms use energy and logistics; energy producers use metals and machinery; mining uses energy, machinery and logistics; machinery uses metals, energy and logistics; food processing uses grain, energy and logistics; care uses food, energy and logistics.

The parameters are deliberately synthetic. They are designed to exercise the model's mechanisms, not to represent a real country or calibrated technology.

## 8. Scenarios

The executable runner supports:

- `baseline`;
- `demand_collapse`;
- `energy_import_shock`;
- `metals_shortage`;
- `compound_shock`.

Shocks alter demand or external supply conditions while leaving the underlying accounting identities intact. Scenario outcomes must be interpreted as conditional outputs of these assumptions, not forecasts.

Run from the repository root:

```bash
python prototype/io_economy.py --scenario baseline --periods 12
python prototype/io_economy.py --scenario compound_shock --periods 12
python -m unittest discover -s prototype -p 'test_*.py' -v
```

## 9. What this version does not yet implement

The following are deliberately not claimed as completed:

- trade credit, maturity schedules, receivables/payables, default and bankruptcy;
- worker-level employment contracts, household heterogeneity beyond three synthetic agents, and contribution attribution;
- capital accumulation, depreciation, investment goods demand and capacity expansion;
- multiple outputs per firm, joint production, by-products and transformation technologies;
- product quality, geographic transport networks, delivery delays and spoilage;
- strategic bidding, market power, collusion, entry and exit;
- taxes, subsidies, public sector, public goods and non-market output;
- ecological stocks, emissions, water and material-footprint constraints;
- ownership claims, UEP/UOF, SCI, collective dividends and DAO governance;
- stochastic uncertainty, calibration to official supply-use tables or statistical parameter estimation;
- a full double-entry general ledger and legal/accounting compliance.

The next implementation layer should add payment terms and credit as explicit financial contracts, not as a hidden relaxation of cash constraints. A subsequent layer should add capital and ecological constraints. Institutional comparisons should only follow after these accounting and behavioural modules have independent tests.

## 10. Validation and interpretation

The test suite is designed to check:
- deterministic repeatability;
- multiple suppliers per product;
- cash conservation;
- physical stock conservation product by product;
- non-negative cash;
- valid product references;
- scenario execution;
- separate reporting of production, imports and shortages;
- household expenditure as a period flow rather than a cumulative stock.

Passing these tests establishes only that the tested software invariants hold for tested paths. It does not validate the model's behavioural assumptions, parameters, fairness, efficiency or the broader SYNERGY hypothesis.

## 11. Methodological anchors

The product-by-product and industry-by-industry distinction, the separation of intermediate use from final use, and the supply/use balance follow the general logic of supply-use and input-output accounting. This prototype is not a national-accounts implementation.

- [Eurostat — ESA supply, use and input-output tables methodology](https://ec.europa.eu/eurostat/web/esa-supply-use-input-tables/methodology)
- [OECD / European Union — Handbook on Extended Supply and Use Tables and Extended Input-Output Tables (2025)](https://www.oecd.org/en/publications/handbook-on-extended-supply-and-use-tables-and-extended-input-output-tables_e9fdcf85-en/full-report/what-are-extended-supply-and-use-tables-and-why-are-they-useful_f47a82e1.html)
- [UN Statistics Division — Handbook on Supply, Use and Input-Output Tables with Extensions and Applications](https://unstats.un.org/unsd/nationalaccount/capdev/resources/details?resourceid=36&resourcetype=handbook)
