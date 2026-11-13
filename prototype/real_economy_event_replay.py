"""P6.2c canonical event-log integrity and replay audit.

This validates canonical envelopes already stored in the existing EventStore.
It does not rebuild business state and safely ignores legacy non-canonical events.
"""
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json

from real_economy_event_bridge import canonical_json, EventBridgeError


class EventReplayError(EventBridgeError):
    """Canonical event history is malformed or internally inconsistent."""


@dataclass(frozen=True)
class ReplayAudit:
    total_events: int
    canonical_events: int
    legacy_events: int
    aggregates: int
    commands: int
    last_sequence: int


def _store_digest(event_type, payload):
    # Match the existing EventStore's exact digest algorithm.
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return sha256((event_type + "|" + raw).encode()).hexdigest()


def _non_empty_text(value, field):
    if not isinstance(value, str) or not value.strip():
        raise EventReplayError(f"{field} must be non-empty text")
    return value


def _utc_timestamp(value, field):
    _non_empty_text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        raise EventReplayError(f"{field} must be an ISO-8601 timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset().total_seconds() != 0:
        raise EventReplayError(f"{field} must be UTC")
    return parsed


def _positive_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise EventReplayError(f"{field} must be a positive integer")


def _non_negative_int(value, field):
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise EventReplayError(f"{field} must be a non-negative integer")


def audit_canonical_event_log(event_store):
    """Validate canonical envelopes, global identities and aggregate command order.

    Legacy EventStore records without schema_version are counted but not decoded.
    Any record declaring schema_version is treated as an attempted canonical
    envelope; unsupported or malformed versions fail closed.
    """
    events = tuple(event_store.replay())
    canonical = []
    legacy = 0
    previous_sequence = 0
    seen_event_ids = set()
    seen_idempotency_keys = set()
    command_facts = {}

    for event in events:
        _positive_int(event.sequence, "EventStore sequence")
        if event.sequence != previous_sequence + 1:
            raise EventReplayError("EventStore sequence must be contiguous; a gap indicates missing history")
        previous_sequence = event.sequence

        payload = event.payload
        if not isinstance(payload, dict) or "schema_version" not in payload:
            legacy += 1
            continue
        if payload.get("schema_version") != "synergy.event.v1":
            raise EventReplayError("unsupported canonical event schema_version")

        required = (
            "event_id", "event_type", "aggregate_type", "aggregate_id",
            "aggregate_version", "event_ordinal", "occurred_at", "recorded_at",
            "actor_id", "authority_ref", "idempotency_key", "command_id",
            "correlation_id", "payload", "evidence_refs", "payload_digest",
        )
        if any(key not in payload for key in required):
            raise EventReplayError("canonical event envelope is missing required fields")

        event_id = _non_empty_text(payload["event_id"], "event_id")
        event_type = _non_empty_text(payload["event_type"], "event_type")
        idempotency_key = _non_empty_text(payload["idempotency_key"], "idempotency_key")
        aggregate_type = _non_empty_text(payload["aggregate_type"], "aggregate_type")
        aggregate_id = _non_empty_text(payload["aggregate_id"], "aggregate_id")
        command_id = _non_empty_text(payload["command_id"], "command_id")
        actor_id = _non_empty_text(payload["actor_id"], "actor_id")
        authority_ref = _non_empty_text(payload["authority_ref"], "authority_ref")
        correlation_id = _non_empty_text(payload["correlation_id"], "correlation_id")

        if event_id != event.event_id:
            raise EventReplayError("envelope event_id differs from EventStore identity")
        if event_type != event.event_type:
            raise EventReplayError("envelope event_type differs from EventStore identity")
        if idempotency_key != event.idempotency_key:
            raise EventReplayError("envelope idempotency_key differs from EventStore identity")
        if event_id in seen_event_ids:
            raise EventReplayError("duplicate canonical event_id")
        if idempotency_key in seen_idempotency_keys:
            raise EventReplayError("duplicate canonical idempotency_key")
        seen_event_ids.add(event_id)
        seen_idempotency_keys.add(idempotency_key)

        if "causation_id" in payload and payload["causation_id"] is not None:
            _non_empty_text(payload["causation_id"], "causation_id")
        _utc_timestamp(payload["occurred_at"], "occurred_at")
        _utc_timestamp(payload["recorded_at"], "recorded_at")
        _positive_int(payload["aggregate_version"], "aggregate_version")
        _non_negative_int(payload["event_ordinal"], "event_ordinal")

        refs = payload["evidence_refs"]
        if not isinstance(refs, list):
            raise EventReplayError("evidence_refs must be a list")
        normalized_refs = [_non_empty_text(ref, "evidence_ref") for ref in refs]
        if len(set(normalized_refs)) != len(normalized_refs):
            raise EventReplayError("evidence_refs must be unique")

        if not isinstance(payload["payload"], dict):
            raise EventReplayError("canonical domain payload must be an object")
        digest = sha256(canonical_json(payload["payload"]).encode("utf-8")).hexdigest()
        if digest != payload["payload_digest"]:
            raise EventReplayError("canonical domain payload digest mismatch")
        if _store_digest(event.event_type, payload) != event.digest:
            raise EventReplayError("EventStore envelope digest mismatch")

        # A command has one aggregate/version and stable actor/authority/
        # correlation metadata. This coordinator emits exactly one aggregate
        # transition per command; cross-aggregate workflows need an explicit
        # future schema rather than being silently accepted here.
        facts = (aggregate_type, aggregate_id, payload["aggregate_version"],
                 actor_id, authority_ref, correlation_id)
        prior_facts = command_facts.setdefault(command_id, facts)
        if prior_facts != facts:
            raise EventReplayError("command_id reused across aggregate/version or command metadata")
        canonical.append((event.sequence, payload))

    aggregate_groups = {}
    for sequence, payload in canonical:
        key = (payload["aggregate_type"], payload["aggregate_id"])
        aggregate_groups.setdefault(key, []).append((sequence, payload))

    command_count = 0
    for aggregate, rows in aggregate_groups.items():
        last_version = 0
        index = 0
        while index < len(rows):
            _, first = rows[index]
            version = first["aggregate_version"]
            command_id = first["command_id"]
            if version != last_version + 1:
                raise EventReplayError(
                    f"aggregate {aggregate} version gap or regression: "
                    f"expected {last_version + 1}, got {version}"
                )
            ordinal = 0
            while index < len(rows):
                _, item = rows[index]
                if item["aggregate_version"] != version:
                    break
                if item["command_id"] != command_id:
                    raise EventReplayError("multiple commands share one aggregate version")
                if item["event_ordinal"] != ordinal:
                    raise EventReplayError("event ordinals must be contiguous from zero")
                ordinal += 1
                index += 1
            last_version = version
            command_count += 1

    return ReplayAudit(
        total_events=len(events),
        canonical_events=len(canonical),
        legacy_events=legacy,
        aggregates=len(aggregate_groups),
        commands=command_count,
        last_sequence=previous_sequence,
    )
