# A2.4.6 — audit of existing SCCE experiment protocol

**Date:** 11 November 2026  
**Status:** source-code audit of existing synthetic experiments; not a preregistration and not empirical validation.

## 1. Scope and source basis

This audit inspects the actual experiment implementations rather than selecting new regimes or inventing parameters:

- `prototype/scc_dynamic_economy.py`
- `prototype/scc_endogenous_household_experiment.py`
- `prototype/scc_household_experiment.py`
- `prototype/cellular_coordination.py`
- `.github/workflows/prototype-validation.yml`

The code and workflow define reproducible exploratory experiments. They do not yet define a confirmatory A2.4.6 preregistration with frozen primary outcomes, a minimum practically important effect, exclusions, or a complete incremental-input account.

## 2. Actual economic regimes and comparator

The economic policy tuple in `scc_dynamic_economy.py` is:

1. `market`
2. `central`
3. `cooperative`
4. `cellular`

The paired Monte Carlo routine runs all four policies for each seed, with the same seed, shock and horizon, and reports paired differences against `market`. This is an actual implementation-defined comparator, not a new comparator invented for this audit.

The household experiment additionally compares three allocation policies:

- `proportional`
- `priority_weighted`
- `floor_priority`

It reports economic-policy differences against market within the same household policy, and household-allocation differences against proportional within the same economic policy.

## 3. Existing horizons, seeds and scenarios

| Experiment | Existing code/workflow configuration | Interpretation |
|---|---|---|
| Stage-B Monte Carlo function | default 100 runs; seeds 1…100; 24 periods; 2 cellular hops; default shock `none` | paired synthetic regime comparison |
| Stage-B CI baseline | 100 seeds; 24 periods; no shock; 2 hops | reproducibility/stress baseline |
| Stage-B CI compound stress | 100 seeds; 24 periods; compound shock; 2 hops | synthetic stress comparison |
| Stage-B CI reach sensitivity | 100 seeds; compound shock; 1, 2 and 3 hops | sensitivity to cellular reach |
| Stage-C2-A2 CI experiment | 20 runs; seeds 1…20; 24 periods; compound shock; 2 hops; 10 households/cell; priority dispersion 0.4; essential floor 0.5; backlog retention 0.5; max backlog 1.0 period; max queue age 3 periods; backlog-first service | paired four-economic-policy × three-household-policy synthetic comparison |

The Stage-C2-A2 workflow leaves the economic and household policy lists at the script defaults, which are all four economic regimes and all three household allocation policies. The seed loop is explicitly `range(1, runs + 1)`.

These are existing exploratory settings. Reusing them does not retroactively make prior outputs preregistered. No new seed range, sample size, horizon or exclusion rule is selected in this audit.

## 4. Outcomes already emitted by the code

The Stage-C2-A2 experiment's `METRICS` tuple contains the following outcomes:

- current essential, food, care and overall fulfilment;
- total food and care delivered;
- cumulative care backlog served;
- cumulative unmet food;
- expired, attrited and unqueued care claims;
- cumulative lower-decile and minimum current essential fulfilment;
- cumulative household essential-fulfilment Gini;
- mean-period lower-decile fulfilment and worst-period minimum fulfilment;
- ending and peak essential backlog;
- fixed-price final-consumption and gross-output indices;
- total coordination hours.

The Stage-B model additionally emits product output/consumption, unmet final units, input shortages, logistics and coordination costs, communication costs, resource extraction/regeneration/ending stock, inventory value, event count and event-log digest.

**Critical gap:** the code emits many metrics but does not identify a frozen primary/secondary outcome hierarchy. The presence of a metric in a summary is not a preregistered primary endpoint. No single scalar net-synergy estimate is justified by the current metric list.

## 5. Existing statistical procedure and limitations

The current helper computes mean, median, sample standard deviation and a nominal 95% interval using:

`mean ± 1.96 × sample_sd / sqrt(n)`.

Paired differences are computed seed-by-seed against market or proportional. This correctly preserves common random numbers for the paired comparisons.

However, the current procedure does not implement:
- a Student-t critical value or a bootstrap/randomization interval;
- a preregistered primary endpoint and multiplicity hierarchy;
- a predeclared minimum practically important effect;
- explicit missing-run and exclusion accounting;
- a formal stopping rule;
- distribution diagnostics or robust interval sensitivity;
- a confirmatory held-out seed set;
- a separate causal-identification argument beyond the model's paired stochastic design.

For n=20, the normal 1.96 approximation is not automatically adequate. For skewed, bounded, zero-inflated or path-dependent metrics, the mean interval may not describe the distribution well. This is a methodological limitation to fix before confirmatory claims, not evidence that the current exploratory comparisons are invalid as code experiments.

## 6. Net-synergy accounting gap

The Stage-B model exposes coordination hours, logistics/coordination/communication costs, physical resource use and output/consumption indices. The Stage-C2-A2 metrics include coordination hours and household outcomes.

The current experiment does not yet provide a complete, non-overlapping incremental-input vector for each regime covering:
- labour and unpaid care by task and person-time;
- capital services and capital consumption;
- material and energy inputs by native unit;
- water, land, ecological depletion and pollution;
- public subsidies, governance, monitoring, dispute resolution and risk;
- externalized costs and effects on non-participants.

The financial layer is intentionally outside the current SCCE physical experiment. Therefore financial income, wealth, debt and credit cannot be included as validated SCCE outcomes yet. Do not compute `S_net` by subtracting only coordination hours or by monetizing unrelated indices.

## 7. A2.4.6 disposition

**What is closed by source inspection:** the actual regime list, market comparator, common-seed pairing, existing horizons, existing CI scenario matrix, outcome fields and current summary-statistic method have been recovered from code.

**What remains open:** primary/secondary outcome hierarchy, treatment definition for a specific institutional feature, complete incremental-input account, adverse-outcome constraints, practically important effect, exclusions/missingness, confirmatory seed design, statistical method and independent reproduction.

**Decision:** the current experiments are suitable for exploratory synthetic comparison and software regression. They must not be relabelled as preregistered evidence of net synergy or empirical superiority. A2.4.6 remains open until a new confirmatory protocol is frozen before its results are generated and all required input/outcome registers are available.
