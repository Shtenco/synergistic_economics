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

The current model does not infer household need from protected personal attributes. Priority is an explicit synthetic model parameter and must not be interpreted as a measure of a person's worth. The experiment uses a reproducible synthetic household panel; the default priority dispersion is 0.4 around a common baseline, not an empirical estimate.

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

Two transparent rules are implemented.

### 4.1 Proportional rationing

If available stock is below total claims in a category, every household receives the same fraction of its declared claim:

\[
x_h=N_h\cdot\min\left(1,\frac{S}{\sum_jN_j}\right)
\]

This is a neutral benchmark. It does not distinguish vulnerability or urgency.

### 4.2 Priority-weighted max-min rationing

The second rule uses declared positive priority weights. It allocates scarce quantities in proportion to priority until a household's claim is met, then redistributes the remaining stock among unsatisfied claims.

This is not automatically fair. The weights are policy parameters; they must be justified, disclosed and sensitivity-tested. The algorithm must never use them to remove basic rights or to value people.

### 4.3 Essential-first sequence

For each cell and product:
1. allocate essential claims;
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

The separate Stage-C1 rationing experiment uses ten synthetic households per cell and a declared priority dispersion of 0.4. For each seed and economic regime, it simulates the Stage-B world once, then applies proportional and priority-weighted allocation to the exact same per-cell consumed quantities and the same persistent household panel. The paired difference therefore isolates the post-hoc rationing rule; it does not measure a production response to household distribution.

The integration preserves the boundary:
- Stage B determines what goods reach each cell and records cell-level consumption;
- Stage C1 splits those same quantities among the cell's households;
- neither layer creates physical quantities;
- household disaggregation is not counted as an inter-cell trade or a second delivery;
- aggregate household quantities must reconcile exactly to the Stage-B cell totals.

`prototype/scc_household_experiment.py` compares proportional and priority-weighted rationing using a persistent synthetic household panel across all periods. It reports cumulative-horizon household fulfilment alongside mean-period lower-decile fulfilment, mean-period minimum fulfilment, inequality and worst-period minimum fulfilment. Thus the cumulative measure does not conceal the timing of shortages; period-level tail metrics remain visible. Full in-loop household demand feedback into Stage-B production planning is not yet implemented.

Experiments should compare:
- proportional versus priority-weighted distribution;
- different essential floors;
- homogeneous versus heterogeneous household needs;
- cell-level versus household-level inequality;
- distribution under supply shocks and network fragmentation.

## 8. Limitations and next work

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
