"""End-to-end protocol-store backup, corruption quarantine and restore drill.

This validates the coordinator's six independent SQLite conformance stores. It
does not claim that the authoritative domain-register databases are integrated.
"""
from contextlib import closing
from io import BytesIO
from pathlib import Path
import hashlib
import json
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from cross_register_coordinator import (
    PARTICIPANTS, CrossRegisterCoordinator, SQLiteParticipant,
)
from external_checkpoints import (
    Ed25519Signer, LocalImmutableAnchor, TrustedKeyRegistry,
    publish_checkpoint, sha256_bytes, verify_backup_bytes, verify_checkpoint,
)


def _operations():
    payloads = {
        "physical": {"product": "grain", "quantity": "3.25", "unit": "t"},
        "capital": {"cohort_id": "cohort-7", "service_flow": "2.0", "unit": "service_unit"},
        "labour": {"hours": "4", "time_basis": "week", "consent_state": "accepted"},
        "product": {"quantity": "3.25", "unit": "t", "unit_price": "4", "currency": "LCU"},
        "legal_rights": {"right_id": "right-9", "scope": "use", "evidence_ref": "legal-evidence-9"},
        "financial": {"amount": "13", "currency": "LCU", "valuation_basis": "NOMINAL"},
    }
    return {
        name: {
            "stream_id": f"{name}-stream",
            "native_event_id": f"{name}-dr-event-001",
            "expected_revision": 0,
            "payload": payloads[name],
        }
        for name in PARTICIPANTS
    }


def _open(root):
    participants = {
        name: SQLiteParticipant(name, root / f"{name}.sqlite3")
        for name in PARTICIPANTS
    }
    coordinator = CrossRegisterCoordinator(root / "coordinator.sqlite3", participants)
    return coordinator, participants


def _backup_database(source_path, backup_path):
    with closing(sqlite3.connect(source_path)) as source, closing(sqlite3.connect(backup_path)) as target:
        source.execute("PRAGMA foreign_keys=ON")
        checkpoint = source.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
        assert checkpoint[0] == 0, f"WAL checkpoint busy for {source_path}: {checkpoint}"
        source.backup(target)
        assert target.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        assert target.execute("PRAGMA foreign_key_check").fetchall() == []


def _backup_bundle(backup_paths):
    buffer = BytesIO()
    with tarfile.open(fileobj=buffer, mode="w:gz") as archive:
        for path in sorted(backup_paths, key=lambda p: p.name):
            data = path.read_bytes()
            info = tarfile.TarInfo(path.name)
            info.size = len(data)
            info.mtime = 0
            info.mode = 0o600
            archive.addfile(info, BytesIO(data))
    return buffer.getvalue()


def _verify_database(path):
    with closing(sqlite3.connect(path)) as con:
        assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok", path
        assert con.execute("PRAGMA foreign_key_check").fetchall() == [], path


def main():
    with tempfile.TemporaryDirectory(prefix="synergy-cross-register-dr-") as directory:
        root = Path(directory)
        live = root / "live"
        backup_dir = root / "backup"
        quarantine = root / "quarantine"
        live.mkdir()
        backup_dir.mkdir()
        quarantine.mkdir()

        coordinator, participants = _open(live)
        operations = _operations()
        coordinator.submit(
            "cross-register-dr-001", "scenario-dr-001",
            "causation-dr-001", operations,
        )
        coordinator.execute("cross-register-dr-001")
        assert coordinator.is_visible("cross-register-dr-001")
        for participant in participants.values():
            assert participant.event_count("cross-register-dr-001") == 1

        live_paths = [live / "coordinator.sqlite3"] + [
            live / f"{name}.sqlite3" for name in PARTICIPANTS
        ]
        backup_paths = []
        for path in live_paths:
            target = backup_dir / path.name
            _backup_database(path, target)
            backup_paths.append(target)

        bundle = _backup_bundle(backup_paths)
        bundle_path = backup_dir / "all-registers-backup.tar.gz"
        bundle_path.write_bytes(bundle)
        backup_digest = sha256_bytes(bundle)

        signer = Ed25519Signer.generate("synergy-dr-recovery-key")
        trust = TrustedKeyRegistry({signer.key_id: signer.public_bytes()})
        with closing(sqlite3.connect(coordinator.database_path)) as con:
            envelope_json = con.execute(
                "SELECT envelope_json FROM coordinator_transactions WHERE transaction_id=?",
                ("cross-register-dr-001",),
            ).fetchone()[0]
        event_root = sha256_bytes(envelope_json.encode("utf-8"))
        receipt_inventory = sorted(
            (name, participants[name].status("cross-register-dr-001")["receipt_json"])
            for name in PARTICIPANTS
        )
        projection_hash = sha256_bytes(
            json.dumps(receipt_inventory, sort_keys=True, separators=(",", ":")).encode("utf-8")
        )
        manifest = {
            "service_id": "synergy-six-register-protocol",
            "database_schema_version": 1,
            "mapper_version": "cross-register-coordinator-protocol@1",
            "projection_generation": 0,
            "commit_sequence": 1,
            "event_count": 6,
            "event_log_root": event_root,
            "instrument_opening_hash": hashlib.sha256(b"protocol-fixture-instrument-openings").hexdigest(),
            "control_opening_hash": hashlib.sha256(b"protocol-fixture-control-openings").hexdigest(),
            "projection_state_hash": projection_hash,
            "coverage_count": 6,
            "applied_through_cursor": 1,
            "period": 0,
            "period_closed": False,
            "backup_sha256": backup_digest,
            "checkpoint_sequence": 1,
            "created_at_utc": "2026-11-12T10:59:00Z",
            "signer_key_id": signer.key_id,
        }
        anchor = LocalImmutableAnchor(root / "external-anchor.sqlite3")
        checkpoint_ref, checkpoint_digest = publish_checkpoint(manifest, signer, anchor)
        verified_manifest = verify_checkpoint(checkpoint_ref, checkpoint_digest, trust, anchor)
        assert verified_manifest == manifest
        assert verify_backup_bytes(verified_manifest, bundle)

        # Corrupt every live protocol database only after its WAL has been
        # checkpointed and a separately verified backup has been produced.
        for path in live_paths:
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(path) + suffix)
                if sidecar.exists():
                    assert sidecar.stat().st_size == 0, f"non-empty sidecar before quarantine: {sidecar}"
                    sidecar.unlink()
            quarantined = quarantine / path.name
            shutil.move(path, quarantined)
            path.write_bytes(b"CORRUPTED-PRIMARY-IMAGE")

        start = time.perf_counter()
        for path in live_paths:
            corrupted = path.read_bytes()
            assert corrupted == b"CORRUPTED-PRIMARY-IMAGE"
            path.unlink()
            shutil.copy2(backup_dir / path.name, path)
            _verify_database(path)
        restore_seconds = time.perf_counter() - start

        # Re-open every independent participant and coordinator after restore.
        restored_coordinator, restored_participants = _open(live)
        assert verify_checkpoint(checkpoint_ref, checkpoint_digest, trust, anchor) == manifest
        assert verify_backup_bytes(manifest, bundle)
        assert restored_coordinator.recover("cross-register-dr-001") == "COMMITTED"
        assert restored_coordinator.is_visible("cross-register-dr-001")
        for name, participant in restored_participants.items():
            assert participant.event_count("cross-register-dr-001") == 1
            with closing(sqlite3.connect(participant.database_path)) as con:
                row = con.execute(
                    "SELECT native_event_id,payload_json FROM participant_events WHERE transaction_id=?",
                    ("cross-register-dr-001",),
                ).fetchone()
                assert row[0] == f"{name}-dr-event-001"
                assert json.loads(row[1]) == operations[name]["payload"]

        assert restored_coordinator.recover("cross-register-dr-001") == "COMMITTED"
        for participant in restored_participants.values():
            assert participant.event_count("cross-register-dr-001") == 1

        print("PASS: seven independent SQLite online backups passed integrity and foreign-key checks")
        print("PASS: Ed25519 checkpoint anchored the combined backup package digest")
        print("PASS: all corrupted primaries quarantined and restored from verified backups")
        print("PASS: all six participant receipts and native payloads survived restore")
        print("PASS: commit barrier and repeated recovery preserve exactly one effect per register")
        print(f"RESTORE_DURATION_SECONDS={restore_seconds:.6f}")
        print("LIMIT: protocol-store DR conformance only; authoritative domain DBs and remote WORM remain external gates")


if __name__ == "__main__":
    main()
