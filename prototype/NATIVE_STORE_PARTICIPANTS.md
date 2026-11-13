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


## Signed first-administrator bootstrap

For production composition, construct `SignedApprovalVerifier` with an independently administered issuer key resolver and live revocation callback, then wrap it in `SignedBootstrapAuthorizer` from `signed_approval_assertions.py` and inject that callable as `bootstrap_authorizer` into `LabourRegister` / `LegalRightsRegister`. The `authority_ref` supplied to `bootstrap_admin()` is the compact EdDSA JWT/JWS assertion itself. Its signed claims must use the register name as `service_id`, the stable `REGISTER:ACL:BOOTSTRAP:PRINCIPAL` request ID, the `bootstrap_admin` role, the principal as `sub`, and the SHA-256 request digest returned by `SignedBootstrapAuthorizer.request_context()`. The assertion is short-lived, audience/issuer/key bound, revocation checked and replay protected by the verifier.

The adapter is production-capable verification logic, not a production identity provider. This repository still does not operate the issuer, key-distribution service, revocation service or their independent trust domain. Never use the deterministic test signer/key resolver as production authority.

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

All six coordinator participants now target native domain stores. Do not describe the system as a complete six-register production ledger.


## Financial participant

The financial adapter requires an already activated and replay-verified SFC opening snapshot. It decodes canonical JournalEvent payloads, validates them with a fresh EntityJournal against the same EntityRegistry, and commits through append_projected_group. This single FinancialEventStore transaction contains the immutable event group, journal lines, instrument/control projection deltas, coverage, event checkpoints and projection cursor. The prepare inbox is colocated in the same database and its reservation is checked by append_projected_group.

The financial T/V/O movement metadata is independently derived by the same `_map_event` function used by the SFC projection and compared byte-for-byte with the command's declaration. The current bridge covers SFC instrument asset positions; control-only and all liability-side movement declarations still need explicit extensions and independent GOLD mirror evidence. The coordinator orders commits with financial last, after all other five participants have committed. This makes an SFC projection commit evidence that the other domain participants have already committed, while global readers still use the coordinator visibility barrier.


## Native commit-retry fault injection

The native participant test suite now injects a failure after PhysicalFlowStore has committed its native append but before the coordinator receipt is persisted. A newly constructed participant retries the same immutable prepare; the native append is idempotent, the receipt completes, and the event count remains one. This covers the native append/receipt crash window without weakening the global commit barrier.


## Financial journal restart replay

On adapter construction, committed FinancialEventStore groups are replayed in immutable commit order into the supplied EntityJournal after the store verifies its event-group and posting-mirror chains. A conflicting preloaded in-memory event is rejected. This prevents a restarted process from validating new journal events against an empty in-memory journal while durable financial history already exists. The native integration test reopens all six stores and the coordinator, then verifies the committed event group and global visibility barrier.


## Durable common event stream

After all six participant receipts verify, the coordinator persists the assembled canonical event group in its own append-only `coordinator_event_groups` table. Groups have a monotonic commit sequence, canonical payload digest, previous hash and group hash. Update/delete triggers reject history mutation; startup and reads verify the complete chain. The global read barrier is crossed only after the event group is durable and the transaction state is COMMITTED. `iter_committed_event_groups()` returns the committed prefix; `latest_event_group_checkpoint()` supplies the current sequence/hash for external anchoring. A crash after group persistence but before the COMMITTED barrier is recoverable and explicitly fault-injected.


The coordinator also exposes reconcile_event_stream(opening_positions, closing_positions), which reads only the verified committed-prefix and routes its canonical T/V/O movement declarations through the shared period reconciliation kernel. Current supported movement mappings remain physical flow endpoints and financial instrument asset positions; the method fails closed if any participant has neither a valid movement declaration nor an explicit no-effect declaration.
