"""Durable legal rights, claims, title, encumbrance and dispute register."""
from __future__ import annotations
from durable_event_register import DurableEventRegister, RegisterError, required_text, utc_timestamp


class LegalRightsRegisterError(RegisterError):
    pass


class LegalRightsRegister(DurableEventRegister):
    REGISTER_NAME = "legal_rights"
    read_permission = "legal_rights:read"

    @staticmethod
    def write_permission(event_type):
        if event_type in {"right.created", "right.transferred", "right.encumbered", "right.released", "right.extinguished"}:
            return "legal_rights:write"
        if event_type in {"right.disputed", "right.adjudicated", "right.corrected", "right.evidence_attached"}:
            return "legal_rights:adjudicate"
        return "legal_rights:admin"

    def reduce_event(self, old, event):
        typ, p = event["event_type"], event["payload"]
        state = dict(old or {})
        if typ == "right.created":
            if old is not None:
                raise LegalRightsRegisterError("legal right/claim identity already exists")
            for field in ("holder_id","right_type","scope","jurisdiction","legal_instrument_ref"):
                required_text(p.get(field), field)
            utc_timestamp(p.get("effective_from"), "effective_from")
            if p.get("obligor_id") is not None:
                required_text(p.get("obligor_id"), "obligor_id")
            evidence = p.get("evidence_refs")
            if not isinstance(evidence,list) or not evidence or any(not isinstance(x,str) or not x.strip() for x in evidence):
                raise LegalRightsRegisterError("right creation requires evidence references")
            if p.get("obligor_id") is not None and p["holder_id"] == p["obligor_id"]:
                raise LegalRightsRegisterError("holder and obligor must be distinct identities")
            return {"holder_id":p["holder_id"],"obligor_id":p.get("obligor_id"),
                    "right_type":p["right_type"],"scope":p["scope"],
                    "jurisdiction":p["jurisdiction"],"legal_instrument_ref":p["legal_instrument_ref"],
                    "effective_from":p["effective_from"],"status":"ACTIVE",
                    "evidence_refs":list(dict.fromkeys(evidence)),"encumbrances":[],
                    "dispute_ref":None,"adjudication":None,"correction_event_ids":[]}
        if old is None:
            raise LegalRightsRegisterError("legal right event references unknown claim")
        if typ == "right.evidence_attached":
            ref = required_text(p.get("evidence_ref"), "evidence_ref")
            if ref in state["evidence_refs"]:
                raise LegalRightsRegisterError("evidence reference already attached")
            state["evidence_refs"] = list(state["evidence_refs"])+[ref]
        elif typ == "right.transferred":
            if state["status"] != "ACTIVE":
                raise LegalRightsRegisterError("only active rights can be transferred")
            expected = required_text(p.get("from_holder_id"), "from_holder_id")
            target = required_text(p.get("to_holder_id"), "to_holder_id")
            if state["holder_id"] != expected or target == expected or (state["obligor_id"] is not None and target == state["obligor_id"]):
                raise LegalRightsRegisterError("transferor mismatch or invalid new holder")
            required_text(p.get("transfer_instrument_ref"), "transfer_instrument_ref")
            required_text(p.get("evidence_ref"), "evidence_ref")
            state["holder_id"] = target
        elif typ == "right.encumbered":
            if state["status"] != "ACTIVE":
                raise LegalRightsRegisterError("only active rights can be encumbered")
            encumbrance_id = required_text(p.get("encumbrance_id"), "encumbrance_id")
            if any(x["encumbrance_id"] == encumbrance_id for x in state["encumbrances"]):
                raise LegalRightsRegisterError("encumbrance identity already exists")
            priority = p.get("priority")
            if not isinstance(priority,int) or isinstance(priority,bool) or priority < 1:
                raise LegalRightsRegisterError("encumbrance priority must be a positive integer")
            state["encumbrances"] = list(state["encumbrances"])+[{
                "encumbrance_id":encumbrance_id,"beneficiary_id":required_text(p.get("beneficiary_id"),"beneficiary_id"),
                "scope":required_text(p.get("scope"),"scope"),"priority":priority,
                "instrument_ref":required_text(p.get("instrument_ref"),"instrument_ref"),
                "evidence_ref":required_text(p.get("evidence_ref"),"evidence_ref"),"status":"ACTIVE"}]
        elif typ == "right.released":
            encumbrance_id = required_text(p.get("encumbrance_id"), "encumbrance_id")
            matches = [x for x in state["encumbrances"] if x["encumbrance_id"] == encumbrance_id and x["status"] == "ACTIVE"]
            if len(matches) != 1:
                raise LegalRightsRegisterError("active encumbrance not found")
            for item in state["encumbrances"]:
                if item["encumbrance_id"] == encumbrance_id:
                    item["status"] = "RELEASED"
            required_text(p.get("release_instrument_ref"), "release_instrument_ref")
            required_text(p.get("evidence_ref"), "evidence_ref")
        elif typ == "right.disputed":
            if state["status"] not in {"ACTIVE","ENCUMBERED"}:
                raise LegalRightsRegisterError("right cannot be disputed in current state")
            state["status"] = "DISPUTED"
            state["dispute_ref"] = required_text(p.get("dispute_ref"), "dispute_ref")
            required_text(p.get("forum_ref"), "forum_ref")
            required_text(p.get("evidence_ref"), "evidence_ref")
        elif typ == "right.adjudicated":
            if state["status"] != "DISPUTED":
                raise LegalRightsRegisterError("adjudication requires an open dispute")
            outcome = p.get("outcome")
            if outcome not in {"upheld","rejected","modified"}:
                raise LegalRightsRegisterError("unknown adjudication outcome")
            state["adjudication"] = {"outcome":outcome,"decision_ref":required_text(p.get("decision_ref"),"decision_ref"),
                                     "effective_at":event["effective_at"]}
            state["status"] = "ACTIVE" if outcome in {"upheld","modified"} else "VOID"
        elif typ == "right.extinguished":
            if state["status"] not in {"ACTIVE","VOID","ENCUMBERED"}:
                raise LegalRightsRegisterError("claim cannot be extinguished in current state")
            if any(x["status"] == "ACTIVE" for x in state["encumbrances"]):
                raise LegalRightsRegisterError("active encumbrances must be released before extinguishment")
            required_text(p.get("extinguishment_basis"), "extinguishment_basis")
            required_text(p.get("legal_instrument_ref"), "legal_instrument_ref")
            required_text(p.get("evidence_ref"), "evidence_ref")
            state["status"] = "EXTINGUISHED"
        elif typ == "right.corrected":
            target = required_text(p.get("corrects_event_id"), "corrects_event_id")
            if target not in state.get("_event_ids", []):
                raise LegalRightsRegisterError("correction target is not in this claim history")
            reason = required_text(p.get("reason"), "reason")
            evidence = required_text(p.get("evidence_ref"), "evidence_ref")
            changes = p.get("changes")
            if not isinstance(changes,dict) or not changes or set(changes)-{"scope","jurisdiction","legal_instrument_ref"}:
                raise LegalRightsRegisterError("correction may change only scope, jurisdiction or instrument reference")
            for key,value in changes.items():
                state[key] = required_text(value,key)
            state["correction_event_ids"] = list(state["correction_event_ids"])+[event["event_id"]]
            state["last_correction"] = {"target_event_id":target,"reason":reason,"evidence_ref":evidence}
        else:
            raise LegalRightsRegisterError(f"unsupported legal rights event type: {typ}")
        if state["status"] == "ACTIVE" and state["encumbrances"]:
            state["status"] = "ENCUMBERED"
        elif state["status"] == "ENCUMBERED" and not any(x["status"] == "ACTIVE" for x in state["encumbrances"]):
            state["status"] = "ACTIVE"
        return state
