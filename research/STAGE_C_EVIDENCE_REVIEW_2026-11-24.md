# Stage-C evidence review — 24 November 2026

**Evidence source:** GitHub Actions run 45424081523, artifacts `synergy-stage-c-experiment-evidence`  
**Scope:** Stage-C1 post-hoc household allocation and Stage-C2-A2 endogenous household/backlog experiment  
**Status:** preliminary synthetic simulation evidence; not calibrated empirical economics

## 1. Reproducibility and execution

The prototype-validation job completed successfully on commit `669aa52332acd93150432a7f44e7e9306c7aa877`. Its full prototype unit-test step passed (494 tests). The job also completed the existing Stage-B Monte Carlo and Stage-C experiments and uploaded the Stage-C evidence archive.

The separate cross-repository job failed in the Maps viewer build step because npm terminated with `Cannot read properties of null (reading 'edgesOut')`. This is a Maps frontend integration failure, not a failure of the economic prototype test job. Cross-repository integration is therefore not fully green.

## 2. Stage-C1: household allocation sensitivity

Design: 20 paired seeds, 24 periods, compound shock, two-hop local reach, 10 synthetic households per cell, priority dispersion 0.4. The Stage-B physical trajectories are held fixed while household allocation rules are compared. This is a post-hoc decomposition: it cannot alter production, cell-level deliveries or aggregate physical consumption.

The 25%, 50% and 75% essential-floor settings were run as separate sensitivity cases. They change the `floor_priority` rule, not the proportional or priority-weighted rules. The aggregate essential fulfilment for the floor-priority rule remained approximately 0.4422 across all three settings; lower-decile fulfilment rose modestly from 0.1957 (25%) to 0.2036 (50%) and 0.2044 (75%) when averaged across the four economic regimes. This is not evidence of a large or universal floor effect.

At the 50% setting, paired differences from proportional allocation show:
- Under the cellular regime, floor-priority was effectively neutral on the lower-decile metric: +0.0003, 95% interval [-0.0010, +0.0015].
- Under the cooperative regime, it was slightly worse on the lower-decile metric: -0.0021, 95% interval [-0.0039, -0.0003].
- Under the central regime, it was slightly worse: -0.0008, 95% interval [-0.0019, +0.0003].
- Under the market regime, it was effectively neutral: approximately 0.0000, 95% interval [-0.0004, +0.0004].

Priority-weighted allocation was materially worse than proportional for lower-decile fulfilment in the cellular and cooperative regimes in this setup. This cautions against assuming that unequal priority weights necessarily improve distributional outcomes.

## 3. Stage-C2-A2: endogenous household/backlog experiment

Design: 20 paired seeds, 24 periods, compound shock, two-hop local reach, 10 synthetic households per cell, priority dispersion 0.4, backlog retention 0.5, maximum backlog 1.0 period, maximum care-queue age 3 periods.

Under proportional household allocation, selected means (n=20; intervals are the reported 95% normal intervals across seeds) were:

| Regime | Lower-decile essential fulfilment | Household essential Gini | Unmet food units |
|---|---:|---:|---:|
| Market | 0.0412 [0.0384, 0.0440] | 0.4181 [0.4142, 0.4221] | 140.69 [138.75, 142.63] |
| Central | 0.1345 [0.1286, 0.1403] | 0.3245 [0.3099, 0.3392] | 156.05 [152.88, 159.22] |
| Cellular | 0.2882 [0.2828, 0.2937] | 0.2030 [0.1979, 0.2082] | 166.71 [164.57, 168.85] |
| Cooperative | 0.3039 [0.2985, 0.3092] | 0.2081 [0.2034, 0.2128] | 181.48 [179.53, 183.44] |

In this particular synthetic scenario, cellular and cooperative regimes produce substantially higher lower-decile fulfilment and lower household inequality than the market regime, but also more unmet food units and lower aggregate current essential fulfilment. The cooperative regime has the lowest ending essential backlog and much lower care-claim attrition than the market regime in this run configuration. These are trade-offs, not a single scalar victory.

Crucially, household allocation policies redistribute the same physical supply. They do not reduce unmet food at the cell/economy level by themselves. Changes in lower-tail fulfilment should not be reported as newly created output or as proof of higher GDP or welfare.

## 4. Interpretation and limitations

1. The household population, needs and priorities are synthetic. No household survey calibration or real-world validation is present.
2. The experiment uses a small seed count (20) and one compound-shock configuration for this evidence bundle. Broader shock, parameter and seed coverage is required.
3. The reported intervals describe variation across simulation seeds under the model; they are not empirical confidence intervals for a real economy.
4. Stage-C1 is explicitly post-hoc. Stage-C2-A2 adds backlog/claim dynamics but remains a stylized model, not a field-tested institutional intervention.
5. Aggregate production, essential access, distributional tails, backlog, attrition and coordination costs must remain separate outcome dimensions. No composite score should conceal a trade-off.

## 5. Next experiments

- Expand to at least 100 paired seeds for the strongest Stage-C2-A2 comparisons.
- Run a factorial grid over shock type/severity, local reach, backlog retention, household floor and care-queue expiry.
- Add sensitivity to household size and within-cell needs heterogeneity, with explicit calibration ranges.
- Add coordination and administration costs to the same outcome ledger.
- Preregister primary metrics and non-inferiority thresholds before running the expanded grid.
- Keep all results paired by seed and preserve raw per-seed evidence; report effect sizes and intervals, not only averages.

**Conclusion:** the evidence supports continued investigation of cellular/cooperative coordination as a distributional trade-off worth testing. It does not establish general superiority. The next milestone is robustness and calibration, not a stronger marketing claim.
