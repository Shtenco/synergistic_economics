# Banking-to-SFC integration: source-contract blockers and implementation gate

Audit date: 2026-11-15
Scope: `research/bank-deposit-credit-audit-fix-20261115`, current PR #13 head before this audit note.
Status: verified source-contract findings; no claim of implemented adapter or macroeconomic closure.

## Executive finding

A native banking SFC adapter is feasible, but the current financial register payload is not yet rich enough to construct a complete, economically typed multi-period projection for every supported instrument. Implementing a mapper immediately by filling absent fields with defaults would create false precision. The correct next step is to extend and version the financial instrument identity and opening-stock contracts, then implement the adapter against those explicit contracts.

## Verified source facts

1. `prototype/operating_financial_register.py` defines financial movement identities in `_identity` with: register_id, position_id, measure, unit, currency, valuation_basis, holder_id, issuer_id, instrument_id.
2. The SFC projection kernel's `SFCIdentity` additionally requires instrument_class, holder_sector, issuer_sector, maturity and denomination.
3. The current financial `_identity` does not supply maturity or denomination. The event payloads for bank loan origination/repayment and central-bank refinancing also do not carry contractual maturity, repricing terms or day-count details.
4. `OperatingFinancialRegister.sectors` is a static mapping supplied at construction; it is validated against allowed sector codes but is not an effective-dated, versioned sector-membership history.
5. `deposit_opening_positions` and `reserve_opening_positions` explicitly support only `period_index == 1`.
6. No corresponding `loan_opening_positions` or `refinancing_opening_positions` exporter exists in the inspected register implementation.
7. `history(aggregate_id, principal_id=...)` is available through the durable register and returns immutable history rows; this is a viable source for deterministic replay.
8. The existing `sfc_projection_store.py` is coupled to `FinancialEventStore`, `EntityJournal`, and mapper `gold2a-entity-journal-mapper@1`. It must not be fed operating-financial event envelopes as if they were GOLD-2A journal events.
9. The pure SFC kernel already has explicit opening requirements, T/V/O roll-forward, continuity checks and a transaction-only `financial_net_lending` helper. These are reusable invariants, not evidence that the banking adapter already exists.

## Blockers that must be resolved before claiming complete projection

### B1. Instrument metadata contract

Add a versioned financial-instrument master / immutable instrument terms contract. At minimum:
- instrument_id and instrument_type/class;
- denomination and currency;
- valuation basis;
- contractual maturity or an explicit `PERPETUAL` / `ON_DEMAND` classification where legally correct;
- interest-rate type, index/spread and reset frequency where applicable;
- day-count and payment frequency where interest is in scope;
- origination/effective period and termination/maturity date;
- source authority and evidence references.

Do not invent `ON_DEMAND` for loans or assign generic maturity to unknown instruments. Unsupported or missing terms must fail closed. The current principal-only prototype may initially project nominal principal stocks while explicitly marking maturity and interest dimensions as out of scope; it must not pretend to support liquidity maturity ladders.

### B2. Effective-dated institutional sector registry

Replace the unversioned constructor-only sector mapping as the projection authority with an explicit effective-dated registry (or a stable reference to the existing `EntityRegistry` contract). Pin the registry snapshot/version or digest to each projection batch and recovery checkpoint.

For each movement period, resolve both holder and issuer sectors. Reject missing membership, overlapping membership and retroactive changes that would silently rewrite a sealed projection. Corrections require a versioned re-projection with an auditable reason.

### B3. Opening-stock lifecycle

Define opening snapshots for every supported financial position, not only deposits/reserves in period 1:
- deposits and matching bank liabilities;
- reserves and matching central-bank liabilities;
- loan assets and borrower liabilities;
- refinancing claims and bank liabilities;
- wage claims/payables if included in the same projection.

Support instruments introduced after period 1 using explicit, evidence-backed initial position rows at the instrument's first active period. A zero opening is allowed only as an explicit attested row, never as an implicit missing-row default. Existing account-opening events must remain opening-stock evidence and must not be converted into transaction flows.

### B4. Sector-flow sign convention and aggregation

The adapter must use a typed rule that distinguishes:
- positive increase in a sector-owned financial asset;
- positive increase in a sector-incurred financial liability;
- holder/issuer mirror identity;
- counterparty sector and instrument metadata.

Sector financial net lending for transactions is computed as the change in financial assets minus the change in financial liabilities, by period and currency/valuation basis. Mirror validation is separate from sector aggregation. Never sum both mirror sides as assets, never net currencies, and never use a hidden plug to force the six-sector sum to zero.

The closed six-sector universe includes ROW. A non-zero aggregate after correct mapping is a diagnostic finding, not permission to create a balancing item.

### B5. Period-close completeness

A missing register event stream does not prove that a sector/register had zero activity. Add explicit signed period-close declarations for each register (including zero-activity declarations), source sequence/checkpoint, period bounds, registry version, and evidence. The period assembler may close only when all required registers have declared completeness.

## Implementation sequence

1. Version the instrument terms and financial position identity schema. Preserve migration provenance; do not mutate historical event payloads.
2. Add effective-dated, digest-pinned sector registry resolution.
3. Add evidence-backed opening position snapshots for all supported instrument types and periods.
4. Implement a separate `operating_financial_sfc_adapter.py` and mapper version. It reads immutable financial-register history; it does not call the GOLD-2A mapper.
5. Add a native financial projection store or a clearly isolated adapter boundary. Persist source checkpoint, source-event coverage, movement coverage, opening snapshot digest, mapper version, registry digest, position roll-forward and sector aggregates atomically.
6. Add deterministic recovery/reprojection and crash-injection tests.
7. Add a period-close assembler that combines native register projections and genuine six-register coordinated events without fabricating participant events.
8. Demonstrate multi-period sector financial accounts, capital-account reconciliation and real-economy constraints in an integrated fixture.

## Mandatory tests

- Reject loan/refinancing identities without required terms; reject false maturity defaults.
- Resolve sector membership by effective period and pinned registry digest.
- Detect changed sector membership on recovery.
- Require explicit openings for every position and first-active period.
- Verify loan origination/repayment and refinancing advance/repayment position changes.
- Verify interbank settlement redistributes reserves without changing system-wide reserve stock.
- Verify deposit transfer changes holder-side deposit assets and issuer-side deposit liabilities correctly.
- Verify all six sector financial net lending values by period and currency; no automatic discrepancy plug.
- Reject missing period-close declarations and incomplete source checkpoints.
- Prove idempotent replay and atomic rollback under injected crashes.
- Prove no financial-only event is represented by fabricated physical/labour/product/capital/legal events.
- Reconcile sector financial net lending to capital-account net lending only after all relevant non-financial transactions, capital transfers and statistical discrepancy rules are explicitly represented.

## Definition of done

The adapter is not done when the mapper emits rows. It is done only when:
- all supported instruments have typed metadata and explicit opening-stock provenance;
- source and registry versions are pinned;
- every source event and movement is covered exactly once;
- all position roll-forwards close for multiple consecutive periods;
- mirror checks pass;
- six-sector financial net lending is computed without plugs;
- capital-account reconciliation is independently supported by source events;
- recovery reproduces identical balances and coverage;
- all tests pass on the exact resulting HEAD.

Even a fully closed SFC accounting model does not by itself prove that the economy has sufficient liquidity, that credit finances productive activity, or that the system is solvent. Those are separate empirical and scenario-based tests requiring production, capacity, prices, income distribution, payment timing, maturity and default dynamics.
