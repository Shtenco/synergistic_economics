"""Adversarial closed-period governance integrated with signed Ed25519 checkpoints."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from external_checkpoints import (
    Ed25519Signer, LocalImmutableAnchor, TrustedKeyRegistry,
    publish_checkpoint, sha256_bytes, verify_checkpoint,
)
from period_governance import (
    REGISTERS, PeriodGovernance, PeriodGovernanceError,
)


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _checkpoint(signer, anchor, sequence, generation, event_root=None, projection_hash=None, period=7):
    backup = f"period-{7}-generation-{generation}-backup".encode()
    manifest = {
        "manifest_schema_version": 1,
        "service_id": "synergy-period-governance",
        "database_schema_version": 4,
        "mapper_version": "gold2a-entity-journal-mapper@1",
        "projection_generation": generation,
        "commit_sequence": sequence,
        "event_count": 100,
        "event_log_root": event_root or _sha("period-7-event-root"),
        "instrument_opening_hash": _sha("instrument-openings"),
        "control_opening_hash": _sha("control-openings"),
        "projection_state_hash": projection_hash or _sha(f"projection-generation-{generation}"),
        "coverage_count": 100,
        "applied_through_cursor": sequence,
        "period": period,
        "period_closed": True,
        "backup_sha256": sha256_bytes(backup),
        "checkpoint_sequence": sequence,
        "created_at_utc": f"2026-11-12T10:0{sequence}:00Z",
        "signer_key_id": signer.key_id,
    }
    ref, digest = publish_checkpoint(manifest, signer, anchor)
    return ref, digest


def _reconciliation_hash(source_root):
    receipts = [{
        "register_name": name,
        "old_generation": 0,
        "new_generation": 1,
        "source_event_root": source_root,
        "event_count": 100,
        "opening_state_hash": _sha(name + "-opening"),
        "closing_state_hash": _sha(name + "-closing"),
        "reconciliation_hash": _sha(name + "-reconciliation"),
    } for name in sorted(REGISTERS)]
    canonical = json.dumps(receipts, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def _authorization_verifier(approver_id, role, context, evidence_ref):
    # Deterministic test identity provider. Production must replace this with
    # a separately administered signed-assertion verifier.
    expected = {
        ("person-A", "period_owner", "approval://owner-A"),
        ("person-B", "independent_controller", "approval://controller-B"),
    }
    return (
        (approver_id, role, evidence_ref) in expected
        and context["service_id"] == "synergy-period-governance"
        and context["period"] == 7
        and context["request_id"] in {"reopen-001", "reopen-002"}
        and context["scope"] == sorted(REGISTERS)
        and len(context["request_digest"]) == 64
    )


def _rejects(call, message):
    try:
        call()
    except (PeriodGovernanceError, sqlite3.IntegrityError):
        return
    raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="synergy-period-governance-") as directory:
        root = Path(directory)
        anchor = LocalImmutableAnchor(root / "external-anchor.sqlite3")
        signer = Ed25519Signer.generate("synergy-period-close-key-2026")
        trust = TrustedKeyRegistry({signer.key_id: signer.public_bytes()})
        close_ref, close_digest = _checkpoint(signer, anchor, 1, 0)
        verify = lambda ref, digest: _verify_bool(ref, digest, trust, anchor)
        governance = PeriodGovernance(
            root / "period-governance.sqlite3", verify, "synergy-period-governance",
            _authorization_verifier,
        )
        wrong_service = PeriodGovernance(
            root / "wrong-service.sqlite3", verify, "another-ledger",
            _authorization_verifier,
        )
        _rejects(lambda: wrong_service.close_period(
            7, 0, close_ref, close_digest, "controller-A"
        ), "checkpoint from another service identity was accepted")

        assert governance.close_period(7, 0, close_ref, close_digest, "controller-A")
        assert not governance.close_period(7, 0, close_ref, close_digest, "controller-A")
        assert governance.active_generation(7) == 0

        # Extend the close chain across three consecutive accounting periods.
        # Each close has its own signed checkpoint; the global checkpoint
        # sequence remains monotonic across period identities.
        close8_ref, close8_digest = _checkpoint(signer, anchor, 2, 0, period=8)
        assert governance.close_period(8, 0, close8_ref, close8_digest, "controller-A")
        close9_ref, close9_digest = _checkpoint(signer, anchor, 3, 0, period=9)
        assert governance.close_period(9, 0, close9_ref, close9_digest, "controller-A")
        assert [governance.active_generation(p) for p in (7, 8, 9)] == [0, 0, 0]

        correction = {
            "reversal_of": "native-event-original",
            "amount": "12.50",
            "currency": "LCU",
            "valuation_basis": "NOMINAL",
        }
        assert governance.append_correction(
            "correction-001", 10, "native-event-original",
            "late evidence discovered after close", "period-owner-A",
            "legal-evidence://correction-001", correction,
        )
        assert not governance.append_correction(
            "correction-001", 10, "native-event-original",
            "late evidence discovered after close", "period-owner-A",
            "legal-evidence://correction-001", correction,
        )
        _rejects(lambda: governance.append_correction(
            "correction-in-closed-period", 9, "native-event-original",
            "attempt to rewrite closed history", "period-owner-A",
            "legal-evidence://bad", correction,
        ), "correction was allowed to mutate a closed period")

        scope = list(REGISTERS)
        assert governance.request_reopen(
            "reopen-001", 7, "correct material cohort classification",
            "authority://reopen-001", scope, close_ref, close_digest,
        )
        _rejects(lambda: governance.approve_reopen(
            "reopen-001", "person-A", "period_owner", "approval://forged-owner-proof"
        ), "approval accepted without an independently verified role assertion")
        _rejects(lambda: governance.approve_reopen(
            "reopen-001", "unauthorized-person", "period_owner", "approval://owner-A"
        ), "unauthorized identity was allowed to claim period_owner")
        assert governance.approve_reopen(
            "reopen-001", "person-A", "period_owner", "approval://owner-A"
        )
        _rejects(lambda: governance.approve_reopen(
            "reopen-001", "person-A", "independent_controller",
            "approval://controller-same-person",
        ), "same person satisfied both approval roles")
        assert governance.approve_reopen(
            "reopen-001", "person-B", "independent_controller",
            "approval://controller-B",
        )

        root_hash = _sha("immutable-event-log-root-period-7")
        global_reconciliation = _reconciliation_hash(root_hash)
        for name in REGISTERS[:-1]:
            governance.record_rebuild(
                "reopen-001", name, root_hash, 100,
                _sha(name + "-opening"), _sha(name + "-closing"),
                _sha(name + "-reconciliation"),
            )
        generation1_ref, generation1_digest = _checkpoint(
            signer, anchor, 4, 1, event_root=root_hash,
            projection_hash=global_reconciliation,
        )
        _rejects(lambda: governance.publish_generation(
            "reopen-001", global_reconciliation,
            generation1_ref, generation1_digest,
        ), "generation published without all six register rebuild receipts")
        assert governance.active_generation(7) == 0

        governance.record_rebuild(
            "reopen-001", "financial", root_hash, 100,
            _sha("financial-opening"), _sha("financial-closing"),
            _sha("financial-reconciliation"),
        )
        # A valid signature for the same period/generation is insufficient
        # when its event root does not match the six participant rebuilds.
        wrong_root_ref, wrong_root_digest = _checkpoint(
            signer, anchor, 5, 1, event_root=_sha("wrong-event-root"),
            projection_hash=global_reconciliation,
        )
        _rejects(lambda: governance.publish_generation(
            "reopen-001", global_reconciliation,
            wrong_root_ref, wrong_root_digest,
        ), "publication accepted a signed checkpoint for another event root")

        # The global hash must be the canonical digest of all six receipts.
        _rejects(lambda: governance.publish_generation(
            "reopen-001", _sha("wrong-global-reconciliation"),
            wrong_root_ref, wrong_root_digest,
        ), "publication accepted an unrelated global reconciliation hash")

        generation1_ref, generation1_digest = _checkpoint(
            signer, anchor, 6, 1, event_root=root_hash,
            projection_hash=global_reconciliation,
        )
        assert governance.publish_generation(
            "reopen-001", global_reconciliation,
            generation1_ref, generation1_digest,
        )
        assert not governance.publish_generation(
            "reopen-001", global_reconciliation,
            generation1_ref, generation1_digest,
        )
        assert not governance.approve_reopen(
            "reopen-001", "person-A", "period_owner", "approval://owner-A"
        )
        assert not governance.record_rebuild(
            "reopen-001", "physical", root_hash, 100,
            _sha("physical-opening"), _sha("physical-closing"),
            _sha("physical-reconciliation"),
        )
        assert governance.active_generation(7) == 1

        with sqlite3.connect(root / "period-governance.sqlite3") as con:
            history = con.execute(
                "SELECT generation,checkpoint_ref FROM generation_history "
                "WHERE period=7 ORDER BY generation"
            ).fetchall()
            assert history == [(0, close_ref), (1, generation1_ref)]
            _rejects(lambda: con.execute(
                "UPDATE period_closures SET generation=99 WHERE period=7"
            ), "closed-period snapshot was mutable")

        _rejects(lambda: governance.request_reopen(
            "reopen-stale", 7, "stale generation checkpoint",
            "authority://stale", scope, close_ref, close_digest,
        ), "reopen accepted stale generation checkpoint")
        assert governance.request_reopen(
            "reopen-002", 7, "second governed correction",
            "authority://reopen-002", scope,
            generation1_ref, generation1_digest,
        )
        assert governance.active_generation(7) == 1

    print("PASS: corrections append in an open period; closed period remains immutable")
    print("PASS: reopening requires two distinct approvers in separate roles")
    print("PASS: generation switch waits for all six same-root rebuild receipts")
    print("PASS: prior generation retained; repeated reopen binds to active signed checkpoint")


def _verify_bool(ref, digest, trust, anchor):
    try:
        return verify_checkpoint(ref, digest, trust, anchor, require_latest=False)
    except Exception:
        return False


if __name__ == "__main__":
    main()
