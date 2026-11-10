# A2.4.6 — preregistered net-synergy estimand

**Date:** 11 November 2026  
**Branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Status:** measurement/identification contract; not an empirical result.

## 1. Estimand

The starting definition in Volume II §24 is retained:

[
S_{net}(C)=
Delta Y_{observed}
-Delta Y_{extra inputs}
-C_{coord}
-C_{integration}
-C_{external}
-C_{risk}.
]

It is valid as a scalar only when all terms are converted to a compatible, explicitly justified valuation basis and no cost is deducted twice. Otherwise the primary result is a vector:

[
mathbf S_{net}=(S_{output},S_{quality},S_{capability},
S_{resilience},S_{ecology},S_{distribution}).
]

A2.4.6 fixes the comparison protocol; it does not authorize collapsing the vector into one arbitrary score.

## 2. Counterfactual

For each treatment regime (r) and matched exogenous scenario/seed (s), define:

[
Delta Y_{k,s}(r,b)=Y_{k,s}(r)-Y_{k,s}(b),
]

where (b) is a credible alternative without the treatment being evaluated. The baseline is not zero activity. It may be market contracting, an existing firm hierarchy, a cooperative, public provision or another network design. The selected comparator and why it is credible must be preregistered.

For four-regime SCCE comparisons, each regime receives identical:
- opening physical stocks and asset cohorts;
- household needs/capabilities and initial distribution;
- technology and production recipes;
- resource/ecological state and boundary;
- exogenous shocks, timing and random seed;
- accounting and metric definitions.

Common random numbers support paired comparisons; they do not by themselves establish causal identification.

## 3. Additional inputs and costs

Measure incremental differences relative to the comparator, not gross totals:

[
Delta X=(Delta labour,Delta capital services,Delta materials,
Delta energy,Delta land/water,Delta public subsidy,
Delta data/infrastructure,Delta risk exposure).
]

Include unpaid labour, training, coordination hours, software, governance, monitoring, dispute resolution, switching, delays, security, maintenance, subsidies and costs shifted to third parties. If an input is already included in an observed net outcome or intermediate cost, do not subtract it again.

A scalar valuation is permitted only when:
- the price basis and period are consistent;
- shadow prices for non-market inputs are disclosed;
- distributional and ecological constraints are reported separately;
- uncertainty ranges and sensitivity to valuation are published.

Where inputs/outcomes are not commensurable, report the vector and constraint violations. Do not manufacture a scalar to force a ranking.

## 4. Outcome vector and hierarchy

The preregistration must select one or more primary outcomes before results are observed. A defensible SCCE vector includes:
- delivered final goods/services by product in native units;
- essential-need fulfilment, including lower decile and minimum household outcome;
- quality/reliability and unmet need/backlog by age;
- productive services and capital condition;
- labour/coordination time and rest constraints;
- resource extraction, emissions/pollution, water and residual stocks;
- net income/wealth and debt burden once the financial layer is validated;
- distribution, inequality, rights, consent and exclusion.

Aggregate consumption or final-consumption index alone is not a welfare or synergy measure. A backlog can increase recorded final delivery while worsening current unmet needs. Intermediate turnover, loans, deposits, asset-price appreciation and token transactions are not primary synergy outcomes.

## 5. Estimation and uncertainty

For paired seeds (s=1,ldots,n), estimate:

[
widehat{	au}_k(r,b)=rac1nsum_s
left(Y_{k,s}(r)-Y_{k,s}(b)ight).
]

Report the paired distribution, confidence/credible interval as appropriate, seed count, exclusions, missingness, sensitivity and all run/code/data hashes. For non-linear or path-dependent outcomes, retain per-seed trajectories and terminal states; do not rely only on the mean.

Pre-register:
- primary/secondary outcomes and signs;
- comparator regimes;
- seed generation and sample size;
- horizon and burn-in;
- scenario/shock distributions;
- treatment definition and compliance;
- stopping/exclusion rules;
- aggregation/weighting and uncertainty method;
- minimum practically important effect;
- adverse outcomes and falsification conditions.

A synthetic ABM comparison identifies the effect of the model's rules under its assumptions, not an empirical effect in a real economy. Empirical claims require external data, a defensible identification design and external-validity discussion.

## 6. Falsification and guardrails

A positive synergy claim is not supported if:
- output rises only because more labour, capital, energy or materials were added and these are not accounted for;
- results disappear under a credible baseline or reasonable parameter sensitivity;
- costs are shifted to unpaid workers, other regions, the public sector or ecosystems;
- lower-tail fulfilment, rights, safety or ecological hard constraints materially worsen;
- gains come from double-counted intermediate output, financial transfers or revaluation;
- treatment and comparator do not share initial states and shocks;
- results cannot be reproduced from frozen seeds and code/data hashes.

No weighted average may compensate for a hard rights violation or an ecological threshold breach. Pareto dominance and constraint satisfaction should be reported before any optional scalar ranking.

## 7. Current status

Volume II §24 already contains the conceptual estimand and causal-identification cautions. Existing SCCE reports contain paired synthetic comparisons but are not empirical estimates. This document makes the protocol operational; A2.4.6 remains open until a preregistered run and independent reproduction pass.


## 8. Source-code audit of existing experiments

See `A2_4_6_EXISTING_EXPERIMENT_PROTOCOL_AUDIT.md` for the exact regime list,
market comparator, paired seed loop, existing Stage-B and Stage-C2-A2
configuration, emitted outcome metrics and statistical helper recovered from
the repository's actual Python implementations and CI commands.

This inspection closes the uncertainty about which regimes and settings
already exist. It does **not** retroactively preregister prior runs. The current
experiments remain exploratory synthetic comparisons: they do not declare
primary endpoints, a minimum practically important effect, complete
incremental-input accounting, missingness/exclusion rules or a confirmatory
held-out seed design. A2.4.6 remains open.
