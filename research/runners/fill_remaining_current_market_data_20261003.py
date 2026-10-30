from __future__ import annotations
from pathlib import Path
import hashlib, json, math, time
import numpy as np
import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[2]
IN=ROOT/"experiments/professor-current-fallback-20261003/equal-priority-v2/current_company_facts_equal_priority.csv.gz"
OUT=ROOT/"experiments/current-data-recovery-20261003"
CUTOFF=pd.Timestamp("2026-09-18")
END="2026-09-19"
START="2016-09-01"
OUT.mkdir(parents=True,exist_ok=True)
FILL_FIELDS=["product_baseline_yoy_growth","product_baseline_cagr_3y","product_baseline_cagr_5y"]
def yahoo_candidates(row):
    vals=[]
    p=row.get("bulk_classification_provider_symbol")
    if isinstance(p,str) and p.strip() and p.strip().lower()!="nan":
        vals.append(p.strip())
    t=str(row.get("ticker",""))
    if t.startswith("BSE-"):
        vals.append(t.split("-",1)[1]+".BO")
    elif t.startswith("NSE-"):
        vals.append(t.split("-",1)[1]+".NS")
    out=[]
    for v in vals:
        if v not in out:
            out.append(v)
    return out

def strict_cagr(s,years):
    s=s.dropna()
    if len(s)<2: return np.nan
    anchor=CUTOFF-pd.DateOffset(years=years)
    before=s.loc[s.index<=anchor]
    if before.empty: return np.nan
    d0=before.index[-1]
    if (anchor-d0).days>7: return np.nan
    d1=s.index[-1]
    if (CUTOFF-d1).days>21 or d1<=d0: return np.nan
    span=(d1-d0).days
    return float(np.expm1(np.log(float(s.iloc[-1])/float(before.iloc[-1]))*365.0/span))
def extract_hist(raw,sym):
    try:
        if isinstance(raw.columns,pd.MultiIndex):
            if sym in raw.columns.get_level_values(0):
                f=raw[sym].copy()
            elif sym in raw.columns.get_level_values(1):
                f=raw.xs(sym,axis=1,level=1).copy()
            else:
                return None
        else:
            f=raw.copy()
        col="Adj Close" if "Adj Close" in f.columns else ("Close" if "Close" in f.columns else None)
        if col is None: return None
        s=pd.to_numeric(f[col],errors="coerce").dropna()
        s.index=pd.to_datetime(s.index).tz_localize(None)
        s=s.loc[(s.index<=CUTOFF)&(s>0)]
        return s if len(s) else None
    except Exception:
        return None

def download_many(symbols,start=START):
    got={}
    symbols=list(dict.fromkeys(symbols))
    for i in range(0,len(symbols),80):
        batch=symbols[i:i+80]
        try:
            raw=yf.download(batch,start=start,end=END,auto_adjust=False,actions=False,
                            progress=False,threads=True,group_by="ticker",timeout=20)
        except Exception:
            raw=pd.DataFrame()
        for sym in batch:
            s=extract_hist(raw,sym) if not raw.empty else None
            if s is not None: got[sym]=s
        print("download",min(i+80,len(symbols)),"/",len(symbols),"usable",len(got),flush=True)
        time.sleep(0.25)
    return got
d=pd.read_csv(IN,low_memory=False)
before={c:int(d[c].isna().sum()) for c in FILL_FIELDS}
before["product_baseline_days_since_recorded_high"]=int(d["product_baseline_days_since_recorded_high"].isna().sum())
for c in ["product_baseline_yoy_growth_source","product_baseline_cagr_3y_source",
          "product_baseline_cagr_5y_source","product_baseline_days_since_recorded_high_source",
          "recorded_high_source","current_cagr_7y_source","current_cagr_10y_source"]:
    if c not in d.columns: d[c]=pd.Series([None]*len(d),dtype="object")
    else: d[c]=d[c].astype("object")
d["current_cagr_7y"]=pd.to_numeric(d.get("professor_workbook_cagr_7y"),errors="coerce")
d["current_cagr_10y"]=pd.to_numeric(d.get("professor_workbook_cagr_10y"),errors="coerce")
d.loc[d["current_cagr_7y"].notna(),"current_cagr_7y_source"]="PROFESSOR_EXCEL"
d.loc[d["current_cagr_10y"].notna(),"current_cagr_10y_source"]="PROFESSOR_EXCEL"

need_mask=d[FILL_FIELDS].isna().any(axis=1)|d["current_cagr_7y"].isna()|d["current_cagr_10y"].isna()
rows=d.loc[need_mask].copy()
row_candidates={i:yahoo_candidates(r) for i,r in rows.iterrows()}
primary=[v[0] for v in row_candidates.values() if v]
hist=download_many(primary,START)
fallback=[]
for i,r in rows.iterrows():
    cands=row_candidates.get(i,[])
    if len(cands)<2: continue
    s=hist.get(cands[0])
    need=False
    if s is None:
        need=True
    else:
        for field,years in [("product_baseline_yoy_growth",1),("product_baseline_cagr_3y",3),
                            ("product_baseline_cagr_5y",5)]:
            if pd.isna(r[field]) and pd.isna(strict_cagr(s,years)): need=True
        if pd.isna(r.get("professor_workbook_cagr_7y")) and pd.isna(strict_cagr(s,7)): need=True
        if pd.isna(r.get("professor_workbook_cagr_10y")) and pd.isna(strict_cagr(s,10)): need=True
    if need: fallback.append(cands[1])
hist.update(download_many(fallback,START))
ledger=[]
def choose_series(i):
    choices=[hist.get(x) for x in row_candidates.get(i,[]) if hist.get(x) is not None]
    if not choices: return None,None
    choices.sort(key=lambda s:(s.index[-1],len(s)),reverse=True)
    s=choices[0]
    sym=next(x for x in row_candidates[i] if hist.get(x) is s)
    return s,sym
source_map={
    "product_baseline_yoy_growth":"product_baseline_yoy_growth_source",
    "product_baseline_cagr_3y":"product_baseline_cagr_3y_source",
    "product_baseline_cagr_5y":"product_baseline_cagr_5y_source",
}
for i,r in rows.iterrows():
    s,sym=choose_series(i)
    if s is None: continue
    for field,years in [("product_baseline_yoy_growth",1),("product_baseline_cagr_3y",3),
                        ("product_baseline_cagr_5y",5)]:
        if pd.isna(d.at[i,field]):
            v=strict_cagr(s,years)
            if pd.notna(v):
                d.at[i,field]=v
                d.at[i,source_map[field]]="YAHOO_FINANCE_ADJUSTED_CLOSE"
                ledger.append({"row":int(i),"isin":r.get("isin"),"ticker":r.get("ticker"),
                               "field":field,"value":float(v),"source":"YAHOO_FINANCE_ADJUSTED_CLOSE",
                               "provider_symbol":sym})
    for field,years in [("current_cagr_7y",7),("current_cagr_10y",10)]:
        if pd.isna(d.at[i,field]):
            v=strict_cagr(s,years)
            if pd.notna(v):
                d.at[i,field]=v
                d.at[i,field+"_source"]="YAHOO_FINANCE_ADJUSTED_CLOSE"
                ledger.append({"row":int(i),"isin":r.get("isin"),"ticker":r.get("ticker"),
                               "field":field,"value":float(v),"source":"YAHOO_FINANCE_ADJUSTED_CLOSE",
                               "provider_symbol":sym})
need_high=d["product_baseline_days_since_recorded_high"].isna()|d["recorded_high"].isna()|d["recorded_high_date"].isna()
high_rows=d.loc[need_high].copy()
high_candidates={i:yahoo_candidates(r) for i,r in high_rows.iterrows()}
all_high_syms=[]
for vals in high_candidates.values():
    all_high_syms.extend(vals)
full_hist=download_many(all_high_syms,"1990-01-01")

for i,r in high_rows.iterrows():
    opts=[(sym,full_hist.get(sym)) for sym in high_candidates.get(i,[]) if full_hist.get(sym) is not None]
    if not opts: continue
    opts.sort(key=lambda x:(x[1].index[-1],len(x[1])),reverse=True)
    sym,s=opts[0]
    if (CUTOFF-s.index[-1]).days>21: continue
    peak=float(s.max()); peak_date=s.idxmax().normalize()
    days=int((CUTOFF-peak_date).days)
    for field,value,srcfield in [
        ("recorded_high",peak,"recorded_high_source"),
        ("recorded_high_date",peak_date.date().isoformat(),"recorded_high_source"),
        ("product_baseline_days_since_recorded_high",days,"product_baseline_days_since_recorded_high_source"),
    ]:
        if pd.isna(d.at[i,field]):
            d.at[i,field]=value
            d.at[i,srcfield]="YAHOO_FINANCE_ADJUSTED_CLOSE"
            ledger.append({"row":int(i),"isin":r.get("isin"),"ticker":r.get("ticker"),
                           "field":field,"value":value,"source":"YAHOO_FINANCE_ADJUSTED_CLOSE",
                           "provider_symbol":sym})
orig=pd.read_csv(IN,low_memory=False)
protected=FILL_FIELDS+["product_baseline_days_since_recorded_high","recorded_high","recorded_high_date"]
for field in protected:
    mask=orig[field].notna()
    left=orig.loc[mask,field].astype(str).reset_index(drop=True)
    right=d.loc[mask,field].astype(str).reset_index(drop=True)
    if not left.equals(right):
        raise RuntimeError("existing nonblank value changed: "+field)

out_file=OUT/"current_company_facts_recovered.csv.gz"
d.to_csv(out_file,index=False,compression="gzip")
led=pd.DataFrame(ledger)
led.to_csv(OUT/"filled_cells.csv",index=False)
track=FILL_FIELDS+["product_baseline_days_since_recorded_high","current_cagr_7y","current_cagr_10y"]
after={c:int(d[c].isna().sum()) for c in track}
before.update({
    "current_cagr_7y":int(pd.to_numeric(orig.get("professor_workbook_cagr_7y"),errors="coerce").isna().sum()),
    "current_cagr_10y":int(pd.to_numeric(orig.get("professor_workbook_cagr_10y"),errors="coerce").isna().sum()),
})
unresolved=d.loc[d[track].isna().any(axis=1),
                 ["ticker","company","isin","bulk_classification_provider_symbol"]+track].copy()
unresolved.to_csv(OUT/"unresolved_rows.csv",index=False)
summary={"schema":"current_data_recovery_v1","cutoff":CUTOFF.date().isoformat(),
         "input":str(IN.relative_to(ROOT)),"output":str(out_file.relative_to(ROOT)),
         "filled_cells":int(len(led)),"stocks_filled":int(led["ticker"].nunique()) if len(led) else 0,
         "missing_before":before,"missing_after":after,
         "existing_nonblank_overwritten":0,"historical_training_modified":False,
         "production_modified":False,"sources":["PROFESSOR_EXCEL","YAHOO_FINANCE_ADJUSTED_CLOSE"]}
(OUT/"summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
manifest={}
for p in sorted(OUT.iterdir()):
    if p.is_file():
        manifest[p.name]={"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
(OUT/"manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2),flush=True)
print("OUTPUT",out_file,flush=True)
