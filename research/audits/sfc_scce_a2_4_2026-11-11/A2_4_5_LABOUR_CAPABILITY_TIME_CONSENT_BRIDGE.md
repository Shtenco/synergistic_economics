# A2.4.5 — labour, capability, time and consent bridge

**Date:** 11 November 2026  
**Branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Status:** typed interface specification; no wage/labour runtime is integrated into SCCE.

## 1. Non-equivalence rule

The following objects must remain separate:

- human capability/skill state — a person's evolving ability to perform tasks;
- available time — a finite time budget over a defined period;
- consent/participation — a voluntary or legally grounded state of engagement;
- labour/care/training service — an actual activity flow delivered during a period;
- output/service quality — the result of activity, measured separately;
- compensation — a financial or in-kind transfer with a legal basis;
- ownership and residual rights — a separate legal register.

An hour is not a capability stock. A capability score is not an hour supplied. A contribution record is not an ownership title. No production model may infer that a person consents to work merely because they have available time or a skill.

## 2. Time account

For person (i), activity (a), period (t), use a mutually exclusive time allocation:

[
T^{period}_{i,t}=
T^{sleep/rest}_{i,t}+T^{personal}_{i,t}
+T^{paid}_{i,t}+T^{unpaidcare}_{i,t}
+T^{training}_{i,t}+T^{civic}_{i,t}
+T^{leisure}_{i,t}+T^{unallocated}_{i,t}.
]

For a weekly model, (T^{period}) is 168 hours; for another period, use its exact duration. Every activity interval is assigned once; simultaneous activities require an explicit multi-activity measurement rule rather than double-counting hours. Safety, rest, care duties, legal limits and personal constraints are hard feasibility conditions, not merely weighted preferences.

Available time is not the same as labour supply. Only hours actually performed and accepted as delivered service enter the realized labour/care flow. Offered, scheduled, accepted, started, completed, disputed and cancelled hours are distinct states.

## 3. Capability and skill stock

For person (i) and skill/task domain (k), maintain a typed capability record:

- skill/domain identifier and proficiency scale;
- evidence (qualification, assessment, work sample, experience);
- measurement date, validity and uncertainty;
- learning/training event history;
- recency/obsolescence or skill-maintenance assumptions;
- self-reported preferences and task eligibility, with consent;
- accommodation and safety constraints where voluntarily/legally recorded.

A schematic capability transition is:

[
C_{i,k,t+1}=C_{i,k,t}
+Learning_{i,k,t}
-Obsolescence_{i,k,t}
+VerifiedUpdate_{i,k,t}.
]

This is a skill/capability state, not a financial asset or property claim. Capabilities across different domains are not summed into one universal score without a validated measurement model. The production function may use task-specific capability only through a declared, testable mapping to service quality or output.

## 4. Delivered labour and care services

Record separately:

[
H^{delivered}_{i,a,t}quad [hours/period],
]

[
Q^{service}_{i,a,t}quad [task	ext{-}specific quality],
]

[
Y^{service}_{i,a,t}quad [native output/service unit].
]

Do not multiply hours by a generic capability score and call the result output unless the mapping is estimated and validated for that task. Do not treat unpaid care as zero physical output because no wage is paid. Conversely, do not add imputed unpaid care automatically to market GDP; keep satellite-account valuation separate from core national-account output.

For household care, distinguish care need, care offered, care delivered, quality, recipient, duration, unpaid/paid status and unmet need. A queue claim is not delivered care; only actual service clears the claim.

## 5. Consent, contract and participation states

A participation event should have a clear state path, for example:

[
Offered	o Accepted	o Scheduled	o Started	o Delivered
	o Verified/Disputed	o Settled.
]

Withdrawal, refusal, cancellation, illness, safety stop and dispute are explicit states. Acceptance may be withdrawn according to the governing contract and law. A system must not infer consent from prior participation, availability, capability, household membership or an AI recommendation.

The legal basis may be employment, contract for services, cooperative membership, family/unpaid care, volunteer activity or another lawful arrangement. These categories are not interchangeable and can have different protections and payment obligations.

## 6. Compensation and financial recognition

For paid work, distinguish:
- service performed/accrued compensation;
- gross wage/fee;
- tax and social contribution;
- net payable;
- cash/in-kind settlement;
- arrears, dispute, adjustment and reversal.

Accrual of wage expense and payable can precede payment. Payment settles the payable; it does not create the labour service a second time. Unpaid care may have a satellite valuation but no fictitious cash receivable unless a legally enforceable claim exists. Training time may build capability but is not automatically current production labour. The same hour cannot be both paid productive labour and unpaid care in two ledgers.

## 7. Production and distribution interfaces

The production interface receives only:
- actual delivered hours by task and period;
- verified task eligibility/quality inputs;
- safety and capacity constraints;
- an explicit productivity mapping with evidence status.

The financial interface receives wage/fee accrual, tax/contribution and settlement events. The rights register receives contract, consent, appeal and governance rights. The ownership register is not generated from time or capability alone.

No contribution score may automatically determine legal title, voting power, access to basic rights or a residual ownership share. Any incentive/distribution rule must be separately authorized, transparent and appealable.

## 8. Minimum tests

1. Time allocations never exceed the period duration.
2. Overlapping activity intervals are not double-counted.
3. Available time does not become labour supply without acceptance and delivery.
4. Skill stock changes only through explicit learning/obsolescence/verified events.
5. A skill index is not added to hours or monetary values.
6. Delivered hours are bounded by scheduled/accepted hours and safety/legal constraints.
7. Care need, offered care and delivered care remain distinct.
8. Paid and unpaid hours are mutually exclusive under the chosen classification.
9. Wage accrual and cash settlement are separate and reconcile.
10. Training can change capability without being misclassified as current output.
11. No ownership/right is inferred from contribution.
12. Personal data is minimized; capability and health-related evidence is not exposed through public aggregate signals.

**Current status:** conceptual separation exists across Volumes II, III, XIII and the SCCE household model, but the complete time/consent/compensation event bridge is not implemented. A2.4.5 remains open.


## 6. Hardened component fixture

The executable fixture `audit_labour_consent.py` now rejects unknown consent
states, any delivered service without an active consent state, delivery above
accepted/scheduled/safety limits, overlapping time intervals, a non-positive
period budget, negative closing capability stock, and wage settlement above
accrued payable. It keeps capability change, service hours and wage settlement
as separate quantities.

This is still a component contract. It does not yet implement person-level
identity/privacy controls, revocation chronology, legal basis by jurisdiction,
appeal, safeguarding, collective bargaining, non-wage in-kind compensation or
live SCCE service-event integration. A2.4.5 remains open.
