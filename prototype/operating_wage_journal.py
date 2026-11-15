"""Research operating wage subledger, kept separate from the frozen GOLD-2A journal.

This is a deterministic prototype ledger, not yet a durable native-register adapter.
It accepts only verified paid labour deliveries and records wage accrual/payment
with balanced postings and explicit stock-flow movement metadata.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Mapping
from types import MappingProxyType


class OperatingWageError(ValueError):
    pass


D = Decimal
_VERIFIED_TOKEN = object()


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise OperatingWageError(f"{field} must be trimmed non-empty text")
    return value


def _positive(value, field):
    if isinstance(value, bool):
        raise OperatingWageError(f"{field} must be a finite positive Decimal")
    try:
        number = D(str(value))
    except Exception as exc:
        raise OperatingWageError(f"{field} must be a finite positive Decimal") from exc
    if not number.is_finite() or number <= 0:
        raise OperatingWageError(f"{field} must be a finite positive Decimal")
    return number


def _minor_unit(value):
    unit = _positive(value, "minor_unit")
    if unit > 1 or unit.as_tuple().exponent > 0:
        raise OperatingWageError("minor_unit must be a positive fraction no greater than one")
    return unit


@dataclass(frozen=True)
class WageContract:
    worker_id: str
    employer_id: str
    period_label: str
    period_index: int
    currency: str
    hourly_rate: Decimal
    contract_ref: str
    evidence_ref: str
    minor_unit: Decimal = D("0.01")

    def validate(self):
        for field in ("worker_id", "employer_id", "period_label", "currency",
                      "contract_ref", "evidence_ref"):
            _text(getattr(self, field), field)
        if self.worker_id == self.employer_id:
            raise OperatingWageError("worker and employer must be distinct")
        if not isinstance(self.period_index, int) or isinstance(self.period_index, bool) or self.period_index < 1:
            raise OperatingWageError("period_index must be a positive integer")
        if not isinstance(self.hourly_rate, D) or not isinstance(self.minor_unit, D):
            raise OperatingWageError("hourly_rate and minor_unit must be Decimal values")
        _positive(self.hourly_rate, "hourly_rate")
        _minor_unit(self.minor_unit)


@dataclass(frozen=True)
class VerifiedLabourDelivery:
    engagement_id: str
    delivery_event_id: str
    verification_ref: str
    worker_id: str
    employer_id: str
    delivery_evidence_ref: str
    period_label: str
    delivered_hours: Decimal
    aggregate_version: int
    _authority_token: object = field(default=None, repr=False, compare=False)

    def validate(self):
        for field in ("engagement_id", "delivery_event_id", "verification_ref",
                      "worker_id", "employer_id", "delivery_evidence_ref", "period_label"):
            _text(getattr(self, field), field)
        _positive(self.delivered_hours, "delivered_hours")
        if self._authority_token is not _VERIFIED_TOKEN:
            raise OperatingWageError("labour delivery must originate from the authorized labour-register reader")
        if not isinstance(self.delivered_hours, D):
            raise OperatingWageError("delivered_hours must be a Decimal value")
        if not isinstance(self.aggregate_version, int) or isinstance(self.aggregate_version, bool) or self.aggregate_version < 1:
            raise OperatingWageError("aggregate_version must be positive")


def verified_delivery_from_register(labour_register, engagement_id, principal_id,
                                    *, verification_ref):
    """Read the authoritative labour aggregate; never infer delivery from an offer."""
    _text(engagement_id, "engagement_id")
    _text(principal_id, "principal_id")
    _text(verification_ref, "verification_ref")
    state, version = labour_register.state(engagement_id, principal_id=principal_id)
    if not isinstance(state, dict):
        raise OperatingWageError("labour engagement does not exist")
    if state.get("status") != "VERIFIED":
        raise OperatingWageError("wages require a VERIFIED labour engagement")
    if state.get("classification") != "paid":
        raise OperatingWageError("unpaid care, civic, training or other labour cannot enter wage accrual")
    delivery_event_id = _text(state.get("delivery_event_id"), "delivery_event_id")
    if not state.get("verification_ref"):
        raise OperatingWageError("verified labour event has no verification evidence")
    if state["verification_ref"] != verification_ref:
        raise OperatingWageError("verification evidence does not match the labour register")
    return VerifiedLabourDelivery(
        engagement_id=engagement_id,
        delivery_event_id=delivery_event_id,
        verification_ref=verification_ref,
        worker_id=_text(state.get("person_ref"), "person_ref"),
        employer_id=_text(state.get("activity_id"), "activity_id"),
        delivery_evidence_ref=_text(state.get("delivery_evidence_ref"), "delivery_evidence_ref"),
        period_label=_text(state.get("period"), "period"),
        delivered_hours=_positive(state.get("delivered_hours"), "delivered_hours"),
        aggregate_version=version,
        _authority_token=_VERIFIED_TOKEN,
    )


@dataclass(frozen=True)
class OperatingPosting:
    account: str
    side: str
    amount: Decimal
    entity_id: str
    sector: str
    counterparty_id: str
    instrument_id: str
    currency: str


@dataclass(frozen=True)
class OperatingEvent:
    event_id: str
    event_type: str
    period_index: int
    engagement_id: str
    period_label: str
    delivered_hours: Decimal
    hourly_rate: Decimal
    claim_id: str
    worker_id: str
    employer_id: str
    bank_id: str
    currency: str
    amount: Decimal
    causation_id: str
    evidence_ref: str
    delivery_event_id: str
    delivery_evidence_ref: str
    verification_ref: str
    contract_ref: str
    contract_evidence_ref: str
    labour_aggregate_version: int
    minor_unit: Decimal
    lines: tuple[OperatingPosting, ...]
    stock_flow_movements: tuple[dict, ...]

    def to_native_payload(self):
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "period_index": self.period_index,
            "engagement_id": self.engagement_id,
            "period_label": self.period_label,
            "delivered_hours": str(self.delivered_hours),
            "hourly_rate": str(self.hourly_rate),
            "claim_id": self.claim_id,
            "worker_id": self.worker_id,
            "employer_id": self.employer_id,
            "bank_id": self.bank_id,
            "currency": self.currency,
            "amount": str(self.amount),
            "minor_unit": str(self.minor_unit),
            "causation_id": self.causation_id,
            "evidence_ref": self.evidence_ref,
            "delivery_event_id": self.delivery_event_id,
            "delivery_evidence_ref": self.delivery_evidence_ref,
            "verification_ref": self.verification_ref,
            "contract_ref": self.contract_ref,
            "contract_evidence_ref": self.contract_evidence_ref,
            "labour_aggregate_version": self.labour_aggregate_version,
            "postings": [
                {**asdict(line), "amount": str(line.amount)}
                for line in self.lines
            ],
        }


class OperatingWageJournal:
    """Balanced, replayable-in-memory wage claim and deposit settlement ledger."""

    def __init__(self, *, bank_id, sectors: Mapping[str, str], opening_deposits: Mapping[tuple[str, str], Decimal]):
        self.bank_id = _text(bank_id, "bank_id")
        if not isinstance(sectors, Mapping) or not isinstance(opening_deposits, Mapping):
            raise OperatingWageError("sectors and opening_deposits mappings are required")
        self.sectors = dict(sectors)
        self.sectors.setdefault(self.bank_id, "CBank")
        for entity, sector in self.sectors.items():
            _text(entity, "sector entity")
            if sector not in {"H", "NFC", "CB", "CBank", "GOV", "ROW"}:
                raise OperatingWageError(f"unsupported institutional sector for {entity}")
        self.deposits = {}
        for key, value in opening_deposits.items():
            if not isinstance(key, tuple) or len(key) != 2:
                raise OperatingWageError("deposit keys must be (entity_id, currency)")
            entity, currency = key
            _text(entity, "deposit entity")
            _text(currency, "deposit currency")
            amount = D(str(value))
            if not amount.is_finite() or amount < 0:
                raise OperatingWageError("opening deposits must be finite and non-negative")
            self.deposits[(entity, currency)] = amount
        self.events = {}
        self.outstanding = {}
        self._delivery_claims = set()
        self._claim_contracts = {}

    def _sector(self, entity):
        try:
            return self.sectors[entity]
        except KeyError as exc:
            raise OperatingWageError(f"missing explicit institutional sector for {entity}") from exc

    @staticmethod
    def _balanced(lines):
        debit = sum((x.amount for x in lines if x.side == "D"), D("0"))
        credit = sum((x.amount for x in lines if x.side == "C"), D("0"))
        if debit != credit:
            raise OperatingWageError(f"unbalanced operating event: debit {debit} != credit {credit}")

    def _line(self, account, side, amount, entity, counterparty, instrument, currency):
        return OperatingPosting(account, side, amount, entity, self._sector(entity),
                                counterparty, instrument, currency)

    @staticmethod
    def _identity(position_id, holder, issuer, instrument_id, currency):
        return {
            "register_id": "financial",
            "position_id": position_id,
            "measure": "monetary",
            "unit": currency,
            "currency": currency,
            "valuation_basis": "NOMINAL",
            "holder_id": holder,
            "issuer_id": issuer,
            "instrument_id": instrument_id,
        }

    def _claim_movements(self, event_id, claim_id, worker, employer, currency, amount, evidence_ref):
        instrument = f"WAGE:{claim_id}"
        common = {
            "period_index": None,
            "movement_class": "T",
            "amount": str(amount),
            "evidence_ref": evidence_ref,
            "mirror_group_id": event_id,
            "mirror_policy": "equal",
        }
        return [
            {"movement_id": f"{event_id}:WAGE-RECEIVABLE",
             "identity": self._identity(f"{instrument}:ASSET", worker, employer, instrument, currency),
             **(common | {"mirror_side": "asset_holder"})},
            {"movement_id": f"{event_id}:WAGE-PAYABLE",
             "identity": self._identity(f"{instrument}:LIABILITY", employer, worker, instrument, currency),
             **(common | {"mirror_side": "liability_issuer"})},
        ]

    def accrue_verified_wage(self, *, event_id, delivery: VerifiedLabourDelivery,
                             contract: WageContract, causation_id,
                             labour_register, principal_id):
        _text(event_id, "event_id")
        _text(causation_id, "causation_id")
        if not isinstance(delivery, VerifiedLabourDelivery) or not isinstance(contract, WageContract):
            raise OperatingWageError("typed verified delivery and wage contract are required")
        delivery.validate()
        contract.validate()
        _text(principal_id, "principal_id")
        if causation_id != delivery.delivery_event_id:
            raise OperatingWageError("wage accrual causation must reference the verified delivery event")
        if (delivery.worker_id != contract.worker_id
                or delivery.employer_id != contract.employer_id
                or delivery.period_label != contract.period_label):
            raise OperatingWageError("wage contract does not match verified worker, employer and labour period")
        current_state, current_version = labour_register.state(
            delivery.engagement_id, principal_id=principal_id
        )
        if current_version != delivery.aggregate_version:
            raise OperatingWageError("labour aggregate changed after delivery verification; refresh the verified delivery")
        if not isinstance(current_state, dict) or any((
            current_state.get("status") != "VERIFIED",
            current_state.get("classification") != "paid",
            current_state.get("delivery_event_id") != delivery.delivery_event_id,
            current_state.get("verification_ref") != delivery.verification_ref,
            current_state.get("person_ref") != delivery.worker_id,
            current_state.get("activity_id") != delivery.employer_id,
            current_state.get("period") != delivery.period_label,
            D(str(current_state.get("delivered_hours"))) != delivery.delivered_hours,
        )):
            raise OperatingWageError("current labour aggregate no longer matches verified delivery")
        delivery_key = (delivery.engagement_id, delivery.delivery_event_id)
        if delivery_key in self._delivery_claims:
            raise OperatingWageError("verified labour delivery has already been accrued")
        amount = (delivery.delivered_hours * contract.hourly_rate / contract.minor_unit).quantize(
            D("1"), rounding=ROUND_HALF_UP
        ) * contract.minor_unit
        if amount <= 0:
            raise OperatingWageError("rounded wage amount must be positive")
        claim_id = f"{delivery.engagement_id}:{delivery.delivery_event_id}"
        if event_id in self.events or claim_id in self.outstanding:
            raise OperatingWageError("duplicate operating event or wage claim")
        lines = (
            self._line("wage_expense", "D", amount, contract.employer_id, contract.worker_id, claim_id, contract.currency),
            self._line("wage_payable", "C", amount, contract.employer_id, contract.worker_id, claim_id, contract.currency),
            self._line("wage_receivable", "D", amount, contract.worker_id, contract.employer_id, claim_id, contract.currency),
            self._line("wage_income", "C", amount, contract.worker_id, contract.employer_id, claim_id, contract.currency),
        )
        self._balanced(lines)
        movements = self._claim_movements(event_id, claim_id, contract.worker_id,
                                          contract.employer_id, contract.currency, amount,
                                          delivery.verification_ref)
        for movement in movements:
            movement["period_index"] = contract.period_index
        event = OperatingEvent(
            event_id=event_id, event_type="wage_accrual", period_index=contract.period_index,
            engagement_id=delivery.engagement_id, period_label=delivery.period_label,
            delivered_hours=delivery.delivered_hours,
            hourly_rate=contract.hourly_rate, claim_id=claim_id, worker_id=contract.worker_id, employer_id=contract.employer_id,
            bank_id=self.bank_id, currency=contract.currency, amount=amount,
            causation_id=causation_id, evidence_ref=contract.evidence_ref,
            delivery_event_id=delivery.delivery_event_id,
            delivery_evidence_ref=delivery.delivery_evidence_ref,
            verification_ref=delivery.verification_ref, contract_ref=contract.contract_ref,
            contract_evidence_ref=contract.evidence_ref,
            labour_aggregate_version=delivery.aggregate_version, minor_unit=contract.minor_unit,
            lines=lines, stock_flow_movements=tuple(MappingProxyType(x) for x in movements),
        )
        self.events[event_id] = event
        self.outstanding[claim_id] = amount
        self._delivery_claims.add(delivery_key)
        self._claim_contracts[claim_id] = contract
        return event

    def pay_wage(self, *, event_id, claim_id, amount, causation_id, evidence_ref, period_index):
        _text(event_id, "event_id")
        _text(claim_id, "claim_id")
        _text(causation_id, "causation_id")
        _text(evidence_ref, "evidence_ref")
        if not isinstance(period_index, int) or isinstance(period_index, bool) or period_index < 1:
            raise OperatingWageError("period_index must be a positive integer")
        amount = _positive(amount, "payment amount")
        if event_id in self.events:
            raise OperatingWageError("duplicate operating event ID")
        if claim_id not in self.outstanding:
            raise OperatingWageError("unknown wage claim")
        accrued = self.events[next(k for k, v in self.events.items()
                                   if v.claim_id == claim_id and v.event_type == "wage_accrual")]
        if accrued.currency not in {currency for (entity, currency) in self.deposits if entity == accrued.employer_id}:
            raise OperatingWageError("employer opening deposit account is missing")
        contract = self._claim_contracts[claim_id]
        if period_index < accrued.period_index:
            raise OperatingWageError("wage payment cannot precede its accrual period")
        units = amount / contract.minor_unit
        if units != units.to_integral_value():
            raise OperatingWageError("payment amount must be an exact multiple of the currency minor unit")
        prior_claim_events = [event for event in self.events.values() if event.claim_id == claim_id]
        if not prior_claim_events or causation_id != prior_claim_events[-1].event_id:
            raise OperatingWageError("payment causation must reference the immediately preceding claim event")
        if period_index < prior_claim_events[-1].period_index:
            raise OperatingWageError("payment period cannot move backwards within a wage claim")
        outstanding = self.outstanding[claim_id]
        if amount > outstanding:
            raise OperatingWageError("wage payment exceeds outstanding claim")
        employer_key = (accrued.employer_id, accrued.currency)
        worker_key = (accrued.worker_id, accrued.currency)
        employer_cash = self.deposits.get(employer_key, D("0"))
        if amount > employer_cash:
            raise OperatingWageError("employer deposit balance is insufficient")
        lines = (
            self._line("wage_payable", "D", amount, accrued.employer_id, accrued.worker_id, claim_id, accrued.currency),
            self._line("deposit_asset", "C", amount, accrued.employer_id, self.bank_id, f"DEPOSIT:{accrued.employer_id}:{self.bank_id}", accrued.currency),
            self._line("deposit_liability", "D", amount, self.bank_id, accrued.employer_id, f"DEPOSIT:{accrued.employer_id}:{self.bank_id}", accrued.currency),
            self._line("wage_receivable", "C", amount, accrued.worker_id, accrued.employer_id, claim_id, accrued.currency),
            self._line("deposit_asset", "D", amount, accrued.worker_id, self.bank_id, f"DEPOSIT:{accrued.worker_id}:{self.bank_id}", accrued.currency),
            self._line("deposit_liability", "C", amount, self.bank_id, accrued.worker_id, f"DEPOSIT:{accrued.worker_id}:{self.bank_id}", accrued.currency),
        )
        self._balanced(lines)
        movements = self._claim_movements(event_id, claim_id, accrued.worker_id,
                                          accrued.employer_id, accrued.currency, -amount, evidence_ref)
        for movement in movements:
            movement["period_index"] = period_index
        for entity, delta, side in ((accrued.employer_id, -amount, "employer"),
                                    (accrued.worker_id, amount, "worker")):
            instrument = f"DEPOSIT:{entity}:{self.bank_id}:{accrued.currency}"
            asset = self._identity(f"{instrument}:ASSET", entity, self.bank_id, instrument, accrued.currency)
            liability = self._identity(f"{instrument}:LIABILITY", self.bank_id, entity, instrument, accrued.currency)
            movements.extend([
                {"movement_id": f"{event_id}:DEPOSIT:{side}:ASSET", "identity": asset,
                 "period_index": period_index, "movement_class": "T", "amount": str(delta),
                 "evidence_ref": evidence_ref, "mirror_group_id": f"{event_id}:DEPOSIT:{side}",
                 "mirror_side": "asset_holder", "mirror_policy": "equal"},
                {"movement_id": f"{event_id}:DEPOSIT:{side}:LIABILITY", "identity": liability,
                 "period_index": period_index, "movement_class": "T", "amount": str(delta),
                 "evidence_ref": evidence_ref, "mirror_group_id": f"{event_id}:DEPOSIT:{side}",
                 "mirror_side": "liability_issuer", "mirror_policy": "equal"},
            ])
        event = OperatingEvent(
            event_id=event_id, event_type="wage_payment", period_index=period_index,
            engagement_id=accrued.engagement_id, period_label=accrued.period_label,
            delivered_hours=accrued.delivered_hours,
            hourly_rate=accrued.hourly_rate, claim_id=claim_id, worker_id=accrued.worker_id, employer_id=accrued.employer_id,
            bank_id=self.bank_id, currency=accrued.currency, amount=amount,
            causation_id=causation_id, evidence_ref=evidence_ref,
            delivery_event_id=accrued.delivery_event_id,
            delivery_evidence_ref=accrued.delivery_evidence_ref,
            verification_ref=accrued.verification_ref, contract_ref=accrued.contract_ref,
            contract_evidence_ref=accrued.contract_evidence_ref,
            labour_aggregate_version=accrued.labour_aggregate_version,
            minor_unit=accrued.minor_unit,
            lines=lines, stock_flow_movements=tuple(MappingProxyType(x) for x in movements),
        )
        self.events[event_id] = event
        self.outstanding[claim_id] = outstanding - amount
        self.deposits[employer_key] = employer_cash - amount
        self.deposits[worker_key] = self.deposits.get(worker_key, D("0")) + amount
        return event


def native_financial_operation(events, *, actor_id, authority_ref, effective_at, recorded_at,
                               expected_revision):
    """Build one immutable native financial event group from wage journal events."""
    if not isinstance(events, (tuple, list)) or not events:
        raise OperatingWageError("at least one wage event is required")
    for value, field in ((actor_id, "actor_id"), (authority_ref, "authority_ref"),
                         (effective_at, "effective_at"), (recorded_at, "recorded_at")):
        _text(value, field)
    if any(not isinstance(event, OperatingEvent) for event in events):
        raise OperatingWageError("native wage group requires OperatingEvent values")
    claim_ids = {event.claim_id for event in events}
    if len(claim_ids) != 1:
        raise OperatingWageError("one native financial group may contain only one wage claim")
    from operating_financial_register import wage_stock_flow_movement_specs
    payload_events = [event.to_native_payload() for event in events]
    movements = wage_stock_flow_movement_specs(payload_events)
    claim_id = next(iter(claim_ids))
    native_id = f"WAGE-GROUP:{claim_id}:{events[-1].event_id}"
    envelope = {
        "event_type": "wage.event_group_committed",
        "effective_at": effective_at,
        "recorded_at": recorded_at,
        "actor_id": actor_id,
        "authority_ref": authority_ref,
        "idempotency_key": native_id,
        "payload": {"claim_id": claim_id, "events": payload_events,
                    "stock_flow_movements": movements},
        "stock_flow_movements": movements,
    }
    return {
        "stream_id": "operating-financial",
        "native_event_id": native_id,
        "expected_revision": expected_revision,
        "payload": envelope,
    }
