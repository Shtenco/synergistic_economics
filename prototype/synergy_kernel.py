"""Minimal dependency-free SYNERGY kernel. Research prototype, not production software."""
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from hashlib import sha256
import json

class KernelError(ValueError):
    pass

def money(value):
    try:
        value = Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception as exc:
        raise KernelError("Invalid monetary value") from exc
    if not value.is_finite():
        raise KernelError("Money must be finite")
    return value

@dataclass(frozen=True)
class JournalLine:
    account: str
    debit: Decimal = Decimal("0.00")
    credit: Decimal = Decimal("0.00")
    def __post_init__(self):
        if not self.account or self.debit < 0 or self.credit < 0 or (self.debit and self.credit):
            raise KernelError("Invalid journal line")

@dataclass(frozen=True)
class JournalEntry:
    entry_id: str
    currency: str
    memo: str
    lines: tuple

class DoubleEntryLedger:
    """Balances are debit-positive; every journal entry must balance."""
    def __init__(self, accounts=()):
        self.accounts = set(accounts)
        self.balances = {}
        self.entries = []
        self._ids = set()
    def add_account(self, account):
        if not account: raise KernelError("Account required")
        self.accounts.add(account)
    def post(self, entry):
        if entry.entry_id in self._ids: raise KernelError("Duplicate entry")
        if not entry.currency or len(entry.lines) < 2: raise KernelError("Invalid entry header")
        if sum((x.debit for x in entry.lines), Decimal("0")) != sum((x.credit for x in entry.lines), Decimal("0")):
            raise KernelError("Unbalanced entry")
        unknown = {x.account for x in entry.lines} - self.accounts
        if unknown: raise KernelError(f"Unknown accounts: {sorted(unknown)}")
        for line in entry.lines:
            key = (line.account, entry.currency)
            self.balances[key] = self.balances.get(key, Decimal("0")) + line.debit - line.credit
        self.entries.append(entry)
        self._ids.add(entry.entry_id)
    def balance(self, account, currency="UNIT"):
        if account not in self.accounts: raise KernelError("Unknown account")
        return self.balances.get((account, currency), Decimal("0.00"))
    def assert_balanced(self):
        for currency in {e.currency for e in self.entries}:
            total = sum((v for (a,c),v in self.balances.items() if c == currency), Decimal("0"))
            if total != 0: raise KernelError(f"Ledger imbalance: {currency} {total}")

@dataclass(frozen=True)
class Event:
    event_id: str
    event_type: str
    sequence: int
    payload: dict
    idempotency_key: str
    digest: str

class EventStore:
    """Append-only ordered event log with duplicate/idempotency protection."""
    def __init__(self):
        self.events, self._ids, self._keys = [], set(), set()
    def append(self, event_id, event_type, payload, idempotency_key):
        if not all((event_id,event_type,idempotency_key)): raise KernelError("Event fields required")
        if event_id in self._ids or idempotency_key in self._keys: raise KernelError("Duplicate event")
        raw = json.dumps(payload, sort_keys=True, separators=(",",":"), default=str)
        digest = sha256((event_type+"|"+raw).encode()).hexdigest()
        event = Event(event_id,event_type,len(self.events)+1,dict(payload),idempotency_key,digest)
        self.events.append(event); self._ids.add(event_id); self._keys.add(idempotency_key)
        return event
    def replay(self):
        return tuple(sorted(self.events,key=lambda x:x.sequence))

@dataclass
class Firm:
    firm_id: str
    labour: Decimal
    productivity: Decimal
    materials: Decimal
    material_per_unit: Decimal
    energy: Decimal
    energy_per_unit: Decimal
    capacity: Decimal
    inventory: Decimal = Decimal("0")
    def produce(self, demand):
        values=(self.labour,self.productivity,self.materials,self.material_per_unit,self.energy,self.energy_per_unit,self.capacity,self.inventory)
        if any(x < 0 for x in values) or self.material_per_unit <= 0 or self.energy_per_unit <= 0:
            raise KernelError("Invalid production inputs")
        demand=Decimal(str(demand))
        if demand < 0: raise KernelError("Negative demand")
        output=min(demand,self.capacity,self.labour*self.productivity,self.materials/self.material_per_unit,self.energy/self.energy_per_unit)
        self.materials -= output*self.material_per_unit
        self.energy -= output*self.energy_per_unit
        self.inventory += output
        return output
    def ship(self, quantity):
        quantity=Decimal(str(quantity))
        if quantity < 0 or quantity > self.inventory: raise KernelError("Insufficient inventory")
        self.inventory -= quantity
        return quantity

def allocate_pool(pool, weights):
    """Proportional allocation with deterministic cent rounding and exact budget balance."""
    pool=money(pool)
    if pool < 0: raise KernelError("Negative pool")
    if not weights:
        if pool: raise KernelError("No recipients")
        return {}
    weights={k:Decimal(str(v)) for k,v in weights.items()}
    if any(not k or v < 0 or not v.is_finite() for k,v in weights.items()): raise KernelError("Invalid weights")
    denominator=sum(weights.values(),Decimal("0"))
    if denominator <= 0:
        if pool: raise KernelError("Zero total weight")
        return {k:Decimal("0.00") for k in sorted(weights)}
    keys=sorted(weights); result={}; allocated=Decimal("0.00")
    for key in keys[:-1]:
        share=(pool*weights[key]/denominator).quantize(Decimal("0.01"),rounding=ROUND_HALF_UP)
        result[key]=share; allocated+=share
    result[keys[-1]]=pool-allocated
    if sum(result.values()) != pool or any(x < 0 for x in result.values()): raise KernelError("Budget balance failure")
    return result

@dataclass
class SynergyKernel:
    ledger: DoubleEntryLedger = field(default_factory=lambda: DoubleEntryLedger({"cash:cell_a","cash:cell_b"}))
    events: EventStore = field(default_factory=EventStore)
    sequence: int = 0
    def transfer_cash(self, sender, recipient, amount, currency="UNIT", idempotency_key=None):
        amount=money(amount)
        if amount <= 0: raise KernelError("Transfer must be positive")
        debit,credit=f"cash:{recipient}",f"cash:{sender}"
        if debit not in self.ledger.accounts or credit not in self.ledger.accounts: raise KernelError("Cash account missing")
        self.sequence+=1
        jid=f"J{self.sequence:08d}"
        self.ledger.post(JournalEntry(jid,currency,"Settled inter-cell transfer",(JournalLine(debit,debit=amount),JournalLine(credit,credit=amount))))
        self.events.append(f"E{self.sequence:08d}","cash_transfer_settled",{"sender":sender,"recipient":recipient,"amount":str(amount),"currency":currency},idempotency_key or jid)
        self.ledger.assert_balanced()

def demo():
    k=SynergyKernel()
    k.ledger.add_account("equity:cell_a"); k.ledger.add_account("equity:cell_b")
    k.ledger.post(JournalEntry("OPEN-A","UNIT","Opening A",(JournalLine("cash:cell_a",debit=money(100)),JournalLine("equity:cell_a",credit=money(100)))))
    k.ledger.post(JournalEntry("OPEN-B","UNIT","Opening B",(JournalLine("cash:cell_b",debit=money(20)),JournalLine("equity:cell_b",credit=money(20)))))
    k.transfer_cash("cell_a","cell_b",15,idempotency_key="demo-transfer")
    firm=Firm("firm-1",Decimal(10),Decimal(2),Decimal(30),Decimal(1),Decimal(20),Decimal(1),Decimal(25))
    output=firm.produce(100)
    shares=allocate_pool(12,{"member-a":2,"member-b":1,"member-c":1})
    return {"cash_a":str(k.ledger.balance("cash:cell_a")),"cash_b":str(k.ledger.balance("cash:cell_b")),"output":str(output),"inventory":str(firm.inventory),"shares":{k:str(v) for k,v in shares.items()},"events":len(k.events.events)}

if __name__ == "__main__":
    print(json.dumps(demo(),indent=2,sort_keys=True))
