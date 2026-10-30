"""Post-lock retrospective stress of V13 on already-known V12 2025 finals.

These outcomes were known before V13 was conceived, so this file is diagnostic
only and must never be presented as fresh validation or used to retune V13.
"""
from pathlib import Path
import json,sys,hashlib
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import pandas as pd
from research.runners import personalized_deeper_championship_v2 as d

V13=ROOT/"experiments/personalized-v13-20261002"
V12=d.OUT
DATES={"2025-01-31","2025-08-31"}

def sha(path):
    h=hashlib.sha256()
    with Path(path).open("rb") as f:
        for b in iter(lambda:f.read(1024*1024),b""): h.update(b)
    return h.hexdigest()

def main():
    lock=V13/"locked_selection.json"
    if sha(lock)!="dad3ce68b22a1f744650e501505a3ebc78dc7c4bd39c3247982c4ed84bcac13b":
        raise ValueError("selection lock drift")
    score=pd.read_csv(V12/"untouched_final_2025_scores.csv.gz",low_memory=False)
    feat=pd.read_pickle(V12/"prepared.pkl.gz",compression="gzip")
    feat=feat.loc[feat.decision_date.isin(DATES),
                  ["isin","decision_date","profile_name","downside_volatility_1y"]]
    x=score.merge(feat,on=["isin","decision_date","profile_name"],how="left",validate="one_to_one")
    missing=x.cagr_5y_observed.ne(1).astype(float)
    gap=(1-x.history_months.fillna(0).div(60).clip(0,1)).clip(0,1)*missing
    downside=x.downside_volatility_1y
    downside=downside.fillna(downside.groupby(x.decision_date).transform("median")).fillna(downside.median()).clip(0,2).div(2)
    weekly=x.profile_name.eq("weekly").astype(float)
    x["v13_score"]=x.champion_score-.06*gap.pow(.5)-.20*downside-.15*weekly*downside
    actual=pd.read_csv(d.PANEL,usecols=["isin","decision_date","profile_name","future_xirr","future_shortfall","future_drawdown"],low_memory=False)
    actual=actual.loc[actual.decision_date.isin(DATES)]
    x=x.merge(actual,on=["isin","decision_date","profile_name"],how="left",validate="one_to_one")
    champ=d.hist.evaluate(x,"champion_score"); v13=d.hist.evaluate(x,"v13_score")
    j=champ.merge(v13,on=["decision_date","profile"],suffixes=("_champion","_v13"))
    j.to_csv(V13/"known_2025_retrospective_profile_metrics.csv",index=False)
    aggregate={}
    for m in d.METRICS:
        old=float(champ[m].mean()); new=float(v13[m].mean())
        aggregate[m]={"champion":old,"v13":new,"delta":new-old}
    profiles={}
    for p in ("weekly","lookback60"):
        one=j.loc[j.profile.eq(p)]
        profiles[p]={
          "achievement_delta":float((one.target_achievement_top20_v13-one.target_achievement_top20_champion).mean()),
          "shortfall_delta":float((one.target_shortfall_top20_v13-one.target_shortfall_top20_champion).mean()),
          "median_xirr_delta":float((one.median_xirr_top20_v13-one.median_xirr_top20_champion).mean()),
          "drawdown_delta":float((one.mean_asset_drawdown_top20_v13-one.mean_asset_drawdown_top20_champion).mean())}
    record={"schema":"personalized_v13_known_2025_stress_v1",
            "selection_lock_sha256":sha(lock),
            "diagnostic_only":True,
            "used_for_selection":False,
            "dates":sorted(DATES),
            "aggregate":aggregate,"profile_focus":profiles,
            "production_mutated":False,"frozen_champion_mutated":False}
    (V13/"known_2025_retrospective_stress.json").write_text(json.dumps(record,indent=2)+"\n")
    print(json.dumps(record,indent=2))
if __name__=="__main__":main()
