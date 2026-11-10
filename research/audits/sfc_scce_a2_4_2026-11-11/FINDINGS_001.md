# A2.4 continuation — independent SFC/SCCE audit, 11 November 2026

**Audit branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Canonical source branch:** `main` (not modified)  
**Scope:** resume after A2.3 at A2.4; no integrated economic engine is implemented or proposed here.

## Executive decision

The six-sector synthetic SFC example is arithmetically closed for its stated one-period assumptions. Its main debt mirror positions and sectoral capital/financial-account balances reconcile. That is a useful accounting control, not empirical validation and not yet a dynamic economic model.

Three cross-volume problems remain blocking:
1. **A2-44 — incompatible state spaces** across Volumes VIII, IX and XV. A single untyped state vector would conflate stocks, flows, rights, network structure, outcomes and uncertainty.
2. **A2-46 — capital stock / productive capacity / capital services / depreciation are not cleanly separated.** This creates a risk of counting wear once in capital-stock evolution and again in the production/service function, or of treating GFCF as a direct increment to services.
3. **A2-48 — two different credit mechanisms are mixed:** commercial-bank loan origination that creates a matching deposit, versus a non-bank transfer of an already-existing financial asset/deposit. They have different system-wide money effects and must be distinct event types.

Five mandatory A2.4 control directions remain:
- **A2.4.1 Canonical state/transition:** typed registers, stock/flow/event/rule/outcome time types, and explicit transition boundaries.
- **A2.4.2 Capital stock/services bridge:** gross and net stocks, vintage/productive efficiency, CFC, retirement, repair, utilization and service flow.
- **A2.4.3 Production dimensional contract:** product-specific natural units, recipes, yield/loss/waste, valuation price basis and bridge to monetary output/GVA.
- **A2.4.4 Financial event/balance bridge:** double-entry event types, instrument-holder-issuer mirror, payment settlement, SFC accounts, revaluation and other volume changes.
- **A2.4.5 Labour/capability bridge:** human capabilities and available time as distinct stocks/constraints; paid/unpaid work and consented participation as interval flows; no automatic conversion of contribution into rights.

A2.4.6 (synergy estimand) and A2.4.7 (automated test suite) remain cross-cutting controls. The next integrating test is **A2.4.8 — one end-to-end numerical experiment** that instantiates all interfaces without merging them into an executable economic engine.

## 1. Reproducible six-sector SFC closure

Frozen source: `research/FULL_SIX_SECTOR_SFC_NUMERICAL_CLOSURE.md`, blob SHA `383ffdcc88ce28035c6e00eacd8b7d80e6a2211c`.

### 1.1 Product and GDP

[
149+30=30+55+19+68+7=179.
]
[
GDP_{production}=149-30=119,
quad GDP_{income}=60+4+55=119,
]
[
GDP_{expenditure}=55+19+68+7-30=119.
]

All three approaches and the product supply/use table agree exactly. These are accounting identities in a synthetic single-product example, not an estimated production function.

### 1.2 Sectoral saving and net lending

| Sector | Saving | GCF | Capital-account net lending |
|---|---:|---:|---:|
| H | 7 | 0 | +7 |
| NFC | 49 | 68 | −19 |
| CB | 4 | 0 | +4 |
| CBank | 0 | 0 | 0 |
| GOV | −15 | 0 | −15 |
| ROW | +23 | 0 | +23 |
| **Total** | **68** | **68** | **0** |

[
NL_s=S_s+KTr_s-GCF_s-NPNA_s.
]
In this example (KTr=NPNA=0), so (NL=S-GCF). ROW's +23 is the external current-account surplus/financing position in the example, not resident-sector saving in the ordinary household/firms sense.

### 1.3 Financial account and debt mirrors

| Sector | Net acquisition of FA | Net incurrence of FL | Financial net lending |
|---|---:|---:|---:|
| H | +7 | 0 | +7 |
| NFC | 0 | +19 | −19 |
| CB | +19 | +15 | +4 |
| CBank | 0 | 0 | 0 |
| GOV | 0 | +15 | −15 |
| ROW | +23 | 0 | +23 |
| **Total** | **49** | **49** | **0** |

Mirror checks:
- Deposits: (107_H+8_{ROW}=115=CB) deposit liabilities.
- Loans: (30_H+99_{NFC}=129=CB) loan assets.
- Reserves: (30_{CB}=30_{CBank}).
- Government bonds: (10_H+40_{CBank}+15_{ROW}=65=GOV) liabilities.
- External reserve asset: (10_{CBank}=10_{ROW}) external liability.

Capital and financial net lending agree for all six sectors. Opening-to-closing net worth changes are (+7,+49,+4,0,-15,+23); sum (+68), matching NFC's increase in produced capital from 200 to 268 under the deliberately no-depreciation/no-revaluation assumptions.

Independent executable check: `audit_sfc_six_sector.py`. It uses Decimal and asserts every equation and mirror above plus the B2 physical controls.

## 2. Important accounting nuance: credit creation vs deposit transfer

Two events must not share one generic "loan" handler.

**Commercial-bank loan origination** (19 D.E.):
- bank: loan asset +19;
- borrower: loan liability +19;
- bank: deposit liability +19;
- borrower: deposit asset +19.

This creates a matching deposit at origination. Later spending transfers the deposit to a seller; it does not create another deposit.

**Non-bank loan from an existing deposit** (19 D.E.):
- lender: deposit asset −19 and loan asset +19;
- borrower: deposit asset +19 and loan liability +19.

System-wide deposits change by zero. The lender transfers existing purchasing power; it does not create bank money.

In the six-sector example, the +19 bank loan, NFC interest expense 6 and household deposit interest 2 reconcile the bank's deposit-liability increase:
[
Delta Deposits=19-6+2=15,
quad Delta Equity=6-2=4.
]
This is consistent with the bank balance sheet. It does not imply that every loan or credit instrument in SCCE is a deposit-creating bank loan.

## 3. Capital stock and capital services must be separate

The current SFC example explicitly assumes zero CFC/depreciation, no retirements, no revaluation and no other volume changes. Under those assumptions, (K_{close}=200+68=268) is arithmetically fine. It cannot be generalized to the dynamic engine without a bridge.

Required separate identities:
[
K^{gross}_{t+1}=K^{gross}_{t}+GFCF_t-Retirements_t+OVC^{gross}_t,
]
[
K^{net}_{t+1}=K^{net}_{t}+GFCF_t-CFC_t-Retirements^{net}_t
+Revaluation_t+OVC^{net}_t,
]
with a documented convention to avoid subtracting retirements twice if already embedded in CFC.

Capital services are a flow, not the book value:
[
KS_t=sum_v int_t^{t+1}
K^{productive}_{v}(	au),
u_v(	au),phi_v(	au),d	au,
]
where (v) indexes vintages, (u) utilization and (phi) effective productive efficiency. Repair, downtime, age, obsolescence and replacement modify availability/efficiency; they are not interchangeable with CFC.

The B8.1 cohort file already carries repair, materials and asset-age concepts. The unresolved task is to reconcile those physical/productive cohorts with the financial GFCF/CFC/valuation bridge without double-counting depreciation or assuming that a repair payment itself creates a new asset.

## 4. Production dimensional contract is still missing at the SFC–physical boundary

The six-sector SFC example expresses its one aggregate product and intermediate use in D.E. The separate B2 test uses:
- steel and grain: tonnes;
- electricity: MWh;
- fuel: GJ;
- equipment: units;
- scrap and process residues: tonnes.

B2 correctly keeps unlike units separate and closes each balance. But the SFC document does not provide the product-price/valuation map, quality correspondence, time alignment or process-to-sector mapping needed to convert those physical quantities into its D.E. flows. Conversely, a monetary input-output table cannot prove a natural-unit balance.

Therefore the two examples are independently valid synthetic controls, but **they are not yet one integrated physical-financial numerical experiment**. A2.4.3 needs a typed product registry and explicit price bridge (Value_{j,t}=Price_{j,t}^{(basis)}Quantity_{j,t}), with separate price basis, quality, unit, period, origin, intermediate/final/capital classification and stock changes. The price bridge must not alter the physical conservation equation.

## 5. Labour/capability boundary to SCCE

Stage-B/C2 uses synthetic labour-hours as a coordination cost and production constraint. The physical model does not yet model wages, household cash budgets, ownership income, paid/unpaid labour choice or the legal/consent basis for work. Household capabilities, available time, chosen participation and delivered labour services must remain separate typed objects. A labour-hour is a flow of service over a period; it is not a human-capital stock, a universal value score or an automatic property claim.

The A2.4.5 interface must record:
- person/household capability and skill state;
- available time budget by period and activity;
- voluntary/contractual participation and consent;
- paid labour, unpaid care and training as separate activities;
- actual hours and service quality delivered;
- compensation/transfer and legal basis as separate financial/right events;
- safety, rest and care constraints.

No wage or ownership layer should be inserted into SCCE until the physical household model and these event contracts are validated.

## 6. SCCE audit — CI failure is a real current blocker

Current source branch `main`, latest observed head `2747bac75a44d6e4c68296914d39d673ccbdf7cb`.

Two latest workflows at 2026-11-10 11:45 UTC:
- Prototype validation run `42810082229`;
- SCCE Stage-C2 validation run `42810081975`.

Both fail at the same single unit test:
`test_care_queue_age_expiry_and_overflow_are_accounted`, line 110 of `prototype/test_scc_endogenous_household_economy.py`. The test runs a fixed scenario (seed 67, compound shock, 12 periods, max queue age 1) and asserts cumulative expired care claims (>0); actual is 0.0. The remaining 132/133 tests pass in each run. Later experiment steps are skipped because unit tests fail first.

The queue primitive has separate direct unit tests that verify FIFO expiry, retention attrition and capacity overflow. Thus current evidence localizes the immediate failure to the integration fixture's assumption that this particular economy trajectory must generate an expired care claim; it does **not yet prove** a defect in the queue primitive. Do not weaken the assertion to accept zero. Replace the scenario-dependent test with a deterministic integration fixture that guarantees unmet care and then verifies admission, waiting, service opportunity, expiry and overflow; keep the queue primitive tests as a separate layer. Only after both workflows pass should C2-A3 be treated as validated.

Relevant frozen sources:
- `prototype/test_scc_endogenous_household_economy.py`, SHA `44c91ceefabe41cf11e91aee51ebbc99b8fb6f60`.
- `prototype/care_service_queue.py`, SHA `e0a028f38dc8d19187977d3587f6cab11aab8ea7`.
- `prototype/test_care_service_queue.py`, SHA `dca9f2ed5a2b155aa87216805533e941c28895cf`.
- CI run logs: `42810082229` and `42810081975`.

## 7. SCCE comparative evidence: what is supported and what is not

The existing Stage-B and C2-A2 runs are synthetic, seven-cell, matched-seed experiments. They show mechanisms and trade-offs, not calibrated institutional superiority:
- Cooperative pooling leads on aggregate consumption/overall fulfilment in the current parameterization.
- Market matching leads on current food/combined essential fulfilment in the C2-A2 typed-backlog result, but has a much worse lower tail and higher essential Gini.
- Cellular coordination has a better lower tail than market in that sample but incurs much higher coordination labour and lower aggregate consumption than cooperative.
- Care backlog can raise the final-consumption index while worsening current fulfilment/lower-tail outcomes in some regimes; therefore final-consumption index is not a welfare proxy.
- FIFO versus current-first attribution changes which care claims count as served without changing aggregate physical deliveries. This is an accounting/priority convention that must be event-logged, not hidden in the metric.

The existing C2-A2 report explicitly predates age-cohort integration. The current CI failure means the age-cohort integration is not yet validated. Keep the older C2-A2 statistical table as evidence only for its exact older model version.

## 8. A2.4.8 — next end-to-end control (not engine integration)

The next experiment should use one explicitly frozen scenario and period, with:
1. a physical product registry and separate natural-unit stock-flow balances;
2. production recipes and capital-vintage/service records;
3. labour/capability/time constraints;
4. event IDs linking delivery, invoice, payment and financial instrument changes;
5. six-sector opening/closing financial positions and mirror matrix;
6. bank-loan creation and non-bank deposit-transfer control arms;
7. capital-account and financial-account net lending reconciliation;
8. CFC/repair/retirement/revaluation separated from physical output and GFCF;
9. a rights/ownership ledger that is not inferred from contribution;
10. paired SCCE, market, cooperative and central regimes under equal initial physical conditions;
11. preregistered outcome vector and held-out seeds, not a single scalar welfare score.

Pass criteria:
- every physical product closes in its own unit;
- each journal balances and each financial instrument has its mirror;
- capital/financial net lending reconciles by sector;
- stock-flow reconciliation holds for every asset/liability;
- no money/credit event changes physical output absent a production/delivery event;
- no physical output is counted twice through intermediate/final/capital use;
- no labour-hour is inferred from capability or vice versa;
- SCCE and comparator results are reproducible from frozen seeds and code hashes;
- all CI tests pass.

**Do not assemble the unified economic engine yet.** A2.4.8 is a paper-and-test interface experiment. The engine remains blocked until A2.4.1–A2.4.7 have explicit contracts and the cross-domain test passes.
