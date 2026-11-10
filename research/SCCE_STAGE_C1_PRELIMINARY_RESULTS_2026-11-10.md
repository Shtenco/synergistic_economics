# SCCE Stage-C1 Preliminary Household Distribution Results

**Date:** 10 November 2026  
**Version:** 0.3  
**Status:** 20-seed paired synthetic experiment; three rationing policies; post-hoc physical disaggregation only  
**Engine:** \`prototype/household_distribution.py\`, \`prototype/scc_household_bridge.py\`, \`prototype/scc_household_experiment.py\`  
**Validation:** unit tests and paired 20-seed floor sensitivity runs in GitHub Actions [42804288897](https://github.com/Shtenco/synergistic_economics/actions/runs/42804288897)

---

## 1. Research question

Once Stage B has determined how much physical consumption reaches each economic cell, how does the within-cell rationing rule affect household-level essential fulfilment and inequality?

This experiment deliberately isolates the distribution rule. It does not allow the household allocator to alter production, trade, prices, wages or cell-level deliveries.

## 2. Experimental design

- 20 paired random seeds;
- 7 production cells and 10 synthetic households per cell (70 households per seed);
- 24 periods under the compound shock;
- four Stage-B production/coordination regimes: market, central, cooperative and cellular;
- a persistent synthetic household panel across all 24 periods;
- priority dispersion 0.4 and essential-floor fraction 0.5;
- all three rationing rules receive the same household needs, priorities and already-consumed physical quantities within each seed and production regime.

The three household rules are:
1. **Proportional:** each household receives the same fraction of its essential claim, then the same fraction of its discretionary claim, subject to cell stock.
2. **Priority-weighted max-min:** scarce quantities are allocated in proportion to declared synthetic household priorities, with saturated claims removed and remaining stock redistributed.
3. **Floor-priority:** reserve 50% of each household's essential claim first; if supply is insufficient for the combined floor claims, ration those floor claims proportionally; then allocate residual essential needs by priority and discretionary needs last.

The floor-priority rule is not an absolute guarantee: if physical supply is below the combined floor claims, households receive only a proportional fraction of the declared floor.

All 95% confidence intervals are normal-approximation intervals across 20 seeds. Paired differences compare each alternative rule with proportional allocation within the same seed.

## 3. Core finding: totals stay fixed, distribution changes

Within each Stage-B production regime, the two rationing rules produce the same aggregate essential and overall fulfilment to numerical precision. This is expected: both rules allocate the same physical quantities to the same cell households, and neither can create additional goods.

The difference appears in who receives those quantities.

### Cumulative household outcomes

| Stage-B regime | Rationing | Essential fulfilment | Overall fulfilment | Lower-decile essential fulfilment | Minimum household essential fulfilment | Essential fulfilment Gini |
|---|---|---:|---:|---:|---:|---:|
| Cellular | Proportional | 42.52% | 46.05% | 31.63% | 30.17% | 0.185 |
| Cellular | Priority-weighted | 42.52% | 46.05% | 23.87% | 17.22% | 0.248 |
| Cooperative | Proportional | 44.54% | 51.13% | 30.87% | 27.83% | 0.206 |
| Cooperative | Priority-weighted | 44.54% | 51.13% | 27.24% | 21.16% | 0.234 |
| Central | Proportional | 43.28% | 46.07% | 13.44% | 9.13% | 0.308 |
| Central | Priority-weighted | 43.28% | 46.07% | 13.30% | 9.02% | 0.312 |
| Market | Proportional | 46.53% | 47.48% | 5.77% | 4.86% | 0.413 |
| Market | Priority-weighted | 46.53% | 47.48% | 5.81% | 4.70% | 0.412 |

The production regime determines aggregate consumption in this experiment. The rationing rule changes the distribution of that consumption among households.

## 4. Paired effect of priority weighting

The most consequential changes occur in the cellular and cooperative production regimes.

| Production regime | Change in lower-decile essential fulfilment | 95% paired CI | Change in essential fulfilment Gini | 95% paired CI |
|---|---:|---:|---:|---:|
| Cellular | −7.76 pp | −8.35 to −7.17 pp | +0.0626 | +0.0593 to +0.0659 |
| Cooperative | −3.64 pp | −4.05 to −3.23 pp | +0.0277 | +0.0255 to +0.0299 |
| Central | −0.14 pp | −0.32 to +0.05 pp | +0.0034 | +0.0023 to +0.0044 |
| Market | +0.03 pp | −0.04 to +0.11 pp | −0.0004 | −0.0007 to −0.0001 |

For the cellular regime, priority weighting reduces the lower-decile household essential fulfilment from 31.63% to 23.87%, while increasing essential-fulfilment inequality. In the cooperative regime, the lower decile also falls, from 30.87% to 27.24%.

The mean-period lower-decile measure shows the same pattern:
- Cellular: −7.50 percentage points (95% CI −8.08 to −6.93).
- Cooperative: −4.02 points (CI −4.33 to −3.72).
- Central: +0.40 points (CI +0.32 to +0.48).
- Market: +0.02 points (CI +0.002 to +0.030).

The worst-period minimum household fulfilment is not improved consistently. For cellular it is essentially unchanged; for cooperative it improves slightly, but the cumulative minimum and lower-decile measures still deteriorate.

## 5. Interpretation

This is an important warning for SCCE design:

**Priority weighting is not the same thing as fairness.** A priority-weighted allocator can improve the allocation of scarce goods to households with higher declared weights while worsening the lower tail. The outcome depends on who assigns the weights, how they are justified, whether households can contest them, and whether protected floors constrain the optimizer.

The experiment does not establish that proportional rationing is universally fairer. Proportional rationing is a neutral benchmark with its own limitations: it ignores differences in need severity, urgency, disability-related consumption requirements, household size and other legitimate circumstances. The synthetic priority weights are not calibrated to actual households.

The defensible conclusion is narrower: **a priority score must not be allowed to override a minimum essential-service safeguard.**

## 6. Next mechanism to test: protected essential floors

The next Stage-C1 allocator should test a lexicographic sequence:

1. Calculate a declared minimum essential-service floor for each household and product.
2. If available supply is below the total floor claims, distribute the scarce floor pool proportionally across those claims.
3. If supply covers all floors, meet every floor before allocating any remaining stock.
4. Allocate remaining essential demand using the selected rule (proportional or priority-weighted).
5. Allocate discretionary demand only after essential claims are processed.

The floor parameter must be visible and sensitivity-tested. It is a physical-service protection rule, not a claim that all needs can be reduced to one scalar or that the model can determine human worth.

Required comparisons:
- floor fractions 0.50, 0.75 and 1.00;
- homogeneous and heterogeneous household needs;
- priority dispersion from zero to higher stress values;
- baseline, compound and supply-crisis scenarios;
- lower-decile, minimum-household and worst-period essential fulfilment;
- exact physical reconciliation and no cross-cell transfer.

## 7. Essential-floor sensitivity: 25%, 50% and 75%

The floor fraction was varied while holding the 20 seeds, 24-period compound shock, household panel, priority dispersion (0.4), production regime and all Stage-B physical quantities fixed. Each alternative is paired against proportional rationing under the same seed. The table reports the change caused by floor-priority allocation relative to proportional allocation; lower-decile changes are percentage points, while Gini changes are absolute index units.

| Production regime | Essential floor | Change in lower-decile fulfilment (95% paired CI) | Change in essential Gini (95% paired CI) |
|---|---:|---:|---:|
| Cellular | 25% | −2.54 pp (−2.89 to −2.18) | +0.02048 (+0.01845 to +0.02251) |
| Cellular | 50% | +0.03 pp (−0.10 to +0.15) | +0.00006 (−0.00022 to +0.00033) |
| Cellular | 75% | +0.02 pp (−0.04 to +0.07) | +0.00008 (−0.00001 to +0.00018) |
| Cooperative | 25% | −0.78 pp (−1.02 to −0.55) | +0.00653 (+0.00573 to +0.00732) |
| Cooperative | 50% | −0.21 pp (−0.39 to −0.03) | +0.00308 (+0.00270 to +0.00345) |
| Cooperative | 75% | −0.03 pp (−0.11 to +0.05) | +0.00090 (+0.00073 to +0.00106) |
| Central | 25% | −0.11 pp (−0.28 to +0.06) | +0.00195 (+0.00113 to +0.00277) |
| Central | 50% | −0.08 pp (−0.19 to +0.03) | +0.00122 (+0.00056 to +0.00188) |
| Central | 75% | +0.03 pp (−0.01 to +0.08) | +0.00042 (+0.00008 to +0.00075) |
| Market | 25% | +0.01 pp (−0.05 to +0.06) | −0.00042 (−0.00068 to −0.00017) |
| Market | 50% | −0.001 pp (−0.043 to +0.041) | −0.00046 (−0.00066 to −0.00027) |
| Market | 75% | +0.006 pp (−0.009 to +0.021) | −0.00033 (−0.00047 to −0.00018) |

The minimum-household measure reinforces the warning. At a 25% floor, cellular minimum essential fulfilment falls by 4.49 pp (95% CI −4.93 to −4.05) and cooperative minimum falls by 1.70 pp (−2.18 to −1.22). At a 50% floor, the cooperative minimum falls by 0.72 pp (−0.98 to −0.47). At 75%, the cooperative minimum falls by 0.15 pp (−0.23 to −0.07). Cellular minimum changes at 50% and 75% are statistically indistinguishable from zero in this sample.

**Why does a lower floor sometimes perform worse?** In the compound-shock runs, aggregate essential fulfilment is only about 42.5% in the cellular arm and 44.5% in the cooperative arm. With a 75% floor, available supply is below the sum of protected claims, so the floor pool itself is rationed proportionally; there is almost no residual stock for priority allocation. At a 25% floor, the floor claims can be met, leaving more residual stock to be distributed by random synthetic priority weights. Those weights are not calibrated to need severity, and the resulting priority allocation worsens the lower tail. A 50% floor sits between these cases and remains ineffective as a strong safeguard under this scarcity level.

This is not evidence that a 75% floor is intrinsically best, or that proportional allocation is a complete theory of fairness. It shows that a nominal floor does not protect anyone when total physical supply is below the combined floor claims. If a protected minimum is a constitutional commitment, it must be paired with an explicit supply guarantee, emergency procurement/reserve mechanism, or a transparent statement that the guarantee is infeasible under current physical constraints. A rationing formula cannot manufacture the missing goods.

## 7. Limitations

- Household needs and priorities are synthetic, not survey-calibrated.
- The household bridge is post-hoc: household allocations do not yet feed back into Stage-B production or inter-cell matching.
- No household income, wages, ownership income, money, credit, prices or purchasing-power constraints are modelled.
- No migration, household formation, care-time or public-service access is modelled.
- A 20-seed experiment is exploratory; larger seed counts and parameter sensitivity are required.
- Fulfilment rates are physical allocation metrics, not a complete measure of welfare.

## 8. Decision

Stage C1 now exposes a distributional effect that cell-level averages conceal. The current evidence rejects the assumption that priority-weighted rationing is automatically more equitable. Before any endogenous household economy is integrated into SCCE, the allocator should include a protected essential floor and demonstrate that it improves lower-tail outcomes without violating physical conservation or cell autonomy.

---

**Reproducibility:** the paired experiment is run by \`prototype/scc_household_experiment.py\`; household allocation invariants are tested by \`prototype/test_household_distribution.py\` and \`prototype/test_scc_household_bridge.py\`.
