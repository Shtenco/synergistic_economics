"""Atomic SFC projection-aware append and deterministic projection recovery.

The module couples the schema-v4 event log, instrument positions, separate
control positions, per-event coverage and the applied-through cursor in one
SQLite transaction. It is a single-host SQLite protocol, not distributed
consensus or a production security certification.
"""
from __future__ import annotations

from contextlib import closing
from decimal import Decimal, localcontext
import hashlib
import json
import sqlite3
from typing import Sequence

import financial_event_store as fes
from entity_journal import EntityJournal, JournalEvent, SECTORS, EVENT_SEMANTICS, EXPECTED_ACCOUNTS
from financial_event_store import FinancialEventStore, FinancialEventStoreError
from sfc_projection_kernel import SFCIdentity, canonical_decimal, replay_positions
from sfc_projection_registry import verify_sfc_projection_openings

D = Decimal
MAPPER_VERSION = "gold2a-entity-journal-mapper@1"
INSTRUMENT_ACCOUNTS = {"loan_asset", "deposit_asset", "interest_receivable"}
CONTROL_IDS = {"impairment_allowance", "writeoff_memorandum"}


class SFCProjectionStoreError(ValueError):
    """Raised when an atomic SFC projection append or recovery check fails."""


def _json(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)


def _dec(value, field):
    try:
        result = D(value)
    except Exception as exc:
        raise SFCProjectionStoreError(f"{field} must be a decimal value") from exc
    if not result.is_finite():
        raise SFCProjectionStoreError(f"{field} must be finite")
    return result


def _canon(value):
    if not isinstance(value, D) or not value.is_finite():
        raise SFCProjectionStoreError("projection amount must be a finite Decimal")
    return canonical_decimal(format(value, "f"))


def _sum_exact(values):
    values = tuple(values)
    if any(not isinstance(value,D) or not value.is_finite() for value in values):
        raise SFCProjectionStoreError("exact projection sum requires finite Decimals")
    with localcontext() as context:
        context.prec = 4096
        return sum(values,D("0"))


def _control_rows(rows):
    if not isinstance(rows, (tuple, list)) or not rows:
        raise SFCProjectionStoreError("explicit control opening positions are required")
    clean, seen = [], set()
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise SFCProjectionStoreError(f"control opening {index} must be a mapping")
        item = {}
        for field in ("control_id", "entity_id", "sector", "currency", "valuation_basis", "evidence_ref"):
            value = row.get(field)
            if not isinstance(value, str) or not value or value != value.strip():
                raise SFCProjectionStoreError(f"control opening {field} must be trimmed non-empty text")
            item[field] = value
        if item["control_id"] not in CONTROL_IDS:
            raise SFCProjectionStoreError("unknown control position")
        if item["sector"] not in SECTORS:
            raise SFCProjectionStoreError("control opening has an unknown institutional sector")
        period = row.get("period")
        if not isinstance(period, int) or isinstance(period, bool) or period != 0:
            raise SFCProjectionStoreError("control openings must explicitly start at period 0")
        amount = canonical_decimal(row.get("amount"))
        if D(amount) < 0:
            raise SFCProjectionStoreError("control opening balances must be non-negative")
        key = tuple(item[field] for field in ("control_id", "entity_id", "currency", "valuation_basis")) + (period,)
        if key in seen:
            raise SFCProjectionStoreError("duplicate control opening identity")
        seen.add(key)
        item.update(period=period, amount=amount)
        clean.append(item)
    owners = {(row["entity_id"],row["currency"],row["valuation_basis"]) for row in clean}
    for owner in owners:
        present = {row["control_id"] for row in clean
                   if (row["entity_id"],row["currency"],row["valuation_basis"]) == owner}
        if present != CONTROL_IDS:
            raise SFCProjectionStoreError("each control owner requires explicit allowance and write-off memorandum openings")
    clean.sort(key=lambda x: (x["control_id"], x["entity_id"], x["currency"], x["valuation_basis"], x["period"]))
    return clean


def activate_control_openings(store: FinancialEventStore, openings: Sequence[dict], *,
                              mapper_version: str, evidence_ref: str) -> bool:
    """Seal separate allowance/memorandum openings without inventing instruments."""
    if not isinstance(store, FinancialEventStore):
        raise SFCProjectionStoreError("FinancialEventStore is required")
    for value, field in ((mapper_version, "mapper_version"), (evidence_ref, "evidence_ref")):
        if not isinstance(value, str) or not value or value != value.strip():
            raise SFCProjectionStoreError(f"{field} must be trimmed non-empty text")
    if mapper_version != CONTROL_MAPPER_VERSION:
        raise SFCProjectionStoreError("unsupported control opening mapper version")
    clean = _control_rows(openings)
    if any(row["evidence_ref"] != evidence_ref for row in clean):
        raise SFCProjectionStoreError("each control opening must cite the sealed control snapshot evidence")
    digest = hashlib.sha256(_json(clean).encode("utf-8")).hexdigest()
    with closing(store._connect()) as con:
        con.execute("BEGIN IMMEDIATE")
        try:
            if not verify_sfc_projection_openings(con):
                raise SFCProjectionStoreError("instrument opening snapshot must be activated first")
            if con.execute("SELECT COUNT(*) FROM event_groups").fetchone()[0]:
                raise SFCProjectionStoreError("control openings must be sealed before the first event")
            con.execute("""CREATE TABLE IF NOT EXISTS sfc_control_opening_meta(
                singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
                schema_version INTEGER NOT NULL CHECK(schema_version=1),
                snapshot_sha256 TEXT NOT NULL, mapper_version TEXT NOT NULL,
                evidence_ref TEXT NOT NULL, opening_count INTEGER NOT NULL CHECK(opening_count>0))""")
            con.execute("""CREATE TABLE IF NOT EXISTS sfc_control_openings(
                control_id TEXT NOT NULL, entity_id TEXT NOT NULL, sector TEXT NOT NULL,
                currency TEXT NOT NULL, valuation_basis TEXT NOT NULL,
                period INTEGER NOT NULL CHECK(period=0), amount TEXT NOT NULL,
                evidence_ref TEXT NOT NULL,
                PRIMARY KEY(control_id,entity_id,currency,valuation_basis,period))""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS sfc_control_openings_no_insert
                BEFORE INSERT ON sfc_control_openings WHEN EXISTS(
                SELECT 1 FROM sfc_control_opening_meta WHERE singleton_id=1)
                BEGIN SELECT RAISE(ABORT,'control opening snapshot is sealed'); END""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS sfc_control_openings_no_update
                BEFORE UPDATE ON sfc_control_openings BEGIN SELECT RAISE(ABORT,'control openings are immutable'); END""")
            con.execute("""CREATE TRIGGER IF NOT EXISTS sfc_control_openings_no_delete
                BEFORE DELETE ON sfc_control_openings BEGIN SELECT RAISE(ABORT,'control openings are immutable'); END""")
            existing = con.execute("SELECT snapshot_sha256,mapper_version,evidence_ref,opening_count FROM sfc_control_opening_meta WHERE singleton_id=1").fetchone()
            if existing:
                if (existing["snapshot_sha256"], existing["mapper_version"], existing["evidence_ref"], existing["opening_count"]) != (digest, mapper_version, evidence_ref, len(clean)):
                    raise SFCProjectionStoreError("control opening snapshot already sealed with different content")
                if not _verify_control_openings(con):
                    raise SFCProjectionStoreError("sealed control opening snapshot is corrupt")
                con.execute("COMMIT")
                return False
            for row in clean:
                con.execute("""INSERT INTO sfc_control_openings(
                    control_id,entity_id,sector,currency,valuation_basis,period,amount,evidence_ref)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    tuple(row[k] for k in ("control_id","entity_id","sector","currency","valuation_basis","period","amount","evidence_ref")))
            con.execute("""INSERT INTO sfc_control_opening_meta VALUES(1,1,?,?,?,?)""",
                        (digest, mapper_version, evidence_ref, len(clean)))
            con.execute("COMMIT")
            return True
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            raise


def _verify_control_openings(con):
    try:
        meta = con.execute("SELECT * FROM sfc_control_opening_meta WHERE singleton_id=1").fetchone()
        if meta is None:
            return False
        rows = con.execute("""SELECT control_id,entity_id,sector,currency,valuation_basis,
            period,amount,evidence_ref FROM sfc_control_openings""").fetchall()
        clean = [dict(row) for row in rows]
        clean.sort(key=lambda x: (x["control_id"],x["entity_id"],x["currency"],x["valuation_basis"],x["period"]))
        if (meta["schema_version"] != 1 or meta["mapper_version"] != CONTROL_MAPPER_VERSION
                or not isinstance(meta["evidence_ref"],str) or not meta["evidence_ref"].strip()
                or len(clean) != meta["opening_count"]):
            return False
        for row in clean:
            if (canonical_decimal(row["amount"]) != row["amount"] or row["period"] != 0
                    or row["evidence_ref"] != meta["evidence_ref"]):
                return False
        return hashlib.sha256(_json(clean).encode("utf-8")).hexdigest() == meta["snapshot_sha256"]
    except (sqlite3.DatabaseError, TypeError, ValueError, KeyError):
        return False


def _schema(con):
    statements = (
        """CREATE TABLE IF NOT EXISTS sfc_projection_runtime(
            singleton_id INTEGER PRIMARY KEY CHECK(singleton_id=1),
            mapper_version TEXT NOT NULL, applied_commit_sequence INTEGER NOT NULL CHECK(applied_commit_sequence>=0),
            current_period INTEGER NOT NULL CHECK(current_period>=0), state_sha256 TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS sfc_projection_positions(
            instrument_id TEXT NOT NULL,instrument_class TEXT NOT NULL,holder_entity_id TEXT NOT NULL,
            holder_sector TEXT NOT NULL,issuer_entity_id TEXT NOT NULL,issuer_sector TEXT NOT NULL,
            currency TEXT NOT NULL,maturity TEXT NOT NULL,denomination TEXT NOT NULL,valuation_basis TEXT NOT NULL,
            period INTEGER NOT NULL CHECK(period>=0),opening_balance TEXT NOT NULL,
            transaction_delta TEXT NOT NULL,revaluation_delta TEXT NOT NULL,other_volume_delta TEXT NOT NULL,
            closing_balance TEXT NOT NULL,
            PRIMARY KEY(instrument_id,instrument_class,holder_entity_id,holder_sector,issuer_entity_id,
                issuer_sector,currency,maturity,denomination,valuation_basis,period))""",
        """CREATE TABLE IF NOT EXISTS sfc_control_positions(
            control_id TEXT NOT NULL,entity_id TEXT NOT NULL,sector TEXT NOT NULL,currency TEXT NOT NULL,
            valuation_basis TEXT NOT NULL,period INTEGER NOT NULL CHECK(period>=0),opening_balance TEXT NOT NULL,
            transaction_delta TEXT NOT NULL,revaluation_delta TEXT NOT NULL,other_volume_delta TEXT NOT NULL,
            closing_balance TEXT NOT NULL,
            PRIMARY KEY(control_id,entity_id,currency,valuation_basis,period))""",
        """CREATE TABLE IF NOT EXISTS sfc_event_coverage(
            event_id TEXT PRIMARY KEY REFERENCES events(event_id),group_id TEXT NOT NULL,
            commit_sequence INTEGER NOT NULL,event_index INTEGER NOT NULL,
            disposition TEXT NOT NULL CHECK(disposition IN ('mapped','no_stock_effect')),
            delta_count INTEGER NOT NULL CHECK(delta_count>=0),mapping_version TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS sfc_instrument_deltas(
            event_id TEXT NOT NULL REFERENCES events(event_id),delta_index INTEGER NOT NULL CHECK(delta_index>=0),
            instrument_id TEXT NOT NULL,instrument_class TEXT NOT NULL,holder_entity_id TEXT NOT NULL,
            holder_sector TEXT NOT NULL,issuer_entity_id TEXT NOT NULL,issuer_sector TEXT NOT NULL,
            currency TEXT NOT NULL,maturity TEXT NOT NULL,denomination TEXT NOT NULL,valuation_basis TEXT NOT NULL,
            effective_period INTEGER NOT NULL,component TEXT NOT NULL CHECK(component IN ('T','V','O')),
            amount TEXT NOT NULL,opening_balance TEXT NOT NULL,
            PRIMARY KEY(event_id,delta_index))""",
        """CREATE TABLE IF NOT EXISTS sfc_control_deltas(
            event_id TEXT NOT NULL REFERENCES events(event_id),delta_index INTEGER NOT NULL CHECK(delta_index>=0),
            control_id TEXT NOT NULL,entity_id TEXT NOT NULL,sector TEXT NOT NULL,currency TEXT NOT NULL,
            valuation_basis TEXT NOT NULL,effective_period INTEGER NOT NULL,
            component TEXT NOT NULL CHECK(component IN ('T','V','O')),amount TEXT NOT NULL,opening_balance TEXT NOT NULL,
            PRIMARY KEY(event_id,delta_index))""",
        """CREATE TABLE IF NOT EXISTS sfc_sector_flows(
            period INTEGER NOT NULL,sector TEXT NOT NULL,transaction_asset_delta TEXT NOT NULL,
            transaction_liability_delta TEXT NOT NULL,financial_net_lending TEXT NOT NULL,
            PRIMARY KEY(period,sector))""",
        """CREATE TABLE IF NOT EXISTS sfc_projection_event_checkpoints(
            event_id TEXT PRIMARY KEY REFERENCES events(event_id),commit_sequence INTEGER NOT NULL,
            event_index INTEGER NOT NULL,current_period INTEGER NOT NULL,state_sha256 TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS sfc_projection_group_checkpoints(
            commit_sequence INTEGER PRIMARY KEY,group_id TEXT NOT NULL,current_period INTEGER NOT NULL,
            state_sha256 TEXT NOT NULL)""",
    )
    for statement in statements:
        con.execute(statement)
    for table in ("sfc_event_coverage","sfc_instrument_deltas","sfc_control_deltas",
                  "sfc_projection_event_checkpoints","sfc_projection_group_checkpoints"):
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table}
            BEGIN SELECT RAISE(ABORT,'projection audit rows are immutable'); END""")
        con.execute(f"""CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
            BEGIN SELECT RAISE(ABORT,'projection audit rows are immutable'); END""")


def _identity_from_line(line):
    if line.account not in INSTRUMENT_ACCOUNTS:
        return None
    return SFCIdentity(
        instrument_id=line.instrument_id, instrument_class=line.instrument_class,
        holder_entity_id=line.entity_id, holder_sector=line.institutional_sector,
        issuer_entity_id=line.issuer_entity_id, issuer_sector=line.issuer_sector,
        currency=line.currency, maturity=line.maturity, denomination=line.denomination,
        valuation_basis=line.valuation_basis,
    )


def _map_event(event: JournalEvent):
    instruments, controls = [], []
    for line in event.lines:
        identity = _identity_from_line(line)
        if identity is not None:
            delta = line.amount if line.side == "D" else -line.amount
            instruments.append((identity, event.component, delta))
    if event.event_type == "impairment_allowance_recognition":
        line = next(x for x in event.lines if x.account == "impairment_allowance")
        loan = next(x for x in event.lines if x.account == "impairment_expense")
        if not line.currency or not line.valuation_basis:
            raise SFCProjectionStoreError("impairment allowance requires explicit currency and valuation basis")
        controls.append(("impairment_allowance", line.entity_id, line.institutional_sector,
                         line.currency, line.valuation_basis, event.component, line.amount))
    elif event.event_type == "creditor_write_off":
        allowance = next(x for x in event.lines if x.account == "impairment_allowance")
        loan = next(x for x in event.lines if x.account == "loan_asset")
        controls.append(("impairment_allowance", allowance.entity_id, allowance.institutional_sector,
                         loan.currency, loan.valuation_basis, event.component, -allowance.amount))
        controls.append(("writeoff_memorandum", loan.entity_id, loan.institutional_sector,
                         loan.currency, loan.valuation_basis, event.component, event.writeoff_claim_delta))
    return instruments, controls


def _position_key(identity):
    return tuple(getattr(identity, f) for f in SFCIdentity.__dataclass_fields__)


def _verify_event_payload_semantics(event_payload):
    """Fail-closed recovery validation of GOLD-2A source-event semantics."""
    event_type = event_payload.get("event_type")
    if event_type not in EVENT_SEMANTICS:
        raise SFCProjectionStoreError("stored event uses a non-canonical GOLD-2A event type")
    expected_component, expected_legal_effect = EVENT_SEMANTICS[event_type]
    if (event_payload.get("component") != expected_component
            or event_payload.get("legal_effect") != expected_legal_effect):
        raise SFCProjectionStoreError("stored event T/V/O or legal-effect metadata mismatch")
    postings = event_payload.get("postings")
    if not isinstance(postings,list) or not postings:
        raise SFCProjectionStoreError("stored event postings are missing")
    actual = {}
    debit_terms = []
    credit_terms = []
    amounts = set()
    for line in postings:
        account, side = line.get("account"), line.get("side")
        amount = D(line.get("amount"))
        if not amount.is_finite() or amount <= 0 or side not in ("D","C"):
            raise SFCProjectionStoreError("stored event contains an invalid amount or side")
        amounts.add(amount)
        if side == "D":
            debit_terms.append(amount)
        else:
            credit_terms.append(amount)
        actual.setdefault(account,[]).append(side)
    debit = _sum_exact(debit_terms)
    credit = _sum_exact(credit_terms)
    expected = EXPECTED_ACCOUNTS[event_type]
    if set(actual) != set(expected) or debit != credit or len(amounts) != 1:
        raise SFCProjectionStoreError("stored event balance/account composition mismatch")
    for account,(side,count) in expected.items():
        if actual.get(account,[]).count(side) != count or len(actual.get(account,[])) != count:
            raise SFCProjectionStoreError("stored event account-side contract mismatch")
    amount = next(iter(amounts))
    claim_accounts = {"loan_asset","loan_liability","deposit_asset","deposit_liability",
                      "interest_receivable","interest_payable"}
    asset_claims, liability_claims = {}, {}
    for line in postings:
        account = line.get("account")
        if account not in claim_accounts:
            continue
        identity_fields = ("instrument_id","instrument_class","currency","maturity",
                           "denomination","valuation_basis")
        if any(not isinstance(line.get(field),str) or not line[field].strip()
               for field in identity_fields):
            raise SFCProjectionStoreError("stored claim posting has incomplete instrument identity")
        if account in {"loan_asset","deposit_asset","interest_receivable"}:
            if not all(isinstance(line.get(field),str) and line[field].strip()
                       for field in ("entity_id","institutional_sector","issuer_entity_id","issuer_sector")):
                raise SFCProjectionStoreError("stored claim asset lacks holder/issuer identity")
            key = tuple(line[field] for field in identity_fields[:2]) + (
                line["entity_id"],line["institutional_sector"],line["issuer_entity_id"],
                line["issuer_sector"]) + tuple(line[field] for field in identity_fields[2:])
            signed = D(line["amount"]) if line["side"]=="D" else -D(line["amount"])
            asset_claims[key] = _sum_exact((asset_claims.get(key,D("0")),signed))
        else:
            if not all(isinstance(line.get(field),str) and line[field].strip()
                       for field in ("entity_id","institutional_sector","counterparty_entity_id","counterparty_sector")):
                raise SFCProjectionStoreError("stored claim liability lacks issuer/holder identity")
            key = tuple(line[field] for field in identity_fields[:2]) + (
                line["counterparty_entity_id"],line["counterparty_sector"],line["entity_id"],
                line["institutional_sector"]) + tuple(line[field] for field in identity_fields[2:])
            signed = D(line["amount"]) if line["side"]=="C" else -D(line["amount"])
            liability_claims[key] = _sum_exact((liability_claims.get(key,D("0")),signed))
    if event_type in {"bank_loan_origination","interest_accrual","interest_payment",
                      "principal_repayment","legal_debt_forgiveness"} and asset_claims != liability_claims:
        raise SFCProjectionStoreError("stored claim holder/issuer movement mirror mismatch")
    if event_type == "impairment_allowance_recognition":
        allowance = next(x for x in postings if x.get("account")=="impairment_allowance")
        if (not isinstance(allowance.get("currency"),str) or not allowance["currency"].strip()
                or not isinstance(allowance.get("valuation_basis"),str)
                or not allowance["valuation_basis"].strip()):
            raise SFCProjectionStoreError("stored impairment allowance lacks explicit currency/valuation basis")
    if event_type == "creditor_write_off":
        if D(event_payload.get("writeoff_claim_delta")) != amount:
            raise SFCProjectionStoreError("stored write-off memo delta mismatch")
    if event_type == "bank_loan_origination":
        loan = next(x for x in postings if x.get("account")=="loan_asset")
        borrower = loan.get("issuer_entity_id")
        bank = loan.get("entity_id")
        deposit_asset = next(x for x in postings if x.get("account")=="deposit_asset")
        if (loan.get("institutional_sector")!="CB"
                or deposit_asset.get("entity_id")!=borrower
                or deposit_asset.get("issuer_entity_id")!=bank):
            raise SFCProjectionStoreError("stored bank origination participant roles mismatch")
    if event_type == "legal_debt_forgiveness":
        evidence = event_payload.get("legal_evidence")
        parties = evidence.get("parties") if isinstance(evidence,dict) else None
        event_entities = {line.get("entity_id") for line in postings}
        if (D(event_payload.get("forgiven_principal")) != amount or not isinstance(evidence,dict)
                or not all(isinstance(evidence.get(k),str) and evidence[k].strip()
                           for k in ("evidence_ref","authority","effective_at","scope"))
                or evidence.get("scope") != f"principal:{_canon(amount)}"
                or not isinstance(parties,list) or len(parties) < 2
                or len(set(parties)) != len(parties)
                or not set(parties).issubset(event_entities)):
            raise SFCProjectionStoreError("stored legal forgiveness lacks complete legal evidence")
    elif event_payload.get("forgiven_principal") is not None or event_payload.get("legal_evidence") is not None:
        raise SFCProjectionStoreError("non-forgiveness event carries legal forgiveness metadata")
    if event_type != "creditor_write_off" and event_payload.get("writeoff_claim_delta") is not None:
        raise SFCProjectionStoreError("non-write-off event carries a write-off memo delta")


def _map_payload_event(event_payload):
    """Re-derive projection deltas from the immutable source event envelope."""
    _verify_event_payload_semantics(event_payload)
    instruments, controls = [], []
    component = event_payload.get("component")
    event_type = event_payload.get("event_type")
    postings = event_payload.get("postings")
    for line in postings:
        if line.get("account") in INSTRUMENT_ACCOUNTS:
            identity = SFCIdentity(
                instrument_id=line.get("instrument_id"),
                instrument_class=line.get("instrument_class"),
                holder_entity_id=line.get("entity_id"),
                holder_sector=line.get("institutional_sector"),
                issuer_entity_id=line.get("issuer_entity_id"),
                issuer_sector=line.get("issuer_sector"),
                currency=line.get("currency"), maturity=line.get("maturity"),
                denomination=line.get("denomination"), valuation_basis=line.get("valuation_basis"),
            )
            amount = D(line["amount"])
            instruments.append((identity,component,amount if line.get("side")=="D" else -amount))
    if event_type == "impairment_allowance_recognition":
        allowance = next(x for x in postings if x.get("account")=="impairment_allowance")
        if not allowance.get("currency") or not allowance.get("valuation_basis"):
            raise SFCProjectionStoreError("stored impairment allowance lacks explicit valuation dimensions")
        controls.append(("impairment_allowance",allowance["entity_id"],allowance["institutional_sector"],
                         allowance["currency"],allowance["valuation_basis"],component,D(allowance["amount"])))
    elif event_type == "creditor_write_off":
        allowance = next(x for x in postings if x.get("account")=="impairment_allowance")
        loan = next(x for x in postings if x.get("account")=="loan_asset")
        controls.append(("impairment_allowance",allowance["entity_id"],allowance["institutional_sector"],
                         loan["currency"],loan["valuation_basis"],component,-D(allowance["amount"])))
        controls.append(("writeoff_memorandum",loan["entity_id"],loan["institutional_sector"],
                         loan["currency"],loan["valuation_basis"],component,D(event_payload["writeoff_claim_delta"])))
    return instruments, controls


def _state_payload(con, period):
    instrument = [dict(row) for row in con.execute(
        "SELECT instrument_id,instrument_class,holder_entity_id,holder_sector,issuer_entity_id,issuer_sector,currency,maturity,denomination,valuation_basis,opening_balance,transaction_delta,revaluation_delta,other_volume_delta,closing_balance FROM sfc_projection_positions WHERE period=? ORDER BY instrument_id,instrument_class,holder_entity_id,holder_sector,issuer_entity_id,issuer_sector,currency,maturity,denomination,valuation_basis",
        (period,)).fetchall()]
    control = [dict(row) for row in con.execute(
        "SELECT control_id,entity_id,sector,currency,valuation_basis,opening_balance,transaction_delta,revaluation_delta,other_volume_delta,closing_balance FROM sfc_control_positions WHERE period=? ORDER BY control_id,entity_id,currency,valuation_basis",
        (period,)).fetchall()]
    return {"period": period, "instruments": instrument, "controls": control}


def _state_hash(con, period):
    return hashlib.sha256(_json(_state_payload(con, period)).encode("utf-8")).hexdigest()


def _validate_instrument_kernel_replay(con):
    """Use the pure SFC kernel as an independent instrument roll-forward oracle."""
    event_rows = con.execute("""SELECT e.event_id,e.effective_period
        FROM events e JOIN event_groups g ON g.group_id=e.group_id
        WHERE EXISTS(SELECT 1 FROM sfc_instrument_deltas d WHERE d.event_id=e.event_id)
        ORDER BY g.commit_sequence,e.event_index""").fetchall()
    projection_events = []
    event_specs = []
    for event in event_rows:
        rows = con.execute("SELECT * FROM sfc_instrument_deltas WHERE event_id=? ORDER BY delta_index",
                           (event["event_id"],)).fetchall()
        raw_deltas = []
        for row in rows:
            identity = {field:row[field] for field in SFCIdentity.__dataclass_fields__}
            raw_deltas.append({
                "event_id":event["event_id"],"delta_index":row["delta_index"],
                "effective_period":row["effective_period"],"identity":identity,
                "component":row["component"],"amount":row["amount"],
                "opening_balance":row["opening_balance"],
            })
        event_specs.append({"event_id":event["event_id"],"effective_period":event["effective_period"]})
        projection_events.append({"event_id":event["event_id"],"disposition":"mapped","deltas":raw_deltas})
    if not event_specs:
        return True
    openings = {}
    for row in con.execute("SELECT * FROM sfc_projection_positions").fetchall():
        identity = SFCIdentity(**{field:row[field] for field in SFCIdentity.__dataclass_fields__})
        openings[(identity,row["period"])] = row["opening_balance"]
    identities = {key[0] for key in openings}
    replayed = replay_positions(
        event_specs, {"mapping_version":MAPPER_VERSION,"events":projection_events},
        openings, nonnegative_identities=identities)
    for (identity,period),roll in replayed.items():
        key = _position_key(identity)
        where = " AND ".join(f"{field}=?" for field in SFCIdentity.__dataclass_fields__)
        row = con.execute(f"SELECT * FROM sfc_projection_positions WHERE {where} AND period=?",
                          key+(period,)).fetchone()
        if row is None:
            raise SFCProjectionStoreError("pure kernel replay produced a missing materialized position")
        actual = tuple(D(row[field]) for field in (
            "opening_balance","transaction_delta","revaluation_delta",
            "other_volume_delta","closing_balance"))
        expected = (roll.opening,roll.transactions,roll.revaluations,
                    roll.other_volume_changes,roll.closing)
        if actual != expected:
            raise SFCProjectionStoreError("pure SFC kernel replay differs from materialized instrument positions")
    return True


def _initialize_runtime(con):
    existing = con.execute("SELECT singleton_id FROM sfc_projection_runtime WHERE singleton_id=1").fetchone()
    if existing:
        return
    instrument_rows = con.execute("SELECT * FROM sfc_openings ORDER BY instrument_id,instrument_class,holder_entity_id,issuer_entity_id").fetchall()
    control_rows = con.execute("SELECT * FROM sfc_control_openings ORDER BY control_id,entity_id").fetchall()
    periods = {row["period"] for row in instrument_rows} | {row["period"] for row in control_rows}
    if periods != {0}:
        raise SFCProjectionStoreError("P2 requires explicit period-0 openings for every instrument and control position")
    for row in instrument_rows:
        identity = {field: row[field] for field in SFCIdentity.__dataclass_fields__}
        amount = canonical_decimal(row["amount"])
        con.execute("""INSERT INTO sfc_projection_positions(
            instrument_id,instrument_class,holder_entity_id,holder_sector,issuer_entity_id,issuer_sector,
            currency,maturity,denomination,valuation_basis,period,opening_balance,transaction_delta,
            revaluation_delta,other_volume_delta,closing_balance)
            VALUES(?,?,?,?,?,?,?,?,?,?,0,?,'0','0','0',?)""",
            tuple(identity[f] for f in SFCIdentity.__dataclass_fields__) + (amount, amount))
    for row in control_rows:
        amount = canonical_decimal(row["amount"])
        con.execute("""INSERT INTO sfc_control_positions(
            control_id,entity_id,sector,currency,valuation_basis,period,opening_balance,
            transaction_delta,revaluation_delta,other_volume_delta,closing_balance)
            VALUES(?,?,?,?,?,0,?,'0','0','0',?)""",
            (row["control_id"],row["entity_id"],row["sector"],row["currency"],row["valuation_basis"],amount,amount))
    digest = _state_hash(con, 0)
    con.execute("INSERT INTO sfc_projection_runtime VALUES(1,?,0,0,?)", (MAPPER_VERSION, digest))


def _advance_period(con, target):
    runtime = con.execute("SELECT current_period FROM sfc_projection_runtime WHERE singleton_id=1").fetchone()
    current = runtime["current_period"]
    if target < current:
        raise SFCProjectionStoreError("backdated effective period requires explicit period reopen/rebuild")
    for period in range(current + 1, target + 1):
        for row in con.execute("SELECT * FROM sfc_projection_positions WHERE period=?", (period-1,)).fetchall():
            opening = row["closing_balance"]
            fields = tuple(row[f] for f in SFCIdentity.__dataclass_fields__)
            con.execute("""INSERT INTO sfc_projection_positions(
                instrument_id,instrument_class,holder_entity_id,holder_sector,issuer_entity_id,issuer_sector,
                currency,maturity,denomination,valuation_basis,period,opening_balance,transaction_delta,
                revaluation_delta,other_volume_delta,closing_balance)
                VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'0','0','0',?)""",
                fields + (period, opening, opening))
        for row in con.execute("SELECT * FROM sfc_control_positions WHERE period=?", (period-1,)).fetchall():
            opening = row["closing_balance"]
            con.execute("""INSERT INTO sfc_control_positions(
                control_id,entity_id,sector,currency,valuation_basis,period,opening_balance,
                transaction_delta,revaluation_delta,other_volume_delta,closing_balance)
                VALUES(?,?,?,?,?,?,?,'0','0','0',?)""",
                (row["control_id"],row["entity_id"],row["sector"],row["currency"],row["valuation_basis"],period,opening,opening))
        con.execute("UPDATE sfc_projection_runtime SET current_period=? WHERE singleton_id=1", (period,))


def _apply_instrument_delta(con, identity, period, component, amount):
    key = _position_key(identity)
    where = " AND ".join(f"{field}=?" for field in SFCIdentity.__dataclass_fields__)
    row = con.execute(f"SELECT * FROM sfc_projection_positions WHERE {where} AND period=?",
                      key + (period,)).fetchone()
    if row is None:
        raise SFCProjectionStoreError("instrument delta has no explicit opening identity")
    opening = _dec(row["opening_balance"], "opening_balance")
    current_component = {"T":"transaction_delta","V":"revaluation_delta","O":"other_volume_delta"}[component]
    new_component = _sum_exact((_dec(row[current_component], current_component), amount))
    closing = _sum_exact((opening,_dec(row["transaction_delta"],"T"),_dec(row["revaluation_delta"],"V"),_dec(row["other_volume_delta"],"O")))
    if component == "T":
        closing = _sum_exact((opening,new_component,_dec(row["revaluation_delta"],"V"),_dec(row["other_volume_delta"],"O")))
    elif component == "V":
        closing = _sum_exact((opening,_dec(row["transaction_delta"],"T"),new_component,_dec(row["other_volume_delta"],"O")))
    else:
        closing = _sum_exact((opening,_dec(row["transaction_delta"],"T"),_dec(row["revaluation_delta"],"V"),new_component))
    if closing < 0:
        raise SFCProjectionStoreError("GOLD-2A recognized instrument position cannot become negative")
    con.execute(f"UPDATE sfc_projection_positions SET {current_component}=?,closing_balance=? WHERE {where} AND period=?",
                (_canon(new_component),_canon(closing)) + key + (period,))


def _apply_control_delta(con, control_id, entity, sector, currency, basis, period, component, amount):
    row = con.execute("""SELECT * FROM sfc_control_positions WHERE control_id=? AND entity_id=?
        AND currency=? AND valuation_basis=? AND period=?""",
        (control_id,entity,currency,basis,period)).fetchone()
    if row is None or row["sector"] != sector:
        raise SFCProjectionStoreError("control delta has no explicit matching opening position")
    opening = _dec(row["opening_balance"],"control opening")
    col = {"T":"transaction_delta","V":"revaluation_delta","O":"other_volume_delta"}[component]
    updated = _sum_exact((_dec(row[col],col),amount))
    parts = {k:_dec(row[k],k) for k in ("transaction_delta","revaluation_delta","other_volume_delta")}
    parts[{"T":"transaction_delta","V":"revaluation_delta","O":"other_volume_delta"}[component]] = updated
    closing = _sum_exact((opening,*parts.values()))
    if closing < 0:
        raise SFCProjectionStoreError(f"{control_id} control position cannot become negative")
    con.execute(f"""UPDATE sfc_control_positions SET {col}=?,closing_balance=?
        WHERE control_id=? AND entity_id=? AND currency=? AND valuation_basis=? AND period=?""",
        (_canon(updated),_canon(closing),control_id,entity,currency,basis,period))


def _update_sector_flows(con, identity, component, amount, period):
    if component != "T":
        return
    for sector, asset, liability in (
        (identity.holder_sector, amount, D("0")),
        (identity.issuer_sector, D("0"), amount),
    ):
        row = con.execute("SELECT transaction_asset_delta,transaction_liability_delta FROM sfc_sector_flows WHERE period=? AND sector=?",
                          (period,sector)).fetchone()
        old_a, old_l = (D(row[0]),D(row[1])) if row else (D("0"),D("0"))
        new_a, new_l = _sum_exact((old_a,asset)), _sum_exact((old_l,liability))
        nl = _sum_exact((new_a,-new_l))
        con.execute("""INSERT INTO sfc_sector_flows VALUES(?,?,?,?,?)
            ON CONFLICT(period,sector) DO UPDATE SET transaction_asset_delta=excluded.transaction_asset_delta,
            transaction_liability_delta=excluded.transaction_liability_delta,financial_net_lending=excluded.financial_net_lending""",
            (period,sector,_canon(new_a),_canon(new_l),_canon(nl)))


def _assert_control_invariants(con, period):
    instruments = con.execute(
        "SELECT * FROM sfc_projection_positions WHERE period=?", (period,)).fetchall()
    controls = con.execute(
        "SELECT * FROM sfc_control_positions WHERE period=?", (period,)).fetchall()
    for control in controls:
        amount = D(control["closing_balance"])
        if control["control_id"] == "impairment_allowance":
            gross_loan = _sum_exact(
                D(position["closing_balance"]) for position in instruments
                if position["instrument_class"] == "loan"
                and position["holder_entity_id"] == control["entity_id"]
                and position["currency"] == control["currency"]
                and position["valuation_basis"] == control["valuation_basis"])
            if amount < 0 or amount > gross_loan:
                raise SFCProjectionStoreError(
                    "impairment allowance must remain between zero and gross loan assets "
                    "for the same holder, currency and valuation basis")
        elif control["control_id"] == "writeoff_memorandum" and amount < 0:
            raise SFCProjectionStoreError("written-off legal claim memorandum cannot be negative")
    sector_rows = con.execute(
        "SELECT financial_net_lending FROM sfc_sector_flows WHERE period=?", (period,)).fetchall()
    if _sum_exact(D(row[0]) for row in sector_rows) != 0:
        raise SFCProjectionStoreError("transaction-only sector financial net lending must sum to zero")


def append_projected_group(journal: EntityJournal, store: FinancialEventStore, group_id: str,
                           events: Sequence[JournalEvent], *, causation_id: str | None = None) -> bool:
    """Atomically persist events, instrument/control projections, coverage and cursor."""
    if not isinstance(journal, EntityJournal) or not isinstance(store, FinancialEventStore):
        raise SFCProjectionStoreError("canonical EntityJournal and FinancialEventStore are required")
    if not isinstance(events, (tuple,list)) or not events or any(not isinstance(e,JournalEvent) for e in events):
        raise SFCProjectionStoreError("a non-empty sequence of canonical JournalEvent values is required")
    initial_ids = set(journal.events)
    try:
        for event in events:
            result = journal.post(event)
            if result[0] != result[1]:
                raise SFCProjectionStoreError("unbalanced validated journal event")
        from financial_journal_adapter import _event_payload
        payloads = [_event_payload(e) for e in events]
        group_id, causation_id, normalized = fes._validate_group(group_id, causation_id, payloads)
        envelope = {"group_id":group_id,"causation_id":causation_id,"events":normalized}
        payload_json = fes._canonical_json(envelope)
        payload_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
        event_rows = []
        for event in normalized:
            event_json = fes._canonical_json(event)
            event_rows.append((event["event_id"],event["event_type"],event["effective_period"],len(event_rows),
                               hashlib.sha256(event_json.encode("utf-8")).hexdigest(),event_json,event["postings"]))
        mapped = [_map_event(e) for e in events]
        periods = [e.effective_period for e in events]
        if periods != sorted(periods):
            raise SFCProjectionStoreError("events inside a transaction group must be ordered by effective period")

        with closing(store._connect()) as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                if not verify_sfc_projection_openings(con) or not _verify_control_openings(con):
                    raise SFCProjectionStoreError("both instrument and control opening snapshots must be sealed")
                _schema(con)
                if not fes._verify_group_chain(con) or not fes._verify_event_posting_mirrors(con):
                    raise SFCProjectionStoreError("event-store chain or posting mirrors are corrupt")
                _initialize_runtime(con)
                existing = con.execute("SELECT payload_sha256,commit_sequence FROM event_groups WHERE group_id=?",(group_id,)).fetchone()
                if existing:
                    if existing["payload_sha256"] != payload_hash:
                        raise SFCProjectionStoreError("group ID reused with changed immutable content")
                    coverage = con.execute("SELECT COUNT(*) FROM sfc_event_coverage WHERE group_id=?",(group_id,)).fetchone()[0]
                    runtime = con.execute("SELECT applied_commit_sequence FROM sfc_projection_runtime WHERE singleton_id=1").fetchone()
                    checkpoints = con.execute("SELECT COUNT(*) FROM sfc_projection_event_checkpoints WHERE commit_sequence=?",(existing["commit_sequence"],)).fetchone()[0]
                    if (coverage != len(events) or runtime is None
                            or runtime["applied_commit_sequence"] < existing["commit_sequence"]
                            or checkpoints != len(events)):
                        raise SFCProjectionStoreError("existing group has incomplete projection/cursor coverage")
                    con.execute("ROLLBACK")
                    return False
                for event_id,*_ in event_rows:
                    if con.execute("SELECT 1 FROM events WHERE event_id=?",(event_id,)).fetchone():
                        raise SFCProjectionStoreError(f"event ID already exists: {event_id}")
                next_sequence = con.execute("SELECT COALESCE(MAX(commit_sequence),0)+1 FROM event_groups").fetchone()[0]
                tail = con.execute("SELECT group_chain_hash FROM event_groups ORDER BY commit_sequence DESC LIMIT 1").fetchone()
                previous_hash = tail["group_chain_hash"] if tail else fes._CHAIN_GENESIS
                chain_hash = fes._group_chain_hash(next_sequence,group_id,payload_hash,previous_hash)
                con.execute("""INSERT INTO event_groups(group_id,causation_id,commit_sequence,previous_group_hash,
                    group_chain_hash,payload_sha256,payload_json) VALUES(?,?,?,?,?,?,?)""",
                    (group_id,causation_id,next_sequence,previous_hash,chain_hash,payload_hash,payload_json))
                for event_id,event_type,period,event_index,event_hash,event_json,postings in event_rows:
                    con.execute("""INSERT INTO events(event_id,group_id,event_type,effective_period,event_index,payload_sha256,payload_json)
                        VALUES(?,?,?,?,?,?,?)""",(event_id,group_id,event_type,period,event_index,event_hash,event_json))
                    for line_no,posting in enumerate(postings):
                        con.execute("INSERT INTO journal_lines(event_id,line_no,posting_json) VALUES(?,?,?)",
                                    (event_id,line_no,fes._canonical_json(posting)))

                for index,(event,instrument_deltas,control_deltas) in enumerate(zip(events,*zip(*mapped))):
                    _advance_period(con,event.effective_period)
                    disposition = "mapped" if instrument_deltas or control_deltas else "no_stock_effect"
                    total_deltas = len(instrument_deltas)+len(control_deltas)
                    con.execute("""INSERT INTO sfc_event_coverage VALUES(?,?,?,?,?,?,?)""",
                        (event.event_id,group_id,next_sequence,index,disposition,total_deltas,MAPPER_VERSION))
                    delta_index = 0
                    for identity,component,amount in instrument_deltas:
                        row = con.execute("""SELECT opening_balance FROM sfc_projection_positions WHERE
                            instrument_id=? AND instrument_class=? AND holder_entity_id=? AND holder_sector=?
                            AND issuer_entity_id=? AND issuer_sector=? AND currency=? AND maturity=?
                            AND denomination=? AND valuation_basis=? AND period=?""",
                            _position_key(identity)+(event.effective_period,)).fetchone()
                        if row is None:
                            raise SFCProjectionStoreError("instrument delta missing explicit period opening")
                        opening = D(row["opening_balance"])
                        _apply_instrument_delta(con,identity,event.effective_period,component,amount)
                        con.execute("""INSERT INTO sfc_instrument_deltas VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (event.event_id,delta_index,*_position_key(identity),event.effective_period,component,
                             _canon(amount),_canon(opening)))
                        _update_sector_flows(con,identity,component,amount,event.effective_period)
                        delta_index += 1
                    control_index = 0
                    for control_id,entity,sector,currency,basis,component,amount in control_deltas:
                        row = con.execute("""SELECT opening_balance FROM sfc_control_positions WHERE control_id=?
                            AND entity_id=? AND currency=? AND valuation_basis=? AND period=?""",
                            (control_id,entity,currency,basis,event.effective_period)).fetchone()
                        if row is None:
                            raise SFCProjectionStoreError("control delta missing explicit period opening")
                        opening = D(row["opening_balance"])
                        _apply_control_delta(con,control_id,entity,sector,currency,basis,event.effective_period,component,amount)
                        con.execute("""INSERT INTO sfc_control_deltas VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
                            (event.event_id,control_index,control_id,entity,sector,currency,basis,
                             event.effective_period,component,_canon(amount),_canon(opening)))
                        control_index += 1
                    _assert_control_invariants(con,event.effective_period)
                    digest = _state_hash(con,event.effective_period)
                    con.execute("INSERT INTO sfc_projection_event_checkpoints VALUES(?,?,?,?,?)",
                        (event.event_id,next_sequence,index,event.effective_period,digest))
                _validate_instrument_kernel_replay(con)
                runtime = con.execute("SELECT current_period FROM sfc_projection_runtime WHERE singleton_id=1").fetchone()
                digest = _state_hash(con,runtime["current_period"])
                con.execute("UPDATE sfc_projection_runtime SET applied_commit_sequence=?,state_sha256=? WHERE singleton_id=1",
                            (next_sequence,digest))
                con.execute("INSERT INTO sfc_projection_group_checkpoints VALUES(?,?,?,?)",
                            (next_sequence,group_id,runtime["current_period"],digest))
                con.execute("COMMIT")
                return True
            except Exception:
                if con.in_transaction:
                    con.execute("ROLLBACK")
                raise
    except Exception:
        for event in events:
            if event.event_id not in initial_ids and journal.events.get(event.event_id) == event:
                journal.events.pop(event.event_id,None)
        raise


def verify_projection_replay(store: FinancialEventStore) -> bool:
    """Read-only deterministic rebuild and comparison of positions, coverage and cursor."""
    try:
        with closing(store._connect()) as con:
            con.execute("BEGIN")
            if not verify_sfc_projection_openings(con) or not _verify_control_openings(con):
                return False
            if not fes._verify_group_chain(con) or not fes._verify_event_posting_mirrors(con):
                return False
            if not con.execute("SELECT 1 FROM sfc_projection_runtime WHERE singleton_id=1").fetchone():
                return False
            groups = con.execute("SELECT commit_sequence,payload_json FROM event_groups ORDER BY commit_sequence").fetchall()
            coverage = con.execute("SELECT COUNT(*) FROM sfc_event_coverage").fetchone()[0]
            event_count = con.execute("SELECT COUNT(*) FROM events").fetchone()[0]
            if coverage != event_count:
                return False
            runtime_meta = con.execute("SELECT mapper_version FROM sfc_projection_runtime WHERE singleton_id=1").fetchone()
            if runtime_meta is None or runtime_meta["mapper_version"] != MAPPER_VERSION:
                return False
            if con.execute("SELECT COUNT(*) FROM sfc_projection_event_checkpoints").fetchone()[0] != event_count:
                return False
            if con.execute("SELECT COUNT(*) FROM sfc_projection_group_checkpoints").fetchone()[0] != len(groups):
                return False
            event_checkpoint_rows = con.execute("SELECT * FROM sfc_projection_event_checkpoints").fetchall()
            event_checkpoint_map = {row["event_id"]:row for row in event_checkpoint_rows}
            group_checkpoint_rows = con.execute("SELECT * FROM sfc_projection_group_checkpoints ORDER BY commit_sequence").fetchall()
            for group_row, checkpoint in zip(groups, group_checkpoint_rows):
                if checkpoint["commit_sequence"] != group_row["commit_sequence"]:
                    return False
                envelope = json.loads(group_row["payload_json"])
                group_events = envelope.get("events", [])
                if not group_events:
                    return False
                last_event = group_events[-1]
                last_checkpoint = event_checkpoint_map.get(last_event.get("event_id"))
                if (checkpoint["group_id"] != envelope.get("group_id")
                        or last_checkpoint is None
                        or checkpoint["current_period"] != last_event.get("effective_period")
                        or checkpoint["state_sha256"] != last_checkpoint["state_sha256"]):
                    return False
            coverage_rows = con.execute("""SELECT c.event_id,c.commit_sequence,c.event_index,c.mapping_version,
                c.disposition,c.delta_count,e.group_id AS stored_group_id,
                e.event_index AS stored_event_index,g.commit_sequence AS stored_sequence,e.payload_json
                FROM sfc_event_coverage c JOIN events e ON e.event_id=c.event_id
                JOIN event_groups g ON g.group_id=e.group_id""").fetchall()
            event_components = {}
            for item in coverage_rows:
                event_payload = json.loads(item["payload_json"])
                event_components[item["event_id"]] = event_payload.get("component")
                checkpoint = event_checkpoint_map.get(item["event_id"])
                if (item["group_id"] != item["stored_group_id"]
                        or item["commit_sequence"] != item["stored_sequence"]
                        or item["event_index"] != item["stored_event_index"]
                        or item["mapping_version"] != MAPPER_VERSION
                        or event_payload.get("component") not in ("T","V","O")
                        or checkpoint is None
                        or checkpoint["commit_sequence"] != item["commit_sequence"]
                        or checkpoint["event_index"] != item["event_index"]
                        or checkpoint["current_period"] != event_payload.get("effective_period")):
                    return False
            deltas = con.execute("""SELECT d.*,e.group_id,e.event_index,g.commit_sequence FROM sfc_instrument_deltas d
                JOIN events e ON e.event_id=d.event_id JOIN event_groups g ON g.group_id=e.group_id
                ORDER BY g.commit_sequence,e.event_index,d.delta_index""").fetchall()
            control_deltas = con.execute("""SELECT d.*,e.group_id,e.event_index,g.commit_sequence FROM sfc_control_deltas d
                JOIN events e ON e.event_id=d.event_id JOIN event_groups g ON g.group_id=e.group_id
                ORDER BY g.commit_sequence,e.event_index,d.delta_index""").fetchall()
            # Re-derive every mapper output from the immutable source event,
            # then compare the persisted delta rows byte-for-byte at typed precision.
            for item in coverage_rows:
                event_payload = json.loads(item["payload_json"])
                expected_i, expected_c = _map_payload_event(event_payload)
                event_id = item["event_id"]
                stored_i = [row for row in deltas if row["event_id"]==event_id]
                stored_c = [row for row in control_deltas if row["event_id"]==event_id]
                exp_i = sorted((_position_key(identity),component,amount,event_payload["effective_period"])
                               for identity,component,amount in expected_i)
                got_i = sorted((tuple(row[f] for f in SFCIdentity.__dataclass_fields__),
                                row["component"],D(row["amount"]),row["effective_period"])
                               for row in stored_i)
                exp_c = sorted((cid,entity,sector,currency,basis,component,amount,event_payload["effective_period"])
                               for cid,entity,sector,currency,basis,component,amount in expected_c)
                got_c = sorted((row["control_id"],row["entity_id"],row["sector"],row["currency"],
                                row["valuation_basis"],row["component"],D(row["amount"]),row["effective_period"])
                               for row in stored_c)
                if exp_i != got_i or exp_c != got_c:
                    return False
                if [row["delta_index"] for row in stored_i] != list(range(len(stored_i))):
                    return False
                if [row["delta_index"] for row in stored_c] != list(range(len(stored_c))):
                    return False
                n = len(stored_i)+len(stored_c)
                if (n != item["delta_count"]
                        or (item["disposition"]=="mapped" and n==0)
                        or (item["disposition"]=="no_stock_effect" and n!=0)):
                    return False
            # Rebuild positions using the same explicit openings, never zero defaults.
            instrument_expected = {}
            for row in con.execute("SELECT * FROM sfc_openings").fetchall():
                identity = tuple(row[f] for f in SFCIdentity.__dataclass_fields__)
                instrument_expected[(identity,0)] = [D(row["amount"]),D(0),D(0),D(0)]
            control_expected = {}
            for row in con.execute("SELECT * FROM sfc_control_openings").fetchall():
                key = (row["control_id"],row["entity_id"],row["sector"],row["currency"],row["valuation_basis"],0)
                control_expected[key] = [D(row["amount"]),D(0),D(0),D(0)]
            checkpoints = {r["event_id"]:r["state_sha256"] for r in con.execute("SELECT * FROM sfc_projection_event_checkpoints").fetchall()}
            event_order = con.execute("""SELECT e.event_id,e.effective_period,e.event_index,g.commit_sequence
                FROM events e JOIN event_groups g ON g.group_id=e.group_id ORDER BY g.commit_sequence,e.event_index""").fetchall()
            inst_by_event, ctrl_by_event = {}, {}
            for row in deltas: inst_by_event.setdefault(row["event_id"],[]).append(row)
            for row in control_deltas: ctrl_by_event.setdefault(row["event_id"],[]).append(row)
            current = 0
            for ev in event_order:
                target = ev["effective_period"]
                if target < current:
                    return False
                for p in range(current+1,target+1):
                    for (ident,oldp),vals in list(instrument_expected.items()):
                        if oldp==p-1: instrument_expected[(ident,p)] = [_sum_exact((vals[0],*vals[1:])),D(0),D(0),D(0)]
                    for (cid,ent,sec,cur,basis,oldp),vals in list(control_expected.items()):
                        if oldp==p-1: control_expected[(cid,ent,sec,cur,basis,p)] = [_sum_exact((vals[0],*vals[1:])),D(0),D(0),D(0)]
                current = target
                for row in inst_by_event.get(ev["event_id"],[]):
                    ident = tuple(row[f] for f in SFCIdentity.__dataclass_fields__)
                    key=(ident,target)
                    if key not in instrument_expected or instrument_expected[key][0] != D(row["opening_balance"]):
                        return False
                    col={"T":1,"V":2,"O":3}[row["component"]]
                    instrument_expected[key][col] = _sum_exact((instrument_expected[key][col],D(row["amount"])))
                for row in ctrl_by_event.get(ev["event_id"],[]):
                    key=(row["control_id"],row["entity_id"],row["sector"],row["currency"],row["valuation_basis"],target)
                    if key not in control_expected or control_expected[key][0] != D(row["opening_balance"]):
                        return False
                    col={"T":1,"V":2,"O":3}[row["component"]]
                    control_expected[key][col] = _sum_exact((control_expected[key][col],D(row["amount"])))
                # Event checkpoint hash is recomputed from rebuilt state at this period.
                inst_payload=[]
                for (ident,p),vals in sorted(instrument_expected.items(),key=lambda x:(x[0][1],x[0][0])):
                    if p==target:
                        inst_payload.append(dict(zip(
                            tuple(SFCIdentity.__dataclass_fields__),
                            ident
                        )) | {"opening_balance":_canon(vals[0]),"transaction_delta":_canon(vals[1]),
                              "revaluation_delta":_canon(vals[2]),"other_volume_delta":_canon(vals[3]),
                              "closing_balance":_canon(_sum_exact((vals[0],*vals[1:])))})
                ctrl_payload=[]
                for (cid,ent,sec,cur,basis,p),vals in sorted(control_expected.items()):
                    if p==target:
                        ctrl_payload.append({"control_id":cid,"entity_id":ent,"sector":sec,"currency":cur,
                            "valuation_basis":basis,"opening_balance":_canon(vals[0]),
                            "transaction_delta":_canon(vals[1]),"revaluation_delta":_canon(vals[2]),
                            "other_volume_delta":_canon(vals[3]),"closing_balance":_canon(_sum_exact((vals[0],*vals[1:])))})
                digest=hashlib.sha256(_json({"period":target,"instruments":inst_payload,"controls":ctrl_payload}).encode("utf-8")).hexdigest()
                if checkpoints.get(ev["event_id"]) != digest:
                    return False
            # Compare all rebuilt rows with materialized rows.
            for (ident,period),vals in instrument_expected.items():
                row=con.execute("""SELECT opening_balance,transaction_delta,revaluation_delta,other_volume_delta,closing_balance
                    FROM sfc_projection_positions WHERE instrument_id=? AND instrument_class=? AND holder_entity_id=? AND holder_sector=?
                    AND issuer_entity_id=? AND issuer_sector=? AND currency=? AND maturity=? AND denomination=? AND valuation_basis=? AND period=?""",
                    ident+(period,)).fetchone()
                if row is None or [D(row[k]) for k in ("opening_balance","transaction_delta","revaluation_delta","other_volume_delta","closing_balance")] != [vals[0],*vals[1:],vals[0]+sum(vals[1:],D(0))]:
                    return False
            for (cid,ent,sec,cur,basis,period),vals in control_expected.items():
                row=con.execute("""SELECT opening_balance,transaction_delta,revaluation_delta,other_volume_delta,closing_balance
                    FROM sfc_control_positions WHERE control_id=? AND entity_id=? AND currency=? AND valuation_basis=? AND period=?""",
                    (cid,ent,cur,basis,period)).fetchone()
                if row is None or row["sector"] != sec or [D(row[k]) for k in ("opening_balance","transaction_delta","revaluation_delta","other_volume_delta","closing_balance")] != [vals[0],*vals[1:],vals[0]+sum(vals[1:],D(0))]:
                    return False
            runtime=con.execute("SELECT applied_commit_sequence,current_period,state_sha256 FROM sfc_projection_runtime WHERE singleton_id=1").fetchone()
            max_seq=groups[-1]["commit_sequence"] if groups else 0
            if runtime["applied_commit_sequence"] != max_seq or runtime["current_period"] != current:
                return False
            if runtime["state_sha256"] != _state_hash(con,current):
                return False
            _validate_instrument_kernel_replay(con)
            expected_flows = {}
            for row in deltas:
                if row["component"] != "T":
                    continue
                amount = D(row["amount"])
                period = row["effective_period"]
                for sector, asset, liability in (
                    (row["holder_sector"], amount, D("0")),
                    (row["issuer_sector"], D("0"), amount),
                ):
                    key = (period, sector)
                    old_a, old_l = expected_flows.get(key, (D("0"), D("0")))
                    expected_flows[key] = (_sum_exact((old_a,asset)), _sum_exact((old_l,liability)))
            actual_flows = {}
            for row in con.execute("SELECT * FROM sfc_sector_flows").fetchall():
                actual_flows[(row["period"], row["sector"])] = (
                    D(row["transaction_asset_delta"]),
                    D(row["transaction_liability_delta"]),
                    D(row["financial_net_lending"]),
                )
            normalized_expected = {key: (a, l, _sum_exact((a,-l))) for key, (a,l) in expected_flows.items()}
            if actual_flows != normalized_expected:
                return False
            for period in {key[0] for key in actual_flows}:
                if _sum_exact(values[2] for key, values in actual_flows.items() if key[0] == period) != 0:
                    return False
            expected_instrument_count = len(instrument_expected)
            actual_instrument_count = con.execute("SELECT COUNT(*) FROM sfc_projection_positions").fetchone()[0]
            expected_control_count = len(control_expected)
            actual_control_count = con.execute("SELECT COUNT(*) FROM sfc_control_positions").fetchone()[0]
            if actual_instrument_count != expected_instrument_count or actual_control_count != expected_control_count:
                return False
            return True
    except (sqlite3.DatabaseError, ValueError, TypeError, KeyError, AttributeError, SFCProjectionStoreError):
        return False
