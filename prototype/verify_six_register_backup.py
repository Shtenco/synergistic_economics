"""Verify a restored six-register SQLite backup, coordinator chain and native receipts."""
from __future__ import annotations
from pathlib import Path
from io import BytesIO
import argparse, hashlib, json, sqlite3, tarfile, tempfile

from physical_flow_store import PhysicalFlowStore
from capital_cohort_store import CapitalCohortStore
from labour_register import LabourRegister
from product_register import ProductRegister
from legal_rights_register import LegalRightsRegister
from financial_event_store import FinancialEventStore
from sfc_projection_store import verify_projection_replay
from cross_register_coordinator import _verify_event_group_chain

REGISTERS=("physical","capital","labour","product","legal_rights","financial")
DB_FILES={name:f"{name}.sqlite3" for name in REGISTERS}
DB_FILES["coordinator"]="coordinator.sqlite3"

def _sha(data): return hashlib.sha256(data).hexdigest()

def _extract_verified(archive_path, destination):
    expected=set(DB_FILES.values())|{"backup-manifest.json"}
    with tarfile.open(archive_path,"r:gz") as archive:
        members=archive.getmembers()
        names=[m.name for m in members]
        if set(names)!=expected or len(names)!=len(expected):
            raise RuntimeError("backup archive must contain exactly seven SQLite stores and backup-manifest.json")
        for member in members:
            if not member.isfile() or member.name.startswith("/") or ".." in Path(member.name).parts:
                raise RuntimeError("backup archive contains an unsafe member")
            target=destination/member.name
            with archive.extractfile(member) as source, target.open("wb") as sink:
                sink.write(source.read())
    manifest=json.loads((destination/"backup-manifest.json").read_text(encoding="utf-8"))
    if manifest.get("schema")!="synergy.six-register-backup.v1" or manifest.get("registers_verified")!=6:
        raise RuntimeError("backup manifest schema or register count is invalid")
    if manifest.get("snapshot_consistency")!="coordinator-exclusive-lock-v1":
        raise RuntimeError("backup does not prove coordinator-locked cross-register snapshot consistency")
    for name in DB_FILES.values():
        raw=(destination/name).read_bytes()
        record=manifest.get("files",{}).get(name)
        if not isinstance(record,dict) or record.get("sha256")!=_sha(raw) or record.get("size_bytes")!=len(raw):
            raise RuntimeError(f"backup file digest/size mismatch: {name}")
        con=sqlite3.connect(str(destination/name))
        try:
            if con.execute("PRAGMA integrity_check").fetchone()[0]!="ok":
                raise RuntimeError(f"SQLite integrity check failed: {name}")
            if con.execute("PRAGMA foreign_key_check").fetchall():
                raise RuntimeError(f"SQLite foreign-key check failed: {name}")
        finally: con.close()
    return manifest

def _native_event_exists(register, con, inbox):
    native_id=inbox["native_event_id"]
    if register=="physical":
        return con.execute("SELECT 1 FROM physical_flows WHERE flow_id=?",(native_id,)).fetchone() is not None
    if register=="capital":
        envelope=json.loads(inbox["payload_json"])
        period=envelope["payload"]["period"]
        return con.execute("SELECT 1 FROM capital_cohort_periods WHERE period=?",(period,)).fetchone() is not None
    if register in ("labour","legal_rights"):
        return con.execute("SELECT 1 FROM register_events WHERE event_id=?",(native_id,)).fetchone() is not None
    if register=="product":
        return con.execute("SELECT 1 FROM product_events WHERE event_id=?",(native_id,)).fetchone() is not None
    if register=="financial":
        return con.execute("SELECT 1 FROM event_groups WHERE group_id=?",(native_id,)).fetchone() is not None
    raise RuntimeError(f"unknown native register: {register}")

def verify_bundle(archive_path):
    with tempfile.TemporaryDirectory(prefix="synergy-restore-") as tmp:
        root=Path(tmp)
        manifest=_extract_verified(archive_path,root)
        physical=PhysicalFlowStore(root/DB_FILES["physical"])
        capital=CapitalCohortStore(root/DB_FILES["capital"])
        labour=LabourRegister(root/DB_FILES["labour"])
        product=ProductRegister(root/DB_FILES["product"])
        rights=LegalRightsRegister(root/DB_FILES["legal_rights"])
        financial=FinancialEventStore(root/DB_FILES["financial"])
        store_checks={
            "physical":physical.verify(),"capital":capital.verify(),"labour":labour.verify(),
            "product":product.verify(),"legal_rights":rights.verify(),
            "financial":financial.integrity_check() and verify_projection_replay(financial),
        }
        if not all(store_checks.values()):
            raise RuntimeError(f"native register replay/integrity verification failed: {store_checks}")

        coordinator_path=root/DB_FILES["coordinator"]
        coord=sqlite3.connect(str(coordinator_path)); coord.row_factory=sqlite3.Row
        participant_connections={}
        try:
            if not _verify_event_group_chain(coord): raise RuntimeError("coordinator event-group hash chain is invalid")
            unresolved=coord.execute("SELECT COUNT(*) FROM coordinator_transactions WHERE state NOT IN ('COMMITTED','ABORTED')").fetchone()[0]
            if unresolved: raise RuntimeError(f"coordinator contains {unresolved} unresolved transactions")
            committed=coord.execute("SELECT transaction_id FROM coordinator_transactions WHERE state='COMMITTED' ORDER BY transaction_id").fetchall()
            groups=coord.execute("SELECT transaction_id,payload_json,group_hash FROM coordinator_event_groups ORDER BY commit_sequence").fetchall()
            if len(committed)!=len(groups) or len(groups)!=manifest.get("committed_transactions"):
                raise RuntimeError("coordinator committed transaction count differs from backup manifest")
            for register in REGISTERS:
                con=sqlite3.connect(str(root/DB_FILES[register])); con.row_factory=sqlite3.Row
                participant_connections[register]=con
            for tx in committed:
                txid=tx["transaction_id"]
                operations=coord.execute("SELECT * FROM coordinator_operations WHERE transaction_id=? ORDER BY participant",(txid,)).fetchall()
                if {op["participant"] for op in operations}!=set(REGISTERS) or len(operations)!=6:
                    raise RuntimeError(f"transaction {txid} does not contain exactly six participant operations")
                group_row=next((g for g in groups if g["transaction_id"]==txid),None)
                if group_row is None: raise RuntimeError(f"committed transaction {txid} has no event group")
                group=json.loads(group_row["payload_json"])
                if group.get("common_event_id")!=txid or {e.get("register_id") for e in group.get("events",[])}!=set(REGISTERS):
                    raise RuntimeError(f"transaction {txid} canonical event group is incomplete")
                for event in group["events"]:
                    sid,sv=event.get("event_schema_id"),event.get("event_schema_version")
                    if (sid is None)!=(sv is None) or (sid is not None and (sid!="synergy.native-register-event" or sv!=1)):
                        raise RuntimeError(f"transaction {txid} contains an invalid native event schema marker")
                for op in operations:
                    register=op["participant"]; con=participant_connections[register]
                    inbox=con.execute("SELECT * FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
                    if inbox is None or inbox["state"]!="COMMITTED" or op["state"]!="COMMITTED":
                        raise RuntimeError(f"transaction {txid} lacks a committed native receipt for {register}")
                    for field in ("stream_id","native_event_id","payload_digest","expected_revision","prepare_token"):
                        if inbox[field]!=op[field]: raise RuntimeError(f"participant receipt mismatch: {txid}/{register}/{field}")
                    if inbox["payload_json"]!=op["payload_json"] or not inbox["receipt_json"] or not op["receipt_json"]:
                        raise RuntimeError(f"participant payload/receipt missing or divergent: {txid}/{register}")
                    if json.loads(inbox["receipt_json"])!=json.loads(op["receipt_json"]):
                        raise RuntimeError(f"coordinator/native durable receipts differ: {txid}/{register}")
                    if not _native_event_exists(register,con,inbox):
                        raise RuntimeError(f"native domain event missing after commit: {txid}/{register}")
            latest=groups[-1]["group_hash"] if groups else "0"*64
            if latest!=manifest.get("event_root"): raise RuntimeError("coordinator event root differs from backup manifest")
        finally:
            for con in participant_connections.values(): con.close()
            coord.close()
        return {"status":"PASS","registers_verified":6,"event_root":manifest["event_root"],
            "committed_transactions":manifest["committed_transactions"],"native_receipts_verified":manifest["committed_transactions"]*6,
            "financial_projection_replay":"PASS","store_checks":store_checks}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("archive")
    args=parser.parse_args()
    result=verify_bundle(Path(args.archive))
    print(json.dumps(result,sort_keys=True))

if __name__=="__main__": main()
