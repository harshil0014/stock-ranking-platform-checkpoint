"""Current-sector composition diagnostic; no historical sector backfill."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
import pandas as pd

OUT=ROOT/"experiments/personalized-deep-championship-20261002/v3"
v3=pd.read_csv(ROOT/"experiments/history-enrichment-20261002/final-data-quality-v3/history_enrichment.csv.gz",
               usecols=["isin","sector","ticker"])
scores=pd.read_csv(OUT/"current_scores.csv.gz")
base=scores.loc[scores.profile_name.eq("base7500")].merge(v3,on="isin",how="left")
rows=[]
for kind,score in (("champion","champion_score"),("challenger","candidate_score")):
    top=base.dropna(subset=[score]).sort_values([score,"isin"],ascending=[False,True]).head(20)
    for sector,count in top.sector.value_counts().items():
        rows.append({"kind":kind,"sector":sector,"top20_count":int(count)})
result=pd.DataFrame(rows)
result.to_csv(OUT/"current_sector_composition.csv",index=False)
print(result.to_string(index=False))
