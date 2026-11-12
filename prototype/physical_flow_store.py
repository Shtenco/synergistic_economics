"""Durable append-only physical-flow register with paired endpoints and replay verification.
Historical flows are immutable; corrections must be separately identified compensating flows."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from contextlib import closing
from decimal import Decimal
from datetime import datetime
import hashlib, json, sqlite3
from pathlib import Path

D = Decimal
EVIDENCE = {"measured", "documented", "estimated", "simulated"}
GENESIS = "0" * 64
DOMAIN = b"SYNERGY_PHYSICAL_FLOW_CHAIN_V1\0"


class PhysicalFlowError(ValueError):
    pass


@dataclass(frozen=True)
class FlowPosting:
    flow_id: str
    node_id: str
    role: str
    origin_node: str
    destination_node: str
    origin_boundary: str
    destination_boundary: str
    product_id: str
    grade_id: str
    quantity: D
    unit: str
    event_time: str
    period: str
    flow_class: str
    quality: str
    measurement_method: str
    uncertainty: D
    evidence_status: str
    correction_of: str | None = None
    correction_reason: str = ""


def _text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise PhysicalFlowError(f"{field} must be non-empty trimmed text")


def _decimal(value, field, positive=False):
    if isinstance(value, bool):
        raise PhysicalFlowError(f"{field} must be finite Decimal")
    try:
        result = D(str(value))
    except Exception as exc:
        raise PhysicalFlowError(f"{field} must be finite Decimal") from exc
    if not result.is_finite() or (positive and result <= 0):
        raise PhysicalFlowError(f"{field} must be finite" + (" and positive" if positive else ""))
    return result


def _aware_timestamp(value):
    _text(value, "event_time")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00" if value.endswith(("Z", "z")) else value)
    except ValueError as exc:
        raise PhysicalFlowError("event_time must be valid ISO 8601 with an explicit UTC offset") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PhysicalFlowError("event_time must be timezone-aware")
    return parsed


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _posting_dict(posting):
    row = asdict(posting)
    row["quantity"] = format(_decimal(posting.quantity, "quantity", True), "f")
    row["uncertainty"] = format(_decimal(posting.uncertainty, "uncertainty"), "f")
    return row


def validate_pair(outflow, inflow):
    if not isinstance(outflow, FlowPosting) or not isinstance(inflow, FlowPosting):
        raise PhysicalFlowError("both endpoints must be FlowPosting values")
    if outflow.role != "outflow" or inflow.role != "inflow":
        raise PhysicalFlowError("endpoint roles must be outflow then inflow")
    if outflow.flow_id != inflow.flow_id:
        raise PhysicalFlowError("flow_id mismatch")
    shared = ("origin_node","destination_node","origin_boundary","destination_boundary",
              "product_id","grade_id","quantity","unit","event_time","period","flow_class",
              "quality","measurement_method","uncertainty","evidence_status")
    for field in shared:
        if getattr(outflow, field) != getattr(inflow, field):
            raise PhysicalFlowError(f"endpoint {field} mismatch")
    if outflow.node_id != outflow.origin_node or inflow.node_id != inflow.destination_node:
        raise PhysicalFlowError("endpoint node does not match declared origin/destination")
    if outflow.origin_node == outflow.destination_node:
        raise PhysicalFlowError("self-transfer is invalid")
    for field in ("flow_id","origin_node","destination_node","origin_boundary","destination_boundary",
                  "product_id","grade_id","unit","event_time","period","flow_class","quality","measurement_method"):
        _text(getattr(outflow, field), field)
    _aware_timestamp(outflow.event_time)
    _decimal(outflow.quantity, "quantity", True)
    if _decimal(outflow.uncertainty, "uncertainty") < 0:
        raise PhysicalFlowError("uncertainty must be non-negative")
    if outflow.evidence_status not in EVIDENCE:
        raise PhysicalFlowError("unknown evidence_status")


class PhysicalFlowStore:
    SCHEMA_VERSION = 1

    def __init__(self, database_path):
        self.path = str(database_path)
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS physical_flow_meta(
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                    schema_version INTEGER NOT NULL CHECK(schema_version=1),
                    event_count INTEGER NOT NULL CHECK(event_count>=0), tail_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS physical_flows(
                    commit_sequence INTEGER PRIMARY KEY CHECK(commit_sequence>0),
                    flow_id TEXT NOT NULL UNIQUE, payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL, previous_hash TEXT NOT NULL, chain_hash TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS physical_flows_no_update BEFORE UPDATE ON physical_flows
                    BEGIN SELECT RAISE(ABORT,'physical flow events are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS physical_flows_no_delete BEFORE DELETE ON physical_flows
                    BEGIN SELECT RAISE(ABORT,'physical flow events are immutable'); END;
            """)
            con.execute("INSERT OR IGNORE INTO physical_flow_meta VALUES(1,1,0,?)", (GENESIS,))

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA synchronous=FULL")
        return con

    @staticmethod
    def _chain_hash(sequence, flow_id, digest, previous):
        value = {"sequence":sequence,"flow_id":flow_id,"payload_sha256":digest,"previous_hash":previous}
        return hashlib.sha256(DOMAIN + _canonical(value).encode()).hexdigest()

    def append(self, outflow, inflow):
        validate_pair(outflow, inflow)
        payload_json = _canonical({"outflow":_posting_dict(outflow),"inflow":_posting_dict(inflow)})
        digest = hashlib.sha256(payload_json.encode()).hexdigest()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute("SELECT payload_sha256 FROM physical_flows WHERE flow_id=?",
                                  (outflow.flow_id,)).fetchone()
                if old:
                    if old["payload_sha256"] != digest:
                        raise PhysicalFlowError("flow_id reused with changed immutable content")
                    con.execute("ROLLBACK")
                    if not self.verify():
                        raise PhysicalFlowError("identical retry refused: replay verification failed")
                    return False
                if outflow.correction_of is not None:
                    _text(outflow.correction_of, "correction_of")
                    _text(outflow.correction_reason, "correction_reason")
                    if outflow.correction_of == outflow.flow_id:
                        raise PhysicalFlowError("a correction cannot reference itself")
                    original = con.execute("SELECT payload_json FROM physical_flows WHERE flow_id=?",
                                           (outflow.correction_of,)).fetchone()
                    if original is None:
                        raise PhysicalFlowError("correction must reference an earlier recorded flow")
                    original_out = json.loads(original["payload_json"])["outflow"]
                    if (outflow.product_id, outflow.grade_id, outflow.unit) != (
                            original_out["product_id"], original_out["grade_id"], original_out["unit"]):
                        raise PhysicalFlowError("correction product, grade and unit must match original flow")
                    if (outflow.origin_node, outflow.destination_node) != (
                            original_out["destination_node"], original_out["origin_node"]):
                        raise PhysicalFlowError("compensating flow must reverse original endpoints")
                elif outflow.correction_reason:
                    raise PhysicalFlowError("correction_reason requires correction_of")
                meta = con.execute("SELECT event_count,tail_hash FROM physical_flow_meta WHERE singleton_id=1").fetchone()
                if meta is None:
                    raise PhysicalFlowError("physical flow metadata is missing")
                seq = meta["event_count"] + 1
                chain = self._chain_hash(seq,outflow.flow_id,digest,meta["tail_hash"])
                con.execute("INSERT INTO physical_flows VALUES(?,?,?,?,?,?)",
                            (seq,outflow.flow_id,payload_json,digest,meta["tail_hash"],chain))
                con.execute("UPDATE physical_flow_meta SET event_count=?,tail_hash=? WHERE singleton_id=1",
                            (seq,chain))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def _rows(self):
        with closing(self._connect()) as con:
            return con.execute("SELECT * FROM physical_flows ORDER BY commit_sequence").fetchall()

    def flow_count(self):
        if not self.verify():
            raise PhysicalFlowError("physical flow integrity verification failed; read refused")
        with closing(self._connect()) as con:
            return con.execute("SELECT COUNT(*) FROM physical_flows").fetchone()[0]

    def node_net(self, node_id, product_id, grade_id, period, unit):
        if not self.verify():
            raise PhysicalFlowError("physical flow integrity verification failed; read refused")
        for value, field in ((node_id,"node_id"),(product_id,"product_id"),(grade_id,"grade_id"),(period,"period"),(unit,"unit")):
            _text(value,field)
        total = D("0")
        for row in self._rows():
            payload = json.loads(row["payload_json"])
            out, inc = payload["outflow"], payload["inflow"]
            if (out["product_id"],out["grade_id"],out["period"]) != (product_id,grade_id,period):
                continue
            if unit is not None and out["unit"] != unit:
                continue
            if out["node_id"] == node_id: total -= D(out["quantity"])
            if inc["node_id"] == node_id: total += D(inc["quantity"])
        return total

    def consolidated_net(self, node_ids, product_id, grade_id, period, unit):
        if not self.verify():
            raise PhysicalFlowError("physical flow integrity verification failed; read refused")
        nodes=set(node_ids)
        if not nodes: raise PhysicalFlowError("consolidation requires at least one node")
        for node in nodes: _text(node,"node_id")
        rows = self._rows()
        total = D("0")
        for row in rows:
            payload = json.loads(row["payload_json"])
            out, inc = payload["outflow"], payload["inflow"]
            if (out["product_id"],out["grade_id"],out["period"],out["unit"]) != (product_id,grade_id,period,unit):
                continue
            if out["node_id"] in nodes: total -= D(out["quantity"])
            if inc["node_id"] in nodes: total += D(inc["quantity"])
        return total

    def verify(self):
        try:
            rows, previous, seen = self._rows(), GENESIS, set()
            for seq, row in enumerate(rows, 1):
                if row["commit_sequence"] != seq or row["previous_hash"] != previous:
                    return False
                payload = json.loads(row["payload_json"])
                if set(payload) != {"outflow","inflow"} or _canonical(payload) != row["payload_json"]:
                    return False
                digest = hashlib.sha256(row["payload_json"].encode()).hexdigest()
                if digest != row["payload_sha256"] or row["flow_id"] in seen:
                    return False
                out, inc = payload["outflow"], payload["inflow"]
                if out["flow_id"] != row["flow_id"] or inc["flow_id"] != row["flow_id"]:
                    return False
                def decode(x):
                    return FlowPosting(**(x | {"quantity":D(x["quantity"]),"uncertainty":D(x["uncertainty"])}))
                validate_pair(decode(out),decode(inc))
                chain = self._chain_hash(seq,row["flow_id"],digest,previous)
                if chain != row["chain_hash"]: return False
                previous, seen = chain, seen | {row["flow_id"]}
            with closing(self._connect()) as con:
                meta = con.execute("SELECT * FROM physical_flow_meta WHERE singleton_id=1").fetchone()
                return bool(meta and meta["schema_version"] == self.SCHEMA_VERSION
                    and meta["event_count"] == len(rows) and meta["tail_hash"] == previous)
        except (sqlite3.DatabaseError,ValueError,TypeError,KeyError,AttributeError):
            return False
