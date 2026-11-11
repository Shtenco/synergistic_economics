#!/usr/bin/env python3
"""Independent standard-library Decimal oracle for SFC-GOLD-2A.

No production, journal, SQLite, projection, or recovery modules are imported.
The only shared input is the frozen JSON corpus.
"""
from collections import defaultdict
from decimal import Decimal
import copy
import json
import sys
from pathlib import Path

D = Decimal
DEFAULT_CORPUS = Path(__file__).with_name("SFC_GOLD_2A_CORPUS.json")
ACCOUNT_KEYS = (
    "loan_asset", "loan_liability", "impairment_allowance",
    "interest_receivable", "interest_payable", "deposit_asset",
    "deposit_liability",
)
METRIC_KEYS = ACCOUNT_KEYS + ("writeoff_memorandum", "net_loan_carrying")
NORMAL = {
    "loan_asset": "D", "interest_receivable": "D", "deposit_asset": "D",
    "loan_liability": "C", "interest_payable": "C", "deposit_liability": "C",
    "impairment_allowance": "C",
}
EXPECTED = {
    "bank_loan_origination": ("T", {"loan_asset": ("D","100"), "loan_liability": ("C","100"), "deposit_asset": ("D","100"), "deposit_liability": ("C","100")}),
    "interest_accrual": ("T", {"interest_receivable": ("D","10"), "interest_income": ("C","10"), "interest_expense": ("D","10"), "interest_payable": ("C","10")}),
    "interest_payment": ("T", {"deposit_liability": ("D","4"), "interest_receivable": ("C","4"), "interest_payable": ("D","4"), "deposit_asset": ("C","4")}),
    "impairment_allowance_recognition": ("V", {"impairment_expense": ("D","20"), "impairment_allowance": ("C","20")}),
    "principal_repayment": ("T", {"loan_liability": ("D","20"), "loan_asset": ("C","20"), "deposit_liability": ("D","20"), "deposit_asset": ("C","20")}),
    "creditor_write_off": ("O", {"impairment_allowance": ("D","15"), "loan_asset": ("C","15")}),
    "legal_debt_forgiveness": ("T", {"debt_forgiveness_expense": ("D","5"), "loan_asset": ("C","5"), "loan_liability": ("D","5"), "debt_forgiveness_gain": ("C","5")}),
}
IDENTITY_FIELDS = ("instrument_id","instrument_class","currency","maturity","denomination","valuation_basis")


class OracleError(ValueError):
    pass


def dec(value, label):
    if not isinstance(value, str):
        raise OracleError(label + " must be a decimal string")
    try:
        x = D(value)
    except Exception as exc:
        raise OracleError(label + " is not decimal") from exc
    if not x.is_finite():
        raise OracleError(label + " must be finite")
    return x


def canonical(x):
    if x == 0:
        return "0"
    return format(x.normalize(), "f")


def identity_key(p, account):
    for field in IDENTITY_FIELDS:
        if not isinstance(p.get(field), str) or not p[field].strip():
            raise OracleError("incomplete instrument identity: " + field)
    entity = p.get("entity_id")
    cp = p.get("counterparty_entity_id")
    issuer = p.get("issuer_entity_id")
    if account.endswith("_asset"):
        holder = entity
    else:
        holder = cp
    if not all(isinstance(x, str) and x.strip() for x in (holder, issuer)):
        raise OracleError("missing holder/issuer identity")
    return tuple(p[field] for field in IDENTITY_FIELDS) + (holder, issuer)


def expected_postings(event):
    rows = event.get("postings")
    if not isinstance(rows, list) or not rows:
        raise OracleError("event requires postings")
    actual = defaultdict(list)
    debit = D(0)
    credit = D(0)
    for row in rows:
        if not isinstance(row, dict):
            raise OracleError("posting must be an object")
        account, side = row.get("account"), row.get("side")
        if not isinstance(account, str) or not account:
            raise OracleError("posting account missing")
        if side not in ("D", "C"):
            raise OracleError("posting side must be D or C")
        amount = dec(row.get("amount"), "posting.amount")
        if amount <= 0:
            raise OracleError("posting amount must be positive")
        actual[account].append((side, canonical(amount)))
        if side == "D":
            debit += amount
        else:
            credit += amount
        if account in NORMAL:
            identity_key(row, account)
    if debit != credit:
        raise OracleError(f"event {event.get('event_id')} unbalanced: {debit} != {credit}")
    return {k: sorted(v) for k,v in actual.items()}


def metrics(b):
    result = {k: canonical(b[k]) for k in ACCOUNT_KEYS}
    result["writeoff_memorandum"] = canonical(b["writeoff_memorandum"])
    result["net_loan_carrying"] = canonical(b["loan_asset"] - b["impairment_allowance"])
    return result


def evaluate(corpus):
    if corpus.get("corpus_id") != "SFC-GOLD-2A" or corpus.get("version") != "1.0.0":
        raise OracleError("unsupported corpus identity/version")
    if corpus.get("status") != "FROZEN_SYNTHETIC_CONTROL_CORPUS":
        raise OracleError("corpus is not frozen")
    entities = {r["entity_id"]:r["sector"] for r in corpus.get("entities", [])}
    if not entities or len(entities) != len(corpus.get("entities", [])):
        raise OracleError("entity registry is empty or duplicated")
    periods = corpus.get("periods")
    if [p.get("period") for p in periods] != [1,2,3,4]:
        raise OracleError("periods must be contiguous 1..4")
    opening = corpus.get("opening_snapshot", {})
    if opening.get("period") != 0:
        raise OracleError("opening snapshot must be period 0")
    b = {k: dec(opening["balances"][k], "opening."+k) for k in ACCOUNT_KEYS}
    b["writeoff_memorandum"] = dec(opening["balances"]["writeoff_memorandum"], "opening.writeoff")
    event_ids = set()
    by_period = defaultdict(list)
    checkpoints = {r["after_event_id"]:r["balances"] for r in corpus.get("replay_checkpoints", [])}
    if len(checkpoints) != len(corpus.get("replay_checkpoints", [])):
        raise OracleError("duplicate replay checkpoint")
    period_open = {}
    period_flow = {}
    replay = []
    for period in periods:
        n = period["period"]
        for key in METRIC_KEYS:
            expected_open = dec(period["opening_balances"][key], f"P{n}.opening.{key}")
            actual_open = D(metrics(b)[key])
            if expected_open != actual_open:
                raise OracleError(f"P{n} opening {key} does not equal prior close: {expected_open} != {actual_open}")
        period_open[n] = metrics(b)
        period_flow[n] = {k:{c:D(0) for c in "TVO"} for k in METRIC_KEYS}
        events = [e for e in corpus["events"] if e["effective_period"] == n]
        for event in events:
            eid = event.get("event_id")
            if not isinstance(eid,str) or not eid or eid in event_ids:
                raise OracleError("missing or duplicate event ID")
            event_ids.add(eid)
            et = event.get("event_type")
            if et not in EXPECTED:
                raise OracleError("unsupported event type: "+str(et))
            component, expected = EXPECTED[et]
            if event.get("component") != component:
                raise OracleError(f"{eid}: incorrect T/V/O component")
            actual = expected_postings(event)
            normalized_expected = {k:[v] for k,v in expected.items()}
            if actual != normalized_expected:
                raise OracleError(f"{eid}: event posting composition/amount differs from frozen semantic contract")
            for row in event["postings"]:
                entity = row["entity_id"]
                sector = row.get("institutional_sector")
                if entities.get(entity) != sector:
                    raise OracleError(f"{eid}: entity/sector mismatch")
                for efield,sfield in (("counterparty_entity_id","counterparty_sector"),("issuer_entity_id","issuer_sector")):
                    related = row.get(efield)
                    if related is not None and entities.get(related) != row.get(sfield):
                        raise OracleError(f"{eid}: {efield}/{sfield} mismatch")
                account = row["account"]
                if account not in NORMAL:
                    continue
                amount = dec(row["amount"], "amount")
                delta = amount if row["side"] == NORMAL[account] else -amount
                b[account] += delta
                period_flow[n][account][component] += delta
            if et == "creditor_write_off":
                if event.get("legal_effect") != "accounting_derecognition_no_legal_extinguishment":
                    raise OracleError("write-off must not be treated as legal forgiveness")
                memo_delta = dec(event.get("writeoff_claim_delta"), "writeoff_claim_delta")
                if memo_delta <= 0:
                    raise OracleError("write-off memo delta must be positive")
                b["writeoff_memorandum"] += memo_delta
                period_flow[n]["writeoff_memorandum"]["O"] += memo_delta
            elif et == "impairment_allowance_recognition":
                if event.get("legal_effect") != "valuation_allowance_only":
                    raise OracleError("impairment must be valuation-only")
            elif et == "legal_debt_forgiveness":
                if event.get("legal_effect") != "legally_extinguish_principal":
                    raise OracleError("forgiveness requires legal extinguishment")
                forgiven = dec(event.get("forgiven_principal"), "forgiven_principal")
                if forgiven != D("5"):
                    raise OracleError("forgiveness amount differs from frozen case")
            # Fundamental position relations after every event.
            if b["loan_asset"] + b["writeoff_memorandum"] != b["loan_liability"]:
                raise OracleError(f"{eid}: contractual principal != recognized asset + enforceable write-off memo")
            if b["impairment_allowance"] < 0 or b["impairment_allowance"] > b["loan_asset"]:
                raise OracleError(f"{eid}: allowance outside gross recognized loan bounds")
            if b["interest_receivable"] != b["interest_payable"]:
                raise OracleError(f"{eid}: accrued interest receivable/payable mismatch")
            if b["deposit_asset"] != b["deposit_liability"]:
                raise OracleError(f"{eid}: deposit holder/issuer mirror mismatch")
            snap = metrics(b)
            if checkpoints.get(eid) != snap:
                raise OracleError(f"{eid}: replay checkpoint mismatch")
            replay.append({"after_event_id":eid,"balances":snap})
        expected_close = period["closing_balances"]
        actual_close = metrics(b)
        if actual_close != expected_close:
            raise OracleError(f"P{n} closing snapshot mismatch")
        for key in METRIC_KEYS:
            flows = period_flow[n][key]
            opening_value = D(period_open[n][key])
            closing_value = D(actual_close[key])
            if opening_value + flows["T"] + flows["V"] + flows["O"] != closing_value:
                raise OracleError(f"P{n} T/V/O roll-forward failed for {key}")
        period["closing_balances"] if False else None
    if len(event_ids) != len(corpus["events"]):
        raise OracleError("event outside declared period or not replayed")
    final = metrics(b)
    expected_final = corpus.get("expected_closing", {})
    for key,value in {
        "contractual_principal":"75","recognized_gross_loan_asset":"60",
        "unrecognized_but_legally_enforceable_written_off_claim":"15",
        "impairment_allowance":"5","net_loan_carrying_amount":"55",
        "interest_receivable":"6","interest_payable":"6",
        "deposit_asset":"76","deposit_liability":"76",
    }.items():
        if expected_final.get(key) != value:
            raise OracleError("frozen final expected value changed: "+key)
    if (final["loan_liability"], final["loan_asset"], final["writeoff_memorandum"],
        final["impairment_allowance"], final["net_loan_carrying"]) != ("75","60","15","5","55"):
        raise OracleError("final debt/allowance state mismatch")
    return {"corpus_id":"SFC-GOLD-2A","version":"1.0.0","status":"PASS",
            "event_count":len(event_ids),"period_count":len(periods),
            "final_balances":final,"replay_checkpoints":replay}


def must_reject(mutator, corpus, label):
    changed = copy.deepcopy(corpus)
    mutator(changed)
    try:
        evaluate(changed)
    except (OracleError, KeyError, TypeError, ValueError):
        return
    raise AssertionError("negative control accepted: "+label)


def negative_controls(corpus):
    def duplicate(c): c["events"].append(copy.deepcopy(c["events"][0]))
    def float_amount(c): c["events"][0]["postings"][0]["amount"] = 100.0
    def wrong_holder(c): c["events"][0]["postings"][0]["counterparty_entity_id"] = "bank-1"
    def impairment_principal(c):
        c["events"][3]["postings"][1]["account"] = "loan_asset"
    def writeoff_forgives(c):
        c["events"][5]["postings"].extend([
            {"account":"loan_liability","side":"D","amount":"15","entity_id":"borrower-1","institutional_sector":"H",
             "counterparty_entity_id":"bank-1","counterparty_sector":"CB","issuer_entity_id":"borrower-1","issuer_sector":"H",
             "instrument_id":"LOAN-001","instrument_class":"loan","currency":"LCU","maturity":"2030-12-31","denomination":"NOMINAL","valuation_basis":"NOMINAL"},
            {"account":"writeoff_gain","side":"C","amount":"15","entity_id":"borrower-1","institutional_sector":"H"}])
    def checkpoint(c): c["replay_checkpoints"][2]["balances"]["deposit_asset"]="97"
    def period(c): c["events"][1]["effective_period"]=2
    def forgiveness_one_sided(c): c["events"][6]["postings"][2]["amount"]="4"
    cases=[(duplicate,"duplicate event"),(float_amount,"binary float"),
           (wrong_holder,"wrong holder identity"),(impairment_principal,"impairment changes gross principal"),
           (writeoff_forgives,"write-off silently forgives debt"),(checkpoint,"tampered checkpoint"),
           (period,"wrong effective period"),(forgiveness_one_sided,"one-sided forgiveness")]
    for fn,label in cases: must_reject(fn,corpus,label)
    return len(cases)


def main():
    path = Path(sys.argv[1]) if len(sys.argv)>1 and not sys.argv[1].startswith("--") else DEFAULT_CORPUS
    corpus=json.loads(path.read_text(encoding="utf-8"))
    result=evaluate(corpus)
    controls=negative_controls(corpus)
    result["negative_controls_rejected"]=controls
    if "--json" in sys.argv:
        print(json.dumps(result,sort_keys=True,separators=(",",":")))
    else:
        print("SFC-GOLD-2A independent Decimal oracle: PASS")
        print(f"events={result['event_count']} periods={result['period_count']} negative_controls={controls}")
        for k,v in result["final_balances"].items(): print(f"{k}={v}")
        print("No production modules imported.")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
