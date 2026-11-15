# Cross-register SFC/GOLD period reconciliation kernel

economic_stock_flow_reconciliation.py is a typed Decimal control kernel for multi-period position reconciliation. It requires one immutable opening and closing snapshot per full position identity and period, and typed movements classified exactly once as transactions (T), revaluations (V) or other volume changes (O).

For every full identity and period it enforces:

closing(t) = opening(t) + T(t) + V(t) + O(t)

and for every adjacent period:

opening(t+1) = closing(t).

The identity includes register, position, measure, native unit, currency, valuation basis, holder, issuer and instrument. This prevents summing kilograms with tonnes, physical units with monetary values, or different currencies/valuation bases. Duplicate event IDs, missing periods, unbalanced positions and mirror mismatches fail closed.

Mirror groups can assert equal holder-asset/issuer-liability changes or opposite sender-outflow/receiver-inflow changes. A correction is a new movement referencing an earlier immutable event; it does not overwrite the source record.

## Common event group input

The coordinator exposes committed_event_group(txid) only after the six-participant visibility barrier. It returns one common_event_id and six participant envelopes. Each participant must declare either a non-empty stock_flow_movements list or an explicit no_stock_flow_effect reason. Silent omission is rejected. Movement IDs remain native event references; common_event_id binds movements to the coordinator transaction.

## Integration status

The kernel and adversarial tests are implemented. The coordinator event-group read model is implemented and tested with two native domain stores plus four protocol-conformance participants. The physical, capital, product and financial stores still need native adapters and actual schema mappers into this movement contract. Therefore this is not yet live six-register SFC/GOLD reconciliation. No synthetic or manually supplied movement may be presented as a production ledger posting.

##  Current banking-register integration boundary

The durable `OperatingFinancialRegister` now records and validates bank-created deposit credit, principal repayment, reserve-account openings, interbank reserve settlement and principal-only central-bank refinancing. Its event mappers produce mirrored holder/issuer movements, and the principal-only refinancing lifecycle is covered by dedicated tests.

These capabilities are **not yet wired into** the six-register `CrossRegisterCoordinator` or the persistent `SFCProjectionStore`. In particular, the financial register's durable history is not yet consumed by a production projection adapter that advances bank loan assets, borrower loan liabilities, customer deposits, bank reserve assets, central-bank reserve liabilities and central-bank refinancing claims inside one authoritative multi-period sector projection.

The six-register wage coordinator is a domain-specific workflow; it must not be reused for banking events by fabricating labour, physical, product, capital or legal events. The next integration must define explicit participant semantics for financial-only events, preserve the coordinator's visibility barrier, and make projection append/recovery idempotent against the source event IDs. Until that adapter exists, bank-register stock-flow tests are local accounting controls, not proof of a live six-sector SFC close.

