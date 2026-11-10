# SCCE Stage C2 — Endogenous Household–Cell Economy

**Date:** 10 November 2026  
**Version:** 0.1  
**Status:** Research design; implementation not yet claimed  
**Parent:** [SCCE cellular engine and comparative experiment](SCCE_CELLULAR_ENGINE_AND_COMPARATIVE_EXPERIMENT_V0_2.md)  
**Predecessor:** [Stage C1 household physical distribution](SCCE_STAGE_C_HOUSEHOLD_DISTRIBUTION_V0_1.md)  
**Preliminary evidence:** [Stage C1 household distribution results](SCCE_STAGE_C1_PRELIMINARY_RESULTS_2026-11-10.md)

---

## 1. Why Stage C2 is required

Stage C1 made household-level distribution visible, but its household layer is post-hoc. Stage B decides how much physical consumption reaches each cell; Stage C1 then divides those already-consumed quantities among synthetic households. Household outcomes cannot yet change next-period production, cell membership, work, investment or demand composition.

That boundary is useful for isolating rationing, but it is not yet an endogenous household economy. Stage C2 closes the feedback loop between households and economic cells without assuming that money, tokens or accounting balances are equivalent to real welfare.

The central research question becomes:

> When households are explicit, heterogeneous agents whose needs, time, skills, income, participation and unmet essential claims feed back into local cell decisions, does a cellular economy produce more sustained and more equitably distributed real capabilities than matched market, central and cooperative institutions?

This remains a falsifiable question. Stage C2 must not be designed to guarantee a favourable SCCE result.

## 2. Four quantities that must never be conflated

For household h, product/service p and period t, keep four distinct objects:

1. **Normative or declared need** — the physical quantity required under the experiment's stated need model.
2. **Effective market demand** — the quantity the household is willing and able to purchase under its budget and current prices.
3. **Request or service claim** — a signed request submitted to a cell or public-service provider; a request is not a delivery or a contract.
4. **Actual fulfilment** — verified physical goods or services received at the required quality and time.

A household can have unmet need without effective purchasing power. A forecast is not a purchase order. A token or credit limit is not a physical good. A booked service is not a delivered service.

For every period, report both need-based fulfilment and budget-constrained consumption. Never use a high market-sales figure as a proxy for universal need satisfaction.

## 3. Household state and autonomy

A household agent has a persistent identity within the synthetic experiment and a state vector:

[
H_h(t)=(N_h,T_h,S_h,Y_h,B_h,A_h,D_h,C_h,W_h,E_h)
]

where:

- (N_h): essential and discretionary needs, quality requirements and unmet claims;
- (T_h): available time, care obligations, rest and voluntary work choices;
- (S_h): skills and productive capabilities;
- (Y_h): wages, transfers, ownership income and other income flows;
- (B_h): cash/deposit balances and liquid budget;
- (A_h): productive and household assets, ownership and encumbrances;
- (D_h): debt, maturity, arrears and explicitly authorized guarantees;
- (C_h): consent, cell memberships, service entitlements and participation mandates;
- (W_h): multidimensional well-being and service access indicators;
- (E_h): evidence, provenance, confidence and privacy permissions.

A household may participate in several cells and may leave or decline an offer subject to transparent contractual obligations. No model rule may compel work, confiscate property, penalize lawful exit or make basic rights conditional on an AI-generated score.

The household's capability and well-being vector must not be collapsed into a scalar measure of human worth. Any summary index is a diagnostic with disclosed components and weights.

## 4. Household–cell coupling

The household layer connects to the cellular economy through explicit, typed edges:

- **need/request:** household to a service or production cell;
- **work offer:** household to one or more cells, with skill, time window and conditions;
- **delivery:** cell to household, with quantity, quality and timestamp;
- **income/payment:** cell to household, with legal basis and settlement state;
- **membership/governance:** household to cell, with consent and decision rights;
- **care/community support:** household-to-household or cell-to-household service links.

A household request can be visible only to its chosen provider, authorized federation or explicitly consented discovery network. Personal need data must not be broadcast to all cells by default.

A cell's household-facing demand signal is an aggregate of authorized requests, not an unrestricted copy of household records. Public aggregate signals must be privacy-preserving and must not permit trivial re-identification in small cells.

## 5. Local household-to-cell transition

At the start of period t, each household generates:
- current essential needs;
- current discretionary needs;
- any permitted carry-over of unmet claims;
- voluntary work offers and time constraints;
- purchase requests constrained by its budget;
- requests for non-market or collectively funded services.

A local cell receives only authorized signals from its own members and eligible counterparties. It then forms a production/service proposal subject to:
- productive capacity and input availability;
- signed orders and credible requests;
- member-approved service obligations;
- liquidity and commitment limits;
- ecological and safety constraints;
- local essential-service rules.

The cell publishes proposals to its eligible neighbours. Cross-cell resource matching remains governed by Stage A/B consent, relay permissions, reservations and physical constraints. Household demand must not create a global all-seeing planner.

A candidate demand decomposition is:

[
D_{c,p}(t)=D^{current}_{c,p}(t)+D^{backlog}_{c,p}(t)
]

with current need, budget-backed demand and authorized service claims recorded separately. Backlog must be bounded, age-tagged and visible; it must not grow without limit or be counted repeatedly as new final consumption.

## 6. Feedback channels to test separately

Do not introduce all household feedback channels in one opaque model. Add and test them one at a time.

### C2-A — Endogenous household demand and unmet-need records

- Persistent household panel with heterogeneous needs.
- Household requests are aggregated into cell signals.
- Deliveries are allocated back to households.
- Unmet claims can be carried forward with a disclosed cap and expiry.
- Household and cell records reconcile exactly to the same physical quantities.
- A household allocation never creates a second delivery.

### C2-B — Voluntary time and productive participation

- Each household chooses an offered amount of time subject to a finite time budget.
- Paid work, care, self-production, rest and other uses are separate categories.
- No regime can assume unlimited labour or treat unpaid care as zero-cost.
- Participation rules, safety constraints and skill matching are identical across institutional comparisons.
- Labour supply response functions must be exposed as parameters and sensitivity-tested, not hidden inside an optimizer.

### C2-C — Income, purchasing power and ownership claims

- Wages are paid only against verified work or an explicit contractual milestone.
- Dividends are paid only from distributable surplus after reserves and obligations.
- Transfers have an identified funding source.
- Household budgets obey a cash-flow identity.
- Credit is a separate contract with principal, maturity, rate/fee, collateral if any, consent and default treatment.
- The existing accounting kernel and SFC work may serve as internal ledgers, but do not replace the cellular transition or determine physical output by themselves.

### C2-D — Endogenous production and service response

- Household orders, unmet essential claims and voluntary work offers feed back into local production proposals.
- Cells adapt inventories and capacity under local information.
- Cross-cell matching remains bounded by graph edges, capacity, lead time, consent and federation rules.
- Learning and policy adaptation remain separate from ordinary state transitions.

## 7. Essential services: a feasibility constraint, not a magic allocation rule

Stage C1 showed that a nominal essential floor cannot guarantee a minimum when total physical supply is below the sum of protected claims. In the compound-shock sample, the floor pool itself was rationed. A rationing formula cannot create missing food, care capacity, energy or medicine.

Stage C2 must therefore distinguish:

1. **Allocation protection:** who receives scarce available supply.
2. **Supply assurance:** reserves, redundant capacity, emergency procurement and mutual-aid commitments intended to make the protected floor physically feasible.
3. **Infeasibility disclosure:** when the supply assurance fails, the model records the shortfall; it does not fabricate delivery or hide the deficit with a token transfer.

A protected floor must be backed by explicit resource capacity, reserve funding, logistics and delivery commitments. Report the probability and duration of floor breach under shocks.

## 8. Fair institutional comparison

All institutional arms must start with identical:
- household population and need profiles;
- skills, available time and initial asset ownership;
- liquid balances, liabilities and credit constraints once finance is added;
- cell productive assets, stocks, technologies and input recipes;
- demand shocks, natural-resource endowments and ecological limits;
- information available at each decision time;
- quality standards, delivery windows and legal constraints;
- random seeds and exogenous events.

Compare at least:
1. market coordination with explicit household budgets and prices;
2. centralized allocation with a declared information and computation budget;
3. cooperative pooling with member governance and participation costs;
4. local cellular SCCE;
5. cellular SCCE with voluntary federation.

The centralized arm may be run with perfect information as a theoretical upper bound, but that result must be labelled as such. A realistic central arm must face the same information delays and data-quality limits as other regimes. The market and cooperative arms must include search, coordination, governance, enforcement and failure costs rather than being idealized or weakened.

## 9. Outcome vector: no single prosperity score

Report a vector of outcomes, not a winner-takes-all composite:

**Material and service outcomes**
- essential-need fulfilment by product and quality;
- discretionary fulfilment;
- service reliability, waiting time and unmet-need duration;
- household lower decile, minimum and worst-period outcomes.

**Distribution**
- household-level Gini and quantiles;
- between-cell and within-cell dispersion;
- concentration of ownership, income and productive assets;
- intergenerational or persistent deprivation indicators where the data permit.

**Time and agency**
- paid work hours;
- unpaid care hours;
- rest and discretionary time;
- voluntary participation, rejected offers and exit;
- unmet requests for work or services.

**Economic sustainability**
- physical output and value added, avoiding double counting of intermediate goods;
- household real consumption;
- productive investment and maintenance;
- liquidity, arrears, defaults and reserve adequacy;
- coordination, governance, dispute and enforcement labour.

**Ecological sustainability and resilience**
- resource extraction versus regeneration;
- emissions, waste and local ecological stocks;
- recovery time after shocks;
- essential-service continuity under network failures.

Any composite index must be secondary, with published weights and Pareto-frontier analysis. A regime should not be declared superior if it improves an average by imposing unacceptable lower-tail, rights, time or ecological losses.

## 10. Causal identification and anti-overfitting controls

- Use paired seeds and identical exogenous shock paths.
- Separate calibration seeds from held-out evaluation seeds.
- Pre-register primary outcomes and parameter ranges before large sweeps.
- Publish all regimes, including failures and negative controls.
- Run sensitivity to household need heterogeneity, priority dispersion, labour response, backlog persistence, market prices, reserve sizes and coordination costs.
- Include ablations: no household feedback, demand-only feedback, time/labour feedback, income/budget feedback and full household-cell coupling.
- Test adversarial cases: strategic misreporting, supplier concentration, cell exit, relay refusal, household privacy breach, delayed delivery and governance capture.
- Report uncertainty and effect sizes, not only point estimates or p-values.

## 11. Required invariants

1. Physical goods are conserved across production, inventories, transport, delivery and household allocation.
2. Every household allocation is backed by a cell delivery; no second counting of the same good.
3. Household claims are not silently converted into cash-backed demand.
4. Cash, debt and transfers reconcile; no unexplained money creation.
5. Labour hours allocated across paid work, care, self-production and rest do not exceed the household time budget.
6. No household or cell is compelled to accept a contract or relay a message.
7. No transaction crosses an unauthorized edge or counterparty allowlist.
8. No essential-floor guarantee is reported unless a feasible supply assurance exists.
9. Unmet claims, arrears and defaults cannot be erased by refinancing or relabelling.
10. Event replay is deterministic for a fixed seed and rule version.
11. AI adaptation cannot alter rights, ownership or member mandates outside authorized constitutional ranges.
12. Privacy controls prevent unauthorized disclosure of household-level sensitive data.

## 12. Implementation sequence and gate criteria

**C2-A1 — Demand panel:** persistent household needs, requests and privacy-scoped aggregation.  
**C2-A2 — Delivery bridge:** per-period household allocations reconcile to Stage-B physical delivery.  
**C2-A3 — Backlog dynamics:** bounded unmet-need carry-over and ageing, with tests against runaway demand.  
**C2-B1 — Time budget:** voluntary work/care/rest allocation and time conservation.  
**C2-B2 — Labour response:** transparent participation functions, sensitivity analysis and identical rules across regimes.  
**C2-C1 — Household budget:** wages, transfers, ownership income, consumption spending and cash conservation.  
**C2-C2 — Credit and reserves:** maturity, liquidity, consent, default and emergency support.  
**C2-D — Full endogenous comparison:** at least 100 paired held-out seeds and multiple network topologies.

Do not advance to the next gate until the current gate passes physical/accounting invariants, privacy and consent tests, deterministic replay and a negative-control experiment. A passing test establishes software correctness for that invariant, not empirical truth.

## 13. Current decision

Stage C1 establishes that distribution rules can change household lower-tail outcomes without changing aggregate physical consumption. Its 25/50/75% floor sensitivity also shows that a nominal floor may be ineffective or may leave too much residual allocation to arbitrary priority weights when supply is severely constrained.

The next implementation should therefore be **C2-A1: persistent household demand and privacy-scoped cell signals**, followed by a bounded unmet-need state. The first C2 build must remain physical and money-free. Finance is added only after the household-to-cell physical feedback is tested; the existing accounting models remain supporting subsystems.

**No conclusion about SCCE superiority is justified yet.** The model must earn that conclusion through matched, held-out comparisons that include material, distributional, time, ecological and institutional costs.
