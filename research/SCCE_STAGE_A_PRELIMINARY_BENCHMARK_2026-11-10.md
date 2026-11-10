# SCCE Stage-A Preliminary Comparative Benchmark

**Date:** 10 November 2026  
**Version:** 0.2 — updated after central min-cost-flow implementation  
**Status:** 100-seed synthetic mechanism results; not empirical evidence and not a test of the complete SCCE economy  
**Engine:** \`prototype/cellular_coordination.py\`  
**Design:** paired comparisons across four allocation regimes on identical seven-cell worlds

---

## 1. Purpose

This report records the reproducible Stage-A comparison of local cellular matching against stylized market, centralized and cooperative allocation rules. It identifies the effects of local reach and the distribution of shortages.

Stage A is an allocation test over already existing stocks. It does **not** test production, investment, wages, household income or the creation of real wealth. Stage B is the separate dynamic physical-economy prototype.

The report supersedes the first Stage-A results because the central comparator was upgraded from a greedy priority allocator to a global min-cost-flow solver for the linear service-value-minus-route-cost objective. The four institutional labels remain stylized mechanisms, not complete models of actual economic systems.

## 2. Experiment design

Each synthetic world contains seven cells, three product classes (food, materials and energy), heterogeneous supplies, demands and need-priority weights, and a sparse inter-cell network. Every regime receives the same world for a given seed.

Four allocation regimes:
- **Market:** global bilateral price/bid matching with synthetic priority-linked bids.
- **Central:** full-information min-cost-flow allocation maximizing weighted served quantity less route cost, subject to seller stock and buyer demand.
- **Cooperative:** common-pool, priority-weighted max-min rationing, followed by nearest-supplier delivery.
- **Cellular:** repeated local request/response rounds; a buyer can contact only suppliers within the configured hop radius.

Before external matching, each cell's own stock is netted against its own need. Own-use is not recorded as a fictitious trade. The cellular algorithm uses repeated local request rounds; unfilled buyers may approach another supplier in a later round.

Each reported mean is based on 100 deterministic paired seeds. The confidence intervals are 95% normal-approximation intervals for the mean. Paired-difference intervals compare each regime with the market arm using the same seed and initial world.

## 3. Metric definitions and limitations

- **Fulfilment:** served physical units divided by requested units.
- **Weighted fulfilment:** served units weighted by the cell's synthetic need-priority parameter, divided by weighted demand.
- **Lower-cell fulfilment:** minimum cell-level fulfilment ratio.
- **Cell fulfilment Gini:** inequality in the seven cell-level fulfilment ratios.
- **Logistics cost:** allocated quantity multiplied by route hops and synthetic per-hop cost.
- **Coordination cost:** fixed synthetic cost per executed buyer-seller-product allocation.
- **Net service score:** weighted service quantity less logistics and coordination costs.

The net service score is an uncalibrated diagnostic index. Its components are not empirically monetized. The central min-cost-flow solver optimizes weighted service less route cost; it does not optimize the fixed coordination charge. The score is not GDP, income, profit, utility, consumer surplus or measured human welfare.

The market comparator has synthetic bids and no buyer cash budgets, strategic bidding, market power, entry/exit or inventory finance. The cooperative comparator is a stylized max-min pool, not a full cooperative governance model.

## 4. Baseline: no shock

100 paired seeds.

| Regime | Hops | Fulfilment | 95% CI | Weighted fulfilment | Lowest cell | Cell Gini | Unmet units | Net service score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Market | Global | 66.21% | 65.74–66.68% | 64.91% | 57.03% | 0.0491 | 35.217 | 94.106 |
| Central min-cost flow | Global | 66.21% | 65.74–66.68% | 64.91% | 57.03% | 0.0491 | 35.217 | 94.138 |
| Cooperative pool | Global | 66.21% | 65.74–66.68% | 64.91% | 57.03% | 0.0491 | 35.217 | 94.137 |
| Cellular | 1 | 56.46% | 55.94–56.98% | 56.47% | 29.24% | 0.1486 | 45.400 | 82.437 |
| Cellular | 2 | 66.21% | 65.74–66.68% | 64.91% | 57.03% | 0.0491 | 35.217 | 93.991 |

**Finding:** one-hop locality leaves substantial demand unmet even though usable supply exists elsewhere in the connected network. Two-hop cellular matching closes the aggregate fulfilment gap in this topology. Its net service score remains slightly below the global comparators because the current local protocol incurs more synthetic coordination cost and route cost.

The global market, central and cooperative arms serve the same aggregate quantity in this baseline because aggregate supply is the binding constraint; they differ only slightly in route and distribution outcomes.

## 5. Compound shock

The shock combines increased food demand with reduced energy supply.

| Regime | Hops | Fulfilment | 95% CI | Weighted fulfilment | Lowest cell | Cell Gini | Unmet units | Net service score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Market | Global | 56.70% | 55.99–57.40% | 56.08% | 31.26% | 0.1408 | 48.982 | 89.811 |
| Central min-cost flow | Global | 56.70% | 55.99–57.40% | 56.08% | 31.19% | 0.1406 | 48.982 | 89.880 |
| Cooperative pool | Global | 56.70% | 55.99–57.40% | 55.40% | 42.88% | 0.0948 | 48.982 | 88.504 |
| Cellular | 1 | 50.01% | 49.25–50.78% | 49.63% | 17.64% | 0.1979 | 56.543 | 80.065 |
| Cellular | 2 | 56.70% | 55.99–57.40% | 55.35% | 42.83% | 0.0955 | 48.982 | 88.380 |

**Finding:** two-hop cellular matching closes the aggregate fulfilment gap, and its minimum-cell fulfilment and Gini are close to the cooperative pool. It does not achieve the highest weighted fulfilment or net service score. One-hop matching remains materially worse.

## 6. Supply crisis

A reduction in available energy supply:

| Regime | Hops | Fulfilment | 95% CI | Weighted fulfilment | Lowest cell | Cell Gini | Unmet units | Net service score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Market | Global | 50.65% | 49.93–51.36% | 49.75% | 28.42% | 0.1732 | 51.521 | 71.736 |
| Central min-cost flow | Global | 50.65% | 49.93–51.36% | 49.75% | 28.44% | 0.1717 | 51.521 | 71.790 |
| Cooperative pool | Global | 50.65% | 49.93–51.36% | 48.97% | 37.06% | 0.1159 | 51.521 | 70.227 |
| Cellular | 2 | 50.65% | 49.93–51.36% | 48.95% | 36.55% | 0.1182 | 51.521 | 70.229 |

**Finding:** aggregate fulfilment is identical because the same physical supply constraint binds. The cooperative and cellular rules distribute the shortage more evenly across cells, at the cost of lower weighted fulfilment and a lower current net service score.

## 7. Demand surge

A 45% increase in food demand:

| Regime | Hops | Fulfilment | 95% CI | Weighted fulfilment | Lowest cell | Cell Gini | Unmet units | Net service score |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Market | Global | 64.77% | 64.26–65.28% | 63.38% | 51.06% | 0.0713 | 42.238 | 109.788 |
| Central min-cost flow | Global | 64.77% | 64.26–65.28% | 63.38% | 51.06% | 0.0713 | 42.238 | 109.824 |
| Cooperative pool | Global | 64.77% | 64.26–65.28% | 63.37% | 51.19% | 0.0706 | 42.238 | 109.800 |
| Cellular | 2 | 64.77% | 64.26–65.28% | 63.36% | 51.17% | 0.0713 | 42.238 | 109.530 |

**Finding:** with this demand shock, all four rules serve the same aggregate quantity. Differences in weighted fulfilment, distribution and the synthetic net score are small.

## 8. Paired differences and interpretation

The most robust Stage-A result is not a claim of institutional superiority. It is the strong locality penalty at one hop:
- baseline one-hop cellular fulfilment is about **9.75 percentage points below** the market arm;
- compound-shock one-hop cellular fulfilment is about **6.68 points below** the market arm;
- two-hop cellular matching closes the aggregate fulfilment gap in both cases;
- under compound and supply shocks, two-hop cellular and cooperative allocation distribute shortages more evenly than market/central allocation.

In the baseline scenario, two-hop cellular fulfilment is statistically indistinguishable from the global arms, but its paired net service score is lower by about 0.115 synthetic units versus market. Under compound shock, cellular two-hop net service is lower than market by about 1.431 units, while the Gini is lower by about 0.045. These are trade-offs in the diagnostic metric, not welfare conclusions.

## 9. What can and cannot be concluded

### Supported by this prototype
1. The local request/response algorithm executes deterministically.
2. It respects aggregate supply and demand bounds in the tested worlds.
3. It does not trade across disconnected network components.
4. Its outcome depends strongly on the permitted hop radius.
5. Two-hop cellular matching can approach the aggregate service of global comparators in this topology.
6. Cooperative and cellular allocation can improve the distribution of shortages under selected supply shocks.

### Not supported
The results do not establish that:
- a complete SCCE economy creates more real wealth;
- independently running cells can communicate and execute reliably over a real distributed network;
- two-hop local reach is equivalent to consent-based federation;
- local cells outperform mature markets or cooperatives;
- the central min-cost-flow allocation is a whole-economy optimum;
- the market or cooperative comparators represent complete real-world institutions;
- the synthetic service score measures human welfare;
- the result generalizes beyond seven cells, three products and this topology.

## 10. Immediate model changes indicated by the results

1. Add voluntary relay/federation routing with explicit time-to-live, consent and delivery responsibility.
2. Separate message radius from physical delivery radius.
3. Add edge capacity, lead time and failure probability.
4. Add alternative suppliers and technically valid input substitution.
5. Continue dynamic production tests in Stage B; do not infer wealth creation from Stage A.
6. Add household-level essential demand and distribution.
7. Make messages, negotiation, governance, monitoring and dispute resolution consume explicit resources.
8. Strengthen the market, cooperative and central baselines and run matched information treatments.

## 11. Decision

Stage A does not justify claiming that SCCE has won. It establishes that **one-hop isolated cells are inadequate in this network**, while two-hop local coordination can recover aggregate fulfilment. The next design step is not to abolish local autonomy, but to create a bounded, voluntary relay/federation mechanism that connects local initiative to system-wide availability without turning federation into an all-powerful central planner.

Stage B now tests production and inventories. The Stage-B results are reported separately in [SCCE_STAGE_B_PRELIMINARY_RESULTS_2026-11-10.md](SCCE_STAGE_B_PRELIMINARY_RESULTS_2026-11-10.md).

---

**Reproducibility:** paired 100-seed sweeps are executed by GitHub Actions. See the commands in [prototype/README.md](../prototype/README.md).
