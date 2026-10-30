"""Development-only two-signal confidence and downside risk probe."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT),str(ROOT/"src")]
import pandas as pd
from research.runners import personalized_deeper_championship_v2 as d

b=pd.read_pickle(d.OUT/"development_baseline.pkl.gz",compression="gzip")
baseline=d.hist.evaluate(b,"champion_score")
age=(1-b.history_months.fillna(0).div(60).clip(0,1))*b.cagr_5y_observed.ne(1)
v=b.downside_volatility_1y
v=v.fillna(v.groupby(b.decision_date).transform("median")).fillna(v.median()).clip(0,2).div(2)
rows=[]
for a in (.02,.05,.10):
    for q in (.05,.10,.20):
        b["probe"]=b.champion_score-a*age-q*v
        rows.append({"age_coefficient":a,"volatility_coefficient":q,
                     **d.metric_deltas(d.hist.evaluate(b,"probe"),baseline)})
result=pd.DataFrame(rows).sort_values(["eligible","utility"],ascending=[False,False])
result.to_csv(d.OUT/"development_age_downside_combinations.csv",index=False)
print(result[["age_coefficient","volatility_coefficient","utility","eligible",
              "delta_ndcg20","delta_target_achievement_top20",
              "delta_target_shortfall_top20","delta_mean_asset_drawdown_top20"]].to_string(index=False))
