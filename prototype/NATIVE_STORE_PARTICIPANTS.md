# Native domain-store coordinator adapters

## Purpose

native_store_participants.py binds the existing physical-flow, capital-cohort and product register SQLite databases directly to CrossRegisterCoordinator. The participant inbox is installed in the same database file as the domain store. It does not create a second authoritative event log.

## Prepare/commit protocol

1. The coordinator supplies a transaction ID, stream ID, native event ID, expected revision and canonical event envelope.
2. The adapter checks UTC event times, immutable event/idempotency identity, current native revision and an injected external authorization decision.
3. The domain-specific validator checks the candidate against the existing store's invariants/reducer without committing it.
4. A durable PREPARED inbox row reserves the register stream. The store's ordinary append path rejects writes while the reservation exists.
5. After the coordinator records its irreversible COMMIT decision, the adapter invokes the native idempotent append with the matching prepared transaction ID.
6. It records a participant receipt. If the process dies after step 5 but before step 6, retry repeats the idempotent append and completes the receipt.
7. The coordinator's global read barrier remains the publication boundary; consumers should use committed_event_group rather than reading one participant as if the whole transaction were already visible.

The inbox protects immutable prepared content, forbids deletion, constrains state transitions and verifies the payload digest on commit/read. It is a recoverable prepare/commit protocol across independent SQLite databases, not one cross-database SQL transaction.

## Current adapters

- PhysicalFlowStore: one paired outflow/inflow physical flow, stable flow ID, native-unit and endpoint mirror validation.
- CapitalCohortStore: contiguous cohort period transition, replay validation and native period append.
- ProductRegister: product specification, balance, price quote and valuation events, validated by the product reducer.
- LabourRegister and LegalRightsRegister use their own native participant implementations in durable_event_register.py.

The adapter requires an explicit external authorizer callback. Tests use a controlled test authorizer; production must bind a signed authority/permission service and preserve its decision reference. No implicit allow-all policy is provided.

## Remaining boundaries

1. FinancialEventStore still requires a native adapter around the validated EntityJournal and projection-aware append path. A raw append_group adapter would bypass the financial/SFC atomic projection boundary and is intentionally not supplied.
2. PhysicalFlowStore is the physical-flow component. The P6 lot inventory, reservations and custody lifecycle are not yet combined with it in one physical participant.
3. The coordinator still uses a recoverable multi-participant protocol, not a single database transaction. Every consumer must respect the global visibility barrier.
4. The stock-flow mapper currently proves a physical sender/receiver flow. Actual capital, product, labour, legal and financial event-to-T/V/O mappings and a multi-period six-register close remain required.
5. Cross-host consensus, independent authority service, encrypted deployment, external WORM checkpoint custody and production restore/RPO/RTO are separate release gates.

Five of six coordinator participants now use native domain stores. Do not describe the system as a complete six-register production ledger.
