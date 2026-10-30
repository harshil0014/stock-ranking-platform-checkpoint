"""V13 development-only search for history concentration + weekly-risk repair.

Selection uses only the frozen V12 2020-2023 development baseline plus the
current 2026-09-18 structural missing-history concentration. It never loads
2024/2025 outcome files or the raw V12 panel.
"""
from __future__ import annotations
import hashlib, json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import numpy as np
import pandas as pd
from research.runners import personalized_deeper_championship_v2 as d
from research.runners import personalized_successor_20261002 as prior

V12=d.OUT
OUT=ROOT/"experiments/personalized-v13-20261002"
V3=d.V3

AGE=(.03,.05)
MISSING=(.01,.02,.04,.06)
DOWNSIDE=(.15,.20)
WEEKLY_EXTRA=(.05,.10,.15)

def sha(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()

def neutral(frame,name):
    x=frame[name]
    return x.fillna(x.groupby(frame.decision_date).transform("median")).fillna(x.median())

def signals(frame):
    missing=frame.cagr_5y_observed.ne(1).astype(float)
    age=(1-frame.history_months.fillna(0).div(60).clip(0,1))*missing
    downside=neutral(frame,"downside_volatility_1y").clip(0,2).div(2)
    weekly=frame.profile_name.eq("weekly").astype(float)
    return age,missing,downside,weekly

def score(frame,a,m,v,w):
    age,missing,downside,weekly=signals(frame)
    return frame.champion_score-a*age-m*missing-v*downside-w*weekly*downside
def profile_delta(new,base,profile):
    j=base.loc[base.profile.eq(profile)].merge(
        new.loc[new.profile.eq(profile)],on=["decision_date","profile"],suffixes=("_old","_new"))
    def delta(name): return float((j[f"{name}_new"]-j[f"{name}_old"]).mean())
    return {
        f"{profile}_shortfall_delta":delta("target_shortfall_top20"),
        f"{profile}_achievement_delta":delta("target_achievement_top20"),
        f"{profile}_median_xirr_delta":delta("median_xirr_top20"),
        f"{profile}_drawdown_delta":delta("mean_asset_drawdown_top20"),
    }

def current_frame():
    v3=pd.read_csv(V3,low_memory=False)
    frozen=pd.read_csv(d.hist.FREEZE/"rankings.csv.gz",low_memory=False)
    cur=frozen.drop(columns=["cagr_5y"]).merge(
        prior.current_features(v3),on=["isin","decision_date"],how="left",validate="many_to_one")
    cur["champion_score"]=cur.selected_ensemble_score
    return cur

def current_missing(cur,a,m,v,w):
    cur=cur.copy()
    cur["v13_score"]=score(cur,a,m,v,w)
    base=cur.loc[cur.profile_name.eq("base7500")].dropna(subset=["v13_score"]).copy()
    ranked=base.sort_values(["v13_score","isin"],ascending=[False,True])
    return {
        "current_coverage":int(len(ranked)),
        "current_universe_missing_true_5y":float(ranked.cagr_5y_observed.ne(1).mean()),
        "current_top20_missing_true_5y":float(ranked.head(20).cagr_5y_observed.ne(1).mean()),
        "current_top50_missing_true_5y":float(ranked.head(50).cagr_5y_observed.ne(1).mean()),
        "current_top100_missing_true_5y":float(ranked.head(100).cagr_5y_observed.ne(1).mean()),
    }

def main():
    if OUT.exists():
        raise FileExistsError(f"fresh output required: {OUT}")
    OUT.mkdir(parents=True)
    b=pd.read_pickle(V12/"development_baseline.pkl.gz",compression="gzip")
    if pd.to_datetime(b.decision_date).max()>=pd.Timestamp("2024-01-01"):
        raise ValueError("V13 selection frame contains post-development dates")
    ref=d.hist.evaluate(b,"champion_score")
    cur=current_frame()
    rows=[]
    for a in AGE:
        for m in MISSING:
            for v in DOWNSIDE:
                for w in WEEKLY_EXTRA:
                    b["v13_score"]=score(b,a,m,v,w)
                    measure=d.hist.evaluate(b,"v13_score")
                    row={"age_coefficient":a,"missing5y_coefficient":m,
                         "downside_coefficient":v,"weekly_extra_downside":w,
                         **d.metric_deltas(measure,ref),
                         **profile_delta(measure,ref,"weekly"),
                         **profile_delta(measure,ref,"lookback60"),
                         **current_missing(cur,a,m,v,w)}
                    row["v13_gate"]=bool(
                        row["eligible"] and row["utility"]>0
                        and row["weekly_shortfall_delta"]<=0
                        and row["weekly_drawdown_delta"]>=0
                        and row["weekly_achievement_delta"]>=-.02
                        and row["lookback60_shortfall_delta"]<=.005
                        and row["lookback60_drawdown_delta"]>=-.01
                        and row["lookback60_achievement_delta"]>=-.05
                        and row["current_top20_missing_true_5y"]<=.50
                        and row["current_top50_missing_true_5y"]<=.35
                    )
                    rows.append(row)
                    print(json.dumps({"a":a,"m":m,"v":v,"w":w,
                                      "utility":row["utility"],"gate":row["v13_gate"],
                                      "weekly_short":row["weekly_shortfall_delta"],
                                      "top20_missing":row["current_top20_missing_true_5y"]}),flush=True)
    table=pd.DataFrame(rows).sort_values(["v13_gate","utility"],ascending=[False,False])
    table.to_csv(OUT/"development_search.csv",index=False)
    passing=table.loc[table.v13_gate]
    summary={
        "schema":"personalized_v13_development_search_v1",
        "development_dates":sorted(b.decision_date.unique().tolist()),
        "candidate_count":int(len(table)),
        "passing_count":int(len(passing)),
        "post_2023_outcomes_loaded":False,
        "current_structural_diagnostic_used":True,
        "v12_development_baseline_sha256":sha(V12/"development_baseline.pkl.gz"),
        "v3_enrichment_sha256":sha(V3),
        "search_sha256":sha(OUT/"development_search.csv"),
        "selection_rule":{
            "weekly_shortfall_delta_max":0.0,
            "weekly_drawdown_delta_min":0.0,
            "weekly_achievement_delta_min":-.02,
            "lookback60_shortfall_delta_max":.005,
            "lookback60_drawdown_delta_min":-.01,
            "lookback60_achievement_delta_min":-.05,
            "current_top20_missing_true_5y_max":.50,
            "current_top50_missing_true_5y_max":.35,
            "base_v12_eligible_required":True,
            "utility_positive_required":True,
            "ranking":"highest V12 development robustness-adjusted utility among passing candidates",
        },
    }
    if len(passing):
        winner=passing.iloc[0].to_dict()
        summary["winner"]={k:(bool(v) if isinstance(v,(np.bool_,bool)) else
                               float(v) if isinstance(v,(np.floating,float)) else
                               int(v) if isinstance(v,(np.integer,int)) else v)
                           for k,v in winner.items()}
    (OUT/"development_summary.json").write_text(json.dumps(summary,indent=2,default=str)+"\n",encoding="utf-8")
    print(json.dumps({"passing":len(passing),
                      "winner":summary.get("winner")},indent=2,default=str))

if __name__=="__main__": main()
