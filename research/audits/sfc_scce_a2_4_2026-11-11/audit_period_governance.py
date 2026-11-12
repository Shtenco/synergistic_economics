"""Adversarial closed-period governance and generation-switch audit."""
from pathlib import Path
import hashlib
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from period_governance import (
    REGISTERS, PeriodGovernance, PeriodGovernanceError,
)


def _sha(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _rejects(call, message):
    try:
        call()
    except (PeriodGovernanceError, sqlite3.IntegrityError):
        return
    raise AssertionError(message)


def main():
    with tempfile.TemporaryDirectory(prefix="synergy-period-governance-") as directory:
        root = Path(directory)
        trusted = {
            "period-7-close": _sha("signed-close-generation-0"),
            "period-7-generation-1": _sha("signed-reopen-generation-1"),
        }
        verify = lambda ref, digest: trusted.get(ref) == digest
        governance = PeriodGovernance(root / "period-governance.sqlite3", verify)

        assert governance.close_period(
            7, 0, "period-7-close", trusted["period-7-close"], "controller-A"
        )
        assert not governance.close_period(
            7, 0, "period-7-close", trusted["period-7-close"], "controller-A"
        )
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
            "authority://reopen-001", scope,
            "period-7-close", trusted["period-7-close"],
        )
        assert not governance.approve_reopen(
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
        _rejects(lambda: governance.publish_generation(
            "reopen-001", _sha("global-reconciliation"),
            "period-7-generation-1", trusted["period-7-generation-1"],
        ), "generation published without all six register rebuild receipts")
        assert governance.active_generation(7) == 0

        governance.record_rebuild(
            "reopen-001", "financial", root_hash, 100,
            _sha("financial-opening"), _sha("financial-closing"),
            _sha("financial-reconciliation"),
        )
        assert governance.publish_generation(
            "reopen-001", _sha("global-reconciliation"),
            "period-7-generation-1", trusted["period-7-generation-1"],
        )
        assert governance.active_generation(7) == 1

        # The prior generation remains in the immutable history, and a second
        # reopen must bind to generation 1's checkpoint rather than generation 0.
        with sqlite3.connect(root / "period-governance.sqlite3") as con:
            history = con.execute(
                "SELECT generation,checkpoint_ref FROM generation_history "
                "WHERE period=7 ORDER BY generation"
            ).fetchall()
            assert history == [(0, "period-7-close"), (1, "period-7-generation-1")]
            _rejects(lambda: con.execute(
                "UPDATE period_closures SET generation=99 WHERE period=7"
            ), "closed-period snapshot was mutable")

        _rejects(lambda: governance.request_reopen(
            "reopen-stale", 7, "stale generation checkpoint",
            "authority://stale", scope, "period-7-close",
            trusted["period-7-close"],
        ), "reopen accepted stale generation checkpoint")
        assert governance.request_reopen(
            "reopen-002", 7, "second governed correction",
            "authority://reopen-002", scope,
            "period-7-generation-1", trusted["period-7-generation-1"],
        )
        assert governance.active_generation(7) == 1

    print("PASS: corrections append in an open period; closed period remains immutable")
    print("PASS: reopening requires two distinct approvers in separate roles")
    print("PASS: generation switch waits for all six same-root rebuild receipts")
    print("PASS: prior generation retained; repeated reopen binds to active generation checkpoint")


if __name__ == "__main__":
    main()
