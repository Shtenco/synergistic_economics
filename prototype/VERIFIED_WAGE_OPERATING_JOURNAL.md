# Verified wage operating journal (research prototype)

## Why this exists

The six-register coordinator can atomically commit one event from each of the physical, capital, labour, product, legal-rights and financial registers. Its current integration test deliberately records only a labour offer and labels it as having no stock-flow effect. A labour offer is not delivered work, a wage accrual or a payment.

The production `EntityJournal` remains the frozen GOLD-2A bank-credit contract. This experiment therefore does **not** add wage event types to GOLD-2A or weaken its validation. It introduces a separate, in-memory operating subledger for the first missing bridge: verified paid labour -> wage payable/receivable -> bank-deposit settlement.

## Flow

1. Read the engagement through `LabourRegister.state(...)` using an authorized principal.
2. Require the engagement to be `VERIFIED`, classified `paid`, and to carry a matching verification reference.
3. Match worker and labour period against an explicit wage contract containing employer, currency, rate, period index and evidence.
4. Accrue wages using delivered hours × hourly rate, rounded to the declared currency minor unit.
5. Record the wage payable and receivable as equal mirrored financial positions.
6. Pay all or part of the claim only if the employer's deposit balance is sufficient. Settlement extinguishes the wage claim and transfers deposit claims from employer to worker.

## Accounting identities

For a wage accrual of amount W:

- Employer: debit wage expense W; credit wage payable W.
- Worker: debit wage receivable W; credit wage income W.

The combined event has equal debits and credits. The wage receivable and wage payable are mirrored positions for the same claim.

For payment P, where 0 < P <= outstanding wage claim:

- Employer wage payable decreases by P; employer deposit asset decreases by P.
- Worker wage receivable decreases by P; worker deposit asset increases by P.
- The bank's deposit liability to the employer decreases by P and its liability to the worker increases by P.

The settlement event is balanced across all six postings. The stock-flow mapper emits mirrored holder/issuer movements for both the wage claim and the two deposit claims.

## Tests and acceptance criteria

The tests cover:
- authorized read of the labour aggregate;
- rejection of an unverified engagement and a forged delivery object;
- wage accrual only for a verified paid classification;
- exact double-entry balance;
- duplicate-delivery prevention;
- partial and full settlement;
- no payment above the outstanding claim or available employer deposits;
- two-period stock-flow reconciliation of wage claims and bank deposits.

## Explicit limitations

This is a bounded accounting kernel, not a completed production integration:
- The operating journal is in-memory; it is not yet append-only or restart-recoverable.
- Its verified-delivery token prevents accidental construction through the public API but is not a cryptographic boundary against arbitrary code executing inside the same Python process.
- The employer, bank, wage contract and sector membership are explicit inputs; they are not inferred from `activity_id`.
- The subledger is not yet a native financial-register participant and is not included in the six-register coordinator commit.
- It does not model tax, social contributions, benefits, arrears priority, insolvency resolution, price formation or household consumption.
- It must not be described as part of GOLD-2A or as proof that the full economy is stock-flow consistent.

The next integration step is a separately versioned operating-financial event contract and durable participant adapter, followed by one six-register transaction that commits a verified labour settlement and its financial postings without changing the frozen GOLD-2A journal.
