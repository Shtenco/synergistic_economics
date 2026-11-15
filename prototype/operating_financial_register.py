"""Durable operating-wage financial register, separate from GOLD-2A.

This register stores wage claims and settlements under the native durable-register
protocol. It is intentionally not an EntityJournal and does not alter GOLD-2A.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
import hashlib
import json
from typing import Mapping

from durable_event_register import DurableEventRegister, RegisterError
from register_event_contract import normalize_event_envelope
from institutional_sectors import (
    ALLOWED_SECTOR_CODES, SECTOR_COMMERCIAL_BANKS, SECTOR_CENTRAL_BANK,
)


class OperatingFinancialRegisterError(RegisterError):
    pass


D = Decimal


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise OperatingFinancialRegisterError(f"{field} must be trimmed non-empty text")
    return value


def _decimal(value, field, *, positive=False):
    if isinstance(value, bool):
        raise OperatingFinancialRegisterError(f"{field} must be a finite decimal")
    try:
        number = D(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise OperatingFinancialRegisterError(f"{field} must be a finite decimal") from exc
    if not number.is_finite() or (positive and number <= 0):
        raise OperatingFinancialRegisterError(f"{field} must be finite" + (" and positive" if positive else ""))
    if len(number.as_tuple().digits) > 1024 or abs(number.as_tuple().exponent) > 1024:
        raise OperatingFinancialRegisterError(f"{field} exceeds exact-decimal bounds")
    return number


def _sum_decimal_exact(values):
    with localcontext() as context:
        context.prec = 4096
        return sum(values, D("0"))


def _require_account_active(account, period, label):
    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise OperatingFinancialRegisterError(f"{label} movement period must be a positive integer")
    opening_period = account.get("opening_period_index", 1)
    if not isinstance(opening_period, int) or isinstance(opening_period, bool) or opening_period < 1:
        raise OperatingFinancialRegisterError(f"{label} opening period is invalid")
    if period < opening_period:
        raise OperatingFinancialRegisterError(f"{label} movement precedes account opening period")


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


def bank_credit_stock_flow_movement_specs(event):
    """Canonical SFC movements for deposit-money loan origination/repayment."""
    event_id = _text(event.get("event_id"), "event_id")
    event_type = event.get("event_type")
    loan_id = _text(event.get("loan_id"), "loan_id")
    borrower = _text(event.get("borrower_id"), "borrower_id")
    bank = _text(event.get("bank_id"), "bank_id")
    currency = _text(event.get("currency"), "currency")
    amount = _decimal(event.get("amount"), "amount", positive=True)
    period = event.get("period_index")
    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise OperatingFinancialRegisterError("period_index must be a positive integer")
    if borrower == bank:
        raise OperatingFinancialRegisterError("bank and borrower must be distinct")
    if event_type not in {"bank.loan_originated", "bank.loan_principal_repaid"}:
        raise OperatingFinancialRegisterError("unsupported bank credit event type")
    evidence = _text(event.get("evidence_ref"), "evidence_ref")
    signed = amount if event_type == "bank.loan_originated" else -amount
    loan = f"LOAN:{loan_id}"
    deposit = f"DEPOSIT:{borrower}:{bank}:{currency}"
    return [
        {
            "movement_id": f"{event_id}:BANK-LOAN-ASSET",
            "identity": _identity(f"{loan}:BANK-ASSET", bank, borrower, loan, currency),
            "period_index": period, "movement_class": "T", "amount": str(signed),
            "evidence_ref": evidence, "mirror_group_id": f"{event_id}:LOAN",
            "mirror_side": "asset_holder", "mirror_policy": "equal",
        },
        {
            "movement_id": f"{event_id}:BORROWER-LOAN-LIABILITY",
            "identity": _identity(f"{loan}:BORROWER-LIABILITY", borrower, bank, loan, currency),
            "period_index": period, "movement_class": "T", "amount": str(signed),
            "evidence_ref": evidence, "mirror_group_id": f"{event_id}:LOAN",
            "mirror_side": "liability_issuer", "mirror_policy": "equal",
        },
        {
            "movement_id": f"{event_id}:BORROWER-DEPOSIT-ASSET",
            "identity": _identity(f"{deposit}:ASSET", borrower, bank, deposit, currency),
            "period_index": period, "movement_class": "T", "amount": str(signed),
            "evidence_ref": evidence, "mirror_group_id": f"{event_id}:DEPOSIT",
            "mirror_side": "asset_holder", "mirror_policy": "equal",
        },
        {
            "movement_id": f"{event_id}:BANK-DEPOSIT-LIABILITY",
            "identity": _identity(f"{deposit}:LIABILITY", bank, borrower, deposit, currency),
            "period_index": period, "movement_class": "T", "amount": str(signed),
            "evidence_ref": evidence, "mirror_group_id": f"{event_id}:DEPOSIT",
            "mirror_side": "liability_issuer", "mirror_policy": "equal",
        },
    ]



def interbank_payment_stock_flow_movement_specs(event):
    """Canonical SFC movements for a reserve-settled interbank deposit transfer."""
    event_id = _text(event.get("event_id"), "event_id")
    payment_id = _text(event.get("payment_id"), "payment_id")
    payer = _text(event.get("payer_id"), "payer_id")
    payee = _text(event.get("payee_id"), "payee_id")
    payer_bank = _text(event.get("payer_bank_id"), "payer_bank_id")
    payee_bank = _text(event.get("payee_bank_id"), "payee_bank_id")
    central_bank = _text(event.get("central_bank_id"), "central_bank_id")
    currency = _text(event.get("currency"), "currency")
    amount = _decimal(event.get("amount"), "amount", positive=True)
    period = event.get("period_index")
    evidence = _text(event.get("evidence_ref"), "evidence_ref")
    if event.get("event_type") != "bank.interbank_payment_settled":
        raise OperatingFinancialRegisterError("unsupported interbank payment event type")
    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise OperatingFinancialRegisterError("period_index must be a positive integer")
    if len({payer, payee, payer_bank, payee_bank, central_bank}) != 5:
        raise OperatingFinancialRegisterError("interbank payment parties must be distinct")
    if payer_bank == payee_bank:
        raise OperatingFinancialRegisterError("interbank settlement requires two different banks")
    signed = amount
    movements = []
    def add(suffix, position, holder, issuer, instrument, group, side, value):
        movements.append({
            "movement_id": f"{event_id}:{suffix}",
            "identity": _identity(position, holder, issuer, instrument, currency),
            "period_index": period, "movement_class": "T", "amount": str(value),
            "evidence_ref": evidence, "mirror_group_id": f"{event_id}:{group}",
            "mirror_side": side, "mirror_policy": "equal",
        })
    payer_deposit = f"DEPOSIT:{payer}:{payer_bank}:{currency}"
    payee_deposit = f"DEPOSIT:{payee}:{payee_bank}:{currency}"
    payer_reserve = f"RESERVE:{payer_bank}:{central_bank}:{currency}"
    payee_reserve = f"RESERVE:{payee_bank}:{central_bank}:{currency}"
    # Customer deposit assets and their issuing banks' deposit liabilities.
    add("PAYER-DEPOSIT-ASSET", f"{payer_deposit}:ASSET", payer, payer_bank,
        payer_deposit, "PAYER-DEPOSIT", "asset_holder", -signed)
    add("PAYER-DEPOSIT-LIABILITY", f"{payer_deposit}:LIABILITY", payer_bank, payer,
        payer_deposit, "PAYER-DEPOSIT", "liability_issuer", -signed)
    add("PAYEE-DEPOSIT-ASSET", f"{payee_deposit}:ASSET", payee, payee_bank,
        payee_deposit, "PAYEE-DEPOSIT", "asset_holder", signed)
    add("PAYEE-DEPOSIT-LIABILITY", f"{payee_deposit}:LIABILITY", payee_bank, payee,
        payee_deposit, "PAYEE-DEPOSIT", "liability_issuer", signed)
    # Reserve assets of the two banks and matching central-bank liabilities.
    add("PAYER-RESERVE-ASSET", f"{payer_reserve}:ASSET", payer_bank, central_bank,
        payer_reserve, "PAYER-RESERVE", "asset_holder", -signed)
    add("PAYER-RESERVE-LIABILITY", f"{payer_reserve}:LIABILITY", central_bank, payer_bank,
        payer_reserve, "PAYER-RESERVE", "liability_issuer", -signed)
    add("PAYEE-RESERVE-ASSET", f"{payee_reserve}:ASSET", payee_bank, central_bank,
        payee_reserve, "PAYEE-RESERVE", "asset_holder", signed)
    add("PAYEE-RESERVE-LIABILITY", f"{payee_reserve}:LIABILITY", central_bank, payee_bank,
        payee_reserve, "PAYEE-RESERVE", "liability_issuer", signed)
    return movements


def central_bank_refinancing_movement_specs(event):
    """Canonical SFC movements for central-bank lending to a commercial bank."""
    event_id = _text(event.get("event_id"), "event_id")
    event_type = event.get("event_type")
    facility_id = _text(event.get("facility_id"), "facility_id")
    bank = _text(event.get("bank_id"), "bank_id")
    central_bank = _text(event.get("central_bank_id"), "central_bank_id")
    currency = _text(event.get("currency"), "currency")
    amount = _decimal(event.get("amount"), "amount", positive=True)
    period = event.get("period_index")
    if not isinstance(period, int) or isinstance(period, bool) or period < 1:
        raise OperatingFinancialRegisterError("period_index must be a positive integer")
    if bank == central_bank:
        raise OperatingFinancialRegisterError("commercial bank and central bank must be distinct")
    if event_type not in {
        "central_bank.refinancing_advanced",
        "central_bank.refinancing_principal_repaid",
    }:
        raise OperatingFinancialRegisterError("unsupported central-bank refinancing event type")
    evidence = _text(event.get("evidence_ref"), "evidence_ref")
    signed = amount if event_type == "central_bank.refinancing_advanced" else -amount
    loan = f"CBREFI:{facility_id}"
    reserve = f"RESERVE:{bank}:{central_bank}:{currency}"

    def movement(suffix, position_id, holder, issuer, instrument, mirror_group, side):
        return {
            "movement_id": f"{event_id}:{suffix}",
            "identity": _identity(position_id, holder, issuer, instrument, currency),
            "period_index": period,
            "movement_class": "T",
            "amount": str(signed),
            "evidence_ref": evidence,
            "mirror_group_id": f"{event_id}:{mirror_group}",
            "mirror_side": side,
            "mirror_policy": "equal",
        }

    return [
        movement("CB-LOAN-ASSET", f"{loan}:CB-ASSET", central_bank, bank,
                 loan, "LOAN", "asset_holder"),
        movement("BANK-REFINANCING-LIABILITY", f"{loan}:BANK-LIABILITY", bank,
                 central_bank, loan, "LOAN", "liability_issuer"),
        movement("BANK-RESERVE-ASSET", f"{reserve}:ASSET", bank, central_bank,
                 reserve, "RESERVE", "asset_holder"),
        movement("CB-RESERVE-LIABILITY", f"{reserve}:LIABILITY", central_bank,
                 bank, reserve, "RESERVE", "liability_issuer"),
    ]


def wage_stock_flow_movement_specs(events):
    """Canonical SFC movements for operating wage accrual and payment events."""
    specs = []
    for event in events:
        event_id = _text(event.get("event_id"), "event_id")
        event_type = event.get("event_type")
        claim_id = _text(event.get("claim_id"), "claim_id")
        worker = _text(event.get("worker_id"), "worker_id")
        employer = _text(event.get("employer_id"), "employer_id")
        bank = _text(event.get("bank_id"), "bank_id")
        currency = _text(event.get("currency"), "currency")
        amount = _decimal(event.get("amount"), "amount", positive=True)
        period = event.get("period_index")
        if not isinstance(period, int) or isinstance(period, bool) or period < 1:
            raise OperatingFinancialRegisterError("period_index must be a positive integer")
        if event_type not in {"wage_accrual", "wage_payment"}:
            raise OperatingFinancialRegisterError("unsupported wage subevent type")
        signed = amount if event_type == "wage_accrual" else -amount
        evidence = event.get("verification_ref") if event_type == "wage_accrual" else event.get("evidence_ref")
        evidence = _text(evidence, "movement evidence_ref")
        instrument = f"WAGE:{claim_id}"
        specs.extend([
            {
                "movement_id": f"{event_id}:WAGE-RECEIVABLE",
                "identity": _identity(f"{instrument}:ASSET", worker, employer, instrument, currency),
                "period_index": period, "movement_class": "T", "amount": str(signed),
                "evidence_ref": evidence, "mirror_group_id": event_id,
                "mirror_side": "asset_holder", "mirror_policy": "equal",
            },
            {
                "movement_id": f"{event_id}:WAGE-PAYABLE",
                "identity": _identity(f"{instrument}:LIABILITY", employer, worker, instrument, currency),
                "period_index": period, "movement_class": "T", "amount": str(signed),
                "evidence_ref": evidence, "mirror_group_id": event_id,
                "mirror_side": "liability_issuer", "mirror_policy": "equal",
            },
        ])
        if event_type == "wage_payment":
            for entity, delta, side in ((employer, -amount, "employer"), (worker, amount, "worker")):
                deposit = f"DEPOSIT:{entity}:{bank}:{currency}"
                specs.extend([
                    {
                        "movement_id": f"{event_id}:DEPOSIT:{side}:ASSET",
                        "identity": _identity(f"{deposit}:ASSET", entity, bank, deposit, currency),
                        "period_index": period, "movement_class": "T", "amount": str(delta),
                        "evidence_ref": evidence, "mirror_group_id": f"{event_id}:DEPOSIT:{side}",
                        "mirror_side": "asset_holder", "mirror_policy": "equal",
                    },
                    {
                        "movement_id": f"{event_id}:DEPOSIT:{side}:LIABILITY",
                        "identity": _identity(f"{deposit}:LIABILITY", bank, entity, deposit, currency),
                        "period_index": period, "movement_class": "T", "amount": str(delta),
                        "evidence_ref": evidence, "mirror_group_id": f"{event_id}:DEPOSIT:{side}",
                        "mirror_side": "liability_issuer", "mirror_policy": "equal",
                    },
                ])
    return specs


class OperatingFinancialRegister(DurableEventRegister):
    """Append-only financial subledger for verified wage claims and bank settlement."""

    REGISTER_NAME = "financial"
    read_permission = "financial:read"

    def __init__(self, database_path, *, sectors: Mapping[str, str]):
        if not isinstance(sectors, Mapping):
            raise OperatingFinancialRegisterError("explicit institutional sector mapping is required")
        self.sectors = dict(sectors)
        allowed_sectors = ALLOWED_SECTOR_CODES
        if not self.sectors:
            raise OperatingFinancialRegisterError("at least one explicit institutional sector mapping is required")
        for entity, sector in self.sectors.items():
            _text(entity, "sector entity")
            _text(sector, "institutional sector")
            if sector not in allowed_sectors:
                raise OperatingFinancialRegisterError(f"unsupported institutional sector for {entity}")
        super().__init__(database_path)

    @staticmethod
    def write_permission(event_type):
        return "financial:write" if event_type in {
            "wage.event_group_committed", "deposit.account_opened",
            "bank.loan_originated", "bank.loan_principal_repaid",
            "bank.reserve_account_opened", "bank.interbank_payment_settled",
            "central_bank.refinancing_advanced",
            "central_bank.refinancing_principal_repaid",
        } else "financial:admin"

    def _validate_postings(self, event):
        amount = _decimal(event.get("amount"), "posting amount", positive=True)
        worker = _text(event.get("worker_id"), "worker_id")
        employer = _text(event.get("employer_id"), "employer_id")
        bank = _text(event.get("bank_id"), "bank_id")
        currency = _text(event.get("currency"), "currency")
        claim_id = _text(event.get("claim_id"), "claim_id")
        if worker == employer or bank in {worker, employer}:
            raise OperatingFinancialRegisterError("worker, employer and bank must be distinct entities")
        for entity in (worker, employer, bank):
            if entity not in self.sectors:
                raise OperatingFinancialRegisterError(f"missing explicit institutional sector for {entity}")
        if self.sectors[bank] != SECTOR_COMMERCIAL_BANKS:
            raise OperatingFinancialRegisterError("wage settlement bank must be a configured commercial bank")
        event_type = event.get("event_type")
        if event_type == "wage_accrual":
            expected = [
                ("wage_expense", "D", employer, worker, claim_id),
                ("wage_payable", "C", employer, worker, claim_id),
                ("wage_receivable", "D", worker, employer, claim_id),
                ("wage_income", "C", worker, employer, claim_id),
            ]
        elif event_type == "wage_payment":
            expected = [
                ("wage_payable", "D", employer, worker, claim_id),
                ("deposit_asset", "C", employer, bank, f"DEPOSIT:{employer}:{bank}"),
                ("deposit_liability", "D", bank, employer, f"DEPOSIT:{employer}:{bank}"),
                ("wage_receivable", "C", worker, employer, claim_id),
                ("deposit_asset", "D", worker, bank, f"DEPOSIT:{worker}:{bank}"),
                ("deposit_liability", "C", bank, worker, f"DEPOSIT:{worker}:{bank}"),
            ]
        else:
            raise OperatingFinancialRegisterError("unsupported wage subevent type")
        postings = event.get("postings")
        if not isinstance(postings, list) or len(postings) != len(expected):
            raise OperatingFinancialRegisterError("wage posting count differs from the canonical account template")
        debits = credits = D("0")
        for posting, (account, side, entity, counterparty, instrument) in zip(postings, expected):
            if not isinstance(posting, dict):
                raise OperatingFinancialRegisterError("posting must be an object")
            if (posting.get("account"), posting.get("side"), posting.get("entity_id"),
                posting.get("counterparty_id"), posting.get("instrument_id"), posting.get("currency")) != (
                account, side, entity, counterparty, instrument, currency):
                raise OperatingFinancialRegisterError("posting identity differs from the canonical wage account template")
            if entity not in self.sectors or posting.get("sector") != self.sectors[entity]:
                raise OperatingFinancialRegisterError("posting institutional sector differs from configured entity sector")
            line_amount = _decimal(posting.get("amount"), "posting amount", positive=True)
            if line_amount != amount:
                raise OperatingFinancialRegisterError("all canonical wage postings must equal the subevent amount")
            if side == "D":
                debits += line_amount
            elif side == "C":
                credits += line_amount
            else:
                raise OperatingFinancialRegisterError("posting side must be D or C")
        if debits != credits:
            raise OperatingFinancialRegisterError("wage subevent postings are not balanced")

    def _apply_subevent(self, state, event):
        event_id = _text(event.get("event_id"), "subevent event_id")
        event_type = event.get("event_type")
        claim_id = _text(event.get("claim_id"), "claim_id")
        worker = _text(event.get("worker_id"), "worker_id")
        employer = _text(event.get("employer_id"), "employer_id")
        bank = _text(event.get("bank_id"), "bank_id")
        currency = _text(event.get("currency"), "currency")
        amount = _decimal(event.get("amount"), "amount", positive=True)
        minor_unit = _decimal(event.get("minor_unit"), "minor_unit", positive=True)
        if minor_unit > 1 or minor_unit.as_tuple().exponent > 0:
            raise OperatingFinancialRegisterError("minor_unit must be a positive fraction no greater than one")
        if amount / minor_unit != (amount / minor_unit).to_integral_value():
            raise OperatingFinancialRegisterError("wage amount is not an exact multiple of the currency minor unit")
        period = event.get("period_index")
        if not isinstance(period, int) or isinstance(period, bool) or period < 1:
            raise OperatingFinancialRegisterError("period_index must be a positive integer")
        for field in ("engagement_id", "period_label", "delivery_event_id",
                      "causation_id", "evidence_ref", "delivery_evidence_ref",
                      "verification_ref", "contract_ref", "contract_evidence_ref"):
            _text(event.get(field), field)
        labour_version = event.get("labour_aggregate_version")
        if not isinstance(labour_version, int) or isinstance(labour_version, bool) or labour_version < 1:
            raise OperatingFinancialRegisterError("labour_aggregate_version must be positive")
        engagement_id = _text(event.get("engagement_id"), "engagement_id")
        period_label = _text(event.get("period_label"), "period_label")
        delivery_event_id = _text(event.get("delivery_event_id"), "delivery_event_id")
        if claim_id != f"{engagement_id}:{delivery_event_id}":
            raise OperatingFinancialRegisterError("wage claim ID must bind the engagement and verified delivery event")
        delivered_hours = _decimal(event.get("delivered_hours"), "delivered_hours", positive=True)
        hourly_rate = _decimal(event.get("hourly_rate"), "hourly_rate", positive=True)
        self._validate_postings(event)
        if event.get("event_type") == "wage_accrual":
            calculated = (delivered_hours * hourly_rate / minor_unit).quantize(
                D("1"), rounding=ROUND_HALF_UP
            ) * minor_unit
            if calculated != amount:
                raise OperatingFinancialRegisterError("wage amount differs from delivered hours times contract rate")
        if event_type == "wage_accrual":
            if state is not None:
                raise OperatingFinancialRegisterError("wage claim already has an accrual")
            delivery_id = _text(event.get("delivery_event_id"), "delivery_event_id")
            if event["causation_id"] != delivery_id:
                raise OperatingFinancialRegisterError("wage accrual must causally reference the verified labour delivery")
            return {
                "claim_id": claim_id, "engagement_id": engagement_id, "period_label": period_label,
                "delivered_hours": str(delivered_hours), "hourly_rate": str(hourly_rate),
                "worker_id": worker, "employer_id": employer,
                "bank_id": bank, "currency": currency, "minor_unit": str(minor_unit),
                "original_amount": str(amount), "outstanding_amount": str(amount),
                "last_event_id": event_id, "last_period_index": period,
                "delivery_event_id": delivery_id,
                "delivery_evidence_ref": event["delivery_evidence_ref"],
                "verification_ref": event["verification_ref"],
                "contract_ref": event["contract_ref"],
                "contract_evidence_ref": event["contract_evidence_ref"],
                "labour_aggregate_version": labour_version,
                "status": "OUTSTANDING", "event_ids": [event_id],
            }
        if event_type != "wage_payment" or state is None:
            raise OperatingFinancialRegisterError("wage payment requires an existing accrued claim")
        if (state["claim_id"], state["worker_id"], state["employer_id"], state["bank_id"], state["currency"]) != (
            claim_id, worker, employer, bank, currency):
            raise OperatingFinancialRegisterError("wage payment identity differs from the accrued claim")
        if str(minor_unit) != state["minor_unit"]:
            raise OperatingFinancialRegisterError("wage payment currency minor unit differs from the claim")
        if (event["engagement_id"] != state["engagement_id"]
                or event["period_label"] != state["period_label"]
                or delivered_hours != D(state["delivered_hours"])
                or hourly_rate != D(state["hourly_rate"])
                or event["delivery_event_id"] != state["delivery_event_id"]
                or event["delivery_evidence_ref"] != state["delivery_evidence_ref"]
                or event["verification_ref"] != state["verification_ref"]
                or event["contract_ref"] != state["contract_ref"]
                or event["contract_evidence_ref"] != state["contract_evidence_ref"]
                or labour_version != state["labour_aggregate_version"]):
            raise OperatingFinancialRegisterError("wage payment provenance differs from original accrual")
        if event["causation_id"] != state["last_event_id"]:
            raise OperatingFinancialRegisterError("wage payment causation must reference the immediately preceding claim event")
        if period < state["last_period_index"]:
            raise OperatingFinancialRegisterError("wage payment period cannot move backwards")
        outstanding = D(state["outstanding_amount"])
        if amount > outstanding:
            raise OperatingFinancialRegisterError("wage payment exceeds outstanding claim")
        remaining = outstanding - amount
        return state | {
            "outstanding_amount": str(remaining),
            "last_event_id": event_id,
            "last_period_index": period,
            "status": "PAID" if remaining == 0 else "OUTSTANDING",
            "event_ids": list(state["event_ids"]) + [event_id],
        }

    @staticmethod
    def _deposit_key(entity_id, bank_id, currency):
        return f"{_text(entity_id, 'deposit entity')}:{_text(bank_id, 'deposit bank')}:{_text(currency, 'deposit currency')}"

    def _reduce_bank_credit(self, state, event):
        payload = event["payload"]
        event_type = event["event_type"]
        loan_id = _text(payload.get("loan_id"), "loan_id")
        borrower = _text(payload.get("borrower_id"), "borrower_id")
        bank = _text(payload.get("bank_id"), "bank_id")
        currency = _text(payload.get("currency"), "currency")
        amount_field = "outstanding_principal" if event_type == "bank.loan_opening_recorded" else "amount"
        amount = _decimal(payload.get(amount_field), amount_field, positive=(event_type != "bank.loan_opening_recorded"))
        minor_unit = _decimal(payload.get("minor_unit"), "minor_unit", positive=True)
        period = payload.get("period_index")
        evidence = _text(payload.get("evidence_ref"), "evidence_ref")
        if borrower == bank:
            raise OperatingFinancialRegisterError("bank and borrower must be distinct")
        if minor_unit > 1 or minor_unit.as_tuple().exponent > 0:
            raise OperatingFinancialRegisterError("minor_unit must be a positive fraction no greater than one")
        if amount / minor_unit != (amount / minor_unit).to_integral_value():
            raise OperatingFinancialRegisterError("bank credit amount is not an exact multiple of its minor unit")
        if not isinstance(period, int) or isinstance(period, bool) or period < 1:
            raise OperatingFinancialRegisterError("period_index must be a positive integer")
        for entity in (borrower, bank):
            if entity not in self.sectors:
                raise OperatingFinancialRegisterError(f"missing explicit institutional sector for {entity}")
        if self.sectors[bank] != SECTOR_COMMERCIAL_BANKS:
            raise OperatingFinancialRegisterError("bank credit issuer must be a configured commercial bank")
        key = self._deposit_key(borrower, bank, currency)
        account = state["deposits"].get(key)
        if account is None:
            if any(item["entity_id"] == borrower and item["currency"] == currency
                   for item in state["deposits"].values()):
                raise OperatingFinancialRegisterError("loan bank differs from borrower deposit bank; open an account at the issuing bank first")
            raise OperatingFinancialRegisterError("borrower requires a durable deposit account before bank credit")
        if account["bank_id"] != bank:
            raise OperatingFinancialRegisterError("loan bank differs from borrower's authoritative deposit bank")
        _require_account_active(account, period, "deposit")
        if account["minor_unit"] != str(minor_unit):
            raise OperatingFinancialRegisterError("bank credit minor unit differs from deposit account")
        loan = state["loans"].get(loan_id)
        if event_type == "bank.loan_opening_recorded":
            source_account_ref = _text(payload.get("source_account_ref"), "source_account_ref")
            if account.get("account_ref") != source_account_ref:
                raise OperatingFinancialRegisterError(
                    "pre-existing loan source account reference differs from the borrower's durable deposit account"
                )
            if loan is not None:
                raise OperatingFinancialRegisterError("loan ID already exists")
            original = _decimal(payload.get("original_principal"), "original_principal", positive=True)
            origination_period = payload.get("origination_period_index")
            contract_ref = _text(payload.get("contract_ref"), "contract_ref")
            contract_evidence = _text(payload.get("contract_evidence_ref"), "contract_evidence_ref")
            event_id = _text(event.get("event_id"), "event_id")
            if (not isinstance(origination_period, int) or isinstance(origination_period, bool)
                    or origination_period < 0 or origination_period >= period):
                raise OperatingFinancialRegisterError(
                    "pre-existing loan origination period must precede its opening period"
                )
            if amount < 0 or amount > original:
                raise OperatingFinancialRegisterError(
                    "pre-existing loan outstanding principal must be between zero and original principal"
                )
            if original / minor_unit != (original / minor_unit).to_integral_value():
                raise OperatingFinancialRegisterError(
                    "original loan principal is not an exact multiple of its minor unit"
                )
            if amount / minor_unit != (amount / minor_unit).to_integral_value():
                raise OperatingFinancialRegisterError(
                    "opening loan principal is not an exact multiple of its minor unit"
                )
            if not _text(event.get("no_stock_flow_effect"), "opening no_stock_flow_effect"):
                raise OperatingFinancialRegisterError("pre-existing loan opening requires explicit no-stock-flow attestation")
            state["loans"][loan_id] = {
                "loan_id": loan_id, "borrower_id": borrower, "bank_id": bank,
                "currency": currency, "minor_unit": str(minor_unit),
                "original_principal": str(original), "outstanding_principal": str(amount),
                "origination_period_index": origination_period,
                "opening_period_index": period, "last_event_id": event_id,
                "last_period_index": period,
                "origination_evidence_ref": contract_evidence,
                "opening_evidence_ref": evidence, "contract_ref": contract_ref,
                "contract_evidence_ref": contract_evidence,
                "status": "REPAID" if amount == 0 else "OUTSTANDING",
                "event_ids": [event_id],
            }
            return state
        if event_type == "bank.loan_originated":
            if loan is not None:
                raise OperatingFinancialRegisterError("loan ID already exists")
            state["deposits"][key]["balance"] = str(D(account["balance"]) + amount)
            state["loans"][loan_id] = {
                "loan_id": loan_id, "borrower_id": borrower, "bank_id": bank,
                "currency": currency, "minor_unit": str(minor_unit),
                "original_principal": str(amount), "outstanding_principal": str(amount),
                "origination_period_index": period,
                "last_event_id": event["event_id"], "last_period_index": period,
                "origination_evidence_ref": evidence, "status": "OUTSTANDING",
                "event_ids": [event["event_id"]],
            }
            return state
        if loan is None:
            raise OperatingFinancialRegisterError("principal repayment requires an existing durable loan")
        if (loan["borrower_id"], loan["bank_id"], loan["currency"], loan["minor_unit"]) != (
            borrower, bank, currency, str(minor_unit)):
            raise OperatingFinancialRegisterError("repayment identity differs from the original loan")
        if event["event_id"] in loan["event_ids"]:
            raise OperatingFinancialRegisterError("duplicate loan event ID")
        if payload.get("causation_id") != loan["last_event_id"]:
            raise OperatingFinancialRegisterError("repayment causation must reference the immediately preceding loan event")
        if period < loan["last_period_index"]:
            raise OperatingFinancialRegisterError("loan event period cannot move backwards")
        outstanding = D(loan["outstanding_principal"])
        if amount > outstanding:
            raise OperatingFinancialRegisterError("principal repayment exceeds outstanding loan principal")
        balance = D(account["balance"])
        if amount > balance:
            raise OperatingFinancialRegisterError("insufficient deposit balance for principal repayment")
        remaining = outstanding - amount
        state["deposits"][key]["balance"] = str(balance - amount)
        state["loans"][loan_id] = loan | {
            "outstanding_principal": str(remaining),
            "last_event_id": event["event_id"], "last_period_index": period,
            "status": "REPAID" if remaining == 0 else "OUTSTANDING",
            "event_ids": list(loan["event_ids"]) + [event["event_id"]],
        }
        return state


    @staticmethod
    def _reserve_key(bank_id, central_bank_id, currency):
        return f"{_text(bank_id, 'reserve bank')}:{_text(central_bank_id, 'central bank')}:{_text(currency, 'reserve currency')}"

    def _reduce_reserve_opening(self, state, event):
        payload = event["payload"]
        bank = _text(payload.get("bank_id"), "reserve bank_id")
        central_bank = _text(payload.get("central_bank_id"), "central_bank_id")
        currency = _text(payload.get("currency"), "currency")
        account_ref = _text(payload.get("account_ref"), "reserve account_ref")
        evidence = _text(payload.get("evidence_ref"), "reserve evidence_ref")
        opening_period = payload.get("period_index", 1)
        if not isinstance(opening_period, int) or isinstance(opening_period, bool) or opening_period < 1:
            raise OperatingFinancialRegisterError("reserve opening period_index must be a positive integer")
        balance = _decimal(payload.get("opening_balance"), "reserve opening_balance")
        minor_unit = _decimal(payload.get("minor_unit", "0.01"), "reserve minor_unit", positive=True)
        if bank == central_bank or balance < 0:
            raise OperatingFinancialRegisterError("reserve bank and central bank must differ and opening balance cannot be negative")
        if minor_unit > 1 or minor_unit.as_tuple().exponent > 0:
            raise OperatingFinancialRegisterError("reserve minor_unit must be a positive fraction no greater than one")
        if balance / minor_unit != (balance / minor_unit).to_integral_value():
            raise OperatingFinancialRegisterError("reserve opening balance is not an exact multiple of its minor unit")
        if bank not in self.sectors or self.sectors[bank] != SECTOR_COMMERCIAL_BANKS:
            raise OperatingFinancialRegisterError("reserve account holder must be a configured commercial bank")
        if central_bank not in self.sectors or self.sectors[central_bank] != SECTOR_CENTRAL_BANK:
            raise OperatingFinancialRegisterError("reserve issuer must be an explicitly configured central bank sector")
        key = self._reserve_key(bank, central_bank, currency)
        if key in state["reserves"]:
            raise OperatingFinancialRegisterError("bank reserve account already has an opening record")
        if any(item["account_ref"] == account_ref for item in state["reserves"].values()):
            raise OperatingFinancialRegisterError("reserve account reference already exists")
        state["reserves"][key] = {
            "bank_id": bank, "central_bank_id": central_bank, "currency": currency,
            "account_ref": account_ref, "opening_balance": str(balance),
            "balance": str(balance), "minor_unit": str(minor_unit),
            "opening_evidence_ref": evidence, "opening_period_index": opening_period,
        }
        return state

    def _reduce_interbank_payment(self, state, event):
        p = event["payload"]
        payment_id = _text(p.get("payment_id"), "payment_id")
        payer = _text(p.get("payer_id"), "payer_id")
        payee = _text(p.get("payee_id"), "payee_id")
        payer_bank = _text(p.get("payer_bank_id"), "payer_bank_id")
        payee_bank = _text(p.get("payee_bank_id"), "payee_bank_id")
        central_bank = _text(p.get("central_bank_id"), "central_bank_id")
        currency = _text(p.get("currency"), "currency")
        amount_field = (
            "outstanding_principal"
            if event_type == "central_bank.refinancing_opening_recorded"
            else "amount"
        )
        amount = _decimal(
            p.get(amount_field), amount_field,
            positive=(event_type != "central_bank.refinancing_opening_recorded"),
        )
        minor_unit = _decimal(p.get("minor_unit"), "minor_unit", positive=True)
        period = p.get("period_index")
        evidence = _text(p.get("evidence_ref"), "evidence_ref")
        event_id = _text(event.get("event_id"), "event_id")
        if len({payer, payee, payer_bank, payee_bank, central_bank}) != 5:
            raise OperatingFinancialRegisterError("interbank payment parties must be distinct")
        if payer_bank == payee_bank:
            raise OperatingFinancialRegisterError("interbank settlement requires two different banks")
        if not isinstance(period, int) or isinstance(period, bool) or period < 1:
            raise OperatingFinancialRegisterError("period_index must be a positive integer")
        if minor_unit > 1 or minor_unit.as_tuple().exponent > 0:
            raise OperatingFinancialRegisterError("interbank minor_unit must be a positive fraction no greater than one")
        if amount / minor_unit != (amount / minor_unit).to_integral_value():
            raise OperatingFinancialRegisterError("interbank amount is not an exact multiple of its minor unit")
        if payment_id in state["interbank_payments"]:
            raise OperatingFinancialRegisterError("interbank payment ID already exists")
        for entity in (payer, payee, payer_bank, payee_bank, central_bank):
            if entity not in self.sectors:
                raise OperatingFinancialRegisterError(f"missing explicit institutional sector for {entity}")
        if self.sectors[central_bank] != SECTOR_CENTRAL_BANK:
            raise OperatingFinancialRegisterError("interbank reserve issuer must be a central bank")
        if self.sectors[payer_bank] != SECTOR_COMMERCIAL_BANKS or self.sectors[payee_bank] != SECTOR_COMMERCIAL_BANKS:
            raise OperatingFinancialRegisterError("interbank participants must be commercial banks")
        payer_key = self._deposit_key(payer, payer_bank, currency)
        payee_key = self._deposit_key(payee, payee_bank, currency)
        payer_account = state["deposits"].get(payer_key)
        payee_account = state["deposits"].get(payee_key)
        if payer_account is None or payee_account is None:
            raise OperatingFinancialRegisterError("payer and payee must have durable deposit accounts at their respective banks")
        _require_account_active(payer_account, period, "payer deposit")
        _require_account_active(payee_account, period, "payee deposit")
        if payer_account["minor_unit"] != str(minor_unit) or payee_account["minor_unit"] != str(minor_unit):
            raise OperatingFinancialRegisterError("interbank minor unit differs from deposit account")
        payer_reserve_key = self._reserve_key(payer_bank, central_bank, currency)
        payee_reserve_key = self._reserve_key(payee_bank, central_bank, currency)
        payer_reserve = state["reserves"].get(payer_reserve_key)
        payee_reserve = state["reserves"].get(payee_reserve_key)
        if payer_reserve is None or payee_reserve is None:
            raise OperatingFinancialRegisterError("both banks require reserve accounts at the same central bank")
        _require_account_active(payer_reserve, period, "payer reserve")
        _require_account_active(payee_reserve, period, "payee reserve")
        if payer_reserve["minor_unit"] != str(minor_unit) or payee_reserve["minor_unit"] != str(minor_unit):
            raise OperatingFinancialRegisterError("interbank minor unit differs from reserve account")
        payer_balance = D(payer_account["balance"])
        payer_reserve_balance = D(payer_reserve["balance"])
        if payer_balance < amount:
            raise OperatingFinancialRegisterError("insufficient payer deposit balance for interbank payment")
        if payer_reserve_balance < amount:
            raise OperatingFinancialRegisterError("insufficient payer bank reserves for interbank settlement")
        state["deposits"][payer_key]["balance"] = str(payer_balance - amount)
        state["deposits"][payee_key]["balance"] = str(D(payee_account["balance"]) + amount)
        state["reserves"][payer_reserve_key]["balance"] = str(payer_reserve_balance - amount)
        state["reserves"][payee_reserve_key]["balance"] = str(D(payee_reserve["balance"]) + amount)
        state["interbank_payments"][payment_id] = {
            "payment_id": payment_id, "event_id": event_id, "payer_id": payer,
            "payee_id": payee, "payer_bank_id": payer_bank, "payee_bank_id": payee_bank,
            "central_bank_id": central_bank, "currency": currency, "amount": str(amount),
            "period_index": period, "evidence_ref": evidence, "status": "SETTLED",
        }
        return state

    def _reduce_central_bank_refinancing(self, state, event):
        p = event["payload"]
        event_type = event["event_type"]
        facility_id = _text(p.get("facility_id"), "facility_id")
        bank = _text(p.get("bank_id"), "bank_id")
        central_bank = _text(p.get("central_bank_id"), "central_bank_id")
        currency = _text(p.get("currency"), "currency")
        amount_field = (
            "outstanding_principal"
            if event_type == "central_bank.refinancing_opening_recorded"
            else "amount"
        )
        amount = _decimal(
            p.get(amount_field), amount_field,
            positive=(event_type != "central_bank.refinancing_opening_recorded"),
        )
        minor_unit = _decimal(p.get("minor_unit"), "minor_unit", positive=True)
        period = p.get("period_index")
        evidence = _text(p.get("evidence_ref"), "evidence_ref")
        event_id = _text(event.get("event_id"), "event_id")
        if bank == central_bank:
            raise OperatingFinancialRegisterError("commercial bank and central bank must be distinct")
        if minor_unit > 1 or minor_unit.as_tuple().exponent > 0:
            raise OperatingFinancialRegisterError("refinancing minor_unit must be a positive fraction no greater than one")
        if amount / minor_unit != (amount / minor_unit).to_integral_value():
            raise OperatingFinancialRegisterError("refinancing amount is not an exact multiple of its minor unit")
        if not isinstance(period, int) or isinstance(period, bool) or period < 1:
            raise OperatingFinancialRegisterError("period_index must be a positive integer")
        for entity in (bank, central_bank):
            if entity not in self.sectors:
                raise OperatingFinancialRegisterError(f"missing explicit institutional sector for {entity}")
        if self.sectors[bank] != SECTOR_COMMERCIAL_BANKS:
            raise OperatingFinancialRegisterError("refinancing borrower must be a configured commercial bank")
        if self.sectors[central_bank] != SECTOR_CENTRAL_BANK:
            raise OperatingFinancialRegisterError("refinancing lender must be a configured central bank")
        reserve_key = self._reserve_key(bank, central_bank, currency)
        reserve = state["reserves"].get(reserve_key)
        if reserve is None:
            raise OperatingFinancialRegisterError("commercial bank requires a reserve account at the refinancing central bank")
        _require_account_active(reserve, period, "reserve")
        if reserve["minor_unit"] != str(minor_unit):
            raise OperatingFinancialRegisterError("refinancing minor unit differs from reserve account")
        facility = state["refinancing"].get(facility_id)
        if event_type == "central_bank.refinancing_opening_recorded":
            source_account_ref = _text(p.get("source_account_ref"), "source_account_ref")
            if reserve.get("account_ref") != source_account_ref:
                raise OperatingFinancialRegisterError(
                    "pre-existing refinancing source account reference differs from the bank's durable reserve account"
                )
            if facility is not None:
                raise OperatingFinancialRegisterError("refinancing facility ID already exists")
            original = _decimal(p.get("original_principal"), "original_principal", positive=True)
            origination_period = p.get("origination_period_index")
            contract_ref = _text(p.get("contract_ref"), "contract_ref")
            contract_evidence = _text(p.get("contract_evidence_ref"), "contract_evidence_ref")
            if (not isinstance(origination_period, int) or isinstance(origination_period, bool)
                    or origination_period < 0 or origination_period >= period):
                raise OperatingFinancialRegisterError(
                    "pre-existing refinancing origination period must precede its opening period"
                )
            if amount < 0 or amount > original:
                raise OperatingFinancialRegisterError(
                    "pre-existing refinancing outstanding principal must be between zero and original principal"
                )
            if original / minor_unit != (original / minor_unit).to_integral_value():
                raise OperatingFinancialRegisterError(
                    "original refinancing principal is not an exact multiple of its minor unit"
                )
            if amount / minor_unit != (amount / minor_unit).to_integral_value():
                raise OperatingFinancialRegisterError(
                    "opening refinancing principal is not an exact multiple of its minor unit"
                )
            if not _text(event.get("no_stock_flow_effect"), "opening no_stock_flow_effect"):
                raise OperatingFinancialRegisterError(
                    "pre-existing refinancing opening requires explicit no-stock-flow attestation"
                )
            state["refinancing"][facility_id] = {
                "facility_id": facility_id, "bank_id": bank,
                "central_bank_id": central_bank, "currency": currency,
                "minor_unit": str(minor_unit), "original_principal": str(original),
                "outstanding_principal": str(amount),
                "origination_period_index": origination_period,
                "opening_period_index": period, "last_event_id": event_id,
                "last_period_index": period,
                "origination_evidence_ref": contract_evidence,
                "opening_evidence_ref": evidence, "contract_ref": contract_ref,
                "contract_evidence_ref": contract_evidence,
                "status": "REPAID" if amount == 0 else "OUTSTANDING",
                "event_ids": [event_id],
            }
            return state
        if event_type == "central_bank.refinancing_advanced":
            if facility is not None:
                raise OperatingFinancialRegisterError("refinancing facility ID already exists")
            state["reserves"][reserve_key]["balance"] = str(D(reserve["balance"]) + amount)
            state["refinancing"][facility_id] = {
                "facility_id": facility_id, "bank_id": bank,
                "central_bank_id": central_bank, "currency": currency,
                "minor_unit": str(minor_unit), "original_principal": str(amount),
                "outstanding_principal": str(amount), "origination_period_index": period,
                "last_event_id": event_id,
                "last_period_index": period, "origination_evidence_ref": evidence,
                "status": "OUTSTANDING", "event_ids": [event_id],
            }
            return state
        if facility is None:
            raise OperatingFinancialRegisterError("refinancing repayment requires an existing durable facility")
        if (facility["bank_id"], facility["central_bank_id"], facility["currency"],
            facility["minor_unit"]) != (bank, central_bank, currency, str(minor_unit)):
            raise OperatingFinancialRegisterError("repayment identity differs from the original refinancing facility")
        if event_id in facility["event_ids"]:
            raise OperatingFinancialRegisterError("duplicate refinancing event ID")
        if p.get("causation_id") != facility["last_event_id"]:
            raise OperatingFinancialRegisterError("refinancing repayment causation must reference the immediately preceding facility event")
        if period < facility["last_period_index"]:
            raise OperatingFinancialRegisterError("refinancing event period cannot move backwards")
        outstanding = D(facility["outstanding_principal"])
        if amount > outstanding:
            raise OperatingFinancialRegisterError("refinancing repayment exceeds outstanding principal")
        reserve_balance = D(reserve["balance"])
        if amount > reserve_balance:
            raise OperatingFinancialRegisterError("insufficient bank reserves for central-bank refinancing repayment")
        remaining = outstanding - amount
        state["reserves"][reserve_key]["balance"] = str(reserve_balance - amount)
        state["refinancing"][facility_id] = facility | {
            "outstanding_principal": str(remaining), "last_event_id": event_id,
            "last_period_index": period,
            "status": "REPAID" if remaining == 0 else "OUTSTANDING",
            "event_ids": list(facility["event_ids"]) + [event_id],
        }
        return state

    def _reduce_deposit_opening(self, state, event):
        payload = event["payload"]
        entity = _text(payload.get("entity_id"), "deposit entity_id")
        bank = _text(payload.get("bank_id"), "deposit bank_id")
        currency = _text(payload.get("currency"), "deposit currency")
        account_ref = _text(payload.get("account_ref"), "deposit account_ref")
        evidence_ref = _text(payload.get("evidence_ref"), "deposit evidence_ref")
        opening_period = payload.get("period_index", 1)
        if not isinstance(opening_period, int) or isinstance(opening_period, bool) or opening_period < 1:
            raise OperatingFinancialRegisterError("deposit opening period_index must be a positive integer")
        balance = _decimal(payload.get("opening_balance"), "opening_balance")
        minor_unit = _decimal(payload.get("minor_unit", "0.01"), "deposit minor_unit", positive=True)
        if minor_unit > 1 or minor_unit.as_tuple().exponent > 0:
            raise OperatingFinancialRegisterError("deposit minor_unit must be a positive fraction no greater than one")
        if balance < 0:
            raise OperatingFinancialRegisterError("opening deposit balance cannot be negative")
        if balance / minor_unit != (balance / minor_unit).to_integral_value():
            raise OperatingFinancialRegisterError("opening deposit balance is not an exact multiple of its minor unit")
        if entity == bank:
            raise OperatingFinancialRegisterError("deposit owner and issuing bank must be distinct")
        for participant in (entity, bank):
            if participant not in self.sectors:
                raise OperatingFinancialRegisterError(f"missing explicit institutional sector for {participant}")
        if self.sectors[bank] != SECTOR_COMMERCIAL_BANKS:
            raise OperatingFinancialRegisterError("deposit issuer must be a configured commercial bank")
        key = self._deposit_key(entity, bank, currency)
        if key in state["deposits"]:
            raise OperatingFinancialRegisterError("deposit account already has an opening record")
        if any(item["account_ref"] == account_ref for item in state["deposits"].values()):
            raise OperatingFinancialRegisterError("deposit account reference already exists")
        state["deposits"][key] = {
            "entity_id": entity, "bank_id": bank, "currency": currency,
            "account_ref": account_ref, "opening_balance": str(balance),
            "balance": str(balance), "minor_unit": str(minor_unit),
            "opening_evidence_ref": evidence_ref, "opening_period_index": opening_period,
        }
        return state

    def reduce_event(self, old, event):
        # Reducer arithmetic is part of the financial source of truth. Keep
        # enough precision for every accepted source decimal; never inherit
        # the process-wide Decimal precision (normally only 28 digits).
        with localcontext() as context:
            context.prec = 4096
            return self._reduce_event_exact(old, event)

    def _reduce_event_exact(self, old, event):
        if event["aggregate_id"] != "operating-financial":
            raise OperatingFinancialRegisterError("all operating financial events must use the global financial stream")
        state = old or {"claims": {}, "deposits": {}, "loans": {}, "reserves": {}, "interbank_payments": {}, "refinancing": {}}
        state = {"claims": dict(state.get("claims", {})),
                 "deposits": {key: dict(value) for key, value in state.get("deposits", {}).items()},
                 "loans": {key: dict(value) for key, value in state.get("loans", {}).items()},
                 "reserves": {key: dict(value) for key, value in state.get("reserves", {}).items()},
                 "interbank_payments": dict(state.get("interbank_payments", {})),
                 "refinancing": {key: dict(value) for key, value in state.get("refinancing", {}).items()}}
        event_type = event["event_type"]
        if event_type == "deposit.account_opened":
            return self._reduce_deposit_opening(state, event)
        if event_type == "bank.reserve_account_opened":
            return self._reduce_reserve_opening(state, event)
        if event_type == "bank.interbank_payment_settled":
            return self._reduce_interbank_payment(state, event)
        if event_type in {
            "central_bank.refinancing_advanced",
            "central_bank.refinancing_principal_repaid",
            "central_bank.refinancing_opening_recorded",
        }:
            return self._reduce_central_bank_refinancing(state, event)
        if event_type in {
            "bank.loan_originated", "bank.loan_principal_repaid",
            "bank.loan_opening_recorded",
        }:
            return self._reduce_bank_credit(state, event)
        if event_type != "wage.event_group_committed":
            raise OperatingFinancialRegisterError("unsupported operating financial event type")

        payload = event["payload"]
        claim_id = _text(payload.get("claim_id"), "claim_id")
        events = payload.get("events")
        if not isinstance(events, list) or not events:
            raise OperatingFinancialRegisterError("wage event group must contain a non-empty event list")
        claim_state = state["claims"].get(claim_id)
        seen = set()
        for subevent in events:
            if not isinstance(subevent, dict) or subevent.get("claim_id") != claim_id:
                raise OperatingFinancialRegisterError("wage event group contains a malformed or cross-claim subevent")
            event_id = _text(subevent.get("event_id"), "subevent event_id")
            if event_id in seen or (claim_state is not None and event_id in claim_state["event_ids"]):
                raise OperatingFinancialRegisterError("duplicate wage subevent ID")
            seen.add(event_id)
            if subevent.get("event_type") == "wage_payment":
                employer = _text(subevent.get("employer_id"), "employer_id")
                worker = _text(subevent.get("worker_id"), "worker_id")
                bank = _text(subevent.get("bank_id"), "bank_id")
                currency = _text(subevent.get("currency"), "currency")
                amount = _decimal(subevent.get("amount"), "payment amount", positive=True)
                employer_key = self._deposit_key(employer, bank, currency)
                worker_key = self._deposit_key(worker, bank, currency)
                employer_account = state["deposits"].get(employer_key)
                worker_account = state["deposits"].get(worker_key)
                if employer_account is None or worker_account is None:
                    raise OperatingFinancialRegisterError("both employer and worker require durable deposit accounts")
                _require_account_active(employer_account, subevent.get("period_index"), "employer deposit")
                _require_account_active(worker_account, subevent.get("period_index"), "worker deposit")
                if (employer_account["bank_id"] != bank or worker_account["bank_id"] != bank):
                    raise OperatingFinancialRegisterError("wage payment bank differs from the authoritative deposit accounts")
                if (employer_account["minor_unit"] != str(subevent.get("minor_unit"))
                        or worker_account["minor_unit"] != str(subevent.get("minor_unit"))):
                    raise OperatingFinancialRegisterError("wage payment minor unit differs from the authoritative deposit accounts")
                employer_balance = D(employer_account["balance"])
                worker_balance = D(worker_account["balance"])
                if employer_balance < amount:
                    raise OperatingFinancialRegisterError("insufficient durable employer deposit balance")
                state["deposits"][employer_key]["balance"] = str(employer_balance - amount)
                state["deposits"][worker_key]["balance"] = str(worker_balance + amount)
            claim_state = self._apply_subevent(claim_state, subevent)
        state["claims"][claim_id] = claim_state
        return state

    def prepare(self, txid, operation):
        if not isinstance(operation, dict) or not isinstance(operation.get("payload"), dict):
            raise OperatingFinancialRegisterError("financial participant operation is malformed")
        envelope = normalize_event_envelope("financial", operation["payload"])
        if envelope.get("idempotency_key") != operation.get("native_event_id"):
            raise OperatingFinancialRegisterError("financial native event and idempotency IDs must match")
        if operation.get("stream_id") != "operating-financial":
            raise OperatingFinancialRegisterError("financial operation must target the global operating-financial stream")
        if envelope["event_type"] == "wage.event_group_committed":
            events = envelope["payload"].get("events")
            if not isinstance(events, list) or not events:
                raise OperatingFinancialRegisterError("wage event group must contain subevents")
            expected = wage_stock_flow_movement_specs(events)
            if envelope.get("stock_flow_movements") != expected:
                raise OperatingFinancialRegisterError("financial stock-flow movements differ from canonical wage mapper")
        elif envelope["event_type"] in {
            "bank.loan_opening_recorded",
            "central_bank.refinancing_opening_recorded",
        }:
            if envelope.get("stock_flow_movements") is not None:
                raise OperatingFinancialRegisterError(
                    "pre-existing principal opening must initialize a stock, not invent a transaction movement"
                )
            _text(envelope.get("no_stock_flow_effect"), "opening no_stock_flow_effect")
        elif envelope["event_type"] in {"bank.loan_originated", "bank.loan_principal_repaid"}:
            payload = envelope["payload"]
            expected = bank_credit_stock_flow_movement_specs(
                {"event_id": envelope["idempotency_key"], **payload,
                 "event_type": envelope["event_type"]}
            )
            if envelope.get("stock_flow_movements") != expected:
                raise OperatingFinancialRegisterError("bank credit stock-flow movements differ from canonical mapper")
        elif envelope["event_type"] == "bank.reserve_account_opened":
            if envelope.get("stock_flow_movements") is not None:
                raise OperatingFinancialRegisterError("reserve opening must initialize a stock, not invent a transaction movement")
            _text(envelope.get("no_stock_flow_effect"), "reserve opening no_stock_flow_effect")
        elif envelope["event_type"] == "bank.interbank_payment_settled":
            payload = envelope["payload"]
            expected = interbank_payment_stock_flow_movement_specs(
                {"event_id": envelope["idempotency_key"], **payload,
                 "event_type": envelope["event_type"]}
            )
            if envelope.get("stock_flow_movements") != expected:
                raise OperatingFinancialRegisterError("interbank stock-flow movements differ from canonical mapper")
        elif envelope["event_type"] in {
            "central_bank.refinancing_advanced",
            "central_bank.refinancing_principal_repaid",
        }:
            payload = envelope["payload"]
            expected = central_bank_refinancing_movement_specs(
                {"event_id": envelope["idempotency_key"], **payload,
                 "event_type": envelope["event_type"]}
            )
            if envelope.get("stock_flow_movements") != expected:
                raise OperatingFinancialRegisterError("central-bank refinancing movements differ from canonical mapper")
        elif envelope["event_type"] == "deposit.account_opened":
            if envelope.get("stock_flow_movements") is not None:
                raise OperatingFinancialRegisterError("deposit opening must initialize a stock, not invent a transaction movement")
            _text(envelope.get("no_stock_flow_effect"), "deposit opening no_stock_flow_effect")
        else:
            raise OperatingFinancialRegisterError("unsupported operating financial prepare event")
        try:
            return super().prepare(txid, operation)
        except OperatingFinancialRegisterError:
            raise
        except RegisterError as exc:
            raise OperatingFinancialRegisterError(str(exc)) from exc

    def open_deposit_account(self, *, event_id, entity_id, bank_id, currency,
                             account_ref, opening_balance, evidence_ref,
                             actor_id, authority_ref, effective_at, recorded_at,
                             expected_revision, minor_unit="0.01", period_index=1):
        event_id = _text(event_id, "event_id")
        operation = {
            "stream_id": "operating-financial",
            "native_event_id": event_id,
            "expected_revision": expected_revision,
            "payload": {
                "event_type": "deposit.account_opened",
                "effective_at": effective_at, "recorded_at": recorded_at,
                "actor_id": actor_id, "authority_ref": authority_ref,
                "idempotency_key": event_id,
                "payload": {
                    "entity_id": entity_id, "bank_id": bank_id, "currency": currency,
                    "account_ref": account_ref, "opening_balance": str(_decimal(opening_balance, "opening_balance")),
                    "minor_unit": str(_decimal(minor_unit, "minor_unit", positive=True)),
                    "evidence_ref": evidence_ref, "period_index": period_index,
                },
                "no_stock_flow_effect": "account opening establishes a financial opening stock, not a period transaction movement",
            },
        }
        token = self.prepare(event_id, operation)
        return self.commit(event_id, token)


    def open_bank_reserve_account(self, *, event_id, bank_id, central_bank_id,
                                  currency, account_ref, opening_balance, evidence_ref,
                                  actor_id, authority_ref, effective_at, recorded_at,
                                  expected_revision, minor_unit="0.01", period_index=1):
        event_id = _text(event_id, "event_id")
        operation = {
            "stream_id": "operating-financial", "native_event_id": event_id,
            "expected_revision": expected_revision,
            "payload": {
                "event_type": "bank.reserve_account_opened",
                "effective_at": effective_at, "recorded_at": recorded_at,
                "actor_id": actor_id, "authority_ref": authority_ref,
                "idempotency_key": event_id,
                "payload": {
                    "bank_id": bank_id, "central_bank_id": central_bank_id,
                    "currency": currency, "account_ref": account_ref,
                    "opening_balance": str(_decimal(opening_balance, "opening_balance")),
                    "minor_unit": str(_decimal(minor_unit, "minor_unit", positive=True)),
                    "evidence_ref": evidence_ref, "period_index": period_index,
                },
                "no_stock_flow_effect": "reserve account opening establishes an opening stock, not a period transaction movement",
            },
        }
        token = self.prepare(event_id, operation)
        return self.commit(event_id, token)

    def _credit_facility_opening_positions(self, *, period_index, principal_id, facility_kind):
        """Reconstruct debt openings from immutable originations and historical stock records.

        Ordinary originations in the requested period are zero opening stocks;
        a separately evidenced pre-existing opening record is included at its
        declared opening boundary without creating a cashflow. Prior repayments
        reduce later-period openings, while repayments in the requested period
        affect closing only.
        """
        if not isinstance(period_index, int) or isinstance(period_index, bool) or period_index < 1:
            raise OperatingFinancialRegisterError("opening period_index must be a positive integer")
        if facility_kind not in {"loan", "refinancing"}:
            raise OperatingFinancialRegisterError("unsupported financial facility opening kind")
        if not self.verify():
            raise OperatingFinancialRegisterError("financial source register hash-chain verification failed")
        history = self.history("operating-financial", principal_id=principal_id)
        if not history:
            raise OperatingFinancialRegisterError("operating financial stream has not been initialized")

        if facility_kind == "loan":
            origin_type = "bank.loan_originated"
            opening_type = "bank.loan_opening_recorded"
            repayment_type = "bank.loan_principal_repaid"
            id_field = "loan_id"
        else:
            origin_type = "central_bank.refinancing_advanced"
            opening_type = "central_bank.refinancing_opening_recorded"
            repayment_type = "central_bank.refinancing_principal_repaid"
            id_field = "facility_id"

        facilities = {}
        seen_event_ids = set()
        for row in history:
            event_id = _text(row.get("event_id"), "history.event_id")
            if event_id in seen_event_ids:
                raise OperatingFinancialRegisterError("duplicate event ID in financial source history")
            seen_event_ids.add(event_id)
            event_type = row.get("event_type")
            if event_type not in {origin_type, opening_type, repayment_type}:
                continue
            payload = row.get("payload")
            if not isinstance(payload, Mapping):
                raise OperatingFinancialRegisterError("financial facility history payload must be a mapping")
            event_period = payload.get("period_index")
            if not isinstance(event_period, int) or isinstance(event_period, bool) or event_period < 1:
                raise OperatingFinancialRegisterError("financial facility history period must be a positive integer")
            if event_period > period_index:
                continue
            facility_id = _text(payload.get(id_field), id_field)
            evidence_ref = _text(payload.get("evidence_ref"), "evidence_ref")
            if facility_kind == "loan":
                identity_fields = {
                    "borrower_id": _text(payload.get("borrower_id"), "borrower_id"),
                    "bank_id": _text(payload.get("bank_id"), "bank_id"),
                    "currency": _text(payload.get("currency"), "currency"),
                }
            else:
                identity_fields = {
                    "bank_id": _text(payload.get("bank_id"), "bank_id"),
                    "central_bank_id": _text(payload.get("central_bank_id"), "central_bank_id"),
                    "currency": _text(payload.get("currency"), "currency"),
                }

            if event_type == opening_type:
                if facility_id in facilities:
                    raise OperatingFinancialRegisterError("duplicate facility opening/origination in source history")
                original = _decimal(payload.get("original_principal"), "original_principal", positive=True)
                outstanding = _decimal(payload.get("outstanding_principal"), "outstanding_principal")
                origination_period = payload.get("origination_period_index")
                contract_ref = _text(payload.get("contract_ref"), "contract_ref")
                contract_evidence_ref = _text(payload.get("contract_evidence_ref"), "contract_evidence_ref")
                if (not isinstance(origination_period, int) or isinstance(origination_period, bool)
                        or origination_period < 0 or origination_period >= event_period):
                    raise OperatingFinancialRegisterError("historical facility origination period must precede opening period")
                if outstanding < 0 or outstanding > original:
                    raise OperatingFinancialRegisterError("historical opening principal is outside original principal bounds")
                minor_unit = _decimal(payload.get("minor_unit"), "minor_unit", positive=True)
                if original / minor_unit != (original / minor_unit).to_integral_value():
                    raise OperatingFinancialRegisterError("historical original principal is not a minor-unit multiple")
                if outstanding / minor_unit != (outstanding / minor_unit).to_integral_value():
                    raise OperatingFinancialRegisterError("historical outstanding principal is not a minor-unit multiple")
                facilities[facility_id] = {
                    **identity_fields,
                    "opening_balance": outstanding,
                    "origin_period": origination_period,
                    "opening_period": event_period,
                    "proof_rows": [row],
                    "contract_ref": contract_ref,
                    "contract_evidence_ref": contract_evidence_ref,
                }
                continue

            amount = _decimal(payload.get("amount"), "amount", positive=True)
            if event_type == origin_type:
                if facility_id in facilities:
                    raise OperatingFinancialRegisterError("duplicate facility origination in source history")
                facilities[facility_id] = {
                    **identity_fields,
                    "opening_balance": amount if event_period < period_index else D("0"),
                    "origin_period": event_period,
                    "opening_period": event_period,
                    "proof_rows": [row],
                }
                continue

            facility = facilities.get(facility_id)
            if facility is None:
                raise OperatingFinancialRegisterError("facility repayment precedes its recorded opening/origination")
            if event_period < facility["opening_period"] or event_period < facility["origin_period"]:
                raise OperatingFinancialRegisterError("facility repayment period precedes its recorded opening/origination")
            expected_fields = (
                ("borrower_id", "bank_id", "currency") if facility_kind == "loan"
                else ("bank_id", "central_bank_id", "currency")
            )
            for field in expected_fields:
                if payload.get(field) != facility[field]:
                    raise OperatingFinancialRegisterError("facility repayment identity differs from its opening/origination")
            if event_period < period_index:
                with localcontext() as context:
                    context.prec = 4096
                    facility["opening_balance"] -= amount
                if facility["opening_balance"] < 0:
                    raise OperatingFinancialRegisterError("facility opening balance became negative during history replay")
                facility["proof_rows"].append(row)

        from economic_stock_flow_reconciliation import OpeningPosition, PositionIdentity
        positions = []
        for facility_id, item in sorted(facilities.items()):
            currency = item["currency"]
            proof = [{
                "event_id": row["event_id"],
                "commit_sequence": row["commit_sequence"],
                "payload_sha256": row["payload_sha256"],
                "chain_hash": row["chain_hash"],
                "evidence_ref": row["payload"]["evidence_ref"],
            } for row in item["proof_rows"]]
            proof_digest = hashlib.sha256(
                json.dumps(proof, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            evidence = f"financial-opening-v1:{facility_kind}:{period_index}:{proof_digest}"
            if facility_kind == "loan":
                instrument = f"LOAN:{facility_id}"
                pairs = (
                    (f"{instrument}:BANK-ASSET", item["bank_id"], item["borrower_id"]),
                    (f"{instrument}:BORROWER-LIABILITY", item["borrower_id"], item["bank_id"]),
                )
            else:
                instrument = f"CBREFI:{facility_id}"
                pairs = (
                    (f"{instrument}:CB-ASSET", item["central_bank_id"], item["bank_id"]),
                    (f"{instrument}:BANK-LIABILITY", item["bank_id"], item["central_bank_id"]),
                )
            for position_id, holder, issuer in pairs:
                identity = PositionIdentity(
                    "financial", position_id, "monetary", currency, currency,
                    "NOMINAL", holder, issuer, instrument,
                )
                positions.append(OpeningPosition(
                    period_index, identity, item["opening_balance"], evidence,
                ))
        return tuple(positions)

    def loan_opening_positions(self, *, period_index, principal_id):
        """Export bilateral loan-principal opening positions for one period."""
        return self._credit_facility_opening_positions(
            period_index=period_index, principal_id=principal_id, facility_kind="loan",
        )

    def refinancing_opening_positions(self, *, period_index, principal_id):
        """Export central-bank refinancing principal opening positions for one period."""
        return self._credit_facility_opening_positions(
            period_index=period_index, principal_id=principal_id, facility_kind="refinancing",
        )

    def _account_opening_positions(self, *, period_index, principal_id, account_kind):
        """Reconstruct deposit/reserve openings from opening records and all prior T flows.

        Account balances are shared stocks: loan creation/repayment, wage settlement,
        interbank settlement and refinancing all affect them. Therefore this reducer
        replays the immutable native movement envelopes instead of replaying only
        account-specific events.
        """
        if not isinstance(period_index, int) or isinstance(period_index, bool) or period_index < 1:
            raise OperatingFinancialRegisterError("opening period_index must be a positive integer")
        if account_kind not in {"deposit", "reserve"}:
            raise OperatingFinancialRegisterError("unsupported financial account opening kind")
        if not self.verify():
            raise OperatingFinancialRegisterError("financial source register hash-chain verification failed")
        history = self.history("operating-financial", principal_id=principal_id)
        if not history:
            raise OperatingFinancialRegisterError("operating financial stream has not been initialized")
        state, _ = self.state("operating-financial", principal_id=principal_id)
        all_accounts = state.get("deposits" if account_kind == "deposit" else "reserves", {})
        accounts = {
            key: account for key, account in all_accounts.items()
            if account.get("opening_period_index", 1) <= period_index
        }
        if not accounts:
            return ()

        from economic_stock_flow_reconciliation import OpeningPosition, PositionIdentity

        positions_by_account = {}
        proof_by_account = {}
        opening_event_type = "deposit.account_opened" if account_kind == "deposit" else "bank.reserve_account_opened"
        for key, account in accounts.items():
            if account_kind == "deposit":
                entity, bank, currency = account["entity_id"], account["bank_id"], account["currency"]
                instrument = f"DEPOSIT:{entity}:{bank}:{currency}"
                pairs = (
                    (f"{instrument}:ASSET", entity, bank),
                    (f"{instrument}:LIABILITY", bank, entity),
                )
            else:
                bank, central_bank, currency = account["bank_id"], account["central_bank_id"], account["currency"]
                instrument = f"RESERVE:{bank}:{central_bank}:{currency}"
                pairs = (
                    (f"{instrument}:ASSET", bank, central_bank),
                    (f"{instrument}:LIABILITY", central_bank, bank),
                )
            identities = tuple(PositionIdentity(
                "financial", position_id, "monetary", currency, currency,
                "NOMINAL", holder, issuer, instrument,
            ) for position_id, holder, issuer in pairs)
            positions_by_account[key] = {
                "account": account, "identities": identities,
                "balance": D(account["opening_balance"]),
            }
            proof_by_account[key] = []

        # Bind each opening stock to its actual immutable account-opening event.
        opening_rows = {}
        for row in history:
            if row.get("event_type") != opening_event_type:
                continue
            payload = row.get("payload")
            if not isinstance(payload, Mapping):
                raise OperatingFinancialRegisterError("financial account opening payload must be a mapping")
            if account_kind == "deposit":
                account_key = self._deposit_key(
                    payload.get("entity_id"), payload.get("bank_id"), payload.get("currency"),
                )
            else:
                account_key = self._reserve_key(
                    payload.get("bank_id"), payload.get("central_bank_id"), payload.get("currency"),
                )
            opening_period = payload.get("period_index", 1)
            if not isinstance(opening_period, int) or isinstance(opening_period, bool) or opening_period < 1:
                raise OperatingFinancialRegisterError("financial account opening period must be positive")
            if opening_period > period_index:
                continue
            if account_key not in positions_by_account or account_key in opening_rows:
                raise OperatingFinancialRegisterError("duplicate or unknown financial account opening event")
            if positions_by_account[account_key]["account"].get("opening_period_index", 1) != opening_period:
                raise OperatingFinancialRegisterError("financial account opening period differs from immutable source event")
            opening_rows[account_key] = row
        if set(opening_rows) != set(positions_by_account):
            raise OperatingFinancialRegisterError("durable financial account is missing its opening source event")
        for key, row in opening_rows.items():
            payload = row.get("payload")
            if not isinstance(payload, Mapping):
                raise OperatingFinancialRegisterError("financial account opening payload must be a mapping")
            account = positions_by_account[key]["account"]
            expected_opening = (
                payload.get("opening_balance") if isinstance(payload, Mapping) else None
            )
            expected_evidence = payload.get("evidence_ref") if isinstance(payload, Mapping) else None
            expected_account_ref = payload.get("account_ref") if isinstance(payload, Mapping) else None
            if (
                _decimal(expected_opening, "account opening source balance") != D(account["opening_balance"])
                or expected_evidence != account["opening_evidence_ref"]
                or expected_account_ref != account["account_ref"]
                or str(_decimal(payload.get("minor_unit", "0.01"), "account opening minor_unit", positive=True))
                   != account["minor_unit"]
            ):
                raise OperatingFinancialRegisterError("financial account opening state differs from its immutable source event")
            proof_by_account[key].append(row)

        # Every transaction type is replayed through its canonical movement rows.
        # Filtering is by exact position identity, not by event family, so flows
        # from any supported subsystem update the same shared deposit/reserve stock.
        position_to_account = {}
        for key, item in positions_by_account.items():
            # The account's native balance is the holder-side asset. The mirrored
            # issuer-side liability is a separate SFC position, not a second
            # movement of this same account balance.
            asset_identities = [
                identity for identity in item["identities"]
                if identity.position_id.endswith(":ASSET")
            ]
            if len(asset_identities) != 1:
                raise OperatingFinancialRegisterError("financial account must have exactly one holder-side asset identity")
            identity = asset_identities[0]
            if identity.position_id in position_to_account:
                raise OperatingFinancialRegisterError("duplicate financial account position identity")
            position_to_account[identity.position_id] = key

        seen_sequences = set()
        for row in history:
            sequence = row.get("commit_sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
                raise OperatingFinancialRegisterError("financial history commit_sequence must be positive")
            if sequence in seen_sequences:
                raise OperatingFinancialRegisterError("duplicate financial history commit_sequence")
            seen_sequences.add(sequence)
            envelope_json = row.get("native_envelope_json")
            if not isinstance(envelope_json, str):
                raise OperatingFinancialRegisterError("financial history is missing its immutable native envelope")
            try:
                envelope = json.loads(envelope_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise OperatingFinancialRegisterError("financial native envelope JSON is invalid") from exc
            envelope_digest = hashlib.sha256(envelope_json.encode("utf-8")).hexdigest()
            if envelope_digest != row.get("native_envelope_sha256"):
                raise OperatingFinancialRegisterError("financial native envelope digest mismatch")
            if not isinstance(envelope, Mapping) or envelope.get("event_type") != row.get("event_type"):
                raise OperatingFinancialRegisterError("financial native envelope event type mismatch")
            if envelope.get("payload") != row.get("payload"):
                raise OperatingFinancialRegisterError("financial native envelope payload differs from committed history payload")
            if envelope.get("idempotency_key") != row.get("idempotency_key"):
                raise OperatingFinancialRegisterError("financial native envelope idempotency key differs from committed history")
            for field in ("effective_at", "recorded_at", "actor_id", "authority_ref"):
                if envelope.get(field) != row.get(field):
                    raise OperatingFinancialRegisterError(
                        f"financial native envelope {field} differs from event-chain metadata"
                    )
            movements = envelope.get("stock_flow_movements")
            if movements is None:
                continue
            if not isinstance(movements, list):
                raise OperatingFinancialRegisterError("financial stock-flow movements must be a list")
            touched = set()
            for movement in movements:
                if not isinstance(movement, Mapping):
                    raise OperatingFinancialRegisterError("financial stock-flow movement must be a mapping")
                identity = movement.get("identity")
                if not isinstance(identity, Mapping):
                    raise OperatingFinancialRegisterError("financial stock-flow movement identity is invalid")
                account_key = position_to_account.get(identity.get("position_id"))
                if account_key is None:
                    continue
                expected_identity = next(
                    item for item in positions_by_account[account_key]["identities"]
                    if item.position_id == identity.get("position_id")
                )
                if (
                    identity.get("register_id") != "financial"
                    or identity.get("measure") != "monetary"
                    or identity.get("unit") != expected_identity.unit
                    or identity.get("currency") != expected_identity.currency
                    or identity.get("valuation_basis") != "NOMINAL"
                    or identity.get("holder_id") != expected_identity.holder_id
                    or identity.get("issuer_id") != expected_identity.issuer_id
                    or identity.get("instrument_id") != expected_identity.instrument_id
                ):
                    raise OperatingFinancialRegisterError("financial account movement identity differs from its opening account")
                movement_period = movement.get("period_index")
                if not isinstance(movement_period, int) or isinstance(movement_period, bool) or movement_period < 1:
                    raise OperatingFinancialRegisterError("financial account movement period must be positive")
                opening_period = positions_by_account[account_key]["account"].get("opening_period_index", 1)
                if movement_period < opening_period:
                    raise OperatingFinancialRegisterError("financial account movement predates its opening period")
                if movement.get("movement_class") != "T":
                    raise OperatingFinancialRegisterError("financial account opening replay accepts transaction movements only")
                if movement.get("mirror_policy") != "equal":
                    raise OperatingFinancialRegisterError("financial account opening replay requires equal mirror movements")
                side = movement.get("mirror_side")
                if side not in {"asset_holder", "liability_issuer"}:
                    raise OperatingFinancialRegisterError("financial account movement has an invalid mirror side")
                amount = _decimal(movement.get("amount"), "financial account movement amount")
                # The account is one stock represented by an asset and its
                # mirrored liability. Apply only the account-owner asset side;
                # summing both mirror rows would double every transaction.
                if movement_period < period_index and side == "asset_holder":
                    with localcontext() as context:
                        context.prec = 4096
                        positions_by_account[account_key]["balance"] += amount
                    touched.add(account_key)
            for key in touched:
                proof_by_account[key].append(row)

        result = []
        for key, item in sorted(positions_by_account.items()):
            account = item["account"]
            proof = []
            for row in proof_by_account[key]:
                proof.append({
                    "event_id": row["event_id"],
                    "commit_sequence": row["commit_sequence"],
                    "payload_sha256": row["payload_sha256"],
                    "chain_hash": row["chain_hash"],
                    "native_envelope_sha256": row["native_envelope_sha256"],
                })
            digest = hashlib.sha256(
                json.dumps(proof, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            evidence = f"financial-opening-v1:{account_kind}:{period_index}:{digest}"
            for identity in item["identities"]:
                result.append(OpeningPosition(
                    identity, period_index, item["balance"], evidence,
                ))
        return tuple(result)

    def reserve_opening_positions(self, *, period_index, principal_id):
        """Export reserve openings after replaying every prior reserve-affecting flow."""
        return self._account_opening_positions(
            period_index=period_index, principal_id=principal_id, account_kind="reserve",
        )

    def commit_central_bank_refinancing(self, *, event_id, event_type, facility_id,
                                        bank_id, central_bank_id, currency, amount,
                                        period_index, evidence_ref, actor_id,
                                        authority_ref, effective_at, recorded_at,
                                        expected_revision, minor_unit="0.01",
                                        causation_id=None):
        if event_type not in {
            "central_bank.refinancing_advanced",
            "central_bank.refinancing_principal_repaid",
        }:
            raise OperatingFinancialRegisterError("unsupported central-bank refinancing event type")
        event_id = _text(event_id, "event_id")
        payload = {
            "facility_id": _text(facility_id, "facility_id"),
            "bank_id": _text(bank_id, "bank_id"),
            "central_bank_id": _text(central_bank_id, "central_bank_id"),
            "currency": _text(currency, "currency"),
            "amount": str(_decimal(amount, "amount", positive=True)),
            "minor_unit": str(_decimal(minor_unit, "minor_unit", positive=True)),
            "period_index": period_index,
            "evidence_ref": _text(evidence_ref, "evidence_ref"),
        }
        if causation_id is not None:
            payload["causation_id"] = _text(causation_id, "causation_id")
        envelope = {
            "event_type": event_type, "effective_at": effective_at,
            "recorded_at": recorded_at, "actor_id": actor_id,
            "authority_ref": authority_ref, "idempotency_key": event_id,
            "payload": payload,
            "stock_flow_movements": central_bank_refinancing_movement_specs(
                {"event_id": event_id, **payload, "event_type": event_type}
            ),
        }
        operation = {
            "stream_id": "operating-financial", "native_event_id": event_id,
            "expected_revision": expected_revision, "payload": envelope,
        }
        token = self.prepare(event_id, operation)
        return self.commit(event_id, token)

    def record_existing_refinancing_facility(
        self, *, event_id, facility_id, bank_id, central_bank_id, currency,
        original_principal, outstanding_principal, origination_period_index,
        opening_period_index, source_account_ref, contract_ref, contract_evidence_ref, evidence_ref,
        actor_id, authority_ref, effective_at, recorded_at, expected_revision,
        minor_unit="0.01",
    ):
        """Record a pre-model refinancing liability without issuing new reserves."""
        event_id = _text(event_id, "event_id")
        payload = {
            "facility_id": _text(facility_id, "facility_id"),
            "bank_id": _text(bank_id, "bank_id"),
            "central_bank_id": _text(central_bank_id, "central_bank_id"),
            "currency": _text(currency, "currency"),
            "original_principal": str(_decimal(original_principal, "original_principal", positive=True)),
            "outstanding_principal": str(_decimal(outstanding_principal, "outstanding_principal")),
            "minor_unit": str(_decimal(minor_unit, "minor_unit", positive=True)),
            "origination_period_index": origination_period_index,
            "period_index": opening_period_index,
            "source_account_ref": _text(source_account_ref, "source_account_ref"),
            "contract_ref": _text(contract_ref, "contract_ref"),
            "contract_evidence_ref": _text(contract_evidence_ref, "contract_evidence_ref"),
            "evidence_ref": _text(evidence_ref, "evidence_ref"),
        }
        envelope = {
            "event_type": "central_bank.refinancing_opening_recorded",
            "effective_at": effective_at, "recorded_at": recorded_at,
            "actor_id": actor_id, "authority_ref": authority_ref,
            "idempotency_key": event_id, "payload": payload,
            "stock_flow_movements": None,
            "no_stock_flow_effect": (
                "historical central-bank refinancing opening position; no current-period reserve issuance"
            ),
        }
        operation = {
            "stream_id": "operating-financial", "native_event_id": event_id,
            "expected_revision": expected_revision, "payload": envelope,
        }
        token = self.prepare(event_id, operation)
        return self.commit(event_id, token)

    def refinancing_state(self, facility_id, *, principal_id):
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            return None, version
        return state.get("refinancing", {}).get(facility_id), version

    def settle_interbank_payment(self, *, event_id, payment_id, payer_id, payee_id,
                                 payer_bank_id, payee_bank_id, central_bank_id,
                                 currency, amount, period_index, evidence_ref,
                                 actor_id, authority_ref, effective_at, recorded_at,
                                 expected_revision, minor_unit="0.01"):
        event_id = _text(event_id, "event_id")
        payload = {
            "payment_id": _text(payment_id, "payment_id"),
            "payer_id": _text(payer_id, "payer_id"),
            "payee_id": _text(payee_id, "payee_id"),
            "payer_bank_id": _text(payer_bank_id, "payer_bank_id"),
            "payee_bank_id": _text(payee_bank_id, "payee_bank_id"),
            "central_bank_id": _text(central_bank_id, "central_bank_id"),
            "currency": _text(currency, "currency"),
            "amount": str(_decimal(amount, "amount", positive=True)),
            "minor_unit": str(_decimal(minor_unit, "minor_unit", positive=True)),
            "period_index": period_index,
            "evidence_ref": _text(evidence_ref, "evidence_ref"),
        }
        envelope = {
            "event_type": "bank.interbank_payment_settled",
            "effective_at": effective_at, "recorded_at": recorded_at,
            "actor_id": actor_id, "authority_ref": authority_ref,
            "idempotency_key": event_id, "payload": payload,
            "stock_flow_movements": interbank_payment_stock_flow_movement_specs(
                {"event_id": event_id, **payload,
                 "event_type": "bank.interbank_payment_settled"}
            ),
        }
        operation = {
            "stream_id": "operating-financial", "native_event_id": event_id,
            "expected_revision": expected_revision, "payload": envelope,
        }
        token = self.prepare(event_id, operation)
        return self.commit(event_id, token)

    def interbank_payment_state(self, payment_id, *, principal_id):
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            return None, version
        return state.get("interbank_payments", {}).get(payment_id), version

    def bank_reserve_snapshot(self, bank_id, central_bank_id, currency, *, principal_id):
        key = self._reserve_key(bank_id, central_bank_id, currency)
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None or key not in state.get("reserves", {}):
            raise OperatingFinancialRegisterError("durable bank reserve account does not exist")
        account = state["reserves"][key]
        return {"bank_id": bank_id, "central_bank_id": central_bank_id,
                "currency": currency, "reserve_balance": D(account["balance"]),
                "revision": version}


    def wage_opening_positions(self, *, period_index, principal_id):
        """Reconstruct bilateral wage-claim openings from immutable wage event groups.

        Accruals and settlements in the requested period are excluded from its
        opening balance. A claim first accrued in the requested period is still
        emitted with an explicit zero opening on both mirror sides.
        """
        if not isinstance(period_index, int) or isinstance(period_index, bool) or period_index < 1:
            raise OperatingFinancialRegisterError("opening period_index must be a positive integer")
        if not self.verify():
            raise OperatingFinancialRegisterError("financial source register hash-chain verification failed")
        history = self.history("operating-financial", principal_id=principal_id)
        if not history:
            raise OperatingFinancialRegisterError("operating financial stream has not been initialized")

        from economic_stock_flow_reconciliation import OpeningPosition, PositionIdentity

        claims = {}
        last_sequence = 0
        seen_event_ids = set()
        for row in history:
            sequence = row.get("commit_sequence")
            if not isinstance(sequence, int) or isinstance(sequence, bool) or sequence < 1:
                raise OperatingFinancialRegisterError("financial history commit_sequence must be positive")
            if sequence <= last_sequence:
                raise OperatingFinancialRegisterError("financial history commit_sequence is not strictly increasing")
            last_sequence = sequence
            event_id = _text(row.get("event_id"), "history.event_id")
            if event_id in seen_event_ids:
                raise OperatingFinancialRegisterError("duplicate event ID in financial source history")
            seen_event_ids.add(event_id)

            envelope_json = row.get("native_envelope_json")
            if not isinstance(envelope_json, str):
                raise OperatingFinancialRegisterError("financial history is missing its immutable native envelope")
            try:
                envelope = json.loads(envelope_json)
            except (TypeError, json.JSONDecodeError) as exc:
                raise OperatingFinancialRegisterError("financial native envelope JSON is invalid") from exc
            envelope_digest = hashlib.sha256(envelope_json.encode("utf-8")).hexdigest()
            if envelope_digest != row.get("native_envelope_sha256"):
                raise OperatingFinancialRegisterError("financial native envelope digest mismatch")
            if (
                not isinstance(envelope, Mapping)
                or envelope.get("event_type") != row.get("event_type")
                or envelope.get("payload") != row.get("payload")
                or envelope.get("idempotency_key") != row.get("idempotency_key")
            ):
                raise OperatingFinancialRegisterError("financial native envelope differs from committed history")
            for field in ("effective_at", "recorded_at", "actor_id", "authority_ref"):
                if envelope.get(field) != row.get(field):
                    raise OperatingFinancialRegisterError(
                        f"financial native envelope {field} differs from event-chain metadata"
                    )
            if row.get("event_type") != "wage.event_group_committed":
                continue

            payload = row.get("payload")
            if not isinstance(payload, Mapping):
                raise OperatingFinancialRegisterError("wage history payload must be a mapping")
            events = payload.get("events")
            if not isinstance(events, list) or not events:
                raise OperatingFinancialRegisterError("wage history group must contain a non-empty event list")
            expected_movements = wage_stock_flow_movement_specs(events)
            if envelope.get("stock_flow_movements") != expected_movements:
                raise OperatingFinancialRegisterError("wage history movements differ from canonical mapper")

            group_claim_id = _text(payload.get("claim_id"), "wage history claim_id")
            group_event_ids = set()
            for subevent in events:
                if not isinstance(subevent, Mapping) or subevent.get("claim_id") != group_claim_id:
                    raise OperatingFinancialRegisterError("wage history contains malformed or cross-claim subevent")
                subevent_id = _text(subevent.get("event_id"), "wage subevent event_id")
                if subevent_id in group_event_ids:
                    raise OperatingFinancialRegisterError("duplicate wage subevent ID within event group")
                group_event_ids.add(subevent_id)
                event_type = subevent.get("event_type")
                if event_type not in {"wage_accrual", "wage_payment"}:
                    raise OperatingFinancialRegisterError("unsupported wage history subevent type")
                event_period = subevent.get("period_index")
                if not isinstance(event_period, int) or isinstance(event_period, bool) or event_period < 1:
                    raise OperatingFinancialRegisterError("wage history period must be a positive integer")
                amount = _decimal(subevent.get("amount"), "wage history amount", positive=True)
                if event_period > period_index:
                    continue

                wage_rows = [
                    movement for movement in expected_movements
                    if movement.get("movement_id") in {
                        f"{subevent_id}:WAGE-RECEIVABLE",
                        f"{subevent_id}:WAGE-PAYABLE",
                    }
                ]
                if len(wage_rows) != 2:
                    raise OperatingFinancialRegisterError("wage subevent must map to exactly two bilateral claim rows")
                identities = []
                for movement in wage_rows:
                    identity = movement.get("identity")
                    if not isinstance(identity, Mapping):
                        raise OperatingFinancialRegisterError("wage movement identity is invalid")
                    identities.append(PositionIdentity(
                        identity["register_id"], identity["position_id"], identity["measure"],
                        identity["unit"], identity["currency"], identity["valuation_basis"],
                        identity["holder_id"], identity["issuer_id"], identity["instrument_id"],
                    ))
                if identities[0].instrument_id != identities[1].instrument_id:
                    raise OperatingFinancialRegisterError("wage bilateral movement instruments differ")
                claim = claims.get(group_claim_id)
                if event_type == "wage_accrual":
                    if claim is not None:
                        raise OperatingFinancialRegisterError("duplicate wage accrual in committed source history")
                    opening = amount if event_period < period_index else D("0")
                    claims[group_claim_id] = {
                        "identities": tuple(identities),
                        "balance": opening,
                        "proof": [{
                            "event_id": event_id,
                            "subevent_id": subevent_id,
                            "commit_sequence": sequence,
                            "payload_sha256": row.get("payload_sha256"),
                            "chain_hash": row.get("chain_hash"),
                            "native_envelope_sha256": row.get("native_envelope_sha256"),
                        }],
                    }
                else:
                    if claim is None:
                        raise OperatingFinancialRegisterError("wage payment precedes its accrual in source history")
                    if set(claim["identities"]) != set(identities):
                        raise OperatingFinancialRegisterError("wage payment identity differs from original accrual")
                    if event_period < period_index:
                        if amount > claim["balance"]:
                            raise OperatingFinancialRegisterError("historical wage payment exceeds opening outstanding claim")
                        with localcontext() as context:
                            context.prec = 4096
                            claim["balance"] -= amount
                        claim["proof"].append({
                            "event_id": event_id,
                            "subevent_id": subevent_id,
                            "commit_sequence": sequence,
                            "payload_sha256": row.get("payload_sha256"),
                            "chain_hash": row.get("chain_hash"),
                            "native_envelope_sha256": row.get("native_envelope_sha256"),
                        })

        result = []
        for claim_id, claim in sorted(claims.items()):
            proof = claim["proof"]
            for field in ("payload_sha256", "chain_hash", "native_envelope_sha256"):
                for item in proof:
                    _text(item.get(field), f"wage opening proof {field}")
            digest = hashlib.sha256(
                json.dumps(proof, sort_keys=True, separators=(",", ":")).encode("utf-8")
            ).hexdigest()
            evidence = f"financial-opening-v1:wage:{period_index}:{digest}"
            for identity in claim["identities"]:
                result.append(OpeningPosition(
                    identity, period_index, claim["balance"], evidence,
                ))
        return tuple(result)

    def deposit_opening_positions(self, *, period_index, principal_id):
        """Export deposit openings after replaying all prior deposit-affecting flows."""
        return self._account_opening_positions(
            period_index=period_index, principal_id=principal_id, account_kind="deposit",
        )

    def commit_bank_credit(self, *, event_id, event_type, loan_id, borrower_id,
                           bank_id, currency, amount, period_index, evidence_ref,
                           actor_id, authority_ref, effective_at, recorded_at,
                           expected_revision, minor_unit="0.01", causation_id=None):
        if event_type not in {"bank.loan_originated", "bank.loan_principal_repaid"}:
            raise OperatingFinancialRegisterError("unsupported bank credit event type")
        event_id = _text(event_id, "event_id")
        payload = {
            "loan_id": _text(loan_id, "loan_id"),
            "borrower_id": _text(borrower_id, "borrower_id"),
            "bank_id": _text(bank_id, "bank_id"),
            "currency": _text(currency, "currency"),
            "amount": str(_decimal(amount, "amount", positive=True)),
            "minor_unit": str(_decimal(minor_unit, "minor_unit", positive=True)),
            "period_index": period_index,
            "evidence_ref": _text(evidence_ref, "evidence_ref"),
        }
        if causation_id is not None:
            payload["causation_id"] = _text(causation_id, "causation_id")
        envelope = {
            "event_type": event_type, "effective_at": effective_at,
            "recorded_at": recorded_at, "actor_id": actor_id,
            "authority_ref": authority_ref, "idempotency_key": event_id,
            "payload": payload,
            "stock_flow_movements": bank_credit_stock_flow_movement_specs(
                {"event_id": event_id, **payload, "event_type": event_type}
            ),
        }
        operation = {
            "stream_id": "operating-financial", "native_event_id": event_id,
            "expected_revision": expected_revision, "payload": envelope,
        }
        token = self.prepare(event_id, operation)
        return self.commit(event_id, token)

    def record_existing_bank_loan(
        self, *, event_id, loan_id, borrower_id, bank_id, currency,
        original_principal, outstanding_principal, origination_period_index,
        opening_period_index, source_account_ref, contract_ref, contract_evidence_ref, evidence_ref,
        actor_id, authority_ref, effective_at, recorded_at, expected_revision,
        minor_unit="0.01",
    ):
        """Record a pre-model loan stock without creating a deposit or T-flow."""
        event_id = _text(event_id, "event_id")
        payload = {
            "loan_id": _text(loan_id, "loan_id"),
            "borrower_id": _text(borrower_id, "borrower_id"),
            "bank_id": _text(bank_id, "bank_id"),
            "currency": _text(currency, "currency"),
            "original_principal": str(_decimal(original_principal, "original_principal", positive=True)),
            "outstanding_principal": str(_decimal(outstanding_principal, "outstanding_principal")),
            "minor_unit": str(_decimal(minor_unit, "minor_unit", positive=True)),
            "origination_period_index": origination_period_index,
            "period_index": opening_period_index,
            "source_account_ref": _text(source_account_ref, "source_account_ref"),
            "contract_ref": _text(contract_ref, "contract_ref"),
            "contract_evidence_ref": _text(contract_evidence_ref, "contract_evidence_ref"),
            "evidence_ref": _text(evidence_ref, "evidence_ref"),
        }
        envelope = {
            "event_type": "bank.loan_opening_recorded",
            "effective_at": effective_at, "recorded_at": recorded_at,
            "actor_id": actor_id, "authority_ref": authority_ref,
            "idempotency_key": event_id, "payload": payload,
            "stock_flow_movements": None,
            "no_stock_flow_effect": (
                "historical loan principal opening position; no current-period credit creation or deposit issuance"
            ),
        }
        operation = {
            "stream_id": "operating-financial", "native_event_id": event_id,
            "expected_revision": expected_revision, "payload": envelope,
        }
        token = self.prepare(event_id, operation)
        return self.commit(event_id, token)

    def loan_state(self, loan_id, *, principal_id):
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            return None, version
        return state.get("loans", {}).get(loan_id), version

    def bank_principal_snapshot(self, bank_id, currency, *, principal_id):
        """Aggregate recorded deposit liabilities and loan principal by bank/currency.

        This is a partial balance-sheet view: reserves, capital, accrued interest,
        impairment and off-balance-sheet exposures are intentionally not inferred.
        """
        bank_id = _text(bank_id, "bank_id")
        currency = _text(currency, "currency")
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            raise OperatingFinancialRegisterError("operating financial stream has not been initialized")
        deposits = _sum_decimal_exact(
            D(item["balance"]) for item in state.get("deposits", {}).values()
            if item["bank_id"] == bank_id and item["currency"] == currency
        )
        loans = _sum_decimal_exact(
            D(item["outstanding_principal"]) for item in state.get("loans", {}).values()
            if item["bank_id"] == bank_id and item["currency"] == currency
        )
        reserves = _sum_decimal_exact(
            D(item["balance"]) for item in state.get("reserves", {}).values()
            if item["bank_id"] == bank_id and item["currency"] == currency
        )
        return {
            "bank_id": bank_id, "currency": currency,
            "deposit_liabilities": deposits, "loan_assets": loans,
            "reserve_assets": reserves,
            "reserve_to_deposit_liability_ratio": (
                reserves / deposits if deposits > 0 else None
            ),
            "revision": version,
        }

    def claim_state(self, claim_id, *, principal_id):
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            return None, version
        return state["claims"].get(claim_id), version

    def deposit_balance(self, entity_id, currency, *, principal_id, bank_id=None):
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            raise OperatingFinancialRegisterError("operating financial stream has not been initialized")
        entity_id = _text(entity_id, "deposit entity")
        currency = _text(currency, "deposit currency")
        if bank_id is not None:
            account = state["deposits"].get(self._deposit_key(entity_id, bank_id, currency))
            if account is None:
                raise OperatingFinancialRegisterError("durable deposit account does not exist")
            return D(account["balance"]), version
        matches = [item for item in state["deposits"].values()
                   if item["entity_id"] == entity_id and item["currency"] == currency]
        if not matches:
            raise OperatingFinancialRegisterError("durable deposit account does not exist")
        if len(matches) != 1:
            raise OperatingFinancialRegisterError("deposit balance is ambiguous across banks; specify bank_id")
        return D(matches[0]["balance"]), version

    def append_event(self, **kwargs):
        if kwargs.get("event_type") in {
            "wage.event_group_committed", "deposit.account_opened",
            "bank.loan_originated", "bank.loan_principal_repaid",
            "bank.loan_opening_recorded", "bank.reserve_account_opened",
            "bank.interbank_payment_settled", "central_bank.refinancing_advanced",
            "central_bank.refinancing_principal_repaid",
            "central_bank.refinancing_opening_recorded",
        }:
            raise OperatingFinancialRegisterError("operating financial events must commit through the native prepare/commit protocol")
        return super().append_event(**kwargs)
