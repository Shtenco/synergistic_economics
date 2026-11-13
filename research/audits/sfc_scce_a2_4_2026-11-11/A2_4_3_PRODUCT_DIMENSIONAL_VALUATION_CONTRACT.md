# A2.4.3 — product dimensional and valuation contract

**Date:** 11 November 2026  
**Branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Status:** specification and B2 arithmetic controls; no monetary or physical runtime integration.

## 1. Finding

B2 already demonstrates separate native-unit balances for steel, grain, electricity, fuel, scrap and equipment. B3 adds product/process/node/edge separation and unique physical flow IDs. The integrated framework already separates physical supply-use from monetary GDP/GVA. The remaining gap is a canonical typed registry and an explicit valuation adapter connecting each physical product/quality/period to SFC monetary values without treating a currency unit as a physical unit.

The six-sector SFC example is a valid monetary closure in D.E.; it is not a multi-commodity physical conservation test. B2 is a valid natural-unit closure; it has no prices, cash events or financial accounts. They must remain two distinct control layers until a shared product/event mapping exists.

## 2. Product identity and dimensional type

A product is not identified by a free-text label alone. Minimum immutable product key:

| Field | Contract |
|---|---|
| `product_id` | stable canonical product/material/service code |
| `grade_id` | specification/quality grade; no silent substitution across grades |
| `physical_dimension` | mass, volume, energy, count, area, time, service, etc. |
| `native_unit` | t, kg, m³, MWh, GJ, unit, machine-hour, service-unit, etc. |
| `unit_scale` | exact conversion to the chosen base unit within the same dimension |
| `stockability` | stockable, non-stockable flow, or work-in-progress |
| `time_basis` | instant stock, period flow, rate, or duration |
| `quality_schema` | purity, grade, moisture, temperature, pressure, reliability, service class |
| `origin_scope` | domestic/imported, region, process and source |
| `valuation_basis` | basic, producer, purchasers', CIF/FOB or explicit project basis |
| `price_reference` | currency, price date/period, unit denominator, source and uncertainty |
| `evidence_status` | measured, documented, estimated or simulated |

A quantity without product, grade, unit, period and system boundary is not eligible for a conservation test. A price without a product grade, unit denominator, price basis and date is not eligible for valuation.

## 3. Native-unit physical balance

For each homogeneous product (j), grade (g), node (n) and period (t):

[
S^{open}_{jgnt}+Output_{jgnt}+Imports_{jgnt}
+sum_m Flow_{jg,m	o n,t}
=
IntermediateUse_{jgnt}+FinalUse_{jgnt}+GFCF_{jgnt}
+Exports_{jgnt}+Losses_{jgnt}+S^{close}_{jgnt}
+sum_m Flow_{jg,n	o m,t}.
]

The equation is evaluated independently for each compatible product-grade-unit key. The same physical transfer has one `flow_id`; sender and receiver records reference that event. Internal flows cancel at the consolidated boundary but remain traceable at node level.

For non-stockable services and electricity in a model without storage, use a period flow balance; do not invent a warehouse stock. For electricity with storage, distinguish generation, charging, stored energy, discharging, conversion losses and delivered electricity. Power (MW) is a rate/capacity; energy (MWh) is a flow over time. They are not interchangeable.

Work-in-progress is a stock in process and must be included where a process has time lags. Waste, residues and co-products receive their own product/stream IDs and units; a process residual cannot be erased as an efficiency coefficient without a measured physical destination.

## 4. Process transformation contract

Each process has:
- `process_id`, technology version, location and time interval;
- input vector indexed by product-grade-native unit;
- output vector indexed by product-grade-native unit, including co-products;
- explicit loss/residue streams and WIP change;
- capacity, actual utilization and process state;
- yield coefficients with provenance and uncertainty.

For each process and each conserved element/energy carrier, the component balance is:

[
Input^{component}=TargetOutput^{component}
+CoProducts^{component}+Residues^{component}
+Losses^{component}+Delta WIP^{component}.
]

This is not necessarily a simple mass equality for chemical/biological transformations. For a chemical process, conserve elements (and charge where relevant); for energy, define the boundary and distinguish energy carriers and quality. Converting MWh to GJ uses (1,MWh=3.6,GJ), but does not make electricity, low-grade heat and fuel services interchangeable. Conversion efficiency and useful output must be explicit.

## 5. Monetary valuation adapter

For product (j), grade (g), period (t), at declared valuation basis (b):

[
V^{b}_{jg,t}=Q_{jg,t},P^{b}_{jg,t},
]

where (Q) remains in its native unit and (P) is currency per that exact unit. The valuation adapter produces a monetary view; it must not mutate the physical quantity or physical balance.

The adapter must record:
- currency and scale;
- price per native unit (e.g. D.E./t, D.E./MWh, D.E./machine, D.E./service-unit);
- basic/producer/purchasers' price basis;
- taxes/subsidies on products and trade/transport margins as separate adjustments;
- import valuation and exchange-rate convention (CIF/FOB where relevant);
- quality/grade adjustment;
- price period, index/deflator and uncertainty;
- source and revision lineage.

Do not value one tonne of different grades at the same price without an explicit grade adjustment. Do not apply one average price to a mixed basket before recording its composition. Do not use current prices for volume growth without a constant-price/chain-volume method.

### 5.1 Valuation does not close physical balances

A monetary identity such as (149+30=179) cannot prove mass or energy conservation across steel, grain, electricity and equipment. Conversely, a closed tonne/MWh/unit balance does not prove that payments, income, sectoral net lending or financial claims reconcile.

### 5.2 GVA and intermediate goods

For each producer/industry (i):

[
GVA_i=GrossOutput_i-IntermediateConsumption_i
]

at consistent valuation basis. Summing gross output across sequential production stages counts intermediate goods more than once. Internal physical transfers retain unique IDs and cancel on consolidation; GVA is the monetary value-added measure. A transfer of ownership of an existing asset does not create a second physical asset or new GFCF.

### 5.3 GFCF versus inventory change

The physical product balance carries opening/closing inventories and identifies equipment acquisitions in native units. National-accounts gross capital formation is a monetary aggregate and includes GFCF plus inventory change and valuables under the selected standard. Do not put inventory change inside GFCF and also count it via opening/closing stocks. The valuation adapter must classify a delivered piece of newly produced equipment as GFCF for its purchaser, while the producer's output and the purchaser's acquisition remain linked by one delivery event.

## 6. B2 controls re-expressed as product-specific assertions

The frozen B2 example includes these independently balanced rows:

- Steel: (5+10+2=8+3+1+1+4=17) t.
- Grain: (20+30+5=5+35+5+5+5=55) t.
- Electricity: (100+10=60+40+5+5=110) MWh.
- Scrap: (12=12+0) t.
- Equipment: (0+2=2+0) units.
- Scrap processing: (12) t input (=10) t secondary steel (+2) t residue.
- Fuel/energy conversion: (500) GJ input (=100) MWh electricity (	imes3.6) GJ/MWh (+140) GJ thermal losses.

The 4 MWh used in scrap processing is already inside the 60 MWh of intermediate electricity use. The 20 MWh used for equipment assembly is also a decomposition of the same 60 MWh, not an extra use. These suballocations must not be added twice.

## 7. A2.4.3 required tests

1. Reject missing product, grade, unit, period or boundary.
2. Reject incompatible dimensions in addition/subtraction.
3. Permit unit conversion only through a versioned, dimensionally valid conversion.
4. Close each product-grade-node balance independently.
5. Verify sender/receiver equality for each `flow_id`.
6. Consolidate internal transfers exactly once.
7. Close each process's component/energy/WIP balance.
8. Keep residues and losses explicit.
9. Reconcile quantity × unit price to monetary value at the same grade/basis/period.
10. Show that changing price changes value but not physical quantity.
11. Show that changing physical quantity changes native balance and, at fixed price, monetary value.
12. Prevent inventory change from being counted both as stock movement and as GFCF.
13. Reconcile producer output, intermediate consumption and GVA without double counting.
14. Reconcile equipment units to purchaser GFCF and supplier output through one delivery event.

**Current status:** B2/B3 and the integrated framework provide substantial foundations; the canonical product registry and price adapter are specified here but not yet implemented or calibrated. A2.4.3 remains open pending an executable cross-register test.
