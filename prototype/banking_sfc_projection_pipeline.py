"""Orchestration boundary joining verified financial history to durable SFC snapshots."""
from __future__ import annotations

import hashlib
import json

from operating_financial_sfc_adapter import (
    OperatingFinancialSFCAdapter,
    OperatingFinancialSFCAdapterError,
)
from banking_sfc_projection_store import BankingSFCProjectionStore


def _opening_digest(snapshots):
    ordered = sorted(snapshots, key=lambda item: item.period_index)
    payload = [{"period_index": item.period_index, "digest": item.digest} for item in ordered]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def project_and_persist(register, *, principal_id, instrument_registry,
                        sector_registry, opening_snapshots, store,
                        source_register_id):
    """Verify source chain, rebuild projection, and atomically persist its checkpoint."""
    if getattr(register, "REGISTER_NAME", None) != "financial" or not register.verify():
        raise OperatingFinancialSFCAdapterError("verified native financial register is required")
    history = register.history("operating-financial", principal_id=principal_id)
    if not history:
        raise OperatingFinancialSFCAdapterError("financial register has no authorized source history")
    sequence_values = [row.get("commit_sequence") for row in history]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1
           for value in sequence_values):
        raise OperatingFinancialSFCAdapterError("source history lacks valid commit sequence metadata")
    if sequence_values != sorted(set(sequence_values)):
        raise OperatingFinancialSFCAdapterError("source history sequence is duplicated or unordered")
    projection = OperatingFinancialSFCAdapter.build(
        history, instrument_registry=instrument_registry,
        sector_registry=sector_registry, opening_snapshots=opening_snapshots,
    )
    result = store.append(
        projection, source_register_id=source_register_id,
        source_sequence=sequence_values[-1],
        instrument_registry_digest=instrument_registry.digest,
        sector_registry_digest=sector_registry.digest,
        opening_snapshot_digest=_opening_digest(opening_snapshots),
    )
    return projection, result


def rebuild_and_verify(register, *, principal_id, instrument_registry,
                       sector_registry, opening_snapshots, store,
                       source_register_id):
    """Re-read and verify source truth before comparing deterministic projection state."""
    if getattr(register, "REGISTER_NAME", None) != "financial" or not register.verify():
        raise OperatingFinancialSFCAdapterError("financial source hash-chain verification failed")
    history = register.history("operating-financial", principal_id=principal_id)
    if not history:
        raise OperatingFinancialSFCAdapterError("financial register has no authorized source history")
    sequence_values = [row.get("commit_sequence") for row in history]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1
           for value in sequence_values) or sequence_values != sorted(set(sequence_values)):
        raise OperatingFinancialSFCAdapterError("source history cursor is invalid")
    projection = OperatingFinancialSFCAdapter.build(
        history, instrument_registry=instrument_registry,
        sector_registry=sector_registry, opening_snapshots=opening_snapshots,
    )
    checkpoint = store.recover(
        projection, source_register_id=source_register_id,
        source_sequence=sequence_values[-1],
        instrument_registry_digest=instrument_registry.digest,
        sector_registry_digest=sector_registry.digest,
        opening_snapshot_digest=_opening_digest(opening_snapshots),
    )
    return projection, checkpoint


__all__ = ["project_and_persist", "rebuild_and_verify"]
