# Canonical Economic Entity Register v1

Status: implemented prototype on top of the durable register substrate; not a production legal-identity authority.

## Authority boundaries

The canonical entity register is the source of truth for:
- stable tenant-scoped economic entity IDs;
- entity kind and jurisdiction;
- explicit, effective-dated institutional-sector membership;
- issuer-attested external registry references;
- entity lifecycle state (active, suspended, retired).

It is not a land/title register and does not prove beneficial ownership, lease, control, encumbrances or legal disputes. Those facts remain in the Legal Rights Register and their authoritative evidence. It does not own balances, prices, credit, payments or settlement.

## Event model

Supported append-only domain events:
- `entity.registered`
- `entity.updated` (jurisdiction and display name only)
- `entity.external_reference_added`
- `entity.sector_changed`
- `entity.suspended`
- `entity.reactivated`
- `entity.retired`

Identity and tenant scope are immutable. Entity kind is immutable. External references are append-only. Sector membership is effective-dated and never inferred. Event effective times cannot move backwards. Aggregate versions and idempotency are enforced by `DurableEventRegister`.

## Two independent integrity controls

1. The local append-only SHA-256 event chain detects payload, ordering and storage tampering.
2. Every domain event also requires an Ed25519 signature over the canonical event envelope, including event ID/type, aggregate, effective/recorded times, actor, authority reference and unsigned domain payload.

A SHA-256 digest is not treated as proof of issuer identity. The verifier checks the Ed25519 key, issuer, tenant, authority-ref scope, key validity interval and revocation time. Historical signatures remain valid only when signed before the effective revocation time.

The canonical resolver snapshot carries the event-chain digest as `source_digest`, the final source event ID as `authority_event_ref`, and `verified: true` only after the register has replayed and validated the signed event history.

## Tenant and register authorization

The register requires both:
- the existing durable register ACL (`entity:read`, `entity:write`, `entity:admin`);
- a mandatory tenant authorization callback receiving `principal_id`, `tenant_id`, permission and (for writes) the signed `authority_ref`.

Tenant checks apply to direct event append, state reads, history reads and resolver calls. Authorization service failure denies access. Native six-register transaction participation and unscoped cross-register event lookup are deliberately disabled for this authority register.

The `CanonicalEconomicEntityResolverAdapter` exposes the two-argument resolver interface expected by Synergy Metaverse. Configure a dedicated service principal with both register-level `entity:read` and tenant-level read authorization for each permitted tenant.

## Snapshot contract

Schema: `schemas/canonical-economic-entity-snapshot-v1.schema.json`

The resolver returns tenant/entity identity, entity kind, jurisdiction, effective sector, aggregate version/status, authority system/event, 64-character source digest, verification flag, effective timestamp and append-only external references.

## Integration example

```python
verifier = Ed25519EntityAuthorityVerifier(trusted_key_snapshot)
register = CanonicalEconomicEntityRegister(
    database_path,
    authority_verifier=verifier,
    tenant_authorizer=tenant_policy_service.authorize,
)
resolver = CanonicalEconomicEntityResolverAdapter(
    register,
    service_principal_id="metaverse-entity-reader",
)
snapshot = resolver.resolve_entity("tenant-kz", "economic-entity-001")
```

The Metaverse `BusinessTwinBindingStore` can receive this adapter as its `authority_resolver`. It then checks the tenant, entity ID, institutional sector, source event reference, version, active status and verified digest before accepting a spatial binding.

Do not store personal national IDs, passport numbers, subscriber IDs or raw identity documents in the entity register. Store opaque evidence references to a separately permissioned legal-evidence vault. Public company registration references may be retained only after jurisdictional legal review.

## Production release blockers

- Durable, independently governed authority-key registry with registration, rotation, revocation, audit and trusted-root bootstrap.
- Production tenant IAM/policy adapter and key distribution/revocation freshness guarantees.
- Secure evidence vault, encryption-at-rest and retention/erasure policy for regulated identifiers.
- Authenticated remote resolver API between separate Economics and Metaverse deployments; the in-process adapter is a reference integration, not a network service.
- Jurisdiction-specific validation of company, sole-proprietor, household, financial institution and public-sector identity sources across EAEU countries.
- Independent review that legal title/ownership facts remain in the Legal Rights Register and are not inferred from spatial co-location.
- Full prototype CI, schema CI and downstream Metaverse CI green before merge or production claims.
