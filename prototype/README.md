# SYNERGY Kernel Prototype

A small, dependency-free Python research prototype for selected invariants in Volume IV and Volume V.

## Requirements

- Python 3.10 or later
- Standard library only
- No network access or external packages required

## Run

From this directory:

```bash
python synergy_kernel.py
python -m unittest -v
```

## Included components

- debit/credit journal entries with strict balancing;
- duplicate journal-entry rejection;
- append-only event log with deterministic sequence and idempotency keys;
- deterministic event replay ordering;
- a capacity-constrained production function with labour, material, energy and demand bottlenecks;
- inventory checks and shipment bounds;
- proportional distribution with cent rounding and exact budget balance;
- a small demonstration of an inter-cell cash transfer.

## Prototype scope and limitations

This is a **research kernel**, not production financial software. It does not implement legal accounting standards, bank settlement, authentication, authorization, database durability, concurrency control, insolvency law, tax, multi-currency conversion, full event-sourced state reconstruction, privacy controls or a complete economic simulation.

The ledger is deliberately minimal: balances are debit-positive and the test model uses a closed set of accounts. A production implementation needs a typed chart of accounts, account normal-side semantics, immutable durable storage, transaction atomicity, concurrency safety, audit controls and jurisdiction-specific accounting review.

The event store records and orders events; it does not yet rebuild all domain state from events. The production function is a simple bottleneck model, not a calibrated sector model. The allocation function is a mathematical demonstration, not a universal fairness rule.

## Current invariant tests

The test suite checks:
1. a balanced inter-cell transfer preserves consolidated cash;
2. a transfer cannot overdraw available cash;
3. duplicate transfer idempotency keys cannot create a second journal posting;
2. an unbalanced journal is rejected before posting;
3. duplicate event idempotency keys are rejected;
4. production is bounded by the tightest input constraint;
5. shipments cannot exceed inventory;
6. allocation exactly exhausts the declared pool;
7. negative distribution pools are rejected.

Passing these tests demonstrates only these narrow software properties. It does not validate the full SYNERGY economic theory.
