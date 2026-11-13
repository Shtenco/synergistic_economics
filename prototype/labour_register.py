"""Durable rights-aware labour, capability, time and consent event register."""
from __future__ import annotations
from decimal import Decimal
from durable_event_register import DurableEventRegister, RegisterError, finite_decimal, required_text


class LabourRegisterError(RegisterError):
    pass


class LabourRegister(DurableEventRegister):
    REGISTER_NAME = "labour"
    read_permission = "labour:read"

    @staticmethod
    def write_permission(event_type):
        return "labour:admin" if event_type.startswith("capability.") else "labour:write"

    def reduce_event(self, old, event):
        typ, p = event["event_type"], event["payload"]
        state = dict(old or {})
        if typ == "engagement.offered":
            if old is not None:
                raise LabourRegisterError("engagement can only be offered once")
            for field in ("person_ref", "activity_id", "period", "classification", "consent_basis"):
                required_text(p.get(field), field)
            if p["classification"] not in {"paid", "unpaid_care", "training", "civic", "other"}:
                raise LabourRegisterError("unknown labour classification")
            planned = finite_decimal(p.get("planned_hours"), "planned_hours", minimum=Decimal("0"))
            if planned <= 0:
                raise LabourRegisterError("planned_hours must be positive")
            evidence_refs = p.get("evidence_refs", [])
            if not isinstance(evidence_refs, list) or any(not isinstance(x,str) or not x.strip() for x in evidence_refs):
                raise LabourRegisterError("evidence_refs must be a list of non-empty references")
            return {"person_ref":p["person_ref"],"activity_id":p["activity_id"],
                    "period":p["period"],"classification":p["classification"],
                    "consent_basis":p["consent_basis"],"planned_hours":str(planned),
                    "accepted_hours":"0","scheduled_hours":"0","delivered_hours":"0",
                    "status":"OFFERED","evidence_refs":list(evidence_refs),
                    "correction_event_ids":[]}
        if typ.startswith("engagement.") or typ == "hours.corrected":
            if old is None:
                raise LabourRegisterError("engagement transition references unknown engagement")
            transitions = {
                "engagement.accepted":{"OFFERED"}, "engagement.declined":{"OFFERED"},
                "engagement.withdrawn":{"OFFERED","ACCEPTED","SCHEDULED"},
                "engagement.scheduled":{"ACCEPTED"}, "engagement.started":{"SCHEDULED"},
                "engagement.delivered":{"STARTED"}, "engagement.stopped":{"STARTED"},
                "engagement.verified":{"DELIVERED","STOPPED","DISPUTED"},
                "engagement.disputed":{"DELIVERED","VERIFIED"},
                "engagement.cancelled":{"OFFERED","ACCEPTED","SCHEDULED","STARTED"},
                "engagement.settled":{"VERIFIED"},
            }
            status = state["status"]
            if typ == "hours.corrected":
                if status not in {"DELIVERED","STOPPED","VERIFIED","DISPUTED","SETTLED"}:
                    raise LabourRegisterError("hours correction requires a delivered service")
                target = required_text(p.get("corrects_event_id"), "corrects_event_id")
                reason = required_text(p.get("reason"), "reason")
                delta = finite_decimal(p.get("delta_hours"), "delta_hours")
                if target != state.get("delivery_event_id"):
                    raise LabourRegisterError("hours correction must reference the immutable delivery event")
                corrected = Decimal(state["delivered_hours"]) + delta
                if corrected < 0 or corrected > Decimal(state["scheduled_hours"]):
                    raise LabourRegisterError("corrected delivered hours exceed scheduled bounds")
                state["delivered_hours"] = str(corrected)
                state["correction_event_ids"] = list(state["correction_event_ids"]) + [event["event_id"]]
                state["last_correction_reason"] = reason
                return state
            allowed = transitions.get(typ)
            if allowed is None or status not in allowed:
                raise LabourRegisterError(f"illegal labour transition {typ} from {status}")
            if typ == "engagement.accepted":
                required_text(p.get("consent_ref"), "consent_ref")
                accepted = finite_decimal(p.get("accepted_hours", state["planned_hours"]), "accepted_hours", minimum=Decimal("0"))
                if accepted <= 0 or accepted > Decimal(state["planned_hours"]):
                    raise LabourRegisterError("accepted hours exceed offered hours")
                state["accepted_hours"] = str(accepted)
                state["status"] = "ACCEPTED"
            elif typ == "engagement.declined":
                state["status"] = "DECLINED"
                state["decision_reason"] = required_text(p.get("reason"), "reason")
            elif typ == "engagement.withdrawn":
                state["status"] = "WITHDRAWN"
                state["withdrawal_reason"] = required_text(p.get("reason"), "reason")
            elif typ == "engagement.scheduled":
                hours = finite_decimal(p.get("scheduled_hours"), "scheduled_hours", minimum=Decimal("0"))
                if hours <= 0 or hours > Decimal(state["accepted_hours"]):
                    raise LabourRegisterError("scheduled hours exceed accepted consent")
                state["scheduled_hours"] = str(hours)
                state["status"] = "SCHEDULED"
            elif typ == "engagement.started":
                state["status"] = "STARTED"
            elif typ in {"engagement.delivered","engagement.stopped"}:
                hours = finite_decimal(p.get("delivered_hours"), "delivered_hours", minimum=Decimal("0"))
                if hours > Decimal(state["scheduled_hours"]):
                    raise LabourRegisterError("delivered hours exceed scheduled hours")
                if typ == "engagement.delivered" and hours <= 0:
                    raise LabourRegisterError("delivered hours must be positive")
                state["delivered_hours"] = str(hours)
                state["status"] = "DELIVERED" if typ == "engagement.delivered" else "STOPPED"
                state["delivery_event_id"] = event["event_id"]
                state["delivery_evidence_ref"] = required_text(p.get("evidence_ref"), "evidence_ref")
                if typ == "engagement.stopped":
                    state["stop_reason"] = required_text(p.get("reason"), "reason")
            elif typ == "engagement.verified":
                state["status"] = "VERIFIED"
                state["verification_ref"] = required_text(p.get("verification_ref"), "verification_ref")
            elif typ == "engagement.disputed":
                state["status"] = "DISPUTED"
                state["dispute_ref"] = required_text(p.get("dispute_ref"), "dispute_ref")
            elif typ == "engagement.cancelled":
                state["status"] = "CANCELLED"
                state["cancellation_reason"] = required_text(p.get("reason"), "reason")
            elif typ == "engagement.settled":
                state["status"] = "SETTLED"
                state["settlement_ref"] = required_text(p.get("settlement_ref"), "settlement_ref")
            return state
        if typ == "capability.assessed":
            if old is not None and state.get("person_ref") != p.get("person_ref"):
                raise LabourRegisterError("capability aggregate person identity changed")
            person = required_text(p.get("person_ref"), "person_ref")
            skill = required_text(p.get("skill_id"), "skill_id")
            if event["aggregate_id"] != f"capability:{person}:{skill}":
                raise LabourRegisterError("capability aggregate ID must bind person and skill")
            score = finite_decimal(p.get("proficiency"), "proficiency", minimum=Decimal("0"))
            scale_max = finite_decimal(p.get("scale_max"), "scale_max", minimum=Decimal("0"))
            if scale_max <= 0 or score > scale_max:
                raise LabourRegisterError("capability score is outside declared scale")
            evidence = required_text(p.get("evidence_ref"), "evidence_ref")
            return {"person_ref":person,"skill_id":skill,"proficiency":str(score),
                    "scale_max":str(scale_max),"evidence_ref":evidence,
                    "assessed_at":event["effective_at"],
                    "assessment_history":list(state.get("assessment_history",[]))+[event["event_id"]]}
        if typ == "time.allocation.recorded":
            if old is not None and (state.get("person_ref"),state.get("period")) != (p.get("person_ref"),p.get("period")):
                raise LabourRegisterError("time allocation identity changed")
            person = required_text(p.get("person_ref"), "person_ref")
            period = required_text(p.get("period"), "period")
            if event["aggregate_id"] != f"time:{person}:{period}":
                raise LabourRegisterError("time aggregate ID must bind person and period")
            period_hours = finite_decimal(p.get("period_hours"), "period_hours", minimum=Decimal("0"))
            if period_hours <= 0:
                raise LabourRegisterError("period_hours must be positive")
            intervals = p.get("intervals")
            if not isinstance(intervals,list) or not intervals:
                raise LabourRegisterError("time allocation requires interval records")
            normalized, total = [], Decimal("0")
            for item in intervals:
                if not isinstance(item,dict):
                    raise LabourRegisterError("time interval must be an object")
                category = required_text(item.get("category"),"category")
                if category not in {"rest","personal","paid","unpaid_care","training","civic","leisure","unallocated"}:
                    raise LabourRegisterError("unknown time-allocation category")
                start = finite_decimal(item.get("start_hour"),"start_hour",minimum=Decimal("0"))
                end = finite_decimal(item.get("end_hour"),"end_hour",minimum=Decimal("0"))
                if end <= start or end > period_hours:
                    raise LabourRegisterError("time interval outside period bounds")
                normalized.append((start,end,category))
                total += end-start
            ordered = sorted(normalized)
            if any(ordered[i][0] < ordered[i-1][1] for i in range(1,len(ordered))):
                raise LabourRegisterError("overlapping time intervals are not permitted")
            if total > period_hours:
                raise LabourRegisterError("time allocations exceed period duration")
            return {"person_ref":person,"period":period,"period_hours":str(period_hours),
                    "allocated_hours":str(total),
                    "intervals":[{"start_hour":str(a),"end_hour":str(b),"category":c} for a,b,c in ordered]}
        raise LabourRegisterError(f"unsupported labour event type: {typ}")
