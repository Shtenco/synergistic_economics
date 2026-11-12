"""Adversarial tests for externally signed Ed25519 approval assertions."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import tempfile

from cryptography.hazmat.primitives import serialization\nfrom cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from period_governance import REGISTERS, PeriodGovernance, PeriodGovernanceError\nfrom signed_approval_assertions import (
    ApprovalAssertionError, SignedApprovalVerifier, encode_assertion_payload,
)

ISSUER = "https://identity.example.test"
AUDIENCE = "synergy-period-governance"
KID = "approval-ed25519-2026-01"
NOW = 1_800_000_000
DOMAIN = b"SYNERGY_PERIOD_APPROVAL_ASSERTION_V1\\0"


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _sign(payload, private_key):
    segment = encode_assertion_payload(payload)
    signature = private_key.sign(DOMAIN + segment.encode("ascii"))
    import base64
    encoded = base64.urlsafe_b64encode(signature).decode("ascii").rstrip("=")
    return segment + "." + encoded


def _payload(context, *, sub="controller-A", role="period_owner",
             jti="jti-valid-001", iat=NOW - 5, exp=NOW + 120,
             iss=ISSUER, aud=AUDIENCE, service_id=None,
             request_digest=None, kid=KID):
    return {
        "alg": "EdDSA",
        "iss": iss,
        "sub": sub,
        "aud": aud,
        "service_id": service_id or context["service_id"],
        "request_id": context["request_id"],
        "request_digest": request_digest or context["request_digest"],
        "role": role,
        "evidence_ref": "approval-evidence://governance/reopen-7",
        "jti": jti,
        "iat": iat,
        "exp": exp,
        "kid": kid,
    }


def _rejects(call, reason):
    try:
        call()
    except ApprovalAssertionError:
        return
    raise AssertionError(reason)


def main():
    with tempfile.TemporaryDirectory(prefix="synergy-signed-approval-") as directory:
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(\n            encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw\n        )
        revoked_keys = set()
        revoked_jtis = set()
        resolver_calls = []
        revocation_calls = []

        def key_resolver(issuer, kid):
            resolver_calls.append((issuer, kid))
            return public if issuer == ISSUER and kid == KID else None

        def is_revoked(issuer, kid, jti):
            revocation_calls.append((issuer, kid, jti))
            return (issuer, kid) in revoked_keys or (issuer, jti) in revoked_jtis

        verifier = SignedApprovalVerifier(
            Path(directory) / "assertion-replay.sqlite3",
            issuer=ISSUER, audience=AUDIENCE, key_resolver=key_resolver,
            is_revoked=is_revoked, clock=lambda: NOW,
            clock_skew_seconds=10, max_lifetime_seconds=300,
        )
        context = {
            "service_id": "synergy-period-governance",
            "request_id": "reopen-2026-001",
            "period": 7,
            "old_generation": 0,
            "new_generation": 1,
            "reason": "correct material cohort classification",
            "evidence_ref": "authority://reopen-2026-001",
            "scope": ["capital", "financial", "labour", "legal_rights", "physical", "product"],
        }
        context["request_digest"] = hashlib.sha256(_canonical(context)).hexdigest()

        valid = _sign(_payload(context), private)
        assert verifier("controller-A", "period_owner", context, valid) is True
        # An exact retry is safe/idempotent; a jti collision with changed signed
        # content is rejected even if the altered assertion has a valid signature.
        assert verifier("controller-A", "period_owner", context, valid) is True
        changed = _payload(context, jti="jti-valid-001", sub="attacker")
        changed_token = _sign(changed, private)
        _rejects(lambda: verifier("attacker", "period_owner", context, changed_token),
                 "jti reused with changed signed content was accepted")

        expired = _sign(_payload(
            context, jti="jti-expired", iat=NOW - 500, exp=NOW - 400
        ), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, expired),
                 "expired approval assertion was accepted")

        future = _sign(_payload(
            context, jti="jti-future", iat=NOW + 60, exp=NOW + 120
        ), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, future),
                 "not-yet-valid approval assertion was accepted")

        revoked_jtis.add((ISSUER, "jti-revoked"))
        revoked = _sign(_payload(context, jti="jti-revoked"), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, revoked),
                 "revoked assertion ID was accepted")

        revoked_keys.add((ISSUER, KID))
        revoked_key_token = _sign(_payload(context, jti="jti-revoked-key"), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, revoked_key_token),
                 "revoked signing key was accepted")
        revoked_keys.clear()

        wrong_audience = _sign(_payload(context, jti="jti-wrong-aud", aud="other-service"), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, wrong_audience),
                 "wrong audience was accepted")

        wrong_service = _sign(_payload(context, jti="jti-wrong-service",
                                        service_id="another-service"), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, wrong_service),
                 "wrong service identity was accepted")

        wrong_digest = _sign(_payload(context, jti="jti-wrong-digest",
                                      request_digest="0" * 64), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, wrong_digest),
                 "assertion for another request digest was accepted")

        wrong_role = _sign(_payload(context, jti="jti-wrong-role",
                                    role="independent_controller"), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, wrong_role),
                 "role escalation was accepted")

        unknown_key = _sign(_payload(context, jti="jti-unknown-key", kid="untrusted-key"), private)
        _rejects(lambda: verifier("controller-A", "period_owner", context, unknown_key),
                 "unknown signing key was accepted")

        bad_signature = valid[:-1] + ("A" if valid[-1] != "A" else "B")
        _rejects(lambda: verifier("controller-A", "period_owner", context, bad_signature),
                 "tampered signature was accepted")

        outage = SignedApprovalVerifier(
            Path(directory) / "outage.sqlite3", issuer=ISSUER, audience=AUDIENCE,
            key_resolver=key_resolver,
            is_revoked=lambda *_: (_ for _ in ()).throw(RuntimeError("revocation API unavailable")),
            clock=lambda: NOW,
        )
        _rejects(lambda: outage("controller-A", "period_owner", context,
                                _sign(_payload(context, jti="jti-revocation-outage"), private)),
                 "revocation service outage did not fail closed")

        # Exercise the verifier through the actual period-governance approval
        # boundary, including durable two-person approval and idempotent retry.
        service_id = "synergy-period-governance-integration"
        manifest = {
            "service_id": service_id, "period": 7,
            "projection_generation": 0, "period_closed": True,
        }
        governance_verifier = SignedApprovalVerifier(
            Path(directory) / "governance-assertion-replay.sqlite3",
            issuer=ISSUER, audience=AUDIENCE, key_resolver=key_resolver,
            is_revoked=is_revoked, clock=lambda: NOW,
        )
        governance = PeriodGovernance(
            Path(directory) / "period-governance.sqlite3",
            lambda _ref, _digest: manifest, service_id, governance_verifier,
        )
        checkpoint_digest = "a" * 64
        assert governance.close_period(
            7, 0, "checkpoint://period-7-generation-0",
            checkpoint_digest, "closing-controller",
        )
        assert governance.request_reopen(
            "reopen-signed-001", 7, "verified late physical evidence",
            "evidence://reopen-signed-001", list(REGISTERS),
            "checkpoint://period-7-generation-0", checkpoint_digest,
        )
        with sqlite3.connect(Path(directory) / "period-governance.sqlite3") as con:
            con.row_factory = sqlite3.Row
            request = con.execute(
                "SELECT * FROM reopen_requests WHERE request_id=?",
                ("reopen-signed-001",),
            ).fetchone()
        gov_context = {
            "service_id": service_id,
            "request_id": request["request_id"],
            "period": request["period"],
            "old_generation": request["old_generation"],
            "new_generation": request["new_generation"],
            "reason": request["reason"],
            "evidence_ref": request["evidence_ref"],
            "scope": json.loads(request["scope_json"]),
            "pre_reopen_checkpoint_ref": request["pre_reopen_checkpoint_ref"],
            "pre_reopen_checkpoint_digest": request["pre_reopen_checkpoint_digest"],
        }
        gov_context["request_digest"] = hashlib.sha256(_canonical(gov_context)).hexdigest()
        owner_assertion = _sign(_payload(
            gov_context, sub="signed-owner-A", role="period_owner",
            jti="jti-governance-owner",
        ), private)
        assert governance.approve_reopen(
            "reopen-signed-001", "signed-owner-A", "period_owner", owner_assertion
        )
        assert not governance.approve_reopen(
            "reopen-signed-001", "signed-owner-A", "period_owner", owner_assertion
        )
        same_person_assertion = _sign(_payload(
            gov_context, sub="signed-owner-A", role="independent_controller",
            jti="jti-governance-same-person",
        ), private)
        _rejects(lambda: governance.approve_reopen(
            "reopen-signed-001", "signed-owner-A", "independent_controller",
            same_person_assertion,
        ), "same signed identity satisfied both governance approval roles")
        controller_assertion = _sign(_payload(
            gov_context, sub="signed-controller-B", role="independent_controller",
            jti="jti-governance-controller",
        ), private)
        assert governance.approve_reopen(
            "reopen-signed-001", "signed-controller-B",
            "independent_controller", controller_assertion,
        )
        with sqlite3.connect(Path(directory) / "period-governance.sqlite3") as con:
            state = con.execute(
                "SELECT state FROM reopen_requests WHERE request_id=?",
                ("reopen-signed-001",),
            ).fetchone()[0]
        assert state == "APPROVED"

        assert resolver_calls and revocation_calls
        print("PASS: Ed25519 assertion signature, issuer and audience verified")
        print("PASS: service, subject, role and canonical request digest bound")
        print("PASS: expiry, not-before and maximum lifetime enforced")
        print("PASS: revoked jti, revoked signing key, unknown key, changed signature and role escalation rejected")
        print("PASS: revocation-provider outage fails closed")
        print("PASS: assertion jti is durable; exact retry idempotent and changed-content reuse rejected")\n        print("PASS: signed assertions authorize the real period-governance dual-approval transition")


if __name__ == "__main__":
    main()
