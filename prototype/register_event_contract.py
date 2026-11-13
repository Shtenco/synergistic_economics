"""Versioned canonical envelope contract for all six native economic registers."""
from __future__ import annotations
from datetime import datetime, timedelta
from collections.abc import Mapping
from copy import deepcopy

SCHEMA_ID = "synergy.native-register-event"
SCHEMA_VERSION = 1
REGISTERS = ("physical", "capital", "labour", "product", "legal_rights", "financial")

class RegisterEventContractError(ValueError):
    """Invalid or unsupported native register event contract."""

def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise RegisterEventContractError(f"{field} must be trimmed non-empty text")
    return value

def _utc(value, field):
    _text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RegisterEventContractError(f"{field} must be an ISO-8601 UTC timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        raise RegisterEventContractError(f"{field} must explicitly use UTC")
    return value

def normalize_event_envelope(register_id, envelope):
    """Migrate legacy unversioned v0 envelopes to v1; reject unknown versions."""
    if register_id not in REGISTERS:
        raise RegisterEventContractError("unknown register_id")
    if not isinstance(envelope, Mapping):
        raise RegisterEventContractError("native event envelope must be an object")
    result = deepcopy(dict(envelope))
    schema_id, version = result.get("schema_id"), result.get("schema_version")
    if schema_id is None and version is None:
        source_version = 0
    elif schema_id == SCHEMA_ID and version == 0 and not isinstance(version, bool):
        source_version = 0
    elif schema_id == SCHEMA_ID and version == SCHEMA_VERSION and not isinstance(version, bool):
        source_version = SCHEMA_VERSION
    else:
        raise RegisterEventContractError("unsupported or incomplete native event schema identity")
    if source_version == 0:
        if result.get("register_id") not in (None, register_id):
            raise RegisterEventContractError("legacy envelope register_id does not match its participant")
        result.update({"schema_id": SCHEMA_ID, "schema_version": SCHEMA_VERSION, "register_id": register_id})
        result["migration"] = {"migration_id": "native-event-envelope-v0-to-v1", "source_schema_version": 0}
    elif result.get("register_id") != register_id:
        raise RegisterEventContractError("native envelope register_id does not match its participant")
    for field in ("event_type", "actor_id", "authority_ref", "idempotency_key"):
        _text(result.get(field), field)
    _utc(result.get("effective_at"), "effective_at")
    _utc(result.get("recorded_at"), "recorded_at")
    if not isinstance(result.get("payload"), Mapping):
        raise RegisterEventContractError("native domain payload must be an object")
    result["payload"] = dict(result["payload"])
    allowed = {"schema_id", "schema_version", "register_id", "event_type", "effective_at",
               "recorded_at", "actor_id", "authority_ref", "idempotency_key", "payload",
               "stock_flow_movements", "no_stock_flow_effect", "migration"}
    unknown = set(result) - allowed
    if unknown:
        raise RegisterEventContractError(f"unknown native event envelope fields: {sorted(unknown)}")
    if "stock_flow_movements" in result:
        specs = result["stock_flow_movements"]
        if not isinstance(specs, list) or not specs or any(not isinstance(item, Mapping) for item in specs):
            raise RegisterEventContractError("stock_flow_movements must be a non-empty array of objects")
        if "no_stock_flow_effect" in result:
            raise RegisterEventContractError("event cannot declare movements and no-stock-flow effect together")
    if "no_stock_flow_effect" in result:
        _text(result["no_stock_flow_effect"], "no_stock_flow_effect")
    migration = result.get("migration")
    if migration is not None and dict(migration) != {
        "migration_id": "native-event-envelope-v0-to-v1", "source_schema_version": 0
    }:
        raise RegisterEventContractError("migration provenance does not match the registered v0-to-v1 migration")
    return result


def equivalent_event_envelopes(register_id, left, right):
    """Compare envelopes by current semantics without rewriting either source."""
    try:
        return normalize_event_envelope(register_id, left) == normalize_event_envelope(register_id, right)
    except (RegisterEventContractError, TypeError, AttributeError):
        return False
