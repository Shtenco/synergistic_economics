"""Typed, append-only product registry, native-unit balance and valuation ledger."""
from __future__ import annotations
from dataclasses import asdict, dataclass
from contextlib import closing
from decimal import Decimal
import hashlib, json, sqlite3
from pathlib import Path

D=Decimal
GENESIS="0"*64
DOMAIN=b"SYNERGY_PRODUCT_REGISTER_CHAIN_V1\\0"
STOCKABILITY={"stockable","non_stockable"}
TIME_BASES={"period_stock","period_flow"}


class ProductRegisterError(ValueError):
    pass


@dataclass(frozen=True)
class ProductSpec:
    product_id: str
    grade_id: str
    dimension: str
    native_unit: str
    stockability: str
    time_basis: str
    evidence_ref: str


@dataclass(frozen=True)
class ProductBalance:
    balance_id: str
    product_id: str
    grade_id: str
    period: str
    period_index: int
    boundary: str
    unit: str
    opening: D
    output: D
    imports: D
    intermediate: D
    final: D
    gfcf: D
    exports: D
    losses: D
    closing: D
    evidence_ref: str


@dataclass(frozen=True)
class PriceQuote:
    price_id: str
    product_id: str
    grade_id: str
    price: D
    denominator_unit: str
    currency: str
    period: str
    valuation_basis: str
    source_id: str
    evidence_ref: str


@dataclass(frozen=True)
class ValuationRecord:
    valuation_id: str
    balance_id: str
    price_id: str
    quantity_component: str
    value: D
    evidence_ref: str


def _text(x,field):
    if not isinstance(x,str) or not x or x!=x.strip():
        raise ProductRegisterError(f"{field} must be trimmed non-empty text")


def _amount(x,field):
    if isinstance(x,bool): raise ProductRegisterError(f"{field} must be finite Decimal")
    try: n=D(str(x))
    except Exception as exc: raise ProductRegisterError(f"{field} must be finite Decimal") from exc
    if not n.is_finite() or n<0: raise ProductRegisterError(f"{field} must be finite and non-negative")
    return n


def _canonical(x):
    return json.dumps(x,sort_keys=True,separators=(",",":"),ensure_ascii=False,allow_nan=False)


def _decimal_payload(value):
    row=asdict(value)
    for k,v in tuple(row.items()):
        if isinstance(v,D): row[k]=format(v,"f")
    return row


def _validate_spec(s):
    if not isinstance(s,ProductSpec): raise ProductRegisterError("ProductSpec required")
    for f in ("product_id","grade_id","dimension","native_unit","evidence_ref"): _text(getattr(s,f),f)
    if s.stockability not in STOCKABILITY: raise ProductRegisterError("unknown stockability")
    if s.time_basis not in TIME_BASES: raise ProductRegisterError("unknown time_basis")


def _validate_balance(b,spec,previous):
    if not isinstance(b,ProductBalance): raise ProductRegisterError("ProductBalance required")
    for f in ("balance_id","product_id","grade_id","period","boundary","unit","evidence_ref"): _text(getattr(b,f),f)
    if b.product_id!=spec.product_id or b.grade_id!=spec.grade_id or b.unit!=spec.native_unit:
        raise ProductRegisterError("balance product/grade/native-unit mismatch")
    if not isinstance(b.period_index,int) or isinstance(b.period_index,bool) or b.period_index<0:
        raise ProductRegisterError("period_index must be a non-negative integer")
    if spec.time_basis=="period_flow" and spec.stockability=="non_stockable" and (b.opening!=0 or b.closing!=0):
        raise ProductRegisterError("non-stockable flow product cannot carry opening or closing stock")
    values={k:_amount(getattr(b,k),k) for k in
        ("opening","output","imports","intermediate","final","gfcf","exports","losses","closing")}
    if previous is not None:
        if b.period_index!=previous.period_index+1 or b.opening!=previous.closing:
            raise ProductRegisterError("period sequence or closing-to-opening stock carry-forward mismatch")
        if b.boundary!=previous.boundary:
            raise ProductRegisterError("balance boundary changed within a product stream")
    lhs=values["opening"]+values["output"]+values["imports"]
    rhs=values["intermediate"]+values["final"]+values["gfcf"]+values["exports"]+values["losses"]+values["closing"]
    if lhs!=rhs: raise ProductRegisterError(f"native-unit balance does not close: {lhs} != {rhs}")


def _validate_price(p,spec):
    if not isinstance(p,PriceQuote): raise ProductRegisterError("PriceQuote required")
    for f in ("price_id","product_id","grade_id","denominator_unit","currency","period","valuation_basis","source_id","evidence_ref"):
        _text(getattr(p,f),f)
    if p.product_id!=spec.product_id or p.grade_id!=spec.grade_id: raise ProductRegisterError("price product/grade mismatch")
    if p.denominator_unit!=spec.native_unit: raise ProductRegisterError("price denominator differs from native unit")
    _amount(p.price,"price")


def _validate_valuation(v,price,balance):
    if not isinstance(v,ValuationRecord): raise ProductRegisterError("ValuationRecord required")
    for f in ("valuation_id","balance_id","price_id","quantity_component","evidence_ref"): _text(getattr(v,f),f)
    if v.quantity_component not in {"opening","output","imports","intermediate","final","gfcf","exports","losses","closing"}:
        raise ProductRegisterError("unknown balance quantity component")
    if (v.balance_id!=balance.balance_id or v.price_id!=price.price_id
            or balance.product_id!=price.product_id or balance.grade_id!=price.grade_id
            or balance.period!=price.period or balance.unit!=price.denominator_unit):
        raise ProductRegisterError("valuation, balance and price identities/period/unit mismatch")
    quantity=_amount(getattr(balance,v.quantity_component),v.quantity_component)
    expected=quantity*price.price
    if _amount(v.value,"value")!=expected:
        raise ProductRegisterError("valuation amount differs from referenced balance quantity times price")


class ProductRegister:
    SCHEMA_VERSION=1

    def __init__(self,database_path):
        self.path=str(database_path)
        Path(self.path).parent.mkdir(parents=True,exist_ok=True)
        with closing(self._connect()) as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS product_register_meta(
                    singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                    schema_version INTEGER NOT NULL CHECK(schema_version=1),
                    event_count INTEGER NOT NULL CHECK(event_count>=0),tail_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS product_events(
                    commit_sequence INTEGER PRIMARY KEY CHECK(commit_sequence>0),
                    event_id TEXT NOT NULL UNIQUE,event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL,payload_sha256 TEXT NOT NULL,
                    previous_hash TEXT NOT NULL,chain_hash TEXT NOT NULL);
                CREATE TRIGGER IF NOT EXISTS product_events_no_update BEFORE UPDATE ON product_events
                    BEGIN SELECT RAISE(ABORT,'product register events are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS product_events_no_delete BEFORE DELETE ON product_events
                    BEGIN SELECT RAISE(ABORT,'product register events are immutable'); END;
            """)
            con.execute("INSERT OR IGNORE INTO product_register_meta VALUES(1,1,0,?)",(GENESIS,))

    def _connect(self):
        con=sqlite3.connect(self.path,timeout=30,isolation_level=None)
        con.row_factory=sqlite3.Row
        con.execute("PRAGMA busy_timeout=30000")
        con.execute("PRAGMA synchronous=FULL")
        return con

    @staticmethod
    def _chain(seq,event_id,event_type,digest,previous):
        value={"sequence":seq,"event_id":event_id,"event_type":event_type,
               "payload_sha256":digest,"previous_hash":previous}
        return hashlib.sha256(DOMAIN+_canonical(value).encode()).hexdigest()

    def _replay(self,rows):
        specs,balances,prices,valuations={}, {}, {}, {}
        streams={}
        for row in rows:
            payload=json.loads(row["payload_json"])
            if _canonical(payload)!=row["payload_json"]: raise ProductRegisterError("non-canonical event payload")
            typ=row["event_type"]
            if typ=="product_spec":
                s=ProductSpec(**payload); _validate_spec(s)
                if row["event_id"] != f"SPEC:{s.product_id}:{s.grade_id}":
                    raise ProductRegisterError("product specification event ID mismatch")
                key=(s.product_id,s.grade_id)
                if key in specs: raise ProductRegisterError("duplicate product/grade specification")
                specs[key]=s
            elif typ=="product_balance":
                b=ProductBalance(**(payload | {k:D(payload[k]) for k in
                    ("opening","output","imports","intermediate","final","gfcf","exports","losses","closing")}))
                if row["event_id"] != b.balance_id:
                    raise ProductRegisterError("product balance event ID mismatch")
                key=(b.product_id,b.grade_id)
                if key not in specs: raise ProductRegisterError("balance references unknown product")
                stream=(b.product_id,b.grade_id,b.boundary)
                _validate_balance(b,specs[key],streams.get(stream))
                if b.balance_id in balances: raise ProductRegisterError("duplicate balance ID")
                balances[b.balance_id]=b; streams[stream]=b
            elif typ=="price_quote":
                p=PriceQuote(**(payload | {"price":D(payload["price"])}))
                if row["event_id"] != p.price_id:
                    raise ProductRegisterError("price quote event ID mismatch")
                key=(p.product_id,p.grade_id)
                if key not in specs: raise ProductRegisterError("price references unknown product")
                _validate_price(p,specs[key])
                if p.price_id in prices: raise ProductRegisterError("duplicate price ID")
                prices[p.price_id]=p
            elif typ=="valuation":
                v=ValuationRecord(**(payload | {"value":D(payload["value"])}))
                if row["event_id"] != v.valuation_id:
                    raise ProductRegisterError("valuation event ID mismatch")
                if v.price_id not in prices or v.balance_id not in balances:
                    raise ProductRegisterError("valuation references unknown price or balance")
                _validate_valuation(v,prices[v.price_id],balances[v.balance_id])
                if v.valuation_id in valuations: raise ProductRegisterError("duplicate valuation ID")
                valuations[v.valuation_id]=v
            else: raise ProductRegisterError("unknown product event type")
        return specs,balances,prices,valuations

    def _append(self,event_id,event_type,payload):
        _text(event_id,"event_id")
        payload_json=_canonical(payload)
        digest=hashlib.sha256(payload_json.encode()).hexdigest()
        with closing(self._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                old=con.execute("SELECT payload_sha256,event_type FROM product_events WHERE event_id=?",(event_id,)).fetchone()
                if old:
                    if old["payload_sha256"]!=digest or old["event_type"]!=event_type:
                        raise ProductRegisterError("event ID reused with changed immutable content")
                    con.execute("ROLLBACK")
                    if not self.verify(): raise ProductRegisterError("idempotent retry refused: replay failed")
                    return False
                rows=con.execute("SELECT * FROM product_events ORDER BY commit_sequence").fetchall()
                if not self.verify(): raise ProductRegisterError("existing product register failed replay")
                specs,balances,prices,valuations=self._replay(rows)
                candidate={"event_id":event_id,"event_type":event_type,"payload_json":payload_json,
                           "payload_sha256":digest}
                # Validate the candidate against the full state before appending.
                candidate_row={"event_type":event_type,"payload_json":payload_json}
                self._replay(list(rows)+[candidate_row])
                meta=con.execute("SELECT event_count,tail_hash FROM product_register_meta WHERE singleton_id=1").fetchone()
                seq=meta["event_count"]+1
                chain=self._chain(seq,event_id,event_type,digest,meta["tail_hash"])
                con.execute("INSERT INTO product_events VALUES(?,?,?,?,?,?,?)",
                    (seq,event_id,event_type,payload_json,digest,meta["tail_hash"],chain))
                con.execute("UPDATE product_register_meta SET event_count=?,tail_hash=? WHERE singleton_id=1",
                    (seq,chain))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction: con.execute("ROLLBACK")
                raise

    def register_product(self,spec):
        _validate_spec(spec)
        return self._append(f"SPEC:{spec.product_id}:{spec.grade_id}","product_spec",_decimal_payload(spec))

    def record_balance(self,balance):
        if not isinstance(balance,ProductBalance): raise ProductRegisterError("ProductBalance required")
        return self._append(balance.balance_id,"product_balance",_decimal_payload(balance))

    def record_price(self,quote):
        if not isinstance(quote,PriceQuote): raise ProductRegisterError("PriceQuote required")
        return self._append(quote.price_id,"price_quote",_decimal_payload(quote))

    def record_valuation(self,value):
        if not isinstance(value,ValuationRecord): raise ProductRegisterError("ValuationRecord required")
        return self._append(value.valuation_id,"valuation",_decimal_payload(value))

    def verify(self):
        try:
            with closing(self._connect()) as con:
                meta=con.execute("SELECT * FROM product_register_meta WHERE singleton_id=1").fetchone()
                if meta is None or meta["schema_version"]!=self.SCHEMA_VERSION: return False
                rows=con.execute("SELECT * FROM product_events ORDER BY commit_sequence").fetchall()
                previous=GENESIS
                for seq,row in enumerate(rows,1):
                    if row["commit_sequence"]!=seq or row["previous_hash"]!=previous: return False
                    digest=hashlib.sha256(row["payload_json"].encode()).hexdigest()
                    if digest!=row["payload_sha256"]: return False
                    chain=self._chain(seq,row["event_id"],row["event_type"],digest,previous)
                    if chain!=row["chain_hash"]: return False
                    previous=chain
                self._replay(rows)
                return meta["event_count"]==len(rows) and meta["tail_hash"]==previous
        except (sqlite3.DatabaseError,ValueError,TypeError,KeyError,AttributeError):
            return False

    def valuation(self,valuation_id):
        with closing(self._connect()) as con:
            rows=con.execute("SELECT * FROM product_events ORDER BY commit_sequence").fetchall()
        _,_,_,values=self._replay(rows)
        return values.get(valuation_id)
