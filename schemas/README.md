# Canonical Economic Data Contracts

**Schema version:** 1.0.0  
**Dialect:** JSON Schema Draft 2020-12  
**Status:** Initial structural contract; subject to review before production use.

## Purpose

These contracts define interoperable record shapes for the SYNERGY economic research and simulation system. They keep identity, institutional structure, assets, accounting references, contractual claims, contribution evidence and economic events explicit and separately addressable.

## Included record types

| Record | Meaning | Does not prove |
|---|---|---|
| Person | Participant identity within the model | Civil identity or legal capacity |
| Household | Household grouping and selected needs | Consent to every use |
| Enterprise | Productive/legal organization | Solvency or ownership by itself |
| Economic cell | Polycentric coordination unit | Legal personality |
| Federation | Network of cells | Authority beyond its charter |
| Asset | Productive, financial or ecological resource | Unencumbered title or market value |
| Project | Bounded activity with participants and objectives | Positive NPV or success |
| Account | Ledger/accounting endpoint | A bank account or independently held money |
| Contract | Reference to terms and parties | Enforceability or valid consent |
| Ownership claim | Typed claim to a specific right | Verified title unless independently confirmed |
| Contribution | Contribution observation and evidence | Ownership, entitlement, human worth or causal certainty |
| Economic event | Recorded event candidate | Physical truth merely because it was recorded |

## Non-negotiable semantic boundaries

1. **Contribution is not ownership.** Contribution records may contain an experimental SCI score, but SCI never establishes title, governance rights, payment entitlement or human worth.
2. **Ownership is a typed bundle of rights.** Legal title, beneficial interest, usufruct, license, security interest, residual cash flow and governance rights are distinct claims.
3. **An account is not an asset.** Account records point to ledger structures. Balances must be derived from posted journal entries.
4. **Credit principal is not income.** Loans, receivables, payables and deposits remain distinguishable in accounting.
5. **Token balances are not legal claims by default.** Legal basis, issuer, redemption/settlement rules and jurisdictional analysis are required before a token represents enforceable rights.
6. **Internal transfers cancel on consolidation.** Consolidated reports eliminate reciprocal intra-network positions and flows.
7. **Evidence has provenance and limitations.** Provenance fields do not certify the source.
8. **Events are idempotent.** Producers supply stable idempotency keys. Corrections use compensating/reversal events, not silent mutation.
9. **Time is explicit.** Effective time and recorded time are separate.
10. **Money is exact.** Canonical money uses integer minor units, currency and scale; binary floating-point amounts are prohibited.

## Validation boundary

The schema validates structure and local constraints. It cannot validate cross-record references, database-wide uniqueness, legal status, accounting balance, asset existence, consent validity, causal contribution or economic outcomes. Those require application-level checks, independent evidence and, where relevant, legal review.

The root schema accepts one canonical record. The examples file is an envelope with a records array; validate each item in that array separately against the root schema.

## Cross-record validation

The companion validator checks more than JSON shape:

- duplicate record IDs;
- typed references between participants, enterprises, cells, federations, projects, assets, accounts and ownership claims;
- unresolved event subjects and duplicate event idempotency keys;
- aggregate overlap of verified legal-title and beneficial-interest shares for the same asset and right class.

Run it with:

```bash
python -m pip install -r schemas/requirements-dev.txt
python schemas/validate_records.py schemas/examples/canonical_records.json
```

The ownership aggregation is intentionally limited to verified claims of the same right class. It does not sum different rights (for example, legal title and usufruct), decide whether a claim is legally valid, or infer rights from contribution scores. Time intervals are treated as half-open: validFrom is inclusive and validUntil is exclusive.

## Versioning policy

- Patch: editorial clarifications without changing accepted instances.
- Minor: backward-compatible optional fields or new enum values, with migration notes.
- Major: changed required fields, semantics, identifiers, numeric representation or breaking constraints.
- Never silently reinterpret an existing field.
- Preserve old schema versions and record the version used to validate each record.
- Changes to legal-right semantics require explicit review.

## Required application-level invariants before production

- Unique IDs within namespace and tenant.
- Referential integrity for every ID and reference field.
- Ownership-share aggregation rules by asset, right class and time interval; overlapping rights need an explicit rights model.
- Journal entries balance by currency and accounting entity.
- No negative inventory, impossible capacity use or unauthorized transfer.
- Contract parties, effective dates, jurisdiction and consent are independently verified.
- Event idempotency and reversal semantics are enforced transactionally.
- Consolidation eliminates internal claims and flows.
- Access controls protect personal and commercially sensitive data.
- Retention, correction, deletion and lawful-processing rules are defined per jurisdiction.

## Next implementation step

Add a validation package that loads records, validates each against Draft 2020-12, performs cross-record reference checks, and runs accounting and rights invariants. Keep schema validation separate from economic truth and evidence verification.
