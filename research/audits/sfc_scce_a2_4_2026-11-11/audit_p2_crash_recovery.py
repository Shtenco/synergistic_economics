"""Subprocess crash/restart and SQLite backup-recovery audit for P2."""
from contextlib import closing
from pathlib import Path
from decimal import Decimal
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
AUDIT_DIR = ROOT / "research" / "audits" / "sfc_scce_a2_4_2026-11-11"
sys.path.insert(0, str(ROOT / "prototype"))
sys.path.insert(0, str(AUDIT_DIR))

from audit_financial_journal_adapter import _corpus_events
from audit_sfc_projection_store import _activate
from entity_journal import EntityJournal
from financial_event_store import FinancialEventStore
from sfc_projection_store import append_projected_group, verify_projection_replay

CRASH_EXIT = 83
STAGES = (
    "INSERT INTO EVENT_GROUPS",
    "INSERT INTO EVENTS(",
    "INSERT INTO JOURNAL_LINES",
    "INSERT INTO SFC_EVENT_COVERAGE",
    "INSERT INTO SFC_INSTRUMENT_DELTAS",
    "INSERT INTO SFC_CONTROL_DELTAS",
    "INSERT INTO SFC_PROJECTION_EVENT_CHECKPOINTS",
    "UPDATE SFC_PROJECTION_RUNTIME SET APPLIED_COMMIT_SEQUENCE",
    "INSERT INTO SFC_PROJECTION_GROUP_CHECKPOINTS",
    "COMMIT",
)


class CrashConnection(sqlite3.Connection):
    crash_stage = None

    def execute(self, sql, parameters=()):
        result = super().execute(sql, parameters)
        normalized = " ".join(str(sql).upper().split())
        if self.crash_stage and self.crash_stage in normalized:
            os._exit(CRASH_EXIT)
        return result


def _child(database, stage):
    registry, events = _corpus_events()
    store = FinancialEventStore(database)
    CrashConnection.crash_stage = stage

    def crash_connect():
        con = sqlite3.connect(
            store.database_path, timeout=store.timeout, isolation_level=None,
            factory=CrashConnection,
        )
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(f"PRAGMA busy_timeout={int(store.timeout * 1000)}")
        con.execute("PRAGMA synchronous=FULL")
        return con

    store._connect = crash_connect
    append_projected_group(
        EntityJournal(registry), store, "crash-restart-group", events,
        causation_id="crash-restart-audit",
    )
    raise AssertionError(f"crash stage was not reached: {stage}")


def _run_parent():
    registry, events = _corpus_events()
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for index, stage in enumerate(STAGES):
            database = root / f"crash-{index}.sqlite3"
            initial = FinancialEventStore(database)
            _activate(initial)
            completed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 "--crash-child", str(database), stage],
                cwd=ROOT, check=False, capture_output=True, text=True,
            )
            assert completed.returncode == CRASH_EXIT, (
                f"crash injection did not terminate at {stage}: "
                f"exit={completed.returncode}, stderr={completed.stderr[-1000:]}"
            )

            recovered = FinancialEventStore(database)
            if stage == "COMMIT":
                assert recovered.counts()["groups"] == 1
                assert recovered.counts()["events"] == len(events)
                assert verify_projection_replay(recovered), "committed transaction failed restart replay"
                assert append_projected_group(
                    EntityJournal(registry), recovered, "crash-restart-group", events,
                    causation_id="crash-restart-audit",
                ) is False
            else:
                assert recovered.counts() == {"groups": 0, "events": 0, "journal_lines": 0}, (
                    f"partial durable group after crash at {stage}"
                )
                assert append_projected_group(
                    EntityJournal(registry), recovered, "crash-restart-group", events,
                    causation_id="crash-restart-audit",
                ) is True
                assert verify_projection_replay(recovered), f"retry failed after crash at {stage}"

        # SQLite online backup is checked independently, then restored into a
        # fresh path and replay-verified. A corrupt primary must not be trusted.
        source_path = root / "backup-source.sqlite3"
        source = FinancialEventStore(source_path)
        _activate(source)
        assert append_projected_group(
            EntityJournal(registry), source, "backup-group", events,
            causation_id="backup-audit",
        )
        backup_path = root / "verified-backup.sqlite3"
        with closing(source._connect()) as src, closing(sqlite3.connect(backup_path)) as dst:
            src.backup(dst)
            assert dst.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        backup = FinancialEventStore(backup_path)
        assert verify_projection_replay(backup), "backup failed independent projection replay"

        # Replace the primary with an unmistakably invalid database image.
        corrupt_path = root / "corrupt-primary.sqlite3"
        corrupt_path.write_bytes(b"not-a-sqlite-database")
        try:
            FinancialEventStore(corrupt_path)
        except sqlite3.DatabaseError:
            pass
        else:
            raise AssertionError("corrupt database image was accepted")
        restored_path = root / "restored-from-backup.sqlite3"
        shutil.copy2(backup_path, restored_path)
        restored = FinancialEventStore(restored_path)
        assert verify_projection_replay(restored), "restored backup failed independent replay"
        assert restored.counts()["events"] == len(events)

    print("P2 subprocess crash/restart: PASS at every selected durable write boundary")
    print("pre-COMMIT crashes leave no partial group; post-COMMIT crash recovers committed group")
    print("idempotent retry after crash and independent replay verified")
    print("SQLite online backup integrity_check and replay-verified restore: PASS")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--crash-child":
        _child(sys.argv[2], sys.argv[3])
    else:
        _run_parent()
