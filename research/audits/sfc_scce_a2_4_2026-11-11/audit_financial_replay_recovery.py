#!/usr/bin/env python3
"""Read-only SFC-GOLD-2A financial replay and recovery audit.

This script imports no production Python module. It independently reads the
SQLite v4 event-group schema, verifies the group chain and normalized mirrors,
rebuilds positions, and compares them with the independent GOLD-2A oracle.
--self-test builds a schema-compatible synthetic database fixture; it is not
a test of the production FinancialEventStore append path.
"""
from collections import defaultdict
from contextlib import closing
from decimal import Decimal
import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

D = Decimal
ROOT = Path(__file__).resolve().parent
CORPUS = ROOT / "SFC_GOLD_2A_CORPUS.json"
ORACLE = ROOT / "audit_sfc_gold_2a_oracle.py"
GENESIS = hashlib.sha256(b"SYNERGY_FINANCIAL_EVENT_STORE_CHAIN_GENESIS_V1").hexdigest()
IDENTITY_FIELDS = ("instrument_id","instrument_class","holder_entity_id","holder_sector",
                   "issuer_entity_id","issuer_sector","currency","maturity",
                   "denomination","valuation_basis")
NORMAL = {
    "loan_asset":"D","loan_liability":"C","impairment_allowance":"C",
    "interest_receivable":"D","interest_payable":"C",
    "deposit_asset":"D","deposit_liability":"C",
}
BALANCE_KEYS = tuple(NORMAL) + ("writeoff_memorandum","net_loan_carrying")


class RecoveryError(ValueError):
    pass


def canonical_json(value):
    return json.dumps(value, sort_keys=True, separators=(",",":"), ensure_ascii=False, allow_nan=False)


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chain_hash(sequence, group_id, payload_hash, previous):
    return sha(canonical_json({"commit_sequence":sequence,"group_id":group_id,
                               "payload_sha256":payload_hash,"previous_group_hash":previous}))


def verify_store(connection):
    version = connection.execute("PRAGMA user_version").fetchone()[0]
    if version != 4:
        raise RecoveryError(f"unsupported SQLite event-store schema version: {version}")
    if connection.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
        raise RecoveryError("SQLite integrity_check failed")
    if connection.execute("PRAGMA foreign_key_check").fetchall():
        raise RecoveryError("SQLite foreign-key check failed")
    groups = connection.execute(
        "SELECT group_id,causation_id,commit_sequence,previous_group_hash,group_chain_hash,payload_sha256,payload_json "
        "FROM event_groups ORDER BY commit_sequence").fetchall()
    previous = GENESIS
    all_events = []
    for seq,row in enumerate(groups,1):
        if row["commit_sequence"] != seq:
            raise RecoveryError("commit sequence gap or permutation")
        if sha(row["payload_json"]) != row["payload_sha256"]:
            raise RecoveryError("group payload hash mismatch")
        envelope = json.loads(row["payload_json"])
        if (canonical_json(envelope) != row["payload_json"] or
            envelope.get("group_id") != row["group_id"] or
            envelope.get("causation_id") != row["causation_id"]):
            raise RecoveryError("non-canonical or misidentified group envelope")
        if row["previous_group_hash"] != previous:
            raise RecoveryError("group predecessor hash mismatch")
        expected_hash = chain_hash(seq,row["group_id"],row["payload_sha256"],previous)
        if row["group_chain_hash"] != expected_hash:
            raise RecoveryError("group chain hash mismatch")
        events = envelope.get("events")
        if not isinstance(events,list) or not events:
            raise RecoveryError("empty or invalid event group")
        stored = connection.execute(
            "SELECT event_id,event_type,effective_period,event_index,payload_sha256,payload_json "
            "FROM events WHERE group_id=? ORDER BY event_index",(row["group_id"],)).fetchall()
        if len(stored) != len(events):
            raise RecoveryError("normalized event mirror count mismatch")
        for index,(event,dbrow) in enumerate(zip(events,stored)):
            payload = canonical_json(event)
            if (dbrow["event_index"] != index or dbrow["event_id"] != event.get("event_id") or
                dbrow["event_type"] != event.get("event_type") or
                dbrow["effective_period"] != event.get("effective_period") or
                dbrow["payload_json"] != payload or dbrow["payload_sha256"] != sha(payload)):
                raise RecoveryError("normalized event mirror mismatch")
            lines = connection.execute(
                "SELECT line_no,posting_json FROM journal_lines WHERE event_id=? ORDER BY line_no",
                (dbrow["event_id"],)).fetchall()
            postings = event.get("postings")
            if not isinstance(postings,list) or len(lines) != len(postings):
                raise RecoveryError("normalized posting mirror count mismatch")
            if [x["line_no"] for x in lines] != list(range(len(postings))):
                raise RecoveryError("posting line order gap")
            if [x["posting_json"] for x in lines] != [canonical_json(x) for x in postings]:
                raise RecoveryError("normalized posting mirror content mismatch")
        all_events.extend(events)
        previous = expected_hash
    return all_events, len(groups)


def verify_openings(connection, corpus):
    tables = {r[0] for r in connection.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    if not {"sfc_projection_meta","sfc_openings"}.issubset(tables):
        return {"persisted_openings":False,"status":"NO_PERSISTED_OPENING_REGISTRY"}
    meta = connection.execute(
        "SELECT projection_schema_version,state,snapshot_sha256,mapper_version,evidence_ref,opening_count "
        "FROM sfc_projection_meta WHERE singleton_id=1").fetchone()
    if meta is None:
        raise RecoveryError("SFC opening metadata row missing")
    rows = connection.execute(
        "SELECT instrument_id,instrument_class,holder_entity_id,holder_sector,issuer_entity_id,issuer_sector,"
        "currency,maturity,denomination,valuation_basis,period,amount,evidence_ref FROM sfc_openings").fetchall()
    normalized=[]
    for row in rows:
        identity={field:row[field] for field in IDENTITY_FIELDS}
        amount=D(row["amount"])
        if not amount.is_finite() or format(amount.normalize(),"f") != row["amount"]:
            raise RecoveryError("non-canonical persisted opening amount")
        normalized.append({"identity":identity,"period":row["period"],
                           "amount":row["amount"],"evidence_ref":row["evidence_ref"]})
    normalized.sort(key=lambda x:(tuple(x["identity"][f] for f in IDENTITY_FIELDS),x["period"]))
    snapshot_hash=sha(canonical_json(normalized))
    expected=corpus["opening_snapshot"]
    if (meta["projection_schema_version"] != 1 or meta["state"] != "prepared" or
        meta["mapper_version"] != expected["mapper_version"] or
        meta["evidence_ref"] != expected["evidence_ref"] or
        meta["opening_count"] != len(expected["rows"]) or
        normalized != sorted(expected["rows"],key=lambda x:(tuple(x["identity"][f] for f in IDENTITY_FIELDS),x["period"])) or
        snapshot_hash != meta["snapshot_sha256"]):
        raise RecoveryError("persisted SFC opening snapshot differs from frozen corpus")
    return {"persisted_openings":True,"status":"PERSISTED_OPENINGS_VERIFIED","snapshot_sha256":snapshot_hash}


def metric_state(state):
    result={k:format(state[k].normalize(),"f") if state[k] else "0" for k in NORMAL}
    result["writeoff_memorandum"]=format(state["writeoff_memorandum"].normalize(),"f") if state["writeoff_memorandum"] else "0"
    result["net_loan_carrying"]=format((state["loan_asset"]-state["impairment_allowance"]).normalize(),"f")
    return result


def rebuild(events, corpus):
    state={k:D(corpus["opening_snapshot"]["balances"][k]) for k in NORMAL}
    state["writeoff_memorandum"]=D(corpus["opening_snapshot"]["balances"]["writeoff_memorandum"])
    output=[]
    seen=set()
    for event in events:
        eid=event.get("event_id")
        if not eid or eid in seen:
            raise RecoveryError("duplicate or blank event ID during recovery")
        seen.add(eid)
        component=event["component"]
        for posting in event["postings"]:
            account=posting["account"]
            if account not in NORMAL:
                continue
            amount=D(posting["amount"])
            delta=amount if posting["side"]==NORMAL[account] else -amount
            state[account]+=delta
        if event["event_type"]=="creditor_write_off":
            state["writeoff_memorandum"]+=D(event["writeoff_claim_delta"])
        output.append({"after_event_id":eid,"balances":metric_state(state)})
    return output


def run_oracle(corpus_path, oracle_path):
    proc=subprocess.run([sys.executable,str(oracle_path),str(corpus_path),"--json"],
                        text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=60)
    if proc.returncode:
        raise RecoveryError("independent oracle failed: "+proc.stdout)
    return json.loads(proc.stdout)


def recover(database_path, corpus_path=CORPUS, oracle_path=ORACLE):
    corpus=json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    oracle=run_oracle(corpus_path,oracle_path)
    uri=Path(database_path).resolve().as_uri()+"?mode=ro"
    with closing(sqlite3.connect(uri,uri=True,isolation_level=None)) as connection:
        connection.row_factory=sqlite3.Row
        connection.execute("BEGIN")
        events,group_count=verify_store(connection)
        opening_report=verify_openings(connection,corpus)
        if [canonical_json(x) for x in events] != [canonical_json(x) for x in corpus["events"]]:
            raise RecoveryError("saved event groups differ from the frozen GOLD-2A event stream")
        recovered=rebuild(events,corpus)
        if recovered != oracle["replay_checkpoints"]:
            raise RecoveryError("recovered positions/checkpoints differ from independent oracle")
        snapshot_table=connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='sfc_position_snapshots'").fetchone()
        persisted_snapshots=False
        if snapshot_table:
            rows=connection.execute(
                "SELECT after_event_id,balances_json FROM sfc_position_snapshots ORDER BY snapshot_sequence").fetchall()
            saved=[{"after_event_id":r["after_event_id"],"balances":json.loads(r["balances_json"])} for r in rows]
            if saved != recovered:
                raise RecoveryError("persisted materialized position snapshots differ from replay")
            persisted_snapshots=True
        connection.execute("COMMIT")
    return {"status":"PASS" if opening_report["persisted_openings"] and persisted_snapshots else "PASS_WITH_LIMITATIONS",
            "group_count":group_count,"event_count":len(events),
            "opening_snapshot":opening_report["status"],
            "persisted_position_snapshots":persisted_snapshots,
            "replay_matches_independent_oracle":True,
            "final_balances":recovered[-1]["balances"],
            "limitations":[x for x,ok in (
                ("NO_PERSISTED_OPENING_REGISTRY",opening_report["persisted_openings"]),
                ("NO_PERSISTED_POSITION_SNAPSHOTS",persisted_snapshots)) if not ok]}


def create_fixture(path, corpus):
    """Create a schema-compatible fixture; does not call production append APIs."""
    connection=sqlite3.connect(path)
    connection.row_factory=sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.executescript("""
    CREATE TABLE event_groups(
      group_id TEXT PRIMARY KEY, causation_id TEXT, commit_sequence INTEGER UNIQUE NOT NULL,
      previous_group_hash TEXT NOT NULL, group_chain_hash TEXT NOT NULL,
      payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL);
    CREATE TABLE events(
      event_id TEXT PRIMARY KEY, group_id TEXT NOT NULL REFERENCES event_groups(group_id),
      event_type TEXT NOT NULL, effective_period INTEGER NOT NULL, event_index INTEGER NOT NULL,
      payload_sha256 TEXT NOT NULL, payload_json TEXT NOT NULL, UNIQUE(group_id,event_index));
    CREATE TABLE journal_lines(
      event_id TEXT NOT NULL REFERENCES events(event_id), line_no INTEGER NOT NULL,
      posting_json TEXT NOT NULL, PRIMARY KEY(event_id,line_no));
    CREATE TABLE sfc_projection_meta(
      singleton_id INTEGER PRIMARY KEY, projection_schema_version INTEGER NOT NULL,
      state TEXT NOT NULL, snapshot_sha256 TEXT NOT NULL, mapper_version TEXT NOT NULL,
      evidence_ref TEXT NOT NULL, opening_count INTEGER NOT NULL);
    CREATE TABLE sfc_openings(
      instrument_id TEXT NOT NULL,instrument_class TEXT NOT NULL,holder_entity_id TEXT NOT NULL,
      holder_sector TEXT NOT NULL,issuer_entity_id TEXT NOT NULL,issuer_sector TEXT NOT NULL,
      currency TEXT NOT NULL,maturity TEXT NOT NULL,denomination TEXT NOT NULL,
      valuation_basis TEXT NOT NULL,period INTEGER NOT NULL,amount TEXT NOT NULL,evidence_ref TEXT NOT NULL);
    """)
    connection.execute("PRAGMA user_version=4")
    group_id="GOLD2A-GROUP-001"
    causation="GOLD2A-CAUSE-001"
    envelope={"group_id":group_id,"causation_id":causation,"events":corpus["events"]}
    payload=canonical_json(envelope)
    payload_hash=sha(payload)
    group_hash=chain_hash(1,group_id,payload_hash,GENESIS)
    connection.execute("INSERT INTO event_groups VALUES(?,?,?,?,?,?,?)",
        (group_id,causation,1,GENESIS,group_hash,payload_hash,payload))
    for index,event in enumerate(corpus["events"]):
        event_json=canonical_json(event)
        connection.execute("INSERT INTO events VALUES(?,?,?,?,?,?,?)",
            (event["event_id"],group_id,event["event_type"],event["effective_period"],index,sha(event_json),event_json))
        for line_no,posting in enumerate(event["postings"]):
            connection.execute("INSERT INTO journal_lines VALUES(?,?,?)",
                (event["event_id"],line_no,canonical_json(posting)))
    rows=corpus["opening_snapshot"]["rows"]
    sorted_rows=sorted(rows,key=lambda x:(tuple(x["identity"][f] for f in IDENTITY_FIELDS),x["period"]))
    snapshot_hash=sha(canonical_json(sorted_rows))
    meta=corpus["opening_snapshot"]
    connection.execute("INSERT INTO sfc_projection_meta VALUES(1,1,'prepared',?,?,?,?)",
        (snapshot_hash,meta["mapper_version"],meta["evidence_ref"],len(rows)))
    for item in sorted_rows:
        ident=item["identity"]
        vals=tuple(ident[f] for f in IDENTITY_FIELDS)+(item["period"],item["amount"],item["evidence_ref"])
        connection.execute("INSERT INTO sfc_openings VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",vals)
    connection.commit()
    connection.close()


def main():
    args=sys.argv[1:]
    if "--self-test" in args:
        corpus=json.loads(CORPUS.read_text(encoding="utf-8"))
        with tempfile.TemporaryDirectory() as tmp:
            db=Path(tmp)/"gold2a-recovery.sqlite"
            create_fixture(db,corpus)
            result=recover(db)
        print("GOLD-2A recovery self-test: PASS (schema-compatible synthetic fixture)")
        print("verified event-group chain, normalized mirrors, opening snapshot and oracle replay")
        print("persisted materialized position snapshots: absent (reported limitation)")
        print("This does not test the production store append path or P2 atomic projection commit.")
        return 0
    if not args:
        print("usage: audit_financial_replay_recovery.py DATABASE [CORPUS] [ORACLE]",file=sys.stderr)
        return 2
    db=Path(args[0])
    corpus=Path(args[1]) if len(args)>1 else CORPUS
    oracle=Path(args[2]) if len(args)>2 else ORACLE
    result=recover(db,corpus,oracle)
    print(json.dumps(result,sort_keys=True,indent=2))
    return 0


if __name__=="__main__":
    raise SystemExit(main())
