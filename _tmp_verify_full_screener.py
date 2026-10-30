import json,pandas as pd
from pathlib import Path
root=Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
bdir=root/"experiments/current-data-recovery-20261003/screener-full-export-batches"
plan=json.load(open(bdir/"batch_plan.json",encoding="utf-8"))
planned=set()
exported=set()
for k,terms in plan["chunks"].items():
    planned.update(terms)
    p=bdir/f"screener_remaining_batch_{int(k):02d}.csv"
    h=set(pd.read_csv(p,nrows=0).columns)
    exported.update(h)
    miss=set(terms)-h
    print("batch",k,"planned",len(terms),"cols",len(h),"missing_planned",len(miss))
    if miss: print(" MISS",sorted(miss))
print("remaining planned total",len(planned),"found",len(planned&exported),"missing",len(planned-exported))
if planned-exported: print(sorted(planned-exported))
b1=set(pd.read_csv(Path(r"C:\Users\Harshil\Downloads\query-results.csv"),nrows=0).columns)
b2=set(pd.read_csv(Path(r"C:\Users\Harshil\Downloads\query-results (1).csv"),nrows=0).columns)
union=(b1|b2|exported)-{"Name","BSE Code","NSE Code","ISIN Code","Industry Group","Industry"}
inv=json.load(open(Path(r"C:\Users\Harshil\Downloads\screener_category_inventory.json"),encoding="utf-8"))
alln={x["name"] for v in inv.values() if isinstance(v,list) for x in v}
print("all selectable inventory",len(alln),"covered selectable",len(alln&union),"missing selectable",len(alln-union))
if alln-union: print("MISSING_ALL",sorted(alln-union))
