"""Native operating-financial to SFC projection adapter.

The adapter is intentionally separate from GOLD-2A and from the generic
SFCProjectionStore. It consumes committed financial-register history plus
version-pinned instrument/sector registries and explicit opening snapshots.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
import hashlib
import json
from typing import Mapping, Sequence

from sfc_projection_kernel import (
    SFCIdentity,
    SFCProjectionError,
    canonical_decimal,
    financial_net_lending,
    replay_positions,
)
from sfc_source_contracts import (
    EffectiveDatedSectorRegistry,
    InstrumentTermsRegistry,
    OpeningStockSnapshot,
    SFCSourceContractError,
)


class OperatingFinancialSFCAdapterError(ValueError):
    """A financial source event cannot be projected without ambiguity."""


_OPENING_EVENT_TYPES = frozenset({
    "deposit.account_opened",
    "bank.reserve_account_opened",
})
_MOVEMENT_EVENT_TYPES = frozenset({
    "wage.event_group_committed",
    "bank.loan_originated",
    "bank.loan_principal_repaid",
    "bank.interbank_payment_settled",
    "central_bank.refinancing_advanced",
    "central_bank.refinancing_principal_repaid",
})


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise OperatingFinancialSFCAdapterError(f"{field} must be trimmed non-empty text")
    return value


def _sum_exact(values):
    values = tuple(values)
    if not values:
        return Decimal("0")
    with localcontext() as context:
        context.prec = 4096
        return sum(values, Decimal("0"))


def _source_event_groups(envelope, native_event_id, movements):
    event_type = envelope.get("event_type")
    payload = envelope.get("payload")
    if event_type == "wage.event_group_committed":
        source_events = payload.get("events") if isinstance(payload, Mapping) else None
        if not isinstance(source_events, list) or not source_events:
            raise OperatingFinancialSFCAdapterError("wage group has no source subevents")
        ids = [_text(item.get("event_id"), "wage subevent event_id")
               for item in source_events if isinstance(item, Mapping)]
        if len(ids) != len(source_events) or len(set(ids)) != len(ids):
            raise OperatingFinancialSFCAdapterError("wage subevent IDs must be unique")
    else:
        ids = [_text(envelope.get("idempotency_key") or native_event_id,
                     "financial idempotency key")]
    grouped = {source_id: [] for source_id in ids}
    for movement in movements:
        movement_id = _text(movement.get("movement_id"), "movement_id")
        matches = [source_id for source_id in ids
                   if movement_id.startswith(source_id + ":")]
        if not matches:
            raise OperatingFinancialSFCAdapterError(
                f"movement {movement_id} cannot be assigned to a source event"
            )
        source_id = max(matches, key=len)
        grouped[source_id].append(movement)
    if any(not items for items in grouped.values()):
        raise OperatingFinancialSFCAdapterError("source event has no stock-flow movements")
    return grouped


def _resolve_identity(raw, period, instruments, sectors):
    if not isinstance(raw, Mapping):
        raise OperatingFinancialSFCAdapterError("movement identity must be a mapping")
    if raw.get("register_id") != "financial" or raw.get("measure") != "monetary":
        raise OperatingFinancialSFCAdapterError("only native financial monetary positions are supported")
    _text(raw.get("position_id"), "identity.position_id")
    currency = _text(raw.get("currency"), "identity.currency")
    if raw.get("unit") != currency:
        raise OperatingFinancialSFCAdapterError("financial position unit must equal its currency")
    instrument_id = _text(raw.get("instrument_id"), "identity.instrument_id")
    terms = instruments.resolve(instrument_id, period)
    if (
        raw.get("valuation_basis") != terms.valuation_basis
        or currency != terms.currency
    ):
        raise OperatingFinancialSFCAdapterError(
            f"movement metadata differs from pinned instrument terms for {instrument_id}"
        )
    holder = _text(raw.get("holder_id"), "identity.holder_id")
    issuer = _text(raw.get("issuer_id"), "identity.issuer_id")
    try:
        return SFCIdentity(
            instrument_id=instrument_id,
            instrument_class=terms.instrument_class,
            holder_entity_id=holder,
            holder_sector=sectors.resolve(holder, period),
            issuer_entity_id=issuer,
            issuer_sector=sectors.resolve(issuer, period),
            currency=currency,
            maturity=terms.maturity,
            denomination=terms.denomination,
            valuation_basis=terms.valuation_basis,
        )
    except (SFCSourceContractError, SFCProjectionError) as exc:
        raise OperatingFinancialSFCAdapterError(str(exc)) from exc


def _validate_mirror_groups(source_id, rows):
    groups = {}
    for row in rows:
        group_id = _text(row.get("mirror_group_id"), "mirror_group_id")
        groups.setdefault(group_id, []).append(row)
    for group_id, pair in groups.items():
        if len(pair) != 2:
            raise OperatingFinancialSFCAdapterError(
                f"mirror group {source_id}/{group_id} must contain exactly two sides"
            )
        by_side = {item.get("mirror_side"): item for item in pair}
        if set(by_side) != {"asset_holder", "liability_issuer"}:
            raise OperatingFinancialSFCAdapterError("mirror sides must be asset_holder and liability_issuer")
        asset = by_side["asset_holder"]
        liability = by_side["liability_issuer"]
        if asset.get("mirror_policy") != "equal" or liability.get("mirror_policy") != "equal":
            raise OperatingFinancialSFCAdapterError("unsupported mirror policy")
        if canonical_decimal(asset.get("amount")) != canonical_decimal(liability.get("amount")):
            raise OperatingFinancialSFCAdapterError("mirrored transaction amounts differ")
        ai, li = asset["_resolved_identity"], liability["_resolved_identity"]
        if (
            ai.instrument_id != li.instrument_id
            or ai.instrument_class != li.instrument_class
            or ai.currency != li.currency
            or ai.maturity != li.maturity
            or ai.denomination != li.denomination
            or ai.valuation_basis != li.valuation_basis
            or ai.holder_entity_id != li.issuer_entity_id
            or ai.issuer_entity_id != li.holder_entity_id
            or asset["period_index"] != liability["period_index"]
        ):
            raise OperatingFinancialSFCAdapterError("mirrored financial positions are not reciprocal")


@dataclass(frozen=True)
class BankingSFCProjection:
    mapping_version: str
    source_digest: str
    events: tuple[dict, ...]
    projection: dict
    openings: dict
    roll_forward: dict
    sector_financial_net_lending: dict
    source_event_count: int
    mapped_source_event_count: int
    excluded_opening_event_count: int


class OperatingFinancialSFCAdapter:
    """Build and validate deterministic SFC projections from committed history."""

    @staticmethod
    def from_register(
        register,
        *,
        principal_id: str,
        instrument_registry: InstrumentTermsRegistry,
        sector_registry: EffectiveDatedSectorRegistry,
        opening_snapshots: Sequence[OpeningStockSnapshot],
    ) -> BankingSFCProjection:
        if getattr(register, "REGISTER_NAME", None) != "financial":
            raise OperatingFinancialSFCAdapterError("source must be the native financial register")
        if not register.verify():
            raise OperatingFinancialSFCAdapterError("financial source register hash-chain verification failed")
        history = register.history("operating-financial", principal_id=principal_id)
        return OperatingFinancialSFCAdapter.build(
            history,
            instrument_registry=instrument_registry,
            sector_registry=sector_registry,
            opening_snapshots=opening_snapshots,
        )

    @staticmethod
    def build(
        history_rows: Sequence[Mapping],
        *,
        instrument_registry: InstrumentTermsRegistry,
        sector_registry: EffectiveDatedSectorRegistry,
        opening_snapshots: Sequence[OpeningStockSnapshot],
    ) -> BankingSFCProjection:
        if not isinstance(history_rows, (tuple, list)) or not history_rows:
            raise OperatingFinancialSFCAdapterError("committed financial history is required")
        if not isinstance(instrument_registry, InstrumentTermsRegistry):
            raise OperatingFinancialSFCAdapterError("versioned instrument registry is required")
        if not isinstance(sector_registry, EffectiveDatedSectorRegistry):
            raise OperatingFinancialSFCAdapterError("effective-dated sector registry is required")
        if not isinstance(opening_snapshots, (tuple, list)) or not opening_snapshots:
            raise OperatingFinancialSFCAdapterError("explicit opening snapshots are required")

        if any(not isinstance(item, OpeningStockSnapshot) for item in opening_snapshots):
            raise OperatingFinancialSFCAdapterError("opening snapshot list contains an invalid value")
        snapshots = sorted(opening_snapshots, key=lambda item: item.period_index)
        periods = [item.period_index for item in snapshots]
        if len(set(periods)) != len(periods):
            raise OperatingFinancialSFCAdapterError("duplicate opening snapshot period")
        if periods != list(range(periods[0], periods[-1] + 1)):
            raise OperatingFinancialSFCAdapterError("opening snapshot period sequence contains a gap")

        openings = {}
        snapshot_digests = []
        for snapshot in snapshots:
            try:
                snapshot.validate_against(instrument_registry, sector_registry)
            except SFCSourceContractError as exc:
                raise OperatingFinancialSFCAdapterError(str(exc)) from exc
            snapshot_digests.append(snapshot.digest)
            for key, value in snapshot.as_projection_openings().items():
                if key in openings:
                    raise OperatingFinancialSFCAdapterError("duplicate opening position-period key")
                openings[key] = value

        ordered_rows = sorted(history_rows, key=lambda row: row.get("commit_sequence", 0))
        native_ids = set()
        movement_ids = set()
        source_events = []
        transaction_assets = {}
        transaction_liabilities = {}
        excluded_openings = 0
        mapped_count = 0

        for row in ordered_rows:
            if not isinstance(row, Mapping):
                raise OperatingFinancialSFCAdapterError("history row must be a mapping")
            native_id = _text(row.get("event_id"), "history.event_id")
            if native_id in native_ids:
                raise OperatingFinancialSFCAdapterError("duplicate native financial event ID")
            native_ids.add(native_id)
            envelope_json = row.get("native_envelope_json") or row.get("payload_json")
            try:
                envelope = json.loads(envelope_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise OperatingFinancialSFCAdapterError("immutable native envelope JSON is invalid") from exc
            if not isinstance(envelope, Mapping) or envelope.get("event_type") != row.get("event_type"):
                raise OperatingFinancialSFCAdapterError("history event type differs from immutable envelope")
            if "native_envelope_json" in row:
                envelope_digest = hashlib.sha256(envelope_json.encode("utf-8")).hexdigest()
                if envelope_digest != row.get("native_envelope_sha256"):
                    raise OperatingFinancialSFCAdapterError("immutable native envelope digest mismatch")
                if envelope.get("payload") != row.get("payload"):
                    raise OperatingFinancialSFCAdapterError("immutable envelope payload differs from committed history payload")
                for field in ("event_type", "effective_at", "recorded_at", "actor_id", "authority_ref", "idempotency_key"):
                    if envelope.get(field) != row.get(field):
                        raise OperatingFinancialSFCAdapterError(f"immutable envelope {field} differs from event-chain metadata")
            if envelope.get("idempotency_key") != row.get("idempotency_key", native_id):
                raise OperatingFinancialSFCAdapterError("history event ID differs from immutable idempotency key")
            if row.get("aggregate_id") not in (None, "operating-financial"):
                raise OperatingFinancialSFCAdapterError("history row belongs to a different aggregate")
            event_type = envelope.get("event_type")
            movements = envelope.get("stock_flow_movements")
            if event_type in _OPENING_EVENT_TYPES:
                if movements is not None or not envelope.get("no_stock_flow_effect"):
                    raise OperatingFinancialSFCAdapterError("opening event incorrectly carries transaction flow")
                excluded_openings += 1
                continue
            if event_type not in _MOVEMENT_EVENT_TYPES:
                raise OperatingFinancialSFCAdapterError(f"unsupported financial event type: {event_type}")
            if not isinstance(movements, list) or not movements:
                raise OperatingFinancialSFCAdapterError("transaction event has no canonical stock-flow movements")

            grouped = _source_event_groups(envelope, native_id, movements)
            for source_id, source_rows in grouped.items():
                prepared = []
                for movement in source_rows:
                    movement_id = _text(movement.get("movement_id"), "movement_id")
                    if movement_id in movement_ids:
                        raise OperatingFinancialSFCAdapterError("duplicate financial movement ID")
                    movement_ids.add(movement_id)
                    period = movement.get("period_index")
                    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
                        raise OperatingFinancialSFCAdapterError("movement period_index must be positive")
                    if period not in periods:
                        raise OperatingFinancialSFCAdapterError(
                            f"movement period {period} has no complete opening snapshot"
                        )
                    if movement.get("movement_class") != "T":
                        raise OperatingFinancialSFCAdapterError(
                            "banking adapter v1 accepts transaction movements T only"
                        )
                    amount = canonical_decimal(movement.get("amount"))
                    _text(movement.get("evidence_ref"), "movement.evidence_ref")
                    identity = _resolve_identity(
                        movement.get("identity"), period, instrument_registry, sector_registry
                    )
                    opening_key = (identity, period)
                    if opening_key not in openings:
                        raise OperatingFinancialSFCAdapterError(
                            f"movement {movement_id} has no explicit opening stock row"
                        )
                    if movement.get("mirror_policy") != "equal":
                        raise OperatingFinancialSFCAdapterError("unsupported mirror policy")
                    side = movement.get("mirror_side")
                    if side not in {"asset_holder", "liability_issuer"}:
                        raise OperatingFinancialSFCAdapterError("unknown mirror side")
                    prepared.append({
                        **movement,
                        "period_index": period,
                        "amount": amount,
                        "_resolved_identity": identity,
                    })
                    # The canonical financial identity is oriented to the balance-sheet
                    # entity for both asset and liability rows; mirror_side determines
                    # whether its amount enters assets or liabilities.
                    bucket_key = (period, identity.holder_sector, identity.currency)
                    bucket = transaction_assets if side == "asset_holder" else transaction_liabilities
                    bucket.setdefault(bucket_key, []).append(amount)

                _validate_mirror_groups(source_id, prepared)
                event_periods = {item["period_index"] for item in prepared}
                if len(event_periods) != 1:
                    raise OperatingFinancialSFCAdapterError(
                        f"source event {source_id} contains movements from multiple periods"
                    )
                period = next(iter(event_periods))
                projection_event_id = f"{native_id}::{source_id}"
                if any(item["event_id"] == projection_event_id for item in source_events):
                    raise OperatingFinancialSFCAdapterError("duplicate projected source event ID")
                deltas = []
                for index, item in enumerate(prepared):
                    identity = item["_resolved_identity"]
                    deltas.append({
                        "event_id": projection_event_id,
                        "delta_index": index,
                        "effective_period": period,
                        "identity": identity.__dict__,
                        "component": "T",
                        "amount": item["amount"],
                        "opening_balance": openings[(identity, period)],
                    })
                source_events.append({
                    "event_id": projection_event_id,
                    "effective_period": period,
                    "disposition": "mapped",
                    "deltas": deltas,
                })
                mapped_count += 1

        if not source_events:
            raise OperatingFinancialSFCAdapterError("financial history has no transaction events to project")

        mapping_seed = {
            "adapter": "operating-financial-sfc-v1",
            "instrument_registry_digest": instrument_registry.digest,
            "sector_registry_digest": sector_registry.digest,
            "opening_snapshot_digests": snapshot_digests,
        }
        mapping_version = "banking-sfc-v1:" + hashlib.sha256(
            json.dumps(mapping_seed, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        projection = {
            "mapping_version": mapping_version,
            "events": [{
                "event_id": item["event_id"],
                "disposition": item["disposition"],
                "deltas": item["deltas"],
            } for item in source_events],
        }
        try:
            roll_forward = replay_positions(
                [{"event_id": item["event_id"], "effective_period": item["effective_period"]}
                 for item in source_events],
                projection,
                openings,
                nonnegative_identities={
                    identity for identity, _period in openings
                    if instrument_registry.resolve(identity.instrument_id, _period).nonnegative_gross_position
                },
            )
        except SFCProjectionError as exc:
            raise OperatingFinancialSFCAdapterError(str(exc)) from exc

        # A non-zero position cannot silently disappear from a later complete
        # opening snapshot. Extinction/write-off must be represented by an
        # explicit transaction or other-volume-change contract, not omission.
        snapshot_period_set = set(periods)
        for (identity, period), roll in roll_forward.items():
            next_period = period + 1
            if next_period in snapshot_period_set and (identity, next_period) not in openings:
                if roll.closing != 0:
                    raise OperatingFinancialSFCAdapterError(
                        f"non-zero position {identity.instrument_id} disappears from period {next_period} opening"
                    )

        nl = {}
        keys = set(transaction_assets) | set(transaction_liabilities)
        for key in keys:
            assets = transaction_assets.get(key, [])
            liabilities = transaction_liabilities.get(key, [])
            nl[key] = financial_net_lending(assets, liabilities)

        # Every native financial transaction is represented by reciprocal
        # asset/liability positions. Financial net lending must therefore
        # conserve to zero independently for each period and currency; a
        # cross-period or cross-currency cancellation is not an acceptable
        # substitute for a closed transaction set.
        conservation = {}
        for (period, sector, currency), amount in nl.items():
            key = (period, currency)
            conservation.setdefault(key, []).append(amount)
        for (period, currency), amounts in conservation.items():
            if _sum_exact(amounts) != 0:
                raise OperatingFinancialSFCAdapterError(
                    f"financial net lending does not conserve for period {period}, currency {currency}"
                )

        source_digest = hashlib.sha256(json.dumps(
            [{
                "commit_sequence": row.get("commit_sequence"),
                "event_id": row.get("event_id"),
                "payload_sha256": row.get("payload_sha256"),
                "native_envelope_sha256": row.get("native_envelope_sha256"),
                "chain_hash": row.get("chain_hash"),
            } for row in ordered_rows],
            sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        ).encode("utf-8")).hexdigest()
        return BankingSFCProjection(
            mapping_version=mapping_version,
            source_digest=source_digest,
            events=tuple(source_events),
            projection=projection,
            openings=openings,
            roll_forward=roll_forward,
            sector_financial_net_lending=nl,
            source_event_count=len(ordered_rows),
            mapped_source_event_count=mapped_count,
            excluded_opening_event_count=excluded_openings,
        )


__all__ = [
    "OperatingFinancialSFCAdapterError",
    "BankingSFCProjection",
    "OperatingFinancialSFCAdapter",
]
