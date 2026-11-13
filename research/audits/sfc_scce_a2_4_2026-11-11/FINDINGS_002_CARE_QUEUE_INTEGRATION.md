# SCCE care-queue integration audit — finding 002

**Date:** 11 November 2026  
**Source branch:** `main`  
**Audit branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Scope:** read-only analysis of the failing care-queue integration test; no prototype code changed.

## 1. Exact execution path

The failing test is `test_care_queue_age_expiry_and_overflow_are_accounted` in `prototype/test_scc_endogenous_household_economy.py`. Its expiry arm runs the full stochastic physical economy with seed 67, compound shock, 12 periods, retention 1.0 and maximum care-queue age 1, then asserts that cumulative expired claims are positive.

In `EndogenousHouseholdEconomy.step`, the per-household care path is:

1. Read delivered care from the household allocation.
2. Under `backlog_first`, serve the existing queue FIFO from delivered care.
3. Allocate any remaining delivered quantity to current-period care need.
4. Compute current unmet care.
5. Call `queue.advance_and_add(current_unmet, period)`.
6. Add the returned expired/attrited/overflow quantities to cumulative counters.

The order matters: an existing lot has its service opportunity in the current step before ageing/expiry is applied. New unmet care is admitted after this service allocation at age zero.

## 2. Queue timing contract

For `max_age_periods=1`:

- A newly admitted lot is stored at age 0 at the end of period (t).
- During period (t+1), it is included in backlog demand and can be served by the allocator.
- At the end of period (t+1), any surviving remainder advances to age 1 and expires.

This is consistent with the queue docstring: a lot gets its final service opportunity before expiry. The primitive test for `max_age_periods=2` independently checks the analogous two-opportunity boundary.

Therefore, `expired > 0` is not implied by `max_age_periods=1` alone. It additionally requires at least one positive admitted lot to remain partially or wholly unserved through its service-opportunity period.

## 3. What the current CI failure proves

The observed value `cumulative_expired_care_claim_units == 0.0` proves only that no positive queue quantity reached the expiry counter in that particular 12-period run. It does not, by itself, distinguish among:

- no unmet care was ever admitted;
- unmet care was admitted but served before its expiry boundary;
- the age-one configuration and scenario generated no surviving lot at the relevant transition.

It does not prove that FIFO, expiry, retention, or overflow primitives are broken. Those are separately exercised by `prototype/test_care_service_queue.py`.

## 4. Required deterministic integration fixture

Do not weaken the positive-expiry assertion, and do not change the queue's expiry boundary merely to make the seed-67 run pass.

Replace the scenario-dependent expiry premise with a controlled integration test that holds the physical allocation outcome fixed while exercising the actual `EndogenousHouseholdEconomy.step` bookkeeping path. The fixture must:

- establish a positive, explicitly identified household care shortfall;
- admit that shortfall to that household's actual `care_queues[household_id]`;
- preserve the one-period service opportunity for the admitted lot;
- constrain delivered care in the following period to a known amount strictly below the opening queued claim;
- assert the exact amount served from the old lot, the remaining amount expired, and the cumulative expiry counter;
- assert that current-period unmet care is separately admitted after the old lot's service/expiry processing;
- retain separate primitive tests for FIFO order, retention attrition, and capacity overflow;
- assert queue mirror equality and `model.validate()` after each controlled transition.

A test double may control only the physical delivery/allocation seam. It must not replace `CareServiceQueue`, bypass `EndogenousHouseholdEconomy.step`, or silently change physical output while leaving the recorded physical supply unchanged. The controlled delivery fixture should explicitly state that it is a test harness, not an economic scenario result.

## 5. Additional assertion quality issue

The current test loops through `care_queue_age_distribution` and checks that each key converts to integer zero. The summary constructs this dictionary with every configured age key, including zero-quantity ages. This assertion checks the shape of the summary, not whether queue lots actually have the asserted ages. The integration fixture should inspect actual non-zero age quantities (or the queue lots) and separately assert the summary mirror.

## 6. Decision

**Status: fixture defect/assumption is the leading explanation; root cause is not fully proven.** No production-code defect is established from the available evidence. The correct next action is to add the deterministic integration fixture on an isolated test branch, run the targeted test, then both full CI workflows. Until then, the existing C2-A3 age-cohort result remains unvalidated.

## Frozen source references

- `prototype/test_scc_endogenous_household_economy.py` at main: blob `44c91ceefabe41cf11e91aee51ebbc99b8fb6f60`.
- `prototype/scc_endogenous_household_economy.py`: inspected source; care service/age/expiry transition occurs in `step`.
- `prototype/care_service_queue.py`: blob `e0a028f38dc8d19187977d3587f6cab11aab8ea7`.
- `prototype/test_care_service_queue.py`: blob `dca9f2ed5a2b155aa87216805533e941c28895cf`.
- Prototype validation: run `42810082229`.
- Stage-C2 validation: run `42810081975`.
