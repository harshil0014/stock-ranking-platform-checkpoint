"""Post-lock, descriptive market-return regimes from V12 base-profile outcomes."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import pandas as pd

OUT=ROOT/"experiments/personalized-deep-championship-20261002/v3"
PANEL=ROOT/"experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz"
if not (OUT/"evaluation_record.json").exists():
    raise RuntimeError("regime audit requires completed locked final evaluation")
raw=pd.read_csv(PANEL,usecols=["decision_date","profile_name","status","future_xirr"],low_memory=False)
base=raw.loc[raw.profile_name.eq("base7500") & raw.status.eq("AVAILABLE")]
regime=base.groupby("decision_date").future_xirr.median().rename("universe_median_12m_xirr").reset_index()
regime["return_regime"]=pd.cut(regime.universe_median_12m_xirr,
    bins=[-float("inf"),0,.2,float("inf")],labels=["negative","zero_to_20pct","above_20pct"])
metrics=pd.read_csv(OUT/"all_profile_date_slices.csv")
joined=metrics.merge(regime,on="decision_date",validate="many_to_one")
joined.to_csv(OUT/"outcome_regime_profile_slices.csv",index=False)
rows=[]
for (part,kind),g in joined.groupby(["partition","return_regime"],observed=True):
    row={"partition":part,"return_regime":str(kind),"decision_dates":g.decision_date.nunique(),
         "profile_date_blocks":len(g)}
    for metric in ("ndcg20","target_achievement_top20","target_shortfall_top20",
                   "median_xirr_top20","mean_asset_drawdown_top20"):
        row[metric+"_delta"]=(g[metric+"_challenger"]-g[metric+"_champion"]).mean()
    rows.append(row)
pd.DataFrame(rows).to_csv(OUT/"outcome_regime_summary.csv",index=False)
regime.to_csv(OUT/"outcome_regime_dates.csv",index=False)
print(pd.DataFrame(rows).to_string(index=False))
