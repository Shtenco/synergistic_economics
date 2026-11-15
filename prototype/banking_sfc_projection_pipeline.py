"""Orchestration boundary joining verified financial history to durable SFC snapshots."""
from __future__ import annotations

import hashlib
import json

from operating_financial_sfc_adapter import (
    OperatingFinancialSFCAdapter,
    OperatingFinancialSFCAdapterError,
)
from banking_sfc_projection_store import BankingSFCProjectionStore
from sfc_projection_kernel import SFCIdentity
from sfc_source_contracts import OpeningPosition, OpeningStockSnapshot


def _opening_digest(snapshots):
    ordered = sorted(snapshots, key=lambda item: item.period_index)
    payload = [{"period_index": item.period_index, "digest": item.digest} for item in ordered]
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def _verified_source_cursor(principal_id, history, checkpoint):
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


def build_opening_snapshots_from_register(
    register, *, principal_id, periods, instrument_registry, sector_registry,
):
    """Build complete bilateral opening snapshots from verified native financial stocks.

    The source register is read at one pinned global checkpoint. Existing reducers
    replay immutable openings and all prior native T-flows for deposits, reserves,
    loans and central-bank refinancing. A checkpoint change during extraction
    invalidates the whole build.
    """
    if getattr(register, "REGISTER_NAME", None) != "financial" or not register.verify():
        raise OperatingFinancialSFCAdapterError("verified native financial register is required")
    if not isinstance(periods, (tuple, list)) or not periods:
        raise OperatingFinancialSFCAdapterError("one or more opening periods are required")
    ordered_periods = sorted(periods)
    if (any(not isinstance(value, int) or isinstance(value, bool) or value < 1
            for value in ordered_periods)
            or len(set(ordered_periods)) != len(ordered_periods)
            or ordered_periods != list(range(ordered_periods[0], ordered_periods[-1] + 1))):
        raise OperatingFinancialSFCAdapterError(
            "opening periods must be unique, positive and contiguous"
        )
    history_reader = getattr(register, "history_with_checkpoint", None)
    checkpoint_reader = getattr(register, "source_checkpoint", None)
    if not callable(history_reader) or not callable(checkpoint_reader):
        raise OperatingFinancialSFCAdapterError(
            "financial register must expose atomic history/checkpoint and source checkpoint APIs"
        )
    history, checkpoint = history_reader("operating-financial", principal_id=principal_id)
    if not history:
        raise OperatingFinancialSFCAdapterError("financial register has no authorized source history")
    source_register_id, source_sequence, source_chain_hash = _verified_source_cursor(
        principal_id, history, checkpoint,
    )
    exporters = (
        "deposit_opening_positions",
        "reserve_opening_positions",
        "loan_opening_positions",
        "refinancing_opening_positions",
    )
    if any(not callable(getattr(register, name, None)) for name in exporters):
        raise OperatingFinancialSFCAdapterError(
            "financial register lacks one or more native opening-position exporters"
        )

    snapshots = []
    for period in ordered_periods:
        native_positions = []
        for method_name in exporters:
            native_positions.extend(getattr(register, method_name)(
                period_index=period, principal_id=principal_id,
            ))
        if not native_positions:
            raise OperatingFinancialSFCAdapterError(
                f"financial register has no supported opening positions for period {period}"
            )
        positions = []
        expected = []
        seen = set()
        for native in native_positions:
            raw = getattr(native, "identity", None)
            if raw is None or getattr(native, "period_index", None) != period:
                raise OperatingFinancialSFCAdapterError(
                    "native opening exporter returned a malformed or wrong-period position"
                )
            if (getattr(raw, "register_id", None) != "financial"
                    or getattr(raw, "measure", None) != "monetary"
                    or getattr(raw, "unit", None) != getattr(raw, "currency", None)
                    or getattr(raw, "valuation_basis", None) != "NOMINAL"):
                raise OperatingFinancialSFCAdapterError(
                    "native opening position has unsupported financial identity metadata"
                )
            instrument_id = raw.instrument_id
            try:
                terms = instrument_registry.resolve(instrument_id, period)
                holder_sector = sector_registry.resolve(raw.holder_id, period)
                issuer_sector = sector_registry.resolve(raw.issuer_id, period)
                identity = SFCIdentity(
                    instrument_id=instrument_id,
                    instrument_class=terms.instrument_class,
                    holder_entity_id=raw.holder_id,
                    holder_sector=holder_sector,
                    issuer_entity_id=raw.issuer_id,
                    issuer_sector=issuer_sector,
                    currency=raw.currency,
                    maturity=terms.maturity,
                    denomination=terms.denomination,
                    valuation_basis=terms.valuation_basis,
                )
            except (ValueError, KeyError, TypeError) as exc:
                raise OperatingFinancialSFCAdapterError(
                    f"opening position {instrument_id} cannot be resolved against pinned registries: {exc}"
                ) from exc
            if terms.currency != raw.currency or terms.valuation_basis != raw.valuation_basis:
                raise OperatingFinancialSFCAdapterError(
                    f"opening position metadata differs from pinned instrument terms for {instrument_id}"
                )
            if identity in seen:
                raise OperatingFinancialSFCAdapterError(
                    f"duplicate native opening identity for {instrument_id}"
                )
            seen.add(identity)
            expected.append(identity)
            evidence_ref = getattr(native, "evidence_ref", None)
            if not isinstance(evidence_ref, str) or not evidence_ref.strip():
                raise OperatingFinancialSFCAdapterError(
                    f"opening position {instrument_id} has no evidence provenance"
                )
            source_ref = (
                f"{source_register_id}@{source_sequence}:{source_chain_hash}:"
                f"{raw.position_id}"
            )
            positions.append(OpeningPosition(
                identity=identity,
                balance=str(native.amount),
                evidence_ref=evidence_ref,
                source_ref=source_ref,
            ))
        expected = tuple(sorted(expected, key=lambda item: (
            item.instrument_id, item.holder_entity_id, item.issuer_entity_id,
        )))
        positions = tuple(sorted(positions, key=lambda item: (
            item.identity.instrument_id, item.identity.holder_entity_id,
            item.identity.issuer_entity_id,
        )))
        snapshot = OpeningStockSnapshot(
            version=f"financial-opening-v1-period-{period}",
            period_index=period,
            instrument_registry_version=instrument_registry.version,
            instrument_registry_digest=instrument_registry.digest,
            sector_registry_version=sector_registry.version,
            sector_registry_digest=sector_registry.digest,
            expected_identities=expected,
            positions=positions,
            source_register_id=source_register_id,
            source_sequence=source_sequence,
            source_chain_hash=source_chain_hash,
        )
        try:
            snapshot.validate_against(instrument_registry, sector_registry)
        except ValueError as exc:
            raise OperatingFinancialSFCAdapterError(str(exc)) from exc
        snapshots.append(snapshot)

    if checkpoint_reader() != checkpoint:
        raise OperatingFinancialSFCAdapterError(
            "financial source changed while opening snapshots were being assembled; retry build"
        )
    return tuple(snapshots)


def _build_projection(register, *, principal_id, instrument_registry,
                      sector_registry, opening_snapshots, source_register_id):
    if getattr(register, "REGISTER_NAME", None) != "financial" or not register.verify():
        raise OperatingFinancialSFCAdapterError("verified native financial register is required")
    history_reader = getattr(register, "history_with_checkpoint", None)
    if not callable(history_reader):
        raise OperatingFinancialSFCAdapterError(
            "financial register must expose an atomic verified history/checkpoint read"
        )
    history, checkpoint = history_reader(
        "operating-financial", principal_id=principal_id
    )
    if not history:
        raise OperatingFinancialSFCAdapterError("financial register has no authorized source history")
    derived_id, sequence, chain_hash = _verified_source_cursor(
        principal_id, history, checkpoint,
    )
    if source_register_id is not None and source_register_id != derived_id:
        raise OperatingFinancialSFCAdapterError("caller-supplied source_register_id differs from durable register identity")
    for snapshot in opening_snapshots:
        if (
            getattr(snapshot, "source_register_id", None) != derived_id
            or getattr(snapshot, "source_sequence", None) != sequence
            or getattr(snapshot, "source_chain_hash", None) != chain_hash
        ):
            raise OperatingFinancialSFCAdapterError(
                "opening snapshot is not pinned to the exact verified financial source checkpoint"
            )
    projection = OperatingFinancialSFCAdapter.build(
        history, instrument_registry=instrument_registry,
        sector_registry=sector_registry, opening_snapshots=opening_snapshots,
    )
    return projection, derived_id, sequence, chain_hash


def _verify_checkpoint_ancestry(register, source_register_id, source_sequence,
                                store):
    """Prove the prior sealed source cursor is an ancestor of the current chain."""
    latest = store.latest_checkpoint(source_register_id)
    if latest is None:
        return
    previous_sequence = latest["applied_through_sequence"]
    if previous_sequence > source_sequence:
        return  # append/recover will reject the stale cursor itself
    ancestor_reader = getattr(register, "chain_hash_at", None)
    if not callable(ancestor_reader):
        raise OperatingFinancialSFCAdapterError(
            "financial register cannot prove ancestry of the persisted source checkpoint"
        )
    try:
        observed_hash = ancestor_reader(previous_sequence)
    except (ValueError, TypeError, KeyError) as exc:
        raise OperatingFinancialSFCAdapterError(
            "financial register cannot resolve the persisted source checkpoint ancestor"
        ) from exc
    if observed_hash != latest["source_chain_hash"]:
        raise OperatingFinancialSFCAdapterError(
            "financial source history diverges from the previously sealed checkpoint"
        )


def project_and_persist(register, *, principal_id, instrument_registry,
                        sector_registry, opening_snapshots, store,
                        source_register_id=None):
    """Verify durable source identity/cursor, rebuild projection and atomically persist its checkpoint."""
    projection, derived_id, sequence, chain_hash = _build_projection(
        register, principal_id=principal_id, instrument_registry=instrument_registry,
        sector_registry=sector_registry, opening_snapshots=opening_snapshots,
        source_register_id=source_register_id,
    )
    _verify_checkpoint_ancestry(register, derived_id, sequence, store)
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
    _verify_checkpoint_ancestry(register, derived_id, sequence, store)
    checkpoint = store.recover(
        projection, source_register_id=derived_id,
        source_sequence=sequence, source_chain_hash=chain_hash,
        instrument_registry_digest=instrument_registry.digest,
        sector_registry_digest=sector_registry.digest,
        opening_snapshot_digest=_opening_digest(opening_snapshots),
    )
    return projection, checkpoint


__all__ = [
    "build_opening_snapshots_from_register",
    "project_and_persist",
    "rebuild_and_verify",
]
