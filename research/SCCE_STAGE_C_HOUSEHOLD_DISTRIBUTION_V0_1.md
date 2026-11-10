# SCCE Stage C1 — Household-Level Physical Distribution

**Date:** 10 November 2026  
**Version:** 0.1  
**Status:** Executable money-free distribution kernel with a tested post-hoc Stage-B bridge; household decisions do not yet feed back into production planning  
**Implementation:** \`prototype/household_distribution.py\`  
**Tests:** \`prototype/test_household_distribution.py\`

---

## 1. Why Stage C1 is necessary

Stage B measures final consumption at the level of an economic cell. That is not enough to determine whether households inside the same cell receive goods fairly or whether essential needs are protected.

A cell can report 80% aggregate food fulfilment while one household receives all its food and another receives almost none. Cell averages hide this distribution. Stage C1 adds households as explicit agents without prematurely adding wages, money, ownership income or credit.

The module answers a narrow physical question:

> Given a quantity of goods already available inside a cell, how should that cell distribute those goods among its own households, and what distributional outcomes result?

It does not decide how goods move between cells. It does not create goods. It does not claim that a synthetic fulfilment metric is human welfare.

## 2. Household state

A household is represented by:
- stable household identifier;
- home economic cell;
- essential needs by product;
- discretionary needs by product;
- essential-need priority;
- discretionary-need priority.

Essential and discretionary claims are separate even when they concern the same product. This allows the rule to protect a minimum food requirement before distributing additional food as discretionary consumption.

The current model does not infer household need from protected personal attributes. Priority is an explicit synthetic model parameter and must not be interpreted as a measure of a person's worth. Product classification is also synthetic: Stage B currently labels food, care, machinery, logistics and software as final-demand outputs. Stage C1 treats food and care as essential and the remaining declared final-demand products as discretionary only for this prototype. A calibrated household basket must reclassify capital equipment and business services rather than assume that every Stage-B final-demand product is ordinary household consumption. The experiment uses a reproducible synthetic household panel; the default priority dispersion is 0.4 around a common baseline, not an empirical estimate.

## 3. Distribution boundary

The input is a map of available physical stocks by cell and product:

\[
S_{c,p}\geq 0
\]

Each household belongs to exactly one cell. Its consumption can draw only on the stock assigned to that cell. The module does not silently pool inventories across the network.

For every cell \(c\) and product \(p\):

\[
\sum_{h\in H_c}
(x^{E}_{h,p}+x^{D}_{h,p})
\leq S_{c,p}
\]

For each household:

\[
0\leq x^{E}_{h,p}\leq N^{E}_{h,p}
\]

\[
0\leq x^{D}_{h,p}\leq N^{D}_{h,p}
\]

where \(E\) denotes essential needs and \(D\) discretionary needs.

## 4. Allocation rules

Three transparent rules are implemented.

### 4.1 Proportional rationing

If available stock is below total claims in a category, every household receives the same fraction of its declared claim:

\[
x_h=N_h\cdot\min\left(1,\frac{S}{\sum_jN_j}\right)
\]

This is a neutral benchmark. It does not distinguish vulnerability or urgency.

### 4.2 Priority-weighted max-min rationing

The second rule uses declared positive priority weights. It allocates scarce quantities in proportion to priority until a household's claim is met, then redistributes the remaining stock among unsatisfied claims.

This is not automatically fair. The weights are policy parameters; they must be justified, disclosed and sensitivity-tested. The algorithm must never use them to remove basic rights or to value people.

### 4.3 Floor-priority rationing

The third rule reserves a configurable fraction of every household's essential claim before distributing the remaining essential stock by priority weights. The default floor fraction is 0.5.

If available stock covers all declared floors, every household receives at least that fraction of its essential claim before the residual stock is priority-allocated. If stock is below the sum of floor claims, the floor claims themselves are rationed proportionally. The rule therefore cannot guarantee an absolute floor when physical supply is insufficient.

This is a minimum-protection experiment, not a claim that 50% is the correct social minimum. The fraction must be disclosed, sensitivity-tested and subject to member governance.

### 4.4 Essential-first sequence

For each cell and product:
1. allocate essential claims using the selected essential rule;
2. subtract the physical quantity served;
3. allocate remaining stock to discretionary claims.

This is a transparent sequencing rule, not a claim that all real goods are substitutable or that every essential need can be represented by a simple quantity.

## 5. Outcome vector

The module reports:
- aggregate essential fulfilment;
- aggregate overall fulfilment;
- household-level essential and overall fulfilment;
- minimum household essential fulfilment;
- lower-decile household essential fulfilment;
- Gini inequality of household fulfilment rates;
- per-product essential fulfilment.

The lower-decile metric is a nearest-rank statistic in this prototype. It is not a confidence interval and should be accompanied by the full household distribution in larger experiments.

No composite score is used as the verdict. A high mean can coexist with a severe lower-tail shortfall.

## 6. Invariants

The executable validator checks:
1. every household receives only within its own cell;
2. total allocations do not exceed the cell's stock;
3. no essential allocation exceeds declared essential need;
4. no discretionary allocation exceeds declared discretionary need;
5. the allocation set contains each household exactly once;
6. negative supply and negative need are rejected.

The test suite also checks that priority-weighted allocation changes the distribution while conserving the same physical stock, that the same household panel persists when period demand scales, and that the Stage-B bridge reconciles aggregate household demand and consumption to the cell-level physical records.

## 7. Integration with Stage B

The module remains separate from Stage-B production and matching, but a tested data bridge now exists. Stage B exposes per-cell final demand and per-cell physical consumption in each `PeriodResult`. The bridge in `prototype/scc_household_bridge.py` constructs reproducible synthetic household profiles whose product totals exactly reconcile to each cell's Stage-B demand, then allocates the already-consumed Stage-B quantities to those households. It checks total demand, total physical consumption and essential food/care service against Stage B.

The Stage-B Monte Carlo summary now calls the horizon bridge and reports household-level cumulative essential/overall fulfilment, lower-decile and minimum household essential fulfilment, household fulfilment Gini, mean period lower-tail metrics and the worst-period household minimum. Its default reporting panel uses five synthetic households per cell, proportional rationing and zero priority dispersion. This adds distributional observability to the four economic-regime comparisons without changing their physical production or trade decisions.

The separate Stage-C1 rationing experiment uses ten synthetic households per cell and a declared priority dispersion of 0.4. For each seed and economic regime, it simulates the Stage-B world once, then applies proportional, priority-weighted and essential-floor-first allocation to the exact same per-cell consumed quantities and the same persistent household panel. Paired differences therefore isolate the post-hoc rationing rule; they do not measure a production response to household distribution.

The integration preserves the boundary:
- Stage B determines what goods reach each cell and records cell-level consumption;
- Stage C1 splits those same quantities among the cell's households;
- neither layer creates physical quantities;
- household disaggregation is not counted as an inter-cell trade or a second delivery;
- aggregate household quantities must reconcile exactly to the Stage-B cell totals.

`prototype/scc_household_experiment.py` compares proportional and priority-weighted rationing using a persistent synthetic household panel across all periods. It reports cumulative-horizon household fulfilment alongside mean-period lower-decile fulfilment, mean-period minimum fulfilment, inequality and worst-period minimum fulfilment. Thus the cumulative measure does not conceal the timing of shortages; period-level tail metrics remain visible. Full in-loop household demand feedback into Stage-B production planning is not yet implemented.

Experiments should compare:
- proportional versus priority-weighted versus essential-floor-first distribution;
- sensitivity to the 50% essential floor and priority dispersion;
- different essential floors;
- homogeneous versus heterogeneous household needs;
- cell-level versus household-level inequality;
- distribution under supply shocks and network fragmentation.

## 8. Preliminary paired household-distribution results

The CI experiment ran 20 paired seeds, 24 periods, the compound shock, two-hop cellular reach, ten synthetic households per cell and priority dispersion 0.4. For each seed and economic regime, Stage B was simulated once. Proportional and priority-weighted household rationing then received the exact same per-cell physical consumption and persistent household panel.

| Stage-B regime | Overall fulfilment (both rules) | Essential fulfilment (both rules) | Household lower-decile essential fulfilment: proportional | Priority-weighted | Household minimum: proportional | Priority-weighted | Essential-fulfilment Gini: proportional | Priority-weighted |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Cellular | 46.21% | 42.64% | 31.26% | 23.75% | 29.65% | 17.09% | 0.2411 | 0.2946 |
| Central | 47.04% | 44.27% | 11.18% | 11.58% | 8.37% | 7.56% | 0.4727 | 0.4773 |
| Cooperative | 51.99% | 45.50% | 31.81% | 27.79% | 28.77% | 20.71% | 0.1844 | 0.2055 |
| Market | 47.63% | 46.57% | 3.54% | 3.56% | 2.18% | 2.14% | 0.4348 | 0.4356 |

The aggregate fulfilment columns are unchanged by household rationing, as they must be: both rules distribute the same already-consumed physical quantities. The household lower tail, minimum and Gini can nevertheless change substantially.

Paired priority-weighted-minus-proportional differences:

| Regime | Lower-decile essential fulfilment | Minimum household essential fulfilment | Essential-fulfilment Gini |
|---|---:|---:|---:|
| Cellular | −7.50 pp (95% CI −8.08 to −6.93) | −12.56 pp (−13.33 to −11.79) | +0.0535 (+0.0504 to +0.0567) |
| Central | +0.40 pp (+0.32 to +0.48) | −0.81 pp (−0.91 to −0.71) | +0.0046 (+0.0034 to +0.0057) |
| Cooperative | −4.02 pp (−4.33 to −3.72) | −8.06 pp (−8.71 to −7.41) | +0.0258 (+0.0238 to +0.0277) |
| Market | +0.016 pp (+0.002 to +0.030) | −0.035 pp (−0.070 to +0.001) | +0.00074 (+0.00044 to +0.00105) |

**Interpretation.** In this synthetic sample, the market regime has the highest aggregate essential fulfilment (46.57%) but the weakest household lower decile (3.54%). The cooperative regime has the highest overall fulfilment (51.99%) and a much stronger lower-decile result (31.81%) under proportional rationing. Cellular is close to the cooperative lower tail (31.26%) but has lower aggregate essential fulfilment (42.64%). These comparisons expose a real distinction between aggregate service and the distribution of that service; they do not establish a real-world ranking.

The priority-weighted rule does not improve aggregate consumption. With random priority weights drawn independently of household need, it substantially worsens the cellular and cooperative lower tails and increases their inequality. This is a warning against arbitrary priority scores, not evidence that all needs-based priority rules are harmful. Priority must be grounded in explicit, auditable need criteria, not demographic proxies or a score of human worth.

The experiment is post-hoc: it cannot change production, trade, employment or total output. Its household profiles are synthetic and not calibrated to survey data. The 95% intervals are normal-approximation intervals across 20 seeds. The results are exploratory and must not be represented as measured human welfare.

## 9. Limitations and next work

Not yet implemented:
- household income, wages, transfers, ownership income or purchasing power;
- time use, employment, care work and household production;
- household migration or membership changes;
- quality, perishability, storage and substitution between products;
- public services and shared goods;
- privacy-preserving household data governance;
- appeals, member voting and democratic control of distribution rules;
- calibrated household survey or administrative data.

The module is a physical distribution kernel, not a complete household economy. It should be integrated only after the invariants remain valid across larger synthetic populations and stress scenarios.

---

**Decision:** Stage C1 makes household-level distribution observable without pretending that cell-level consumption is equal to household welfare. This closes one important measurement gap in SCCE, while leaving monetary, institutional and empirical layers explicitly open.
