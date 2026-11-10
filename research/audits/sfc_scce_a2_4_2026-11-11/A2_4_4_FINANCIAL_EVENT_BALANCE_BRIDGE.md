# A2.4.4 — financial event and balance bridge

**Date:** 11 November 2026  
**Branch:** `audit/sfc-scce-a2-4-continuation-20261111`  
**Status:** event and posting contract; independent synthetic checks; no runtime integration.

## 1. Purpose

A2.4.4 links economic events to sectoral accounts and instrument-holder/issuer positions without treating financial operations as physical production. It extends the existing integrated framework and six-sector SFC control. It does not introduce a generic event handler that would erase differences between credit creation, transfer of existing deposits, payment, income, revaluation and write-off.

## 2. Three separate layers

1. **Economic event:** what legally/economically happened, when it became effective, who participated, and what evidence supports it.
2. **Journal postings:** the balanced debit/credit entries in each applicable ledger, with account, sector, instrument and valuation basis.
3. **State transition:** the resulting change in physical stocks, production, income, financial positions or rights.

One event may cause multiple postings, but a journal entry is not itself proof that the physical event occurred. A payment for equipment does not create the machine; the delivery/commissioning event changes the physical asset record. Conversely, production can occur before the invoice is paid.

## 3. Minimum immutable event envelope

Every event carries:

- unique `event_id`, `event_type`, `schema_version`, source and evidence;
- effective/event time, recognition/accrual time, settlement time and period;
- actor, counterparty, institutional sector, legal entity and jurisdiction;
- instrument/product/asset IDs and grade where applicable;
- quantity plus native unit for physical events;
- amount, currency, price basis and valuation date for monetary events;
- contractual/legal basis, status and dispute/correction lineage;
- links to predecessor/successor events and settlement batch;
- explicit flags for whether the event affects physical quantity, production, income, financial position, rights or only valuation.

The original event is immutable. Corrections are new linked events; duplicate `event_id` must be rejected idempotently.

## 4. Canonical event families and distinct posting rules

| Event | Financial effect | Physical/production effect |
|---|---|---|
| Bank loan origination | bank loan asset +; borrower loan liability +; matching deposit asset/liability + | none automatically |
| Non-bank loan from existing deposit | lender deposit − / loan asset +; borrower deposit + / loan liability + | none automatically |
| Deposit payment/transfer | payer deposit −; payee deposit + | only if linked delivery/service event exists |
| Principal repayment | borrower deposit and loan liability −; bank deposit liability and loan asset − | none |
| Interest accrual | interest receivable/payable and income/expense accrue under recognition rules | none |
| Interest settlement | deposit/payment positions settle the accrued interest | none |
| Default/arrears | status, risk and impairment/provision records change | no automatic physical change |
| Debt write-off/forgiveness | claim/liability reduced only under a documented legal/accounting event; counterpart treatment explicit | none |
| Asset acquisition/delivery | payment/payable and financing entries; purchaser GFCF if newly produced fixed asset | one asset delivered/commissioned; supplier output linked to same event |
| Routine repair | maintenance expense, supplier income and settlement | availability/condition changes; no automatic GFCF |
| Capital improvement | capitalized GFCF only if recognition criteria met | component/capacity/service state changes |
| CFC accrual | sector/asset-class capital account and net-stock value change | not a physical unit retirement |
| Revaluation | holding gain/loss and balance-sheet values change | physical quantity and current production unchanged |
| Other-volume change | separate balance-sheet adjustment (catastrophe, classification, scope, etc.) | only if physical event actually changes quantity/state |

## 5. Credit origination and existing-deposit transfer must remain distinct

### 5.1 Bank-created deposit

For a bank loan of 19 D.E.:

| Sector/account | Change |
|---|---:|
| Bank loan asset | +19 |
| Bank deposit liability | +19 |
| Borrower deposit asset | +19 |
| Borrower loan liability | +19 |

The bank's loan asset and deposit liability mirror the borrower's loan liability and deposit asset. System-wide deposits increase by 19 at origination. No goods, GVA or physical capital are created by the loan event itself.

### 5.2 Non-bank loan funded from an existing deposit

For a non-bank lender advancing 19 D.E. from its existing deposit:

| Sector/account | Change |
|---|---:|
| Lender deposit asset | −19 |
| Lender loan asset | +19 |
| Borrower deposit asset | +19 |
| Borrower loan liability | +19 |

System-wide deposits change by zero. The lender transfers an existing deposit claim; it does not create a new bank deposit. Both borrower and lender balance sheets change, but aggregate deposit money does not.

### 5.3 Payment is not another loan creation

When the borrower later pays a supplier, the deposit moves from payer to payee. Total system deposits remain unchanged. The physical delivery, service, inventory change or asset acquisition must be represented by its own linked event.

## 6. Accrual, settlement and bank equity

The six-sector control has:
- bank loan origination: +19 deposits;
- NFC interest expense/paid to bank: −6 deposits;
- bank deposit interest paid to households: +2 household deposits.

Thus:

[
Delta Deposits=19-6+2=15.
]

The bank's net interest margin is:

[
Delta Equity_{bank}=6-2=4.
]

The +6 interest income and −2 interest expense must not be collapsed into principal repayment or a new loan. Accrual and cash settlement may occur in different periods; the receivable/payable remains until settled, waived or written off.

## 7. Default, impairment and write-off

Default/arrears is a state/status, not necessarily extinguishment of the debt. Expected-credit-loss impairment/provision is a valuation/risk adjustment; it does not automatically cancel the contractual claim. Write-off removes or reduces the recognized claim under the applicable accounting/legal basis and requires a counterpart liability treatment or explicit explanation of the debtor's continuing legal obligation. Debt forgiveness may be treated differently from unilateral creditor write-off. These event types must remain separate and preserve dispute/recovery rights.

## 8. Stock-flow reconciliation

For every sector/instrument:

[
ClosingPosition=OpeningPosition+Transactions+Revaluations+OtherVolumeChanges.
]

Transaction postings must reconcile with the event journal. Revaluation cannot be posted as cash income or production. Other-volume changes cannot be used as an unexplained plug. For each instrument with a counterpart liability, holder-side assets and issuer-side liabilities must match under the declared valuation convention. Financial net lending must reconcile with capital-account net lending, with any statistical discrepancy shown explicitly.

## 9. Minimum cross-register tests

1. Bank loan creation increases deposits once and creates matching loan positions.
2. Non-bank loan transfer leaves system-wide deposits unchanged.
3. Payment transfers deposits and cannot create money.
4. Principal repayment reduces matching loan asset/liability and deposit positions.
5. Interest accrual and settlement are separate and do not alter principal.
6. Default does not silently write off the claim.
7. Write-off has a documented legal/accounting counterpart.
8. Revaluation changes value but not physical quantity or GDP.
9. Asset purchase links one delivery to purchaser GFCF and supplier output; payment timing may differ.
10. Repair payment does not create a new fixed asset absent a qualifying improvement.
11. Every journal balances; duplicate event IDs are rejected.
12. Sector capital and financial net lending reconcile; total net lending sums to zero across the complete sector boundary.
13. Every physical delivery has one product/asset flow ID and quantity/unit; money events cannot fabricate delivery.
14. Opening/closing financial positions reconcile with transactions, revaluation and other-volume changes.

**Current status:** event categories are specified. Component fixtures now cover balanced journal event families and the exact six-sector example's ten holder/issuer positions, stock-flow roll-forward, seven issuer-mirror groups and sector financial net lending. These remain synthetic controls: they do not yet provide a general event-sourced ledger, complete account taxonomy, legal instrument registry, or integrated runtime. A2.4.4 remains open.

## 6. Executable instrument stock-flow fixture

`audit_instrument_stock_flow.py` transcribes the opening and closing positions
in `FULL_SIX_SECTOR_SFC_NUMERICAL_CLOSURE.md` and checks, position by position:

`closing = opening + transactions + revaluation + other_volume_changes`.

It then checks holder/issuer mirrors by instrument and issuer, and derives
sector financial net lending from changes in financial assets less changes in
liabilities. The expected vector is H +7, NFC −19, CB +4, CBank 0, GOV −15,
ROW +23; the complete sum is zero. Negative controls reject a broken deposit
roll-forward and a missing issuer liability.

An independent Decimal arithmetic check of the ten positions, seven mirror
groups and six-sector net-lending vector returned PASS. This is a separate
arithmetic verification of the fixture's data, **not** execution evidence for
the committed script and not proof of a full general-ledger implementation.

