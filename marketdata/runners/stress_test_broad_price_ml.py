"""Fixed diagnostics for the locked broad chronological price-model test."""
from __future__ import annotations
import argparse, json
from hashlib import sha256
from pathlib import Path
import numpy as np
import pandas as pd

def run(source:Path, output:Path):
    if output.exists(): raise ValueError("fresh output required")
    summary=json.loads((source/"summary.json").read_text(encoding="utf-8"))
    rows=pd.read_csv(source/"evaluated_rows.csv")
    test=rows.loc[rows.decision_date.between("2024-09-01","2025-08-31")].dropna(subset=["selected_ensemble","baseline_signal","future_12m"])
    cells=[]
    for (date,sector),g in test.groupby(["decision_date","sector"],sort=True):
        if len(g)<3: continue
        y=g.future_12m.rank(); challenger=g.selected_ensemble.rank().corr(y); baseline=g.baseline_signal.rank().corr(y)
        q=max(1,len(g)//5); ordered_c=g.sort_values("selected_ensemble"); ordered_b=g.sort_values("baseline_signal")
        cells.append({"decision_date":date,"sector":sector,"peers":len(g),"challenger_rank_ic":challenger,"baseline_rank_ic":baseline,
          "delta_rank_ic":challenger-baseline,
          "challenger_top_bottom":ordered_c.tail(q).future_12m.mean()-ordered_c.head(q).future_12m.mean(),
          "baseline_top_bottom":ordered_b.tail(q).future_12m.mean()-ordered_b.head(q).future_12m.mean()})
    cells=pd.DataFrame(cells); monthly=cells.groupby("decision_date").agg(cells=("delta_rank_ic","size"),challenger_rank_ic=("challenger_rank_ic","mean"),baseline_rank_ic=("baseline_rank_ic","mean"),delta_rank_ic=("delta_rank_ic","mean")).reset_index()
    sectors=cells.groupby("sector").agg(cells=("delta_rank_ic","size"),mean_delta=("delta_rank_ic","mean"),win_fraction=("delta_rank_ic",lambda x:float((x>0).mean()))).reset_index()
    rng=np.random.default_rng(20260730); values=monthly.delta_rank_ic.to_numpy(); boot=np.array([rng.choice(values,len(values),replace=True).mean() for _ in range(10000)])
    thresholds={str(n):{"cells":int((cells.peers>=n).sum()),"challenger":float(cells.loc[cells.peers>=n].challenger_rank_ic.mean()),"baseline":float(cells.loc[cells.peers>=n].baseline_rank_ic.mean()),"delta":float(cells.loc[cells.peers>=n].delta_rank_ic.mean())} for n in (3,5,10,20)}
    result={"schema_version":"broad_price_ml_stress_v1","source_fingerprint":json.loads((source/"manifest.json").read_text())["fingerprint"],
      "selected":summary["selected_before_locked_test"],"company_rows":len(test),"issuers":int(test["isin"].nunique()),"months":len(monthly),"cells":len(cells),
      "mean_delta_rank_ic":float(cells.delta_rank_ic.mean()),"cell_win_fraction":float(cells.delta_rank_ic.gt(0).mean()),
      "month_win_fraction":float(monthly.delta_rank_ic.gt(0).mean()),"bootstrap_month_delta_95pct":[float(np.quantile(boot,.025)),float(np.quantile(boot,.975))],
      "top_bottom":{"challenger":float(cells.challenger_top_bottom.mean()),"baseline":float(cells.baseline_top_bottom.mean())},"peer_thresholds":thresholds,
      "sector_positive_fraction":float(sectors.mean_delta.gt(0).mean()),"promotion_permitted":False,
      "reason":"Strong locked comparative result, but current-survivor membership and current sector labels prevent unconditional production promotion."}
    output.mkdir(parents=True); cells.to_csv(output/"cell_diagnostics.csv",index=False,float_format="%.17g",lineterminator="\n"); monthly.to_csv(output/"monthly_diagnostics.csv",index=False,float_format="%.17g",lineterminator="\n"); sectors.to_csv(output/"sector_diagnostics.csv",index=False,float_format="%.17g",lineterminator="\n")
    (output/"summary.json").write_text(json.dumps(result,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    artifacts=[{"path":p.name,"sha256":sha256(p.read_bytes()).hexdigest(),"size":p.stat().st_size} for p in sorted(output.iterdir())]
    fp=sha256(json.dumps(artifacts,sort_keys=True,separators=(",", ":")).encode()).hexdigest(); (output/"manifest.json").write_text(json.dumps({"fingerprint":fp,"artifacts":artifacts},indent=2,sort_keys=True)+"\n",encoding="utf-8"); return result|{"fingerprint":fp}
def main():
    p=argparse.ArgumentParser();p.add_argument("--source",type=Path,required=True);p.add_argument("--output",type=Path,required=True);a=p.parse_args();print(json.dumps(run(a.source,a.output),sort_keys=True))
if __name__=="__main__":main()
