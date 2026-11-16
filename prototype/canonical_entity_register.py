"""Durable, tenant-scoped canonical economic entity register.

Economic identity and institutional-sector membership are authoritative here.
Spatial systems may consume verified snapshots but cannot create legal title,
ownership, balances, prices, credit or settlement facts.

Every domain event is Ed25519-attested by a tenant-scoped authority key. The
register's local hash chain detects storage tampering; the external signature
proves the event was authorized by a configured issuer key. These are distinct
controls and both are required.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Protocol

from durable_event_register import (
    DurableEventRegister,
    RegisterError,
    canonical_json,
    required_text,
    utc_timestamp,
)


class EconomicEntityRegisterError(RegisterError):
    """Canonical economic entity register validation or authority failure."""


ENTITY_KINDS = frozenset({
    "company", "sole_proprietor", "household", "bank", "government_unit",
    "cooperative", "non_profit", "other",
})
SECTORS = frozenset({"H", "NFC", "CB", "CBank", "GOV", "ROW"})
LIFECYCLE = frozenset({"ACTIVE", "SUSPENDED", "RETIRED"})
DOMAIN_EVENTS = frozenset({
    "entity.registered", "entity.updated", "entity.external_reference_added",
    "entity.sector_changed", "entity.suspended", "entity.reactivated", "entity.retired",
})
ATTESTATION_FIELDS = frozenset({
    "algorithm", "key_id", "issuer", "signed_at", "signature", "scope",
})


def _parse_utc(value: str, field: str) -> datetime:
    utc_timestamp(value, field)
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc)


def _entity_aggregate_id(tenant_id: str, entity_id: str) -> str:
    return f"{tenant_id}::{entity_id}"


def entity_event_signing_document(
    *,
    event_id: str,
    event_type: str,
    aggregate_id: str,
    effective_at: str,
    recorded_at: str,
    actor_id: str,
    authority_ref: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Canonical document external authority signers must sign (attestation excluded)."""
    unsigned_payload = {key: value for key, value in payload.items()
                        if key != "authority_attestation"}
    return {
        "schema_id": "synergy.economic.entity-event",
        "schema_version": 1,
        "event_id": event_id,
        "event_type": event_type,
        "aggregate_id": aggregate_id,
        "effective_at": effective_at,
        "recorded_at": recorded_at,
        "actor_id": actor_id,
        "authority_ref": authority_ref,
        "payload": unsigned_payload,
    }


@dataclass(frozen=True)
class TrustedEntityAuthorityKey:
    key_id: str
    issuer: str
    tenant_id: str
    public_key_raw: bytes
    valid_from: str
    valid_until: str
    authority_refs: tuple[str, ...] = ("*",)
    revoked_at: str | None = None


class EntityAuthorityVerifier(Protocol):
    def verify(self, event: Mapping[str, Any]) -> bool:
        """Verify issuer signature, tenant, authority scope and key validity."""


TenantAuthorize = Callable[[str, str, str, str | None], bool]


class Ed25519EntityAuthorityVerifier:
    """Ed25519 verifier backed by an externally managed trusted-key snapshot.

    Production must source keys and revocations from a durable, independently
    governed trust registry. This in-memory key mapping is a verifier adapter,
    not itself the production trust registry.
    """

    def __init__(self, trusted_keys):
        # Accept either a static test snapshot or a live resolver backed by the
        # durable TrustedKeyRegistry. Production must use the live resolver so
        # key revocation takes effect without restarting consumers.
        if callable(trusted_keys):
            self.trusted_keys = None
            self.key_resolver = trusted_keys
            return
        if not isinstance(trusted_keys, Mapping) or not trusted_keys:
            raise EconomicEntityRegisterError("a trusted key mapping or live key resolver is required")
        self.trusted_keys = dict(trusted_keys)
        for mapping_key, key in self.trusted_keys.items():
            if not isinstance(key, TrustedEntityAuthorityKey) or mapping_key != key.key_id:
                raise EconomicEntityRegisterError("trusted authority key map must use canonical key IDs")
            required_text(key.key_id, "key.key_id")
            required_text(key.issuer, "key.issuer")
            required_text(key.tenant_id, "key.tenant_id")
            if not isinstance(key.public_key_raw, bytes) or len(key.public_key_raw) != 32:
                raise EconomicEntityRegisterError("Ed25519 public keys must be exactly 32 raw bytes")
            if not isinstance(key.authority_refs, tuple) or not key.authority_refs:
                raise EconomicEntityRegisterError("authority_refs must be a non-empty tuple")
            for authority_ref in key.authority_refs:
                required_text(authority_ref, "key.authority_ref")
            if _parse_utc(key.valid_from, "key.valid_from") >= _parse_utc(key.valid_until, "key.valid_until"):
                raise EconomicEntityRegisterError("trusted authority key validity interval is empty")
        self.key_resolver = lambda key_id: self.trusted_keys.get(key_id)

            if key.revoked_at is not None:
                _parse_utc(key.revoked_at, "key.revoked_at")

    def verify(self, event: Mapping[str, Any]) -> bool:
        payload = event.get("payload")
        if not isinstance(payload, Mapping):
            return False
        attestation = payload.get("authority_attestation")
        if not isinstance(attestation, Mapping) or set(attestation) != ATTESTATION_FIELDS:
            return False
        if attestation.get("algorithm") != "Ed25519":
            return False
        if attestation.get("scope") != "synergy.economic.entity-event/v1":
            return False
        key_id = attestation.get("key_id")
        try:
            key = self.key_resolver(key_id) if isinstance(key_id, str) else None
        except Exception:
            return False
        if not isinstance(key, TrustedEntityAuthorityKey):
            return False
        try:
            tenant_id = required_text(payload.get("tenant_id"), "tenant_id")
            issuer = required_text(attestation.get("issuer"), "attestation.issuer")
            signed_at = _parse_utc(attestation.get("signed_at"), "attestation.signed_at")
            recorded_at = _parse_utc(event.get("recorded_at"), "recorded_at")
            valid_from = _parse_utc(key.valid_from, "key.valid_from")
            valid_until = _parse_utc(key.valid_until, "key.valid_until")
            if signed_at < valid_from or signed_at >= valid_until or signed_at > recorded_at:
                return False
            if key.revoked_at is not None and signed_at >= _parse_utc(key.revoked_at, "key.revoked_at"):
                return False
            if (tenant_id != key.tenant_id or issuer != key.issuer
                    or event.get("authority_ref") not in key.authority_refs
                    and "*" not in key.authority_refs):
                return False
            if not isinstance(key.public_key_raw, bytes) or len(key.public_key_raw) != 32:
                return False
            signature_text = attestation.get("signature")
            if not isinstance(signature_text, str) or not signature_text:
                return False
            signature = base64.b64decode(signature_text, validate=True)
            from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

            public_key = Ed25519PublicKey.from_public_bytes(key.public_key_raw)
            signed = entity_event_signing_document(
                event_id=event["event_id"],
                event_type=event["event_type"],
                aggregate_id=event["aggregate_id"],
                effective_at=event["effective_at"],
                recorded_at=event["recorded_at"],
                actor_id=event["actor_id"],
                authority_ref=event["authority_ref"],
                payload=payload,
            )
            public_key.verify(signature, canonical_json(signed).encode("utf-8"))
            return True
        except Exception:
            return False



def entity_authority_key_resolver(registry):
    """Build a live economic-authority resolver from the durable trust registry."""
    if not callable(getattr(registry, "resolve_key", None)):
        raise EconomicEntityRegisterError("durable trust registry is required")

    def resolve(key_id):
        record = registry.resolve_key(
            key_id, required_scope="synergy.economic.entity-event/v1"
        )
        if record is None:
            return None
        return TrustedEntityAuthorityKey(
            key_id=record.key_id, issuer=record.issuer, tenant_id=record.tenant_id,
            public_key_raw=record.public_key, valid_from=record.valid_from,
            valid_until=record.valid_until, authority_refs=record.scopes,
            revoked_at=None,
        )
    return resolve


class CanonicalEconomicEntityRegister(DurableEventRegister):
    """Durable canonical entity identities and effective-dated sector memberships."""

    REGISTER_NAME = "economic_entities"
    read_permission = "entity:read"

    def __init__(self, database_path, *, authority_verifier: EntityAuthorityVerifier,
                 tenant_authorizer: TenantAuthorize, clock=None):
        if not callable(getattr(authority_verifier, "verify", None)):
            raise EconomicEntityRegisterError("an Ed25519 authority verifier is mandatory")
        if not callable(tenant_authorizer):
            raise EconomicEntityRegisterError("a tenant-scoped authorization service is mandatory")
        self.authority_verifier = authority_verifier
        self.tenant_authorizer = tenant_authorizer
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        super().__init__(database_path)

    @staticmethod
    def write_permission(event_type):
        if event_type in {"entity.suspended", "entity.reactivated", "entity.retired"}:
            return "entity:admin"
        return "entity:write"

    def _authorize_tenant(self, principal_id, tenant_id, permission, authority_ref=None):
        principal_id = required_text(principal_id, "principal_id")
        tenant_id = required_text(tenant_id, "tenant_id")
        permission = required_text(permission, "tenant_permission")
        if authority_ref is not None:
            authority_ref = required_text(authority_ref, "authority_ref")
        try:
            allowed = self.tenant_authorizer(principal_id, tenant_id, permission, authority_ref)
        except Exception as exc:
            raise EconomicEntityRegisterError("tenant authorization service unavailable; access denied") from exc
        if allowed is not True:
            raise EconomicEntityRegisterError(
                f"tenant authorization denied for {principal_id} on {tenant_id} ({permission})"
            )

    def append_event(self, **kwargs):
        payload = kwargs.get("payload")
        if not isinstance(payload, Mapping):
            raise EconomicEntityRegisterError("canonical entity event payload must be an object")
        event_type = required_text(kwargs.get("event_type"), "event_type")
        self._authorize_tenant(
            kwargs.get("actor_id"),
            payload.get("tenant_id"),
            self.write_permission(event_type),
            kwargs.get("authority_ref"),
        )
        return super().append_event(**kwargs)

    @staticmethod
    def _tenant_from_aggregate(aggregate_id):
        aggregate_id = required_text(aggregate_id, "aggregate_id")
        if "::" not in aggregate_id:
            raise EconomicEntityRegisterError("entity aggregate ID must contain tenant scope")
        tenant_id, entity_id = aggregate_id.split("::", 1)
        required_text(tenant_id, "tenant_id")
        required_text(entity_id, "entity_id")
        return tenant_id

    def state(self, aggregate_id, *, principal_id):
        tenant_id = self._tenant_from_aggregate(aggregate_id)
        self._authorize_tenant(principal_id, tenant_id, "entity:read")
        return super().state(aggregate_id, principal_id=principal_id)

    def history(self, aggregate_id, *, principal_id):
        tenant_id = self._tenant_from_aggregate(aggregate_id)
        self._authorize_tenant(principal_id, tenant_id, "entity:read")
        return super().history(aggregate_id, principal_id=principal_id)

    def prepare(self, txid, operation):
        raise EconomicEntityRegisterError(
            "canonical entity authority is not a six-register native transaction participant"
        )

    def commit(self, txid, prepare_token):
        raise EconomicEntityRegisterError(
            "canonical entity authority does not accept native participant commits"
        )

    def events_for_common_event(self, common_event_id, *, principal_id):
        raise EconomicEntityRegisterError(
            "cross-register event lookup is not exposed by the canonical entity register"
        )

    def committed_event(self, txid):
        raise EconomicEntityRegisterError(
            "native participant receipts are not exposed by the canonical entity register"
        )

    def _verify_event(self, event):
        for field in ("event_id", "event_type", "aggregate_id", "actor_id", "authority_ref"):
            required_text(event.get(field), field)
        utc_timestamp(event.get("effective_at"), "effective_at")
        utc_timestamp(event.get("recorded_at"), "recorded_at")
        event_type = event.get("event_type")
        if event_type not in DOMAIN_EVENTS:
            raise EconomicEntityRegisterError("unsupported canonical entity event")
        effective_at = _parse_utc(event["effective_at"], "effective_at")
        recorded_at = _parse_utc(event["recorded_at"], "recorded_at")
        if event_type != "entity.sector_changed" and effective_at > recorded_at:
            raise EconomicEntityRegisterError(
                "only effective-dated sector membership may be scheduled in the future"
            )
        if self.authority_verifier.verify(event) is not True:
            raise EconomicEntityRegisterError(
                "entity event lacks a valid tenant-scoped Ed25519 authority attestation"
            )

    @staticmethod
    def _validate_external_reference(reference):
        if not isinstance(reference, Mapping):
            raise EconomicEntityRegisterError("external reference must be an object")
        if set(reference) != {"namespace", "value", "issuer", "evidence_ref"}:
            raise EconomicEntityRegisterError("external reference fields do not match the canonical contract")
        for field in ("namespace", "value", "issuer", "evidence_ref"):
            required_text(reference.get(field), f"external_reference.{field}")
        return dict(reference)

    def reduce_event(self, old, event):
        self._verify_event(event)
        typ, payload = event["event_type"], event["payload"]
        tenant_id = required_text(payload.get("tenant_id"), "tenant_id")
        entity_id = required_text(payload.get("entity_id"), "entity_id")
        if event["aggregate_id"] != _entity_aggregate_id(tenant_id, entity_id):
            raise EconomicEntityRegisterError("aggregate ID must bind tenant and canonical entity ID")

        if typ == "entity.registered":
            if old is not None:
                raise EconomicEntityRegisterError("canonical entity identity already exists")
            allowed = {
                "tenant_id", "entity_id", "entity_kind", "jurisdiction",
                "institutional_sector", "display_name", "external_refs",
                "authority_attestation",
            }
            if set(payload) - allowed:
                raise EconomicEntityRegisterError("entity.registered contains unknown fields")
            kind = required_text(payload.get("entity_kind"), "entity_kind")
            if kind not in ENTITY_KINDS:
                raise EconomicEntityRegisterError("unsupported entity_kind")
            sector = required_text(payload.get("institutional_sector"), "institutional_sector")
            if sector not in SECTORS:
                raise EconomicEntityRegisterError("institutional sector must be explicit and canonical")
            jurisdiction = required_text(payload.get("jurisdiction"), "jurisdiction")
            display_name = payload.get("display_name")
            if display_name is not None:
                required_text(display_name, "display_name")
            references = payload.get("external_refs", [])
            if not isinstance(references, list):
                raise EconomicEntityRegisterError("external_refs must be an array")
            normalized, identities = [], set()
            for reference in references:
                item = self._validate_external_reference(reference)
                identity = (item["namespace"], item["value"], item["issuer"])
                if identity in identities:
                    raise EconomicEntityRegisterError("duplicate external reference")
                identities.add(identity)
                normalized.append(item)
            return {
                "tenant_id": tenant_id,
                "entity_id": entity_id,
                "entity_kind": kind,
                "jurisdiction": jurisdiction,
                "display_name": display_name,
                "institutional_sector": sector,
                "sector_memberships": [{
                    "sector": sector,
                    "effective_from": event["effective_at"],
                    "effective_to": None,
                }],
                "external_refs": normalized,
                "status": "ACTIVE",
                "registered_at": event["effective_at"],
                "last_effective_at": event["effective_at"],
                "last_authority_event_ref": event["event_id"],
            }

        if old is None:
            raise EconomicEntityRegisterError("entity transition references an unknown canonical identity")
        state = dict(old)
        if state["tenant_id"] != tenant_id or state["entity_id"] != entity_id:
            raise EconomicEntityRegisterError("tenant/entity identity is immutable")
        if _parse_utc(event["effective_at"], "effective_at") < _parse_utc(
            state["last_effective_at"], "last_effective_at"
        ):
            raise EconomicEntityRegisterError("entity event effective time cannot move backwards")

        if typ == "entity.updated":
            if set(payload) != {"tenant_id", "entity_id", "changes", "authority_attestation"}:
                raise EconomicEntityRegisterError("entity.updated contains unknown fields")
            if state["status"] == "RETIRED":
                raise EconomicEntityRegisterError("retired entity cannot be updated")
            changes = payload.get("changes")
            if not isinstance(changes, Mapping) or not changes:
                raise EconomicEntityRegisterError("entity.updated requires a non-empty changes object")
            if set(changes) - {"jurisdiction", "display_name"}:
                raise EconomicEntityRegisterError("entity.updated may change only jurisdiction/display_name")
            if "jurisdiction" in changes:
                state["jurisdiction"] = required_text(changes["jurisdiction"], "jurisdiction")
            if "display_name" in changes:
                state["display_name"] = required_text(changes["display_name"], "display_name")

        elif typ == "entity.external_reference_added":
            if set(payload) != {"tenant_id", "entity_id", "external_ref", "authority_attestation"}:
                raise EconomicEntityRegisterError("entity.external_reference_added contains unknown fields")
            if state["status"] == "RETIRED":
                raise EconomicEntityRegisterError("retired entity cannot receive new external references")
            reference = self._validate_external_reference(payload.get("external_ref"))
            identity = (reference["namespace"], reference["value"], reference["issuer"])
            if any((x["namespace"], x["value"], x["issuer"]) == identity
                   for x in state["external_refs"]):
                raise EconomicEntityRegisterError("external reference already registered")
            state["external_refs"] = list(state["external_refs"]) + [reference]

        elif typ == "entity.sector_changed":
            if set(payload) != {"tenant_id", "entity_id", "institutional_sector", "authority_attestation"}:
                raise EconomicEntityRegisterError("entity.sector_changed contains unknown fields")
            if state["status"] == "RETIRED":
                raise EconomicEntityRegisterError("retired entity cannot change sector")
            sector = required_text(payload.get("institutional_sector"), "institutional_sector")
            if sector not in SECTORS:
                raise EconomicEntityRegisterError("institutional sector must be explicit and canonical")
            memberships = [dict(x) for x in state["sector_memberships"]]
            current = memberships[-1]
            if sector == current["sector"]:
                raise EconomicEntityRegisterError("sector change must change the sector")
            if event["effective_at"] <= current["effective_from"]:
                raise EconomicEntityRegisterError("sector change must follow the previous effective start")
            current["effective_to"] = event["effective_at"]
            memberships.append({
                "sector": sector,
                "effective_from": event["effective_at"],
                "effective_to": None,
            })
            state["sector_memberships"] = memberships
            state["institutional_sector"] = sector

        elif typ == "entity.suspended":
            if set(payload) != {"tenant_id", "entity_id", "reason", "evidence_ref", "authority_attestation"}:
                raise EconomicEntityRegisterError("entity.suspended contains unknown fields")
            if state["status"] != "ACTIVE":
                raise EconomicEntityRegisterError("only an active entity can be suspended")
            state["status"] = "SUSPENDED"
            state["suspended_at"] = event["effective_at"]
            state["lifecycle_evidence_ref"] = required_text(payload.get("evidence_ref"), "evidence_ref")
            state["lifecycle_reason"] = required_text(payload.get("reason"), "reason")

        elif typ == "entity.reactivated":
            if set(payload) != {"tenant_id", "entity_id", "reason", "evidence_ref", "authority_attestation"}:
                raise EconomicEntityRegisterError("entity.reactivated contains unknown fields")
            if state["status"] != "SUSPENDED":
                raise EconomicEntityRegisterError("only a suspended entity can be reactivated")
            state["status"] = "ACTIVE"
            state["reactivated_at"] = event["effective_at"]
            state["lifecycle_evidence_ref"] = required_text(payload.get("evidence_ref"), "evidence_ref")
            state["lifecycle_reason"] = required_text(payload.get("reason"), "reason")

        elif typ == "entity.retired":
            if set(payload) != {"tenant_id", "entity_id", "reason", "evidence_ref", "authority_attestation"}:
                raise EconomicEntityRegisterError("entity.retired contains unknown fields")
            if state["status"] not in {"ACTIVE", "SUSPENDED"}:
                raise EconomicEntityRegisterError("entity can be retired only once")
            state["status"] = "RETIRED"
            state["retired_at"] = event["effective_at"]
            state["lifecycle_evidence_ref"] = required_text(payload.get("evidence_ref"), "evidence_ref")
            state["lifecycle_reason"] = required_text(payload.get("reason"), "reason")

        else:
            raise EconomicEntityRegisterError(f"unsupported entity event: {typ}")

        state["last_effective_at"] = event["effective_at"]
        state["last_authority_event_ref"] = event["event_id"]
        return state

    def _aggregate(self, tenant_id, entity_id):
        tenant_id = required_text(tenant_id, "tenant_id")
        entity_id = required_text(entity_id, "entity_id")
        return _entity_aggregate_id(tenant_id, entity_id)

    def register_entity(self, *, entity_id, tenant_id, entity_kind, jurisdiction,
                        institutional_sector, event_id, idempotency_key, effective_at,
                        recorded_at, actor_id, authority_ref, authority_attestation,
                        external_refs=(), display_name=None):
        payload = {
            "tenant_id": tenant_id, "entity_id": entity_id, "entity_kind": entity_kind,
            "jurisdiction": jurisdiction, "institutional_sector": institutional_sector,
            "external_refs": list(external_refs), "authority_attestation": authority_attestation,
        }
        if display_name is not None:
            payload["display_name"] = display_name
        return self.append_event(
            event_id=event_id, idempotency_key=idempotency_key,
            aggregate_id=self._aggregate(tenant_id, entity_id),
            event_type="entity.registered", effective_at=effective_at, recorded_at=recorded_at,
            actor_id=actor_id, authority_ref=authority_ref, payload=payload, expected_version=0,
        )

    def append_entity_event(self, *, tenant_id, entity_id, event_type, event_id,
                            idempotency_key, effective_at, recorded_at, actor_id,
                            authority_ref, authority_attestation, payload, expected_version):
        if event_type not in DOMAIN_EVENTS - {"entity.registered"}:
            raise EconomicEntityRegisterError("unsupported entity transition event type")
        document = dict(payload)
        if "tenant_id" in document or "entity_id" in document or "authority_attestation" in document:
            raise EconomicEntityRegisterError("identity and attestation fields are supplied by the register boundary")
        document.update({
            "tenant_id": tenant_id, "entity_id": entity_id,
            "authority_attestation": authority_attestation,
        })
        return self.append_event(
            event_id=event_id, idempotency_key=idempotency_key,
            aggregate_id=self._aggregate(tenant_id, entity_id),
            event_type=event_type, effective_at=effective_at, recorded_at=recorded_at,
            actor_id=actor_id, authority_ref=authority_ref, payload=document,
            expected_version=expected_version,
        )

    @staticmethod
    def _sector_at(memberships, as_of):
        instant = _parse_utc(as_of, "as_of")
        matches = []
        for membership in memberships:
            start = _parse_utc(membership["effective_from"], "effective_from")
            end = (_parse_utc(membership["effective_to"], "effective_to")
                   if membership["effective_to"] is not None else None)
            if start <= instant and (end is None or instant < end):
                matches.append(membership["sector"])
        if len(matches) != 1:
            raise EconomicEntityRegisterError("entity has no unique effective institutional sector at this time")
        return matches[0]

    def resolve_entity(self, tenant_id: str, economic_entity_id: str,
                       *, principal_id: str, as_of: str | None = None) -> dict[str, Any]:
        aggregate_id = self._aggregate(tenant_id, economic_entity_id)
        state, version = self.state(aggregate_id, principal_id=principal_id)
        if state is None:
            raise EconomicEntityRegisterError("canonical economic entity not found")
        history = self.history(aggregate_id, principal_id=principal_id)
        if not history:
            raise EconomicEntityRegisterError("canonical economic entity has no authoritative event history")
        now = self.clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise EconomicEntityRegisterError("resolver clock must return a timezone-aware datetime")
        instant = as_of or now.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
        sector = self._sector_at(state["sector_memberships"], instant)
        latest = history[-1]
        return {
            "schema_id": "synergy.economic.canonical-entity-snapshot",
            "schema_version": 1,
            "tenant_id": state["tenant_id"],
            "entity_id": state["entity_id"],
            "entity_kind": state["entity_kind"],
            "jurisdiction": state["jurisdiction"],
            "institutional_sector": sector,
            "version": version,
            "status": state["status"],
            "authority_system": "synergistic_economics",
            "authority_event_ref": latest["event_id"],
            "source_digest": latest["chain_hash"],
            "verified": True,
            "display_name": state.get("display_name"),
            "external_refs": list(state["external_refs"]),
            "effective_as_of": instant,
        }


class CanonicalEconomicEntityResolverAdapter:
    """Least-privilege adapter exposing the two-argument Metaverse resolver contract."""

    def __init__(self, register: CanonicalEconomicEntityRegister, *, service_principal_id: str):
        if not isinstance(register, CanonicalEconomicEntityRegister):
            raise TypeError("register must be a CanonicalEconomicEntityRegister")
        self.register = register
        self.service_principal_id = required_text(service_principal_id, "service_principal_id")

    def resolve_entity(self, tenant_id: str, economic_entity_id: str) -> Mapping[str, Any]:
        return self.register.resolve_entity(
            tenant_id, economic_entity_id, principal_id=self.service_principal_id
        )
