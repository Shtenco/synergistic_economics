"""Structural and cross-record validation for canonical SYNERGY records.

This module checks data consistency, not legal validity or factual truth.
"""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parent
DEFAULT_SCHEMA = ROOT / "synergy-economy.schema.json"


def _parse_time(value: str | None, default: datetime) -> datetime:
    if value is None:
        return default
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def validate_records(records: list[dict[str, Any]], schema: dict[str, Any]) -> list[str]:
    """Return deterministic structural and cross-record validation errors."""
    issues: list[str] = []
    validator = Draft202012Validator(schema, format_checker=FormatChecker())

    for index, record in enumerate(records):
        for error in validator.iter_errors(record):
            path = ".".join(str(part) for part in error.absolute_path) or "$"
            issues.append(f"records[{index}].{path}: {error.message}")

    by_id: dict[str, dict[str, Any]] = {}
    for index, record in enumerate(records):
        record_id = record.get("id")
        if not isinstance(record_id, str):
            continue
        if record_id in by_id:
            issues.append(f"records[{index}].id: duplicate id {record_id!r}")
        else:
            by_id[record_id] = record

    entity_types = {"person", "household", "enterprise", "economic_cell", "federation"}
    reference_rules = {
        "household": {"memberIds": {"person"}},
        "enterprise": {
            "ownerClaimIds": {"ownership_claim"},
            "workerPersonIds": {"person"},
        },
        "economic_cell": {
            "memberEntityIds": entity_types,
            "enterpriseIds": {"enterprise"},
            "parentCellId": {"economic_cell"},
            "federationId": {"federation"},
            "reserveAccountIds": {"account"},
        },
        "federation": {"cellIds": {"economic_cell"}},
        "asset": {"custodianEntityId": entity_types},
        "project": {
            "sponsorEntityId": entity_types,
            "participantEntityIds": entity_types,
        },
        "account": {"ownerEntityId": entity_types},
        "contract": {"parties[].entityId": entity_types},
        "ownership_claim": {
            "assetId": {"asset"},
            "claimantEntityId": entity_types,
        },
        "contribution": {
            "contributorEntityId": entity_types,
            "projectId": {"project"},
        },
        "economic_event": {"actorEntityId": entity_types},
    }

    def check_ref(source_id: str, field: str, target_id: Any, allowed: set[str]) -> None:
        if target_id is None:
            return
        target = by_id.get(target_id)
        if target is None:
            issues.append(f"{source_id}.{field}: unresolved reference {target_id!r}")
        elif target.get("recordType") not in allowed:
            issues.append(
                f"{source_id}.{field}: expected {sorted(allowed)}, "
                f"got {target.get('recordType')!r} for {target_id!r}"
            )

    for record in records:
        source_id = record.get("id", "<missing-id>")
        kind = record.get("recordType")
        for field, allowed in reference_rules.get(kind, {}).items():
            if field == "parties[].entityId":
                for party_index, party in enumerate(record.get("parties", [])):
                    check_ref(source_id, f"parties[{party_index}].entityId",
                              party.get("entityId"), allowed)
                continue
            value = record.get(field)
            if isinstance(value, list):
                for item_index, target_id in enumerate(value):
                    check_ref(source_id, f"{field}[{item_index}]", target_id, allowed)
            else:
                check_ref(source_id, field, value, allowed)

        if kind == "economic_event":
            for index, target_id in enumerate(record.get("subjectEntityIds", [])):
                if target_id not in by_id:
                    issues.append(
                        f"{source_id}.subjectEntityIds[{index}]: "
                        f"unresolved reference {target_id!r}"
                    )

    seen_idempotency: dict[str, str] = {}
    for record in records:
        if record.get("recordType") != "economic_event":
            continue
        key = record.get("idempotencyKey")
        if not key:
            continue
        previous = seen_idempotency.get(key)
        if previous is not None:
            issues.append(
                f"{record.get('id')}.idempotencyKey: duplicate key {key!r} "
                f"also used by {previous!r}"
            )
        else:
            seen_idempotency[key] = record.get("id", "<missing-id>")

    # Shares are aggregated only within the same asset and right class.
    # Different right classes are not fungible and must never be summed together.
    ownership_groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        if record.get("recordType") != "ownership_claim":
            continue
        if record.get("rightType") not in {"legal_title", "beneficial_interest"}:
            continue
        if record.get("verificationStatus") not in {"document_checked", "registry_confirmed"}:
            continue
        if isinstance(record.get("share"), (int, float)):
            ownership_groups[(record.get("assetId"), record.get("rightType"))].append(record)

    earliest = datetime.min.replace(tzinfo=timezone.utc)
    latest = datetime.max.replace(tzinfo=timezone.utc)
    for (asset_id, right_type), claims in ownership_groups.items():
        boundaries = sorted({
            _parse_time(claim.get("validFrom"), earliest)
            for claim in claims
        } | {
            _parse_time(claim.get("validUntil"), latest)
            for claim in claims
        })
        for point in boundaries:
            active = [
                claim for claim in claims
                if _parse_time(claim.get("validFrom"), earliest) <= point
                and point < _parse_time(claim.get("validUntil"), latest)
            ]
            total = sum(claim["share"] for claim in active)
            if total > 1.000000001:
                issues.append(
                    f"asset {asset_id!r} {right_type}: overlapping verified "
                    f"claims sum to {total:.8f} at {point.isoformat()} (> 1)"
                )
                break

    return sorted(set(issues))


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate canonical SYNERGY records.")
    parser.add_argument("input", type=Path, help="JSON file with a records array")
    parser.add_argument("--schema", type=Path, default=DEFAULT_SCHEMA)
    args = parser.parse_args()

    schema = json.loads(args.schema.read_text(encoding="utf-8"))
    document = json.loads(args.input.read_text(encoding="utf-8"))
    records = document.get("records") if isinstance(document, dict) else None
    if not isinstance(records, list):
        parser.error("input must be a JSON object containing a records array")

    issues = validate_records(records, schema)
    if issues:
        print("\n".join(issues))
        return 1
    print(f"OK: {len(records)} records passed structural and cross-record checks.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
