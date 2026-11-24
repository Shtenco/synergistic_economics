# Stage-C evidence review — 24 November 2026 (refreshed)

**Evidence source:** GitHub Actions run [45432821623](https://github.com/Shtenco/synergistic_economics/actions/runs/45432821623), exact Economics head `a055522c3a27fe31d665977b2e5f6ee51a4bf5a6`, artifact `synergy-stage-c-experiment-evidence` (artifact ID `14940865401`, SHA-256 `7add50d20dd93a44de6b6392b9647fa111754bfb729afb82e83f5a770a26d40d`).

**Status:** completed, reproducible synthetic simulation evidence; not calibrated empirical economics and not a causal estimate for a real population.

## 1. Execution and reproducibility

The exact-head `test-economic-prototypes` job completed successfully. It passed the prototype unit tests, baseline and compound-crisis simulations, input-output simulations, fixed-asset and capital-cohort audits, Stage-B comparisons (including 100-seed paired scenarios), coordination-labour sensitivity/frontier runs, and all Stage-C jobs.

Stage-C evidence contains four JSON outputs:
- Stage-C1, 50% essential floor: 100 paired seeds × 4 economic regimes × 3 household allocation policies = 1,200 paired rows.
- Stage-C1 floor sensitivities at 25% and 75%: 20 paired seeds each × 4 regimes × 3 policies = 240 rows per file.
- Stage-C2-A2 endogenous household/backlog: 100 paired seeds × 4 regimes × 3 policies = 1,200 paired rows.

Each scenario has 24 periods, compound shock, two-hop local reach, 10 synthetic households per cell and priority dispersion 0.4. Stage-C2-A2 additionally uses backlog retention 0.5, backlog-first service, maximum backlog 1.0 period and maximum care-queue age 3 periods.

The reported 95% intervals are simulation-seed intervals from the experiment output. They do not represent empirical uncertainty about real economies. Paired differences are calculated within matched seeds; do not substitute differences between independent confidence intervals for the paired intervals.

## 2. Stage-C1 — household allocation and essential floor

The Stage-C1 experiment holds each Stage-B physical trajectory fixed and compares household allocation rules after production and delivery. It therefore tests distribution of a fixed supply, not production effects.

### 2.1 Primary 100-seed result: 50% essential floor

For the cellular regime:
- Proportional allocation lower-decile essential fulfilment: 0.3182 (95% interval 0.3157–0.3207); household essential Gini: 0.1841 (0.1820–0.1862).
- Floor-priority allocation lower-decile fulfilment: 0.3187 (0.3163–0.3211); Gini: 0.1842 (0.1821–0.1862).
- Paired floor-priority minus proportional lower-decile difference: +0.00051 (paired 95% interval +0.00004 to +0.00098); Gini difference: +0.00006 (−0.00006 to +0.00019).

For the cooperative regime:
- Proportional lower-decile fulfilment: 0.3089 (0.3067–0.3111); Gini: 0.2057 (0.2037–0.2077).
- Floor-priority lower-decile fulfilment: 0.3074 (0.3052–0.3096); Gini: 0.2087 (0.2067–0.2106).
- Paired lower-decile difference: −0.00148 (−0.00221 to −0.00075); Gini difference: +0.00297 (+0.00281 to +0.00314).

For the central regime, floor-priority changes lower-decile fulfilment by −0.00058 (−0.00095 to −0.00020) and Gini by +0.00119 (+0.00094 to +0.00144), relative to proportional allocation.

For the market regime, the paired lower-decile difference is +0.00022 (approximately 0.00000 to +0.00044) and the Gini difference is −0.00036 (−0.00044 to −0.00029).

Priority-weighted allocation is materially worse than proportional allocation for the lower decile in the cellular regime (−0.08133; paired interval −0.08387 to −0.07880) and cooperative regime (−0.03462; −0.03654 to −0.03270). This is a strong warning against treating priority weights as inherently equitable.

### 2.2 Floor sensitivity

The 25% and 75% floor sensitivity runs remain at 20 paired seeds. They are exploratory sensitivity checks, not equally powered replications of the 100-seed primary experiment.

Across these settings, the floor rule does not dominate proportional allocation consistently:
- At 25%, lower-decile fulfilment under floor-priority is below proportional in the cellular and cooperative regimes.
- At 75%, it is approximately neutral in cellular and slightly below proportional in cooperative.
- The central regime remains weakly below proportional at both settings.
- Market-regime differences are small.

The floor parameter should not be promoted as a universal fairness improvement. Its effects depend on institutional regime and allocation design.

## 3. Stage-C2-A2 — endogenous household needs, backlog and care claims

This experiment changes the dynamic household state: unmet needs can persist as backlog and care claims age/attrit. Unlike Stage-C1, this can influence subsequent allocation and service dynamics, but it remains a stylized synthetic model.

### 3.1 Proportional allocation: regime means

All values below are means over 100 paired seeds; intervals are 95% simulation-seed intervals.

| Regime | Current overall fulfilment | Current essential fulfilment | Current food fulfilment | Current care fulfilment | Essential Gini | Ending essential backlog | Attrited care claims | Coordination hours |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Market | 0.47484 | 0.46907 | 0.47158 | 0.45858 | 0.41859 | 0.44907 | 23.18558 | 16.15890 |
| Central | 0.45240 | 0.44101 | 0.41472 | 0.55196 | 0.32502 | 0.81114 | 16.78667 | 17.07060 |
| Cellular | 0.43665 | 0.39918 | 0.37721 | 0.49198 | 0.20074 | 0.66548 | 16.15863 | 107.95848 |
| Cooperative | 0.51206 | 0.44654 | 0.31991 | 0.98124 | 0.20722 | 0.02120 | 0.59275 | 28.58080 |

Selected 95% intervals:
- Cooperative current overall fulfilment: 0.51059–0.51353.
- Cooperative current essential fulfilment: 0.44500–0.44808.
- Cooperative current food fulfilment: 0.31818–0.32164.
- Cooperative current care fulfilment: 0.97855–0.98393.
- Cooperative ending essential backlog: 0.01556–0.02684.
- Cooperative cumulative attrited care claims: 0.50768–0.67781.
- Cooperative coordination hours: 28.52163–28.63997.
- Market current overall fulfilment: 0.47327–0.47641.
- Market current food fulfilment: 0.46890–0.47426.
- Market coordination hours: 16.10919–16.20861.

### 3.2 Paired cooperative-minus-market differences

For proportional allocation, matched-seed differences are:
- Current overall fulfilment: +0.03722 (paired 95% interval +0.03615 to +0.03830).
- Current essential fulfilment: −0.02253 (−0.02423 to −0.02083).
- Current food fulfilment: −0.15167 (−0.15427 to −0.14907).
- Current care fulfilment: +0.52266 (+0.51820 to +0.52711).
- Ending essential backlog: −0.42786 (−0.53466 to −0.32107).
- Cumulative attrited care claims: −22.59284 (−22.77202 to −22.41365).
- Cumulative household essential Gini: −0.21137 (−0.21384 to −0.20889).
- Fixed-price gross output index: +24.39571 (+22.12560 to +26.66582).
- Total coordination hours: +12.42190 (+12.34524 to +12.49856).

This is not a single-direction victory. The cooperative configuration materially improves care fulfilment, backlog and distributional inequality in this model, while food fulfilment is substantially lower and coordination requires more labour. Essential fulfilment is also slightly lower than market. The cellular configuration has lower inequality than market but lower overall and essential fulfilment, higher backlog, and a very large coordination-hours burden (about 108 versus 16.2 market hours). That coordination burden is a major model finding and a priority for decomposition, not a detail to hide.

### 3.3 Interpretation constraints

1. Higher care fulfilment and lower attrition do not erase the food/essential-access trade-off.
2. The coordination-hours difference must be included in any efficiency or welfare interpretation. It must not be silently treated as free labour.
3. Fixed-price output and consumption indices are model indices, not national-account GDP or market prices.
4. Lower inequality is not itself proof of higher total welfare; no single composite score should conceal access, output, backlog, care, food and labour trade-offs.
5. Allocation policies redistribute and prioritize within the model's supply and service constraints. Do not report a distributional gain as newly created physical output.
6. The 100 seeds reduce Monte Carlo noise for these specified parameters but do not solve model misspecification, synthetic-household calibration, or external validity.

## 4. HardNAV V4 replay — separate integration evidence

The same workflow's separate `hardnav-v4-historical-replay` job completed successfully and uploaded artifact `14942210437` (SHA-256 `7c20904ffefaf45884b45721d7ee4c2e605a0a17dec09c9656170270ad2befa2`).

The replay validated 13,000 contiguous Ethereum blocks (23,544,921–23,557,920), with 10,000 TRAIN and 3,000 OOS blocks, continuous state without reset, weights frozen after training and hedge-anchor selection using TRAIN only. The OOS segment was not used for selection.

Reported deterministic replay:
- TRAIN return: +0.16407%; OOS return: +0.05033%; full return: +0.21448%.
- Full maximum drawdown: 0.18328%; OOS maximum drawdown: 0.06538%.
- 89.78% of per-step returns were negative despite the small positive aggregate return.

Important data/model limitations:
- Price alignment uses last completed one-minute candles and causal forward-fill; zero future-candle violations were reported.
- Maximum forward-fill staleness varies materially by asset: VVV 1,500 seconds; cbETH 660 seconds; MORPHO 360 seconds; AERO 180 seconds. These stale intervals can materially affect valuation and must be stress-tested.
- cbBTC and cbXRP are priced using underlying BTC/XRP market feeds as 1:1 redeemable-underlying proxies, not independent wrapper-market prices.
- Gas base fees are cross-checked against Ethereum PublicNode RPC, but strategy gas units are modeled from configuration and priority tips are excluded.
- Modeled bridge and external AMM fee estimates are explicitly excluded from HardNAV. Observed bridge and AMM transaction fee revenue is zero in this replay; no external fee journal is configured, verified or balanced.
- This is one deterministic historical replay, not live execution, a repeated out-of-sample study, or evidence of deployable profitability.

## 5. Integration CI status

For exact Economics head `a055522c3a27fe31d665977b2e5f6ee51a4bf5a6`, workflow run [45432821623](https://github.com/Shtenco/synergistic_economics/actions/runs/45432821623) completed all three jobs successfully:
- `test-economic-prototypes`: success.
- `cross-repository-contract`: success, including Maps Python trust/spatial tests, Cesium build, global Maps viewer npm install/tests/build, EAEU plan verification, Kazakhstan Overture smoke and HardNAV accounting regressions.
- `hardnav-v4-historical-replay`: success, including evidence validation and artifact upload.

The minimal Maps dependency fix commit `24581ccfea6911a01370233e0b4bdc1d57185aaa` was therefore validated by the consuming Economics workflow. The separate standalone Maps PR CI runner still did not expose job steps/logs; its status is unresolved, not a demonstrated source/test failure.

## 6. Next experiments and engineering gates

1. Decompose coordination labour by task, actor and regime; test whether cellular coordination hours reflect genuine work, duplicated accounting or an over-scaled coordination mechanism.
2. Add a sensitivity frontier for coordination productivity, paid/unpaid labour valuation, congestion and coordination failure. Report both physical hours and valued opportunity cost.
3. Test food/essential/care service capacity jointly; inspect whether the cooperative care priority crowds out food and whether the result changes under capacity constraints and minimum service floors.
4. Expand the 25% and 75% floor sensitivities to 100 paired seeds before drawing fine-grained conclusions.
5. Run factorial robustness across shock severity/type, local reach, household heterogeneity, backlog retention, care expiry and household size.
6. Preregister primary metrics and non-inferiority thresholds; preserve raw per-seed outputs and paired seed alignment.
7. Calibrate household needs and production/service capacities against real data before making policy or welfare claims.

**Conclusion:** the 100-seed Stage-C evidence is now complete and reveals robust simulated trade-offs, not general superiority. Cooperative coordination performs strongly on care, backlog and inequality in the tested scenario but sacrifices food access and consumes additional coordination labour. Cellular coordination's labour burden is especially important. The correct next milestone is causal-mechanism diagnosis, coordination-cost accounting and calibration—not stronger claims.
