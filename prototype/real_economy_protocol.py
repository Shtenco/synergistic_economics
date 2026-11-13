"""Additive Prototype 6 real-economy primitives.

This module is a deterministic, in-memory research reference. It does not
replace the Volume IV EventStore or DoubleEntryLedger, and it is not a
durable/concurrent production inventory service. Domain transitions return
event descriptions for an adapter to persist atomically with aggregate state.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from threading import RLock
from typing import Callable, Mapping
import re


class RealEconomyError(ValueError):
    """Invalid real-economy command or state transition."""


class IdempotencyConflict(RealEconomyError):
    """An idempotency key was reused for a different command."""


def _quantity(value, field_name="quantity") -> Decimal:
    if isinstance(value, bool):
        raise RealEconomyError(f"{field_name} must be a finite decimal")
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise RealEconomyError(f"{field_name} must be a finite decimal") from exc
    if not result.is_finite():
        raise RealEconomyError(f"{field_name} must be finite")
    return result


def _aware(value: datetime, field_name: str) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise RealEconomyError(f"{field_name} must be timezone-aware")
    return value


def _event(event_type: str, aggregate_id: str, version: int,
           idempotency_key: str, payload: Mapping) -> dict:
    event_id = sha256(
        (event_type + "|" + aggregate_id + "|" + idempotency_key).encode("utf-8")
    ).hexdigest()
    return {
        "event_id": event_id,
        "event_type": event_type,
        "aggregate_id": aggregate_id,
        "aggregate_version": version,
        "idempotency_key": idempotency_key,
        "payload": dict(payload),
    }


@dataclass(frozen=True)
class Lot:
    lot_id: str
    product_id: str
    owner_id: str
    custodian_id: str
    location_id: str
    quantity: Decimal
    unit: str
    quality_status: str = "RELEASED"
    reserved_quantity: Decimal = Decimal("0")
    version: int = 1
    authorized_actors: frozenset[str] = frozenset()
    source_lot_id: str | None = None

    @property
    def available_quantity(self) -> Decimal:
        if self.quality_status != "RELEASED":
            return Decimal("0")
        return self.quantity - self.reserved_quantity


@dataclass(frozen=True)
class Reservation:
    reservation_id: str
    lot_id: str
    quantity: Decimal
    remaining_quantity: Decimal
    actor_id: str
    counterparty_id: str
    purpose: str
    expires_at: datetime
    status: str
    version: int
    idempotency_key: str
    request_fingerprint: str


@dataclass(frozen=True)
class CommandReceipt:
    result: object
    events: tuple[dict, ...]


class LotInventory:
    """Single in-memory stock authority for this prototype's lot boundary.

    Custody does not confer authority to reserve or dispose of a lot. The owner
    and explicitly authorized actors may reserve it. Title transfer is outside
    this module and must be represented by the canonical rights/asset model.
    """

    def __init__(self):
        self._lots: dict[str, Lot] = {}
        self._reservations: dict[str, Reservation] = {}
        self._commands: dict[str, tuple[str, CommandReceipt]] = {}
        self._lock = RLock()

    def register_lot(self, lot_id: str, product_id: str, owner_id: str,
                     custodian_id: str, location_id: str, quantity,
                     unit: str, authorized_actors=()) -> CommandReceipt:
        values = (lot_id, product_id, owner_id, custodian_id, location_id, unit)
        if any(not isinstance(v, str) or not v.strip() for v in values):
            raise RealEconomyError("lot identity, parties, location and unit are required")
        qty = _quantity(quantity)
        if qty <= 0:
            raise RealEconomyError("lot quantity must be positive")
        actors = frozenset(authorized_actors)
        if any(not isinstance(x, str) or not x.strip() for x in actors):
            raise RealEconomyError("authorized actor identifiers must be non-empty")
        with self._lock:
            if lot_id in self._lots:
                raise RealEconomyError("duplicate lot identifier")
            lot = Lot(lot_id, product_id, owner_id, custodian_id, location_id,
                      qty, unit, authorized_actors=actors)
            self._lots[lot_id] = lot
            receipt = CommandReceipt(
                lot,
                (_event("inventory_lot_registered", lot_id, 1, "register:" + lot_id,
                        {"product_id": product_id, "owner_id": owner_id,
                         "custodian_id": custodian_id, "location_id": location_id,
                         "quantity": str(qty), "unit": unit}),),
            )
            return receipt

    def get_lot(self, lot_id: str) -> Lot:
        with self._lock:
            try:
                return self._lots[lot_id]
            except KeyError as exc:
                raise RealEconomyError("unknown lot") from exc

    def get_reservation(self, reservation_id: str) -> Reservation:
        with self._lock:
            try:
                return self._reservations[reservation_id]
            except KeyError as exc:
                raise RealEconomyError("unknown reservation") from exc

    def _idempotent(self, key: str, fingerprint: str):
        if not isinstance(key, str) or not key.strip():
            raise RealEconomyError("idempotency key is required")
        prior = self._commands.get(key)
        if prior is None:
            return None
        if prior[0] != fingerprint:
            raise IdempotencyConflict("idempotency key reused for a different command")
        return prior[1]

    def _remember(self, key: str, fingerprint: str, receipt: CommandReceipt):
        self._commands[key] = (fingerprint, receipt)
        return receipt

    def _authorize_reservation_actor(self, reservation: Reservation, actor_id: str):
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise RealEconomyError("reservation actor is required")
        lot = self.get_lot(reservation.lot_id)
        if actor_id not in {reservation.actor_id, lot.owner_id} and actor_id not in lot.authorized_actors:
            raise RealEconomyError("actor is not authorized for this reservation")

    def reserve(self, lot_id: str, reservation_id: str, quantity,
                actor_id: str, counterparty_id: str, purpose: str,
                expires_at: datetime, idempotency_key: str,
                expected_lot_version: int, now: datetime) -> CommandReceipt:
        qty = _quantity(quantity)
        now = _aware(now, "now")
        expires_at = _aware(expires_at, "expires_at")
        if qty <= 0:
            raise RealEconomyError("reservation quantity must be positive")
        if expires_at <= now:
            raise RealEconomyError("reservation expiry must be in the future")
        if any(not isinstance(v, str) or not v.strip()
               for v in (lot_id, reservation_id, actor_id, counterparty_id, purpose)):
            raise RealEconomyError("reservation identifiers and purpose are required")
        fingerprint = sha256(repr((
            lot_id, reservation_id, str(qty), actor_id, counterparty_id,
            purpose, expires_at.isoformat(), expected_lot_version
        )).encode("utf-8")).hexdigest()
        with self._lock:
            prior = self._idempotent(idempotency_key, fingerprint)
            if prior is not None:
                return prior
            lot = self.get_lot(lot_id)
            if lot.version != expected_lot_version:
                raise RealEconomyError("stale lot version; refresh and retry")
            if actor_id != lot.owner_id and actor_id not in lot.authorized_actors:
                raise RealEconomyError("actor is not authorized by the owner")
            if lot.quality_status != "RELEASED":
                raise RealEconomyError("lot is not released for allocation")
            if reservation_id in self._reservations:
                raise RealEconomyError("duplicate reservation identifier")
            if qty > lot.available_quantity:
                raise RealEconomyError("insufficient available lot quantity")
            updated_lot = replace(
                lot, reserved_quantity=lot.reserved_quantity + qty,
                version=lot.version + 1,
            )
            reservation = Reservation(
                reservation_id, lot_id, qty, qty, actor_id, counterparty_id,
                purpose, expires_at, "RESERVED", 1, idempotency_key, fingerprint,
            )
            event = _event(
                "inventory_quantity_reserved", lot_id, updated_lot.version,
                idempotency_key,
                {"reservation_id": reservation_id, "quantity": str(qty),
                 "unit": lot.unit, "actor_id": actor_id,
                 "counterparty_id": counterparty_id, "expires_at": expires_at.isoformat(),
                 "reservation_version": reservation.version},
            )
            self._lots[lot_id] = updated_lot
            self._reservations[reservation_id] = reservation
            return self._remember(
                idempotency_key, fingerprint, CommandReceipt(reservation, (event,))
            )

    def commit(self, reservation_id: str, actor_id: str, authorization_ref: str,
               idempotency_key: str, expected_reservation_version: int,
               now: datetime) -> CommandReceipt:
        now = _aware(now, "now")
        with self._lock:
            reservation = self.get_reservation(reservation_id)
            self._authorize_reservation_actor(reservation, actor_id)
            if not authorization_ref or not authorization_ref.strip():
                raise RealEconomyError("authorized contract/mandate reference is required")
            fingerprint = sha256(repr(("commit", reservation_id, actor_id,
                                       authorization_ref, expected_reservation_version)).encode()).hexdigest()
            prior = self._idempotent(idempotency_key, fingerprint)
            if prior is not None:
                return prior
            if reservation.version != expected_reservation_version:
                raise RealEconomyError("stale reservation version")
            if reservation.status != "RESERVED":
                raise RealEconomyError("only a reserved allocation can be committed")
            lot = self.get_lot(reservation.lot_id)
            if now >= reservation.expires_at:
                updated_lot = replace(
                    lot, reserved_quantity=lot.reserved_quantity - reservation.remaining_quantity,
                    version=lot.version + 1,
                )
                updated_res = replace(
                    reservation, remaining_quantity=Decimal("0"),
                    status="EXPIRED", version=reservation.version + 1,
                )
                event_type = "inventory_reservation_expired"
            else:
                updated_lot = lot
                updated_res = replace(
                    reservation, status="COMMITTED", version=reservation.version + 1,
                )
                event_type = "inventory_reservation_committed"
            event = _event(event_type, reservation_id, updated_res.version,
                           idempotency_key,
                           {"reservation_id": reservation_id, "lot_id": lot.lot_id,
                            "lot_version": updated_lot.version, "actor_id": actor_id,
                            "authorization_ref": authorization_ref,
                            "remaining_quantity": str(updated_res.remaining_quantity)})
            if updated_lot is not lot:
                self._lots[lot.lot_id] = updated_lot
            self._reservations[reservation_id] = updated_res
            receipt = CommandReceipt(updated_res, (event,))
            return self._remember(idempotency_key, fingerprint, receipt)

    def release(self, reservation_id: str, actor_id: str, idempotency_key: str,
                expected_reservation_version: int) -> CommandReceipt:
        with self._lock:
            reservation = self.get_reservation(reservation_id)
            self._authorize_reservation_actor(reservation, actor_id)
            fingerprint = sha256(repr(("release", reservation_id, actor_id,
                                       expected_reservation_version)).encode()).hexdigest()
            prior = self._idempotent(idempotency_key, fingerprint)
            if prior is not None:
                return prior
            if reservation.version != expected_reservation_version:
                raise RealEconomyError("stale reservation version")
            if reservation.status not in ("RESERVED", "COMMITTED"):
                raise RealEconomyError("reservation has no releasable quantity")
            lot = self.get_lot(reservation.lot_id)
            updated_lot = replace(
                lot, reserved_quantity=lot.reserved_quantity - reservation.remaining_quantity,
                version=lot.version + 1,
            )
            updated_res = replace(
                reservation, remaining_quantity=Decimal("0"),
                status="RELEASED", version=reservation.version + 1,
            )
            event = _event("inventory_reservation_released", reservation_id,
                           updated_res.version, idempotency_key,
                           {"reservation_id": reservation_id, "lot_id": lot.lot_id,
                            "lot_version": updated_lot.version, "actor_id": actor_id,
                            "released_quantity": str(reservation.remaining_quantity)})
            self._lots[lot.lot_id] = updated_lot
            self._reservations[reservation_id] = updated_res
            receipt = CommandReceipt(updated_res, (event,))
            return self._remember(idempotency_key, fingerprint, receipt)

    def consume(self, reservation_id: str, actor_id: str, quantity, moved_lot_id: str,
                destination_location: str, new_custodian_id: str,
                idempotency_key: str, expected_reservation_version: int) -> CommandReceipt:
        qty = _quantity(quantity)
        if qty <= 0:
            raise RealEconomyError("consumed quantity must be positive")
        if not moved_lot_id or not destination_location or not new_custodian_id:
            raise RealEconomyError("moved lot id, destination and new custodian are required")
        with self._lock:
            reservation = self.get_reservation(reservation_id)
            fingerprint = sha256(repr((
                "consume", reservation_id, actor_id, str(qty), moved_lot_id,
                destination_location, new_custodian_id, expected_reservation_version
            )).encode()).hexdigest()
            prior = self._idempotent(idempotency_key, fingerprint)
            if prior is not None:
                return prior
            self._authorize_reservation_actor(reservation, actor_id)
            if reservation.version != expected_reservation_version:
                raise RealEconomyError("stale reservation version")
            if reservation.status != "COMMITTED":
                raise RealEconomyError("only a committed reservation can be consumed")
            if moved_lot_id in self._lots:
                raise RealEconomyError("duplicate moved lot identifier")
            if qty > reservation.remaining_quantity:
                raise RealEconomyError("consumption exceeds committed reservation")
            lot = self.get_lot(reservation.lot_id)
            updated_lot = replace(
                lot, quantity=lot.quantity - qty,
                reserved_quantity=lot.reserved_quantity - qty,
                version=lot.version + 1,
            )
            moved_lot = Lot(
                lot_id=moved_lot_id, product_id=lot.product_id,
                owner_id=lot.owner_id, custodian_id=new_custodian_id,
                location_id=destination_location, quantity=qty, unit=lot.unit,
                quality_status=lot.quality_status,
                authorized_actors=lot.authorized_actors,
                source_lot_id=lot.lot_id,
            )
            remaining = reservation.remaining_quantity - qty
            updated_res = replace(
                reservation, remaining_quantity=remaining,
                status="CONSUMED" if remaining == 0 else "COMMITTED",
                version=reservation.version + 1,
            )
            event = _event(
                "inventory_quantity_moved", lot.lot_id, updated_lot.version,
                idempotency_key,
                {"reservation_id": reservation_id, "actor_id": actor_id,
                 "moved_lot_id": moved_lot_id,
                 "quantity": str(qty), "unit": lot.unit,
                 "from_location": lot.location_id, "to_location": destination_location,
                 "from_custodian": lot.custodian_id, "to_custodian": new_custodian_id,
                 "lot_version": updated_lot.version,
                 "reservation_version": updated_res.version,
                 "owner_id_unchanged": lot.owner_id},
            )
            self._lots[lot.lot_id] = updated_lot
            self._lots[moved_lot_id] = moved_lot
            self._reservations[reservation_id] = updated_res
            receipt = CommandReceipt(
                {"reservation": updated_res, "source_lot": updated_lot,
                 "moved_lot": moved_lot}, (event,)
            )
            return self._remember(idempotency_key, fingerprint, receipt)

    def quarantine(self, lot_id: str, actor_id: str, idempotency_key: str,
                   expected_lot_version: int, reason: str) -> CommandReceipt:
        if not reason or not reason.strip():
            raise RealEconomyError("quarantine reason is required")
        fingerprint = sha256(repr(("quarantine", lot_id, actor_id, expected_lot_version, reason)).encode()).hexdigest()
        with self._lock:
            prior = self._idempotent(idempotency_key, fingerprint)
            if prior is not None:
                return prior
            lot = self.get_lot(lot_id)
            if not isinstance(actor_id, str) or not actor_id.strip():
                raise RealEconomyError("quarantine actor is required")
            if actor_id != lot.owner_id and actor_id not in lot.authorized_actors:
                raise RealEconomyError("actor is not authorized to quarantine this lot")
            if lot.version != expected_lot_version:
                raise RealEconomyError("stale lot version")
            if lot.quality_status != "RELEASED":
                raise RealEconomyError("lot is already restricted")
            if lot.reserved_quantity > 0:
                raise RealEconomyError("release active reservations before quarantine")
            updated = replace(lot, quality_status="QUARANTINED", version=lot.version + 1)
            event = _event("inventory_lot_quarantined", lot_id, updated.version,
                           idempotency_key, {"actor_id": actor_id, "reason": reason,
                                             "quality_status": "QUARANTINED"})
            self._lots[lot_id] = updated
            receipt = CommandReceipt(updated, (event,))
            return self._remember(idempotency_key, fingerprint, receipt)

    def assert_invariants(self) -> None:
        with self._lock:
            reserved_by_lot = {lot_id: Decimal("0") for lot_id in self._lots}
            for reservation in self._reservations.values():
                if reservation.remaining_quantity < 0:
                    raise RealEconomyError("negative reservation remainder")
                if reservation.status in ("RESERVED", "COMMITTED"):
                    reserved_by_lot[reservation.lot_id] += reservation.remaining_quantity
                elif reservation.remaining_quantity != 0:
                    raise RealEconomyError("closed reservation retains quantity")
            for lot_id, lot in self._lots.items():
                if lot.quantity < 0 or lot.reserved_quantity < 0:
                    raise RealEconomyError("negative physical stock or reservation")
                if lot.reserved_quantity > lot.quantity:
                    raise RealEconomyError("reserved quantity exceeds on-hand stock")
                if lot.reserved_quantity != reserved_by_lot[lot_id]:
                    raise RealEconomyError("lot reservation total does not reconcile")
                if lot.quality_status == "QUARANTINED" and lot.available_quantity != 0:
                    raise RealEconomyError("quarantined lot exposes available stock")


@dataclass(frozen=True)
class ClaimProfile:
    """Read-only typed projection of the canonical Volume IV Claim entity."""
    claim_id: str
    claimant_id: str
    obligor_id: str
    contract_id: str
    obligation_id: str
    claim_type: str
    status: str
    quantity: Decimal | None = None
    unit: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    transferable: bool = False

    @classmethod
    def from_canonical_claim(cls, claim: Mapping) -> "ClaimProfile":
        required = ("claim_id", "claimant_id", "obligor_id", "contract_id",
                    "obligation_id", "claim_type", "status")
        if not isinstance(claim, Mapping) or any(
            not isinstance(claim.get(k), str) or not claim.get(k).strip()
            for k in required
        ):
            raise RealEconomyError("canonical claim is missing required identity fields")
        quantity = None if claim.get("quantity") is None else _quantity(claim["quantity"], "claim quantity")
        amount = None if claim.get("amount") is None else _quantity(claim["amount"], "claim amount")
        if quantity is not None and quantity <= 0:
            raise RealEconomyError("claim quantity must be positive")
        if amount is not None and amount < 0:
            raise RealEconomyError("claim amount cannot be negative")
        if quantity is not None and (not isinstance(claim.get("unit"), str) or not claim.get("unit").strip()):
            raise RealEconomyError("quantified claim requires a unit")
        if amount is not None and (not isinstance(claim.get("currency"), str) or not claim.get("currency").strip()):
            raise RealEconomyError("monetary claim requires a currency")
        transferable = claim.get("transferable", False)
        if not isinstance(transferable, bool):
            raise RealEconomyError("transferability must be explicit boolean")
        return cls(
            *(claim[k] for k in required),
            quantity=quantity, unit=claim.get("unit"),
            amount=amount, currency=claim.get("currency"),
            transferable=transferable,
        )


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    subject_ref: str
    proposition_type: str
    issuer_id: str
    evidence_type: str
    content_digest: str
    observed_at: datetime
    valid_until: datetime | None = None
    credential_ref: str | None = None

    def __post_init__(self):
        if any(not isinstance(value, str) or not value.strip() for value in (
            self.evidence_id, self.subject_ref, self.proposition_type,
            self.issuer_id, self.evidence_type
        )):
            raise RealEconomyError("evidence identity, subject, proposition, issuer and type are required")
        if not isinstance(self.observed_at, datetime) or self.observed_at.tzinfo is None or self.observed_at.utcoffset() is None:
            raise RealEconomyError("evidence observed_at must be timezone-aware")
        if self.valid_until is not None and (
            not isinstance(self.valid_until, datetime) or self.valid_until.tzinfo is None
            or self.valid_until.utcoffset() is None
        ):
            raise RealEconomyError("evidence valid_until must be timezone-aware")


@dataclass(frozen=True)
class VerificationPolicy:
    policy_id: str
    version: str
    proposition_type: str
    accepted_evidence_types: frozenset[str]
    trusted_issuers: frozenset[str]
    max_age: timedelta
    require_issuer_authentication: bool = True

    def __post_init__(self):
        if not all((self.policy_id, self.version, self.proposition_type)):
            raise RealEconomyError("verification policy identity is required")
        if not self.accepted_evidence_types or not self.trusted_issuers:
            raise RealEconomyError("policy must declare evidence types and trusted issuers")
        if not isinstance(self.max_age, timedelta) or self.max_age < timedelta(0):
            raise RealEconomyError("maximum evidence age must be a non-negative timedelta")
        if not isinstance(self.require_issuer_authentication, bool):
            raise RealEconomyError("issuer authentication requirement must be boolean")


@dataclass(frozen=True)
class VerificationDecision:
    evidence_id: str
    policy_id: str
    policy_version: str
    result: str
    reasons: tuple[str, ...]


def evaluate_evidence(
    evidence: EvidenceRecord,
    policy: VerificationPolicy,
    observed_at: datetime,
    expected_subject_ref: str,
    payload: bytes | None,
    issuer_verifier: Callable[[EvidenceRecord], bool | None] | None = None,
) -> VerificationDecision:
    """Evaluate one proposition; never infer universal truth from a credential.

    issuer_verifier must perform the actual signature/credential/status checks.
    None means the verifier could not reach a decision. Payload bytes are
    required to check the declared SHA-256 content digest.
    """
    observed_at = _aware(observed_at, "observed_at")
    reasons = []
    if evidence.subject_ref != expected_subject_ref:
        reasons.append("subject_mismatch")
    if evidence.proposition_type != policy.proposition_type:
        reasons.append("proposition_type_mismatch")
    if evidence.evidence_type not in policy.accepted_evidence_types:
        reasons.append("evidence_type_not_allowed")
    if evidence.issuer_id not in policy.trusted_issuers:
        reasons.append("issuer_not_trusted")
    if not isinstance(evidence.observed_at, datetime) or evidence.observed_at.tzinfo is None or evidence.observed_at.utcoffset() is None:
        reasons.append("evidence_time_not_timezone_aware")
    elif evidence.observed_at > observed_at:
        reasons.append("evidence_time_in_future")
    elif observed_at - evidence.observed_at > policy.max_age:
        reasons.append("evidence_too_old")
    if evidence.valid_until is not None:
        if not isinstance(evidence.valid_until, datetime) or evidence.valid_until.tzinfo is None or evidence.valid_until.utcoffset() is None:
            reasons.append("valid_until_not_timezone_aware")
        elif observed_at >= evidence.valid_until:
            reasons.append("evidence_expired")
    if not isinstance(evidence.content_digest, str) or not re.fullmatch(r"[0-9a-f]{64}", evidence.content_digest):
        reasons.append("invalid_sha256_digest")
    elif not isinstance(payload, bytes):
        reasons.append("payload_not_available_for_integrity_check")
    elif sha256(payload).hexdigest() != evidence.content_digest:
        reasons.append("payload_digest_mismatch")

    auth_result = None
    if policy.require_issuer_authentication:
        if issuer_verifier is None:
            reasons.append("issuer_authentication_not_performed")
        else:
            try:
                auth_result = issuer_verifier(evidence)
            except Exception:
                auth_result = False
            if auth_result is False:
                reasons.append("issuer_authentication_failed")
            elif auth_result is None or not isinstance(auth_result, bool):
                reasons.append("issuer_authentication_indeterminate")

    hard_failures = {
        "proposition_type_mismatch", "evidence_type_not_allowed",
        "issuer_not_trusted", "subject_mismatch", "evidence_time_not_timezone_aware",
        "evidence_time_in_future", "evidence_too_old", "valid_until_not_timezone_aware",
        "evidence_expired", "invalid_sha256_digest", "payload_digest_mismatch",
        "issuer_authentication_failed",
    }
    if any(reason in hard_failures for reason in reasons):
        result = "REJECTED"
    elif reasons:
        result = "INDETERMINATE"
    else:
        result = "ACCEPTED"
    return VerificationDecision(
        evidence.evidence_id, policy.policy_id, policy.version, result, tuple(reasons)
    )
