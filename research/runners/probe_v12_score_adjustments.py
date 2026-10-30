"""Development-only, fixed-grid history-risk score adjustments."""
from __future__ import annotations

from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import numpy as np
import pandas as pd
from research.runners import personalized_deeper_championship_v2 as d


def run():
    b=pd.read_pickle(d.OUT/"development_baseline.pkl.gz",compression="gzip")
    m=d.hist.evaluate(b,"champion_score")
    age=(1-b.history_months.fillna(0).div(60).clip(0,1))*b.cagr_5y_observed.ne(1)
    def neutral(name):
        observed=b[name]
        return observed.fillna(observed.groupby(b.decision_date).transform("median")).fillna(observed.median())
    duration=neutral("current_drawdown_duration_days").div(1825).clip(0,1)
    depth=(-neutral("full_history_max_drawdown")).clip(0,1)
    high_age=neutral("days_since_recorded_high").div(1825).clip(0,1)
    high_distance=(-neutral("distance_from_recorded_high")).clip(0,1)
    downside=neutral("downside_volatility_1y").clip(0,2).div(2)
    signals={
        "age":age,
        "underwater":duration*depth,
        "high":high_age*high_distance,
        "full_drawdown":depth,
        "downside_volatility":downside,
        "age_underwater":.5*age+.5*duration*depth,
        "age_high":.5*age+.5*high_age*high_distance,
    }
    rows=[]
    for name,signal in signals.items():
        for penalty in (.02,.05,.10,.20):
            b["candidate_score"]=b.champion_score-penalty*signal
            measure=d.hist.evaluate(b,"candidate_score")
            rows.append({"signal":name,"penalty":penalty,**d.metric_deltas(measure,m)})
        print("tested",name,flush=True)
    result=pd.DataFrame(rows).sort_values(["eligible","utility"],ascending=[False,False])
    result.to_csv(d.OUT/"development_history_adjustments.csv",index=False)
    print(result.head(10)[["signal","penalty","utility","eligible","delta_ndcg20",
                           "delta_target_achievement_top20","delta_target_shortfall_top20",
                           "delta_median_xirr_top20","delta_mean_asset_drawdown_top20"]].to_string(index=False))


if __name__=="__main__":run()
