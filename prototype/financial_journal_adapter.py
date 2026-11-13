"""Lossless adapter from the canonical production EntityJournal to SQLite."""
from __future__ import annotations

from decimal import Decimal
from typing import Sequence

from entity_journal import EntityJournal, JournalEvent, JournalLine
from financial_event_store import FinancialEventStore


class JournalStoreAdapterError(ValueError):
    """Raised when the canonical journal-to-store boundary is violated."""


def _decimal_text(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite() or value <= 0:
        raise JournalStoreAdapterError("journal amount must be a finite positive Decimal")
    return format(value, "f")


def _posting_payload(line: JournalLine) -> dict:
    """Serialize every declared dimension; absence stays absent, never fabricated."""
    if not isinstance(line, JournalLine):
        raise JournalStoreAdapterError("posting must be a canonical JournalLine")
    required = ("account", "side", "entity_id", "institutional_sector")
    optional = (
        "counterparty_entity_id", "counterparty_sector", "issuer_entity_id",
        "issuer_sector", "instrument_id", "instrument_class", "currency",
        "maturity", "denomination", "valuation_basis",
    )
    payload = {}
    for field in required:
        value = getattr(line, field)
        if not isinstance(value, str) or not value or value != value.strip():
            raise JournalStoreAdapterError(f"journal line has invalid {field}")
        payload[field] = value
    for field in optional:
        value = getattr(line, field)
        if value is None:
            continue
        if not isinstance(value, str) or not value or value != value.strip():
            raise JournalStoreAdapterError(f"journal line has invalid optional {field}")
        payload[field] = value
    payload["amount"] = _decimal_text(line.amount)
    return payload


def _event_payload(event: JournalEvent) -> dict:
    if not isinstance(event, JournalEvent):
        raise JournalStoreAdapterError("event must be a canonical JournalEvent")
    if not isinstance(event.lines, tuple) or not event.lines:
        raise JournalStoreAdapterError("event lines must be a non-empty immutable tuple")
    payload = {
        "event_id": event.event_id,
        "event_type": event.event_type,
        "effective_period": event.effective_period,
        "component": event.component,
        "legal_effect": event.legal_effect,
        "postings": [_posting_payload(line) for line in event.lines],
    }
    if event.writeoff_claim_delta is not None:
        payload["writeoff_claim_delta"] = _decimal_text(event.writeoff_claim_delta)
    if event.forgiven_principal is not None:
        payload["forgiven_principal"] = _decimal_text(event.forgiven_principal)
    if event.legal_evidence is not None:
        evidence = event.legal_evidence
        payload["legal_evidence"] = {
            "evidence_ref": evidence.evidence_ref,
            "authority": evidence.authority,
            "effective_at": evidence.effective_at,
            "scope": evidence.scope,
            "parties": list(evidence.parties),
        }
    return payload


def append_validated_group(journal: EntityJournal, store: FinancialEventStore,
                           group_id: str, events: Sequence[JournalEvent],
                           causation_id: str | None = None) -> bool:
    """Validate all GOLD-2A events, then persist the immutable group atomically."""
    if not isinstance(journal, EntityJournal):
        raise JournalStoreAdapterError("production EntityJournal instance is required")
    if not isinstance(store, FinancialEventStore):
        raise JournalStoreAdapterError("FinancialEventStore instance is required")
    if not isinstance(events, (tuple, list)) or not events:
        raise JournalStoreAdapterError("events must be a non-empty tuple or list")
    if any(not isinstance(event, JournalEvent) for event in events):
        raise JournalStoreAdapterError("all events must be canonical JournalEvent values")

    initial_ids = set(journal.events)
    try:
        for event in events:
            if event.event_id in journal.events:
                raise JournalStoreAdapterError(f"event already exists in journal: {event.event_id}")
            result = journal.post(event)
            if (journal.events.get(event.event_id) != event
                    or not isinstance(result, tuple) or len(result) != 2
                    or result[0] != result[1]):
                raise JournalStoreAdapterError(
                    f"EntityJournal did not validate and register {event.event_id}")
        payloads = [_event_payload(event) for event in events]
        return store.append_group(group_id, payloads, causation_id)
    except Exception:
        for event in events:
            if event.event_id not in initial_ids and journal.events.get(event.event_id) == event:
                journal.events.pop(event.event_id, None)
        raise
