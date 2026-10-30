from __future__ import annotations
from pathlib import Path
import hashlib, json, math, time, warnings
import numpy as np
import pandas as pd
import yfinance as yf

from stock_ranker.history_enrichment import compute_history_metrics

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"experiments/current-data-recovery-20261003"
IN=DIR/"current_company_facts_recovered_v6_full_screener.csv.gz"
OUT=DIR/"current_company_facts_recovered_v7_yahoo_full.csv.gz"
METRICS=DIR/"yahoo_full_current_metrics.csv.gz"
CUTOFF=pd.Timestamp("2026-10-03")
START="1990-01-01"
END="2026-10-04"
BATCH=60
warnings.filterwarnings("ignore",category=pd.errors.PerformanceWarning)

d=pd.read_csv(IN,low_memory=False)
orig=d.copy(deep=True)

def clean_code(v):
    if pd.isna(v): return None
    s=str(v).strip()
    if not s or s.lower()=="nan": return None
    try:
        f=float(s)
        if f.is_integer(): return str(int(f))
    except Exception:
        pass
    return s

def candidates(row):
    out=[]
    p=clean_code(row.get("bulk_classification_provider_symbol"))
    if p and (p.endswith(".NS") or p.endswith(".BO")):
        out.append((p,"VERIFIED_PROVIDER_SYMBOL"))
    ex=str(row.get("primary_exchange","")).upper()
    nse=clean_code(row.get("screener_nse_code"))
    bse=clean_code(row.get("screener_bse_code"))
    t=clean_code(row.get("ticker"))
    if ex=="NSE":
        if nse: out.append((nse+".NS","SCREENER_EXACT_ISIN_NSE_CODE"))
        if t and not t.startswith("BSE-"): out.append((t+".NS","REPO_NSE_TICKER"))
        if bse: out.append((bse+".BO","SCREENER_EXACT_ISIN_BSE_CODE"))
    else:
        if bse: out.append((bse+".BO","SCREENER_EXACT_ISIN_BSE_CODE"))
        if t and t.startswith("BSE-"): out.append((t.split("-",1)[1]+".BO","REPO_BSE_CODE"))
        if nse: out.append((nse+".NS","SCREENER_EXACT_ISIN_NSE_CODE"))
    seen=set(); result=[]
    for sym,method in out:
        if sym not in seen:
            seen.add(sym); result.append((sym,method))
    return result

row_candidates={i:candidates(r) for i,r in d.iterrows()}
primary=[vals[0][0] for vals in row_candidates.values() if vals]
print("ROWS",len(d),"PRIMARY_SYMBOLS",len(primary),"UNIQUE",len(set(primary)),flush=True)
def extract_one(raw,sym):
    try:
        if raw is None or raw.empty: return None
        if isinstance(raw.columns,pd.MultiIndex):
            lvl0=raw.columns.get_level_values(0)
            lvl1=raw.columns.get_level_values(1)
            if sym in lvl0:
                f=raw[sym].copy()
            elif sym in lvl1:
                f=raw.xs(sym,axis=1,level=1).copy()
            else:
                return None
        else:
            f=raw.copy()
        f=f.copy()
        f.index=pd.to_datetime(f.index,errors="coerce").tz_localize(None)
        f=f.loc[f.index.notna()].sort_index()
        if f.empty: return None
        return f
    except Exception:
        return None

def batch_download(symbols):
    got={}
    symbols=list(dict.fromkeys(symbols))
    for off in range(0,len(symbols),BATCH):
        batch=symbols[off:off+BATCH]
        raw=None
        for attempt in range(2):
            try:
                raw=yf.download(batch,start=START,end=END,auto_adjust=False,actions=False,
                                progress=False,threads=True,group_by="ticker",timeout=25)
                break
            except Exception as e:
                print("BATCH_ERR",off,attempt,type(e).__name__,str(e)[:120],flush=True)
                time.sleep(1.5)
        if raw is not None and not raw.empty:
            for sym in batch:
                f=extract_one(raw,sym)
                if f is not None and len(f):
                    got[sym]=f
        print("PRIMARY_DL",min(off+BATCH,len(symbols)),"/",len(symbols),"usable",len(got),flush=True)
        time.sleep(0.20)
    return got

hist=batch_download(primary)

# Retry alternate exchange/provider candidates only for rows whose primary symbol failed.
fallback_symbols=[]
for i,vals in row_candidates.items():
    if not vals: continue
    if vals[0][0] in hist: continue
    fallback_symbols.extend(sym for sym,_ in vals[1:])
fallback_symbols=list(dict.fromkeys(fallback_symbols))
print("FALLBACK_SYMBOLS",len(fallback_symbols),flush=True)
hist.update(batch_download(fallback_symbols))
def numeric_series(f,name):
    if name not in f.columns: return pd.Series(dtype=float)
    s=pd.to_numeric(f[name],errors="coerce")
    s.index=f.index
    return s.dropna()

def adj_series(f):
    s=numeric_series(f,"Adj Close")
    if s.empty: s=numeric_series(f,"Close")
    s=s.loc[(s.index<=CUTOFF)&(s>0)]
    return s[~s.index.duplicated(keep="last")].sort_index()

def is_usable_frame(f):
    if f is None: return False
    s=adj_series(f)
    if len(s)<2: return False
    return 0 <= (CUTOFF-s.index[-1].normalize()).days <= 21

extra=[]
for i,vals in row_candidates.items():
    if not vals: continue
    f=hist.get(vals[0][0])
    if is_usable_frame(f): continue
    extra.extend(sym for sym,_ in vals[1:] if sym not in hist)
extra=list(dict.fromkeys(extra))
if extra:
    print("STALE_OR_BAD_PRIMARY_EXTRA",len(extra),flush=True)
    hist.update(batch_download(extra))

def choose(i):
    vals=row_candidates.get(i,[])
    usable=[]
    for priority,(sym,method) in enumerate(vals):
        f=hist.get(sym)
        if not is_usable_frame(f): continue
        s=adj_series(f)
        lag=(CUTOFF-s.index[-1].normalize()).days
        # Prefer primary-exchange identity order, then freshness/history as tie breakers.
        usable.append((priority,lag,-len(s),sym,method,f))
    if not usable: return None
    usable.sort(key=lambda x:(x[0],x[1],x[2]))
    return usable[0][3],usable[0][4],usable[0][5]

def strict_cagr(s,years):
    s=s.dropna().sort_index()
    if len(s)<2: return np.nan
    anchor=CUTOFF-pd.DateOffset(years=years)
    before=s.loc[s.index<=anchor]
    if before.empty: return np.nan
    d0=before.index[-1].normalize()
    if (anchor-d0).days<0 or (anchor-d0).days>7: return np.nan
    d1=s.index[-1].normalize()
    span=(d1-d0).days
    if span<=0: return np.nan
    p0=float(before.iloc[-1]); p1=float(s.iloc[-1])
    if p0<=0 or p1<=0: return np.nan
    return float(np.expm1(np.log(p1/p0)*365.0/span))
# NIFTY 50 benchmark for an explicit price-derived 1Y beta diagnostic.
try:
    nifty_raw=yf.download("^NSEI",start="2025-09-20",end=END,auto_adjust=False,
                          actions=False,progress=False,threads=False,timeout=25)
    nifty=adj_series(nifty_raw)
    nifty_ret=np.log(nifty).diff().dropna()
except Exception:
    nifty_ret=pd.Series(dtype=float)

records=[]
for i,row in d.iterrows():
    chosen=choose(i)
    if chosen is None:
        records.append({"row":int(i),"isin":row.get("isin"),"ticker":row.get("ticker"),
                        "yahoo_status":"NO_USABLE_HISTORY"})
        continue
    sym,method,f=chosen
    adj=adj_series(f)
    frame=pd.DataFrame({"date":adj.index,"price":adj.values})
    try:
        m=compute_history_metrics(frame,cutoff=CUTOFF,listing_date=row.get("listing_date"))
    except Exception as e:
        records.append({"row":int(i),"isin":row.get("isin"),"ticker":row.get("ticker"),
                        "yahoo_symbol":sym,"yahoo_symbol_method":method,
                        "yahoo_status":"METRIC_ERROR","yahoo_error":str(e)[:200]})
        continue
    year=adj.loc[adj.index>=CUTOFF-pd.Timedelta(days=365)]
    high52=float(year.max()) if len(year) else np.nan
    low52=float(year.min()) if len(year) else np.nan
    high52date=year.idxmax().date().isoformat() if len(year) else None
    low52date=year.idxmin().date().isoformat() if len(year) else None
    raw_close=numeric_series(f,"Close")
    raw_high=numeric_series(f,"High")
    raw_low=numeric_series(f,"Low")
    raw_vol=numeric_series(f,"Volume")
    raw_close=raw_close.loc[raw_close.index<=CUTOFF]
    raw_high=raw_high.loc[raw_high.index<=CUTOFF]
    raw_low=raw_low.loc[raw_low.index<=CUTOFF]
    raw_vol=raw_vol.loc[raw_vol.index<=CUTOFF]
    beta=np.nan
    if len(nifty_ret):
        sr=np.log(adj.loc[adj.index>=CUTOFF-pd.Timedelta(days=365)]).diff().dropna()
        z=pd.concat([sr.rename("s"),nifty_ret.rename("m")],axis=1,join="inner").dropna()
        if len(z)>=60 and float(z["m"].var(ddof=1))>0:
            beta=float(z["s"].cov(z["m"])/z["m"].var(ddof=1))
    rec={
        "row":int(i),"isin":row.get("isin"),"ticker":row.get("ticker"),
        "yahoo_symbol":sym,"yahoo_symbol_method":method,"yahoo_status":"OK",
        "yahoo_history_start_date":m["history_start_date"],
        "yahoo_history_end_date":m["history_end_date"],
        "yahoo_history_observation_count":m["history_observation_count"],
        "yahoo_history_months":m["history_months"],
        "yahoo_terminal_lag_days":m["terminal_lag_days"],
        "yahoo_strict_cagr_1y":m["strict_cagr_1y"],
        "yahoo_strict_cagr_3y":m["strict_cagr_3y"],
        "yahoo_strict_cagr_5y":m["strict_cagr_5y"],
        "yahoo_strict_cagr_7y":strict_cagr(adj,7),
        "yahoo_strict_cagr_10y":strict_cagr(adj,10),
        "yahoo_recorded_high_price":m["recorded_high_price"],
        "yahoo_recorded_high_date":m["recorded_high_date"],
        "yahoo_days_since_recorded_high":m["days_since_recorded_high"],
        "yahoo_distance_from_recorded_high":m["distance_from_recorded_high"],
        "yahoo_distance_from_52w_high":m["distance_from_52w_high"],
        "yahoo_high_52w":high52,"yahoo_high_52w_date":high52date,
        "yahoo_low_52w":low52,"yahoo_low_52w_date":low52date,
        "yahoo_full_history_max_drawdown":m["full_history_max_drawdown"],
        "yahoo_current_drawdown_duration_days":m["current_drawdown_duration_days"],
        "yahoo_max_drawdown_duration_days":m["max_drawdown_duration_days"],
        "yahoo_recovery_from_worst_trough":m["recovery_from_worst_trough"],
        "yahoo_realized_volatility_1y":m["realized_volatility_1y"],
        "yahoo_downside_volatility_1y":m["downside_volatility_1y"],
        "yahoo_beta_1y_vs_nifty50":beta,
        "yahoo_latest_adjusted_close":float(adj.iloc[-1]),
        "yahoo_latest_raw_close":float(raw_close.iloc[-1]) if len(raw_close) else np.nan,
        "yahoo_latest_raw_high":float(raw_high.iloc[-1]) if len(raw_high) else np.nan,
        "yahoo_latest_raw_low":float(raw_low.iloc[-1]) if len(raw_low) else np.nan,
        "yahoo_latest_volume":float(raw_vol.iloc[-1]) if len(raw_vol) else np.nan,
    }
    records.append(rec)
    if (i+1)%500==0:
        print("METRICS",i+1,"/",len(d),flush=True)

metrics=pd.DataFrame(records)
metrics.to_csv(METRICS,index=False,compression="gzip")
print("YAHOO_OK",int((metrics["yahoo_status"]=="OK").sum()),"OF",len(metrics),flush=True)
# Attach all Yahoo diagnostics as explicit current-only columns.
metrics_by_row=metrics.set_index("row")
for col in metrics.columns:
    if col in {"row","isin","ticker"}: continue
    vals=d.index.to_series().map(metrics_by_row[col] if col in metrics_by_row.columns else {})
    if col not in d.columns:
        d[col]=vals.values
    else:
        mask=d[col].isna()
        d.loc[mask,col]=vals.loc[mask].values

ledger=[]
def fill_blank(i,target,value,source_col):
    if target not in d.columns or pd.notna(d.at[i,target]) or pd.isna(value):
        return
    d.at[i,target]=value
    ledger.append({"row":int(i),"isin":d.at[i,"isin"],"ticker":d.at[i,"ticker"],
                   "field":target,"value":value,"source":"YAHOO_FINANCE_FULL_HISTORY_2026-10-03",
                   "source_column":source_col,"yahoo_symbol":d.at[i,"yahoo_symbol"]})

for i in d.index:
    if d.at[i,"yahoo_status"]!="OK": continue
    fill_blank(i,"history_start_date",d.at[i,"yahoo_history_start_date"],"yahoo_history_start_date")
    fill_blank(i,"history_end_date",d.at[i,"yahoo_history_end_date"],"yahoo_history_end_date")
    fill_blank(i,"history_observation_count",d.at[i,"yahoo_history_observation_count"],"yahoo_history_observation_count")
    fill_blank(i,"high_52w",d.at[i,"yahoo_high_52w"],"yahoo_high_52w")
    fill_blank(i,"high_52w_date",d.at[i,"yahoo_high_52w_date"],"yahoo_high_52w_date")
    fill_blank(i,"low_52w",d.at[i,"yahoo_low_52w"],"yahoo_low_52w")
    fill_blank(i,"low_52w_date",d.at[i,"yahoo_low_52w_date"],"yahoo_low_52w_date")
    fill_blank(i,"recorded_high",d.at[i,"yahoo_recorded_high_price"],"yahoo_recorded_high_price")
    fill_blank(i,"recorded_high_date",d.at[i,"yahoo_recorded_high_date"],"yahoo_recorded_high_date")
    fill_blank(i,"product_baseline_yoy_growth",d.at[i,"yahoo_strict_cagr_1y"],"yahoo_strict_cagr_1y")
    fill_blank(i,"product_baseline_cagr_3y",d.at[i,"yahoo_strict_cagr_3y"],"yahoo_strict_cagr_3y")
    fill_blank(i,"product_baseline_cagr_5y",d.at[i,"yahoo_strict_cagr_5y"],"yahoo_strict_cagr_5y")
    fill_blank(i,"product_baseline_days_since_recorded_high",d.at[i,"yahoo_days_since_recorded_high"],"yahoo_days_since_recorded_high")
    fill_blank(i,"current_cagr_7y",d.at[i,"yahoo_strict_cagr_7y"],"yahoo_strict_cagr_7y")
    fill_blank(i,"current_cagr_10y",d.at[i,"yahoo_strict_cagr_10y"],"yahoo_strict_cagr_10y")
    fill_blank(i,"latest_price",d.at[i,"yahoo_latest_raw_close"],"yahoo_latest_raw_close")
    fill_blank(i,"high",d.at[i,"yahoo_latest_raw_high"],"yahoo_latest_raw_high")
    fill_blank(i,"low",d.at[i,"yahoo_latest_raw_low"],"yahoo_latest_raw_low")
    fill_blank(i,"volume",d.at[i,"yahoo_latest_volume"],"yahoo_latest_volume")
    if "history_price_basis" in d.columns and pd.isna(d.at[i,"history_price_basis"]):
        d.at[i,"history_price_basis"]="Yahoo adjusted close via current research recovery"
        ledger.append({"row":int(i),"isin":d.at[i,"isin"],"ticker":d.at[i,"ticker"],
                       "field":"history_price_basis","value":"Yahoo adjusted close via current research recovery",
                       "source":"YAHOO_FINANCE_FULL_HISTORY_2026-10-03",
                       "source_column":"yahoo_symbol","yahoo_symbol":d.at[i,"yahoo_symbol"]})
# Small current metadata pass only for generic market-cap/share-count gaps.
fastinfo_log=[]
for i in d.index[(d["market_cap"].isna()) | (d["shares_outstanding"].isna())]:
    sym=d.at[i,"yahoo_symbol"] if "yahoo_symbol" in d.columns else None
    if pd.isna(sym) or not str(sym).strip(): continue
    try:
        fi=yf.Ticker(str(sym)).fast_info
        def fget(key):
            try: return fi.get(key)
            except Exception:
                try: return getattr(fi,key)
                except Exception: return None
        mc=fget("market_cap")
        shares=fget("shares")
        last=fget("last_price")
        if mc is not None and np.isfinite(float(mc)):
            fill_blank(i,"market_cap",float(mc),"yahoo_fast_info.market_cap")
        if shares is not None and np.isfinite(float(shares)):
            fill_blank(i,"shares_outstanding",float(shares),"yahoo_fast_info.shares")
        fastinfo_log.append({"row":int(i),"ticker":d.at[i,"ticker"],"yahoo_symbol":sym,
                             "market_cap":mc,"shares":shares,"last_price":last,"status":"OK"})
    except Exception as e:
        fastinfo_log.append({"row":int(i),"ticker":d.at[i,"ticker"],"yahoo_symbol":sym,
                             "status":"ERROR","error":str(e)[:200]})
    time.sleep(0.15)
pd.DataFrame(fastinfo_log).to_csv(DIR/"yahoo_fastinfo_gap_attempts.csv",index=False)

# Mark product-growth provenance when Yahoo supplied the formerly blank value.
for item in ledger:
    field=item["field"]; i=item["row"]
    srcfield={
        "product_baseline_yoy_growth":"product_baseline_yoy_growth_source",
        "product_baseline_cagr_3y":"product_baseline_cagr_3y_source",
        "product_baseline_cagr_5y":"product_baseline_cagr_5y_source",
        "product_baseline_days_since_recorded_high":"product_baseline_days_since_recorded_high_source",
        "current_cagr_7y":"current_cagr_7y_source",
        "current_cagr_10y":"current_cagr_10y_source",
    }.get(field)
    if srcfield:
        if srcfield not in d.columns:
            d[srcfield]=pd.Series([None]*len(d),dtype="object")
        if pd.isna(d.at[i,srcfield]):
            d.at[i,srcfield]="YAHOO_FINANCE_FULL_HISTORY"

# A latest raw Yahoo close can supply its corresponding trade date when price was absent.
if "trade_date" in d.columns:
    for i in d.index:
        if pd.isna(d.at[i,"trade_date"]) and d.at[i,"yahoo_status"]=="OK":
            d.at[i,"trade_date"]=d.at[i,"yahoo_history_end_date"]
            ledger.append({"row":int(i),"isin":d.at[i,"isin"],"ticker":d.at[i,"ticker"],
                           "field":"trade_date","value":d.at[i,"yahoo_history_end_date"],
                           "source":"YAHOO_FINANCE_FULL_HISTORY_2026-10-03",
                           "source_column":"yahoo_history_end_date","yahoo_symbol":d.at[i,"yahoo_symbol"]})
# Model-ready current aliases; all are explicitly current-only Yahoo-derived features.
ALIASES={
"current_history_months":"yahoo_history_months",
"current_distance_from_recorded_high":"yahoo_distance_from_recorded_high",
"current_distance_from_52w_high":"yahoo_distance_from_52w_high",
"current_full_history_max_drawdown":"yahoo_full_history_max_drawdown",
"current_drawdown_duration_days":"yahoo_current_drawdown_duration_days",
"current_max_drawdown_duration_days":"yahoo_max_drawdown_duration_days",
"current_recovery_from_worst_trough":"yahoo_recovery_from_worst_trough",
"current_realized_volatility_1y":"yahoo_realized_volatility_1y",
"current_downside_volatility_1y":"yahoo_downside_volatility_1y",
"current_beta_1y_vs_nifty50":"yahoo_beta_1y_vs_nifty50",
}
for target,src in ALIASES.items():
    if target not in d.columns:
        d[target]=d[src]
    else:
        mask=d[target].isna()
        d.loc[mask,target]=d.loc[mask,src]

for years,src in [(1,"yahoo_strict_cagr_1y"),(3,"yahoo_strict_cagr_3y"),
                  (5,"yahoo_strict_cagr_5y"),(7,"yahoo_strict_cagr_7y"),
                  (10,"yahoo_strict_cagr_10y")]:
    target=f"current_has_true_{years}y"
    d[target]=pd.to_numeric(d[src],errors="coerce").notna()

# Integrity audit: every pre-existing nonblank V6 value must remain bitwise/numerically equivalent.
for col in orig.columns:
    if col not in d.columns:
        raise RuntimeError("column disappeared: "+col)
    mask=orig[col].notna()
    if not mask.any(): continue
    a=orig.loc[mask,col]; b=d.loc[mask,col]
    if pd.api.types.is_numeric_dtype(a):
        av=pd.to_numeric(a,errors="coerce").to_numpy(float)
        bv=pd.to_numeric(b,errors="coerce").to_numpy(float)
        if not np.allclose(av,bv,rtol=0,atol=1e-12,equal_nan=True):
            raise RuntimeError("existing trusted numeric value changed: "+col)
    else:
        if not a.astype(str).reset_index(drop=True).equals(b.astype(str).reset_index(drop=True)):
            raise RuntimeError("existing trusted text value changed: "+col)
core=[
"product_baseline_yoy_growth","product_baseline_cagr_3y","product_baseline_cagr_5y",
"current_cagr_7y","current_cagr_10y","high_52w","low_52w","recorded_high",
"recorded_high_date","product_baseline_days_since_recorded_high",
"current_history_months","current_distance_from_recorded_high",
"current_full_history_max_drawdown","current_drawdown_duration_days",
"current_downside_volatility_1y","current_realized_volatility_1y",
]
before={c:int(orig[c].isna().sum()) if c in orig.columns else len(orig) for c in core}
after={c:int(d[c].isna().sum()) for c in core}

reason={}
for field,years in [
    ("product_baseline_yoy_growth",1),("product_baseline_cagr_3y",3),
    ("product_baseline_cagr_5y",5),("current_cagr_7y",7),("current_cagr_10y",10)
]:
    miss=d[field].isna()
    hm=pd.to_numeric(d["yahoo_history_months"],errors="coerce")
    reason[field]={
        "missing":int(miss.sum()),
        "no_usable_yahoo_history":int((miss & d["yahoo_status"].ne("OK")).sum()),
        "yahoo_history_shorter_than_horizon":int((miss & hm.notna() & hm.lt(years*12-1)).sum()),
        "history_long_enough_but_strict_anchor_unavailable_or_other":int((miss & hm.notna() & hm.ge(years*12-1)).sum()),
    }

unresolved=d.loc[d["yahoo_status"].ne("OK"),
                 [c for c in ["ticker","company","isin","primary_exchange",
                              "bulk_classification_provider_symbol","screener_nse_code","screener_bse_code",
                              "yahoo_status"] if c in d.columns]].copy()
unresolved.to_csv(DIR/"yahoo_full_unresolved_rows.csv",index=False)

remaining=d.loc[d[core].isna().any(axis=1),
                [c for c in ["ticker","company","isin","yahoo_symbol","yahoo_status"]+core if c in d.columns]].copy()
remaining.to_csv(DIR/"yahoo_full_remaining_core_gaps.csv",index=False)

pd.DataFrame(ledger).to_csv(DIR/"yahoo_full_filled_cells.csv",index=False)
d.to_csv(OUT,index=False,compression="gzip")

summary={
"schema":"yahoo_full_current_recovery_v1",
"cutoff":CUTOFF.date().isoformat(),
"source":"Yahoo Finance via yfinance",
"current_rows":int(len(d)),
"rows_with_usable_yahoo_history":int(d["yahoo_status"].eq("OK").sum()),
"rows_without_usable_yahoo_history":int(d["yahoo_status"].ne("OK").sum()),
"filled_existing_blank_cells":int(len(ledger)),
"stocks_with_existing_blank_fills":int(pd.DataFrame(ledger)["ticker"].nunique()) if ledger else 0,
"new_yahoo_metric_columns":int(len([c for c in d.columns if c.startswith("yahoo_")])),
"missing_before":before,
"missing_after":after,
"remaining_reason_counts":reason,
"existing_nonblank_overwritten":0,
"historical_training_modified":False,
"production_modified":False,
}
(DIR/"yahoo_full_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")

sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest={}
for p in [OUT,METRICS,DIR/"yahoo_full_filled_cells.csv",
          DIR/"yahoo_full_unresolved_rows.csv",DIR/"yahoo_full_remaining_core_gaps.csv",
          DIR/"yahoo_fastinfo_gap_attempts.csv",DIR/"yahoo_full_summary.json"]:
    if p.exists():
        manifest[p.name]={"bytes":p.stat().st_size,"sha256":sha(p)}
(DIR/"yahoo_full_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")

print(json.dumps(summary,indent=2),flush=True)
print("OUTPUT",OUT,flush=True)
