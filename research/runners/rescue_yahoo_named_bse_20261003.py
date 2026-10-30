from __future__ import annotations
from pathlib import Path
import hashlib, json, re, time
from difflib import SequenceMatcher
import numpy as np
import pandas as pd
import yfinance as yf

from stock_ranker.history_enrichment import compute_history_metrics

ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"experiments/current-data-recovery-20261003"
IN=DIR/"current_company_facts_recovered_v7_yahoo_full.csv.gz"
OUT=DIR/"current_company_facts_recovered_v8_yahoo_rescued.csv.gz"
CUTOFF=pd.Timestamp("2026-10-03")

d=pd.read_csv(IN,low_memory=False)
orig=d.copy(deep=True)
unresolved=d.index[d["yahoo_status"].ne("OK")].tolist()
print("UNRESOLVED_START",len(unresolved),flush=True)

STOP={"LIMITED","LTD","PRIVATE","PVT","COMPANY","CO","THE","INDIA","INDIAN","CORPORATION","CORP"}

def norm_name(s):
    s=re.sub(r"[^A-Z0-9 ]+"," ",str(s).upper())
    toks=[x for x in s.split() if x and x not in STOP]
    return " ".join(toks)

def name_score(a,b):
    a=norm_name(a); b=norm_name(b)
    if not a or not b: return 0.0
    seq=SequenceMatcher(None,a,b).ratio()
    sa=set(a.split()); sb=set(b.split())
    jac=len(sa&sb)/max(1,len(sa|sb))
    contain=1.0 if (a in b or b in a) and min(len(a),len(b))>=5 else 0.0
    return max(seq,jac,contain)

def fin(v):
    try:
        x=float(v)
        return x if np.isfinite(x) else None
    except Exception:
        return None

def fast_price(sym):
    try:
        fi=yf.Ticker(sym).fast_info
        for key in ["last_price","lastPrice"]:
            try:
                v=fi.get(key)
            except Exception:
                try: v=getattr(fi,key)
                except Exception: v=None
            x=fin(v)
            if x is not None and x>0: return x
    except Exception:
        return None
    return None
search_log=[]
accepted={}
for n,i in enumerate(unresolved,1):
    row=d.loc[i]
    queries=[]
    for qv in [row.get("company"),row.get("screener_company_name")]:
        qv=str(qv).strip() if pd.notna(qv) else ""
        if qv and qv.lower()!="nan" and qv not in queries:
            queries.append(qv)
    candidates={}
    for query in queries[:2]:
        try:
            res=yf.Search(query,max_results=8,news_count=0)
            for q in res.quotes:
                sym=str(q.get("symbol") or "")
                if not sym.endswith(".BO"): continue
                if str(q.get("exchange") or "").upper()!="BSE": continue
                if str(q.get("quoteType") or "").upper()!="EQUITY": continue
                longn=q.get("longname") or ""
                shortn=q.get("shortname") or ""
                sc=max(name_score(row.get("company"),longn),name_score(row.get("company"),shortn),
                       name_score(row.get("screener_company_name"),longn),name_score(row.get("screener_company_name"),shortn))
                prev=candidates.get(sym)
                if prev is None or sc>prev["name_score"]:
                    candidates[sym]={"name_score":sc,"longname":longn,"shortname":shortn}
        except Exception as e:
            search_log.append({"row":int(i),"ticker":row.get("ticker"),"query":query,
                               "status":"SEARCH_ERROR","error":str(e)[:160]})
        time.sleep(0.08)

    screened=[]
    source_price=fin(row.get("screener_current_price"))
    for sym,meta in sorted(candidates.items(),key=lambda kv:kv[1]["name_score"],reverse=True)[:3]:
        if meta["name_score"]<0.62: continue
        yp=fast_price(sym)
        pdiff=(abs(yp/source_price-1.0) if yp and source_price and source_price>0 else None)
        exact_isin=False
        accept=(
            meta["name_score"]>=0.82 and pdiff is not None and pdiff<=0.05
        ) or (
            meta["name_score"]>=0.97 and pdiff is None
        )
        screened.append({**meta,"symbol":sym,"yahoo_price":yp,"screener_price":source_price,
                         "price_diff":pdiff,"yahoo_isin":None,"exact_isin":False,"accept":accept})
        time.sleep(0.05)

    good=[x for x in screened if x["accept"]]
    good.sort(key=lambda x:(not x["exact_isin"],-x["name_score"],x["price_diff"] if x["price_diff"] is not None else 9))
    chosen=None
    if good:
        if len(good)==1:
            chosen=good[0]
        else:
            a,b=good[0],good[1]
            if a["exact_isin"] or a["name_score"]-b["name_score"]>=0.04 or (
                a["price_diff"] is not None and b["price_diff"] is not None and b["price_diff"]-a["price_diff"]>=0.02
            ):
                chosen=a
    if chosen:
        accepted[i]=chosen
    search_log.append({"row":int(i),"ticker":row.get("ticker"),"company":row.get("company"),
                       "status":"ACCEPTED_SYMBOL" if chosen else "NO_VERIFIED_ALTERNATE",
                       "chosen_symbol":chosen["symbol"] if chosen else None,
                       "name_score":chosen["name_score"] if chosen else None,
                       "price_diff":chosen["price_diff"] if chosen else None,
                       "exact_isin":chosen["exact_isin"] if chosen else None,
                       "candidate_count":len(candidates),"screened":json.dumps(screened,default=str)})
    if n%25==0:
        print("SEARCH",n,"/",len(unresolved),"accepted",len(accepted),flush=True)
pd.DataFrame(search_log).to_csv(DIR/"yahoo_named_bse_search_audit.csv",index=False)
print("VERIFIED_ALTERNATES",len(accepted),flush=True)
def strict_cagr(s,years):
    s=s.dropna().sort_index()
    if len(s)<2: return np.nan
    anchor=CUTOFF-pd.DateOffset(years=years)
    before=s.loc[s.index<=anchor]
    if before.empty: return np.nan
    d0=before.index[-1].normalize()
    if not 0 <= (anchor-d0).days <= 7: return np.nan
    d1=s.index[-1].normalize(); span=(d1-d0).days
    if span<=0: return np.nan
    p0=float(before.iloc[-1]); p1=float(s.iloc[-1])
    if p0<=0 or p1<=0: return np.nan
    return float(np.expm1(np.log(p1/p0)*365.0/span))

try:
    nr=yf.download("^NSEI",start="2025-09-20",end="2026-10-04",auto_adjust=False,
                   actions=False,progress=False,threads=False,timeout=25)
    ncol="Adj Close" if "Adj Close" in nr.columns else "Close"
    nifty=pd.to_numeric(nr[ncol],errors="coerce").dropna()
    if isinstance(nifty,pd.DataFrame): nifty=nifty.iloc[:,0]
    nifty.index=pd.to_datetime(nifty.index).tz_localize(None)
    nifty_ret=np.log(nifty).diff().dropna()
except Exception:
    nifty_ret=pd.Series(dtype=float)

rescue_metrics=[]
for count,(i,choice) in enumerate(accepted.items(),1):
    sym=choice["symbol"]
    row=d.loc[i]
    try:
        f=yf.Ticker(sym).history(period="max",auto_adjust=False,actions=False)
        if f is None or f.empty:
            raise ValueError("empty max history")
        f=f.copy()
        f.index=pd.to_datetime(f.index).tz_localize(None)
        acol="Adj Close" if "Adj Close" in f.columns else "Close"
        adj=pd.to_numeric(f[acol],errors="coerce").dropna()
        adj=adj.loc[(adj.index<=CUTOFF)&(adj>0)].sort_index()
        if len(adj)<2:
            raise ValueError("fewer than two adjusted observations")
        frame=pd.DataFrame({"date":adj.index,"price":adj.values})
        m=compute_history_metrics(frame,cutoff=CUTOFF,listing_date=row.get("listing_date"))
        year=adj.loc[adj.index>=CUTOFF-pd.Timedelta(days=365)]
        raw_close=pd.to_numeric(f["Close"],errors="coerce").dropna() if "Close" in f else pd.Series(dtype=float)
        raw_high=pd.to_numeric(f["High"],errors="coerce").dropna() if "High" in f else pd.Series(dtype=float)
        raw_low=pd.to_numeric(f["Low"],errors="coerce").dropna() if "Low" in f else pd.Series(dtype=float)
        raw_vol=pd.to_numeric(f["Volume"],errors="coerce").dropna() if "Volume" in f else pd.Series(dtype=float)
        for s in [raw_close,raw_high,raw_low,raw_vol]:
            s.index=pd.to_datetime(s.index).tz_localize(None)
        sr=np.log(adj.loc[adj.index>=CUTOFF-pd.Timedelta(days=365)]).diff().dropna()
        z=pd.concat([sr.rename("s"),nifty_ret.rename("m")],axis=1,join="inner").dropna()
        beta=np.nan
        if len(z)>=60 and float(z["m"].var(ddof=1))>0:
            beta=float(z["s"].cov(z["m"])/z["m"].var(ddof=1))
        rescue_metrics.append({
            "row":int(i),"status":"OK","symbol":sym,
            "history_start_date":m["history_start_date"],"history_end_date":m["history_end_date"],
            "history_observation_count":m["history_observation_count"],"history_months":m["history_months"],
            "terminal_lag_days":m["terminal_lag_days"],
            "strict_cagr_1y":m["strict_cagr_1y"],"strict_cagr_3y":m["strict_cagr_3y"],
            "strict_cagr_5y":m["strict_cagr_5y"],"strict_cagr_7y":strict_cagr(adj,7),
            "strict_cagr_10y":strict_cagr(adj,10),
            "recorded_high_price":m["recorded_high_price"],"recorded_high_date":m["recorded_high_date"],
            "days_since_recorded_high":m["days_since_recorded_high"],
            "distance_from_recorded_high":m["distance_from_recorded_high"],
            "distance_from_52w_high":m["distance_from_52w_high"],
            "high_52w":float(year.max()),"high_52w_date":year.idxmax().date().isoformat(),
            "low_52w":float(year.min()),"low_52w_date":year.idxmin().date().isoformat(),
            "full_history_max_drawdown":m["full_history_max_drawdown"],
            "current_drawdown_duration_days":m["current_drawdown_duration_days"],
            "max_drawdown_duration_days":m["max_drawdown_duration_days"],
            "recovery_from_worst_trough":m["recovery_from_worst_trough"],
            "realized_volatility_1y":m["realized_volatility_1y"],
            "downside_volatility_1y":m["downside_volatility_1y"],
            "beta_1y_vs_nifty50":beta,
            "latest_raw_close":float(raw_close.loc[raw_close.index<=CUTOFF].iloc[-1]) if len(raw_close.loc[raw_close.index<=CUTOFF]) else np.nan,
            "latest_raw_high":float(raw_high.loc[raw_high.index<=CUTOFF].iloc[-1]) if len(raw_high.loc[raw_high.index<=CUTOFF]) else np.nan,
            "latest_raw_low":float(raw_low.loc[raw_low.index<=CUTOFF].iloc[-1]) if len(raw_low.loc[raw_low.index<=CUTOFF]) else np.nan,
            "latest_volume":float(raw_vol.loc[raw_vol.index<=CUTOFF].iloc[-1]) if len(raw_vol.loc[raw_vol.index<=CUTOFF]) else np.nan,
        })
    except Exception as e:
        rescue_metrics.append({"row":int(i),"status":"NO_USABLE_HISTORY","symbol":sym,"error":str(e)[:200]})
    if count%20==0:
        print("HISTORY",count,"/",len(accepted),flush=True)
    time.sleep(0.08)

rm=pd.DataFrame(rescue_metrics)
rm.to_csv(DIR/"yahoo_named_bse_rescue_metrics.csv",index=False)
print("RESCUE_HISTORY_OK",int(rm["status"].eq("OK").sum()) if len(rm) else 0,flush=True)
ledger=[]
okrm=rm.loc[rm["status"].eq("OK")].set_index("row") if len(rm) else pd.DataFrame()

def fill_blank(i,target,value,source_col):
    if target not in d.columns or pd.notna(d.at[i,target]) or pd.isna(value):
        return
    d.at[i,target]=value
    ledger.append({"row":int(i),"isin":d.at[i,"isin"],"ticker":d.at[i,"ticker"],
                   "field":target,"value":value,
                   "source":"YAHOO_FINANCE_NAMED_BSE_RESCUE_2026-10-03",
                   "source_column":source_col,"yahoo_symbol":d.at[i,"yahoo_symbol"]})

for i in okrm.index:
    r=okrm.loc[i]
    d.at[i,"yahoo_status"]="OK"
    d.at[i,"yahoo_symbol"]=r["symbol"]
    d.at[i,"yahoo_symbol_method"]="YAHOO_SEARCH_NAME_PRICE_VERIFIED_BSE"
    d.at[i,"yahoo_history_start_date"]=r["history_start_date"]
    d.at[i,"yahoo_history_end_date"]=r["history_end_date"]
    d.at[i,"yahoo_history_observation_count"]=r["history_observation_count"]
    d.at[i,"yahoo_history_months"]=r["history_months"]
    d.at[i,"yahoo_terminal_lag_days"]=r["terminal_lag_days"]
    for yrs in [1,3,5,7,10]:
        d.at[i,f"yahoo_strict_cagr_{yrs}y"]=r[f"strict_cagr_{yrs}y"]
    d.at[i,"yahoo_recorded_high_price"]=r["recorded_high_price"]
    d.at[i,"yahoo_recorded_high_date"]=r["recorded_high_date"]
    d.at[i,"yahoo_days_since_recorded_high"]=r["days_since_recorded_high"]
    d.at[i,"yahoo_distance_from_recorded_high"]=r["distance_from_recorded_high"]
    d.at[i,"yahoo_distance_from_52w_high"]=r["distance_from_52w_high"]
    d.at[i,"yahoo_high_52w"]=r["high_52w"]
    d.at[i,"yahoo_high_52w_date"]=r["high_52w_date"]
    d.at[i,"yahoo_low_52w"]=r["low_52w"]
    d.at[i,"yahoo_low_52w_date"]=r["low_52w_date"]
    d.at[i,"yahoo_full_history_max_drawdown"]=r["full_history_max_drawdown"]
    d.at[i,"yahoo_current_drawdown_duration_days"]=r["current_drawdown_duration_days"]
    d.at[i,"yahoo_max_drawdown_duration_days"]=r["max_drawdown_duration_days"]
    d.at[i,"yahoo_recovery_from_worst_trough"]=r["recovery_from_worst_trough"]
    d.at[i,"yahoo_realized_volatility_1y"]=r["realized_volatility_1y"]
    d.at[i,"yahoo_downside_volatility_1y"]=r["downside_volatility_1y"]
    d.at[i,"yahoo_beta_1y_vs_nifty50"]=r["beta_1y_vs_nifty50"]
    d.at[i,"yahoo_latest_raw_close"]=r["latest_raw_close"]
    d.at[i,"yahoo_latest_raw_high"]=r["latest_raw_high"]
    d.at[i,"yahoo_latest_raw_low"]=r["latest_raw_low"]
    d.at[i,"yahoo_latest_volume"]=r["latest_volume"]

    fill_blank(i,"history_start_date",r["history_start_date"],"history_start_date")
    fill_blank(i,"history_end_date",r["history_end_date"],"history_end_date")
    fill_blank(i,"history_observation_count",r["history_observation_count"],"history_observation_count")
    fill_blank(i,"high_52w",r["high_52w"],"high_52w")
    fill_blank(i,"high_52w_date",r["high_52w_date"],"high_52w_date")
    fill_blank(i,"low_52w",r["low_52w"],"low_52w")
    fill_blank(i,"low_52w_date",r["low_52w_date"],"low_52w_date")
    fill_blank(i,"recorded_high",r["recorded_high_price"],"recorded_high_price")
    fill_blank(i,"recorded_high_date",r["recorded_high_date"],"recorded_high_date")
    fill_blank(i,"product_baseline_yoy_growth",r["strict_cagr_1y"],"strict_cagr_1y")
    fill_blank(i,"product_baseline_cagr_3y",r["strict_cagr_3y"],"strict_cagr_3y")
    fill_blank(i,"product_baseline_cagr_5y",r["strict_cagr_5y"],"strict_cagr_5y")
    fill_blank(i,"current_cagr_7y",r["strict_cagr_7y"],"strict_cagr_7y")
    fill_blank(i,"current_cagr_10y",r["strict_cagr_10y"],"strict_cagr_10y")
    fill_blank(i,"product_baseline_days_since_recorded_high",r["days_since_recorded_high"],"days_since_recorded_high")
    fill_blank(i,"latest_price",r["latest_raw_close"],"latest_raw_close")
    fill_blank(i,"high",r["latest_raw_high"],"latest_raw_high")
    fill_blank(i,"low",r["latest_raw_low"],"latest_raw_low")
    fill_blank(i,"volume",r["latest_volume"],"latest_volume")
    if "history_price_basis" in d.columns and pd.isna(d.at[i,"history_price_basis"]):
        d.at[i,"history_price_basis"]="Yahoo adjusted close via named BSE rescue"
# Refresh model-ready aliases and horizon flags for rescued rows.
for i in okrm.index:
    mapping={
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
    for target,src in mapping.items():
        if target not in d.columns: d[target]=np.nan
        if pd.isna(d.at[i,target]): d.at[i,target]=d.at[i,src]

for yrs in [1,3,5,7,10]:
    target=f"current_has_true_{yrs}y"
    d[target]=pd.to_numeric(d[f"yahoo_strict_cagr_{yrs}y"],errors="coerce").notna()

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
            d.at[i,srcfield]="YAHOO_FINANCE_NAMED_BSE_RESCUE"

# Preserve all pre-existing non-Yahoo, non-current-model values from V7.
for col in orig.columns:
    if col.startswith("yahoo_") or col.startswith("current_"):
        continue
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
before={c:int(orig[c].isna().sum()) for c in core}
after={c:int(d[c].isna().sum()) for c in core}

pd.DataFrame(ledger).to_csv(DIR/"yahoo_named_bse_rescue_filled_cells.csv",index=False)
d.to_csv(OUT,index=False,compression="gzip")

remaining=d.loc[d["yahoo_status"].ne("OK"),
                [c for c in ["ticker","company","isin","primary_exchange",
                             "screener_current_price","screener_all_time_high_price",
                             "yahoo_symbol","yahoo_status"] if c in d.columns]].copy()
remaining.to_csv(DIR/"yahoo_final_unresolved_rows.csv",index=False)

summary={
    "schema":"yahoo_named_bse_rescue_v1",
    "unresolved_before":int(len(unresolved)),
    "verified_alternate_symbols":int(len(accepted)),
    "verified_alternates_with_usable_history":int(len(okrm)),
    "unresolved_after":int(d["yahoo_status"].ne("OK").sum()),
    "additional_existing_blank_cells_filled":int(len(ledger)),
    "additional_stocks_with_blank_fills":int(pd.DataFrame(ledger)["ticker"].nunique()) if ledger else 0,
    "usable_yahoo_history_final":int(d["yahoo_status"].eq("OK").sum()),
    "current_rows":int(len(d)),
    "missing_before":before,
    "missing_after":after,
    "existing_non_yahoo_nonblank_overwritten":0,
    "historical_training_modified":False,
    "production_modified":False,
}
(DIR/"yahoo_named_bse_rescue_summary.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")

sha=lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
manifest={}
for p in [OUT,DIR/"yahoo_named_bse_search_audit.csv",DIR/"yahoo_named_bse_rescue_metrics.csv",
          DIR/"yahoo_named_bse_rescue_filled_cells.csv",DIR/"yahoo_final_unresolved_rows.csv",
          DIR/"yahoo_named_bse_rescue_summary.json"]:
    if p.exists():
        manifest[p.name]={"bytes":p.stat().st_size,"sha256":sha(p)}
(DIR/"yahoo_named_bse_rescue_manifest.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2),flush=True)
print("OUTPUT",OUT,flush=True)
