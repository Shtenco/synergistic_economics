# A2.4 SFC/SCCE audit status — 11 November 2026

## Boundary
- Canonical branch: `main`; unchanged by this audit.
- Audit branch: `audit/sfc-scce-a2-4-continuation-20261111`.
- No unified economic engine is assembled.
- No SFC financial layer is integrated into SCCE.
- Existing prototype code is not modified in this audit branch; this branch adds independent controls and findings only.

## Current position
- Six-sector synthetic SFC: arithmetic and mirror positions close under the source's stated assumptions.
- Three blockers remain: A2-44 state-space incompatibility; A2-46 capital stock/services/depreciation separation; A2-48 bank-created deposits versus transfer of existing deposits.
- Five A2.4 interfaces remain open: canonical state/transition; capital stock/services; production dimensional contract; financial event/balance bridge; labour/capability bridge.
- A2.4.6 synergy estimand and A2.4.7 test suite remain cross-cutting.
- A2.4.8 end-to-end numerical interface experiment is the next control, not a mandate to build the runtime.

## Latest SCCE CI
- Prototype validation run 42810082229: failed one of 133 tests.
- C2 validation run 42810081975: failed the same test.
- Failure: scenario-specific assertion expects positive expired care claims for seed 67, but actual expired quantity is 0.0.
- Queue primitive tests independently cover FIFO expiry, retention and overflow. Current evidence points first to an integration-fixture assumption; do not relax the assertion or alter queue semantics without a deterministic reproducer.

## Artifacts
- `FINDINGS_001.md`: SFC arithmetic, interfaces, SCCE CI and A2.4.8 plan.
- `audit_sfc_six_sector.py`: standard-library Decimal control of the six-sector SFC example, credit event distinction and B2 physical balances.

## Next sequence
1. Create a deterministic care-queue integration fixture that guarantees unmet care, then verify admission, age, service opportunity, expiry and overflow; rerun both CI workflows.
2. Complete the gross/net capital and capital-services bridge against B8.1 cohort data; explicitly prevent CFC/retirement double counting.
3. Define product-level dimensional and valuation contracts linking B2 physical quantities to SFC D.E. without summing unlike units.
4. Freeze event types for bank-loan creation, non-bank loan transfer, payment, principal repayment, interest, default, write-off, revaluation and other volume changes.
5. Complete A2.4.1–A2.4.7, then run A2.4.8 with common scenario IDs, event logs, matched initial states and paired comparator seeds.
6. Only after those controls pass, design the integrated economic engine boundary.
