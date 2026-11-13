"""Typed multi-period stock-flow reconciliation kernel for cross-register events.

Every position is reconciled independently in its native measure/unit and, where
applicable, currency and valuation basis. It intentionally forbids cross-unit sums.
"""
from __future__ import annotations
from dataclasses import dataclass
from decimal import Decimal
from collections import defaultdict


class StockFlowError(ValueError): pass


def _text(value, field):
    if not isinstance(value,str) or not value or value != value.strip():
        raise StockFlowError(f"{field} must be trimmed non-empty text")
    return value


def _decimal(value, field):
    if isinstance(value,bool): raise StockFlowError(f"{field} must be a finite Decimal")
    try: number=Decimal(str(value))
    except Exception as exc: raise StockFlowError(f"{field} must be a finite Decimal") from exc
    if not number.is_finite(): raise StockFlowError(f"{field} must be finite")
    return number


@dataclass(frozen=True, order=True)
class PositionIdentity:
    register_id: str
    position_id: str
    measure: str
    unit: str
    currency: str
    valuation_basis: str
    holder_id: str
    issuer_id: str
    instrument_id: str

    def validate(self):
        for field in self.__dataclass_fields__:
            _text(getattr(self,field),field)
        if self.holder_id == self.issuer_id:
            raise StockFlowError("holder and issuer must be distinct identities")


@dataclass(frozen=True)
class OpeningPosition:
    identity: PositionIdentity
    period_index: int
    amount: Decimal
    evidence_ref: str


@dataclass(frozen=True)
class Movement:
    event_id: str
    common_event_id: str
    identity: PositionIdentity
    period_index: int
    movement_class: str
    amount: Decimal
    evidence_ref: str
    correction_of: str | None = None
    mirror_group_id: str | None = None
    mirror_side: str | None = None
    mirror_policy: str | None = None


@dataclass(frozen=True)
class ClosingPosition:
    identity: PositionIdentity
    period_index: int
    amount: Decimal
    evidence_ref: str


@dataclass(frozen=True)
class PeriodResult:
    identity: PositionIdentity
    period_index: int
    opening: Decimal
    transactions: Decimal
    revaluations: Decimal
    other_volume_changes: Decimal
    closing: Decimal
    event_ids: tuple[str,...]


@dataclass(frozen=True)
class ReconciliationResult:
    periods: tuple[PeriodResult,...]
    event_count: int
    mirror_group_count: int


def reconcile_periods(openings, movements, closings):
    if not all(isinstance(x,tuple) for x in (openings,movements,closings)):
        raise StockFlowError("openings, movements and closings must be immutable tuples")
    opening_map, closing_map = {}, {}
    for row in openings:
        if not isinstance(row,OpeningPosition): raise StockFlowError("OpeningPosition required")
        row.identity.validate()
        if not isinstance(row.period_index,int) or isinstance(row.period_index,bool) or row.period_index<1:
            raise StockFlowError("opening period_index must be a positive integer")
        _text(row.evidence_ref,"opening evidence_ref")
        key=(row.identity,row.period_index)
        if key in opening_map: raise StockFlowError("duplicate opening position")
        opening_map[key]=_decimal(row.amount,"opening amount")
    for row in closings:
        if not isinstance(row,ClosingPosition): raise StockFlowError("ClosingPosition required")
        row.identity.validate()
        if not isinstance(row.period_index,int) or isinstance(row.period_index,bool) or row.period_index<1:
            raise StockFlowError("closing period_index must be a positive integer")
        _text(row.evidence_ref,"closing evidence_ref")
        key=(row.identity,row.period_index)
        if key in closing_map: raise StockFlowError("duplicate closing position")
        closing_map[key]=_decimal(row.amount,"closing amount")
    if not opening_map or set(opening_map)!=set(closing_map):
        raise StockFlowError("each opening position requires exactly one closing for the same identity and period")

    by_position=defaultdict(list); event_ids=set(); mirrors=defaultdict(lambda:defaultdict(Decimal))
    movement_by_id={}
    for row in movements:
        if not isinstance(row,Movement): raise StockFlowError("Movement required")
        row.identity.validate()
        _text(row.event_id,"event_id"); _text(row.common_event_id,"common_event_id"); _text(row.evidence_ref,"evidence_ref")
        if row.event_id in event_ids: raise StockFlowError("duplicate movement event ID")
        event_ids.add(row.event_id); movement_by_id[row.event_id]=row
        if not isinstance(row.period_index,int) or isinstance(row.period_index,bool) or row.period_index<1:
            raise StockFlowError("movement period_index must be a positive integer")
        if row.movement_class not in {"T","V","O"}: raise StockFlowError("movement class must be T, V or O")
        amount=_decimal(row.amount,"movement amount")
        key=(row.identity,row.period_index)
        if key not in opening_map: raise StockFlowError("movement has no matching opening/closing period")
        by_position[key].append(row)
        if row.mirror_group_id is not None or row.mirror_side is not None or row.mirror_policy is not None:
            _text(row.mirror_group_id,"mirror_group_id"); _text(row.mirror_side,"mirror_side")
            if row.mirror_policy not in {"equal","opposite"}: raise StockFlowError("mirror_policy must be equal or opposite")
            mkey=(row.mirror_group_id,row.period_index,row.identity.register_id,row.identity.instrument_id,
                  row.movement_class,row.identity.measure,row.identity.unit,row.identity.currency,
                  row.identity.valuation_basis,row.mirror_policy)
            mirrors[mkey][row.mirror_side] += amount
        if row.correction_of is not None:
            _text(row.correction_of,"correction_of")
            if row.correction_of not in movement_by_id:
                raise StockFlowError("correction must reference an earlier immutable movement")
            original=movement_by_id[row.correction_of]
            if original.identity != row.identity or original.period_index > row.period_index:
                raise StockFlowError("correction target identity or period is incompatible")

    results=[]
    identities=sorted({key[0] for key in opening_map})
    for identity in identities:
        periods=sorted(period for (ident,period) in opening_map if ident==identity)
        if periods != list(range(periods[0],periods[-1]+1)):
            raise StockFlowError("period sequence contains a gap for a position")
        previous_closing=None
        for period in periods:
            key=(identity,period); opening=opening_map[key]; closing=closing_map[key]
            if previous_closing is not None and opening != previous_closing:
                raise StockFlowError("opening(t+1) does not equal closing(t)")
            grouped={"T":Decimal(0),"V":Decimal(0),"O":Decimal(0)}
            rows=by_position.get(key,[])
            for row in rows: grouped[row.movement_class] += _decimal(row.amount,"movement amount")
            expected=opening+grouped["T"]+grouped["V"]+grouped["O"]
            if expected != closing:
                raise StockFlowError(f"stock-flow identity does not close for {identity.position_id} period {period}: {expected} != {closing}")
            results.append(PeriodResult(identity,period,opening,grouped["T"],grouped["V"],grouped["O"],closing,
                                        tuple(sorted(row.event_id for row in rows))))
            previous_closing=closing
    for key,sides in mirrors.items():
        if len(sides)!=2: raise StockFlowError("mirror group must contain exactly two distinct sides")
        values=list(sides.values())
        if key[-1]=="equal" and values[0] != values[1]:
            raise StockFlowError("holder/issuer mirrored movements do not agree")
        if key[-1]=="opposite" and values[0] != -values[1]:
            raise StockFlowError("sender/receiver mirrored movements do not offset")
    return ReconciliationResult(tuple(results),len(movements),len(mirrors))


def movements_from_event_groups(groups):
    """Extract movements from globally committed six-register coordinator groups.

    Every participant must declare stock_flow_movements or an explicit
    no_stock_flow_effect reason. Silent omission cannot masquerade as a balanced
    period or as a register that has no economic effect.
    """
    if not isinstance(groups,tuple):
        raise StockFlowError("committed event groups must be supplied as an immutable tuple")
    required_registers={"physical","capital","labour","product","legal_rights","financial"}
    seen_groups=set(); movements=[]
    for group in groups:
        if not isinstance(group,dict) or group.get("schema_version") != 1:
            raise StockFlowError("unsupported canonical event-group schema")
        common_id=_text(group.get("common_event_id"),"common_event_id")
        if group.get("transaction_id") != common_id or common_id in seen_groups:
            raise StockFlowError("event-group transaction/common identity is invalid or duplicated")
        seen_groups.add(common_id)
        events=group.get("events")
        if not isinstance(events,(tuple,list)) or len(events)!=6:
            raise StockFlowError("event group must contain exactly six participant events")
        names=set()
        for event in events:
            if not isinstance(event,dict): raise StockFlowError("participant event must be an object")
            register=_text(event.get("register_id"),"register_id")
            if register not in required_registers or register in names:
                raise StockFlowError("event group has an unknown or duplicate register participant")
            names.add(register)
            if event.get("common_event_id") != common_id:
                raise StockFlowError("participant event is not bound to its common event group")
            _text(event.get("native_event_id"),"native_event_id")
            revision=event.get("aggregate_version")
            if not isinstance(revision,int) or isinstance(revision,bool) or revision<1:
                raise StockFlowError("participant aggregate_version must be positive")
            payload=event.get("payload")
            if not isinstance(payload,dict): raise StockFlowError("participant domain payload must be an object")
            specs=payload.get("stock_flow_movements")
            if specs is None:
                _text(payload.get("no_stock_flow_effect"),"no_stock_flow_effect")
                continue
            if not isinstance(specs,list) or not specs:
                raise StockFlowError("stock_flow_movements must be a non-empty list when present")
            if "no_stock_flow_effect" in payload:
                raise StockFlowError("event cannot declare both movements and no stock-flow effect")
            for spec in specs:
                if not isinstance(spec,dict): raise StockFlowError("stock-flow movement specification must be an object")
                ident=spec.get("identity")
                if not isinstance(ident,dict): raise StockFlowError("movement identity must be an object")
                try: identity=PositionIdentity(**ident)
                except TypeError as exc: raise StockFlowError("movement identity fields are incomplete or unknown") from exc
                if identity.register_id != register:
                    raise StockFlowError("movement register differs from its event-group participant")
                movements.append(Movement(
                    event_id=_text(spec.get("movement_id"),"movement_id"),
                    common_event_id=common_id,identity=identity,
                    period_index=spec.get("period_index"),
                    movement_class=spec.get("movement_class"),
                    amount=_decimal(spec.get("amount"),"movement amount"),
                    evidence_ref=_text(spec.get("evidence_ref"),"evidence_ref"),
                    correction_of=spec.get("correction_of"),
                    mirror_group_id=spec.get("mirror_group_id"),
                    mirror_side=spec.get("mirror_side"),
                    mirror_policy=spec.get("mirror_policy")))
        if names != required_registers:
            raise StockFlowError("event group omits one or more economic registers")
    return tuple(movements)
