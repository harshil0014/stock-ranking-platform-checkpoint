from pathlib import Path
import hashlib,json
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2]
DIR=ROOT/"experiments/current-data-recovery-20261003"
IN=DIR/"current_company_facts_recovered.csv.gz"
ORIG=ROOT/"experiments/professor-current-fallback-20261003/equal-priority-v2/current_company_facts_equal_priority.csv.gz"
d=pd.read_csv(IN,low_memory=False); orig=pd.read_csv(ORIG,low_memory=False)
cut=pd.Timestamp("2026-09-18"); added=[]
pairs=[("product_baseline_yoy_growth","screener_return_1y_pct","product_baseline_yoy_growth_source"),
       ("product_baseline_cagr_3y","screener_return_3y_pct","product_baseline_cagr_3y_source"),
       ("product_baseline_cagr_5y","screener_return_5y_pct","product_baseline_cagr_5y_source")]
for target,source,srcfield in pairs:
    mask=d[target].isna() & pd.to_numeric(d[source],errors="coerce").notna()
    for i in d.index[mask]:
        v=float(pd.to_numeric(d.at[i,source],errors="coerce"))/100.0
        d.at[i,target]=v; d.at[i,srcfield]="SCREENER_CURRENT"
        added.append({"row":int(i),"ticker":d.at[i,"ticker"],"isin":d.at[i,"isin"],"field":target,"value":v,"source":"SCREENER_CURRENT"})
dates=pd.to_datetime(d["recorded_high_date"],errors="coerce")
mask=d["product_baseline_days_since_recorded_high"].isna() & dates.notna() & dates.le(cut)
for i in d.index[mask]:
    v=int((cut-dates.loc[i].normalize()).days)
    d.at[i,"product_baseline_days_since_recorded_high"]=v
    d.at[i,"product_baseline_days_since_recorded_high_source"]="DERIVED_TRUSTED_RECORDED_HIGH_DATE"
    added.append({"row":int(i),"ticker":d.at[i,"ticker"],"isin":d.at[i,"isin"],
                  "field":"product_baseline_days_since_recorded_high","value":v,
                  "source":"DERIVED_TRUSTED_RECORDED_HIGH_DATE"})

for field in ["product_baseline_yoy_growth","product_baseline_cagr_3y","product_baseline_cagr_5y",
              "product_baseline_days_since_recorded_high","recorded_high"]:
    m=orig[field].notna()
    a=pd.to_numeric(orig.loc[m,field],errors="coerce").to_numpy(float)
    b=pd.to_numeric(d.loc[m,field],errors="coerce").to_numpy(float)
    if not np.allclose(a,b,rtol=0,atol=1e-12,equal_nan=True):
        raise RuntimeError("existing trusted numeric value changed: "+field)
m=orig["recorded_high_date"].notna()
a=pd.to_datetime(orig.loc[m,"recorded_high_date"],errors="coerce").reset_index(drop=True)
b=pd.to_datetime(d.loc[m,"recorded_high_date"],errors="coerce").reset_index(drop=True)
if not a.equals(b):
    raise RuntimeError("existing trusted date changed: recorded_high_date")

out=DIR/"current_company_facts_recovered_v2.csv.gz"
d.to_csv(out,index=False,compression="gzip")
pd.DataFrame(added).to_csv(DIR/"final_cleanup_filled_cells.csv",index=False)
track=["product_baseline_yoy_growth","product_baseline_cagr_3y","product_baseline_cagr_5y",
       "product_baseline_days_since_recorded_high","current_cagr_7y","current_cagr_10y",
       "recorded_high","recorded_high_date"]
after={c:int(d[c].isna().sum()) for c in track}
reason={}
for f,y in [("product_baseline_yoy_growth",1),("product_baseline_cagr_3y",3),
            ("product_baseline_cagr_5y",5),("current_cagr_7y",7),("current_cagr_10y",10)]:
    x=d[d[f].isna()]
    anchor=cut-pd.DateOffset(years=y)
    listing=pd.to_datetime(x["listing_date"],errors="coerce")
    start=pd.to_datetime(x["history_start_date"],errors="coerce")
    reason[f]={"missing":int(len(x)),"listing_too_young":int((listing>anchor).sum()),
               "observed_history_starts_too_late":int((start>anchor).sum())}
summary={"schema":"current_data_recovery_v2","cutoff":"2026-09-18",
         "cleanup_additional_cells":len(added),"missing_after":after,
         "remaining_missing_reason_counts":reason,
         "existing_nonblank_overwritten":0,"historical_training_modified":False,"production_modified":False}
(DIR/"summary_v2.json").write_text(json.dumps(summary,indent=2),encoding="utf-8")
manifest={}
for p in [out,DIR/"filled_cells.csv",DIR/"final_cleanup_filled_cells.csv",DIR/"summary.json",DIR/"summary_v2.json"]:
    manifest[p.name]={"bytes":p.stat().st_size,"sha256":hashlib.sha256(p.read_bytes()).hexdigest()}
(DIR/"manifest_v2.json").write_text(json.dumps(manifest,indent=2),encoding="utf-8")
print(json.dumps(summary,indent=2))
