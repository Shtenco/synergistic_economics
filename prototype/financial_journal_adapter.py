"""Typed adapter from validated entity-journal events to the durable store.

The adapter deliberately delegates all accounting validation to
EntityJournal.post(). It does not accept arbitrary dictionaries as validated
journal events.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from financial_event_store import FinancialEventStore


class JournalStoreAdapterError(ValueError):
    """Raised when the validated-journal-to-store boundary is violated."""


def _decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise JournalStoreAdapterError("journal amount must be a finite positive Decimal")
    return format(value, "f")


def _posting_payload(line) -> dict:
    """Preserve all entity, counterparty, issuer and instrument dimensions."""
    required = (
        "account", "side", "entity_id", "institutional_sector",
        "counterparty_entity_id", "counterparty_sector",
        "issuer_entity_id", "issuer_sector", "instrument_id",
        "instrument_class", "currency", "maturity", "denomination",
        "valuation_basis",
    )
    payload = {}
    for field in required:
        value = getattr(line, field, None)
        if not isinstance(value, str):
            raise JournalStoreAdapterError(
                f"validated journal line has invalid {field}")
        payload[field] = value
    payload["amount"] = _decimal_text(getattr(line, "amount", None))
    return payload


def _event_payload(event) -> dict:
    event_id = getattr(event, "event_id", None)
    event_type = getattr(event, "event_type", None)
    period = getattr(event, "effective_period", None)
    lines = getattr(event, "lines", None)
    if not isinstance(event_id, str) or not event_id.strip():
        raise JournalStoreAdapterError("event_id is required")
    if not isinstance(event_type, str) or not event_type.strip():
        raise JournalStoreAdapterError("event_type is required")
    if not isinstance(period, int) or isinstance(period, bool) or period < 0:
        raise JournalStoreAdapterError("effective_period must be a non-negative integer")
    if not isinstance(lines, tuple) or not lines:
        raise JournalStoreAdapterError("event lines must be a non-empty immutable tuple")
    return {
        "event_id": event_id,
        "event_type": event_type,
        "effective_period": period,
        "postings": [_posting_payload(line) for line in lines],
    }


def append_validated_group(journal, store: FinancialEventStore, group_id: str,
                           events: Sequence, causation_id: str | None = None) -> bool:
    """Validate a group through EntityJournal, then persist it atomically.

    Returns True for a new durable group and False for an identical durable
    replay. If validation or persistence fails, newly inserted in-memory
    journal entries from this call are rolled back. Existing journal entries
    are never removed or overwritten.
    """
    if not callable(getattr(journal, "post", None)):
        raise JournalStoreAdapterError("an EntityJournal-compatible post() is required")
    journal_events = getattr(journal, "events", None)
    if not isinstance(journal_events, dict):
        raise JournalStoreAdapterError("journal must expose its validated event registry")
    if not isinstance(store, FinancialEventStore):
        raise JournalStoreAdapterError("a FinancialEventStore instance is required")
    if not isinstance(events, (tuple, list)) or not events:
        raise JournalStoreAdapterError("events must be a non-empty tuple or list")

    initial_ids = set(journal_events)
    try:
        # Validate every event with the canonical accounting validator before
        # the store receives any serialized payload.
        for event in events:
            event_id = getattr(event, "event_id", None)
            if not isinstance(event_id, str) or not event_id.strip():
                raise JournalStoreAdapterError("event_id is required")
            if event_id in journal_events:
                raise JournalStoreAdapterError(
                    f"event already exists in this journal instance: {event_id}")
            result = journal.post(event)
            if (journal_events.get(event_id) != event
                    or not isinstance(result, tuple) or len(result) != 2
                    or result[0] != result[1]):
                raise JournalStoreAdapterError(
                    f"EntityJournal did not validate and register event {event_id}")
        payloads = [_event_payload(event) for event in events]
        return store.append_group(group_id, payloads, causation_id)
    except Exception:
        # EntityJournal.post() mutates its in-memory event dict only after all
        # checks pass. Undo only entries newly inserted by this adapter call.
        for event in events:
            event_id = getattr(event, "event_id", None)
            if (isinstance(event_id, str) and event_id not in initial_ids
                    and journal_events.get(event_id) == event):
                journal_events.pop(event_id, None)
        raise
