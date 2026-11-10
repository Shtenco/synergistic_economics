# SCCE Stage C2-A2 — Endogenous Household Feedback: Preliminary Results

**Date:** 10 November 2026  
**Version:** 0.1  
**Status:** 20-seed paired synthetic experiment; first in-loop household delivery and bounded essential-backlog prototype  
**Implementation:** `prototype/scc_endogenous_household_economy.py`  
**Experiment:** `prototype/scc_endogenous_household_experiment.py`  
**Validation:** focused GitHub Actions workflow [42806853426](https://github.com/Shtenco/synergistic_economics/actions/runs/42806853426), including unit tests, 20-seed four-regime experiment, zero-backlog control and paired backlog sensitivity

---

## 1. Research question

Does feeding household-level unmet essential needs back into each household's own economic cell change production, consumption and distributional outcomes? Does that feedback help every coordination regime equally?

Stage C2-A2 advances beyond the Stage-C1 post-hoc bridge. Each period:
1. household current needs and prior essential backlog are aggregated into the household's own cell demand;
2. the Stage-B economy plans and executes production and inter-cell matching;
3. actual cell consumption is allocated to the same persistent household panel;
4. the allocation is reconciled to the physical delivery record;
5. unmet essential claims are carried forward under a retention rule and a per-household cap;
6. the next period's own-cell demand includes that backlog.

The Stage-B external-order signal continues to represent unmet demand from other cells. Household backlog adds only the household's own cell demand, so the two signals are not intentionally double-counted.

## 2. Experimental design

- 20 paired seeds;
- seven production cells and ten synthetic households per cell (70 households per seed);
- 24 periods and a compound shock;
- two-hop cellular communication reach;
- priority dispersion 0.4;
- essential floor fraction 0.5;
- backlog retention 0.5;
- maximum essential backlog: one baseline period of that household's essential need;
- four economic regimes: market, central, cooperative and cellular;
- three household allocation rules: proportional, priority-weighted and floor-priority.

All regimes use the same seed-specific production cells, household panel, initial stocks, needs, priorities, technology, shock path and time horizon. Paired comparisons use the same seeds.

The backlog is a **physical unmet-need record**, not money, debt, a token balance or a financial liability. It carries no interest and does not create purchasing power.

### Current-first accounting convention

The household allocator receives current essential needs plus the carried backlog as a combined essential claim. After allocation, delivered quantity is attributed to current-period essential need first; any remainder clears older backlog. This is an explicit accounting convention, not a separate priority layer inside the allocator. It affects backlog dynamics and must be tested against a backlog-first alternative.

## 3. Main results under proportional household allocation

Means and 95% normal-approximation confidence intervals across 20 seeds.

| Economic regime | Current essential fulfilment | Current overall fulfilment | Household lower-decile essential fulfilment | Minimum household essential fulfilment | Essential Gini | Final-consumption index | Ending essential backlog |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cellular | 44.85% (44.41–45.29) | 47.99% (47.68–48.30) | **33.55% (32.95–34.14)** | 31.52% (30.80–32.25) | 0.1764 (0.1717–0.1810) | 786.40 (781.13–791.66) | 8.40 (8.24–8.57) |
| Cooperative | 44.33% (43.96–44.69) | **50.94% (50.61–51.27)** | 30.09% (29.59–30.59) | 27.23% (26.63–27.83) | 0.2101 (0.2057–0.2144) | **826.80 (822.23–831.38)** | 8.00 (7.88–8.12) |
| Market | **46.45% (46.12–46.77)** | 47.15% (46.87–47.42) | 3.96% (3.56–4.35) | 1.97% (1.77–2.17) | 0.4215 (0.4178–0.4252) | 810.99 (806.95–815.04) | 5.65 (5.50–5.80) |
| Central | 40.93% (40.18–41.69) | 42.59% (42.11–43.07) | 13.53% (12.96–14.11) | 8.74% (8.21–9.28) | 0.3453 (0.3318–0.3588) | 768.64 (752.79–784.49) | 7.64 (7.03–8.25) |

The cellular regime has the strongest household lower-decile and minimum outcomes in this sample, while the cooperative regime has the highest overall fulfilment and fixed-price final-consumption index. The market regime has the highest mean current essential fulfilment but a very weak lower tail. The central regime is lowest on current mean essential and overall fulfilment in this particular setup.

This is a multi-objective trade-off, not a single winner:
- **Cellular:** stronger lower-tail protection, lower aggregate physical consumption than cooperative, and substantially higher coordination labour.
- **Cooperative:** highest aggregate physical consumption and overall fulfilment, with a lower tail below cellular but far above the market arm.
- **Market:** strongest mean essential fulfilment, but severe within-household inequality in this synthetic panel.
- **Central:** lower aggregate and lower-tail outcomes here; this is not a proof against central planning in general.

The cellular arm uses about 108.7 coordination labour-hours per run, compared with 28.6 for cooperative, 16.2 for market and 16.9 for central. This coordination burden is material and must be included in any sustainability assessment.

## 4. Paired effect of household rationing rules

Priority-weighted allocation compared with proportional allocation:

| Economic regime | Change in lower-decile essential fulfilment | 95% paired CI | Change in essential Gini | 95% paired CI |
|---|---:|---:|---:|---:|
| Cellular | −8.34 pp | −8.94 to −7.73 | +0.06511 | +0.06206 to +0.06816 |
| Cooperative | −3.59 pp | −4.02 to −3.17 | +0.02660 | +0.02483 to +0.02837 |
| Central | −0.24 pp | −0.50 to +0.02 | +0.00181 | +0.00135 to +0.00227 |
| Market | −0.20 pp | −0.37 to −0.04 | +0.00227 | +0.00184 to +0.00270 |

Random priority weights are not calibrated to need severity. The results repeat the Stage-C1 warning: a priority score can worsen the lower tail even when aggregate quantities are unchanged.

The 50% floor-priority rule is close to proportional in the cellular arm, but does not improve the cooperative lower tail in this sample. It is not a reliable minimum guarantee when physical supply is insufficient. The floor applies to the combined current-plus-backlog essential claim, not only the current period's need.

## 5. Paired backlog feedback versus a zero-backlog control

The zero-backlog control uses the same seeds and all other settings but sets retention and backlog cap to zero. The table reports **with-backlog minus zero-backlog** paired differences under proportional household allocation.

| Regime | Change in current essential fulfilment | 95% paired CI | Change in lower-decile fulfilment | 95% paired CI | Change in essential Gini | 95% paired CI | Change in final-consumption index | 95% paired CI |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Cellular | +2.34 pp | +2.14 to +2.53 | +1.94 pp | +1.40 to +2.49 | −0.00910 | −0.01523 to −0.00297 | +32.24 | +30.19 to +34.30 |
| Central | −2.35 pp | −3.01 to −1.69 | −0.26 pp | −0.77 to +0.25 | +0.03699 | +0.02672 to +0.04727 | +23.93 | +11.41 to +36.44 |
| Cooperative | −0.21 pp | −0.27 to −0.15 | −0.35 pp | −0.45 to −0.24 | +0.00298 | +0.00203 to +0.00394 | +1.98 | +1.33 to +2.63 |
| Market | −0.08 pp | −0.44 to +0.27 | −1.86 pp | −2.32 to −1.39 | +0.00869 | +0.00568 to +0.01170 | +49.91 | +46.91 to +52.91 |

The backlog feedback increases the fixed-price final-consumption index in all four regimes, but it does **not** improve current household outcomes uniformly:
- In the cellular arm, the feedback improves current essential fulfilment and the lower decile, while reducing household essential inequality.
- In the cooperative arm, it modestly increases physical consumption but slightly worsens current fulfilment and the lower tail.
- In the market arm, it substantially increases physical consumption, but worsens the lower decile and essential Gini.
- In the central arm, physical consumption rises while current essential and overall fulfilment fall and household inequality rises.

This is a key finding: **a larger production/consumption index is not equivalent to improved current well-being.** Backlog feedback can stimulate production while diverting part of the resulting flow toward older claims. The distribution and production rules determine who benefits and when.

The results suggest that the cellular local transition responds differently to household backlog than the other three regimes under the current seven-cell topology and production rules. This is a hypothesis for further testing, not a general theorem about cellular economies.

## 6. Interpretation and design consequences

1. Household demand and backlog must remain separate from cash-backed effective demand. A household's unmet need is not a purchase order, money or debt.
2. Backlog must be bounded and age-aware. An unbounded backlog would create runaway demand signals and could make every regime appear to grow simply because claims accumulate.
3. The local cellular transition must be tested against a realistic information and coordination budget. In this sample it has the highest coordination labour.
4. Distribution policy is not a cosmetic post-processing choice once household backlog feeds into production. It can change the household-level backlog distribution and subsequent cell demand.
5. A minimum essential-service promise requires supply assurance—reserves, redundancy, procurement and voluntary mutual aid—not only a rationing formula.
6. Current-first versus backlog-first service attribution, backlog retention, cap size and priority dispersion must all be sensitivity-tested.

## 7. Limitations

- 20 seeds are exploratory, not sufficient for a superiority claim.
- Household needs, priority weights and production coefficients are synthetic.
- The market regime is the Stage-B physical market-matching mechanism; it does **not** yet include household wages, income, wealth, prices paid, budget constraints or purchasing power. It is not a complete ordinary market economy.
- The central and cooperative regimes are stylized allocation controls, not fully specified real-world institutions with governance, enforcement and information costs.
- No wages, voluntary labour supply, household time use, ownership income, money, credit, debt service, household production or migration are modelled.
- The model does not yet measure utility, health, capabilities, leisure, public goods or environmental quality. The fixed-price index is not GDP, value added or welfare.
- The household allocation currently attributes delivered goods to current need before backlog; a backlog-first alternative has not yet been tested.
- Only one seven-cell topology, one compound shock profile, one default backlog retention (0.5) and one backlog cap (one baseline period) are used here.
- The coordination labour assumptions remain synthetic; governance, negotiation, enforcement and dispute-resolution effort are incomplete.

## 8. Decision and next stage

C2-A2 demonstrates a real household-to-cell feedback path: household unmet essential claims change the next period's own-cell demand, and the production regime's response can alter subsequent household fulfilment. The zero-backlog control reproduces the Stage-B physical outcomes, while the backlog-enabled model produces materially different results.

The experiment does **not** establish that SCCE is superior. It identifies a promising mechanism and an important risk: feedback can raise output while worsening the distribution or current fulfilment in some regimes.

Next:
1. test current-first versus backlog-first accounting and multiple retention/cap values;
2. add backlog age cohorts, expiry and essential-service breach duration;
3. test reserve capacity, redundancy and voluntary mutual aid as supply-assurance mechanisms;
4. move to C2-B voluntary household time, care and productive participation under an explicit time budget;
5. only then add household income, budgets, ownership and credit.

The C2-A2 prototype remains a physical household-cell model. It is not a complete SYNERGY economy and it does not yet answer the real-welfare comparison conclusively.
