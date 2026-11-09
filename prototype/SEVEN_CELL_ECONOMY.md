# Prototype 1 — Seven-Cell Economy

**Version:** 0.1.0  
**Status:** Executable deterministic research prototype; illustrative parameters; not calibrated or empirically validated.

## 1. Purpose and system boundary

This prototype turns the Volume V model into a runnable seven-cell economy. It includes physical production, household demand, a shared energy supplier, paid external material inputs, investment, maintenance, member distributions, bounded bilateral trade credit, arrears, an insolvency trigger, ecological regeneration and double-entry journals.

The model is intentionally small and inspectable. It is not designed to make SYNERGY win by construction. Its parameter values are synthetic and must not be interpreted as forecasts or policy recommendations.

## 2. The seven cells

| Cell | Sector | Function |
|---|---|---|
| cell-1 | Food | Final household goods |
| cell-2 | Materials | Final household goods |
| cell-3 | Energy | Shared energy supplier to the other six cells |
| cell-4 | Machinery | Final household goods |
| cell-5 | Logistics | Final household goods |
| cell-6 | Software | Final household goods |
| cell-7 | Care | Final household goods |

Cells differ in labour, productivity, capacity, energy and material intensity, prices, initial cash and input stocks, inventory, credit limits and reserve targets.

## 3. State variables

Each cell tracks cash, material inventory, energy inventory, unsold output inventory, productive-capital index, trade-credit receivables and payables, current and cumulative output, wages, investment, external sales, arrears and insolvency state. The household sector has its own cash balance. External suppliers receive payments for materials, maintenance and capital goods.

## 4. Production function

For each non-energy cell, planned output is constrained by demand, inventory, capacity, labour productivity and available inputs:

\[
q_{i,t}^{plan}=\min\left(\bar q_i,\;L_i A_i K_{i,t},\;\frac{M_{i,t}}{a_i},\;\frac{E_{i,t}}{b_i e_{i,t}},\;D_{i,t}+I_i^*-I_{i,t}\right)_+
\]

Here, (L) is labour, (A) productivity, (K) the capital index, (M) materials, (E) energy, (a) and (b) input coefficients, (e) an energy-intensity shock, (D) final demand, and (I^*) a target inventory buffer.

The energy cell plans output against the derived energy requirements of the other cells plus a small buffer. Actual production is scaled to the shared resource extraction allowance.

The shared resource stock evolves as:

\[
R_{t+1}=\max(0,R_t+g-r\sum_i q_{i,t})
\]

where (g) is regeneration and (r) is resource intensity. This is a single stylized renewable stock, not a model of a particular ecosystem.

## 5. Input-market simplifications

- Cell-3 is the dedicated energy hub. It supplies the six other cells through internal sales.
- Material inputs are purchased from an external supplier at a declared price.
- The model does not yet contain a general input-output matrix, alternative suppliers, logistics constraints or endogenous market clearing.
- The energy hub is a deliberate first simplification; the next version should replace it with a multi-node production network.

Material purchases are paid, not free endowments. Energy sales are internal intermediate transactions and are reported separately from final household expenditure.

## 6. Household budget and final demand

Households begin with a declared cash endowment, receive paid wages and collective distributions, and pay for final goods:

\[
H_{t+1}=H_t+W_t+Div_t-C_t
\]

Aggregate final orders are rationed proportionally if household cash is insufficient. Sales to households are the final-demand measure. Internal energy sales must not be added to final expenditure: doing so would double-count an intermediate input.

## 7. Money, credit and accounting

### Cash conservation

The model tracks cash held by cells, households and external suppliers. In the absence of monetary issuance or destruction:

\[
\sum_i Cash_{i,t}+H_t+S_t=\text{constant}
\]

Wages, purchases, material imports, maintenance, investment and distributions move cash between modelled sectors. Internal cash transfers cancel on consolidation.

### Bilateral trade credit

A seller may extend credit only within the remaining capacity of both parties. Issuance creates a matching receivable and payable; it does not create cash or income. Each debtor-creditor position is stored separately. Repayment reduces the actual bilateral position, not an arbitrary network-wide net balance. Interest accrual increases the same debtor's liability and creditor's receivable.

### Insolvency

The prototype marks a cell insolvent only when both conditions hold:
- wage arrears persist for at least two periods;
- payables exceed a configured share of its credit limit.

There is no automatic bailout. This is a testable software trigger, not a legal definition of insolvency. Maturity schedules, collateral, creditor priority, restructuring and recovery are not yet modelled.

### Journal

Every entry must balance exactly. The journal covers opening cash, wages, household purchases, internal settlements, credit issuance and repayment, interest, material imports, maintenance, investment and member distributions. A balanced journal is necessary but does not establish that the model's economic assumptions are correct.

## 8. Period sequence

1. Regenerate the shared resource and set the extraction allowance.
2. Plan non-energy production from demand, inventories, capacity and opening inputs.
3. Plan energy production from derived cell energy requirements.
4. Scale production to the shared resource constraint and consume inputs.
5. Pay available wages; unpaid obligations become arrears.
6. Sell energy from cell-3 to other cells using cash or bounded bilateral credit.
7. Replenish material inputs through paid external purchases.
8. Execute household final purchases subject to the household cash budget.
9. Pay maintenance and invest above reserve targets.
10. Repay bilateral credit and accrue interest on outstanding positions.
11. Make permitted collective distributions.
12. Apply the insolvency trigger and reconcile journals, credit positions, stocks and cash.

The sequence itself is an assumption. Alternative timing conventions must be tested later.

## 9. Benchmark scenarios

All five scenarios start from the same seven-cell configuration and run for 24 periods.

| Scenario | Treatment |
|---|---|
| baseline | No exogenous shock |
| demand_collapse | Temporary demand decline in machinery, logistics and software |
| energy_shock | Temporary increase in energy intensity for selected cells |
| resource_shock | Temporary reduction in the shared resource extraction allowance |
| compound_crisis | Combined demand, energy-intensity and resource shocks |

The scenario results are saved in `results/seven_cell_scenario_comparison.json`. Shocks are deterministic stress tests, not probability estimates.

## 10. First run: illustrative results

| 24-period metric | Baseline | Compound crisis |
|---|---:|---:|
| Non-energy physical output index | 2,625.60 | 2,502.49 |
| Final household expenditure | 13,640.24 | 12,915.53 |
| Net value-added proxy | 12,833.88 | 12,174.64 |
| Ending resource stock | 1,638.40 | 1,685.65 |
| Ending cash Gini across cells | 0.3502 | 0.3665 |
| Insolvent cells | 0 | 0 |
| System cash conservation error | 0.00 | 0.00 |

The compound crisis reduces the non-energy output index by approximately 4.69%, final household expenditure by 5.31%, and the net value-added proxy by 5.14% relative to the baseline under these specific parameters. This is a model response, not evidence about real economies.

The `net_value_added_proxy` is defined narrowly as final household expenditure minus external material-input cost. It is **not GDP**: the prototype omits taxes, government, depreciation accounting, full inventories, many intermediate sectors, imported energy services and a complete national-accounting boundary.

The gross physical output index sums stylized units across sectors, including energy. Since unlike physical units are not inherently additive, report non-energy output and energy output separately. Do not interpret the unweighted total as real aggregate output.

## 11. Running the model

From the `prototype/` directory:

```bash
python seven_cell_economy.py --scenario baseline --periods 24
python seven_cell_economy.py --scenario compound_crisis --periods 24 --output results/compound_crisis.json
python -m unittest discover -s . -p 'test_*.py' -v
```

Supported scenario names: `baseline`, `demand_collapse`, `energy_shock`, `resource_shock`, `compound_crisis`.

## 12. Known limitations and next upgrades

1. One representative household cash pool; no heterogeneous household needs, incomes or consumption baskets.
2. One shared energy supplier and one external material supplier.
3. Fixed prices; no endogenous price formation, bargaining, markups or inflation.
4. Fixed labour; no labour matching, unemployment choice, training or migration.
5. Capital is an index; no depreciation schedule, asset registry, collateral valuation or replacement lifecycle.
6. One renewable resource stock; no local ecosystems, pollution or threshold dynamics.
7. Credit has no contractual maturity calendar; repayment is deterministic by bilateral position.
8. Insolvency is a simple trigger; no legal procedure or recovery waterfall.
9. Distribution is a cash-pool rule, not the full UEP/UOF and ownership architecture.
10. No federations, governance voting, entry/exit, mergers, cell splits or AI policy agent.
11. Parameters are illustrative and uncalibrated; shocks are not probability estimates.
12. No Monte Carlo replications or confidence intervals; this is deterministic software validation only.

### Next version

- Heterogeneous household agents and multiple consumption baskets.
- General input-output network and capacity-constrained market clearing.
- Endogenous prices, payment terms and maturity-aware credit.
- Full sectoral balance sheets, income statements and consolidated accounting.
- Fairly matched institutional baselines with identical endowments and information.
- Seeded Monte Carlo replications, parameter sweeps, confidence intervals and sensitivity analysis.
- Explicit depreciation, ecological stocks, maintenance and social-capability outcomes.

**Interpretation rule:** passing tests validates only the tested software invariants, not the SYNERGY institutional thesis.
