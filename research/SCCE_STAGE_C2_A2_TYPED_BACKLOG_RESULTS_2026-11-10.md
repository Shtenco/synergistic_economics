# SCCE Stage C2-A2 — Typed Household Need and Care-Queue Results

**Date:** 10 November 2026  
**Version:** 0.1  
**Status:** 20-seed paired synthetic experiment; typed unmet-need semantics  
**Implementation:** `prototype/scc_endogenous_household_economy.py`  
**Experiment:** `prototype/scc_endogenous_household_experiment.py`  
**Validation workflow:** [SCCE Stage-C2 validation — successful](https://github.com/Shtenco/synergistic_economics/actions/runs/42808337962)

---

> **Scope note:** these results validate the typed C2-A2 distinction between recurring food needs and queueable care claims. They predate the C2-A3 age-cohort integration. Queue-age expiry, admission attrition and overflow are not represented in the tables below; those are being validated separately.

## 1. Methodological correction

The first C2-A2 experiment carried both food and care shortfalls forward as if they were queueable claims. A paired service-order sensitivity exposed a problem: the current-need fulfilment metric could change sharply without any change in physical deliveries. The earlier generic-backlog results are preserved in [the superseded experiment record](SCCE_STAGE_C2_A2_PRELIMINARY_RESULTS_2026-11-10.md), but their combined current-essential ranking must not be used as a welfare conclusion.

The corrected model distinguishes:

- **Food:** recurring, period-specific need. An unmet food need is recorded as cumulative deprivation exposure; it does not create a second food order next period.
- **Care:** a queueable service in this prototype. Delayed care claims may carry forward under a retention rule and per-household cap. The queue can feed the household's own cell demand in the next period.
- **Discretionary products:** current-period requests only; no backlog in this version.

This is still a simplified taxonomy. Food and care are not calibrated to actual household consumption or service systems. The model's "food deprivation units" are physical shortfall units, not a clinical health outcome.

## 2. Experiment

- 20 paired seeds; 24 periods; compound shock;
- seven production cells and ten synthetic households per cell (70 households);
- two-hop cellular communication reach;
- priority dispersion 0.4;
- 50% essential floor;
- care-queue retention 0.5 and cap of one baseline period of each household's care need;
- four production/coordination regimes: market, central, cooperative and cellular;
- three household allocation rules: proportional, priority-weighted and floor-priority.

All institutional arms use the same seed-specific household panel, needs, priorities, production coefficients, initial stocks, technology and shock path. Paired differences use identical seeds.

The default queue policy is **backlog-first (FIFO within each household)**. The experiment also compares current-first attribution, where new care requests are credited before older queued claims. The household allocator distributes the same physical care delivery in both cases; the service-order setting determines which of that household's claims is marked as fulfilled.

## 3. Main results: proportional household allocation, FIFO care queue

Means and 95% normal-approximation confidence intervals across 20 seeds.

| Regime | Current food fulfilment | Current care fulfilment | Combined current essential fulfilment | Overall current fulfilment | Lower-decile essential fulfilment | Essential Gini | Cumulative unmet food units | Ending care queue | Final-consumption index |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Cellular | 37.42% (36.81–38.03) | 49.43% (48.72–50.13) | 39.71% (39.26–40.17) | 43.69% (43.40–43.98) | 28.82% (28.28–29.37) | 0.2030 (0.1979–0.2082) | 166.71 (164.57–168.85) | 0.719 (0.628–0.810) | 774.36 (769.22–779.49) |
| Central | 41.42% (40.34–42.50) | 54.99% (51.23–58.75) | 44.02% (43.40–44.63) | 45.21% (44.47–45.95) | 13.45% (12.86–14.03) | 0.3245 (0.3099–0.3392) | 156.05 (152.88–159.22) | 0.825 (0.581–1.070) | 768.64 (752.79–784.49) |
| Cooperative | 31.87% (31.42–32.32) | 98.19% (97.68–98.71) | 44.56% (44.20–44.93) | **51.14% (50.80–51.48)** | **30.39% (29.85–30.92)** | **0.2081 (0.2034–0.2128)** | 181.48 (179.53–183.44) | **0.018 (0.006–0.030)** | **826.80 (822.23–831.38)** |
| Market | **47.19% (46.68–47.69)** | 46.19% (45.30–47.09) | **46.99% (46.66–47.33)** | 47.62% (47.37–47.88) | 4.13% (3.86–4.41) | 0.4181 (0.4141–0.4220) | **140.70 (138.76–142.63)** | 0.389 (0.194–0.584) | 797.42 (793.32–801.51) |

The results are not a single ranking:
- The cooperative arm has the highest overall current fulfilment, nearly complete current care fulfilment, the highest final-consumption index and the smallest ending care queue. It nevertheless has the weakest current food fulfilment among the four arms.
- The market arm has the highest current food and combined essential fulfilment, but the lowest household lower-decile outcome and the highest essential Gini.
- The cellular arm is between those outcomes: it has a much stronger lower tail than the market arm, but lower aggregate consumption than cooperative and lower current essential fulfilment than market.
- The central arm is weaker on most aggregate and lower-tail measures in this parameterization.

Cellular coordination consumes about 108.27 labour-hours per run, versus 28.59 for cooperative, 16.21 for market and 17.08 for central. This remains a major sustainability cost.

## 4. Household rationing rules

Paired changes relative to proportional allocation, under the same economic regime and seed.

### Priority-weighted allocation

| Regime | Change in lower-decile essential fulfilment | 95% paired CI | Change in essential Gini | 95% paired CI |
|---|---:|---:|---:|---:|
| Cellular | −10.29 pp | −10.87 to −9.71 | +0.08206 | +0.07851 to +0.08561 |
| Cooperative | −3.71 pp | −4.15 to −3.26 | +0.02725 | +0.02536 to +0.02913 |
| Central | −0.21 pp | −0.47 to +0.05 | +0.00320 | +0.00204 to +0.00437 |
| Market | +0.59 pp | +0.43 to +0.75 | −0.00050 | −0.00083 to −0.00017 |

Priority-weighted allocation is not universally worse: in this synthetic market arm it slightly improves the lower decile, while in cellular and cooperative arms it substantially worsens it. The result depends on the interaction between synthetic household priorities and each regime's physical allocation pattern. Random priorities are not a defensible proxy for need severity.

### Floor-priority allocation

The 50% floor-priority rule does not produce a robust lower-tail improvement. Its paired lower-decile change is −0.06 pp in cellular (CI −0.17 to +0.05), −0.33 pp in cooperative (−0.47 to −0.19), −0.07 pp in central (−0.21 to +0.08), and +0.12 pp in market (+0.06 to +0.19). The corresponding Gini changes are small but often positive. A nominal floor remains distinct from a feasible physical supply guarantee.

Across household rationing rules, aggregate physical consumption is effectively unchanged within each production regime in this experiment. The primary changes are in which households receive the delivered quantities.

## 5. Care-queue feedback versus zero-queue control

With backlog-first service, 0.5 retention and a one-period cap, compared with the same seeds and all other settings but zero care-queue retention and zero queue cap:

| Regime | Change in final-consumption index | 95% paired CI | Change in current essential fulfilment | 95% paired CI | Change in lower-decile fulfilment | 95% paired CI | Change in essential Gini |
|---|---:|---:|---:|---:|---:|---:|---:|
| Cellular | +20.20 | +18.78 to +21.62 | −2.80 pp | −2.97 to −2.64 | −2.78 pp | −3.10 to −2.47 | +0.01752 |
| Central | +23.93 | +11.41 to +36.44 | +0.73 pp | +0.16 to +1.31 | −0.35 pp | −0.87 to +0.17 | +0.01620 |
| Cooperative | +1.98 | +1.33 to +2.63 | +0.03 pp | −0.001 to +0.053 | −0.05 pp | −0.11 to +0.01 | +0.00099 |
| Market | +36.33 | +32.73 to +39.93 | +0.47 pp | +0.20 to +0.73 | −1.68 pp | −1.93 to −1.43 | +0.00527 |

The care queue increases measured final consumption in all four regimes, but the current-needs and lower-tail outcomes do not improve uniformly. The cellular arm in particular produces more final consumption while current food and current care fulfilment fall in this parameterization. The cooperative arm's changes in current fulfilment are small, while the market arm's lower-decile outcome deteriorates.

The decomposition of the paired change (care queue minus zero-queue control) is important:

| Regime | Change in current food fulfilment (95% paired CI) | Change in current care fulfilment (95% paired CI) | Change in combined essential fulfilment (95% paired CI) | Change in lower-decile fulfilment (95% paired CI) | Change in essential Gini (95% paired CI) |
|---|---:|---:|---:|---:|---:|
| Cellular | −0.60 pp (−0.96 to −0.25) | −12.09 pp (−12.94 to −11.24) | −2.80 pp (−2.97 to −2.64) | −2.78 pp (−3.10 to −2.47) | +0.01752 (+0.01328 to +0.02176) |
| Central | +1.45 pp (+0.45 to +2.46) | −2.27 pp (−5.43 to +0.90) | +0.73 pp (+0.16 to +1.31) | −0.35 pp (−0.87 to +0.17) | +0.01620 (+0.00480 to +0.02760) |
| Cooperative | −0.03 pp (−0.07 to +0.01) | +0.28 pp (+0.17 to +0.39) | +0.03 pp (−0.001 to +0.053) | −0.05 pp (−0.11 to +0.01) | +0.00099 (+0.00028 to +0.00171) |
| Market | +0.22 pp (−0.08 to +0.53) | +1.50 pp (+0.95 to +2.05) | +0.47 pp (+0.20 to +0.73) | −1.68 pp (−1.93 to −1.43) | +0.00527 (+0.00288 to +0.00766) |



This demonstrates why the final-consumption index cannot stand in for well-being: some additional deliveries clear older care claims rather than satisfying current-period needs. Report current food, current care, care-queue clearance and deprivation exposure separately.

## 6. Queue-service order: an attribution and priority sensitivity

Changing within-household care attribution from current-first to backlog-first leaves physical care deliveries, gross output, final consumption and ending care-queue quantity unchanged. It changes which claim is recorded as served.

| Regime | Current care fulfilment: current-first | Current care fulfilment: FIFO/backlog-first | Paired change in current care fulfilment |
|---|---:|---:|---:|
| Cellular | 72.78% | 49.43% | −23.36 pp (95% CI −23.71 to −23.00) |
| Central | 55.42% | 54.99% | −0.42 pp (−0.60 to −0.25) |
| Cooperative | 98.20% | 98.19% | approximately 0 |
| Market | 48.87% | 46.19% | −2.68 pp (−2.89 to −2.47) |

This sensitivity is deliberately visible because it changes current-care fulfilment without changing actual deliveries. The paired care-queue clearance metric makes the transfer explicit:

| Regime | Total care delivered (both rules) | Care backlog cleared: current-first | Care backlog cleared: FIFO/backlog-first | Additional backlog cleared under FIFO (95% paired CI) |
|---|---:|---:|---:|---:|
| Cellular | 46.26 | 0.39 | 15.11 | +14.72 (+14.52 to +14.92) |
| Central | 44.93 | 9.99 | 10.26 | +0.27 (+0.16 to +0.38) |
| Cooperative | 62.45 | 0.55 | 0.55 | +0.002 (−0.002 to +0.005) |
| Market | 39.27 | 8.46 | 10.15 | +1.69 (+1.56 to +1.82) |

Total physical food and care deliveries, gross output, final consumption and ending queue quantity are unchanged. Household-level food fulfilment can nevertheless move slightly because the allocator considers the combined essential claim when splitting goods among households; the service-order setting changes the care component of that claim. Thus report both physical product delivery and household allocation, rather than assuming that a fixed cell-level food flow implies identical household food fulfilment. FIFO/backlog-first is the default for the current prototype because it is the natural rule for an aged service queue, but it is not a neutral convention. The next implementation must record queue age and explicit service priority so that "which claim is cleared" is an auditable event rather than an implicit accounting choice.

## 7. Limitations

- 20 seeds are exploratory; held-out evaluation with at least 100 seeds is still required.
- Household needs, priority weights, care queue retention and production coefficients are synthetic.
- The market arm is still a physical market-matching control, not a complete ordinary market economy with household budgets, wages, wealth, purchasing power and endogenous prices.
- Central and cooperative arms are stylized controls, not complete real-world institutions with full governance, enforcement and information costs.
- No household labour supply, voluntary work, care-time budget, wages, ownership income, money, credit, debt service, household production or migration is modelled.
- Food deprivation units are not a health measure. Care queue units are not calibrated to actual clinical or care services.
- The final-consumption index is not GDP, value added, utility or a welfare measure.
- Only one seven-cell topology, one compound shock and one backlog parameterization are used here.
- Cellular coordination labour remains substantially higher than the other arms.

## 8. Decision and next steps

The typed C2-A2 model is more coherent than the initial generic-backlog version: recurring food shortfalls no longer create future food orders, while delayed care claims are represented as a separate queue. The new results do not show universal SCCE superiority. Cooperative allocation leads on aggregate consumption and overall fulfilment; cellular coordination remains costly; the market control has a severe lower-tail problem in this synthetic setup.

Next:
1. implement explicit age cohorts and expiry for care requests;
2. make service priority a published cell/household rule, not an implicit attribution switch;
3. test reserve capacity, redundancy and voluntary mutual-aid mechanisms to prevent care-queue accumulation;
4. add household time budgets, voluntary labour offers and unpaid care constraints;
5. introduce income, budgets and ownership only after the physical household-cell model is stable;
6. rerun with held-out seeds and alternative cell topologies.

**No claim that SCCE creates more real welfare than market, central or cooperative economies is justified yet.** The current model measures selected physical service and distribution indicators, not complete social welfare.
