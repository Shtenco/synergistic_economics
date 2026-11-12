# A2.4.7 coordinator, governance and recovery deep audit — 12 November 2026

## Scope and evidence boundary

This is a source-level review of the branch-ref implementations:

- `prototype/cross_register_coordinator.py`
- `prototype/period_governance.py`
- `prototype/external_checkpoints.py`
- `research/audits/sfc_scce_a2_4_2026-11-11/audit_cross_register_crash_matrix.py`
- `research/audits/sfc_scce_a2_4_2026-11-11/audit_cross_register_disaster_recovery.py`

No successful execution is inferred from source inspection. The six SQLite participants remain protocol conformance stores, not authoritative domain-register adapters. The findings below are open until code changes and adversarial tests pass on one exact commit.

## Findings

### F-CR-01 — execute retry idempotency (IMPLEMENTED; CI PENDING)

`submit()` treats identical transaction-envelope delivery as idempotent, and `recover()` returns terminal state. However, `execute()` unconditionally attempts `NEW/PREPARING` transition before inspecting the existing transaction state. Re-executing an already `COMMITTED` or `ABORTED` transaction therefore raises an illegal-transition error rather than returning its durable terminal result.

**Remediation committed**
- `execute(txid)` now inspects durable state before attempting any transition.
- `COMMITTED` returns only after native-event visibility verification; `ABORTED` returns the terminal abort result; decision-in-progress states resume through recovery.
- The crash matrix now retries `execute()` after recovery at all 27 crash points and tests terminal committed/aborted retries.
- A lost-response retry and changed-envelope replay controls are included.

**Remaining validation:** execute the complete crash matrix on the exact resulting HEAD. Concurrent worker fencing remains a separate open finding (F-CR-02).

### F-CR-02 — cross-process coordinator execution lock (IMPLEMENTED; CI PENDING)

The coordinator uses SQLite transactions for individual state changes, but the protocol has no durable worker lease, fencing token, or single-flight claim for a transaction. Two workers can both observe a nonterminal state and enter `execute()`/recovery concurrently. Per-participant idempotency limits duplicate event insertion, but it does not establish a single ordered coordinator owner or make all state transitions safe under competing workers.

**Remediation committed**
- Independent coordinator instances sharing the same coordinator database path now acquire a crash-released SQLite `BEGIN EXCLUSIVE` lock in a separate lock database before executing or recovering. The separate lock database avoids blocking participant/coordinator state writes while the execution lock is held.
- The lock is acquired by the OS-backed SQLite file-lock mechanism and is automatically released on process termination; no stale lease holder can continue after a replacement acquires the lock on the same reliable filesystem.
- The crash matrix now starts two independent processes for execute-vs-execute and recover-vs-recover, then verifies one native effect per participant and a valid final visibility barrier.

**Explicit limitation:** this is a conservative single-writer conformance mechanism for a local/shared filesystem with reliable SQLite locking. It serializes all transactions and is not a multi-host distributed lease/fencing protocol. Production deployments on independent hosts require a transactional lock/lease service and participant-enforced fencing epochs. Execute-vs-recover race coverage remains a required extension.

### F-CR-03 — native-event visibility verification (IMPLEMENTED; CI PENDING)

`is_visible()` checks coordinator state, participant inbox state and receipt equality. It does not independently read the participant's native event row and verify native event ID, stream, revision and payload digest. The current SQLite participant writes event and receipt in one transaction, but the barrier's proof is weaker than the production contract it is intended to represent.

**Remediation committed**
- The protocol participant now exposes its persisted native event record separately from its inbox receipt.
- `is_visible()` requires exactly one native event and verifies transaction ID, native event ID, stream, next revision, canonical payload and digest against the coordinator operation.
- The crash-matrix audit deletes a native event while retaining the committed inbox/receipt and requires visibility to fail closed; a repeated execute must reject the inconsistent terminal transaction.

**Remaining validation:** execute the tamper control and full crash matrix on the exact resulting HEAD. Production adapters still need their own authoritative-store verifier.

### F-GOV-01 — approval authorization verifier (IMPLEMENTED AS CONTRACT; CI PENDING)

`approve_reopen()` accepts `approver_id` and `role` from the caller and checks only that the two identifiers differ. It does not authenticate the caller or verify that the identity is authorized for the requested role, period and service. Distinct strings do not prove independent authorized approval.

**Remediation committed**
- `PeriodGovernance` now requires an injected `authorization_verifier`; construction fails if it is absent.
- Before recording approval, governance builds a canonical request context containing service ID, request ID, period, old/new generation, reason, evidence, complete six-register scope and active pre-reopen checkpoint, then computes a request digest.
- The verifier must authenticate the approver, authorize the requested role for that exact context, and validate the supplied independent assertion reference. Any exception or result other than literal `True` fails closed.
- The governance audit supplies a deterministic test verifier and rejects a forged proof reference and an unauthorized identity before accepting the two distinct role approvals.

**Explicit limitation:** the audit verifier is a test fixture, not an identity provider. Production still requires an independently administered signed assertion/identity service with revocation, expiry, audience/service binding, replay protection and auditable key rotation. The governance API now enforces that boundary rather than trusting caller-supplied role strings.

### F-GOV-02 — signed checkpoint/rebuild binding (IMPLEMENTED; CI PENDING)

`publish_generation()` verifies that six receipts share a source root and generation numbers, and that the signed manifest identifies the period/new generation. It does not require the manifest's `event_log_root` to equal the six receipts' shared `source_event_root`, nor does it bind `projection_state_hash` to the supplied global reconciliation hash. A correctly signed checkpoint for the same period/generation can therefore be paired with unrelated internally consistent receipt/reconciliation values.

**Remediation committed**
- Publication now builds a canonical, register-name-ordered inventory of all six persisted rebuild receipts and recomputes its SHA-256 digest.
- The caller-supplied global reconciliation hash must equal that digest.
- The signed checkpoint's `event_log_root` must equal the shared source root, and its `projection_state_hash` must equal the computed six-receipt reconciliation digest.
- The governance audit now rejects a validly signed checkpoint for another event root and rejects an unrelated global reconciliation hash.

**Remaining validation:** run the governance audit and full A2.4 workflow on the exact resulting HEAD. This binds attestations; it does not yet prove that the receipts were produced by authenticated authoritative-domain rebuild adapters (F-GOV-03).

### F-GOV-03 — rebuild receipts are accepted as caller-supplied attestations

The governance database validates receipt field shape and cross-register agreement, but does not establish that each domain register actually replayed the complete immutable event log, persisted the rebuilt generation, or independently reconciled its opening/closing state. This is an explicit adapter/integration gap, not proof of a successful rebuild.

**Required remediation**
- Accept receipts only from authenticated participant rebuild adapters.
- Require durable generation IDs and a queryable immutable rebuild artifact before publication.
- Verify source cursor/root, event count, opening state hash, closing state hash and reconciliation evidence against the authoritative participant store.
- Preserve the old generation and prove that it remains readable until the new generation is published.

### F-CHK-01 — local anchor object/digest binding (IMPLEMENTED; CI PENDING)

`LocalImmutableAnchor.advance_latest()` records the supplied object key and digest without independently checking that the immutable object exists and that its stored bytes hash to that digest. The normal `publish_checkpoint()` helper writes the object first, but the anchor method itself does not enforce this invariant. A malformed direct call can advance the latest pointer to an absent or mismatched object and make recovery unavailable.

**Remediation committed**
- `advance_latest()` now validates service ID, sequence, object key and digest inputs.
- Inside the same SQLite write transaction, it requires the immutable object to exist and verifies both its stored digest and the digest recomputed from its bytes before changing the latest pointer.
- The checkpoint audit now tests missing objects and mismatched digests separately, while retaining a distinct sequence-gap control.

**Remaining validation:** run the external-checkpoint audit on the exact resulting HEAD. A production anchor still requires independently administered WORM/object-lock and external trust-root custody.

### F-DR-01 — disaster-recovery event root label is not a root of all participant event logs

The DR fixture computes `event_log_root` from the coordinator transaction envelope JSON. That is a transaction-envelope digest, not a root over the six participant native event logs or their receipt inventory. The backup package digest does bind the archived database bytes, and the fixture separately verifies participant events after restore; nevertheless, the manifest field name overstates what the event root commits to.

**Required remediation**
- Define a canonical cross-register event-root construction over ordered participant event identities, payload digests, revisions and commit receipts (or explicitly rename the field to coordinator-envelope digest).
- Include the participant set and schema/version domain separator.
- Recompute the root independently before and after restore and compare it to the signed manifest.
- Add reorder, omission, duplicate, changed-payload and changed-receipt negative controls.

## Remediation commits — 12 November 2026

- `209c442b3f8f9093c2bbd4f405a097a6efc6ef10`: terminal-state idempotent execute/recovery handling and native-event verification in the visibility barrier.
- `5921b7ede87aee223042d83fe9f08efd8b039a5f`: crash-matrix assertions for repeated execute, terminal abort retry and native-event deletion tampering.
- `17e085fe38d5b86e0ab27b409a52c59beaa4c261`: checkpoint anchor requires an existing object whose bytes match the supplied digest.
- `cae07e97c6b693b89b1315737a7775fe6d305290`: missing-object and wrong-digest anchor negative controls.
- `afa6907b56a7ad7eed5f8000a58277d443248724`: signed period-generation publication bound to the six-receipt reconciliation digest and event root.
- `49770b1b2a74591b67336a59b7e7926b39e8629d`: governance negative controls for wrong event root and unrelated global reconciliation.

These are source/test commits, not execution evidence. The full CI run must complete on the resulting exact HEAD before any remediation is marked PASS. Because the workflows use `cancel-in-progress: true`, rapid successive commits can cancel older runs; wait for the final branch push to settle and inspect its exact SHA.

## Crash matrix review

The 27 crash points are correctly enumerated as four participant-local boundaries for each of six participants plus three global barriers:

- after each participant prepare;
- after each coordinator prepare receipt;
- after each participant commit;
- after each coordinator commit receipt;
- after all-prepared barrier;
- after durable commit decision;
- after final commit barrier.

The test distinguishes pre-decision abort from post-decision completion. This is valuable protocol-core coverage, but it does not prove host/power-loss durability, cross-process worker fencing, remote participant authentication, or authoritative domain-store integration. The matrix must be extended with the races and native-event tampering described above.

## CI and release gate

The inspected workflow definitions run the A2.4 audit controls, prototype unittest suite and SCCE Stage-C2 validation on branch pushes/path changes. The latest known run IDs from the prior checkpoint are:

- Prototype: `43206084501`
- A2.4 audit controls: `43206084481`
- SCCE Stage-C2: `43206084428`

At the subsequent live poll, the three previously identified jobs had been cancelled (completed with conclusion `cancelled`), not passed. The latest source/test commits have an empty combined-status response and no PR-triggered runs are exposed by the available lookup. The workflows are push-triggered; their fresh exact-HEAD run IDs and logs have not yet been observed. No PASS is claimed.

## Gate disposition

- Coordinator protocol core: idempotent terminal retries and native-event verification implemented; a shared-filesystem single-writer lock and two-process race controls are committed. Multi-host fencing and execute-vs-recover race coverage remain open.
- Closed-period governance: mandatory request-bound authorization-verifier contract and negative controls are committed; production identity-provider integration and authenticated rebuild execution remain open.
- External checkpoint: Ed25519 manifest verification implemented; local anchor remains conformance-only and its direct mutation contract needs hardening.
- Disaster recovery: protocol-store backup/restore fixture implemented; authoritative domain-store recovery and canonical participant event-root verification remain open.
- Production: NOT READY. Keep PR #4 Draft/Open and do not merge. Canonical `main` remains unchanged.
