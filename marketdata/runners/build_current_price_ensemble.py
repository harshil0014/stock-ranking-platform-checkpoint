"""Fit the frozen selected ensemble and emit current outcome-blind rankings."""
from __future__ import annotations
import argparse,json,os
from hashlib import sha256
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/"src"))
CONTROLS={"PYTHONHASHSEED":"20260730","OMP_NUM_THREADS":"1","OPENBLAS_NUM_THREADS":"1","MKL_NUM_THREADS":"1","NUMEXPR_NUM_THREADS":"1"}
if {name:os.environ.get(name) for name in CONTROLS} != CONTROLS:
    raise RuntimeError("deterministic subprocess controls must be set before interpreter startup")
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.preprocessing import StandardScaler
from stock_ranker.company_facts import load_company_fact_snapshot,resolve_company_fact_snapshot

CORE=["mom12_1","mom6_1","reversal1m","low_vol_6m","low_vol_12m","shallow_drawdown_12m","distance_52w_high","trend_consistency_12m"]
def _hash(p):return sha256(Path(p).read_bytes()).hexdigest()
def _idx(dates,target,tolerance=20):
    i=int(np.searchsorted(dates,np.datetime64(pd.Timestamp(target).to_datetime64()),side="right")-1)
    return i if i>=0 and (pd.Timestamp(target)-pd.Timestamp(dates[i])).days<=tolerance else None
def run(source:Path,prospective:Path,state_root:Path,histories:Path,output:Path):
    if output.exists():raise ValueError("fresh output required")
    source_summary=json.loads((source/"summary.json").read_text()); selected=source_summary["selected_before_locked_test"]
    if selected != ["ridge","price_multifactor_signal"]:raise ValueError("unexpected frozen model selection")
    accepted=json.loads((state_root/"accepted_state.json").read_text()); decision=pd.Timestamp(accepted["trade_date"])
    panel=pd.read_csv(source/"panel.csv"); train=panel.loc[pd.to_datetime(panel.endpoint_12m).lt(decision)&panel[CORE].notna().all(axis=1)].copy()
    scaler=StandardScaler().fit(train[CORE]); ridge=Ridge(alpha=10.0).fit(scaler.transform(train[CORE]),train.target)
    frozen=pd.read_csv(prospective/"frozen_signals.csv"); facts=load_company_fact_snapshot(resolve_company_fact_snapshot(state_root)).facts[["ticker","isin","company","product_sector"]]
    current=frozen.merge(facts,on=["ticker","isin","company"],validate="one_to_one")
    current=current.loc[current.product_sector.notna()].copy(); rows=[]; hashes={}
    for item in current.sort_values("ticker",kind="stable").itertuples(index=False):
        path=histories/f"{item.ticker}.csv"
        try:
            raw=path.read_bytes();h=pd.read_csv(path,usecols=["date","adjusted_close"]);h.date=pd.to_datetime(h.date);h=h.dropna().sort_values("date").drop_duplicates("date",keep=False)
            dates=h.date.to_numpy(dtype="datetime64[ns]");prices=h.adjusted_close.to_numpy(float);now=_idx(dates,decision);a6=_idx(dates,decision-pd.DateOffset(months=6));a12=_idx(dates,decision-pd.DateOffset(months=12))
            if None in (now,a6,a12):continue
            w6=prices[a6:now+1];w12=prices[a12:now+1];monthly=[]
            for m in range(12,-1,-1):
                x=_idx(dates,decision-pd.DateOffset(months=m));
                if x is not None:monthly.append(prices[x])
            if len(monthly)<10 or len(w6)<3:continue
            values={"mom12_1":item.mom12m,"mom6_1":item.mom6m,"reversal1m":item.reversal1m,
              "low_vol_6m":-float(np.std(np.diff(w6)/w6[:-1],ddof=1)*np.sqrt(252)),"low_vol_12m":item.low_volatility_12m,
              "shallow_drawdown_12m":item.shallow_drawdown_12m,"distance_52w_high":float(prices[now]/w12.max()),
              "trend_consistency_12m":float((np.diff(monthly)/np.asarray(monthly[:-1])>0).mean())}
            if not np.isfinite(list(values.values())).all():continue
            rows.append({"as_of_date":accepted["trade_date"],"ticker":item.ticker,"isin":item.isin,"company":item.company,"sector":item.product_sector,**values});hashes[item.ticker]=sha256(raw).hexdigest()
        except Exception:continue
    result=pd.DataFrame(rows); result["ridge_prediction"]=ridge.predict(scaler.transform(result[CORE]))
    for c in CORE:result[c+"_pct"]=result.groupby("sector")[c].rank(pct=True)
    result["price_multifactor_signal"]=result[[c+"_pct" for c in CORE]].mean(axis=1)
    result["ridge_pct"]=result.groupby("sector").ridge_prediction.rank(pct=True);result["price_multifactor_pct"]=result.groupby("sector").price_multifactor_signal.rank(pct=True)
    result["ensemble_score"]=(result.ridge_pct+result.price_multifactor_pct)/2;result["ensemble_sector_rank"]=result.groupby("sector").ensemble_score.rank(ascending=False,method="min").astype(int)
    result=result.sort_values(["sector","ensemble_sector_rank","ticker"],kind="stable")
    output.mkdir(parents=True);result.to_csv(output/"rankings.csv",index=False,float_format="%.17g",lineterminator="\n")
    summary={"schema_version":"current_price_ensemble_v1","as_of_date":accepted["trade_date"],"ranked":len(result),"sectors":int(result.sector.nunique()),"training_rows":len(train),"latest_training_endpoint":str(pd.to_datetime(train.endpoint_12m).max().date()),"selected_models":selected,"deterministic_controls":CONTROLS,"product_default":"baseline_v1","product_default_changed":False,"outcomes_accessed_for_current_ranking":False,"research_status":"PROSPECTIVE_CANDIDATE","source_locked_test_fingerprint":json.loads((source/"manifest.json").read_text())["fingerprint"],"accepted_company_fingerprint":accepted["fingerprint"],"accepted_market_fingerprint":accepted["market_fingerprint"]}
    (output/"summary.json").write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8");(output/"provenance.json").write_text(json.dumps({"history_hashes":hashes},indent=2,sort_keys=True)+"\n",encoding="utf-8")
    artifacts=[{"path":p.name,"sha256":_hash(p),"size":p.stat().st_size} for p in sorted(output.iterdir())];fp=sha256(json.dumps(artifacts,sort_keys=True,separators=(",", ":")).encode()).hexdigest();(output/"manifest.json").write_text(json.dumps({"fingerprint":fp,"artifacts":artifacts},indent=2,sort_keys=True)+"\n",encoding="utf-8");return summary|{"fingerprint":fp}
def main():
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--prospective",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.source,a.prospective,ROOT/"data/company_facts",ROOT/"data/live_market/history_cache",a.output),sort_keys=True))
if __name__=="__main__":main()
