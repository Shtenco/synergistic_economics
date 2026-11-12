"""Durable SQLite adapter for the canonical P6.1 LotInventory domain rules.

All lots and reservations live under one inventory-book aggregate root. This
makes commands that affect several lot/reservation records atomic without
claiming the not-yet-implemented P6.3a multi-aggregate protocol.
"""
from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import datetime
from decimal import Decimal
import json

from real_economy_protocol import (
    Lot, Reservation, LotInventory, CommandReceipt, RealEconomyError,
)
from sqlite_event_repository import (
    SQLiteEventRepository, SQLiteRepositoryError, DurableReceipt,
)
from real_economy_event_bridge import EventBridgeConflict


AGGREGATE_TYPE = "inventory_book"
AGGREGATE_ID = "inventory-book"
STATE_SCHEMA = "synergy.inventory-book.v1"


class SQLiteLotInventoryError(RuntimeError):
    """Durable inventory projection or adapter contract failure."""


def _json_value(value):
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise SQLiteLotInventoryError("non-finite inventory quantity")
        return format(value, "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise SQLiteLotInventoryError("inventory datetime must be timezone-aware")
        return value.isoformat()
    if is_dataclass(value):
        return {field.name: _json_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (set, frozenset)):
        return sorted(_json_value(item) for item in value)
    if isinstance(value, (tuple, list)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) for key in value):
            raise SQLiteLotInventoryError("inventory mapping keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (str, int, bool)):
        return value
    raise SQLiteLotInventoryError(f"unsupported inventory serialization type: {type(value).__name__}")


def _initial_state():
    return {"schema": STATE_SCHEMA, "lots": [], "reservations": []}


def _inventory_from_state(state):
    if not isinstance(state, dict) or state.get("schema") != STATE_SCHEMA:
        raise SQLiteLotInventoryError("unsupported inventory aggregate state schema")
    if set(state) != {"schema", "lots", "reservations"}:
        raise SQLiteLotInventoryError("inventory aggregate state has unknown or missing fields")
    if not isinstance(state["lots"], list) or not isinstance(state["reservations"], list):
        raise SQLiteLotInventoryError("inventory lots and reservations must be arrays")
    inventory = LotInventory()
    lots = {}
    for row in state["lots"]:
        if not isinstance(row, dict):
            raise SQLiteLotInventoryError("malformed persisted lot")
        lot = Lot(
            lot_id=row["lot_id"], product_id=row["product_id"],
            owner_id=row["owner_id"], custodian_id=row["custodian_id"],
            location_id=row["location_id"], quantity=Decimal(row["quantity"]),
            unit=row["unit"], quality_status=row["quality_status"],
            reserved_quantity=Decimal(row["reserved_quantity"]),
            version=row["version"], authorized_actors=frozenset(row["authorized_actors"]),
            source_lot_id=row["source_lot_id"],
        )
        if lot.lot_id in lots:
            raise SQLiteLotInventoryError("duplicate lot in persisted projection")
        lots[lot.lot_id] = lot
    reservations = {}
    for row in state["reservations"]:
        if not isinstance(row, dict):
            raise SQLiteLotInventoryError("malformed persisted reservation")
        expires_at = datetime.fromisoformat(row["expires_at"])
        reservation = Reservation(
            reservation_id=row["reservation_id"], lot_id=row["lot_id"],
            quantity=Decimal(row["quantity"]),
            remaining_quantity=Decimal(row["remaining_quantity"]),
            actor_id=row["actor_id"], counterparty_id=row["counterparty_id"],
            purpose=row["purpose"], expires_at=expires_at,
            status=row["status"], version=row["version"],
            idempotency_key=row["idempotency_key"],
            request_fingerprint=row["request_fingerprint"],
        )
        if reservation.reservation_id in reservations:
            raise SQLiteLotInventoryError("duplicate reservation in persisted projection")
        reservations[reservation.reservation_id] = reservation
    inventory._lots = lots
    inventory._reservations = reservations
    inventory.assert_invariants()
    return inventory


def _state_from_inventory(inventory):
    lots = [_json_value(inventory._lots[key]) for key in sorted(inventory._lots)]
    reservations = [
        _json_value(inventory._reservations[key])
        for key in sorted(inventory._reservations)
    ]
    return {"schema": STATE_SCHEMA, "lots": lots, "reservations": reservations}


def _projection_delta(before, after):
    """Canonical full-record upserts needed to rebuild the inventory projection."""
    old_lots = {row["lot_id"]: row for row in before["lots"]}
    new_lots = {row["lot_id"]: row for row in after["lots"]}
    old_reservations = {row["reservation_id"]: row for row in before["reservations"]}
    new_reservations = {row["reservation_id"]: row for row in after["reservations"]}
    return {
        "lots_upsert": [new_lots[key] for key in sorted(new_lots)
                        if old_lots.get(key) != new_lots[key]],
        "lots_remove": sorted(set(old_lots) - set(new_lots)),
        "reservations_upsert": [
            new_reservations[key] for key in sorted(new_reservations)
            if old_reservations.get(key) != new_reservations[key]
        ],
        "reservations_remove": sorted(set(old_reservations) - set(new_reservations)),
    }


def _replay_inventory_projection(events):
    """Rebuild the inventory root from command-scoped event projection deltas."""
    state = _initial_state()
    commands = {}
    for envelope in events:
        if envelope.get("aggregate_type") != AGGREGATE_TYPE or envelope.get("aggregate_id") != AGGREGATE_ID:
            raise SQLiteLotInventoryError("inventory replay encountered a foreign aggregate event")
        commands.setdefault(envelope.get("command_id"), []).append(envelope)
    for command_id, group in commands.items():
        deltas = [
            (index, envelope["payload"]["inventory_projection_delta"])
            for index, envelope in enumerate(group)
            if isinstance(envelope.get("payload"), dict)
            and "inventory_projection_delta" in envelope["payload"]
        ]
        if len(deltas) != 1 or deltas[0][0] != len(group) - 1:
            raise SQLiteLotInventoryError(
                f"command {command_id} must carry exactly one final inventory projection delta"
            )
        delta = deltas[0][1]
        required = {
            "lots_upsert", "lots_remove",
            "reservations_upsert", "reservations_remove",
        }
        if not isinstance(delta, dict) or set(delta) != required:
            raise SQLiteLotInventoryError("malformed inventory projection delta")
        lots = {row["lot_id"]: row for row in state["lots"]}
        reservations = {row["reservation_id"]: row for row in state["reservations"]}
        for lot_id in delta["lots_remove"]:
            if lot_id not in lots:
                raise SQLiteLotInventoryError("replay removes an unknown lot")
            del lots[lot_id]
        for row in delta["lots_upsert"]:
            if not isinstance(row, dict) or not isinstance(row.get("lot_id"), str):
                raise SQLiteLotInventoryError("malformed lot projection upsert")
            lots[row["lot_id"]] = row
        for reservation_id in delta["reservations_remove"]:
            if reservation_id not in reservations:
                raise SQLiteLotInventoryError("replay removes an unknown reservation")
            del reservations[reservation_id]
        for row in delta["reservations_upsert"]:
            if not isinstance(row, dict) or not isinstance(row.get("reservation_id"), str):
                raise SQLiteLotInventoryError("malformed reservation projection upsert")
            reservations[row["reservation_id"]] = row
        state = {
            "schema": STATE_SCHEMA,
            "lots": [lots[key] for key in sorted(lots)],
            "reservations": [reservations[key] for key in sorted(reservations)],
        }
        # Validate the economic invariants after every committed command, not
        # merely at the final head.
        _inventory_from_state(state)
    return state


def _request_value(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (set, frozenset)):
        return sorted(_request_value(item) for item in value)
    if isinstance(value, (tuple, list)):
        return [_request_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _request_value(item) for key, item in value.items()}
    return value


class SQLiteLotInventory:
    """Durable facade that executes the actual LotInventory transitions.

    The entire inventory is one aggregate root. This is intentionally
    single-host SQLite, single-writer serialized, and conservative: it trades
    concurrency for atomicity across source lots, moved lots and reservations.
    """

    def __init__(self, database_path, *, timeout=10.0):
        self.repository = SQLiteEventRepository(str(database_path), timeout=timeout)
        try:
            self.repository.load_aggregate(AGGREGATE_TYPE, AGGREGATE_ID)
        except SQLiteRepositoryError as exc:
            if str(exc) != "aggregate not found":
                raise
            try:
                self.repository.register_aggregate(
                    AGGREGATE_TYPE, AGGREGATE_ID, _initial_state()
                )
            except Exception:
                # Another process may have initialized the same book after our
                # read. Accept only if the canonical aggregate now exists.
                self.repository.load_aggregate(AGGREGATE_TYPE, AGGREGATE_ID)

    def _execute(self, *, operation, command_id, idempotency_key, request,
                 actor_id, authority_ref, correlation_id, occurred_at,
                 recorded_at, handler, evidence_refs=(), causation_id=None,
                 fail_at=None):
        original_version = self.repository.command_expected_version(idempotency_key)
        if original_version is None:
            version, _ = self.repository.load_aggregate(AGGREGATE_TYPE, AGGREGATE_ID)
        else:
            version = original_version
        normalized_request = _request_value({"operation": operation, **request})

        def transition(old_state):
            inventory = _inventory_from_state(old_state)
            receipt = handler(inventory)
            if not isinstance(receipt, CommandReceipt):
                raise SQLiteLotInventoryError("domain command did not return CommandReceipt")
            inventory.assert_invariants()
            new_state = _state_from_inventory(inventory)
            raw_events = []
            for raw in receipt.events:
                event = dict(raw)
                # One root version covers every record touched by this command.
                event["aggregate_id"] = AGGREGATE_ID
                event["aggregate_version"] = version + 1
                raw_events.append(event)
            if not raw_events:
                raise SQLiteLotInventoryError("inventory command must emit canonical domain events")
            # The last event carries the complete command-level projection
            # delta. The event log can now independently rebuild all records.
            raw_events[-1]["payload"] = dict(raw_events[-1]["payload"])
            raw_events[-1]["payload"]["inventory_projection_delta"] = _projection_delta(
                old_state, new_state
            )
            return new_state, _json_value(receipt.result), raw_events

        arguments = dict(
            command_id=command_id, idempotency_key=idempotency_key,
            request=normalized_request, aggregate_type=AGGREGATE_TYPE,
            aggregate_id=AGGREGATE_ID, expected_version=version,
            actor_id=actor_id, authority_ref=authority_ref,
            correlation_id=correlation_id, occurred_at=occurred_at,
            recorded_at=recorded_at, transition=transition,
            evidence_refs=evidence_refs, causation_id=causation_id,
            fail_at=fail_at,
        )
        try:
            return self.repository.execute(**arguments)
        except EventBridgeConflict:
            # Close the race where an identical command commits after our
            # receipt lookup but before we load the aggregate version.
            original_version = self.repository.command_expected_version(idempotency_key)
            if original_version is None or original_version == version:
                raise
            arguments["expected_version"] = original_version
            return self.repository.execute(**arguments)

    def register_lot(self, *, lot_id, product_id, owner_id, custodian_id,
                     location_id, quantity, unit, authorized_actors=(),
                     command_id, idempotency_key, actor_id, authority_ref,
                     correlation_id, occurred_at, recorded_at, evidence_refs=(),
                     causation_id=None, fail_at=None):
        request = {
            "lot_id": lot_id, "product_id": product_id, "owner_id": owner_id,
            "custodian_id": custodian_id, "location_id": location_id,
            "quantity": quantity, "unit": unit,
            "authorized_actors": tuple(authorized_actors),
        }
        return self._execute(
            operation="register_lot", command_id=command_id,
            idempotency_key=idempotency_key, request=request,
            actor_id=actor_id, authority_ref=authority_ref,
            correlation_id=correlation_id, occurred_at=occurred_at,
            recorded_at=recorded_at, evidence_refs=evidence_refs,
            causation_id=causation_id, fail_at=fail_at,
            handler=lambda inv: inv.register_lot(
                lot_id, product_id, owner_id, custodian_id, location_id,
                quantity, unit, authorized_actors,
            ),
        )

    def reserve(self, *, lot_id, reservation_id, quantity, actor_id,
                counterparty_id, purpose, expires_at, idempotency_key,
                expected_lot_version, now, command_id, authority_ref,
                correlation_id, occurred_at, recorded_at, evidence_refs=(),
                causation_id=None, fail_at=None):
        request = {
            "lot_id": lot_id, "reservation_id": reservation_id,
            "quantity": quantity, "actor_id": actor_id,
            "counterparty_id": counterparty_id, "purpose": purpose,
            "expires_at": expires_at, "expected_lot_version": expected_lot_version,
            "now": now,
        }
        return self._execute(
            operation="reserve", command_id=command_id,
            idempotency_key=idempotency_key, request=request,
            actor_id=actor_id, authority_ref=authority_ref,
            correlation_id=correlation_id, occurred_at=occurred_at,
            recorded_at=recorded_at, evidence_refs=evidence_refs,
            causation_id=causation_id, fail_at=fail_at,
            handler=lambda inv: inv.reserve(
                lot_id, reservation_id, quantity, actor_id, counterparty_id,
                purpose, expires_at, idempotency_key, expected_lot_version, now,
            ),
        )

    def commit(self, *, reservation_id, actor_id, authorization_ref,
               idempotency_key, expected_reservation_version, now,
               command_id, authority_ref, correlation_id, occurred_at,
               recorded_at, evidence_refs=(), causation_id=None, fail_at=None):
        request = {
            "reservation_id": reservation_id, "actor_id": actor_id,
            "authorization_ref": authorization_ref,
            "expected_reservation_version": expected_reservation_version, "now": now,
        }
        return self._execute(
            operation="commit_reservation", command_id=command_id,
            idempotency_key=idempotency_key, request=request,
            actor_id=actor_id, authority_ref=authority_ref,
            correlation_id=correlation_id, occurred_at=occurred_at,
            recorded_at=recorded_at, evidence_refs=evidence_refs,
            causation_id=causation_id, fail_at=fail_at,
            handler=lambda inv: inv.commit(
                reservation_id, actor_id, authorization_ref, idempotency_key,
                expected_reservation_version, now,
            ),
        )

    def release(self, *, reservation_id, actor_id, idempotency_key,
                expected_reservation_version, command_id, authority_ref,
                correlation_id, occurred_at, recorded_at, evidence_refs=(),
                causation_id=None, fail_at=None):
        request = {
            "reservation_id": reservation_id, "actor_id": actor_id,
            "expected_reservation_version": expected_reservation_version,
        }
        return self._execute(
            operation="release_reservation", command_id=command_id,
            idempotency_key=idempotency_key, request=request,
            actor_id=actor_id, authority_ref=authority_ref,
            correlation_id=correlation_id, occurred_at=occurred_at,
            recorded_at=recorded_at, evidence_refs=evidence_refs,
            causation_id=causation_id, fail_at=fail_at,
            handler=lambda inv: inv.release(
                reservation_id, actor_id, idempotency_key,
                expected_reservation_version,
            ),
        )

    def consume(self, *, reservation_id, actor_id, quantity, moved_lot_id,
                destination_location, new_custodian_id, idempotency_key,
                expected_reservation_version, command_id, authority_ref,
                correlation_id, occurred_at, recorded_at, evidence_refs=(),
                causation_id=None, fail_at=None):
        request = {
            "reservation_id": reservation_id, "actor_id": actor_id,
            "quantity": quantity, "moved_lot_id": moved_lot_id,
            "destination_location": destination_location,
            "new_custodian_id": new_custodian_id,
            "expected_reservation_version": expected_reservation_version,
        }
        return self._execute(
            operation="consume_reservation", command_id=command_id,
            idempotency_key=idempotency_key, request=request,
            actor_id=actor_id, authority_ref=authority_ref,
            correlation_id=correlation_id, occurred_at=occurred_at,
            recorded_at=recorded_at, evidence_refs=evidence_refs,
            causation_id=causation_id, fail_at=fail_at,
            handler=lambda inv: inv.consume(
                reservation_id, actor_id, quantity, moved_lot_id,
                destination_location, new_custodian_id, idempotency_key,
                expected_reservation_version,
            ),
        )

    def quarantine(self, *, lot_id, actor_id, idempotency_key,
                   expected_lot_version, reason, command_id, authority_ref,
                   correlation_id, occurred_at, recorded_at, evidence_refs=(),
                   causation_id=None, fail_at=None):
        request = {
            "lot_id": lot_id, "actor_id": actor_id,
            "expected_lot_version": expected_lot_version, "reason": reason,
        }
        return self._execute(
            operation="quarantine_lot", command_id=command_id,
            idempotency_key=idempotency_key, request=request,
            actor_id=actor_id, authority_ref=authority_ref,
            correlation_id=correlation_id, occurred_at=occurred_at,
            recorded_at=recorded_at, evidence_refs=evidence_refs,
            causation_id=causation_id, fail_at=fail_at,
            handler=lambda inv: inv.quarantine(
                lot_id, actor_id, idempotency_key, expected_lot_version, reason,
            ),
        )

    def get_lot(self, lot_id):
        _, state = self.repository.load_aggregate(AGGREGATE_TYPE, AGGREGATE_ID)
        inventory = _inventory_from_state(state)
        return inventory.get_lot(lot_id)

    def get_reservation(self, reservation_id):
        _, state = self.repository.load_aggregate(AGGREGATE_TYPE, AGGREGATE_ID)
        inventory = _inventory_from_state(state)
        return inventory.get_reservation(reservation_id)

    def snapshot(self):
        _, state = self.repository.load_aggregate(AGGREGATE_TYPE, AGGREGATE_ID)
        inventory = _inventory_from_state(state)
        inventory.assert_invariants()
        return {
            "lots": tuple(inventory._lots[key] for key in sorted(inventory._lots)),
            "reservations": tuple(
                inventory._reservations[key] for key in sorted(inventory._reservations)
            ),
        }

    def audit(self):
        snapshot = self.repository.verified_snapshot(AGGREGATE_TYPE, AGGREGATE_ID)
        replayed = _replay_inventory_projection(snapshot["events"])
        if replayed != snapshot["aggregate"]["state"]:
            raise SQLiteLotInventoryError(
                "persisted inventory projection differs from independent canonical event replay"
            )
        inventory = _inventory_from_state(replayed)
        return {
            **snapshot["report"], "lots": len(inventory._lots),
            "reservations": len(inventory._reservations),
        }

    def recover(self):
        snapshot = self.repository.verified_snapshot(AGGREGATE_TYPE, AGGREGATE_ID)
        replayed = _replay_inventory_projection(snapshot["events"])
        if replayed != snapshot["aggregate"]["state"]:
            raise SQLiteLotInventoryError(
                "recovery projection differs from independent canonical event replay"
            )
        inventory = _inventory_from_state(replayed)
        inventory.assert_invariants()
        return {
            "version": snapshot["aggregate"]["version"],
            "lots": tuple(inventory._lots[key] for key in sorted(inventory._lots)),
            "reservations": tuple(
                inventory._reservations[key] for key in sorted(inventory._reservations)
            ),
        }
