"""Shared append-only SQLite event/ACL substrate for authoritative domain registers.

This is a local durable register implementation. It deliberately does not claim
cross-host consensus or remote WORM custody; those are separate deployment layers.
"""
from __future__ import annotations

from contextlib import closing
from pathlib import Path
import hashlib
import json
import sqlite3
from typing import Mapping
from datetime import datetime, timezone

GENESIS = "0" * 64
DOMAIN = b"SYNERGY_DOMAIN_REGISTER_V2\0"


class RegisterError(ValueError):
    """Invalid event, authorization, transition, or persisted register state."""


def canonical_json(value):
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"),
                          ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RegisterError("value is not canonical JSON") from exc


def required_text(value, field):
    if not isinstance(value, str) or not value or value != value.strip():
        raise RegisterError(f"{field} must be trimmed non-empty text")
    return value


def utc_timestamp(value, field):
    required_text(value, field)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RegisterError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise RegisterError(f"{field} must explicitly use UTC")
    return value


def finite_decimal(value, field, *, minimum=None):
    from decimal import Decimal, InvalidOperation
    if isinstance(value, bool):
        raise RegisterError(f"{field} must be a finite decimal string")
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise RegisterError(f"{field} must be a finite decimal string") from exc
    if not number.is_finite() or (minimum is not None and number < minimum):
        raise RegisterError(f"{field} is outside its permitted finite range")
    return number


class DurableEventRegister:
    """Hash-chained event log with append-only ACL and replay-derived state."""
    authoritative_domain_adapter = True
    SCHEMA_VERSION = 2
    REGISTER_NAME = "abstract"

    def __init__(self, database_path):
        self.path = str(database_path)
        self.name = self.REGISTER_NAME
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS register_meta(
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                    register_name TEXT NOT NULL,
                    schema_version INTEGER NOT NULL,
                    event_count INTEGER NOT NULL CHECK(event_count>=0),
                    tail_hash TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS register_events(
                    commit_sequence INTEGER PRIMARY KEY CHECK(commit_sequence>0),
                    event_id TEXT NOT NULL UNIQUE,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    common_event_id TEXT NOT NULL,
                    aggregate_id TEXT NOT NULL,
                    aggregate_version INTEGER NOT NULL CHECK(aggregate_version>=0),
                    event_type TEXT NOT NULL,
                    effective_at TEXT NOT NULL,
                    recorded_at TEXT NOT NULL,
                    actor_id TEXT NOT NULL,
                    authority_ref TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    payload_sha256 TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,
                    chain_hash TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS register_events_no_update
                    BEFORE UPDATE ON register_events
                    BEGIN SELECT RAISE(ABORT,'register event history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS register_events_no_delete
                    BEFORE DELETE ON register_events
                    BEGIN SELECT RAISE(ABORT,'register event history is immutable'); END;
                CREATE TABLE IF NOT EXISTS native_participant_inbox(
                    transaction_id TEXT PRIMARY KEY,
                    stream_id TEXT NOT NULL,
                    native_event_id TEXT NOT NULL UNIQUE,
                    payload_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    expected_revision INTEGER NOT NULL CHECK(expected_revision>=0),
                    prepare_token TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('PREPARED','COMMITTED','ABORTED')),
                    receipt_json TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS native_participant_one_prepared_per_stream
                    ON native_participant_inbox(stream_id) WHERE state='PREPARED';
                CREATE TRIGGER IF NOT EXISTS native_participant_payload_no_update
                    BEFORE UPDATE OF transaction_id,stream_id,native_event_id,payload_digest,payload_json,expected_revision,prepare_token
                    ON native_participant_inbox
                    BEGIN SELECT RAISE(ABORT,'prepared native participant payload is immutable'); END;
            """)
            row = con.execute("SELECT register_name,schema_version FROM register_meta WHERE singleton_id=1").fetchone()
            if row is None:
                con.execute("INSERT INTO register_meta VALUES(1,?,?,0,?)",
                            (self.REGISTER_NAME, self.SCHEMA_VERSION, GENESIS))
            elif (row["register_name"], row["schema_version"]) != (self.REGISTER_NAME, self.SCHEMA_VERSION):
                raise RegisterError("register identity/schema mismatch; explicit migration required")

    def _connect(self):
        con = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA synchronous=FULL")
        return con

    @staticmethod
    def _chain(sequence, event, digest, previous):
        body = {"sequence":sequence,"event_id":event["event_id"],
                "idempotency_key":event["idempotency_key"],"common_event_id":event["common_event_id"],
                "aggregate_id":event["aggregate_id"],
                "aggregate_version":event["aggregate_version"],"event_type":event["event_type"],
                "effective_at":event["effective_at"],"recorded_at":event["recorded_at"],
                "actor_id":event["actor_id"],"authority_ref":event["authority_ref"],
                "payload_sha256":digest,"previous_hash":previous}
        return hashlib.sha256(DOMAIN + canonical_json(body).encode("utf-8")).hexdigest()

    def _load(self, con):
        meta = con.execute("SELECT * FROM register_meta WHERE singleton_id=1").fetchone()
        if meta is None or meta["register_name"] != self.REGISTER_NAME or meta["schema_version"] != self.SCHEMA_VERSION:
            raise RegisterError("register metadata is missing or incompatible")
        rows = con.execute("SELECT * FROM register_events ORDER BY commit_sequence").fetchall()
        previous, states, versions, acl = GENESIS, {}, {}, {}
        for sequence, row in enumerate(rows, 1):
            if row["commit_sequence"] != sequence or row["previous_hash"] != previous:
                raise RegisterError("register sequence/hash-chain discontinuity")
            payload = json.loads(row["payload_json"])
            if canonical_json(payload) != row["payload_json"]:
                raise RegisterError("non-canonical persisted payload")
            digest = hashlib.sha256(row["payload_json"].encode("utf-8")).hexdigest()
            if digest != row["payload_sha256"]:
                raise RegisterError("persisted payload digest mismatch")
            chain = self._chain(sequence, row, digest, previous)
            if chain != row["chain_hash"]:
                raise RegisterError("persisted event chain hash mismatch")
            event = dict(row)
            event["payload"] = payload
            if row["event_type"] == "acl.granted":
                principal = required_text(payload.get("principal_id"), "principal_id")
                permissions = payload.get("permissions")
                if not isinstance(permissions, list) or not permissions or any(not isinstance(x, str) or not x for x in permissions):
                    raise RegisterError("invalid persisted ACL grant")
                if sequence == 1:
                    if row["actor_id"] != principal or permissions != ["*"]:
                        raise RegisterError("invalid ACL bootstrap event")
                elif not self._authorized(acl, row["actor_id"], "acl:admin"):
                    raise RegisterError("unauthorized ACL grant in event history")
                acl[principal] = set(permissions)
            elif row["event_type"] == "acl.revoked":
                principal = required_text(payload.get("principal_id"), "principal_id")
                if not self._authorized(acl, row["actor_id"], "acl:admin"):
                    raise RegisterError("unauthorized ACL revocation in event history")
                if principal in acl and ("acl:admin" in acl[principal] or "*" in acl[principal]):
                    admins = sum(1 for grants in acl.values() if "acl:admin" in grants or "*" in grants)
                    if admins <= 1:
                        raise RegisterError("event history revokes the last ACL administrator")
                acl.pop(principal, None)
            else:
                if not self._authorized(acl,row["actor_id"],self.write_permission(row["event_type"])):
                    raise RegisterError("unauthorized domain event in immutable history")
                expected = versions.get(row["aggregate_id"], 0) + 1
                if row["aggregate_version"] != expected:
                    raise RegisterError("aggregate version sequence discontinuity")
                old = states.get(row["aggregate_id"])
                next_state = self.reduce_event(old, event)
                next_state["_event_ids"] = list((old or {}).get("_event_ids", [])) + [row["event_id"]]
                states[row["aggregate_id"]] = next_state
                versions[row["aggregate_id"]] = expected
            previous = chain
        if meta["event_count"] != len(rows) or meta["tail_hash"] != previous:
            raise RegisterError("register metadata does not match event chain")
        return states, versions, acl, rows

    def _authorized(self, acl, actor_id, permission):
        granted = acl.get(actor_id, set())
        return "*" in granted or permission in granted

    def _append(self, *, event_id, idempotency_key, aggregate_id, event_type,
                effective_at, recorded_at, actor_id, authority_ref, payload,
                common_event_id=None, expected_version=None, permission=None, bootstrap=False,
                allow_prepared_txid=None):
        for value, field in ((event_id,"event_id"),(idempotency_key,"idempotency_key"),
                             (aggregate_id,"aggregate_id"),(event_type,"event_type"),
                             (effective_at,"effective_at"),(recorded_at,"recorded_at"),
                             (actor_id,"actor_id"),(authority_ref,"authority_ref")):
            required_text(value, field)
        utc_timestamp(effective_at,"effective_at")
        utc_timestamp(recorded_at,"recorded_at")
        common_event_id = required_text(common_event_id or event_id,"common_event_id")
        if not isinstance(payload, Mapping):
            raise RegisterError("payload must be a JSON object")
        payload_json = canonical_json(dict(payload))
        digest = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                states, versions, acl, rows = self._load(con)
                old = con.execute("SELECT * FROM register_events WHERE event_id=? OR idempotency_key=?",
                                  (event_id, idempotency_key)).fetchone()
                if old:
                    if (old["event_id"], old["idempotency_key"], old["common_event_id"], old["aggregate_id"],
                        old["event_type"], old["payload_sha256"], old["effective_at"],
                        old["recorded_at"], old["actor_id"], old["authority_ref"]) != (
                        event_id, idempotency_key, common_event_id, aggregate_id, event_type, digest,
                        effective_at, recorded_at, actor_id, authority_ref):
                        raise RegisterError("event/idempotency identity reused with changed immutable content")
                    con.execute("COMMIT")
                    return False
                pending = con.execute("SELECT transaction_id FROM native_participant_inbox WHERE stream_id=? AND state='PREPARED'",
                                      (aggregate_id,)).fetchone()
                if pending and pending["transaction_id"] != allow_prepared_txid:
                    raise RegisterError("aggregate is reserved by a prepared cross-register transaction")
                if event_type in {"acl.granted","acl.revoked"} and con.execute(
                    "SELECT 1 FROM native_participant_inbox WHERE state='PREPARED' LIMIT 1").fetchone():
                    raise RegisterError("ACL changes are serialized behind prepared domain transactions")
                prepared_authority = False
                if allow_prepared_txid is not None:
                    prepared = con.execute("SELECT state,payload_json FROM native_participant_inbox WHERE transaction_id=?",
                                           (allow_prepared_txid,)).fetchone()
                    if prepared is None or prepared["state"] != "PREPARED":
                        raise RegisterError("native commit is missing its durable prepared authority record")
                    envelope = json.loads(prepared["payload_json"])
                    if (envelope.get("event_type"),envelope.get("effective_at"),envelope.get("recorded_at"),
                        envelope.get("actor_id"),envelope.get("authority_ref"),envelope.get("idempotency_key"),
                        envelope.get("payload")) != (event_type,effective_at,recorded_at,actor_id,authority_ref,
                                                       idempotency_key,dict(payload)):
                        raise RegisterError("native commit differs from its prepared immutable envelope")
                    prepared_authority = True
                if bootstrap:
                    if rows or acl or event_type != "acl.granted" or payload.get("permissions") != ["*"]:
                        raise RegisterError("bootstrap is permitted only once to create the first administrator")
                elif event_type in {"acl.granted", "acl.revoked"}:
                    if not self._authorized(acl, actor_id, "acl:admin"):
                        raise RegisterError("actor lacks acl:admin permission")
                    if event_type == "acl.revoked":
                        target = payload.get("principal_id")
                        if target in acl and "acl:admin" in acl[target]:
                            admins = sum(1 for grants in acl.values() if "acl:admin" in grants or "*" in grants)
                            if admins <= 1:
                                raise RegisterError("cannot revoke the last ACL administrator")
                else:
                    if not prepared_authority and not self._authorized(acl, actor_id, permission or self.write_permission(event_type)):
                        raise RegisterError("actor is not authorized for this register operation")
                    current = versions.get(aggregate_id, 0)
                    if expected_version != current:
                        raise RegisterError(f"aggregate version conflict: expected {current}, received {expected_version}")
                    event = {"event_id":event_id,"event_type":event_type,"aggregate_id":aggregate_id,
                             "aggregate_version":current+1,"effective_at":effective_at,
                             "recorded_at":recorded_at,"actor_id":actor_id,
                             "authority_ref":authority_ref,"payload":dict(payload)}
                    states[aggregate_id] = self.reduce_event(states.get(aggregate_id), event)
                meta = con.execute("SELECT event_count,tail_hash FROM register_meta WHERE singleton_id=1").fetchone()
                sequence = meta["event_count"] + 1
                aggregate_version = 0 if event_type.startswith("acl.") else versions.get(aggregate_id, 0) + 1
                chain_event = {"event_id":event_id,"idempotency_key":idempotency_key,
                    "common_event_id":common_event_id,"aggregate_id":aggregate_id,"aggregate_version":aggregate_version,"event_type":event_type,
                    "effective_at":effective_at,"recorded_at":recorded_at,"actor_id":actor_id,
                    "authority_ref":authority_ref}
                chain = self._chain(sequence, chain_event, digest, meta["tail_hash"])
                con.execute("""INSERT INTO register_events VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (sequence,event_id,idempotency_key,common_event_id,aggregate_id,aggregate_version,event_type,
                     effective_at,recorded_at,actor_id,authority_ref,payload_json,digest,meta["tail_hash"],chain))
                con.execute("UPDATE register_meta SET event_count=?,tail_hash=? WHERE singleton_id=1",
                            (sequence,chain))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise

    def bootstrap_admin(self, *, principal_id, authority_ref, occurred_at):
        principal_id = required_text(principal_id, "principal_id")
        return self._append(event_id=f"{self.REGISTER_NAME}:ACL:BOOTSTRAP:{principal_id}",
            idempotency_key=f"{self.REGISTER_NAME}:ACL:BOOTSTRAP:{principal_id}",
            aggregate_id=f"ACL:{principal_id}", event_type="acl.granted",
            effective_at=occurred_at, recorded_at=occurred_at, actor_id=principal_id,
            authority_ref=authority_ref, payload={"principal_id":principal_id,"permissions":["*"]},
            bootstrap=True)

    def grant_access(self, *, event_id, idempotency_key, principal_id, permissions,
                     actor_id, authority_ref, occurred_at):
        principal_id = required_text(principal_id, "principal_id")
        raw_permissions = list(permissions) if isinstance(permissions, (list, tuple, set)) else None
        if not raw_permissions or any(not isinstance(x,str) or not x.strip() for x in raw_permissions):
            raise RegisterError("permissions must be a non-empty collection of permission strings")
        permissions = sorted(set(raw_permissions))
        return self._append(event_id=event_id,idempotency_key=idempotency_key,
            aggregate_id=f"ACL:{principal_id}",event_type="acl.granted",
            effective_at=occurred_at,recorded_at=occurred_at,actor_id=actor_id,
            authority_ref=authority_ref,payload={"principal_id":principal_id,"permissions":permissions})

    def revoke_access(self, *, event_id, idempotency_key, principal_id,
                      actor_id, authority_ref, occurred_at):
        principal_id = required_text(principal_id, "principal_id")
        return self._append(event_id=event_id,idempotency_key=idempotency_key,
            aggregate_id=f"ACL:{principal_id}",event_type="acl.revoked",
            effective_at=occurred_at,recorded_at=occurred_at,actor_id=actor_id,
            authority_ref=authority_ref,payload={"principal_id":principal_id})

    def append_event(self, **kwargs):
        return self._append(**kwargs)

    def state(self, aggregate_id, *, principal_id):
        with closing(self._connect()) as con:
            con.execute("BEGIN")
            states, versions, acl, _ = self._load(con)
            if not self._authorized(acl, principal_id, self.read_permission):
                raise RegisterError("actor is not authorized to read this register")
            import copy
            return copy.deepcopy(states.get(aggregate_id)), versions.get(aggregate_id, 0)

    def history(self, aggregate_id, *, principal_id):
        with closing(self._connect()) as con:
            con.execute("BEGIN")
            _, _, acl, rows = self._load(con)
            if not self._authorized(acl, principal_id, self.read_permission):
                raise RegisterError("actor is not authorized to read this register")
            return tuple(dict(row) for row in rows if row["aggregate_id"] == aggregate_id)

    def _participant_token(self, txid, operation):
        digest = hashlib.sha256(canonical_json(operation["payload"]).encode("utf-8")).hexdigest()
        body = {"protocol":"synergy-native-register-prepare-v1", "participant":self.name,
                "transaction_id":txid, "stream_id":operation["stream_id"],
                "native_event_id":operation["native_event_id"], "payload_digest":digest,
                "expected_revision":operation["expected_revision"]}
        return hashlib.sha256(canonical_json(body).encode("utf-8")).hexdigest(), digest

    def prepare(self, txid, operation):
        required_text(txid, "transaction_id")
        if not isinstance(operation, Mapping): raise RegisterError("participant operation must be an object")
        stream = required_text(operation.get("stream_id"), "stream_id")
        native_id = required_text(operation.get("native_event_id"), "native_event_id")
        revision = operation.get("expected_revision")
        if not isinstance(revision,int) or isinstance(revision,bool) or revision < 0:
            raise RegisterError("expected_revision must be a non-negative integer")
        payload = operation.get("payload")
        if not isinstance(payload,Mapping): raise RegisterError("native event payload must be an object")
        envelope = dict(payload)
        from register_event_contract import normalize_event_envelope
        try:
            envelope = normalize_event_envelope(self.REGISTER_NAME, envelope)
        except ValueError as exc:
            raise RegisterError(f"native event contract rejected: {exc}") from exc
        required = ("event_type","effective_at","recorded_at","actor_id","authority_ref","idempotency_key","payload")
        if any(field not in envelope for field in required):
            raise RegisterError("native event envelope is incomplete")
        if not isinstance(envelope["payload"],Mapping): raise RegisterError("native domain payload must be an object")
        for field in required[:-1]: required_text(envelope[field],field)
        utc_timestamp(envelope["effective_at"],"effective_at")
        utc_timestamp(envelope["recorded_at"],"recorded_at")
        payload_json = canonical_json(envelope)
        operation = {"stream_id":stream,"native_event_id":native_id,
                     "expected_revision":revision,"payload":envelope}
        token, digest = self._participant_token(txid, operation)
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old = con.execute("SELECT * FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
                if old:
                    old_raw = old["payload_json"]
                    try:
                        old_envelope = json.loads(old_raw)
                    except (TypeError, json.JSONDecodeError) as exc:
                        raise RegisterError("stored native prepare payload is invalid JSON") from exc
                    old_operation = {"stream_id":old["stream_id"],"native_event_id":old["native_event_id"],
                                     "expected_revision":old["expected_revision"],"payload":old_envelope}
                    old_token, old_digest = self._participant_token(txid, old_operation)
                    if (canonical_json(old_envelope) != old_raw or old_digest != old["payload_digest"]
                            or old_token != old["prepare_token"]):
                        raise RegisterError("stored native prepare payload, digest or token is corrupt")
                    from register_event_contract import equivalent_event_envelopes
                    same_payload = (old_raw == canonical_json(dict(payload))
                                    or equivalent_event_envelopes(self.REGISTER_NAME, old_envelope, envelope))
                    same_identity = (old["stream_id"],old["native_event_id"],old["expected_revision"]) == (
                        stream,native_id,revision)
                    if not same_identity or not same_payload:
                        raise RegisterError("native participant transaction ID reused with changed content")
                    if old["state"] == "ABORTED": raise RegisterError("aborted native transaction cannot be prepared again")
                    # Return the historical token; never rewrite v0 bytes, digest or receipt.
                    con.execute("COMMIT"); return old["prepare_token"]
                states, versions, acl, _ = self._load(con)
                if versions.get(stream,0) != revision:
                    raise RegisterError("native register expected revision conflict")
                if con.execute("SELECT 1 FROM register_events WHERE idempotency_key=? OR event_id=?",
                               (envelope["idempotency_key"],native_id)).fetchone():
                    raise RegisterError("native event or idempotency key already exists")
                for pending_row in con.execute("SELECT payload_json FROM native_participant_inbox WHERE state='PREPARED'"):
                    pending_envelope=json.loads(pending_row["payload_json"])
                    if pending_envelope.get("idempotency_key") == envelope["idempotency_key"]:
                        raise RegisterError("idempotency key is reserved by another prepared transaction")
                if not self._authorized(acl,envelope["actor_id"],self.write_permission(envelope["event_type"])):
                    raise RegisterError("native register actor is not authorized")
                candidate = {"event_id":native_id,"event_type":envelope["event_type"],"aggregate_id":stream,
                    "aggregate_version":revision+1,"effective_at":envelope["effective_at"],
                    "recorded_at":envelope["recorded_at"],"actor_id":envelope["actor_id"],
                    "authority_ref":envelope["authority_ref"],"payload":dict(envelope["payload"])}
                self.reduce_event(states.get(stream),candidate)
                con.execute("INSERT INTO native_participant_inbox VALUES(?,?,?,?,?,?,?,'PREPARED',NULL)",
                    (txid,stream,native_id,digest,payload_json,revision,token))
                con.execute("COMMIT")
                return token
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise

    def commit(self, txid, prepare_token):
        required_text(txid,"transaction_id"); required_text(prepare_token,"prepare_token")
        with closing(self._connect()) as con:
            row = con.execute("SELECT * FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
        if row is None: raise RegisterError("native participant prepare record is missing")
        if row["prepare_token"] != prepare_token: raise RegisterError("native participant prepare token mismatch")
        if row["state"] == "ABORTED": raise RegisterError("aborted native transaction cannot commit")
        if row["state"] == "COMMITTED": return json.loads(row["receipt_json"])
        envelope = json.loads(row["payload_json"])
        self._append(event_id=row["native_event_id"],idempotency_key=envelope["idempotency_key"],
            aggregate_id=row["stream_id"],event_type=envelope["event_type"],
            effective_at=envelope["effective_at"],recorded_at=envelope["recorded_at"],
            actor_id=envelope["actor_id"],authority_ref=envelope["authority_ref"],
            payload=envelope["payload"],common_event_id=txid,expected_version=row["expected_revision"],
            allow_prepared_txid=txid)
        receipt = {"participant":self.name,"transaction_id":txid,
                   "native_event_id":row["native_event_id"],"payload_digest":row["payload_digest"],
                   "prepare_token":prepare_token,"revision":row["expected_revision"]+1}
        receipt_json = canonical_json(receipt)
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                current=con.execute("SELECT state,receipt_json FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
                if current["state"] == "COMMITTED":
                    if current["receipt_json"] != receipt_json: raise RegisterError("native participant receipt changed")
                elif current["state"] == "PREPARED":
                    con.execute("UPDATE native_participant_inbox SET state='COMMITTED',receipt_json=? WHERE transaction_id=?",(receipt_json,txid))
                else: raise RegisterError("native participant is not prepared")
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise
        return receipt

    def abort(self, txid):
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row=con.execute("SELECT state FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
                if row is None: con.execute("COMMIT"); return
                if row["state"] == "COMMITTED": raise RegisterError("committed native participant cannot abort")
                if row["state"] == "PREPARED": con.execute("UPDATE native_participant_inbox SET state='ABORTED' WHERE transaction_id=?",(txid,))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise

    def status(self, txid):
        with closing(self._connect()) as con:
            row=con.execute("SELECT state,prepare_token,receipt_json,native_event_id,payload_digest FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
            return dict(row) if row else None

    def events_for_common_event(self, common_event_id, *, principal_id):
        required_text(common_event_id,"common_event_id")
        with closing(self._connect()) as con:
            con.execute("BEGIN")
            _, _, acl, rows = self._load(con)
            if not self._authorized(acl,principal_id,self.read_permission):
                raise RegisterError("actor is not authorized to read this register")
            result=[]
            for row in rows:
                if row["common_event_id"] == common_event_id:
                    item=dict(row)
                    item["payload"]=json.loads(item.pop("payload_json"))
                    result.append(item)
            return tuple(result)

    def event_count(self, txid):
        with closing(self._connect()) as con:
            row=con.execute("SELECT i.state,COUNT(e.event_id) AS n FROM native_participant_inbox i LEFT JOIN register_events e ON e.event_id=i.native_event_id WHERE i.transaction_id=? GROUP BY i.transaction_id",(txid,)).fetchone()
            return row["n"] if row else 0

    def committed_event(self, txid):
        with closing(self._connect()) as con:
            row=con.execute("""SELECT i.native_event_id,i.stream_id,i.expected_revision,i.payload_digest,i.payload_json,i.state,e.event_id,e.common_event_id
                FROM native_participant_inbox i LEFT JOIN register_events e ON e.event_id=i.native_event_id
                WHERE i.transaction_id=?""",(txid,)).fetchone()
            if row is None or row["state"] != "COMMITTED" or row["event_id"] is None: return None
            return {"native_event_id":row["native_event_id"],"stream_id":row["stream_id"],
                    "revision":row["expected_revision"]+1,"payload_digest":row["payload_digest"],
                    "payload_json":row["payload_json"],"common_event_id":row["common_event_id"]}

    def verify(self):
        try:
            with closing(self._connect()) as con:
                con.execute("BEGIN")
                self._load(con)
                return True
        except (sqlite3.DatabaseError, ValueError, TypeError, KeyError, AttributeError):
            return False

    @property
    def total_event_count(self):
        with closing(self._connect()) as con:
            return con.execute("SELECT event_count FROM register_meta WHERE singleton_id=1").fetchone()[0]
