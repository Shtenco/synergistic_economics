"""Durable operating-wage financial register, separate from GOLD-2A.

This register stores wage claims and settlements under the native durable-register
protocol. It is intentionally not an EntityJournal and does not alter GOLD-2A.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Mapping

from durable_event_register import DurableEventRegister, RegisterError
from register_event_contract import normalize_event_envelope


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
    return number


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
    deposit = f"DEPOSIT:{borrower}:{currency}"
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
                deposit = f"DEPOSIT:{entity}:{currency}"
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
        allowed_sectors = {"H", "NFC", "CB", "CBank", "GOV", "ROW"}
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
            "bank.loan_originated", "bank.loan_principal_repaid"
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
                ("deposit_asset", "C", employer, bank, f"DEPOSIT:{employer}"),
                ("deposit_liability", "D", bank, employer, f"DEPOSIT:{employer}"),
                ("wage_receivable", "C", worker, employer, claim_id),
                ("deposit_asset", "D", worker, bank, f"DEPOSIT:{worker}"),
                ("deposit_liability", "C", bank, worker, f"DEPOSIT:{worker}"),
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
    def _deposit_key(entity_id, currency):
        return f"{_text(entity_id, 'deposit entity')}:{_text(currency, 'deposit currency')}"

    def _reduce_bank_credit(self, state, event):
        payload = event["payload"]
        event_type = event["event_type"]
        loan_id = _text(payload.get("loan_id"), "loan_id")
        borrower = _text(payload.get("borrower_id"), "borrower_id")
        bank = _text(payload.get("bank_id"), "bank_id")
        currency = _text(payload.get("currency"), "currency")
        amount = _decimal(payload.get("amount"), "amount", positive=True)
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
        key = self._deposit_key(borrower, currency)
        account = state["deposits"].get(key)
        if account is None:
            raise OperatingFinancialRegisterError("borrower requires a durable deposit account before bank credit")
        if account["bank_id"] != bank:
            raise OperatingFinancialRegisterError("loan bank differs from borrower's authoritative deposit bank")
        if account["minor_unit"] != str(minor_unit):
            raise OperatingFinancialRegisterError("bank credit minor unit differs from deposit account")
        loan = state["loans"].get(loan_id)
        if event_type == "bank.loan_originated":
            if loan is not None:
                raise OperatingFinancialRegisterError("loan ID already exists")
            state["deposits"][key]["balance"] = str(D(account["balance"]) + amount)
            state["loans"][loan_id] = {
                "loan_id": loan_id, "borrower_id": borrower, "bank_id": bank,
                "currency": currency, "minor_unit": str(minor_unit),
                "original_principal": str(amount), "outstanding_principal": str(amount),
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

    def _reduce_deposit_opening(self, state, event):
        payload = event["payload"]
        entity = _text(payload.get("entity_id"), "deposit entity_id")
        bank = _text(payload.get("bank_id"), "deposit bank_id")
        currency = _text(payload.get("currency"), "deposit currency")
        account_ref = _text(payload.get("account_ref"), "deposit account_ref")
        evidence_ref = _text(payload.get("evidence_ref"), "deposit evidence_ref")
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
        key = self._deposit_key(entity, currency)
        if key in state["deposits"]:
            raise OperatingFinancialRegisterError("deposit account already has an opening record")
        if any(item["account_ref"] == account_ref for item in state["deposits"].values()):
            raise OperatingFinancialRegisterError("deposit account reference already exists")
        state["deposits"][key] = {
            "entity_id": entity, "bank_id": bank, "currency": currency,
            "account_ref": account_ref, "opening_balance": str(balance),
            "balance": str(balance), "minor_unit": str(minor_unit),
            "opening_evidence_ref": evidence_ref,
        }
        return state

    def reduce_event(self, old, event):
        if event["aggregate_id"] != "operating-financial":
            raise OperatingFinancialRegisterError("all operating financial events must use the global financial stream")
        state = old or {"claims": {}, "deposits": {}, "loans": {}}
        state = {"claims": dict(state.get("claims", {})),
                 "deposits": {key: dict(value) for key, value in state.get("deposits", {}).items()},
                 "loans": {key: dict(value) for key, value in state.get("loans", {}).items()}}
        event_type = event["event_type"]
        if event_type == "deposit.account_opened":
            return self._reduce_deposit_opening(state, event)
        if event_type in {"bank.loan_originated", "bank.loan_principal_repaid"}:
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
                employer_key = self._deposit_key(employer, currency)
                worker_key = self._deposit_key(worker, currency)
                employer_account = state["deposits"].get(employer_key)
                worker_account = state["deposits"].get(worker_key)
                if employer_account is None or worker_account is None:
                    raise OperatingFinancialRegisterError("both employer and worker require durable deposit accounts")
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
        elif envelope["event_type"] in {"bank.loan_originated", "bank.loan_principal_repaid"}:
            payload = envelope["payload"]
            expected = bank_credit_stock_flow_movement_specs(
                {"event_id": envelope["idempotency_key"], **payload,
                 "event_type": envelope["event_type"]}
            )
            if envelope.get("stock_flow_movements") != expected:
                raise OperatingFinancialRegisterError("bank credit stock-flow movements differ from canonical mapper")
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
                             expected_revision, minor_unit="0.01"):
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
                    "evidence_ref": evidence_ref,
                },
                "no_stock_flow_effect": "account opening establishes a financial opening stock, not a period transaction movement",
            },
        }
        token = self.prepare(event_id, operation)
        return self.commit(event_id, token)

    def deposit_opening_positions(self, *, period_index, principal_id):
        """Export opening deposit assets/liabilities from the durable account-opening events."""
        if not isinstance(period_index, int) or isinstance(period_index, bool) or period_index != 1:
            raise OperatingFinancialRegisterError("deposit opening positions currently support only the initial period")
        state, _ = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            raise OperatingFinancialRegisterError("operating financial stream has not been initialized")
        from economic_stock_flow_reconciliation import OpeningPosition, PositionIdentity
        positions = []
        for account in state["deposits"].values():
            entity, bank, currency = account["entity_id"], account["bank_id"], account["currency"]
            instrument = f"DEPOSIT:{entity}:{currency}"
            amount = D(account["opening_balance"])
            evidence = account["opening_evidence_ref"]
            asset = PositionIdentity(
                "financial", f"{instrument}:ASSET", "monetary", currency, currency,
                "NOMINAL", entity, bank, instrument,
            )
            liability = PositionIdentity(
                "financial", f"{instrument}:LIABILITY", "monetary", currency, currency,
                "NOMINAL", bank, entity, instrument,
            )
            positions.extend((
                OpeningPosition(asset, period_index, amount, evidence),
                OpeningPosition(liability, period_index, amount, evidence),
            ))
        return tuple(positions)

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
        deposits = sum((
            D(item["balance"]) for item in state.get("deposits", {}).values()
            if item["bank_id"] == bank_id and item["currency"] == currency
        ), D("0"))
        loans = sum((
            D(item["outstanding_principal"]) for item in state.get("loans", {}).values()
            if item["bank_id"] == bank_id and item["currency"] == currency
        ), D("0"))
        return {"bank_id": bank_id, "currency": currency,
                "deposit_liabilities": deposits, "loan_assets": loans,
                "revision": version}

    def claim_state(self, claim_id, *, principal_id):
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            return None, version
        return state["claims"].get(claim_id), version

    def deposit_balance(self, entity_id, currency, *, principal_id):
        state, version = self.state("operating-financial", principal_id=principal_id)
        if state is None:
            raise OperatingFinancialRegisterError("operating financial stream has not been initialized")
        account = state["deposits"].get(self._deposit_key(entity_id, currency))
        if account is None:
            raise OperatingFinancialRegisterError("durable deposit account does not exist")
        return D(account["balance"]), version

    def append_event(self, **kwargs):
        if kwargs.get("event_type") in {"wage.event_group_committed", "deposit.account_opened",
                                        "bank.loan_originated", "bank.loan_principal_repaid"}:
            raise OperatingFinancialRegisterError("operating financial events must commit through the native prepare/commit protocol")
        return super().append_event(**kwargs)
