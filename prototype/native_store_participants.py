"""Recoverable coordinator adapters for existing authoritative SQLite domain stores."""
from __future__ import annotations
from contextlib import closing
from decimal import Decimal
from datetime import datetime, timezone
import hashlib, json


class NativeStoreParticipantError(ValueError): pass


def _canonical(value):
    try: return json.dumps(value,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)
    except (TypeError,ValueError) as exc: raise NativeStoreParticipantError("participant envelope is not canonical JSON") from exc


def _required(value,field):
    if not isinstance(value,str) or not value or value!=value.strip():
        raise NativeStoreParticipantError(f"{field} must be trimmed non-empty text")
    return value


class NativeStoreParticipant:
    def __init__(self,name,store,stream_id,revision_reader,validator,applier,event_exists,authorizer):
        self.name,self.store,self.stream_id=name,store,stream_id
        self.revision_reader,self.validator,self.applier=revision_reader,validator,applier
        self.event_exists,self.authorizer=event_exists,authorizer
        if not callable(authorizer): raise NativeStoreParticipantError("an explicit external authorizer is required")
        with closing(store._connect()) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS native_participant_inbox(
                    transaction_id TEXT PRIMARY KEY, stream_id TEXT NOT NULL,
                    native_event_id TEXT NOT NULL UNIQUE, payload_digest TEXT NOT NULL,
                    payload_json TEXT NOT NULL, expected_revision INTEGER NOT NULL CHECK(expected_revision>=0),
                    prepare_token TEXT NOT NULL, state TEXT NOT NULL CHECK(state IN ('PREPARED','COMMITTED','ABORTED')),
                    receipt_json TEXT
                );
                CREATE UNIQUE INDEX IF NOT EXISTS native_participant_one_prepared_per_stream
                    ON native_participant_inbox(stream_id) WHERE state='PREPARED';
                CREATE TRIGGER IF NOT EXISTS native_participant_payload_no_update
                    BEFORE UPDATE OF transaction_id,stream_id,native_event_id,payload_digest,payload_json,expected_revision,prepare_token
                    ON native_participant_inbox
                    BEGIN SELECT RAISE(ABORT,'prepared native participant payload is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS native_participant_no_delete
                    BEFORE DELETE ON native_participant_inbox
                    BEGIN SELECT RAISE(ABORT,'native participant inbox history is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS native_participant_state_transition
                    BEFORE UPDATE OF state ON native_participant_inbox
                    WHEN NOT (OLD.state='PREPARED' AND NEW.state IN ('COMMITTED','ABORTED'))
                    BEGIN SELECT RAISE(ABORT,'invalid native participant state transition'); END;
            """)

    def _token(self,txid,op,digest):
        body={"protocol":"synergy-native-store-prepare-v1","participant":self.name,"transaction_id":txid,
            "stream_id":op["stream_id"],"native_event_id":op["native_event_id"],
            "payload_digest":digest,"expected_revision":op["expected_revision"]}
        return hashlib.sha256(_canonical(body).encode()).hexdigest()

    def prepare(self,txid,op):
        _required(txid,"transaction_id")
        if not isinstance(op,dict): raise NativeStoreParticipantError("operation must be an object")
        stream=_required(op.get("stream_id"),"stream_id")
        if stream!=self.stream_id: raise NativeStoreParticipantError("operation targets wrong native register stream")
        native_id=_required(op.get("native_event_id"),"native_event_id")
        revision=op.get("expected_revision")
        if not isinstance(revision,int) or isinstance(revision,bool) or revision<0:
            raise NativeStoreParticipantError("expected_revision must be a non-negative integer")
        envelope=op.get("payload")
        if not isinstance(envelope,dict): raise NativeStoreParticipantError("native event envelope must be an object")
        for field in ("event_type","effective_at","recorded_at","actor_id","authority_ref","idempotency_key"):
            _required(envelope.get(field),field)
        for field in ("effective_at","recorded_at"):
            try: stamp=datetime.fromisoformat(envelope[field].replace("Z","+00:00"))
            except ValueError as exc: raise NativeStoreParticipantError(f"{field} must be ISO-8601 UTC") from exc
            if stamp.tzinfo is None or stamp.utcoffset()!=timezone.utc.utcoffset(stamp):
                raise NativeStoreParticipantError(f"{field} must explicitly use UTC")
        if not isinstance(envelope.get("payload"),dict): raise NativeStoreParticipantError("domain payload must be an object")
        payload_json=_canonical(envelope); digest=hashlib.sha256(payload_json.encode()).hexdigest()
        token=self._token(txid,op,digest)
        with closing(self.store._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old=con.execute("SELECT * FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
                if old:
                    if (old["stream_id"],old["native_event_id"],old["payload_digest"],old["payload_json"],old["expected_revision"],old["prepare_token"])!=(stream,native_id,digest,payload_json,revision,token):
                        raise NativeStoreParticipantError("transaction ID reused with changed participant content")
                    if old["state"]=="ABORTED": raise NativeStoreParticipantError("aborted transaction cannot be prepared again")
                    con.execute("COMMIT"); return token
                current=self.revision_reader(con)
                if current!=revision: raise NativeStoreParticipantError(f"native revision conflict: expected {current}, got {revision}")
                if con.execute("SELECT 1 FROM native_participant_inbox WHERE stream_id=? AND state='PREPARED'",(stream,)).fetchone():
                    raise NativeStoreParticipantError("native register stream already has a prepared transaction")
                if con.execute("SELECT 1 FROM native_participant_inbox WHERE native_event_id=?",(native_id,)).fetchone():
                    raise NativeStoreParticipantError("native event ID already reserved")
                if not self.authorizer(envelope["actor_id"],envelope["authority_ref"],envelope["event_type"],envelope["payload"]):
                    raise NativeStoreParticipantError("external authority policy denied native register operation")
                if self.event_exists(con,native_id,envelope):
                    raise NativeStoreParticipantError("native event already exists outside this transaction")
                self.validator(con,native_id,envelope)
                for pending in con.execute("SELECT payload_json FROM native_participant_inbox WHERE state='PREPARED'"):
                    if json.loads(pending["payload_json"]).get("idempotency_key")==envelope["idempotency_key"]:
                        raise NativeStoreParticipantError("idempotency key reserved by another prepared transaction")
                con.execute("INSERT INTO native_participant_inbox VALUES(?,?,?,?,?,?,?,'PREPARED',NULL)",
                    (txid,stream,native_id,digest,payload_json,revision,token))
                con.execute("COMMIT"); return token
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise

    @staticmethod
    def _verified_envelope(row):
        try: envelope=json.loads(row["payload_json"])
        except (TypeError,json.JSONDecodeError) as exc: raise NativeStoreParticipantError("native participant payload is invalid JSON") from exc
        if _canonical(envelope)!=row["payload_json"] or hashlib.sha256(row["payload_json"].encode()).hexdigest()!=row["payload_digest"]:
            raise NativeStoreParticipantError("native participant payload digest mismatch")
        return envelope

    def commit(self,txid,prepare_token):
        _required(txid,"transaction_id"); _required(prepare_token,"prepare_token")
        with closing(self.store._connect()) as con:
            row=con.execute("SELECT * FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
        if row is None or row["prepare_token"]!=prepare_token:
            raise NativeStoreParticipantError("native prepare receipt is missing or mismatched")
        envelope=self._verified_envelope(row)
        if row["state"]=="ABORTED": raise NativeStoreParticipantError("aborted transaction cannot commit")
        if row["state"]=="COMMITTED":
            receipt=json.loads(row["receipt_json"])
            expected={"participant":self.name,"transaction_id":txid,"native_event_id":row["native_event_id"],
                "payload_digest":row["payload_digest"],"prepare_token":prepare_token,"revision":row["expected_revision"]+1}
            if receipt!=expected: raise NativeStoreParticipantError("committed receipt does not match immutable prepare")
            return receipt
        self.applier(row["native_event_id"],envelope,txid)
        receipt={"participant":self.name,"transaction_id":txid,"native_event_id":row["native_event_id"],
            "payload_digest":row["payload_digest"],"prepare_token":prepare_token,"revision":row["expected_revision"]+1}
        receipt_json=_canonical(receipt)
        with closing(self.store._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                current=con.execute("SELECT state,receipt_json FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
                if current["state"]=="COMMITTED":
                    if current["receipt_json"]!=receipt_json: raise NativeStoreParticipantError("native receipt changed")
                elif current["state"]=="PREPARED":
                    con.execute("UPDATE native_participant_inbox SET state='COMMITTED',receipt_json=? WHERE transaction_id=?",(receipt_json,txid))
                else: raise NativeStoreParticipantError("native participant is not prepared")
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise
        return receipt

    def abort(self,txid):
        with closing(self.store._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                row=con.execute("SELECT state FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
                if row is None: con.execute("COMMIT"); return
                if row["state"]=="COMMITTED": raise NativeStoreParticipantError("committed participant cannot abort")
                if row["state"]=="PREPARED": con.execute("UPDATE native_participant_inbox SET state='ABORTED' WHERE transaction_id=?",(txid,))
                con.execute("COMMIT")
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise

    def status(self,txid):
        with closing(self.store._connect()) as con:
            row=con.execute("SELECT state,prepare_token,receipt_json,native_event_id,payload_digest FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
            return dict(row) if row else None

    def event_count(self,txid):
        with closing(self.store._connect()) as con:
            row=con.execute("SELECT * FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
            if row is None or row["state"]!="COMMITTED": return 0
            return 1 if self.event_exists(con,row["native_event_id"],self._verified_envelope(row)) else 0

    def committed_event(self,txid):
        with closing(self.store._connect()) as con:
            row=con.execute("SELECT * FROM native_participant_inbox WHERE transaction_id=?",(txid,)).fetchone()
            if row is None or row["state"]!="COMMITTED": return None
            envelope=self._verified_envelope(row)
            if not self.event_exists(con,row["native_event_id"],envelope): return None
            return {"native_event_id":row["native_event_id"],"stream_id":row["stream_id"],
                "revision":row["expected_revision"]+1,"payload_digest":row["payload_digest"],
                "payload_json":row["payload_json"],"common_event_id":txid}


def make_physical_participant(store,authorizer):
    from physical_flow_store import FlowPosting, validate_pair
    def decode(raw): return FlowPosting(**(raw|{"quantity":Decimal(raw["quantity"]),"uncertainty":Decimal(raw["uncertainty"])}))
    def revision(con): return con.execute("SELECT event_count FROM physical_flow_meta WHERE singleton_id=1").fetchone()[0]
    def validate(con,native_id,envelope):
        p=envelope["payload"]; out,inc=decode(p["outflow"]),decode(p["inflow"]); validate_pair(out,inc)
        if out.flow_id!=native_id or envelope["idempotency_key"]!=native_id:
            raise NativeStoreParticipantError("physical native event/idempotency IDs must equal flow_id")
    def apply(native_id,envelope,txid):
        p=envelope["payload"]; store.append(decode(p["outflow"]),decode(p["inflow"]),allow_prepared_txid=txid)
    def exists(con,native_id,envelope): return con.execute("SELECT 1 FROM physical_flows WHERE flow_id=?",(native_id,)).fetchone() is not None
    return NativeStoreParticipant("physical",store,"physical",revision,validate,apply,exists,authorizer)


def make_capital_participant(store,authorizer):
    from capital_cohort_bridge import CapitalCohort,CohortEvent,advance_cohort_period
    def revision(con): return con.execute("SELECT period_count FROM capital_cohort_meta WHERE singleton_id=1").fetchone()[0]
    def batch(envelope):
        p=envelope["payload"]
        return p["period"],tuple(CohortEvent(**x) for x in p.get("events",[])),tuple(CapitalCohort(**x) for x in p.get("additions",[]))
    def validate(con,native_id,envelope):
        valid,snapshot=store._verify_connection(con)
        if not valid: raise NativeStoreParticipantError("capital replay failed before prepare")
        meta,rows,state=snapshot; period,events,additions=batch(envelope)
        if native_id!=f"CAPITAL-PERIOD:{period}" or envelope["idempotency_key"]!=native_id:
            raise NativeStoreParticipantError("capital event/idempotency ID must bind its period")
        if rows and period!=rows[-1]["period"]+1: raise NativeStoreParticipantError("capital period is not contiguous")
        advance_cohort_period(state,events,additions,period)
    def apply(native_id,envelope,txid):
        period,events,additions=batch(envelope); store.append_period(period,events,additions,allow_prepared_txid=txid)
    def exists(con,native_id,envelope):
        return con.execute("SELECT 1 FROM capital_cohort_periods WHERE period=?",(envelope["payload"]["period"],)).fetchone() is not None
    return NativeStoreParticipant("capital",store,"capital",revision,validate,apply,exists,authorizer)


def make_product_participant(store,authorizer):
    from product_register import _canonical
    def revision(con): return con.execute("SELECT event_count FROM product_register_meta WHERE singleton_id=1").fetchone()[0]
    def expected_id(event_type,payload):
        if event_type=="product_spec": return f"SPEC:{payload['product_id']}:{payload['grade_id']}"
        field={"product_balance":"balance_id","price_quote":"price_id","valuation":"valuation_id"}.get(event_type)
        if field is None: raise NativeStoreParticipantError("unsupported product event type")
        return payload[field]
    def validate(con,native_id,envelope):
        valid,rows=store._verify_connection(con)
        if not valid: raise NativeStoreParticipantError("product replay failed before prepare")
        p=envelope["payload"]; typ=envelope["event_type"]
        if expected_id(typ,p)!=native_id or envelope["idempotency_key"]!=native_id:
            raise NativeStoreParticipantError("product native event/idempotency ID differs from domain identity")
        candidate={"event_id":native_id,"event_type":typ,"payload_json":_canonical(p)}
        store._replay(list(rows)+[candidate])
    def apply(native_id,envelope,txid): store._append(native_id,envelope["event_type"],envelope["payload"],allow_prepared_txid=txid)
    def exists(con,native_id,envelope): return con.execute("SELECT 1 FROM product_events WHERE event_id=?",(native_id,)).fetchone() is not None
    return NativeStoreParticipant("product",store,"product",revision,validate,apply,exists,authorizer)

def _decode_journal_event(raw):
    from entity_journal import JournalEvent,JournalLine,LegalEvidence
    if not isinstance(raw,dict): raise NativeStoreParticipantError("financial event must be an object")
    lines=[]
    for posting in raw.get("postings",[]):
        if not isinstance(posting,dict): raise NativeStoreParticipantError("financial posting must be an object")
        values=dict(posting); values["amount"]=Decimal(values["amount"])
        lines.append(JournalLine(**values))
    evidence_raw=raw.get("legal_evidence")
    evidence=None
    if evidence_raw is not None:
        if not isinstance(evidence_raw,dict): raise NativeStoreParticipantError("legal evidence must be an object")
        evidence=LegalEvidence(evidence_raw["evidence_ref"],evidence_raw["authority"],
            evidence_raw["effective_at"],evidence_raw["scope"],tuple(evidence_raw["parties"]))
    return JournalEvent(event_id=raw["event_id"],event_type=raw["event_type"],
        effective_period=raw["effective_period"],lines=tuple(lines),component=raw["component"],
        legal_effect=raw["legal_effect"],
        writeoff_claim_delta=None if raw.get("writeoff_claim_delta") is None else Decimal(raw["writeoff_claim_delta"]),
        forgiven_principal=None if raw.get("forgiven_principal") is None else Decimal(raw["forgiven_principal"]),
        legal_evidence=evidence)


def financial_stock_flow_movement_specs(events):
    """Derive financial instrument movements using the same mapper as SFC projection."""
    from sfc_projection_store import _map_event
    specs=[]
    for event in events:
        instrument_deltas,_controls=_map_event(event)
        for index,(identity,component,amount) in enumerate(instrument_deltas):
            specs.append({
                "movement_id":f"{event.event_id}:SFC:{index}",
                "identity":{
                    "register_id":"financial",
                    "position_id":f"{identity.instrument_id}:{identity.holder_entity_id}:{identity.issuer_entity_id}",
                    "measure":"monetary","unit":identity.currency,"currency":identity.currency,
                    "valuation_basis":identity.valuation_basis,"holder_id":identity.holder_entity_id,
                    "issuer_id":identity.issuer_entity_id,"instrument_id":identity.instrument_id,
                },
                "period_index":event.effective_period,"movement_class":component,
                "amount":str(amount),"evidence_ref":event.legal_evidence.evidence_ref if event.legal_evidence else event.event_id,
            })
    return specs


def make_financial_participant(store,journal,authorizer):
    from entity_journal import EntityJournal
    from sfc_projection_registry import verify_sfc_projection_openings
    from sfc_projection_store import append_projected_group,verify_projection_replay,_verify_control_openings
    if not isinstance(journal,EntityJournal):
        raise NativeStoreParticipantError("canonical EntityJournal instance is required")

    def projection_ready():
        with closing(store._connect()) as con:
            if not verify_sfc_projection_openings(con) or not _verify_control_openings(con):
                return False
            groups=con.execute("SELECT COUNT(*) FROM event_groups").fetchone()[0]
        return groups==0 or verify_projection_replay(store)

    if not projection_ready():
        raise NativeStoreParticipantError("financial/SFC opening snapshots or existing projection replay are invalid")

    def decode_group(envelope):
        events=envelope["payload"].get("events")
        if not isinstance(events,list) or not events:
            raise NativeStoreParticipantError("financial event group must contain a non-empty event list")
        return tuple(_decode_journal_event(item) for item in events)

    def revision(con):
        return con.execute("SELECT COUNT(*) FROM event_groups").fetchone()[0]

    def validate(con,native_id,envelope):
        payload=envelope["payload"]
        if payload.get("group_id")!=native_id or envelope["idempotency_key"]!=native_id:
            raise NativeStoreParticipantError("financial native event/idempotency ID must equal group_id")
        if not projection_ready():
            raise NativeStoreParticipantError("financial/SFC opening or existing projection replay failed before prepare")
        events=decode_group(envelope)
        candidate=EntityJournal(journal.registry)
        for event in events: candidate.post(event)
        if envelope.get("stock_flow_movements") != financial_stock_flow_movement_specs(events):
            raise NativeStoreParticipantError("financial T/V/O movement metadata differs from canonical SFC mapper")

    def apply(native_id,envelope,txid):
        payload=envelope["payload"]
        append_projected_group(journal,store,native_id,decode_group(envelope),
            causation_id=payload.get("causation_id"),allow_prepared_txid=txid)

    def exists(con,native_id,envelope):
        return con.execute("SELECT 1 FROM event_groups WHERE group_id=?",(native_id,)).fetchone() is not None

    return NativeStoreParticipant("financial",store,"financial",revision,validate,apply,exists,authorizer)
