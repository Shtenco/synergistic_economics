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


def _verified_source_cursor(register, principal_id, history):
    checkpoint_method = getattr(register, "source_checkpoint", None)
    if not callable(checkpoint_method):
        raise OperatingFinancialSFCAdapterError(
            "financial register must expose a verified durable instance/checkpoint identity"
        )
    checkpoint = checkpoint_method()
    if not isinstance(checkpoint, dict):
        raise OperatingFinancialSFCAdapterError("financial source checkpoint metadata is invalid")
    instance_id = checkpoint.get("register_instance_id")
    sequence = checkpoint.get("event_count")
    chain_hash = checkpoint.get("tail_hash")
    if (not isinstance(instance_id, str) or len(instance_id) != 32
            or any(char not in "0123456789abcdef" for char in instance_id)
            or not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1
            or not isinstance(chain_hash, str) or len(chain_hash) != 64
            or any(char not in "0123456789abcdef" for char in chain_hash)):
        raise OperatingFinancialSFCAdapterError("financial source checkpoint identity/cursor is malformed")
    history_sequences = [row.get("commit_sequence") for row in history]
    if any(not isinstance(value, int) or isinstance(value, bool) or value < 1
           for value in history_sequences) or history_sequences != sorted(set(history_sequences)):
        raise OperatingFinancialSFCAdapterError("source history cursor is duplicated, invalid or unordered")
    if history_sequences[-1] > sequence:
        raise OperatingFinancialSFCAdapterError("financial history extends beyond verified source checkpoint")
    source_id = f"financial:{instance_id}:{principal_id}"
    return source_id, sequence, chain_hash


def _build_projection(register, *, principal_id, instrument_registry,
                      sector_registry, opening_snapshots, source_register_id):
    if getattr(register, "REGISTER_NAME", None) != "financial" or not register.verify():
        raise OperatingFinancialSFCAdapterError("verified native financial register is required")
    history = register.history("operating-financial", principal_id=principal_id)
    if not history:
        raise OperatingFinancialSFCAdapterError("financial register has no authorized source history")
    derived_id, sequence, chain_hash = _verified_source_cursor(register, principal_id, history)
    if source_register_id is not None and source_register_id != derived_id:
        raise OperatingFinancialSFCAdapterError("caller-supplied source_register_id differs from durable register identity")
    projection = OperatingFinancialSFCAdapter.build(
        history, instrument_registry=instrument_registry,
        sector_registry=sector_registry, opening_snapshots=opening_snapshots,
    )
    return projection, derived_id, sequence, chain_hash


def project_and_persist(register, *, principal_id, instrument_registry,
                        sector_registry, opening_snapshots, store,
                        source_register_id=None):
    """Verify durable source identity/cursor, rebuild projection and atomically persist its checkpoint."""
    projection, derived_id, sequence, chain_hash = _build_projection(
        register, principal_id=principal_id, instrument_registry=instrument_registry,
        sector_registry=sector_registry, opening_snapshots=opening_snapshots,
        source_register_id=source_register_id,
    )
    result = store.append(
        projection, source_register_id=derived_id,
        source_sequence=sequence, source_chain_hash=chain_hash,
        instrument_registry_digest=instrument_registry.digest,
        sector_registry_digest=sector_registry.digest,
        opening_snapshot_digest=_opening_digest(opening_snapshots),
    )
    return projection, result


def rebuild_and_verify(register, *, principal_id, instrument_registry,
                       sector_registry, opening_snapshots, store,
                       source_register_id=None):
    """Re-read source truth and exact source-chain tail before comparing persisted projection."""
    projection, derived_id, sequence, chain_hash = _build_projection(
        register, principal_id=principal_id, instrument_registry=instrument_registry,
        sector_registry=sector_registry, opening_snapshots=opening_snapshots,
        source_register_id=source_register_id,
    )
    checkpoint = store.recover(
        projection, source_register_id=derived_id,
        source_sequence=sequence, source_chain_hash=chain_hash,
        instrument_registry_digest=instrument_registry.digest,
        sector_registry_digest=sector_registry.digest,
        opening_snapshot_digest=_opening_digest(opening_snapshots),
    )
    return projection, checkpoint


__all__ = ["project_and_persist", "rebuild_and_verify"]
