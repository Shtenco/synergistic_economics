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
- A2.4.1–A2.4.5 now have audit specifications for typed transitions, capital/services, product dimensions/valuation, financial events and labour/capability/time/consent. These are paper contracts, not completed runtime integrations.
- A2.4.6 net-synergy estimand and A2.4.7 cross-register test/release gates are specified. Neither comparative preregistration nor full gate suite has passed.
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
- `A2_4_2_CAPITAL_STOCK_SERVICES_BRIDGE.md`: typed bridge across B8.1, B4 and SFC gross/net valuation; includes a same-cohort numerical example and explicitly separates gross acquisitions/disposals in replacement-cost stock equations from national-accounts net GFCF.
- `A2_4_3_PRODUCT_DIMENSIONAL_VALUATION_CONTRACT.md`: product-grade-native-unit registry, process balance and monetary valuation adapter.
- `A2_4_4_FINANCIAL_EVENT_BALANCE_BRIDGE.md`: immutable event envelope, double-entry posting families and credit-creation/transfer distinctions.
- `A2_4_5_LABOUR_CAPABILITY_TIME_CONSENT_BRIDGE.md`: time, capabilities, actual services, consent, compensation and rights boundaries.
- `A2_4_6_NET_SYNERGY_ESTIMAND.md`: counterfactual, incremental input/cost accounting and preregistered outcome vector.
- `A2_4_7_CROSS_REGISTER_TEST_GATES.md`: layered test architecture and release gates.
- `audit_sfc_six_sector.py`: standard-library Decimal control of the six-sector SFC example, credit event distinction and B2 physical balances.
- `audit_capital_bridge.py`: standard-library Decimal controls for physical quantity, gross/net stock, CFC, disposals, revaluation, capital services and gross/net SFC net lending.
- `audit_product_dimensions.py`: standard-library Decimal controls for B2 product balances, process conversions and price/quantity separation.
- `audit_financial_events.py`: standard-library Decimal controls for bank deposit creation, non-bank transfer, payments, principal and interest.

## Next sequence
1. Verify the deterministic SCCE fixture in CI; obtain both Prototype validation and Stage-C2 workflow logs. Until then C2-A3 is not validated.
2. Build the same-cohort A2.4.2 integration fixture from B8.1 records; test physical states, services, gross/net stock, CFC and revaluation together.
3. Implement the A2.4.3 product registry/valuation adapter and prove the B2 physical quantities reconcile to SFC values without cross-unit aggregation.
4. Implement A2.4.4 event posting fixtures including accrual/settlement, default, impairment and write-off; reconcile instrument mirrors and sector accounts.
5. Add A2.4.5 time/consent/compensation test fixtures and preserve the rights boundary.
6. Freeze A2.4.6 preregistration, then complete A2.4.7 CI coverage; execute A2.4.8 only when the entry conditions in `A2_4_7_CROSS_REGISTER_TEST_GATES.md` are met.
7. Only after Gate 2 and relevant comparative evidence pass, design the integrated economic engine boundary. Do not merge the ledgers prematurely.
