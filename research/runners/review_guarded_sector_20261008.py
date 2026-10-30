"""Apply the existing company-evidence rubric to every newly ranked identity."""
import pandas as pd
import json
from profile_aware_sector_20261008 import ROOT,NEW
OUT=ROOT/'experiments/action-guarded-sector-20261008'

def run():
    current=pd.read_csv(OUT/'current_all_stock_rankings.csv')
    rubric=pd.read_csv(NEW/'all_stock_evidence_review.csv.gz',usecols=['isin','judge_primary','judge_coverage','judge_flags'])
    x=current.merge(rubric,on='isin',how='left',validate='one_to_one')
    assert len(x)==4436
    x.to_csv(OUT/'all_stock_evidence_review.csv.gz',index=False)
    x[x.guarded_sector_rank.le(3)].to_csv(OUT/'current_sector_top3_review.csv',index=False)
    rows=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        models=['guarded_model_score','open_model_score','challenger_score']+(['sector_incumbent'] if scope=='common' else [])
        for sector,g in z.groupby('sector'):
            g=g.dropna(subset=['judge_primary']+models).sort_values('isin')
            if sector=='Unclassified' or len(g)<5:continue
            for model in models:
                top=g.sort_values(model,ascending=False,kind='stable').head(3)
                rows.append(dict(scope=scope,sector=sector,model=model,rubric_top3=top.judge_primary.mean(),matched_sector_stocks=len(g)))
    details=pd.DataFrame(rows);details.to_csv(OUT/'rubric_sector_comparison.csv',index=False)
    summary=details.groupby(['scope','model']).rubric_top3.mean().reset_index()
    summary.to_csv(OUT/'rubric_summary.csv',index=False)
    (OUT/'rubric_protocol.json').write_text(json.dumps({'source':'Existing company-evidence rubric; reused, not newly verified fundamentals or future-return truth.','common':'Stocks with production scores and finite rubric/model values; sectors with at least five such stocks.','expanded':'All stocks with finite rubric/model values; sectors with at least five such stocks, even if production has fewer than five. No production comparator here.','aggregation':'Top-three stocks per sector, then equal sector mean. Excludes Unclassified. Expanded sector set can differ from the common set and older restricted-sector reports.','snapshot':'2026-10-03'},indent=2))
    print(summary.to_string(index=False),flush=True)

if __name__=='__main__':run()
