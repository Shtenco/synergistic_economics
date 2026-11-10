# A2.4 SFC/SCCE audit status — 11 November 2026

## Boundary
- Canonical branch: `main`; unchanged by this audit.
- Audit branch: `audit/sfc-scce-a2-4-continuation-20261111`.
- No unified economic engine is assembled.
- No SFC financial layer is integrated into SCCE.
- The only prototype-path modification on the audit branch is a test-only deterministic SCCE fixture in `prototype/test_scc_endogenous_household_economy.py`; production model and queue implementation are unchanged. No production code or canonical `main` changes.

## Current position
- Six-sector synthetic SFC: arithmetic and mirror positions close under the source's stated assumptions.
- Three blockers remain: A2-44 state-space incompatibility; A2-46 capital stock/services/depreciation separation; A2-48 bank-created deposits versus transfer of existing deposits.
- Five A2.4 interfaces remain open: canonical state/transition; capital stock/services; production dimensional contract; financial event/balance bridge; labour/capability bridge.
- A2.4.6 synergy estimand and A2.4.7 test suite remain cross-cutting.
- A2.4.8 end-to-end numerical interface experiment is the next control, not a mandate to build the runtime.

## Latest SCCE CI
- Prototype validation run 42810082229: failed one of 133 tests.
- C2 validation run 42810081975: failed the same test. Both logs confirm the same assertion failure (0.0 not greater than 0.0); all other 132 tests pass and downstream experiments are skipped.
- On the audit branch only, the seed-dependent expiry/overflow test was replaced with a controlled physical-delivery fixture. It retains the actual SCCE step, household allocator, FIFO queue, queue ageing and validation path. Period 1 admits a known unmet care quantity; period 2 delivers 25% of combined current-plus-backlog claims, which equals half of the old queue when the opening queue equals current need. The remaining half must expire. A separate capacity fixture admits 1% and records 99% as overflow.
- The changed test commit is `bea7d625087b7615f764bd97b2e5ce8ebc8c3070`. The commit has no reported status checks yet; this deterministic test is **not yet CI-verified**. Do not claim C2-A3 is green until both workflows run successfully.
- Queue primitive tests remain unchanged and independently cover FIFO expiry, retention and overflow.

## Artifacts
- `FINDINGS_001.md`: SFC arithmetic, interfaces, SCCE CI and A2.4.8 plan.
- `FINDINGS_002_CARE_QUEUE_INTEGRATION.md`: exact queue timing, failing test path and deterministic-fixture acceptance criteria.
- `A2_4_2_CAPITAL_STOCK_SERVICES_BRIDGE.md`: typed bridge across B8.1, B4 and SFC gross/net valuation; includes a same-cohort numerical example.
- `audit_sfc_six_sector.py`: standard-library Decimal control of the six-sector SFC example, credit event distinction and B2 physical balances.
- `audit_capital_bridge.py`: standard-library Decimal controls for physical quantity, gross/net stock, CFC, disposals, revaluation, capital services and gross/net SFC net lending.

## Next sequence
1. Run the changed deterministic SCCE integration test and both full CI workflows on a PR or other CI-enabled ref; inspect exact logs. If it fails, debug the real fixture, do not weaken assertions.
2. Extend A2.4.2 from the synthetic Decimal bridge to a same-cohort integration fixture that consumes B8.1 asset-state records and emits physical quantity, services, gross/net stock and CFC; add empirical data only after units and valuation basis are fixed.
3. Define A2.4.3 product-level dimensional/valuation contracts linking B2 physical quantities to SFC D.E. without summing unlike units.
4. Freeze A2.4.4 event types for bank-loan creation, non-bank loan transfer, payment, principal repayment, interest, default, write-off, revaluation and other volume changes.
5. Complete A2.4.1, A2.4.5, A2.4.6 and A2.4.7, then run A2.4.8 with common scenario IDs, event logs, matched initial states and paired comparator seeds.
6. Only after those controls pass, design the integrated economic engine boundary.
