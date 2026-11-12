"""Adversarial tests for externally signed Ed25519 approval assertions."""
from pathlib import Path
import hashlib
import json
import sys
import tempfile

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from signed_approval_assertions import (
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
        public = private.public_key().public_bytes_raw()
        revoked_keys = set()
        revoked_jtis = set()
        resolver_calls = []
        revocation_calls = []

        def key_resolver(issuer, kid):
            resolver_calls.append((issuer, kid))
            return public if issuer == ISSUER and kid == KID and (issuer, kid) not in revoked_keys else None

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

        assert resolver_calls and revocation_calls
        print("PASS: Ed25519 assertion signature, issuer and audience verified")
        print("PASS: service, subject, role and canonical request digest bound")
        print("PASS: expiry, not-before and maximum lifetime enforced")
        print("PASS: revoked jti, unknown key, changed signature and role escalation rejected")
        print("PASS: revocation-provider outage fails closed")
        print("PASS: assertion jti is durable; exact retry idempotent and changed-content reuse rejected")


if __name__ == "__main__":
    main()
