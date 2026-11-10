# SCCE Stage-A Preliminary Comparative Benchmark

**Date:** 10 November 2026  
**Version:** 0.1  
**Status:** Preliminary synthetic mechanism results; not empirical evidence and not a test of the complete SCCE economy.  
**Engine:** prototype/cellular_coordination.py  
**Design:** paired comparisons across four allocation regimes on identical seven-cell worlds.

---

## 1. Purpose

This report records the first reproducible comparison of local cellular matching against stylized market, centralized and cooperative allocation rules. The purpose is diagnostic: identify what local coordination currently does well, where it fails, and which mechanisms need to be added before integrating it into the full production economy.

The experiment does **not** establish that cellular economics is superior. In fact, the results show a material one-hop locality penalty and a smaller residual gap after extending the local communication/delivery radius.

## 2. Experiment design

Each synthetic world contains seven cells, three product classes (food, materials and energy), heterogeneous supplies, heterogeneous demands and need-priority weights, and a sparse inter-cell network. Every regime receives the same world for a given seed.

Four allocation regimes are compared:
- **Market:** global bilateral price/bid matching with priority-linked synthetic bids.
- **Central:** full-information greedy allocation by need priority and route distance.
- **Cooperative:** common-pool, priority-weighted max-min rationing, followed by nearest-supplier delivery.
- **Cellular:** repeated local request/response rounds; a buyer can contact only suppliers within the configured hop radius.

The paired Monte Carlo sweeps use 100 deterministic seeds for each scenario/hop combination. The CI workflow runs baseline one-hop and two-hop cases, compound-shock one-hop and two-hop cases, supply-crisis two-hop and demand-surge two-hop cases.

## 3. Metric definitions

- **Fulfilment:** served physical units divided by requested units.
- **Weighted fulfilment:** served units weighted by the cell's synthetic need-priority parameter, divided by weighted demand.
- **Lower-cell fulfilment:** the minimum cell-level fulfilment ratio in the seven-cell world.
- **Cell fulfilment Gini:** inequality in the seven cell-level fulfilment ratios.
- **Logistics cost:** allocated quantity multiplied by route hops and the synthetic per-hop cost.
- **Coordination cost:** a fixed synthetic cost per executed buyer-seller-product allocation.
- **Net service score:** weighted service quantity minus logistics and coordination costs.

The net service score is an **un-calibrated diagnostic index**. Its components are synthetic and not empirically monetized. It is not GDP, income, profit, utility, consumer surplus or a measure of actual human welfare. Results must be interpreted component by component.

## 4. Baseline: no shock

Averages across 100 paired seeds:

| Regime | Local hops | Fulfilment | Weighted fulfilment | Lowest cell fulfilment | Cell Gini | Unmet units | Net service score |
|---|---:|---:|---:|---:|---:|---:|---:|
| Market | Global | 99.67% | 99.80% | 97.56% | 0.0031 | 0.349 | 146.557 |
| Central | Global | 100.00% | 100.00% | 99.99% | 0.00002 | 0.002 | 146.800 |
| Cooperative | Global | 100.00% | 100.00% | 99.99% | 0.00002 | 0.002 | 146.876 |
| Cellular | 1 | 90.29% | 91.63% | 63.05% | 0.0774 | 10.133 | 135.251 |
| Cellular | 2 | 99.73% | 99.82% | 98.13% | 0.0023 | 0.287 | 146.491 |

**Finding:** the one-hop cellular rule leaves meaningful demand unmet while usable supply exists elsewhere in the connected economy. Expanding the search/coordination radius to two hops closes most of the gap in this topology. This is evidence that local reach and federation/relay design are first-order parameters, not implementation details.

## 5. Compound shock

A combined food-demand increase and energy-supply reduction:

| Regime | Local hops | Fulfilment | Weighted fulfilment | Lowest cell fulfilment | Cell Gini | Unmet units | Net service score |
|---|---:|---:|---:|---:|---:|---:|---:|
| Market | Global | 90.91% | 92.05% | 67.16% | 0.0686 | 10.353 | 149.702 |
| Central | Global | 91.21% | 92.24% | 67.26% | 0.0671 | 10.006 | 149.944 |
| Cooperative | Global | 91.21% | 91.34% | 82.65% | 0.0344 | 10.006 | 148.333 |
| Cellular | 1 | 85.48% | 86.70% | 60.82% | 0.0875 | 16.498 | 141.659 |
| Cellular | 2 | 90.96% | 91.13% | 82.44% | 0.0341 | 10.291 | 147.938 |

**Finding:** two-hop cellular matching nearly closes the aggregate fulfilment gap, and its minimum cell fulfilment and Gini are much closer to the cooperative regime than to the market and central comparators. It does not achieve the highest weighted fulfilment or net service score. One-hop cellular matching performs materially worse.

## 6. Supply crisis

A reduction in energy supply:

| Regime | Local hops | Fulfilment | Weighted fulfilment | Lowest cell fulfilment | Cell Gini | Unmet units | Net service score |
|---|---:|---:|---:|---:|---:|---:|---:|
| Market | Global | 84.10% | 85.27% | 61.12% | 0.1020 | 16.653 | 124.925 |
| Central | Global | 84.43% | 85.47% | 61.47% | 0.1005 | 16.306 | 125.167 |
| Cooperative | Global | 84.43% | 84.17% | 75.22% | 0.0422 | 16.306 | 122.907 |
| Cellular | 2 | 84.16% | 83.96% | 75.07% | 0.0421 | 16.591 | 122.642 |

**Finding:** under this supply shock, cellular and cooperative allocations have materially better lower-cell fulfilment and lower inequality than the market and central rules. Cellular remains slightly behind the cooperative regime on the current aggregate diagnostic score and unmet demand.

## 7. Demand surge

A 45% increase in food demand:

| Regime | Local hops | Fulfilment | Weighted fulfilment | Lowest cell fulfilment | Cell Gini | Unmet units | Net service score |
|---|---:|---:|---:|---:|---:|---:|---:|
| Market | Global | 99.51% | 99.62% | 96.62% | 0.0043 | 0.601 | 175.042 |
| Central | Global | 99.80% | 99.79% | 98.69% | 0.0017 | 0.254 | 175.285 |
| Cooperative | Global | 99.80% | 99.77% | 99.29% | 0.0013 | 0.254 | 175.343 |
| Cellular | 2 | 99.56% | 99.62% | 97.56% | 0.0034 | 0.538 | 174.738 |

**Finding:** the cooperative rule is strongest on the current aggregate score and minimum cell fulfilment. Cellular is close but does not lead.

## 8. What can and cannot be concluded

### Supported by this prototype

1. The local cellular request/response algorithm executes deterministically.
2. It respects aggregate supply and demand bounds in the tested worlds.
3. It does not trade across disconnected network components.
4. Its outcome depends strongly on the permitted local hop radius.
5. Under the selected shock configurations, two-hop cellular matching can approach the aggregate service of the global comparators while retaining a more even distribution than the market and central rules in some shortage scenarios.
6. The cooperative rule remains competitive and often leads on the current aggregate diagnostic score.

### Not supported

The results do not establish:
- that a complete SCCE economy creates more real wealth;
- that independently running cells can communicate and execute reliably over a real distributed network;
- that two-hop local reach is equivalent to a consent-based federation;
- that local cells outperform mature markets or cooperatives;
- that the central comparator is a true global optimum;
- that the market comparator is a complete or strong representation of real markets;
- that the synthetic service score measures welfare;
- that the result generalizes beyond seven cells, three products and this network topology.

The market comparator currently uses synthetic priority-linked bids and lacks cash budgets, strategic bidding, market power, firm entry/exit and inventory finance. The central comparator is greedy rather than a solved optimization model. The cooperative comparator is a stylized weighted common-pool rule. These are prototype baselines that must be strengthened.

## 9. Immediate model changes indicated by the results

1. **Add voluntary relay/federation routing.** A local cell should be able to forward a request through neighbours under a bounded time-to-live, while preserving end-to-end consent and traceable delivery responsibility.
2. **Separate message radius from physical delivery radius.** A message may propagate through a network even when a shipment uses a different logistics path.
3. **Add network-edge capacity and delay.** The present hop cost is not a transport-capacity model.
4. **Add alternative suppliers and substitution.** Cells should be able to propose technically valid substitute inputs, not merely search for the same product.
5. **Add inventory carry-over and production constraints.** The matching engine must be connected to real production plans before it can assess wealth creation.
6. **Add household-level essential demand and distribution.** Cell fulfilment is only a coarse proxy for household welfare.
7. **Add actual coordination cost accounting.** Messages, negotiation, governance, monitoring and dispute resolution must consume explicit resources.
8. **Strengthen every baseline.** The next experiment should use a genuine market-clearing protocol, a cooperative governance protocol and a mathematical-programming central upper bound, all under matched information treatments.

## 10. Decision

The Stage-A result does not justify claiming that SCCE has won. It identifies a concrete engineering requirement: **a viable cellular economy cannot be a collection of isolated one-hop cells. It needs bounded multi-hop communication, voluntary federation and a mechanism that connects local initiative to system-wide availability without turning federation into an all-powerful central planner.**

Proceed to Stage B only after adding relay/federation routing and validating it against the same paired scenarios. Then integrate the coordination layer with the existing seven-cell production model and preserve all physical and financial invariants.

---

**Reproducibility:** run the paired 100-seed experiments using the commands in prototype/README.md. The GitHub Actions workflow executes the baseline and stress sweeps on every prototype change.
