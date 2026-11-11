"""P1 opening activation: immutability, empty-store gate and fail-closed append."""
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "prototype"))

from financial_event_store import FinancialEventStore, FinancialEventStoreError
from sfc_projection_registry import (
    SFCProjectionRegistryError,
    activate_sfc_projection,
    verify_sfc_projection_openings,
)


def _opening(amount="0"):
    return {
        "identity": {
            "instrument_id": "DEP-1",
            "instrument_class": "deposit",
            "holder_entity_id": "H-1",
            "holder_sector": "H",
            "issuer_entity_id": "BANK-1",
            "issuer_sector": "CBank",
            "currency": "KZT",
            "maturity": "ON_DEMAND",
            "denomination": "NOMINAL",
            "valuation_basis": "PAR",
        },
        "period": 0,
        "amount": amount,
        "evidence_ref": "opening-ledger:control-1",
    }


def _event(event_id):
    return [{
        "event_id": event_id,
        "event_type": "control",
        "effective_period": 0,
        "postings": [{
            "account": "cash",
            "side": "D",
            "amount": "1",
            "entity_id": "H-1",
        }],
    }]


def _must_reject(fn, label, expected=Exception):
    try:
        fn()
    except expected:
        return
    raise AssertionError(f"expected rejection: {label}")


def main():
    with tempfile.TemporaryDirectory() as directory:
        empty_path = str(Path(directory) / "empty.sqlite")
        empty = FinancialEventStore(empty_path)
        assert activate_sfc_projection(
            empty, [_opening()], mapper_version="mapper@1",
            evidence_ref="snapshot:opening-0")
        assert not activate_sfc_projection(
            empty, [_opening("0.00")], mapper_version="mapper@1",
            evidence_ref="snapshot:opening-0")
        _must_reject(lambda: activate_sfc_projection(
            empty, [_opening("1")], mapper_version="mapper@1",
            evidence_ref="snapshot:opening-0"),
            "changed opening snapshot", SFCProjectionRegistryError)
        _must_reject(lambda: empty.append_group("legacy-path", _event("e-1")),
                     "legacy append after activation", FinancialEventStoreError)

        with sqlite3.connect(empty_path) as connection:
            assert verify_sfc_projection_openings(connection)
            count = connection.execute("SELECT COUNT(*) FROM sfc_openings").fetchone()[0]
            assert count == 1
            _must_reject(lambda: connection.execute(
                "UPDATE sfc_openings SET amount = '99'"),
                "opening row update", sqlite3.IntegrityError)
            _must_reject(lambda: connection.execute(
                "DELETE FROM sfc_openings"),
                "opening row delete", sqlite3.IntegrityError)

        legacy_path = str(Path(directory) / "legacy.sqlite")
        legacy = FinancialEventStore(legacy_path)
        assert legacy.append_group("g-1", _event("legacy-event"))
        _must_reject(lambda: activate_sfc_projection(
            legacy, [_opening()], mapper_version="mapper@1",
            evidence_ref="snapshot:opening-0"),
            "legacy non-empty store", SFCProjectionRegistryError)
        assert legacy.counts()["groups"] == 1
        assert legacy.integrity_check()
        assert legacy.append_group("g-2", _event("legacy-event-2"))

    print("P1 explicit SFC opening activation: PASS")
    print("empty-store-only activation and idempotent identical retry: PASS")
    print("changed snapshot and legacy-history activation rejected: PASS")
    print("opening immutability and hash verification: PASS")
    print("legacy append fail-closed after activation: PASS")


if __name__ == "__main__":
    main()
