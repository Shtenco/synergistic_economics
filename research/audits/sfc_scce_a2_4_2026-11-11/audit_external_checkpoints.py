"""Ed25519 checkpoint, trust-root, anti-rollback and backup digest audit."""
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from external_checkpoints import (
    CheckpointError, Ed25519Signer, LocalImmutableAnchor,
    TrustedKeyRegistry, publish_checkpoint, sha256_bytes,
    verify_backup_bytes, verify_checkpoint,
)


def _manifest(signer, sequence, backup):
    return {
        "manifest_schema_version": 1,
        "service_id": "synergy-test-ledger",
        "database_schema_version": 4,
        "mapper_version": "gold2a-entity-journal-mapper@1",
        "projection_generation": 2,
        "commit_sequence": sequence,
        "event_count": 24,
        "event_log_root": hashlib.sha256(b"event-root").hexdigest(),
        "instrument_opening_hash": hashlib.sha256(b"instrument-openings").hexdigest(),
        "control_opening_hash": hashlib.sha256(b"control-openings").hexdigest(),
        "projection_state_hash": hashlib.sha256(f"projection-{sequence}".encode()).hexdigest(),
        "coverage_count": 24,
        "applied_through_cursor": sequence,
        "period": 7,
        "period_closed": True,
        "backup_sha256": sha256_bytes(backup),
        "checkpoint_sequence": sequence,
        "created_at_utc": f"2026-11-12T10:{sequence:02d}:00Z",
        "signer_key_id": signer.key_id,
    }


def _rejects(call, message):
    try:
        call()
    except (CheckpointError, sqlite3.IntegrityError):
        return
    raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="synergy-checkpoint-") as directory:
        root = Path(directory)
        anchor = LocalImmutableAnchor(root / "independent-anchor.sqlite3")
        signer = Ed25519Signer.generate("synergy-ed25519-2026-01")
        trust = TrustedKeyRegistry({signer.key_id: signer.public_bytes()})
        backup1 = b"sqlite-online-backup-generation-2"
        manifest1 = _manifest(signer, 12, backup1)
        ref1, digest1 = publish_checkpoint(manifest1, signer, anchor)
        assert verify_checkpoint(ref1, digest1, trust, anchor) == manifest1
        assert verify_backup_bytes(manifest1, backup1)
        assert publish_checkpoint(manifest1, signer, anchor) == (ref1, digest1)
        _rejects(lambda: verify_backup_bytes(manifest1, b"tampered-backup"),
                 "backup bytes with wrong digest were accepted")

        _rejects(lambda: anchor.put_immutable(ref1, b"replacement"),
                 "immutable checkpoint object was overwritten")
        with sqlite3.connect(root / "independent-anchor.sqlite3") as con:
            _rejects(lambda: con.execute(
                "UPDATE checkpoint_objects SET object_bytes=? WHERE object_key=?",
                (b"tampered", ref1),
            ), "checkpoint object database accepted mutation")

        backup2 = b"sqlite-online-backup-generation-3"
        manifest2 = _manifest(signer, 13, backup2)
        ref2, digest2 = publish_checkpoint(manifest2, signer, anchor)
        assert verify_checkpoint(ref2, digest2, trust, anchor) == manifest2
        _rejects(lambda: verify_checkpoint(ref1, digest1, trust, anchor),
                 "older checkpoint was accepted after a newer external anchor")
        _rejects(lambda: anchor.advance_latest(manifest1["service_id"], 12, ref1, digest1),
                 "external latest sequence accepted a rollback")
        _rejects(lambda: anchor.advance_latest(manifest1["service_id"], 15, "gap-object", "0" * 64),
                 "external latest sequence accepted an unexplained gap")
        with sqlite3.connect(root / "independent-anchor.sqlite3") as con:
            _rejects(lambda: con.execute(
                "UPDATE checkpoint_history SET object_digest=? WHERE service_id=? AND checkpoint_sequence=?",
                ("0" * 64, manifest1["service_id"], 12),
            ), "immutable checkpoint sequence history was mutable")
        assert verify_checkpoint(ref1, digest1, trust, anchor, require_latest=False) == manifest1

        revoked = TrustedKeyRegistry({signer.key_id: signer.public_bytes()}, revoked={signer.key_id})
        _rejects(lambda: verify_checkpoint(ref2, digest2, revoked, anchor),
                 "revoked signing key was accepted")

        # A validly encoded object with an altered manifest but the old signature
        # must fail cryptographic verification even when it is the latest anchor.
        forged_anchor = LocalImmutableAnchor(root / "forged-anchor.sqlite3")
        envelope = json.loads(anchor.get(ref2))
        envelope["manifest"]["projection_state_hash"] = hashlib.sha256(b"forged").hexdigest()
        forged_bytes = json.dumps(envelope, sort_keys=True, separators=(",", ":"),
                                  ensure_ascii=False, allow_nan=False).encode()
        forged_ref = ref2
        forged_digest = sha256_bytes(forged_bytes)
        forged_anchor.put_immutable(forged_ref, forged_bytes)
        forged_anchor.advance_latest(manifest2["service_id"], 13, forged_ref, forged_digest)
        _rejects(lambda: verify_checkpoint(forged_ref, forged_digest, trust, forged_anchor),
                 "altered manifest with stale signature was accepted")

    print("PASS: Ed25519 signature and external trusted-key verification")
    print("PASS: immutable checkpoint object and monotonic anti-rollback anchor")
    print("PASS: backup artifact digest matches signed manifest")
    print("PASS: altered manifest, stale checkpoint and revoked key rejected")


if __name__ == "__main__":
    main()
