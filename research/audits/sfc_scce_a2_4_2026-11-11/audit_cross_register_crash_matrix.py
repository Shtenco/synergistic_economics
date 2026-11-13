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


def _execute_child(root):
    coordinator, _ = _paths(Path(root))
    assert coordinator.execute("coordinator-concurrent-001") == "COMMITTED"


def _recover_child(root):
    coordinator, _ = _paths(Path(root))
    assert coordinator.recover("coordinator-concurrent-recovery-001") == "COMMITTED"


def _execute_recovery_race_child(root, action):
    coordinator, _ = _paths(Path(root))
    if action == "execute":
        assert coordinator.execute("coordinator-execute-recover-race-001") == "COMMITTED"
    elif action == "recover":
        assert coordinator.recover("coordinator-execute-recover-race-001") == "COMMITTED"
    else:
        raise AssertionError(f"unknown race action: {action}")


def _run_concurrency_controls():
    with tempfile.TemporaryDirectory(prefix="synergy-coord-concurrent-execute-") as directory:
        root = Path(directory)
        coordinator, participants = _paths(root)
        coordinator.submit(
            "coordinator-concurrent-001", "scenario-concurrent",
            "execute-vs-execute", _operations(),
        )
        workers = [
            subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--execute", str(root)],
                cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ) for _ in range(2)
        ]
        results = [worker.communicate(timeout=45) + (worker.returncode,) for worker in workers]
        assert all(code == 0 for _, _, code in results), results
        assert coordinator.state("coordinator-concurrent-001") == "COMMITTED"
        assert coordinator.is_visible("coordinator-concurrent-001")
        assert all(p.event_count("coordinator-concurrent-001") == 1 for p in participants.values())

    with tempfile.TemporaryDirectory(prefix="synergy-coord-concurrent-recover-") as directory:
        root = Path(directory)
        coordinator, participants = _paths(root)
        coordinator.submit(
            "coordinator-concurrent-recovery-001", "scenario-concurrent",
            "recover-vs-recover", _operations(),
        )
        env = os.environ.copy()
        env["SYNERGY_COORDINATOR_CRASH_AT"] = "after_commit_decision"
        crashed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), "--crash-recovery-setup", str(root)],
            cwd=ROOT, env=env, text=True, capture_output=True, check=False,
        )
        assert crashed.returncode == CRASH_EXIT, crashed.stderr[-1500:]
        workers = [
            subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--recover", str(root)],
                cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            ) for _ in range(2)
        ]
        results = [worker.communicate(timeout=45) + (worker.returncode,) for worker in workers]
        assert all(code == 0 for _, _, code in results), results
        recovered, participants = _paths(root)
        assert recovered.state("coordinator-concurrent-recovery-001") == "COMMITTED"
        assert recovered.is_visible("coordinator-concurrent-recovery-001")
        assert all(p.event_count("coordinator-concurrent-recovery-001") == 1
                   for p in participants.values())

    # A process that retries execute and another that performs recovery must
    # serialize around the same durable decision. Exercise both launch orders.
    for iteration in range(2):
        with tempfile.TemporaryDirectory(prefix="synergy-coord-execute-recover-race-") as directory:
            root = Path(directory)
            coordinator, _ = _paths(root)
            txid = "coordinator-execute-recover-race-001"
            coordinator.submit(txid, "scenario-execute-recover-race",
                               "execute-vs-recover", _operations())
            env = os.environ.copy()
            env["SYNERGY_COORDINATOR_CRASH_AT"] = "after_commit_decision"
            crashed = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()),
                 "--crash-recovery-setup", str(root)],
                cwd=ROOT, env=env, text=True, capture_output=True, check=False,
            )
            assert crashed.returncode == CRASH_EXIT, crashed.stderr[-1500:]
            actions = ["execute", "recover"] if iteration == 0 else ["recover", "execute"]
            workers = [
                subprocess.Popen(
                    [sys.executable, str(Path(__file__).resolve()),
                     "--execute-recover-race", str(root), action],
                    cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                ) for action in actions
            ]
            results = [worker.communicate(timeout=45) + (worker.returncode,)
                       for worker in workers]
            assert all(code == 0 for _, _, code in results), results
            recovered, participants = _paths(root)
            assert recovered.state(txid) == "COMMITTED"
            assert recovered.is_visible(txid)
            assert all(p.event_count(txid) == 1 for p in participants.values())


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
        # A lost client response followed by execute retry must return the
        # existing terminal result without adding transitions or native events.
        assert coordinator.execute("coordinator-negative-001") == "COMMITTED"
        assert participants["physical"].event_count("coordinator-negative-001") == 1
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
        except CoordinatorError:
            pass
        else:
            raise AssertionError("stale participant revision was accepted")
        assert coordinator.state("coordinator-negative-002") == "ABORTED"
        for participant in participants.values():
            assert participant.event_count("coordinator-negative-002") == 0
        assert coordinator.execute("coordinator-negative-002") == "ABORTED"

    # A receipt must not make a transaction visible if the native event row
    # has disappeared or been altered outside the participant API.
    with tempfile.TemporaryDirectory(prefix="synergy-coord-native-tamper-") as directory:
        root = Path(directory)
        coordinator, participants = _paths(root)
        coordinator.submit(
            "coordinator-native-tamper-001", "scenario-native-tamper",
            "native-tamper-control", _operations(),
        )
        assert coordinator.execute("coordinator-native-tamper-001") == "COMMITTED"
        assert coordinator.is_visible("coordinator-native-tamper-001")
        with sqlite3.connect(root / "physical.sqlite3") as con:
            con.execute("DROP TRIGGER participant_events_no_delete")
            con.execute(
                "DELETE FROM participant_events WHERE transaction_id=?",
                ("coordinator-native-tamper-001",),
            )
        assert not coordinator.is_visible("coordinator-native-tamper-001")
        try:
            coordinator.execute("coordinator-native-tamper-001")
        except CoordinatorError:
            pass
        else:
            raise AssertionError("committed retry accepted a missing native event")

    print("PASS: changed-content replay rejected; identical submit and execute are idempotent")
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
    crash_points.extend(("after_prepared_barrier", "after_commit_decision", "after_commit_barrier"))

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
            if point == "after_commit_barrier":
                assert recovered.is_visible("coordinator-crash-matrix-001"), (
                    "the durable COMMITTED barrier must expose all six verified participant effects"
                )
            else:
                assert not recovered.is_visible("coordinator-crash-matrix-001"), (
                    f"{point}: incomplete transaction crossed read barrier"
                )
            state = recovered.recover("coordinator-crash-matrix-001")
            predecision = point.startswith(("after_prepare:", "after_prepare_receipt:")) or point == "after_prepared_barrier"
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
            assert recovered.execute("coordinator-crash-matrix-001") == state
            for participant in participants.values():
                assert participant.event_count("coordinator-crash-matrix-001") == expected_events

    _negative_controls()
    _run_concurrency_controls()
    print(f"PASS: {len(crash_points)} subprocess termination points")
    print("PASS: pre-COMMIT_DECIDED recovery aborts all prepared participants")
    print("PASS: post-COMMIT_DECIDED recovery completes all six participants")
    print("PASS: no partial transaction crosses the coordinator visibility barrier")
    print("PASS: repeated recovery is idempotent; no duplicate native event effects")
    print("PASS: concurrent execute/execute and recover/recover workers are serialized")
    print("PASS: execute/recover races in both launch orders preserve one committed effect")


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "--child":
        _child(sys.argv[2], sys.argv[3])
    elif len(sys.argv) == 3 and sys.argv[1] == "--execute":
        _execute_child(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "--recover":
        _recover_child(sys.argv[2])
    elif len(sys.argv) == 3 and sys.argv[1] == "--crash-recovery-setup":
        os.environ["SYNERGY_COORDINATOR_CRASH_AT"] = "after_commit_decision"
        coordinator, _ = _paths(Path(sys.argv[2]))
        # Resolve the transaction from the durable database, not from a
        # process command's caller-supplied identity.
        with sqlite3.connect(Path(sys.argv[2]) / "coordinator.sqlite3") as con:
            rows = con.execute("SELECT transaction_id FROM coordinator_transactions").fetchall()
        if len(rows) != 1:
            raise AssertionError("crash setup requires exactly one transaction")
        coordinator.execute(rows[0][0])
        raise AssertionError("crash point was not reached")
    elif len(sys.argv) == 4 and sys.argv[1] == "--execute-recover-race":
        _execute_recovery_race_child(sys.argv[2], sys.argv[3])
    else:
        _run_parent()
