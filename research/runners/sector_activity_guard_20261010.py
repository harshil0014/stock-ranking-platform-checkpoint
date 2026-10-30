"""Fixed diagnostic follow-up prompted by nearly flat current sector leader."""
import json
import numpy as np
import pandas as pd
import sector_price_rebuild_20261010 as p
BASE=p.OUT;OUT=p.ROOT/'experiments/sector-activity-guard-20261010'

def run():
    OUT.mkdir(exist_ok=True)
    rule={'trigger':'At least 63 observed returns and more than 80% exactly zero price changes in the trailing feature window.',
      'ranking':'Flagged stocks remain covered, ordered below unflagged stocks: score = original score - 1. This is a price-activity proxy, not verified trading volume or a delisting conclusion.',
      'origin':'Current KALYANI review showed 99.6% flat changes and sector rank 1. Threshold fixed before this diagnostic; no selection over thresholds. Current evidence informed the hypothesis, so no fresh-validation claim.',
      'source':'https://www.kalyanicommercials.com/files/annual-reports/KC_AR_2024-25.pdf'}
    (OUT/'protocol.json').write_text(json.dumps(rule,indent=2))
    parent=json.loads((BASE/'selection.json').read_text())['model'];name,w=parent.split('_blend');w=float(w)
    x=pd.concat([pd.read_csv(BASE/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    old=pd.concat([pd.read_csv(p.OLD/f'predictions_{y}.csv.gz',usecols=p.KEYS+['profile_defensive_15']) for y in range(2020,2026)],ignore_index=True)
    x=x.merge(old,on=p.KEYS,validate='one_to_one');x['guarded_previous']=.8*x.open_model+.2*x.profile_defensive_15
    x['parent']=(1-w)*x.guarded_previous+w*x[name]
    f=pd.read_pickle(BASE/'price_features.pkl.gz',compression='gzip')[['isin','decision_date','observations','zero_fraction']]
    x=x.merge(f,on=['isin','decision_date'],validate='many_to_one')
    flag=x.observations.ge(63)&x.zero_fraction.gt(.8);x['activity_guard']=x.parent-flag.astype(float)
    x[p.KEYS+['activity_guard']].rename(columns={'activity_guard':'replacement_score'}).to_csv(OUT/'selected_historical_scores.csv.gz',index=False)
    summaries=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        refs=['activity_guard','parent','open_model','frozen_challenger','guarded_previous']+(['sector_incumbent'] if scope=='common' else [])
        for bounded in [False,True]:
            zz=z.copy()
            if bounded:zz.future_xirr=zz.future_xirr.clip(-1,1)
            q=p.metrics(zz,refs,top_ns=(1,3,5));q.to_csv(OUT/f'queries_{scope}_{bounded}.csv.gz',index=False)
            a=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
            a['scope']=scope;a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
            print('ACTIVITY EVALUATE',scope,bounded,flush=True)
    summary=pd.concat(summaries);summary.to_csv(OUT/'summary.csv',index=False)
    a=summary.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS];rows=[]
    for ref in ['parent','open_model','frozen_challenger','guarded_previous','sector_incumbent']:
        d=(a.loc['activity_guard']-a.loc[ref]).dropna();d.shortfall=-d.shortfall;d['reference']=ref;rows.append(d.reset_index())
    delta=pd.concat(rows);delta.to_csv(OUT/'directional_deltas.csv',index=False)
    v=delta[p.METRICS].to_numpy().ravel();d=delta[delta.reference.eq('parent')][p.METRICS].to_numpy().ravel()
    z=pd.read_csv(BASE/'current_all_stock_rankings.csv');z['flat_price_review']=z.observations.ge(63)&z.zero_fraction.gt(.8)
    z['activity_score']=z.rebuilt_score-z.flat_price_review.astype(float)
    z['activity_sector_rank']=z.activity_score.groupby(z.sector).rank(method='min',ascending=False)
    assert len(z)==4436 and np.isfinite(z.activity_score).all()
    z.to_csv(OUT/'current_all_stock_rankings.csv',index=False)
    result={'parent':parent,'model':'activity_guard','strict_gate':bool((v>=-1e-12).all()),'regressions':int((v < -1e-12).sum()),'comparisons':len(v),
      'parent_regressions':int((d < -1e-12).sum()),'parent_comparisons':len(d),'parent_improvements':int((d>1e-12).sum()),'current_flagged':int(z.flat_price_review.sum()),'current_stocks':len(z),'fresh_validation':False,'production_replaced':False}
    (OUT/'selection.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2),flush=True)

if __name__=='__main__':run()
