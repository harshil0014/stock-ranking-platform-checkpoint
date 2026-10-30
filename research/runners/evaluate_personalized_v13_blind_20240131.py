"""One-time blind evaluation of locked V13 on unseen 2024-01-31 decision."""
from pathlib import Path
import hashlib,json,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import numpy as np
import pandas as pd
from stock_ranker.company_facts import resolve_company_fact_snapshot
from research.runners import personalized_deeper_championship_v2 as d

V13=ROOT/"experiments/personalized-v13-20261002"
RAW=V13/"blind-2024-01-31/checkpoints/deep_added-2024-01-31.csv.gz"
V12=d.OUT
DAY="2024-01-31"
OUT=V13/"blind-evaluation-2024-01-31"

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def neutral(frame,name):
    x=frame[name]
    return x.fillna(x.groupby(frame.decision_date).transform("median")).fillna(x.median())

def v13_score(frame):
    missing=frame.cagr_5y_observed.ne(1).astype(float)
    gap=(1-frame.history_months.fillna(0).div(60).clip(0,1)).clip(0,1)*missing
    smooth=gap.pow(.5)
    downside=neutral(frame,"downside_volatility_1y").clip(0,2).div(2)
    weekly=frame.profile_name.eq("weekly").astype(float)
    return frame.champion_score-.06*smooth-.20*downside-.15*weekly*downside

def main():
    if OUT.exists(): raise FileExistsError(OUT)
    lock=V13/"locked_selection.json"
    if sha(lock)!="dad3ce68b22a1f744650e501505a3ebc78dc7c4bd39c3247982c4ed84bcac13b":
        raise ValueError("V13 selection lock drift")
    plan=V13/"blind_validation_plan.json"
    OUT.mkdir(parents=True)
    # Do not load outcome columns before scores are fixed.
    header=pd.read_csv(RAW,nrows=0).columns.tolist()
    outcome={"future_xirr","future_shortfall","future_drawdown"}
    score_cols=[c for c in header if c not in outcome]
    target=pd.read_csv(RAW,usecols=score_cols,low_memory=False)
    if set(target.decision_date.astype(str))!={DAY}: raise ValueError("blind target date mismatch")
    if len(target)!=30305: raise ValueError(f"unexpected blind row count {len(target)}")
    facts=d.hist.load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT/"data/company_facts")).facts
    locator=facts[["isin","ticker"]].drop_duplicates("isin").copy()
    locator["derived_research_sector"]="GLOBAL"
    features=d.hist.history_features({"blind":target[["isin","decision_date"]].drop_duplicates()},locator)
    features=features.drop(columns=["sector","sector_median_cagr_5y"])
    target=target.rename(columns={"cagr_5y":"original_cagr_5y"}).merge(
        features,on=["isin","decision_date"],how="left",validate="many_to_one")
    target["cagr_5y_observed"]=target.cagr_5y_observed.fillna(0).astype("int8")
    observed=target.loc[target.cagr_5y_observed.eq(1),"observed_cagr_5y"]
    anchor=float(observed.median()) if len(observed) else 0.0
    weight=target.history_months.fillna(0).div(60).clip(0,1)
    estimated=weight*target.history_start_cagr.clip(-.75,1).fillna(0)+(1-weight)*np.clip(anchor,-.5,.5)
    target["cagr_5y"]=target.observed_cagr_5y.where(target.cagr_5y_observed.eq(1),estimated)
    target["cagr_5y_source"]=np.where(target.cagr_5y_observed.eq(1),"OBSERVED",
                                      np.where(target.history_months.notna(),"ESTIMATED_GLOBAL","NO_HISTORY"))
    for c in outcome: target[c]=np.nan

    train=pd.read_pickle(V12/"prepared.pkl.gz",compression="gzip")
    combined=pd.concat([train,target],ignore_index=True,sort=False)
    scored=d.baseline(combined,[DAY])
    scored["v13_score"]=v13_score(scored)
    fixed=scored[["isin","decision_date","profile_name","champion_score","v13_score",
                  "history_months","cagr_5y_observed","downside_volatility_1y"]].copy()
    fixed.to_csv(OUT/"scores_before_reveal.csv.gz",index=False,
                 compression={"method":"gzip","mtime":0})
    score_hash=sha(OUT/"scores_before_reveal.csv.gz")
    prereveal={
      "selection_lock_sha256":sha(lock),"blind_plan_sha256":sha(plan),
      "raw_checkpoint_sha256":sha(RAW),"scores_before_reveal_sha256":score_hash,
      "decision_date":DAY,"score_rows":len(fixed),
      "outcome_columns_loaded":False,"selection_changed":False}
    (OUT/"pre_reveal_record.json").write_text(json.dumps(prereveal,indent=2)+"\n")
    # One-time reveal starts here, after score file and its hash exist.
    actual=pd.read_csv(RAW,usecols=["isin","decision_date","profile_name",
                                    "future_xirr","future_shortfall","future_drawdown"],
                       low_memory=False)
    evaluated=scored.drop(columns=list(outcome)).merge(
        actual,on=["isin","decision_date","profile_name"],how="left",validate="one_to_one")
    champ=d.hist.evaluate(evaluated,"champion_score")
    challenger=d.hist.evaluate(evaluated,"v13_score")
    joined=champ.merge(challenger,on=["decision_date","profile"],suffixes=("_champion","_v13"))
    joined.to_csv(OUT/"profile_metrics.csv",index=False)
    metrics={}
    for metric in d.METRICS:
        old=float(champ[metric].mean()); new=float(challenger[metric].mean())
        metrics[metric]={"champion":old,"v13":new,"delta":new-old}
    profile={}
    for name in ("weekly","lookback60"):
        row=joined.loc[joined.profile.eq(name)].iloc[0]
        profile[name]={
          "achievement_delta":float(row.target_achievement_top20_v13-row.target_achievement_top20_champion),
          "shortfall_delta":float(row.target_shortfall_top20_v13-row.target_shortfall_top20_champion),
          "median_xirr_delta":float(row.median_xirr_top20_v13-row.median_xirr_top20_champion),
          "drawdown_delta":float(row.mean_asset_drawdown_top20_v13-row.mean_asset_drawdown_top20_champion)}
    record={
      "schema":"personalized_v13_blind_evaluation_v1",
      "selection_lock_sha256":sha(lock),"blind_plan_sha256":sha(plan),
      "scores_before_reveal_sha256":score_hash,"raw_checkpoint_sha256":sha(RAW),
      "decision_date":DAY,"endpoint":"2025-01-31",
      "outcomes_revealed_once":True,"selection_changed_after_reveal":False,
      "aggregate":metrics,"profile_focus":profile,
      "promotion_interpretation":"Independent post-development holdout evidence; true prospective 2025-09-30 decision remains deferred.",
      "production_mutated":False,"frozen_champion_mutated":False}
    (OUT/"evaluation_record.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))
if __name__=="__main__": main()
