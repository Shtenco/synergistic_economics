"""P6.2c canonical event-log integrity and replay audit.

This validates canonical envelopes already stored in the existing EventStore.
It does not rebuild business state and safely ignores legacy non-canonical events.
"""
from dataclasses import dataclass
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


def audit_canonical_event_log(event_store):
    """Validate envelope identity, payload digest, store digest and aggregate order.

    Legacy EventStore records without schema_version are counted but not decoded.
    Any record declaring schema_version is treated as an attempted canonical
    envelope; unsupported or malformed versions fail closed.
    """
    events = tuple(event_store.replay())
    canonical = []
    legacy = 0
    previous_sequence = 0

    for event in events:
        if isinstance(event.sequence, bool) or not isinstance(event.sequence, int):
            raise EventReplayError("EventStore sequence must be an integer")
        if event.sequence <= previous_sequence:
            raise EventReplayError("EventStore sequence must be strictly increasing")
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
        if payload["event_id"] != event.event_id:
            raise EventReplayError("envelope event_id differs from EventStore identity")
        if payload["event_type"] != event.event_type:
            raise EventReplayError("envelope event_type differs from EventStore identity")
        if payload["idempotency_key"] != event.idempotency_key:
            raise EventReplayError("envelope idempotency_key differs from EventStore identity")
        if not isinstance(payload["payload"], dict):
            raise EventReplayError("canonical domain payload must be an object")
        digest = sha256(canonical_json(payload["payload"]).encode("utf-8")).hexdigest()
        if digest != payload["payload_digest"]:
            raise EventReplayError("canonical domain payload digest mismatch")
        if _store_digest(event.event_type, payload) != event.digest:
            raise EventReplayError("EventStore envelope digest mismatch")

        for field in ("aggregate_type", "aggregate_id", "command_id"):
            if not isinstance(payload[field], str) or not payload[field].strip():
                raise EventReplayError(f"{field} must be non-empty text")
        version, ordinal = payload["aggregate_version"], payload["event_ordinal"]
        if isinstance(version, bool) or not isinstance(version, int) or version < 1:
            raise EventReplayError("aggregate_version must be a positive integer")
        if isinstance(ordinal, bool) or not isinstance(ordinal, int) or ordinal < 0:
            raise EventReplayError("event_ordinal must be a non-negative integer")
        if not isinstance(payload["evidence_refs"], list):
            raise EventReplayError("evidence_refs must be a list")
        canonical.append((event.sequence, payload))

    # Each aggregate advances exactly one version per command. Events belonging
    # to one command/version must have contiguous ordinals starting at zero.
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
