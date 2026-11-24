# CCM canonical governance evidence boundary

**Status:** executable integration contract; not a production trust service.  
**Scope:** read-only validation of participation, policy, delegation and ballot evidence before governance evaluation.

## Problem addressed

The base CCM domain contract deliberately stores references to consent, rights, delegation authority and ballot evidence. A non-empty reference alone does not establish that the record belongs to the correct subject, host, participation, mandate or decision, or that it was still valid when the vote occurred.

The strict adapter in `prototype/cellular_cooperative_evidence.py` adds a fail-closed boundary around the existing `evaluate_governance` function. It does not replace canonical registers and does not execute decisions.

## Evidence bindings

| Evidence kind | Subject | Resource | Scope |
|---|---|---|---|
| `governance_policy` | Governing subject | Governing subject | Exact `domain:action` |
| `participation_consent` | Participating subject | Exact participation ID | `host_id:capacity` |
| `participation_rights` | Participating subject | Exact participation ID | `host_id:capacity` |
| `delegation_authority` | Represented organization | Exact delegate participation ID | `governing_subject:domain:action` |
| `governance_ballot` | Voter principal | Immutable decision ID | `governing_subject:domain:action` |

Each evidence record also carries issuer and source-snapshot references, a payload SHA-256 digest, verification time, validity start/end and optional revocation time. Expired, revoked, future-verified, mis-scoped, mis-bound or absent evidence is rejected.

The decision ID binding is essential: a ballot proof for one proposal cannot be replayed as a ballot for another proposal merely because the voter, action and policy are otherwise identical. Participation ID binding similarly prevents a consent or rights reference from silently authorizing a different participation record.

## Trust boundary — do not overclaim

`CanonicalEvidence` is a typed assertion supplied by a canonical authority adapter. It is not self-authenticating. A caller can construct the dataclass; therefore the dataclass and its SHA-256 field do not independently prove a signature, issuer identity, legal authority, source freshness or revocation completeness.

Production integration must:
1. Resolve consent, rights, delegation, policy and ballot records from their canonical authoritative services.
2. Authenticate the source and verify signatures/proofs and payload digests using trusted keys and current revocation state.
3. Enforce tenant, jurisdiction, audience and scope restrictions before constructing the adapter records.
4. Use immutable decision IDs and canonical event IDs; enforce durable replay protection in the source/event store.
5. Pass only independently verified records to `evaluate_governance_with_canonical_evidence`.
6. Persist the decision and its evidence snapshot through the canonical governance/audit service; this prototype only evaluates.

A future integration should replace the caller-supplied mapping with a narrow resolver interface or a verified evidence bundle whose provenance is authenticated by the canonical authority stack. It must not create a parallel membership, consent, rights or identity registry.

## Current limitations

- The adapter checks that a record is valid at the supplied decision time; it cannot prove the caller's clock is trusted.
- Revocation completeness depends on the canonical resolver and its snapshot/finality semantics.
- No quorum snapshot, eligible-voter snapshot, signed decision envelope, durable ballot uniqueness store or appeal workflow is persisted here.
- Protected actions remain outside generic governance evaluation and require separate legal/authority workflows.
- No legal entity, title, debt, guarantee, payment, journal or settlement state is created or changed.

## Tests

`prototype/test_cellular_cooperative_evidence.py` covers valid member and organization-delegate votes, missing and mismatched consent/rights, expiration, revocation, wrong policy/ballot scope, future verification, evidence-map substitution, duplicate ballot evidence, and cross-decision ballot replay.

These are unit-level contract tests. They do not replace integration tests against the actual canonical rights/consent/policy resolver.
