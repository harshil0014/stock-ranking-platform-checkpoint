from pathlib import Path
import json
import numpy as np
import pandas as pd

ROOT = Path(r"C:\Users\Harshil\Downloads\stock-ranking-platform-fresh-canonical-verified")
V11 = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v11"
V12 = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12"
s12 = json.loads((V12 / "summary.json").read_text())
source_dates = set(s12["source_dates"])

def source_rows(path):
    parts=[]
    for chunk in pd.read_csv(path, chunksize=100000, low_memory=False):
        x=chunk.loc[chunk["decision_date"].astype(str).isin(source_dates)]
        if not x.empty: parts.append(x)
    return pd.concat(parts,ignore_index=True)

a=source_rows(V11/"deep_panel.csv.gz")
b=source_rows(V12/"deep_panel.csv.gz")
assert a.shape==b.shape and list(a.columns)==list(b.columns)
report={"rows":len(a),"columns":len(a.columns),"non_numeric_mismatches":{},"numeric_drift":{}}
for col in a.columns:
    x,y=a[col],b[col]
    if pd.api.types.is_numeric_dtype(x) and pd.api.types.is_numeric_dtype(y):
        xa=x.to_numpy(float); ya=y.to_numpy(float)
        both_nan=np.isnan(xa)&np.isnan(ya)
        finite=np.isfinite(xa)&np.isfinite(ya)
        bad_nan=np.isnan(xa)^np.isnan(ya)
        absdiff=np.zeros(len(xa))
        absdiff[finite]=np.abs(xa[finite]-ya[finite])
        exact=(xa==ya)|both_nan
        drift=(~exact)&(~bad_nan)
        if drift.any() or bad_nan.any():
            denom=np.maximum(np.abs(xa),np.abs(ya))
            rel=np.zeros(len(xa))
            nz=finite&(denom>0)
            rel[nz]=absdiff[nz]/denom[nz]
            report["numeric_drift"][col]={
                "different_values":int(drift.sum()+bad_nan.sum()),
                "max_abs":float(absdiff.max()),
                "max_rel":float(rel.max()),
                "within_1e_12":bool(np.allclose(xa,ya,rtol=1e-12,atol=1e-15,equal_nan=True)),
            }
    else:
        eq=(x.astype("string").fillna("<NA>")==y.astype("string").fillna("<NA>"))
        if not bool(eq.all()):
            report["non_numeric_mismatches"][col]=int((~eq).sum())
print(json.dumps(report,indent=2))
