# Durable Labour and Legal Rights Registers — implementation contract

## Boundary

LabourRegister and LegalRightsRegister are independent SQLite event-sourced stores. They are not projections over the financial journal and neither may manufacture ownership, consent, labour supply, or legal extinguishment from a contribution score or model output.

Both stores provide:
- canonical finite JSON payloads, global append sequence, per-aggregate optimistic versions and idempotency keys;
- immutable event rows and SHA-256 hash-chain verification over the full event envelope;
- replay-derived state (no mutable projection is treated as authority);
- append-only ACL grants/revocations, default-deny read/write permissions and last-administrator protection;
- effective/recorded UTC timestamps, actor, authority reference, evidence references and correction lineage;
- durable coordinator prepare/commit/abort methods using the same register database as the authoritative event log.

A prepared operation reserves its aggregate. Its authorization is evaluated and its transition validated at prepare time. ACL mutations are serialized behind outstanding prepares. Commit appends the native event and then records the participant receipt; if a process dies between those steps, an idempotent retry completes the receipt. The coordinator's six-participant visibility barrier remains the global publication boundary.

## Labour register

Aggregate families:
- engagement: OFFERED → ACCEPTED → SCHEDULED → STARTED → DELIVERED → VERIFIED → SETTLED, with explicit decline, withdrawal, stop, cancellation and dispute paths;
- capability: person + skill-specific assessment history with declared proficiency scale and evidence;
- time allocation: person + period, mutually exclusive typed intervals, no overlap and no allocation beyond period duration.

The register distinguishes offered, accepted, scheduled, started, delivered, verified, disputed and settled hours. Acceptance requires an explicit consent reference. Delivered hours cannot exceed scheduled hours. A correction is a new hours.corrected event with a reason, a reference to the immutable delivery event and a signed delta; the original event is never edited.

Person identifiers are opaque references. The register does not require names, addresses, health information or other unnecessary personal data. Deployments must keep identity resolution and sensitive evidence in a separately controlled system.

## Legal Rights Register

A claim/right aggregate records holder, optional obligor, right type, scope, jurisdiction, legal instrument, effective date and evidence. Events support evidence attachment, transfer, encumbrance, release, dispute, adjudication, correction and legal extinguishment.

Transfer requires the current holder and transfer instrument. Encumbrances have unique IDs, beneficiary, scope, positive priority, instrument and evidence. Active encumbrances must be released before extinguishment. A creditor write-off is not represented as legal forgiveness: only an explicitly evidenced right.extinguished event changes legal status. Rights are never inferred from labour or time records.

## Coordinator integration

The stores implement the participant protocol natively: prepare, commit, abort, status, event_count and committed_event. The coordinator can therefore commit labour and legal-rights events into their authoritative domain event logs rather than duplicate protocol-only SQLite event stores.

This is a partial six-register integration. Physical, capital, product and financial participant adapters still require the same native-store transaction contract before the whole economic command can be described as authoritative across all six registers. SQLite WAL and process locks are single-host/shared-filesystem mechanisms, not cross-host consensus.

## Security and recovery limitations

Hash chains and SQLite immutability triggers detect accidental/tamper corruption but do not authenticate a privileged database administrator who can rewrite the whole database and recompute the chain. Production deployments still need independent signing, externally administered trust roots, encrypted backups, remote immutable checkpoints, access review, retention and restore drills.
