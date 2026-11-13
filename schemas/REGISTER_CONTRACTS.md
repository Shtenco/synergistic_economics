# Six-register schema and migration contract

**Envelope:** `synergy.native-register-event`; **current version:** 1; **legacy version:** 0 (unversioned).

Registers: physical, capital, labour, product, legal_rights, financial.

The canonical JSON Schema is `native-register-event-envelope-v1.schema.json`; runtime validation and deterministic migration live in `prototype/register_event_contract.py`.

## Contract

A coordinated event carries schema ID/version, register identity, event type, effective and recorded UTC timestamps, actor, authority reference, idempotency key and an object-valued domain payload. Optional stock-flow metadata is included in the immutable digest.

## Migration

Unversioned v0 envelopes are upgraded additively to v1 before prepare and digest calculation. The migration adds the schema identity, register identity and `migration` provenance marker. It does not reinterpret domain payloads, IDs, timestamps, authority or idempotency keys. V1 normalization is idempotent. Partial identities, mismatched registers, malformed UTC timestamps and unknown future versions fail closed.

The normalized envelope is retained in participant inbox evidence and the common event group. Existing domain event histories are not silently rewritten.

## Compatibility boundary

- New coordinated writes use v1.
- Historical unversioned inbox/event-group data remains readable as legacy evidence; no destructive backfill is performed.
- Breaking changes require a new schema version, explicit migration, fixture corpus, downgrade rejection, and upgrade/replay tests against copies of all six native stores.
- Each store's database schema version and migration history remain independently governed. Envelope versioning is not a substitute for a coordinated six-database migration.

**Open boundary:** this work versions the shared event envelope and durable coordinator evidence; it does not claim that all six SQLite database schemas now share one database schema version.
