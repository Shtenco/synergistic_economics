# SFC-GOLD-2A — Debt, interest, impairment allowance, write-off and forgiveness

## Status and scope

Version 1.0.0 is a frozen synthetic control corpus. It is an accounting/replay test vector, not empirical evidence, legal advice, an IFRS/GAAP/SNA compliance opinion, or production certification.

**Included:** contractual loan principal; accrued interest receivable/payable; interest settlement; impairment loss allowance; creditor write-off; legally effective debt forgiveness; explicit period openings, closings and event checkpoints.

**Excluded by design:** foreign-exchange revaluation (GOLD-2B), collateral and guarantees (GOLD-2C), liquidity/central-bank reserve balances, taxes, fees, capital adequacy, securitization, syndication, insolvency waterfall and empirical calibration.

In this corpus, “reserve” means only the loan-loss impairment allowance (contra-asset). It must never be confused with cash, central-bank reserves, regulatory capital or collateral.

## Four-artifact proof package

1. `SFC_GOLD_2A_CORPUS.json` — immutable event and identity data, opening/closing balances by period, and after-event replay checkpoints.
2. `audit_sfc_gold_2a_oracle.py` — standard-library-only independent Decimal oracle. It must not import production modules, the SQLite store, journal adapters, projection kernels or recovery code.
3. `SFC_GOLD_2A_CONTRACT.md` — this semantic contract and acceptance rules.
4. `audit_financial_replay_recovery.py` — read-only recovery audit: load persisted event groups, verify durable envelopes and normalized mirrors, recover opening positions, replay events, inspect available snapshots and compare its result with the independent oracle.

## Canonical accounting semantics

### 1. Contractual principal

The contractual principal is the legally outstanding amount owed by the borrower. Its bilateral identity is fixed by the instrument: holder/creditor, issuer/debtor, instrument ID/class, currency, maturity, denomination and valuation basis.

For this control corpus:

`contractual_principal = recognized_gross_loan_asset + enforceable_written_off_claim_memo`

The memo amount is not a second recognized asset. It records a surviving legal claim that has been derecognized from the lender's recognized gross loan asset.

### 2. Interest

Interest accrual is a transaction (T), not a valuation change. It creates a lender receivable and borrower payable with the same instrument identity and amount. Payment reduces both accrued positions and the payer's deposit asset / bank's deposit liability.

`closing_interest_receivable = closing_interest_payable`

The corpus has no compounding, penalty interest, day-count convention or variable-rate reset. Those require a later versioned contract.

### 3. Impairment

Impairment recognizes a credit-loss allowance against the lender's loan asset. In this corpus, allowance recognition is classified as a valuation change (V). It does not reduce contractual principal, does not reduce the borrower's legal liability and does not itself constitute a write-off.

`net_loan_carrying = recognized_gross_loan_asset - impairment_allowance`

The allowance is a contra-asset, not a borrower liability, not a deposit, and not a pool of cash. It is not mirrored as a separate financial claim against the borrower.

### 4. Creditor write-off

A creditor write-off derecognizes some or all of the lender's recognized gross asset when the creditor no longer recognizes that amount on its balance sheet. It is classified as an other-volume change (O) in this frozen scenario.

A write-off is **not presumed to extinguish the legal obligation**. If the claim remains enforceable, the borrower liability remains outstanding and the derecognized amount is carried in a separate, non-recognized legal-claim memorandum register:

`contractual_principal = recognized_gross_loan_asset + enforceable_written_off_claim_memo`

The write-off consumes the allowance to the extent available. It must not silently reduce the debtor's legal liability or be mislabeled as forgiveness. If the legal claim has actually expired, been waived or otherwise extinguished, a separate legally evidenced event is required.

### 5. Legal forgiveness

Forgiveness is a legally effective extinguishment of the specified debt amount. It is not inferred from an impairment estimate or a creditor-only write-off. The event must identify the legal instrument/authority, effective time, amount, parties, scope (principal vs accrued interest) and evidence reference.

For the principal component in this corpus, forgiveness reduces both lender recognized gross claim and borrower contractual liability by the same amount. Any portion of a previously written-off memorandum claim forgiven later must reduce that memorandum balance, not an unrelated recognized balance. The frozen GOLD-2A scenario forgives 5 from the recognized principal component and leaves the 15 written-off claim enforceable.

## T/V/O classification

For each instrument/account and period:

`closing = opening + transactions(T) + revaluations(V) + other_volume_changes(O)`

Frozen classification:
- loan origination, principal repayment, interest accrual/payment and legal forgiveness: T;
- impairment allowance recognition: V;
- creditor write-off and corresponding reduction of the allowance used: O;
- FX changes: excluded and reserved for GOLD-2B.

A movement must be classified once only. No transaction may be duplicated as both T and V/O. Write-off does not create cash flow or net lending; impairment allowance recognition is not principal repayment.

## Identity and accounting invariants

- Decimal values are canonical finite base-10 strings. Floats, NaN, infinity and locale-formatted amounts are forbidden.
- Each journal event balances in the event currency.
- Each claim is keyed by full instrument identity and holder/issuer identity, not just account name or amount.
- Interest receivable/payable mirrors exactly.
- Deposit asset/liability mirrors exactly.
- Contractual principal equals recognized gross loan asset plus enforceable written-off memorandum claim.
- Net carrying amount equals recognized gross loan asset less impairment allowance.
- Allowance cannot be negative; write-off consumption cannot exceed available allowance in this corpus.
- Every period's opening equals the previous period's closing for each carried position.
- Every event has exactly one stable ID and one effective period; replay order is deterministic and duplicate delivery is rejected.
- Event checkpoints must match the independent oracle after every event, not only at final close.
- A globally balanced journal is necessary but insufficient: wrong holder, issuer, instrument, legal effect, event type or period must fail.

## Recovery and snapshot contract

The recovery audit is read-only. It must:
1. open the saved event-store database in read-only mode and pin one consistent read transaction;
2. verify SQLite structural/foreign-key integrity, schema version, canonical group payload hashes, predecessor hash chain, commit sequence and normalized event/posting mirrors;
3. load groups in verified commit order and reject duplicate event IDs or changed payloads;
4. verify the frozen opening snapshot. If a durable SFC opening table is absent, report that fact explicitly and use only the corpus's frozen opening snapshot for a diagnostic replay; do not claim persisted-opening recovery;
5. rebuild positions from the loaded event groups without mutating the database;
6. compare each rebuilt checkpoint and period close to the corpus and to the independent oracle;
7. compare materialized position snapshots only if a recognized snapshot schema exists. If no persisted position-snapshot table exists, report `NO_PERSISTED_POSITION_SNAPSHOTS`; a full replay is not evidence that snapshot recovery is implemented;
8. reject any mismatch, missing event, extra event, gap, tamper, unknown schema or ambiguous identity.

The current A2.4 SQLite store is a v4 event-group store. P1 opening activation blocks legacy appends after activation; P2 projection-aware atomic append (events + projection deltas + coverage + positions + cursor) is not yet implemented. Therefore a database containing both a P1-sealed opening registry and post-activation event groups cannot be produced through the current public append path. GOLD-2A recovery must expose this limitation rather than bypass it or claim end-to-end production replay.

## Frozen expected closing state

At the end of period 4:
- contractual principal: 75;
- recognized gross loan asset: 60;
- enforceable written-off claim memorandum: 15;
- impairment allowance: 5;
- net loan carrying amount: 55;
- accrued interest receivable/payable: 6 / 6;
- deposit asset/liability: 76 / 76.

The arithmetic is a synthetic control, not an estimate of real borrower credit quality.

## Out-of-scope sequencing

- GOLD-2A: principal, interest, impairment allowance, write-off and forgiveness.
- GOLD-2B: FX translation/revaluation, valuation source/time, functional currency, FX reserve and realized/unrealized FX distinctions.
- GOLD-2C: collateral, guarantees, haircuts, eligibility, encumbrance, priority, margin calls, substitution and enforcement/recovery proceeds.

Do not silently pull 2B or 2C semantics into 2A.
