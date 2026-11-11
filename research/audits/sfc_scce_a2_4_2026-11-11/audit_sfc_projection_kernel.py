"""Independent adversarial controls for the pure SFC projection kernel."""
from decimal import Decimal, getcontext
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3] if len(Path(__file__).resolve().parents) > 3 else Path("/")
PROTOTYPE = ROOT / "prototype"
sys.path.insert(0, str(PROTOTYPE if PROTOTYPE.is_dir() else Path(__file__).resolve().parent))

from sfc_projection_kernel import (
    SFCIdentity,
    SFCProjectionError,
    canonical_decimal,
    financial_net_lending,
    replay_positions,
)


def _delta(identity, event_id, index, period, component, amount, opening):
    return {
        "event_id": event_id,
        "delta_index": index,
        "effective_period": period,
        "identity": {field: getattr(identity, field)
                     for field in identity.__dataclass_fields__},
        "component": component,
        "amount": amount,
        "opening_balance": opening,
    }


def _must_reject(call, label):
    try:
        call()
    except SFCProjectionError:
        return
    raise AssertionError(f"invalid projection accepted: {label}")


def main():
    identity = SFCIdentity(
        "DEP-1", "deposit", "H-1", "H", "BANK-1", "CBank",
        "KZT", "ON_DEMAND", "NOMINAL", "PAR",
    )
    events = [
        {"event_id": "e1", "effective_period": 1},
        {"event_id": "e2", "effective_period": 1},
    ]
    projection = {
        "mapping_version": "test-mapper@1",
        "events": [
            {"event_id": "e1", "disposition": "mapped", "deltas": [
                _delta(identity, "e1", 0, 1, "T", "10.00", "100"),
                _delta(identity, "e1", 1, 1, "V", "5", "100"),
                _delta(identity, "e1", 2, 1, "O", "-2", "100"),
            ]},
            {"event_id": "e2", "disposition": "no_stock_effect", "deltas": []},
        ],
    }
    opening = {(identity, 1): "100"}
    result = replay_positions(
        events, projection, opening, nonnegative_identities={identity})
    position = result[(identity, 1)]
    assert position.opening == Decimal("100")
    assert position.transactions == Decimal("10")
    assert position.revaluations == Decimal("5")
    assert position.other_volume_changes == Decimal("-2")
    assert position.closing == Decimal("113")

    # Three-period continuity and the distinction between stock change and NL.
    period_events = [
        {"event_id": "p1", "effective_period": 1},
        {"event_id": "p2", "effective_period": 2},
        {"event_id": "p3", "effective_period": 3},
    ]
    period_projection = {"mapping_version": "test-mapper@1", "events": [
        {"event_id": "p1", "disposition": "mapped", "deltas": [
            _delta(identity, "p1", 0, 1, "T", "10", "100"),
            _delta(identity, "p1", 1, 1, "V", "5", "100"),
            _delta(identity, "p1", 2, 1, "O", "-2", "100"),
        ]},
        {"event_id": "p2", "disposition": "mapped", "deltas": [
            _delta(identity, "p2", 0, 2, "T", "-8", "113"),
            _delta(identity, "p2", 1, 2, "V", "-3", "113"),
            _delta(identity, "p2", 2, 2, "O", "1", "113"),
        ]},
        {"event_id": "p3", "disposition": "mapped", "deltas": [
            _delta(identity, "p3", 0, 3, "T", "0", "103"),
            _delta(identity, "p3", 1, 3, "V", "7", "103"),
            _delta(identity, "p3", 2, 3, "O", "0", "103"),
        ]},
    ]}
    multi = replay_positions(period_events, period_projection, {
        (identity, 1): "100", (identity, 2): "113", (identity, 3): "103",
    })
    assert [multi[(identity, p)].closing for p in (1, 2, 3)] == [
        Decimal("113"), Decimal("103"), Decimal("110")]
    assert financial_net_lending(["10", "-8", "0"], []) == Decimal("2")
    assert multi[(identity, 3)].closing - multi[(identity, 1)].opening == Decimal("10")
    assert canonical_decimal("1.000") == "1"
    assert canonical_decimal("-0.00") == "0"
    assert canonical_decimal("1E+3") == "1000"

    _must_reject(lambda: replay_positions(
        events, {"mapping_version": "m@1", "events": projection["events"][:1]}, opening),
        "missing event disposition")
    _must_reject(lambda: replay_positions(
        events, {"mapping_version": "m@1", "events": projection["events"] + [projection["events"][0]]}, opening),
        "duplicate event disposition")
    _must_reject(lambda: replay_positions(
        events, {"mapping_version": "m@1", "events": [
            {"event_id": "e1", "disposition": "mapped", "deltas": []}, projection["events"][1]]}, opening),
        "mapped event without deltas")
    _must_reject(lambda: replay_positions(
        events, {"mapping_version": "m@1", "events": [projection["events"][0], {
            "event_id": "e2", "disposition": "no_stock_effect", "deltas": [
                _delta(identity, "e2", 0, 1, "T", "1", "100")] }]}, opening),
        "no-stock-effect event with delta")
    _must_reject(lambda: replay_positions(
        events, {"mapping_version": "m@1", "events": [
            {"event_id": "e1", "disposition": "mapped", "deltas": [
                _delta(identity, "e1", 0, 2, "T", "1", "100")]}, projection["events"][1]]}, opening),
        "event-period mismatch")
    _must_reject(lambda: replay_positions(events, projection, {}),
        "missing explicit opening")
    _must_reject(lambda: replay_positions(
        events, {"mapping_version": "m@1", "events": [
            {"event_id": "e1", "disposition": "mapped", "deltas": [
                _delta(identity, "e1", 0, 1, "T", "1", "99")]}, projection["events"][1]]}, opening),
        "frozen opening mismatch")
    _must_reject(lambda: replay_positions(
        events, {"mapping_version": "m@1", "events": [
            {"event_id": "e1", "disposition": "mapped", "deltas": [
                _delta(identity, "e1", 0, 1, "T", 1.0, "100")]}, projection["events"][1]]}, opening),
        "binary float amount")
    _must_reject(lambda: replay_positions(
        events, {"mapping_version": "m@1", "events": [
            {"event_id": "e1", "disposition": "mapped", "deltas": [
                _delta(identity, "e1", 0, 1, "T", "-101", "100")]}, projection["events"][1]]},
        opening, nonnegative_identities={identity}), "negative gross closing position")
    _must_reject(lambda: replay_positions(
        period_events, period_projection,
        {(identity, 1): "100", (identity, 3): "113"}),
        "period gap")

    # Ambient Decimal precision must not silently round ledger accumulation.
    previous_precision = getcontext().prec
    try:
        getcontext().prec = 8
        exact = financial_net_lending(["12345678901234567890.123456789", "0.000000001"], [])
        assert exact == Decimal("12345678901234567890.123456790")
    finally:
        getcontext().prec = previous_precision

    print("A2.4.4 pure SFC projection kernel: PASS")
    print("T/V/O roll-forward, three-period continuity and transaction-only NL: PASS")
    print("per-event coverage and explicit no-stock-effect disposition: PASS")
    print("10 negative controls: PASS")
    print("exact Decimal accumulation under low ambient precision: PASS")


if __name__ == "__main__":
    main()
