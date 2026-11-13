"""Create a consistent SQLite online-backup bundle for all six native registers and coordinator."""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
from io import BytesIO
import argparse, hashlib, json, sqlite3, tarfile

from cross_register_coordinator import _verify_event_group_chain

KEYS=("physical","capital","labour","product","legal_rights","financial","coordinator")

def _sha(data): return hashlib.sha256(data).hexdigest()

def _snapshot(path):
    source=sqlite3.connect(str(path),timeout=60)
    target=sqlite3.connect(":memory:")
    try:
        source.backup(target,pages=256,sleep=0.01)
        integrity=target.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity!="ok": raise RuntimeError(f"SQLite backup integrity failure for {path}: {integrity}")
        return target.serialize()
    finally:
        target.close(); source.close()

def _coordinator_evidence(path):
    con=sqlite3.connect(str(path)); con.row_factory=sqlite3.Row
    try:
        if not _verify_event_group_chain(con): raise RuntimeError("coordinator event-group hash chain is invalid")
        unresolved=con.execute("SELECT COUNT(*) FROM coordinator_transactions WHERE state NOT IN ('COMMITTED','ABORTED')").fetchone()[0]
        if unresolved: raise RuntimeError(f"coordinator has {unresolved} unresolved transactions")
        committed=con.execute("SELECT COUNT(*) FROM coordinator_transactions WHERE state='COMMITTED'").fetchone()[0]
        groups=con.execute("SELECT COUNT(*) FROM coordinator_event_groups").fetchone()[0]
        if committed<1 or groups!=committed: raise RuntimeError("coordinator committed transactions and event groups do not match")
        row=con.execute("SELECT group_hash FROM coordinator_event_groups ORDER BY commit_sequence DESC LIMIT 1").fetchone()
        return {"event_root":row["group_hash"],"committed_transactions":committed}
    finally: con.close()

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--manifest",required=True)
    parser.add_argument("--output",required=True)
    args=parser.parse_args()
    config=json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    paths=config.get("database_paths")
    if not isinstance(paths,dict) or set(paths)!=set(KEYS):
        raise SystemExit(f"manifest database_paths must contain exactly: {', '.join(KEYS)}")
    files={}
    for key in KEYS:
        path=Path(paths[key]).expanduser()
        if not path.is_file(): raise SystemExit(f"authoritative database is missing: {key}")
        files[f"{key}.sqlite3"]=_snapshot(path)
    coordinator_path=Path(paths["coordinator"]).expanduser()
    evidence=_coordinator_evidence(coordinator_path)
    file_manifest={name:{"sha256":_sha(data),"size_bytes":len(data)} for name,data in sorted(files.items())}
    manifest={"schema":"synergy.six-register-backup.v1","created_at_utc":datetime.now(timezone.utc).isoformat(),
        "registers_verified":6,"files":file_manifest,"event_root":evidence["event_root"],
        "committed_transactions":evidence["committed_transactions"]}
    files["backup-manifest.json"]=json.dumps(manifest,sort_keys=True,separators=(",",":")).encode()
    output=Path(args.output).expanduser()
    output.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(output,"w:gz") as archive:
        for name,data in sorted(files.items()):
            info=tarfile.TarInfo(name); info.size=len(data); info.mode=0o600; info.mtime=0
            archive.addfile(info,BytesIO(data))
    archive_bytes=output.read_bytes()
    print(json.dumps({"status":"PASS","backup_path":str(output.resolve()),"backup_sha256":_sha(archive_bytes),
        "event_root":evidence["event_root"],"committed_transactions":evidence["committed_transactions"],
        "registers_verified":6,"archive_size_bytes":len(archive_bytes)},sort_keys=True))

if __name__=="__main__": main()
