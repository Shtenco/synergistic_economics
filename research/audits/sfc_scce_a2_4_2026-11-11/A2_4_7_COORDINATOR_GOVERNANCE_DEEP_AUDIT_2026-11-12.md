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

### F-CR-02 — concurrent coordinator workers are not fenced

The coordinator uses SQLite transactions for individual state changes, but the protocol has no durable worker lease, fencing token, or single-flight claim for a transaction. Two workers can both observe a nonterminal state and enter `execute()`/recovery concurrently. Per-participant idempotency limits duplicate event insertion, but it does not establish a single ordered coordinator owner or make all state transitions safe under competing workers.

**Required remediation**
- Add an atomic transaction claim with monotonically increasing fencing epoch and lease expiry, or explicitly enforce a single coordinator process with an OS/database lock whose crash semantics are tested.
- Require every state transition and participant call sequence to carry the current fencing epoch.
- Add two-process race tests for execute-vs-execute, execute-vs-recover, and recover-vs-recover at prepare and commit boundaries.

### F-CR-03 — native-event visibility verification (IMPLEMENTED; CI PENDING)

`is_visible()` checks coordinator state, participant inbox state and receipt equality. It does not independently read the participant's native event row and verify native event ID, stream, revision and payload digest. The current SQLite participant writes event and receipt in one transaction, but the barrier's proof is weaker than the production contract it is intended to represent.

**Remediation committed**
- The protocol participant now exposes its persisted native event record separately from its inbox receipt.
- `is_visible()` requires exactly one native event and verifies transaction ID, native event ID, stream, next revision, canonical payload and digest against the coordinator operation.
- The crash-matrix audit deletes a native event while retaining the committed inbox/receipt and requires visibility to fail closed; a repeated execute must reject the inconsistent terminal transaction.

**Remaining validation:** execute the tamper control and full crash matrix on the exact resulting HEAD. Production adapters still need their own authoritative-store verifier.

### F-GOV-01 — approval roles are caller-asserted, not authenticated

`approve_reopen()` accepts `approver_id` and `role` from the caller and checks only that the two identifiers differ. It does not authenticate the caller or verify that the identity is authorized for the requested role, period and service. Distinct strings do not prove independent authorized approval.

**Required remediation**
- Require an authorization verifier or signed identity/role assertion from an independently administered identity provider.
- Bind each approval to request digest, period, old/new generation, complete six-register scope, reason, evidence reference, role, approver identity and expiry.
- Verify role authorization and separation-of-duties policy before inserting the immutable approval.
- Add tests for unauthorized identities, role spoofing, revoked identities, expired assertions, changed request scope and replay across requests/services.

### F-GOV-02 — publication checkpoint is not bound to rebuild roots and reconciliation

`publish_generation()` verifies that six receipts share a source root and generation numbers, and that the signed manifest identifies the period/new generation. It does not require the manifest's `event_log_root` to equal the six receipts' shared `source_event_root`, nor does it bind `projection_state_hash` to the supplied global reconciliation hash. A correctly signed checkpoint for the same period/generation can therefore be paired with unrelated internally consistent receipt/reconciliation values.

**Required remediation**
- Require `manifest.event_log_root == source_event_root`.
- Define a canonical reconciliation object, hash it, and require the signed checkpoint's projection/reconciliation commitment to match that hash.
- Bind all six participant receipt digests into the canonical global reconciliation object.
- Add negative tests using a valid signed checkpoint with a different event root, different projection hash and mismatched participant receipt inventory.

### F-GOV-03 — rebuild receipts are accepted as caller-supplied attestations

The governance database validates receipt field shape and cross-register agreement, but does not establish that each domain register actually replayed the complete immutable event log, persisted the rebuilt generation, or independently reconciled its opening/closing state. This is an explicit adapter/integration gap, not proof of a successful rebuild.

**Required remediation**
- Accept receipts only from authenticated participant rebuild adapters.
- Require durable generation IDs and a queryable immutable rebuild artifact before publication.
- Verify source cursor/root, event count, opening state hash, closing state hash and reconciliation evidence against the authoritative participant store.
- Preserve the old generation and prove that it remains readable until the new generation is published.

### F-CHK-01 — local anchor mutation contract is weaker than its publication helper

`LocalImmutableAnchor.advance_latest()` records the supplied object key and digest without independently checking that the immutable object exists and that its stored bytes hash to that digest. The normal `publish_checkpoint()` helper writes the object first, but the anchor method itself does not enforce this invariant. A malformed direct call can advance the latest pointer to an absent or mismatched object and make recovery unavailable.

**Required remediation**
- In one anchor transaction, require an existing immutable object and compare its stored digest to the requested digest before advancing latest.
- Add a foreign-key or equivalent relational constraint where practical.
- Define an explicit trusted bootstrap rule for the first checkpoint sequence; do not silently accept an arbitrary starting sequence.
- Test missing object, wrong digest, arbitrary first sequence, concurrent sequence advancement and replay.

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

These are source/test commits, not execution evidence. The full CI run must complete on the resulting exact HEAD before either remediation is marked PASS.

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

At the live job inspection during this audit, all three jobs remained `queued`, with no executed steps and no logs. No PASS is claimed.

## Gate disposition

- Coordinator protocol core: implemented; additional idempotency, concurrency fencing and native-event verification required.
- Closed-period governance: implemented as a governance ledger; authenticated approvals and cryptographically bound rebuild publication required.
- External checkpoint: Ed25519 manifest verification implemented; local anchor remains conformance-only and its direct mutation contract needs hardening.
- Disaster recovery: protocol-store backup/restore fixture implemented; authoritative domain-store recovery and canonical participant event-root verification remain open.
- Production: NOT READY. Keep PR #4 Draft/Open and do not merge. Canonical `main` remains unchanged.
