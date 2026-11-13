"""Regression tests for coordinator-consistent six-register backup snapshots."""
from pathlib import Path
import json
import tarfile
import tempfile
import threading
import unittest
from io import BytesIO
from unittest.mock import patch

from create_six_register_backup import KEYS, create_backup
from verify_six_register_backup import _extract_verified
from cross_register_coordinator import _exclusive_process_lock


def _hold_lock(path, entered, release):
    with _exclusive_process_lock(path):
        entered.set()
        if not release.wait(5):
            raise RuntimeError("test lock release timed out")


class SixRegisterBackupLockTests(unittest.TestCase):
    def test_restore_rejects_archive_without_snapshot_consistency_proof(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "legacy-backup.tar.gz"
            manifest = {
                "schema": "synergy.six-register-backup.v1",
                "registers_verified": 6,
            }
            with tarfile.open(archive_path, "w:gz") as archive:
                for key in KEYS:
                    data = b"placeholder"
                    info = tarfile.TarInfo(f"{key}.sqlite3")
                    info.size = len(data)
                    archive.addfile(info, BytesIO(data))
                raw = json.dumps(manifest).encode("utf-8")
                info = tarfile.TarInfo("backup-manifest.json")
                info.size = len(raw)
                archive.addfile(info, BytesIO(raw))
            with self.assertRaisesRegex(RuntimeError, "snapshot consistency"):
                _extract_verified(archive_path, root / "restore")

    def test_backup_waits_for_coordinator_execution_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            paths = {}
            for key in KEYS:
                path = root / f"{key}.sqlite3"
                path.touch()
                paths[key] = path
            coordinator = paths["coordinator"]
            lock_path = coordinator.with_name(coordinator.name + ".execution-lock.sqlite3")
            entered = threading.Event()
            release = threading.Event()
            blocker = threading.Thread(target=_hold_lock, args=(lock_path, entered, release))
            blocker.start()
            self.assertTrue(entered.wait(2), "coordinator lock holder did not start")

            completed = threading.Event()
            failures = []

            def run_backup():
                try:
                    with patch("create_six_register_backup._snapshot", return_value=b"sqlite-snapshot"), \
                         patch("create_six_register_backup._coordinator_evidence",
                               return_value={"event_root": "a" * 64, "committed_transactions": 1}):
                        create_backup(paths, root / "backup.tar.gz")
                except BaseException as exc:
                    failures.append(exc)
                finally:
                    completed.set()

            worker = threading.Thread(target=run_backup)
            worker.start()
            try:
                self.assertFalse(completed.wait(0.25),
                                 "backup bypassed the coordinator execution lock")
            finally:
                release.set()
            blocker.join(2)
            worker.join(5)
            self.assertFalse(blocker.is_alive(), "lock holder did not exit")
            self.assertTrue(completed.is_set(), "backup did not resume after lock release")
            self.assertFalse(failures, f"backup failed: {failures}")
            self.assertTrue((root / "backup.tar.gz").is_file())


if __name__ == "__main__":
    unittest.main()
