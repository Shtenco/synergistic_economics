# Verified wage operating journal (research prototype)

## Why this exists

The six-register coordinator can atomically commit one event from each of the physical, capital, labour, product, legal-rights and financial registers. Its current integration test deliberately records only a labour offer and labels it as having no stock-flow effect. A labour offer is not delivered work, a wage accrual or a payment.

The production `EntityJournal` remains the frozen GOLD-2A bank-credit contract. This experiment therefore does **not** add wage event types to GOLD-2A or weaken its validation. It introduces a separate, in-memory operating subledger for the first missing bridge: verified paid labour -> wage payable/receivable -> bank-deposit settlement.

## Flow

1. Read the engagement through `LabourRegister.state(...)` using an authorized principal.
2. Require the engagement to be `VERIFIED`, classified `paid`, and to carry a matching verification reference.
3. Match worker, employer (`activity_id`) and labour period against an explicit wage contract containing currency, rate, period index and evidence.
4. Re-read the labour aggregate immediately before accrual and require the exact verified version and delivery fields to remain unchanged. This is an optimistic freshness check, not an atomic cross-register lock.
5. Bind the accrual causation ID to the immutable delivery event ID and accrue wages using delivered hours × hourly rate, rounded to the declared currency minor unit.
6. Record the wage payable and receivable as equal mirrored financial positions.
7. Pay all or part of the claim only if the employer's deposit balance is sufficient, the amount is an exact multiple of the currency minor unit, the payment period does not precede accrual, and the causation ID points to the immediately preceding claim event. Settlement extinguishes the wage claim and transfers deposit claims from employer to worker.

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
- rejection of an unverified engagement, unpaid care work and a forged delivery object;
- rejection of a stale verified-delivery snapshot after a labour-hours correction;
- matching of the wage contract to the worker, employer and period in the labour register;
- rejection of fractional-minor-unit payments and broken causal/period ordering;
- wage accrual only for a verified paid classification;
- exact double-entry balance;
- duplicate-delivery prevention;
- partial and full settlement;
- no payment above the outstanding claim or available employer deposits;
- two-period stock-flow reconciliation of wage claims and bank deposits.

## Explicit limitations

This is a bounded accounting kernel, not a completed production integration:
- The operating journal is in-memory; it is not yet append-only or restart-recoverable.
- The labour version is rechecked immediately before accrual, but this check is not atomic with the journal write. A concurrent labour correction after the re-read remains possible until a durable coordinator transaction reserves the labour aggregate and commits the financial participant.
- Its verified-delivery token prevents accidental construction through the public API but is not a cryptographic boundary against arbitrary code executing inside the same Python process.
- The employer is matched against the labour register activity reference; the bank, wage contract and sector membership remain explicit inputs.
- The subledger is not yet a native financial-register participant and is not included in the six-register coordinator commit.
- It does not model tax, social contributions, benefits, arrears priority, insolvency resolution, price formation or household consumption.
- It must not be described as part of GOLD-2A or as proof that the full economy is stock-flow consistent.

The next integration step is a separately versioned operating-financial event contract and durable participant adapter, followed by one six-register transaction that commits a verified labour settlement and its financial postings without changing the frozen GOLD-2A journal.
