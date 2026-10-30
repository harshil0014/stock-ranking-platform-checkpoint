"""Second V13 development-only family: smooth sub-5Y confidence penalty."""
from pathlib import Path
import json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import pandas as pd
from research.runners import personalized_deeper_championship_v2 as d
from research.runners import personalized_successor_20261002 as prior

OUT=ROOT/"experiments/personalized-v13-20261002"
V12=d.OUT
HISTORY=(.02,.04,.06,.08)
DOWNSIDE=(.15,.20)
WEEKLY=(.05,.10,.15)

def neutral(frame,name):
    x=frame[name]
    return x.fillna(x.groupby(frame.decision_date).transform("median")).fillna(x.median())

def score(frame,h,v,w):
    missing=frame.cagr_5y_observed.ne(1).astype(float)
    gap=(1-frame.history_months.fillna(0).div(60).clip(0,1)).clip(0,1)*missing
    smooth=gap.pow(.5)
    downside=neutral(frame,"downside_volatility_1y").clip(0,2).div(2)
    weekly=frame.profile_name.eq("weekly").astype(float)
    return frame.champion_score-h*smooth-v*downside-w*weekly*downside

def prof_delta(new,base,p):
    j=base.loc[base.profile.eq(p)].merge(new.loc[new.profile.eq(p)],on=["decision_date","profile"],suffixes=("_old","_new"))
    def q(n): return float((j[f"{n}_new"]-j[f"{n}_old"]).mean())
    return {f"{p}_shortfall_delta":q("target_shortfall_top20"),
            f"{p}_achievement_delta":q("target_achievement_top20"),
            f"{p}_drawdown_delta":q("mean_asset_drawdown_top20")}

def current():
    v3=pd.read_csv(d.V3,low_memory=False)
    frozen=pd.read_csv(d.hist.FREEZE/"rankings.csv.gz",low_memory=False)
    cur=frozen.drop(columns=["cagr_5y"]).merge(prior.current_features(v3),on=["isin","decision_date"],how="left",validate="many_to_one")
    cur["champion_score"]=cur.selected_ensemble_score
    return cur

def missing(cur,h,v,w):
    x=cur.copy(); x["v13_score"]=score(x,h,v,w)
    x=x.loc[x.profile_name.eq("base7500")].dropna(subset=["v13_score"]).sort_values(["v13_score","isin"],ascending=[False,True])
    return {"current_top20_missing_true_5y":float(x.head(20).cagr_5y_observed.ne(1).mean()),
            "current_top50_missing_true_5y":float(x.head(50).cagr_5y_observed.ne(1).mean()),
            "current_top100_missing_true_5y":float(x.head(100).cagr_5y_observed.ne(1).mean())}

def main():
    b=pd.read_pickle(V12/"development_baseline.pkl.gz",compression="gzip")
    if pd.to_datetime(b.decision_date).max()>=pd.Timestamp("2024-01-01"): raise ValueError("post-development outcome in selection")
    ref=d.hist.evaluate(b,"champion_score")
    cur=current(); rows=[]
    for h in HISTORY:
      for v in DOWNSIDE:
       for w in WEEKLY:
        b["v13_score"]=score(b,h,v,w)
        m=d.hist.evaluate(b,"v13_score")
        r={"history_sqrt_coefficient":h,"downside_coefficient":v,"weekly_extra_downside":w,
           **d.metric_deltas(m,ref),**prof_delta(m,ref,"weekly"),**prof_delta(m,ref,"lookback60"),**missing(cur,h,v,w)}
        r["v13_gate"]=bool(r["eligible"] and r["utility"]>0 and r["weekly_shortfall_delta"]<=0 and r["weekly_drawdown_delta"]>=0 and r["weekly_achievement_delta"]>=-.02 and r["lookback60_shortfall_delta"]<=.005 and r["lookback60_drawdown_delta"]>=-.01 and r["lookback60_achievement_delta"]>=-.05 and r["current_top20_missing_true_5y"]<=.50 and r["current_top50_missing_true_5y"]<=.35)
        rows.append(r); print(json.dumps({"h":h,"v":v,"w":w,"utility":r["utility"],"gate":r["v13_gate"],"top20":r["current_top20_missing_true_5y"],"weekly_short":r["weekly_shortfall_delta"]}),flush=True)
    t=pd.DataFrame(rows).sort_values(["v13_gate","utility"],ascending=[False,False]); t.to_csv(OUT/"smooth_development_search.csv",index=False)
    p=t.loc[t.v13_gate]
    summary={"schema":"personalized_v13_smooth_search_v1","candidate_count":len(t),"passing_count":len(p),"post_2023_outcomes_loaded":False}
    if len(p): summary["winner"]=p.iloc[0].to_dict()
    (OUT/"smooth_summary.json").write_text(json.dumps(summary,indent=2,default=str)+"\n")
    print(json.dumps({"passing":len(p),"winner":summary.get("winner")},indent=2,default=str))
if __name__=="__main__": main()
