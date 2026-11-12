"""Real subprocess crash matrix for the durable cross-register protocol core.

The six SQLite participants are independent durable protocol stores. This
validates coordinator recovery semantics; domain-register adapter integration
is a separate gate and is deliberately not inferred from this test.
"""
from pathlib import Path
import os
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from cross_register_coordinator import (
    CRASH_EXIT, PARTICIPANTS, CoordinatorError, CrossRegisterCoordinator, SQLiteParticipant,
)


def _paths(root):
    participants = {
        name: SQLiteParticipant(name, root / f"{name}.sqlite3")
        for name in PARTICIPANTS
    }
    coordinator = CrossRegisterCoordinator(root / "coordinator.sqlite3", participants)
    return coordinator, participants


def _operations():
    return {
        name: {
            "stream_id": f"{name}-stream",
            "native_event_id": f"{name}-event-001",
            "expected_revision": 0,
            "payload": {
                "register": name,
                "native_event_id": f"{name}-event-001",
                "typed_value": {"quantity": "3.25", "unit": "t"} if name == "physical"
                    else {"record": f"{name}-fixture"},
            },
        }
        for name in PARTICIPANTS
    }


def _child(root, crash_point):
    os.environ["SYNERGY_COORDINATOR_CRASH_AT"] = crash_point
    coordinator, _ = _paths(Path(root))
    coordinator.execute("coordinator-crash-matrix-001")
    raise AssertionError(f"crash point was not reached: {crash_point}")


def _negative_controls():
    with tempfile.TemporaryDirectory(prefix="synergy-coord-negative-") as directory:
        root = Path(directory)
        coordinator, participants = _paths(root)
        operations = _operations()
        assert coordinator.submit(
            "coordinator-negative-001", "scenario-negative",
            "negative-control", operations,
        ) is True
        assert coordinator.submit(
            "coordinator-negative-001", "scenario-negative",
            "negative-control", operations,
        ) is False

        changed = _operations()
        changed["physical"]["payload"]["quantity"] = "999"
        try:
            coordinator.submit(
                "coordinator-negative-001", "scenario-negative",
                "negative-control", changed,
            )
        except CoordinatorError:
            pass
        else:
            raise AssertionError("changed-content transaction ID reuse was accepted")

        coordinator.execute("coordinator-negative-001")
        assert coordinator.is_visible("coordinator-negative-001")
        physical = participants["physical"]
        token = physical.status("coordinator-negative-001")["prepare_token"]
        receipt = physical.commit("coordinator-negative-001", token)
        assert receipt["native_event_id"] == "physical-event-001"
        assert physical.event_count("coordinator-negative-001") == 1

        with sqlite3.connect(root / "coordinator.sqlite3") as con:
            states = [row[0] for row in con.execute(
                "SELECT to_state FROM coordinator_transitions "
                "WHERE transaction_id=? ORDER BY transition_id",
                ("coordinator-negative-001",),
            )]
        assert states == ["NEW", "PREPARING", "PREPARED", "COMMIT_DECIDED",
                          "COMMITTING", "COMMITTED"], states

        stale = _operations()
        for name in PARTICIPANTS:
            stale[name]["native_event_id"] = f"{name}-event-stale"
        coordinator.submit(
            "coordinator-negative-002", "scenario-negative",
            "stale-revision-control", stale,
        )
        try:
            coordinator.execute("coordinator-negative-002")
        except Exception:
            pass
        else:
            raise AssertionError("stale participant revision was accepted")
        assert coordinator.state("coordinator-negative-002") == "ABORTED"
        for participant in participants.values():
            assert participant.event_count("coordinator-negative-002") == 0

    print("PASS: changed-content replay rejected; identical submit and commit are idempotent")
    print("PASS: immutable coordinator transition history records the decision barrier")
    print("PASS: stale participant revision aborts the pre-decision transaction")


def _run_parent():
    crash_points = []
    for name in PARTICIPANTS:
        crash_points.extend((
            f"after_prepare:{name}",
            f"after_prepare_receipt:{name}",
            f"after_commit:{name}",
            f"after_commit_receipt:{name}",
        ))
    crash_points.append("after_commit_barrier")

    for index, point in enumerate(crash_points):
        with tempfile.TemporaryDirectory(prefix=f"synergy-coord-{index}-") as directory:
            root = Path(directory)
            coordinator, participants = _paths(root)
            coordinator.submit(
                "coordinator-crash-matrix-001", "scenario-crash-matrix",
                "audit-crash-matrix", _operations(),
            )
            env = os.environ.copy()
            env["SYNERGY_COORDINATOR_CRASH_AT"] = point
            result = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--child",
                 str(root), point],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False,
            )
            assert result.returncode == CRASH_EXIT, (
                f"{point}: expected process exit {CRASH_EXIT}, got "
                f"{result.returncode}; stderr={result.stderr[-1500:]}"
            )

            # Recreate all participant/coordinator objects after process death.
            recovered, participants = _paths(root)
            assert not recovered.is_visible("coordinator-crash-matrix-001"), (
                f"{point}: partially committed transaction crossed read barrier"
            )
            state = recovered.recover("coordinator-crash-matrix-001")
            predecision = point.startswith(("after_prepare:", "after_prepare_receipt:"))
            if predecision:
                assert state == "ABORTED", f"{point}: pre-decision recovery must abort"
                expected_events = 0
            else:
                assert state == "COMMITTED", f"{point}: post-decision recovery must commit"
                expected_events = 1

            for name, participant in participants.items():
                status = participant.status("coordinator-crash-matrix-001")
                assert participant.event_count("coordinator-crash-matrix-001") == expected_events, (
                    f"{point}: {name} has an unexpected number of native effects"
                )
                if expected_events:
                    assert status and status["state"] == "COMMITTED"
                elif status:
                    assert status["state"] in {"ABORTED"}
            if expected_events:
                assert recovered.is_visible("coordinator-crash-matrix-001"), (
                    f"{point}: complete transaction failed commit barrier verification"
                )
            assert recovered.recover("coordinator-crash-matrix-001") == state
            for participant in participants.values():
                assert participant.event_count("coordinator-crash-matrix-001") == expected_events

    _negative_controls()
    print(f"PASS: {len(crash_points)} subprocess termination points")
    print("PASS: pre-COMMIT_DECIDED recovery aborts all prepared participants")
    print("PASS: post-COMMIT_DECIDED recovery completes all six participants")
    print("PASS: no partial transaction crosses the coordinator visibility barrier")
    print("PASS: repeated recovery is idempotent; no duplicate native event effects")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        _child(sys.argv[2], sys.argv[3])
    else:
        _run_parent()
