"""Deterministic seven-cell SYNERGY economy research prototype (not calibrated)."""
from dataclasses import dataclass
from decimal import Decimal as D, ROUND_HALF_UP
from hashlib import sha256
import argparse, json

ZERO=D("0"); CENT=D("0.01"); QTY=D("0.00000001")
def dec(x): return D(str(x))
def money(x): return dec(x).quantize(CENT,rounding=ROUND_HALF_UP)
class EconomyError(ValueError): pass

@dataclass(frozen=True)
class Line:
    account:str
    debit:D=ZERO
    credit:D=ZERO
@dataclass(frozen=True)
class Entry:
    entry_id:str
    memo:str
    lines:tuple
class Ledger:
    def __init__(self): self.entries=[]; self.ids=set()
    def post(self,e):
        if e.entry_id in self.ids: raise EconomyError("duplicate journal id")
        if len(e.lines)<2 or any(x.debit<0 or x.credit<0 or (x.debit and x.credit) for x in e.lines): raise EconomyError("invalid journal line")
        if sum((x.debit for x in e.lines),ZERO)!=sum((x.credit for x in e.lines),ZERO): raise EconomyError("unbalanced journal")
        self.entries.append(e); self.ids.add(e.entry_id)
    def assert_balanced(self):
        for e in self.entries:
            if sum((x.debit for x in e.lines),ZERO)!=sum((x.credit for x in e.lines),ZERO): raise EconomyError(e.entry_id)

@dataclass
class CellConfig:
    cell_id:str; sector:str; productivity:D; labour:D; capacity:D
    energy_per_unit:D; material_per_unit:D; unit_price:D; initial_cash:D
    initial_material:D; initial_energy:D; initial_inventory:D; credit_limit:D
    reserve_target:D; investment_cost:D; investment_gain:D; external_demand:D
    default_threshold:D=D("0.25")
@dataclass
class Cell:
    cfg:CellConfig; cash:D; material:D; energy:D; inventory:D
    capital:D=D("1"); receivables:D=ZERO; payables:D=ZERO
    output:D=ZERO; cum_output:D=ZERO; wages:D=ZERO; investment:D=ZERO
    external_sales:D=ZERO; internal_sales:D=ZERO; arrears:int=0
    insolvent:bool=False; defaults:D=ZERO
@dataclass
class Period:
    period:int; output:D; non_energy_output:D; energy_output:D
    final_sales:D; internal_sales:D; wages:D; investment:D
    material_imports:D; value_added_proxy:D; resource_stock:D
    cell_cash:D; household_cash:D; supplier_cash:D; system_cash:D
    receivables:D; payables:D; insolvent_cells:int; cash_gini:D; event_hash:str

class SevenCellEconomy:
    def __init__(self,configs=None,initial_resource=D("1200"),regeneration=D("75"),
                 extraction_cap=D("100"),resource_per_unit=D("0.35"),
                 wage=D("1"),material_price=D("0.6"),initial_household_cash=D("20000"),
                 credit_interest=D("0.01"),credit_utilization=D("0.8"),
                 reserve_share=D("0.1"),distribution_share=D("0.1"),investment_share=D("0.2"),maintenance_rate=D("0.015")):
        configs=configs or self.default_configs()
        if len(configs)!=7 or len({c.cell_id for c in configs})!=7: raise EconomyError("exactly seven unique cells required")
        for c in configs:
            if min(c.productivity,c.labour,c.capacity,c.energy_per_unit,c.material_per_unit,c.unit_price,c.initial_cash,c.initial_material,c.initial_energy,c.initial_inventory,c.credit_limit,c.reserve_target,c.investment_cost,c.investment_gain,c.external_demand)<0: raise EconomyError("negative cell parameter")
            if min(c.unit_price,c.energy_per_unit,c.material_per_unit)<=0: raise EconomyError("unit price and input coefficients must be positive")
        self.cells={c.cell_id:Cell(c,c.initial_cash,c.initial_material,c.initial_energy,c.initial_inventory) for c in configs}
        self.resource=dec(initial_resource); self.regeneration=dec(regeneration); self.extraction_cap=dec(extraction_cap); self.resource_per_unit=dec(resource_per_unit)
        self.wage=dec(wage); self.material_price=dec(material_price); self.household_cash=dec(initial_household_cash); self.supplier_cash=ZERO
        self.credit_interest=dec(credit_interest); self.credit_utilization=dec(credit_utilization); self.reserve_share=dec(reserve_share); self.distribution_share=dec(distribution_share); self.investment_share=dec(investment_share); self.maintenance_rate=dec(maintenance_rate)
        self.initial_system_cash=sum((c.cash for c in self.cells.values()),ZERO)+self.household_cash
        self.ledger=Ledger(); self.events=[]; self.keys=set(); self.positions={}; self.results=[]
        self._opening()
    @staticmethod
    def default_configs():
        # sector, productivity, labour, capacity, energy/unit, material/unit, price, cash, material, energy, inventory, credit, reserve, capex, capex_gain, final demand
        rows=[
          ("cell-1","food","1.20","18","24",".55",".40","4.2","90","80","45","8","35","12","1.4",".12","22"),
          ("cell-2","materials","1.05","16","22",".70",".65","5.0","85","95","55","10","32","14","1.7",".12","18"),
          ("cell-3","energy","1.35","70","80",".01",".25","3.8","150","110","90","0","55","30","1.2",".12","0"),
          ("cell-4","machinery",".82","12","16",".80",".90","8.5","120","110","60","4","55","20","2.5",".12","12"),
          ("cell-5","logistics","1.10","15","21",".45",".30","4.8","95","65","50","5","38","14","1.5",".12","18"),
          ("cell-6","software","1.35","10","18",".20",".10","7.2","110","35","30","2","45","18","2.0",".12","16"),
          ("cell-7","care",".90","20","25",".30",".20","3.5","80","45","35","3","30","10","1.0",".12","24")]
        out=[]
        for r in rows:
            cid,sector,*v=r; p,l,cap,ep,mp,price,cash,mat,energy,inv,credit,res,cost,gain,ext=map(dec,v)
            out.append(CellConfig(cid,sector,p,l,cap,ep,mp,price,cash,mat,energy,inv,credit,res,cost,gain,ext))
        return out
    def _post(self,e): self.ledger.post(e)
    def _opening(self):
        if self.household_cash:
            self._post(Entry("opening:households","household endowment",(Line("cash:households",debit=money(self.household_cash)),Line("equity:households",credit=money(self.household_cash)))))
        for c in self.cells.values():
            if c.cash: self._post(Entry("opening:"+c.cfg.cell_id,"cell endowment",(Line("cash:"+c.cfg.cell_id,debit=money(c.cash)),Line("equity:initial",credit=money(c.cash)))))
    def _event(self,kind,payload,key):
        if key in self.keys: raise EconomyError("duplicate event key")
        raw=json.dumps(payload,sort_keys=True,separators=(",",":"),default=str)
        digest=sha256((kind+"|"+raw).encode()).hexdigest()
        self.events.append({"sequence":len(self.events)+1,"type":kind,"payload":payload,"key":key,"digest":digest}); self.keys.add(key)
    def _trade(self,seller,buyer,qty,t):
        qty=min(dec(qty),seller.inventory)
        if qty<=0:return ZERO
        value=money(qty*seller.cfg.unit_price)
        seller_room=seller.cfg.credit_limit*self.credit_utilization-seller.receivables
        buyer_room=buyer.cfg.credit_limit*self.credit_utilization-buyer.payables
        room=max(ZERO,min(seller_room,buyer_room)); cash=min(buyer.cash,value); credit=value-cash
        if credit>room:
            qty=max(ZERO,min(qty,(buyer.cash+room)/seller.cfg.unit_price)).quantize(QTY,rounding=ROUND_HALF_UP)
            value=money(qty*seller.cfg.unit_price); cash=min(buyer.cash,value); credit=value-cash
        if qty<=0 or value<=0 or credit>room:return ZERO
        seller.inventory=max(ZERO,seller.inventory-qty)
        if seller.cfg.sector=="energy": buyer.energy+=qty
        else: buyer.material+=qty
        buyer.cash-=cash; seller.cash+=cash
        if cash:self._post(Entry(f"p{t}:{seller.cfg.cell_id}:{buyer.cfg.cell_id}:cash","internal cash settlement",(Line("cash:"+seller.cfg.cell_id,debit=cash),Line("cash:"+buyer.cfg.cell_id,credit=cash))))
        if credit:
            seller.receivables+=credit; buyer.payables+=credit
            pair=(buyer.cfg.cell_id,seller.cfg.cell_id); self.positions[pair]=self.positions.get(pair,ZERO)+credit
            self._post(Entry(f"p{t}:{seller.cfg.cell_id}:{buyer.cfg.cell_id}:credit","trade credit",(Line("receivable:"+seller.cfg.cell_id,debit=credit),Line("payable:"+buyer.cfg.cell_id,credit=credit))))
        seller.internal_sales+=value
        self._event("internal.trade",{"seller":seller.cfg.cell_id,"buyer":buyer.cfg.cell_id,"qty":str(qty),"value":str(value),"cash":str(cash),"credit":str(credit)},f"trade:{t}:{seller.cfg.cell_id}:{buyer.cfg.cell_id}")
        return qty
    def _repay(self,t):
        for (debtor_id,creditor_id),due in sorted(list(self.positions.items())):
            debtor=self.cells[debtor_id]; creditor=self.cells[creditor_id]
            paid=min(due,debtor.cash)
            if paid<=0:continue
            debtor.cash-=paid; creditor.cash+=paid; debtor.payables-=paid; creditor.receivables-=paid
            left=due-paid
            if left:self.positions[(debtor_id,creditor_id)]=left
            else:self.positions.pop((debtor_id,creditor_id),None)
            self._post(Entry(f"p{t}:{debtor_id}:{creditor_id}:repay","bilateral repayment",(Line("cash:"+creditor_id,debit=paid),Line("cash:"+debtor_id,credit=paid),Line("payable:"+debtor_id,debit=paid),Line("receivable:"+creditor_id,credit=paid))))
            self._event("credit.repayment",{"debtor":debtor_id,"creditor":creditor_id,"amount":str(paid)},f"repay:{t}:{debtor_id}:{creditor_id}")
    def _interest(self,t):
        for debtor in self.cells.values():
            if debtor.payables<=0 or debtor.insolvent:continue
            interest=money(debtor.payables*self.credit_interest)
            pairs=[(p,v) for p,v in sorted(self.positions.items()) if p[0]==debtor.cfg.cell_id and v>0]
            total=sum((v for _,v in pairs),ZERO); left=interest
            for i,(pair,due) in enumerate(pairs):
                share=left if i==len(pairs)-1 else min(left,money(interest*due/total))
                if share<=0:continue
                left-=share; creditor=self.cells[pair[1]]
                debtor.payables+=share; creditor.receivables+=share; self.positions[pair]+=share
                self._post(Entry(f"p{t}:{pair[0]}:{pair[1]}:interest","credit interest accrual",(Line("interest_expense:"+pair[0],debit=share),Line("payable:"+pair[0],credit=share),Line("receivable:"+pair[1],debit=share),Line("interest_income:"+pair[1],credit=share))))
    def _assess_defaults(self,t):
        for c in self.cells.values():
            if not c.insolvent and c.arrears>=2 and c.payables/max(D("1"),c.cfg.credit_limit)>c.cfg.default_threshold:
                c.insolvent=True; c.defaults+=c.payables
                self._event("cell.insolvency",{"cell":c.cfg.cell_id,"payables":str(c.payables)},f"default:{t}:{c.cfg.cell_id}")
    @staticmethod
    def _gini(values):
        v=sorted(max(ZERO,x) for x in values); total=sum(v,ZERO)
        if not v or total==0:return ZERO
        n=D(len(v)); return (D(2)*sum((D(i+1)*x for i,x in enumerate(v)),ZERO)/(n*total)-(n+1)/n).quantize(D("0.0001"))
    def step(self,t,shock=None):
        shock=shock or {}; active=[c for c in self.cells.values() if not c.insolvent]
        self.resource=min(self.resource+D("2400"),self.resource+self.regeneration)
        ext_mult=dec(shock.get("resource_extraction_multiplier",1))
        if ext_mult<0:raise EconomyError("negative extraction shock")
        extraction=min(self.resource,self.extraction_cap*ext_mult)
        energy_supplier=next(c for c in self.cells.values() if c.cfg.sector=="energy")
        plan={}
        for c in active:
            if c.cfg.sector=="energy":continue
            cfg=c.cfg; dm=dec(shock.get("demand_multiplier",{}).get(cfg.cell_id,1)); pm=dec(shock.get("productivity_multiplier",{}).get(cfg.cell_id,1)); em=dec(shock.get("energy_multiplier",{}).get(cfg.cell_id,1)); cm=dec(shock.get("capacity_multiplier",{}).get(cfg.cell_id,1))
            if min(dm,pm,em,cm)<0:raise EconomyError("negative production shock")
            target=cfg.external_demand*D("0.25"); need=max(ZERO,cfg.external_demand*dm+target-c.inventory)
            plan[c.cfg.cell_id]=max(ZERO,min(cfg.capacity*cm,cfg.labour*cfg.productivity*c.capital*pm,c.material/cfg.material_per_unit,c.energy/(cfg.energy_per_unit*em),need)).quantize(QTY,rounding=ROUND_HALF_UP)
        if energy_supplier in active:
            c=energy_supplier; cfg=c.cfg; em=dec(shock.get("energy_multiplier",{}).get(cfg.cell_id,1)); pm=dec(shock.get("productivity_multiplier",{}).get(cfg.cell_id,1)); cm=dec(shock.get("capacity_multiplier",{}).get(cfg.cell_id,1))
            energy_need=sum((plan.get(x.cfg.cell_id,ZERO)*x.cfg.energy_per_unit*dec(shock.get("energy_multiplier",{}).get(x.cfg.cell_id,1)) for x in active if x.cfg.sector!="energy"),ZERO)
            need=max(ZERO,energy_need+max(D("2"),energy_need*D("0.1"))-c.inventory)
            plan[c.cfg.cell_id]=max(ZERO,min(cfg.capacity*cm,cfg.labour*cfg.productivity*c.capital*pm,c.material/cfg.material_per_unit,c.energy/(cfg.energy_per_unit*em),need)).quantize(QTY,rounding=ROUND_HALF_UP)
        desired=sum((q*self.resource_per_unit for q in plan.values()),ZERO); scale=min(D("1"),extraction/desired) if desired else D("1")
        output=nonenergy=energyout=final=internal=wages=investment=imports=ZERO
        for c in active:
            cfg=c.cfg; em=dec(shock.get("energy_multiplier",{}).get(cfg.cell_id,1)); q=max(ZERO,min(plan.get(cfg.cell_id,ZERO)*scale,c.material/cfg.material_per_unit,c.energy/(cfg.energy_per_unit*em))).quantize(QTY,rounding=ROUND_HALF_UP)
            c.material=max(ZERO,c.material-q*cfg.material_per_unit); c.energy=max(ZERO,c.energy-q*cfg.energy_per_unit*em); c.inventory+=q; c.output=q; c.cum_output+=q; output+=q
            if cfg.sector=="energy":energyout+=q
            else:nonenergy+=q
            wage_bill=money(cfg.labour*self.wage); paid=min(c.cash,wage_bill); c.cash-=paid; c.wages+=paid; wages+=paid; self.household_cash+=paid
            if paid:self._post(Entry(f"p{t}:{cfg.cell_id}:wage","wage and household income",(Line("wage_expense:"+cfg.cell_id,debit=paid),Line("cash:households",debit=paid),Line("cash:"+cfg.cell_id,credit=paid),Line("wage_income:households",credit=paid))))
            c.arrears=c.arrears+1 if paid<wage_bill else 0
            self._event("production",{"cell":cfg.cell_id,"output":str(q),"wage_paid":str(paid)},f"production:{t}:{cfg.cell_id}")
        used=output*self.resource_per_unit; self.resource=max(ZERO,self.resource-used)
        for buyer in sorted(self.cells.values(),key=lambda x:x.cfg.cell_id):
            if buyer is energy_supplier or buyer.insolvent or energy_supplier.insolvent:continue
            em=dec(shock.get("energy_multiplier",{}).get(buyer.cfg.cell_id,1)); need=buyer.output*buyer.cfg.energy_per_unit*em
            got=self._trade(energy_supplier,buyer,need,t); internal+=got*energy_supplier.cfg.unit_price
        for c in active:
            used_mat=c.output*c.cfg.material_per_unit; qty=min(used_mat,c.cash/self.material_price) if self.material_price>0 else ZERO
            qty=max(ZERO,qty).quantize(QTY,rounding=ROUND_HALF_UP); cost=money(qty*self.material_price)
            if qty and cost:
                c.cash-=cost; c.material+=qty; self.supplier_cash+=cost; imports+=cost
                self._post(Entry(f"p{t}:{c.cfg.cell_id}:materials","material import",(Line("inventory_material:"+c.cfg.cell_id,debit=cost),Line("cash:external_suppliers",debit=cost),Line("cash:"+c.cfg.cell_id,credit=cost),Line("supplier_income:materials",credit=cost))))
                self._event("material.import",{"cell":c.cfg.cell_id,"quantity":str(qty),"cost":str(cost)},f"materials:{t}:{c.cfg.cell_id}")
        orders={}; requested=ZERO
        for c in active:
            if c.cfg.sector=="energy":continue
            dm=dec(shock.get("demand_multiplier",{}).get(c.cfg.cell_id,1)); qty=min(c.inventory,c.cfg.external_demand*dm); value=money(qty*c.cfg.unit_price); orders[c.cfg.cell_id]=(qty,value); requested+=value
        budget=min(D("1"),self.household_cash/requested) if requested else D("1")
        for c in active:
            if c.cfg.cell_id not in orders:continue
            qty=min(c.inventory,orders[c.cfg.cell_id][0]*budget); revenue=money(qty*c.cfg.unit_price)
            if revenue>self.household_cash:revenue=money(self.household_cash); qty=revenue/c.cfg.unit_price
            if qty>0 and revenue>0:
                c.inventory=max(ZERO,c.inventory-qty); c.cash+=revenue; self.household_cash-=revenue; c.external_sales+=revenue; final+=revenue
                self._post(Entry(f"p{t}:{c.cfg.cell_id}:sale","household final purchase",(Line("cash:"+c.cfg.cell_id,debit=revenue),Line("consumption:households",debit=revenue),Line("cash:households",credit=revenue),Line("sales:"+c.cfg.cell_id,credit=revenue))))
                self._event("household.purchase",{"cell":c.cfg.cell_id,"quantity":str(qty),"spend":str(revenue)},f"sale:{t}:{c.cfg.cell_id}")
        for c in active:
            maintenance=money(c.capital*c.cfg.investment_cost*self.maintenance_rate); paid=min(c.cash,maintenance)
            if paid:
                c.cash-=paid; self.supplier_cash+=paid
                self._post(Entry(f"p{t}:{c.cfg.cell_id}:maintenance","maintenance purchase",(Line("maintenance_expense:"+c.cfg.cell_id,debit=paid),Line("cash:external_suppliers",debit=paid),Line("cash:"+c.cfg.cell_id,credit=paid),Line("supplier_income:maintenance",credit=paid))))
            budget=money(max(ZERO,c.cash-c.cfg.reserve_target)*self.investment_share); budget=min(budget,money(c.cfg.investment_cost))
            if budget>0 and c.cfg.investment_cost>0:
                c.cash-=budget; self.supplier_cash+=budget; c.capital+=c.cfg.investment_gain*budget/c.cfg.investment_cost; c.investment+=budget; investment+=budget
                self._post(Entry(f"p{t}:{c.cfg.cell_id}:investment","capital asset purchase",(Line("productive_capital:"+c.cfg.cell_id,debit=budget),Line("cash:external_suppliers",debit=budget),Line("cash:"+c.cfg.cell_id,credit=budget),Line("supplier_income:capital",credit=budget))))
        self._repay(t); self._interest(t)
        for c in active:
            excess=max(ZERO,c.cash-c.cfg.reserve_target); reserve=money(excess*self.reserve_share); dist=money(max(ZERO,excess-reserve)*self.distribution_share)
            if dist:
                c.cash-=dist; self.household_cash+=dist
                self._post(Entry(f"p{t}:{c.cfg.cell_id}:distribution","member distribution",(Line("distribution_expense:"+c.cfg.cell_id,debit=dist),Line("cash:households",debit=dist),Line("cash:"+c.cfg.cell_id,credit=dist),Line("member_income:households",credit=dist))))
        self._assess_defaults(t); self.ledger.assert_balanced()
        ar=sum((c.receivables for c in self.cells.values()),ZERO); ap=sum((c.payables for c in self.cells.values()),ZERO); positions=sum(self.positions.values(),ZERO)
        if money(ar)!=money(ap) or money(ar)!=money(positions):raise EconomyError("bilateral credit reconciliation failure")
        cellcash=sum((c.cash for c in self.cells.values()),ZERO); system=cellcash+self.household_cash+self.supplier_cash
        if self.resource<0 or any(c.cash<0 or c.inventory<0 for c in self.cells.values()):raise EconomyError("negative stock")
        if money(system)!=money(self.initial_system_cash):raise EconomyError(f"cash conservation failed: {system} != {self.initial_system_cash}")
        digest=sha256("".join(e["digest"] for e in self.events).encode()).hexdigest()
        result=Period(t,output,nonenergy,energyout,final,internal,wages,investment,imports,final-imports,self.resource,cellcash,self.household_cash,self.supplier_cash,system,ar,ap,sum(c.insolvent for c in self.cells.values()),self._gini([c.cash for c in self.cells.values()]),digest)
        self.results.append(result); return result
    def _assess_defaults(self,t):
        for c in self.cells.values():
            if not c.insolvent and c.arrears>=2 and c.payables/max(D("1"),c.cfg.credit_limit)>c.cfg.default_threshold:
                c.insolvent=True; c.defaults+=c.payables
                self._event("cell.insolvency",{"cell":c.cfg.cell_id,"payables":str(c.payables)},f"default:{t}:{c.cfg.cell_id}")
    def run(self,periods=24,shocks=None):
        shocks=shocks or {}
        for t in range(1,periods+1):self.step(t,shocks.get(t,{}))
        return self.results
    def snapshot(self):
        return {"resource_stock":str(self.resource),"household_cash":str(self.household_cash),"external_supplier_cash":str(self.supplier_cash),"system_cash":str(sum((c.cash for c in self.cells.values()),ZERO)+self.household_cash+self.supplier_cash),"initial_system_cash":str(self.initial_system_cash),"cells":{k:{"sector":c.cfg.sector,"cash":str(c.cash),"material":str(c.material),"energy":str(c.energy),"inventory":str(c.inventory),"capital":str(c.capital),"receivables":str(c.receivables),"payables":str(c.payables),"cumulative_output":str(c.cum_output),"wages_paid":str(c.wages),"investment":str(c.investment),"external_sales":str(c.external_sales),"insolvent":c.insolvent} for k,c in self.cells.items()},"periods":[{k:(str(v) if isinstance(v,D) else v) for k,v in p.__dict__.items()} for p in self.results],"journal_entries":len(self.ledger.entries),"events":len(self.events)}

SCENARIOS={
 "baseline":{},
 "demand_collapse":{8:{"demand_multiplier":{"cell-4":D(".25"),"cell-5":D(".35"),"cell-6":D(".50")}},9:{"demand_multiplier":{"cell-4":D(".25"),"cell-5":D(".35"),"cell-6":D(".50")}},10:{"demand_multiplier":{"cell-4":D(".25"),"cell-5":D(".35"),"cell-6":D(".50")}}},
 "energy_shock":{8:{"energy_multiplier":{"cell-1":D("4"),"cell-2":D("3.8"),"cell-4":D("4.5"),"cell-5":D("3.5")}},9:{"energy_multiplier":{"cell-1":D("4"),"cell-2":D("3.8"),"cell-4":D("4.5"),"cell-5":D("3.5")}},10:{"energy_multiplier":{"cell-1":D("2.5"),"cell-2":D("2.3"),"cell-4":D("2.8"),"cell-5":D("2.3")}}},
 "resource_shock":{8:{"resource_extraction_multiplier":D(".35")},9:{"resource_extraction_multiplier":D(".35")},10:{"resource_extraction_multiplier":D(".35")},11:{"resource_extraction_multiplier":D(".6")}},
 "compound_crisis":{8:{"demand_multiplier":{"cell-4":D(".25"),"cell-5":D(".35"),"cell-6":D(".50")},"energy_multiplier":{"cell-1":D("4"),"cell-2":D("3.8"),"cell-4":D("4.5"),"cell-5":D("3.5")},"resource_extraction_multiplier":D(".35")},9:{"demand_multiplier":{"cell-4":D(".25"),"cell-5":D(".35"),"cell-6":D(".50")},"energy_multiplier":{"cell-1":D("4"),"cell-2":D("3.8"),"cell-4":D("4.5"),"cell-5":D("3.5")},"resource_extraction_multiplier":D(".35")},10:{"demand_multiplier":{"cell-4":D(".25"),"cell-5":D(".35"),"cell-6":D(".50")},"resource_extraction_multiplier":D(".6")}}
}
def run_scenario(name,periods=24):
    if name not in SCENARIOS:raise EconomyError("unknown scenario: "+name)
    e=SevenCellEconomy();e.run(periods,SCENARIOS[name]);r=e.results
    summary={"cumulative_gross_physical_output_index":str(sum((x.output for x in r),ZERO)),"cumulative_non_energy_output_index":str(sum((x.non_energy_output for x in r),ZERO)),"cumulative_energy_output_index":str(sum((x.energy_output for x in r),ZERO)),"cumulative_final_household_expenditure":str(sum((x.final_sales for x in r),ZERO)),"cumulative_internal_intermediate_sales":str(sum((x.internal_sales for x in r),ZERO)),"cumulative_material_import_cost":str(sum((x.material_imports for x in r),ZERO)),"cumulative_net_value_added_proxy":str(sum((x.value_added_proxy for x in r),ZERO)),"cumulative_wages_paid":str(sum((x.wages for x in r),ZERO)),"cumulative_capital_investment":str(sum((x.investment for x in r),ZERO)),"ending_resource_stock":str(e.resource),"ending_household_cash":str(e.household_cash),"ending_system_cash":str(sum((c.cash for c in e.cells.values()),ZERO)+e.household_cash+e.supplier_cash),"system_cash_conservation_error":str(sum((c.cash for c in e.cells.values()),ZERO)+e.household_cash+e.supplier_cash-e.initial_system_cash),"insolvent_cells":sum(c.insolvent for c in e.cells.values()),"ending_cash_gini":str(r[-1].cash_gini if r else ZERO),"journal_entries":len(e.ledger.entries),"events":len(e.events),"event_chain_digest":r[-1].event_hash if r else ""}
    return {**e.snapshot(),"scenario":name,"summary":summary}

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--scenario",choices=SCENARIOS,default="baseline");p.add_argument("--periods",type=int,default=24);p.add_argument("--output");a=p.parse_args();data=json.dumps(run_scenario(a.scenario,a.periods),indent=2)
    if a.output:open(a.output,"w",encoding="utf-8").write(data+"\n")
    print(data)
