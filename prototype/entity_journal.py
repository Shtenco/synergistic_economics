"""Canonical production entity journal for the frozen SFC-GOLD-2A contract.

This module is deliberately independent of research audit fixtures. It validates
entity/sector identity, balanced postings, GOLD-2A event semantics and legal
metadata before an event can cross the durable-store adapter boundary.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Iterable

D = Decimal

SECTORS = frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"})
CANONICAL_GOLD_2A_EVENTS = frozenset({
    "bank_loan_origination",
    "interest_accrual",
    "interest_payment",
    "impairment_allowance_recognition",
    "principal_repayment",
    "creditor_write_off",
    "legal_debt_forgiveness",
})
# Deliberately no aliases: historical spellings are rejected at the boundary.
EVENT_SEMANTICS = {
    "bank_loan_origination": ("T", "create_principal_and_deposit"),
    "interest_accrual": ("T", "accrue_interest"),
    "interest_payment": ("T", "settle_accrued_interest"),
    "impairment_allowance_recognition": ("V", "valuation_allowance_only"),
    "principal_repayment": ("T", "reduce_principal"),
    "creditor_write_off": ("O", "accounting_derecognition_no_legal_extinguishment"),
    "legal_debt_forgiveness": ("T", "legally_extinguish_principal"),
}
CLAIM_ACCOUNTS = frozenset({
    "loan_asset", "loan_liability", "deposit_asset", "deposit_liability",
    "interest_receivable", "interest_payable",
})
OPTIONAL_LINE_FIELDS = (
    "counterparty_entity_id", "counterparty_sector", "issuer_entity_id",
    "issuer_sector", "instrument_id", "instrument_class", "currency",
    "maturity", "denomination", "valuation_basis",
)
INSTRUMENT_FIELDS = (
    "instrument_id", "instrument_class", "currency", "maturity",
    "denomination", "valuation_basis",
)
EXPECTED_ACCOUNTS = {
    "bank_loan_origination": {
        "loan_asset": ("D", 1), "loan_liability": ("C", 1),
        "deposit_asset": ("D", 1), "deposit_liability": ("C", 1),
    },
    "interest_accrual": {
        "interest_receivable": ("D", 1), "interest_income": ("C", 1),
        "interest_expense": ("D", 1), "interest_payable": ("C", 1),
    },
    "interest_payment": {
        "deposit_liability": ("D", 1), "interest_receivable": ("C", 1),
        "interest_payable": ("D", 1), "deposit_asset": ("C", 1),
    },
    "impairment_allowance_recognition": {
        "impairment_expense": ("D", 1), "impairment_allowance": ("C", 1),
    },
    "principal_repayment": {
        "loan_liability": ("D", 1), "loan_asset": ("C", 1),
        "deposit_liability": ("D", 1), "deposit_asset": ("C", 1),
    },
    "creditor_write_off": {
        "impairment_allowance": ("D", 1), "loan_asset": ("C", 1),
    },
    "legal_debt_forgiveness": {
        "debt_forgiveness_expense": ("D", 1), "loan_asset": ("C", 1),
        "loan_liability": ("D", 1), "debt_forgiveness_gain": ("C", 1),
    },
}


class EntityJournalError(ValueError):
    """Canonical entity-journal validation failure."""


def _required_text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise EntityJournalError(f"{field} must be trimmed non-empty text")
    return value


def _positive_decimal(value, field):
    if not isinstance(value, D) or not value.is_finite() or value <= 0:
        raise EntityJournalError(f"{field} must be a finite positive Decimal")
    return value


@dataclass(frozen=True)
class SectorMembership:
    entity_id: str
    sector: str
    effective_from: int
    effective_to: int | None = None


class EntityRegistry:
    """Effective-dated entity identity; sector membership is never inferred."""
    def __init__(self, memberships: Iterable[SectorMembership]):
        rows = tuple(memberships)
        grouped = {}
        for row in rows:
            if not isinstance(row, SectorMembership):
                raise EntityJournalError("registry rows must be SectorMembership values")
            _required_text(row.entity_id, "entity_id")
            if row.sector not in SECTORS:
                raise EntityJournalError(f"unknown institutional sector: {row.sector}")
            if not isinstance(row.effective_from, int) or isinstance(row.effective_from, bool) or row.effective_from < 0:
                raise EntityJournalError("effective_from must be a non-negative integer")
            if row.effective_to is not None and (
                not isinstance(row.effective_to, int) or isinstance(row.effective_to, bool)
                or row.effective_to <= row.effective_from
            ):
                raise EntityJournalError("effective_to must be later than effective_from")
            grouped.setdefault(row.entity_id, []).append(row)
        self.memberships = rows
        self._by_entity = {}
        for entity, entries in grouped.items():
            entries.sort(key=lambda x: x.effective_from)
            for left, right in zip(entries, entries[1:]):
                if left.effective_to is None or right.effective_from < left.effective_to:
                    raise EntityJournalError(f"overlapping sector memberships for {entity}")
            self._by_entity[entity] = tuple(entries)

    def sector_of(self, entity_id: str, period: int) -> str:
        _required_text(entity_id, "entity_id")
        if not isinstance(period, int) or isinstance(period, bool) or period < 0:
            raise EntityJournalError("effective period must be a non-negative integer")
        matches = [row for row in self._by_entity.get(entity_id, ())
                   if row.effective_from <= period and
                   (row.effective_to is None or period < row.effective_to)]
        if len(matches) != 1:
            raise EntityJournalError(
                f"entity {entity_id} has {len(matches)} memberships at period {period}")
        return matches[0].sector


@dataclass(frozen=True)
class JournalLine:
    account: str
    side: str
    amount: Decimal
    entity_id: str
    institutional_sector: str
    counterparty_entity_id: str | None = None
    counterparty_sector: str | None = None
    issuer_entity_id: str | None = None
    issuer_sector: str | None = None
    instrument_id: str | None = None
    instrument_class: str | None = None
    currency: str | None = None
    maturity: str | None = None
    denomination: str | None = None
    valuation_basis: str | None = None


@dataclass(frozen=True)
class LegalEvidence:
    evidence_ref: str
    authority: str
    effective_at: str
    scope: str
    parties: tuple[str, ...]


@dataclass(frozen=True)
class JournalEvent:
    event_id: str
    event_type: str
    effective_period: int
    lines: tuple[JournalLine, ...]
    component: str
    legal_effect: str
    writeoff_claim_delta: Decimal | None = None
    forgiven_principal: Decimal | None = None
    legal_evidence: LegalEvidence | None = None


def make_line(registry: EntityRegistry, period: int, account: str, side: str,
              amount: Decimal, entity_id: str, *, counterparty=None, issuer=None,
              instrument_id=None, instrument_class=None, currency=None,
              maturity=None, denomination=None, valuation_basis=None) -> JournalLine:
    sector = registry.sector_of(entity_id, period)
    counterparty_sector = registry.sector_of(counterparty, period) if counterparty is not None else None
    issuer_sector = registry.sector_of(issuer, period) if issuer is not None else None
    return JournalLine(
        account, side, amount, entity_id, sector, counterparty,
        counterparty_sector, issuer, issuer_sector, instrument_id,
        instrument_class, currency, maturity, denomination, valuation_basis,
    )


def _validate_line(line: JournalLine, registry: EntityRegistry, period: int) -> None:
    if not isinstance(line, JournalLine):
        raise EntityJournalError("journal line has the wrong type")
    _required_text(line.account, "account")
    if line.side not in {"D", "C"}:
        raise EntityJournalError("journal side must be D or C")
    _positive_decimal(line.amount, "journal amount")
    if line.institutional_sector != registry.sector_of(line.entity_id, period):
        raise EntityJournalError("entity/sector identity mismatch")
    for value, field in ((line.counterparty_entity_id, "counterparty_entity_id"),
                         (line.counterparty_sector, "counterparty_sector"),
                         (line.issuer_entity_id, "issuer_entity_id"),
                         (line.issuer_sector, "issuer_sector")):
        if value is not None:
            _required_text(value, field)
    if line.counterparty_entity_id is None and line.counterparty_sector is not None:
        raise EntityJournalError("counterparty sector without counterparty entity")
    if line.issuer_entity_id is None and line.issuer_sector is not None:
        raise EntityJournalError("issuer sector without issuer entity")
    if line.counterparty_entity_id is not None:
        if line.counterparty_sector != registry.sector_of(line.counterparty_entity_id, period):
            raise EntityJournalError("counterparty sector identity mismatch")
    if line.issuer_entity_id is not None:
        if line.issuer_sector != registry.sector_of(line.issuer_entity_id, period):
            raise EntityJournalError("issuer sector identity mismatch")
    for field in OPTIONAL_LINE_FIELDS:
        value = getattr(line, field)
        if value is not None:
            _required_text(value, field)
    if line.account in CLAIM_ACCOUNTS:
        for field in INSTRUMENT_FIELDS:
            _required_text(getattr(line, field), field)
        _required_text(line.issuer_entity_id, "claim issuer_entity_id")
        if line.account.endswith("_liability"):
            if line.issuer_entity_id != line.entity_id or line.counterparty_entity_id is None:
                raise EntityJournalError("liability must identify issuer and holder")


def _validate_legal_evidence(evidence: LegalEvidence, event: JournalEvent) -> None:
    if not isinstance(evidence, LegalEvidence):
        raise EntityJournalError("legal debt forgiveness requires typed legal evidence")
    for field in ("evidence_ref", "authority", "effective_at", "scope"):
        _required_text(getattr(evidence, field), f"legal_evidence.{field}")
    if not isinstance(evidence.parties, tuple) or len(evidence.parties) < 2:
        raise EntityJournalError("legal evidence must identify at least two parties")
    parties = tuple(_required_text(x, "legal_evidence.party") for x in evidence.parties)
    if len(set(parties)) != len(parties):
        raise EntityJournalError("legal evidence parties must be unique")
    event_entities = {line.entity_id for line in event.lines}
    if not set(parties).issubset(event_entities):
        raise EntityJournalError("legal evidence parties must be present in event postings")


class EntityJournal:
    """Single canonical validator for GOLD-2A events; no legacy aliases."""
    def __init__(self, registry: EntityRegistry):
        if not isinstance(registry, EntityRegistry):
            raise EntityJournalError("EntityRegistry is required")
        self.registry = registry
        self.events: dict[str, JournalEvent] = {}

    def post(self, event: JournalEvent) -> tuple[Decimal, Decimal]:
        if not isinstance(event, JournalEvent):
            raise EntityJournalError("event must be a canonical JournalEvent")
        _required_text(event.event_id, "event_id")
        if event.event_id in self.events:
            raise EntityJournalError("duplicate event_id")
        if event.event_type not in CANONICAL_GOLD_2A_EVENTS:
            raise EntityJournalError(f"non-canonical or unsupported GOLD-2A event: {event.event_type}")
        if (not isinstance(event.effective_period, int) or isinstance(event.effective_period, bool)
                or event.effective_period < 0):
            raise EntityJournalError("effective_period must be a non-negative integer")
        expected_component, expected_legal_effect = EVENT_SEMANTICS[event.event_type]
        if event.component != expected_component or event.legal_effect != expected_legal_effect:
            raise EntityJournalError("event component/legal_effect contradicts canonical GOLD-2A semantics")
        if not isinstance(event.lines, tuple) or not event.lines:
            raise EntityJournalError("event lines must be a non-empty immutable tuple")

        debit = sum((line.amount for line in event.lines if line.side == "D"), D("0"))
        credit = sum((line.amount for line in event.lines if line.side == "C"), D("0"))
        for line in event.lines:
            _validate_line(line, self.registry, event.effective_period)
        if debit != credit:
            raise EntityJournalError(f"unbalanced event {event.event_id}: {debit} != {credit}")

        composition = {}
        for line in event.lines:
            composition.setdefault(line.account, []).append(line)
        expected = EXPECTED_ACCOUNTS[event.event_type]
        if set(composition) != set(expected):
            raise EntityJournalError("event account composition differs from GOLD-2A contract")
        for account, (side, count) in expected.items():
            rows = composition[account]
            if len(rows) != count or any(row.side != side for row in rows):
                raise EntityJournalError(f"invalid {account} count or debit/credit side")
        amounts = {line.amount for line in event.lines}
        if len(amounts) != 1:
            raise EntityJournalError("GOLD-2A event postings must carry one common event amount")
        amount = next(iter(amounts))

        # Bilateral claim identity: asset holder/issuer equals liability holder/issuer.
        if event.event_type in {
            "bank_loan_origination", "interest_accrual", "interest_payment",
            "principal_repayment", "legal_debt_forgiveness",
        }:
            assets = {}
            liabilities = {}
            for line in event.lines:
                if line.account.endswith("_asset") or line.account in {"interest_receivable"}:
                    key = (line.instrument_id, line.instrument_class, line.entity_id,
                           line.issuer_entity_id, line.currency, line.maturity,
                           line.denomination, line.valuation_basis)
                    assets[key] = assets.get(key, D("0")) + (line.amount if line.side == "D" else -line.amount)
                elif line.account.endswith("_liability") or line.account == "interest_payable":
                    holder = line.counterparty_entity_id
                    key = (line.instrument_id, line.instrument_class, holder,
                           line.entity_id, line.currency, line.maturity,
                           line.denomination, line.valuation_basis)
                    liabilities[key] = liabilities.get(key, D("0")) + (line.amount if line.side == "C" else -line.amount)
            # Interest and principal events can contain offsetting movements;
            # compare absolute movement by the complete instrument key.
            if event.event_type in {"bank_loan_origination", "interest_accrual"}:
                if assets != liabilities:
                    raise EntityJournalError("claim asset/liability identity mirror mismatch")

        if event.event_type == "creditor_write_off":
            _positive_decimal(event.writeoff_claim_delta, "writeoff_claim_delta")
            if event.writeoff_claim_delta != amount:
                raise EntityJournalError("writeoff_claim_delta must equal derecognized principal")
            if event.forgiven_principal is not None or event.legal_evidence is not None:
                raise EntityJournalError("write-off cannot carry forgiveness metadata")
        elif event.writeoff_claim_delta is not None:
            raise EntityJournalError("writeoff_claim_delta is only valid for creditor_write_off")

        if event.event_type == "legal_debt_forgiveness":
            _positive_decimal(event.forgiven_principal, "forgiven_principal")
            if event.forgiven_principal != amount:
                raise EntityJournalError("forgiven_principal must equal the legally extinguished amount")
            _validate_legal_evidence(event.legal_evidence, event)
        elif event.forgiven_principal is not None or event.legal_evidence is not None:
            raise EntityJournalError("forgiveness metadata is only valid for legal_debt_forgiveness")

        # Reserve is a contra-asset: recognition credits it, write-off consumes it.
        if event.event_type == "impairment_allowance_recognition":
            if event.lines[1].account != "impairment_allowance":
                raise EntityJournalError("impairment event must recognize the allowance")
        if event.event_type == "creditor_write_off":
            loan = composition["loan_asset"][0]
            allowance = composition["impairment_allowance"][0]
            if loan.entity_id != allowance.entity_id:
                raise EntityJournalError("write-off and allowance must belong to the same creditor")
            if loan.issuer_entity_id is None:
                raise EntityJournalError("written-off claim must retain debtor identity")

        # Register only after every invariant succeeds.
        self.events[event.event_id] = event
        return debit, credit
