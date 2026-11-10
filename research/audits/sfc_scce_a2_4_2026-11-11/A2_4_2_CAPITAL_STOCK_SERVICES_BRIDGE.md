# A2.4.2 — bridge between physical capital cohorts, capital services and SFC valuation

**Date:** 11 November 2026  
**Audit branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Canonical branch:** `main` (not modified)  
**Status:** interface specification and independent synthetic arithmetic control; not an integrated runtime and not empirical calibration.

## 1. Decision and source hierarchy

A2.4.2 does not create a second capital theory. The repository already contains three complementary pieces:

1. **B8.1** defines physical asset identity, vintage/age, condition, operating state, failure, repair, remanufacturing, final retirement, materials, downtime and delivered capital services.
2. **Integrated physical-financial framework §8** distinguishes physical/technical quantity, capital-service flow and value/CFC.
3. **B4** demonstrates a three-period physical reproduction case with a constant machine count, changing service quality, material recovery and an explicit price revaluation example.

The gap is the *typed bridge*: no single frozen control currently demonstrates, on the same cohort records, physical count, service flow, gross stock, net stock, CFC, retirement value, GrossAcquisitions and revaluation with all conventions explicit. B8.1's material model and B4's service model are valid separate controls; neither alone supplies this complete physical-to-SFC valuation bridge.

## 2. Canonical objects — do not collapse

| Object | Symbol | Unit/type | What changes it |
|---|---|---|---|
| Physical asset quantity | (N_{j,v,a,s,t}) | units, by asset/vintage/age/status | additions, retirement, physical loss, state transitions |
| Technical service potential | (C_{j,v,a,t}) | functional units per period per asset | design, age, component replacement, verified upgrade |
| Technical availability | (A_{j,v,a,t}) | fraction of period in serviceable state | repair queue, planned/unplanned downtime |
| Utilization | (U_{j,v,a,t}) | fraction of available capacity used | demand, operating schedule, constraints |
| Service quality/efficiency | (Q_{j,v,a,t}) | dimensionless measured coefficient | condition, reliability, quality and efficiency |
| Capital services | (KS_{j,t}) | functional units per period | available quantity × capacity × utilization × quality |
| Gross capital stock | (K^G_t) | currency at stated replacement-price basis | GrossAcquisitions, gross disposals, price revaluation, OVC |
| Net capital stock | (K^N_t) | currency at stated net replacement-cost basis | GrossAcquisitions, CFC, net disposals, revaluation, OVC |
| CFC | (CFC_t) | currency per period | age-price/condition profile under declared valuation convention |
| Repair/maintenance | (MNT_t) | event/flow; currency and material inputs separately | repair and service events; normally current intermediate use unless major improvement qualifies as GFCF |

A financial asset (share, bond, loan or deposit) is not a productive asset. A monetary value is not a physical quantity. Capital services are a flow, not a balance-sheet stock.

## 3. Physical cohort transition

Let (s) enumerate mutually exclusive physical states such as operating, reserve, repair, remanufacturing, storage and retired. For each cohort:

[
N_{j,v,a,s,t+1}=sum_{s'}N_{j,v,a-1,s',t}T_{j,v,a,s'	o s,t}
+I_{j,v,t}mathbf{1}_{a=0,s=operating},
]

where (T) is a documented transition matrix whose rows sum to one for surviving units; final retirement and physical loss are explicit exit flows, not hidden state transitions. This equation is a state-accounting contract, not a requirement to implement a matrix engine now.

For total non-retired physical units:

[
N^{total}_{j,t+1}=N^{total}_{j,t}+I_{j,t}
-D^{final}_{j,t}-L^{physical}_{j,t}.
]

Temporary failure, repair, remanufacturing and downtime do **not** subtract units from total non-retired assets. They change state and service availability. A repaired asset retains its original asset vintage and age. A replaced component receives its own component-vintage record; it does not reset the host asset's age. A remanufactured whole asset needs an explicit identity rule: either continued identity with changed condition/components, or retirement of the old asset and recognition of a new asset. The same unit cannot be treated both ways.

### 3.1 Failure and final retirement

Keep two hazards distinct:

- (h^{fail}): conditional probability of failure/intervention while operating;
- (h^{retire}): conditional probability of final retirement, if modeled directly.

If failures are routed through repair/remanufacturing, do not also apply a separate final-retirement hazard to the same failure cohort without an explicit competing-risk construction. A safe event split is:

[
F_t=h^{fail}_tN^{operating}_t,quad
F_t=F^{repair}_t+F^{reman}_t+D^{immediate}_t.
]

Repair/remanufacturing completions leave their queues after their actual delay and return to a serviceable state. Final retirement is recorded once. This resolves the B8.1 warning against subtracting repaired units twice.

## 4. Capital-service flow

Use the B8.1 structure, with one explicit availability convention:

[
KS_{j,t}=sum_{v,a,sin serviceable}
N_{j,v,a,s,t},C_{j,v,a,t},A_{j,v,a,t},
U_{j,v,a,t},Q_{j,v,a,t}.
]

If (N^{available}) is already measured as available units, set (A=1); do not multiply by availability again. If (C) is measured per *actual operating hour*, do not apply an additional utilization factor that already includes those hours. Quality must be independently defined (e.g. conforming output per machine-hour, reliability or service-grade coefficient) and not duplicate availability/utilization.

The minimum observed inputs are: installed quantity by vintage, scheduled hours, operating hours, repair/downtime hours, utilization, conforming output/service, failures, repair completions and component replacements. Monetary value is not an input to this physical service equation.

## 5. Gross and net value bridge — explicit timing convention

For a transparent control, use a perpetual-inventory cohort valuation at current replacement prices. This is a declared simplified convention, not a universal accounting rule.

For opening cohorts (i), let (n_i) be quantity, (p_0) the opening replacement price, (w_i) the opening net-value age factor, and (w'_i) the factor after one period's CFC. Additions are capitalized at the acquisition-period price (p_1). Retirement occurs at period end, after the period's CFC; therefore the retired asset is removed at its *post-CFC* net book value. Revaluation is applied to surviving opening assets after age consumption and retirement. No event may appear in more than one adjustment category.

[
K^G_1=K^G_0+GrossAcquisitions-GrossDisposals+Revaluation^G+OVC^G,
]

[
K^N_1=K^N_0+GrossAcquisitions-CFC-NetBookValueDisposals
+Revaluation^N+OVC^N.
]

Here gross acquisitions are recorded before disposals. Gross disposals remove the current replacement value of the retired asset; net-book-value disposals remove its value after the period's CFC. CFC is calculated once from the opening asset's age/condition profile through the period. Revaluation is the price change on surviving opening assets only. New additions are already measured at (p_1), so do not revalue them a second time in the same period. **This is a cohort replacement-cost stock bridge, not the national-accounts GFCF transaction flow.** In national accounts, GFCF is normally acquisitions less disposals under the applicable transaction-price convention. It must be derived once from acquisition/disposal events and then reconciled to the replacement-cost cohort stock through valuation/other adjustments; do not use net GFCF and subtract disposals again.

If an adopted national-accounts/valuation standard embeds ordinary retirements in its CFC convention, the separate disposal term must be adjusted accordingly. The two conventions cannot be mixed. The test below explicitly uses end-period retirement and separate NBV disposal.

### 5.1 CFC is not physical retirement

CFC is a current-price value of the consumption of fixed capital during the period. It is not the number of machines scrapped, not a material flow, and not automatically equal to the decline in market price. Physical asset quantity can remain unchanged while CFC is positive. Conversely, an exceptional catastrophic loss may be an other-volume change rather than ordinary CFC.

### 5.2 Repair versus capital formation

- Routine maintenance and repair that restore the asset to its expected operating condition are normally current costs; record their labour, parts, materials and payment, but do not automatically capitalize them as GFCF.
- A major improvement that demonstrably increases capacity, extends service potential beyond the originally expected level, or creates a separately identifiable component may qualify as GFCF under the selected standard. Record the new component/vintage and its own service/age profile.
- Spare parts held in inventory remain inventory until used; usage is then classified according to the repair/improvement event.
- Remanufacturing must declare whether it restores an existing asset, creates a distinct new fixed asset, or produces a component. Do not book a full new asset and retain the old one as fully productive unless two physical assets actually exist.

The financial cost of repair is not itself proof of new productive capital. The physical service effect and accounting classification are separate evidence fields.

## 6. Worked Decimal control

All values are synthetic. This control is designed to test arithmetic and category separation.

Opening park:
- 10 machines of age 0, net-value factor 1.0;
- 8 machines of age 1, factor 0.9;
- 6 machines of age 2, factor 0.8;
- opening replacement price (p_0=100) currency units per machine.

During the period:
- 2 new machines are acquired at (p_1=105) each;
- 1 age-2 machine is retired at period end;
- surviving opening cohorts move one age step: factors 1.0→0.9, 0.9→0.8, 0.8→0.7;
- each opening machine consumes 0.1 of its opening replacement value through CFC;
- price revaluation is +5 per surviving opening machine, applied after CFC;
- no other-volume change is assumed.

Opening gross stock:

[
K^G_0=(10+8+6)100=2400.
]

Opening net stock:

[
K^N_0=(10cdot1+8cdot0.9+6cdot0.8)100=2200.
]

Acquisitions and CFC:

[
GrossAcquisitions=2cdot105=210,quad
CFC=(10+8+6)cdot0.1cdot100=240.
]

Retirement removes gross value (100) and post-CFC net book value (0.7cdot100=70). Revaluation on 23 surviving opening units:

[
Revaluation^G=23(105-100)=115,
]

[
Revaluation^N=(10cdot0.9+8cdot0.8+5cdot0.7)(105-100)=94.5.
]

Therefore:

[
K^G_1=2400+210-100+115=2625,
]

[
K^N_1=2200+210-240-70+94.5=2194.5.
]

Direct cohort valuation at the closing price independently gives gross stock (25cdot105=2625) and net stock ((10cdot0.9+8cdot0.8+5cdot0.7+2)cdot105=2194.5). Both reconciliation routes agree exactly.

Physical count separately closes:

[
N_1=24+2-1=25.
]

For service flow, let capacity per machine be one functional unit per period, availability (A=0.9), utilization (U=0.8), and independently measured age-quality factors (q=(1.0,0.95,0.90,0.85)). Then:

[
KS_0=(10cdot1+8cdot0.95+6cdot0.90)0.9cdot0.8=16.56,
]

[
KS_1=(10cdot0.95+8cdot0.90+5cdot0.85+2cdot1.0)0.9cdot0.8=16.524.
]

The example deliberately shows that physical quantity can rise from 24 to 25 while service flow slightly declines because of age/quality mix. Gross stock rises; net stock changes only slightly; CFC is positive; revaluation is positive. None of these numbers is a substitute for another.

## 7. Compatibility with SFC capital accounts

For a sector (s), the capital account uses national-accounts GCF/GFCF under the selected transaction-price convention; GFCF already reflects acquisitions less disposals. The cohort stock bridge above instead uses gross acquisitions and separate gross/NBV disposals at replacement cost. A valuation reconciliation is required between the two. Never substitute net GFCF into a cohort equation that also subtracts disposals.

Using gross saving and gross capital formation:

[
NL_s=S^G_s+KTr_s-GCF_s-NPNA_s.
]

Using net concepts consistently:

[
NL_s=S^N_s+KTr_s-NCF_s-NPNA_s,
quad S^N_s=S^G_s-CFC_s,quad NCF_s=GCF_s-CFC_s.
]

Thus (NL_s) is unchanged by moving from gross to net concepts **only if the same CFC is deducted consistently from both saving and capital formation**. Mixing gross saving with net capital formation, or vice versa, creates a false discrepancy.

The six-sector SFC example remains a valid zero-CFC arithmetic control. It explicitly assumes no depreciation, retirement, revaluation or other-volume change. It must not be silently generalized to the cohort model above. A future SFC extension should post CFC by owning/using institutional sector and asset class, then reconcile gross and net capital accounts and the balance-sheet bridge separately.

## 8. Required event contract for A2.4.1/A2.4.4

Each capital event should minimally carry:

- immutable `event_id`, `asset_id` or `cohort_id`, `component_id`, `period` and event time;
- `event_type`: acquisition, commissioning, failure, repair_start, repair_complete, component_replacement, reman_start, reman_complete, retirement, physical_loss, upgrade, revaluation, CFC_accrual;
- quantity and physical unit;
- old/new operating state and old/new technical condition;
- material inputs, recovered outputs, residues and their product specifications;
- service-capacity/quality effect, measurement method and uncertainty;
- owner, economic user, institutional sector and legal basis;
- gross value, net value, price basis, currency, CFC method and counterpart account where applicable;
- source, evidence quality, model version and correction lineage.

A repair event can alter availability and condition without creating a financial asset. A payment event can settle the repair invoice without changing physical capital quantity. An upgrade event may change service capacity and create GFCF, but only when recognition criteria and physical evidence are met.

## 9. A2.4.2 pass/fail checklist

1. Every physical unit is in exactly one mutually exclusive state at a time.
2. Age never resets on ordinary repair.
3. Component replacement creates a component cohort, not a fictitious new host asset.
4. Temporary failures and repair queues do not reduce total non-retired quantity.
5. Final retirement is counted once, with a declared event timing.
6. Capital services use measured available hours/quantity, utilization and non-duplicative quality.
7. Gross and net stocks are independently reproducible from cohorts and valuation profiles.
8. CFC, disposals, revaluation and other-volume changes are mutually exclusive adjustments.
9. Routine repair does not become GFCF merely because money was spent.
10. GFCF/CFC are assigned to institutional sectors and reconciled to gross/net capital accounts.
11. Financial payment/credit events do not directly change physical quantity or service absent a corresponding asset/repair event.
12. The same cohort dataset reproduces physical count, service flow, gross stock, net stock and all adjustment terms.

**Current status:** the conceptual pieces exist in B8.1, B4 and the integrated framework; the complete same-cohort cross-register test is newly specified here but not yet implemented in the economic runtime or empirically calibrated. A2.4.2 is therefore **partially specified, not closed**.


## 10. Runtime adapter into the existing SCCE capital multiplier

A separate adapter now connects explicit B8.1-style cohort service flows to the
actual Stage-B SCCE engine without changing its default behavior:

- `prototype/capital_cohort_bridge.py` accepts immutable asset-cohort rows
  with stable cohort/cell/asset identity, vintage, age, physical quantity,
  service capacity per asset, operating state, availability, utilization and
  service quality.
- It aggregates physical units, operating units and capital-service flow
  separately for each of the seven SCCE cells.
- A declared positive `baseline_services[cell_id]` is required. The dimensionless
  multiplier is `current_service_flow / baseline_service_flow`.
- All cells are validated and calculated before any `CellState.capital` value
  is changed. A zero-service cell is rejected atomically because the current
  engine's own `validate()` requires strictly positive scalar capital.
- The adapter must be called before each `model.step(period)` for which the
  cohort service state is authoritative. Callers that do not invoke it retain
  the original scalar default of 1.0.

The new `audit_scce_capital_cohort_bridge.py` fixture uses synthetic cohort
records, maps the resulting ratios onto a real `DynamicCellularEconomy`
instance, checks the local production proposal's response to the multiplier,
and executes a real SCCE period. It also checks that repair downtime reduces
service without deleting physical units, and that invalid zero-service,
duplicate-ID and incomplete-baseline cases fail closed.

**Interpretation limits:** this is a runtime adapter and synthetic integration
test, not empirical asset data, not a calibrated capital-service baseline and
not a full B8.1 asset lifecycle. The SCCE engine still does not own or evolve
the cohort register. A future integration must persist cohort transitions
(acquisition, ageing, repair completion, component replacement, retirement,
physical loss), validate the opening-to-closing physical stock identity, and
derive baseline service flows from measured or explicitly calibrated evidence.
The scalar multiplier remains a compatibility boundary, not a monetary capital
stock and not a substitute for asset quantities or capital-service units.
