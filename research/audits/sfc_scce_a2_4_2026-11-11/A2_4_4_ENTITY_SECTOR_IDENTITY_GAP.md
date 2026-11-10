# A2.4.4 — entity identity versus institutional-sector identity

Date: 11 November 2026  
Scope: audit finding and acceptance contract for the synthetic financial-journal fixture.  
Status: **OPEN — interface defect identified; implementation and exact-head execution pending.**

## Finding

The current `audit_financial_journal.py` fixture uses `Line.sector` for two different concepts. Values such as `BORROWER`, `LENDER` and `SUPPLIER` identify individual counterparties, while `BANK` is an institution class/role. These values are not the six institutional sectors used by the SFC position model (`H`, `NFC`, `CB`, `CBank`, `GOV`, `ROW`).

The fixture's per-holder deposit check is useful: it detects a missing bank-liability posting even when the journal remains globally debit/credit balanced. But its current `sector` field cannot simultaneously provide:
1. stable identity of the legal/economic entity;
2. institutional-sector membership for aggregation;
3. the counterparty entity and that counterparty's sector;
4. instrument issuer identity distinct from issuer sector.

This is a semantic interface gap, not a failure of the current deposit arithmetic. The journal can be internally balanced while remaining impossible to aggregate correctly into sector accounts without an external, potentially ambiguous mapping.

## Canonical distinction required

The next journal contract must distinguish at least:

- `entity_id`: stable identity of the account-owning legal/economic unit;
- `institutional_sector`: controlled sector code for that entity at the event's effective time;
- `counterparty_entity_id` and `counterparty_sector`: the other party to the claim or transaction;
- `instrument_id` and `instrument_class`: specific claim identity and its type;
- `issuer_entity_id` and `issuer_sector`: issuer identity and sector;
- `currency`, `maturity`, `denomination`, `valuation_basis`;
- `event_id`, event type, effective/occurred/recognized/settled times and transaction-versus-valuation/other-volume classification.

The controlled sector vocabulary for the six-sector fixture is exactly `H`, `NFC`, `CB`, `CBank`, `GOV`, `ROW`. Entity IDs must never be substituted for sector codes. A sector code must never be used as a unique entity ID.

## Claim-side mirror rule

For a bilateral financial instrument, a holder-side asset and issuer-side liability must resolve to the same canonical claim key, including at minimum:

`(instrument_id, holder_entity_id, issuer_entity_id, currency, maturity, denomination, valuation_basis)`.

The holder and issuer sides must agree on opening stock, transactions (T), revaluation (V), other volume changes (O), and closing stock. Sector aggregation occurs only after entity-level records and claim mirrors have been validated.

A deposit liability posting must identify the issuer bank entity and the deposit holder entity. The matching deposit asset must identify the same holder and issuer. A sector-level match alone is insufficient: two different entities in the same sector must not be allowed to cancel each other's missing or misdirected claims.

## Required adversarial controls

The implementation is not acceptable until it rejects all of the following:

1. A journal line whose entity ID is blank but whose sector is populated.
2. An unknown institutional-sector code.
3. One entity assigned to conflicting sectors at the same effective time.
4. A deposit asset held by entity A paired with a liability naming entity B, even if A and B belong to the same sector and sector totals balance.
5. A correct holder but wrong issuer entity in the mirror.
6. Same nominal amount with wrong currency, maturity, denomination or valuation basis.
7. A duplicate event ID or duplicate claim-side posting that changes a stock twice.
8. A balanced journal whose entity-level postings cannot be reconciled to the sector-level SFC vector.
9. A sector reassignment that is applied retrospectively without an effective-time rule.

Positive controls must include bank-created deposits, transfer of existing deposits between non-bank holders, supplier settlement, principal repayment, interest accrual and settlement, impairment, creditor write-off, and—separately—legal forgiveness. Write-off must not silently extinguish the debtor's legal obligation.

## Required bridge to the six-sector SFC

After entity-level validation, calculate sector financial net lending from transaction flows only:

`NL_s = \sum_{i\in s} NAF_i^{T} - \sum_{i\in s} NIL_i^{T}`.

Revaluation and other-volume changes affect the stock bridge but do not enter transaction-based financial net lending. The resulting sector vector must reconcile to the six-sector control totals without treating ROW's external balance as resident-sector saving.

The current six-sector synthetic example remains the numerical oracle for sector aggregation:
- H: +7
- NFC: −19
- CB: +4
- CBank: 0
- GOV: −15
- ROW: +23
- aggregate: 0

These values are not to be reverse-engineered into invented underlying economic events. Where the source example does not specify event provenance, mark the mapping as unresolved rather than manufacturing a transaction story.

## Implementation sequence

1. Add an entity registry and controlled sector enum to the fixture layer.
2. Separate entity identity from sector membership in journal lines and counterparties.
3. Add bilateral claim identity and holder/issuer mirror checks at entity level.
4. Derive sector totals from entity records; do not store sector totals as a substitute for entity records.
5. Add the adversarial controls above and test sector aggregation against the six-sector oracle.
6. Record exact interpreter, command, stdout, exit code and file hashes in CI. Until that evidence exists, the fixture remains implemented/pending rather than PASS.

## Boundary

This finding does not authorize a unified economic engine, does not close A2.4.4, and does not establish full SFC-A…G closure. It specifies the minimum identity boundary needed before a journal fixture can credibly feed sector accounts.
