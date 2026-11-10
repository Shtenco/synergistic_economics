# SCCE Stage-B Preliminary Dynamic-Economy Results

**Date:** 10 November 2026  
**Version:** 0.1  
**Status:** 100-seed synthetic simulation; preliminary mechanism evidence only  
**Engine:** \`prototype/scc_dynamic_economy.py\`  
**Validation:** GitHub Actions workflow, Python unit tests and paired 100-seed sweeps

---

## 1. Question

Does a network of economic cells, using local information and repeated local coordination, produce more physical output and satisfy more community demand than market, central-allocation and cooperative-pool coordination under identical starting conditions?

This is a much stronger test than Stage A because it includes endogenous production, intermediate inputs, inventories, local community demand and ecological resource stocks. It is still not a complete economy and cannot yet answer whether SYNERGY creates more real human welfare.

## 2. Matched experiment

Each run uses:
- seven production cells: food, materials, energy, machinery, logistics, software and care;
- the same seed-specific capacities, productivity, initial inventories, local raw-resource stocks and community demand across all four regimes;
- the same seven-cell network topology;
- the same 24-period horizon and shock schedule;
- the same production recipes, resource regeneration and unit costs.

Four regimes are compared:
1. **Market:** producers respond to previous-period market-wide unmet orders; price-ranked matching uses synthetic bids.
2. **Central:** current aggregate declared final demand informs production planning; a global min-cost-flow allocator maximizes the linear priority-weighted service-minus-route-cost objective.
3. **Cooperative:** member needs are pooled, with a larger shared production buffer and priority-weighted max-min rationing.
4. **Cellular SCCE:** production responds to unmet demand signals inside the configured network radius; local request/response matching is limited to that same radius.

Every seed is paired across regimes. The 100-seed summaries below use the same 100 initial worlds in all four arms. Confidence intervals are 95% normal-approximation intervals for the mean; paired-difference intervals are calculated from within-seed differences against the market arm.

## 3. What is measured

- **Final fulfilment:** total final community consumption divided by declared final demand.
- **Essential fulfilment:** fulfilment of food and care demand.
- **Weighted fulfilment:** final consumption weighted by declared need-priority coefficients.
- **Cell fulfilment Gini:** inequality across the seven cell-level fulfilment ratios; lower is more even.
- **Fixed-price final-consumption index:** consumed quantities valued at fixed model prices.
- **Fixed-price gross-output index:** produced quantities valued at the same fixed prices, including intermediate products.
- **Unmet demand and input shortage:** physical quantities, reported separately.
- **Logistics and coordination costs:** synthetic diagnostics. Coordination cost is currently a fixed charge per executed allocation; it excludes failed messages, search, governance, enforcement and the labour time consumed by coordination.

The fixed-price indices are not GDP, value added, income, profit, utility or empirically measured welfare. Logistics and monetary coordination diagnostics are not calibrated to the consumption index and must not be subtracted from it to claim net welfare. Coordination labour is deducted from productive capacity, but packet and record time assumptions are synthetic and require sensitivity analysis. Non-cellular message counts are estimates; cellular packets and payload records are counted from the hop-by-hop trace after batching. Governance, enforcement, meetings and dispute resolution remain incomplete.

## 4. Baseline: no external shock

100 paired seeds, 24 periods, two-hop local reach for the cellular arm.

| Regime | Final fulfilment | 95% CI | Essential fulfilment | 95% CI | Weighted fulfilment | Cell Gini | Final-consumption index | Packets | Payload records | Coordination cost | Coordination labour hours |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Market | 51.78% | 51.65–51.91% | 51.15% | 51.03–51.27% | 51.62% | 0.360 | 706.11 | 1,644 | 1,644 | 68.47 | 16.44 |
| Central | 56.40% | 55.97–56.83% | 54.84% | 54.52–55.16% | 55.66% | 0.235 | 771.81 | 1,885 | 1,885 | 76.58 | 18.85 |
| Cooperative | 60.27% | 60.11–60.44% | 53.17% | 52.99–53.36% | 56.26% | 0.113 | 824.68 | 2,932 | 2,932 | 121.33 | 29.32 |
| Cellular, 2 hops | 51.87% | 51.75–51.98% | 49.07% | 48.95–49.19% | 50.35% | 0.151 | 721.97 | 10,141 | 11,190 | 121.22 | 103.51 |

Paired mean differences versus the market arm:
- Central: final fulfilment **+4.62 percentage points** (95% CI +4.16 to +5.08); essential fulfilment +3.69 points; fixed-price consumption index +65.70 (CI +58.86 to +72.55).
- Cooperative: final fulfilment **+8.50 points** (CI +8.31 to +8.68); essential fulfilment +2.02 points; weighted fulfilment +4.63 points; consumption index +118.58 (CI +116.16 to +121.00).
- Cellular, two hops: final fulfilment +0.08 points (CI −0.06 to +0.22; not distinguishable from zero in this experiment); essential fulfilment −2.09 points; weighted fulfilment −1.28 points; consumption index +15.74 (CI +13.83 to +17.65).

**Interpretation:** in the baseline scenario, the cooperative-pool mechanism leads on total final fulfilment, weighted fulfilment and the fixed-price consumption index. Central planning is second on these aggregate measures and has the highest essential fulfilment. Two-hop cellular coordination is approximately tied with the market on total fulfilment, but has lower inequality and weaker essential-service fulfilment.

## 5. Compound shock

The compound shock combines a food-demand increase, reduced resource regeneration and lower productivity. 100 paired seeds, 24 periods.

| Regime | Final fulfilment | 95% CI | Essential fulfilment | 95% CI | Weighted fulfilment | Cell Gini | Final-consumption index | Packets | Payload records | Coordination cost | Coordination labour hours |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Market | 47.50% | 47.35–47.64% | 46.67% | 46.49–46.86% | 47.23% | 0.426 | 761.23 | 1,612 | 1,612 | 66.50 | 16.12 |
| Central | 46.22% | 46.01–46.42% | 44.12% | 43.90–44.33% | 45.53% | 0.317 | 747.99 | 1,814 | 1,814 | 72.12 | 18.14 |
| Cooperative | 51.21% | 51.06–51.35% | 45.60% | 45.44–45.76% | 48.22% | 0.150 | 826.42 | 2,858 | 2,858 | 116.72 | 28.58 |
| Cellular, 2 hops | 46.00% | 45.85–46.15% | 42.77% | 42.58–42.96% | 44.30% | 0.170 | 754.18 | 10,526 | 11,608 | 123.07 | 107.43 |
| Cellular, 3 hops | 46.68% | 46.53–46.82% | 42.12% | 41.96–42.29% | 44.38% | 0.160 | 759.47 | 11,209 | 12,305 | 131.45 | 114.28 |
| Cellular, 1 hop | 14.93% | 14.77–15.10% | 10.87% | 10.69–11.06% | 13.20% | 0.360 | 263.67 | 3,890 | 3,890 | 38.82 | 38.90 |

Paired mean differences versus the market arm:
- Cooperative: final fulfilment **+3.71 points** (CI +3.63 to +3.79); weighted fulfilment +0.99 points; consumption index +65.19 (CI +63.96 to +66.41); essential fulfilment −1.07 points.
- Cellular, two hops: final fulfilment −1.50 points (CI −1.61 to −1.38); essential fulfilment −3.91 points; weighted fulfilment −2.93 points; consumption index −7.03 (CI −8.88 to −5.19).
- Cellular, three hops: final fulfilment −0.82 points (CI −0.93 to −0.70); essential fulfilment −4.55 points; weighted fulfilment −2.85 points; consumption index −1.77 (CI −3.48 to −0.05).
- Cellular, one hop: final fulfilment −32.56 points; essential fulfilment −35.80 points; consumption index −497.56.

**Interpretation:** the cooperative-pool rule is strongest on aggregate final fulfilment, weighted fulfilment, consumption index and distributional evenness in this compound scenario. The market arm has the highest essential-service fulfilment. Cellular coordination improves materially as its reach expands from one hop to two and three hops. Three-hop cellular reach nearly closes the fixed-price consumption-index gap with the market, but does not close the essential-service or weighted-fulfilment gaps.

## 6. The key cellular finding: reach is an economic parameter

The compound-shock cellular results show a sharp dependence on communication/delivery radius:

| Cellular reach | Final fulfilment | Essential fulfilment | Weighted fulfilment | Final-consumption index |
|---|---:|---:|---:|---:|
| 1 hop | 14.93% | 10.87% | 13.20% | 263.67 |
| 2 hops | 46.00% | 42.77% | 44.30% | 754.20 |
| 3 hops | 46.68% | 42.12% | 44.38% | 759.47 |

This is not a small tuning effect. One-hop cells become trapped in local shortages while useful production and demand exist elsewhere. Extending reach across the network recovers much of the lost consumption. However, three-hop reach is not yet a real federation: it is a radius setting in a single-process simulator. It has no federation charter, relay consent, message delay, edge capacity, dispute protocol or independent cell runtime.

## 7. What these results do and do not show

### Supported by the present model
1. The dynamic physical prototype executes four distinct coordination rules on matched initial worlds.
2. Production planning and intermediate-input procurement interact with the matching regime; distribution alone is not the whole result.
3. The cooperative-pool rule currently performs best on aggregate final fulfilment and the fixed-price consumption index in both reported scenarios.
4. The market rule currently has the highest essential fulfilment under the compound shock.
5. Cellular outcomes depend dramatically on local reach. One-hop locality is not viable in this topology; wider reach recovers much of the aggregate shortfall.
6. Cellular fulfilment distribution is more even than market and central in these runs, but this does not compensate automatically for lower essential fulfilment.

### Not supported
The results do not establish that:
- SCCE creates more real wealth than market, central or cooperative economies;
- the stylized market is representative of mature markets with budgets, strategic bids, competition, entry/exit and credit;
- the cooperative-pool rule captures real cooperative governance, participation costs or free-riding;
- the central allocation benchmark is a full social-welfare optimum;
- the synthetic need weights represent actual human preferences or rights;
- fixed-price output/consumption indices measure welfare;
- the seven-cell results generalize to larger, calibrated economies.

The current model excludes money, credit, wages, ownership, investment, household income, employment, working-time choice, public goods, technology diffusion and most ecological externalities. Cellular message forwarding is counted hop by hop and its synthetic labour requirement is deducted from production capacity. Non-cellular message counts remain estimates rather than full protocol traces; governance and enforcement effort remain incomplete. No conclusion about positive-sum prosperity is justified until these are modelled and calibrated.

## 8. Immediate research implications

1. **Do not treat one-hop locality as the canonical SCCE design.** Cells need bounded multi-hop relay and voluntary federation.
2. **Separate communication topology from logistics topology.** A request can propagate through several cells while the physical shipment follows a different route.
3. **Add essential-service safeguards.** The cellular rule must protect food, care and other essential needs during shocks, without turning priority scores into a measure of human worth.
4. **Model coordination as a real resource cost.** Messages, search, negotiation, governance and dispute resolution must consume labour/time or another explicit scarce resource.
5. **Strengthen the market baseline.** Add household/cell budgets, price formation, strategic response, market power, inventories and entry/exit.
6. **Strengthen cooperative governance.** Model member reporting, voting, free-riding, participation and dispute costs rather than only a common-pool allocation formula.
7. **Keep the central min-cost-flow result in its proper role.** It is an upper bound for a narrow linear allocation objective, not a whole-economy optimum.
8. **Integrate financial and ownership layers only after the physical layer is stable.** Cash conservation is necessary but not evidence of additional real output.
9. **Add independent-cell execution and larger networks.** Test 20, 50, 100 and 500 cells, network-density variation, edge failures and communication delays.

## 9. Decision

The first dynamic comparison does **not** show that SCCE is already superior. The strongest result so far is diagnostic: local economic cells need a carefully designed multi-hop/federation layer and explicit essential-service protection. The cooperative-pool control currently leads the stylized model on aggregate consumption; the market control retains an advantage on essential fulfilment during the compound shock; the cellular model improves its aggregate performance as its reach expands, but still does not win.

Proceed with SCCE, but treat these outcomes as constraints for the next design iteration—not as a victory claim. The next step is to implement voluntary relay/federation and resource-priced coordination, then rerun the same paired experiments with stronger market and cooperative baselines.

---

**Reproducibility:** GitHub Actions runs the Stage-B baseline, compound-shock comparisons and 100-seed paired sweeps. The simulator and tests are in \`prototype/scc_dynamic_economy.py\` and \`prototype/test_scc_dynamic_economy.py\`.
