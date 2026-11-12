"""Adversarial closed-period governance integrated with signed Ed25519 checkpoints."""
from pathlib import Path
import hashlib
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


def _checkpoint(signer, anchor, sequence, generation):
    backup = f"period-{7}-generation-{generation}-backup".encode()
    manifest = {
        "manifest_schema_version": 1,
        "service_id": "synergy-period-governance",
        "database_schema_version": 4,
        "mapper_version": "gold2a-entity-journal-mapper@1",
        "projection_generation": generation,
        "commit_sequence": sequence,
        "event_count": 100,
        "event_log_root": _sha("period-7-event-root"),
        "instrument_opening_hash": _sha("instrument-openings"),
        "control_opening_hash": _sha("control-openings"),
        "projection_state_hash": _sha(f"projection-generation-{generation}"),
        "coverage_count": 100,
        "applied_through_cursor": sequence,
        "period": 7,
        "period_closed": True,
        "backup_sha256": sha256_bytes(backup),
        "checkpoint_sequence": sequence,
        "created_at_utc": f"2026-11-12T10:0{sequence}:00Z",
        "signer_key_id": signer.key_id,
    }
    ref, digest = publish_checkpoint(manifest, signer, anchor)
    return ref, digest


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
        governance = PeriodGovernance(root / "period-governance.sqlite3", verify, "synergy-period-governance")
        wrong_service = PeriodGovernance(root / "wrong-service.sqlite3", verify, "another-ledger")
        _rejects(lambda: wrong_service.close_period(
            7, 0, close_ref, close_digest, "controller-A"
        ), "checkpoint from another service identity was accepted")

        assert governance.close_period(7, 0, close_ref, close_digest, "controller-A")
        assert not governance.close_period(7, 0, close_ref, close_digest, "controller-A")
        assert governance.active_generation(7) == 0

        correction = {
            "reversal_of": "native-event-original",
            "amount": "12.50",
            "currency": "LCU",
            "valuation_basis": "NOMINAL",
        }
        assert governance.append_correction(
            "correction-001", 8, "native-event-original",
            "late evidence discovered after close", "period-owner-A",
            "legal-evidence://correction-001", correction,
        )
        assert not governance.append_correction(
            "correction-001", 8, "native-event-original",
            "late evidence discovered after close", "period-owner-A",
            "legal-evidence://correction-001", correction,
        )
        _rejects(lambda: governance.append_correction(
            "correction-in-closed-period", 7, "native-event-original",
            "attempt to rewrite closed history", "period-owner-A",
            "legal-evidence://bad", correction,
        ), "correction was allowed to mutate a closed period")

        scope = list(REGISTERS)
        assert governance.request_reopen(
            "reopen-001", 7, "correct material cohort classification",
            "authority://reopen-001", scope, close_ref, close_digest,
        )
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
        for name in REGISTERS[:-1]:
            governance.record_rebuild(
                "reopen-001", name, root_hash, 100,
                _sha(name + "-opening"), _sha(name + "-closing"),
                _sha(name + "-reconciliation"),
            )
        generation1_ref, generation1_digest = _checkpoint(signer, anchor, 2, 1)
        _rejects(lambda: governance.publish_generation(
            "reopen-001", _sha("global-reconciliation"),
            generation1_ref, generation1_digest,
        ), "generation published without all six register rebuild receipts")
        assert governance.active_generation(7) == 0

        governance.record_rebuild(
            "reopen-001", "financial", root_hash, 100,
            _sha("financial-opening"), _sha("financial-closing"),
            _sha("financial-reconciliation"),
        )
        assert governance.publish_generation(
            "reopen-001", _sha("global-reconciliation"),
            generation1_ref, generation1_digest,
        )
        assert not governance.publish_generation(
            "reopen-001", _sha("global-reconciliation"),
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
