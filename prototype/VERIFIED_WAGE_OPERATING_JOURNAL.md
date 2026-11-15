# Verified wage operating journal (research prototype)

## Why this exists

The research branch now contains a six-register wage transaction path. It commits a measured physical labour-service flow, a capital no-effect period marker, a verified labour settlement, a non-stockable product specification, a legal wage claim and the durable operating-financial event group through the existing coordinator. The integration test verifies the committed event group, all six native receipts, restart visibility and stock-flow reconciliation.

The production `EntityJournal` remains the frozen GOLD-2A bank-credit contract. This experiment therefore does **not** add wage event types to GOLD-2A or weaken its validation. It introduces a separately versioned operating wage subledger and a durable native financial register for the first missing bridge: verified paid labour -> wage payable/receivable -> bank-deposit settlement. The durable register is separate from GOLD-2A and uses the existing native event-envelope and append-only register substrate. The global `operating-financial` stream now stores both wage claims and durable deposit accounts, so a wage payment can atomically reduce the employer deposit and increase the worker deposit.

## Flow

1. Read the engagement through `LabourRegister.state(...)` using an authorized principal.
2. Require the engagement to be `VERIFIED`, classified `paid`, and to carry a matching verification reference.
3. Match worker, employer (`activity_id`) and labour period against an explicit wage contract containing currency, rate, period index and evidence.
4. Re-read the labour aggregate immediately before accrual and require the exact verified version and delivery fields to remain unchanged. Standalone in-memory accrual is not atomic; in the six-register path, the labour participant's prepare step checks the expected revision and reserves the engagement stream until commit or abort.
5. Bind the accrual causation ID to the immutable delivery event ID and accrue wages using delivered hours × hourly rate, rounded to the declared currency minor unit.
6. Record the wage payable and receivable as equal mirrored financial positions.
7. Serialize accrual/payment events with their delivery, verification, contract and bank-evidence references; preserve the labour aggregate version and currency minor unit.
8. Submit all six native operations to `OperatingWageCoordinator`. It cross-checks the live labour state, physical service quantity, product specification, legal claim and financial postings before the coordinator begins prepare/commit.
9. For a fully paid claim, the legal-rights register records `right.created_and_extinguished` with the final payment event and evidence reference in the same six-register transaction. For an unpaid or partially paid claim, the legal right remains active.
10. Deposit accounts are opened as durable, versioned financial events with owner, bank, currency, account reference, opening balance, minor unit and opening evidence.
11. The financial register checks canonical postings, causal order, claim balance, currency precision, sector mapping, matching bank/currency/minor-unit account identities and sufficient employer deposit balance. It debits the employer account and credits the worker account in the same append-only event as the wage claim settlement; the whole stream replays after restart.
12. The financial register exports opening deposit positions from its durable account-opening records to the SFC reconciliation kernel.
13. The physical labour service is recorded as a non-stockable period flow. It is not misrepresented as an opening/closing inventory of hours; only financial instrument positions enter the current T/V/O stock-flow reconciliation.
14. The in-memory journal prechecks employer deposit availability for early feedback; the durable financial register independently rechecks the authoritative persisted balance before commit. It records the supplied bank evidence reference but does not independently query or authenticate the external bank settlement.

## Accounting identities

For a wage accrual of amount W:

- Employer: debit wage expense W; credit wage payable W.
- Worker: debit wage receivable W; credit wage income W.

The combined event has equal debits and credits. The wage receivable and wage payable are mirrored positions for the same claim.

For payment P, where 0 < P <= outstanding wage claim:

- Employer wage payable decreases by P; employer deposit asset decreases by P.
- Worker wage receivable decreases by P; worker deposit asset increases by P.
- The bank's deposit liability to the employer decreases by P and its liability to the worker increases by P.

The settlement event is balanced across all six postings. The stock-flow mapper emits mirrored holder/issuer movements for both the wage claim and the two deposit claims. The same canonical movement list is embedded in the native financial event group and consumed by `movements_from_event_groups`.

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
- two-period stock-flow reconciliation of wage claims and bank deposits;
- durable append-only financial event commit, receipt replay and restart recovery;
- durable opening of employer/worker deposit accounts, atomic balance movement on wage settlement and overdraft rejection even when the in-memory precheck has a larger balance;
- SFC opening positions derived from the durable deposit-account opening records;
- rejection of a payment without a prior accrual, altered movement metadata, altered postings and unauthorized actors;
- separate accrual and later payment commits against consecutive financial aggregate revisions;
- one six-register transaction that commits physical, capital, labour, product, legal-rights and financial participant events;
- a partial-payment six-register transaction that leaves the legal wage claim active and the unpaid balance outstanding;
- rejection of unsupported institutional-sector codes, missing bank-sector mapping, colliding worker/employer/bank identities and claim IDs not bound to the verified engagement/delivery;
- retention of evidence references for every payment in the legal claim record;
- legal extinguishment when the full wage claim is paid in that transaction;
- rejection of a stale labour revision changed after coordinator submission, with all prepared participants aborted and no wage claim committed;
- exclusion of non-stockable labour hours from physical stock positions.

## Explicit limitations

This is a bounded accounting kernel, not a completed production integration:
- `OperatingWageJournal` remains an in-memory event constructor and cash precheck. The separate `OperatingFinancialRegister` is append-only and restart-recoverable for wage claims and settlement postings.
- The standalone in-memory journal's freshness read is not itself atomic. The six-register path closes the race at prepare: a correction after submit but before labour prepare causes a revision conflict and aborts the prepared participants; after successful labour prepare, the engagement stream is reserved until commit or abort.
- Its verified-delivery token prevents accidental construction through the public API but is not a cryptographic boundary against arbitrary code executing inside the same Python process.
- The employer is matched against the labour register activity reference; the bank, wage contract and sector membership remain explicit inputs.
- The six-register path is a research prototype with one tested paid-labour transaction shape. It does not yet provide a general operating-accounting integration for all wages, transfers, taxes, benefits or consumption. Later partial-payment transactions need a corresponding legal-rights and six-register settlement workflow; the financial subledger alone can already replay sequential partial payments.
- The durable financial register now enforces its own append-only deposit-account balances and prevents overdraw on its internal ledger. However, account-opening balances and payment evidence are supplied by authorized actors; the prototype does not independently authenticate bank statements, query a live bank, or prove that an external transfer actually settled.
- It does not model tax, social contributions, benefits, arrears priority, insolvency resolution, price formation or household consumption.
- It must not be described as part of GOLD-2A or as proof that the full economy is stock-flow consistent.

The next integration step is an external bank-evidence verifier (for example, a signed statement/transfer feed) and a coordinated workflow for later partial settlements and household purchases/firm receipts. The frozen GOLD-2A journal remains unchanged.
