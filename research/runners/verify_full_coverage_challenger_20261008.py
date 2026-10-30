"""Reproduce selected predictions and investigate expanded-universe performance."""
import json,hashlib
import numpy as np
import pandas as pd
import lightgbm as lgb
from full_coverage_challenger_20261008 import OUT,ROOT,PKG,RAW,features,predictors,evaluate,aggregate,METRICS,selection,selected_score,activity,needed_models


def run():
    chosen=selection();name=chosen['selected']['name']
    selected=name.split('_blend')[0]
    audit=json.loads((OUT/'training_audit.json').read_text())
    assert len(audit)==48
    assert all(r['max_training_endpoint']<f'{r["year"]}-01-01'<=r['test_start'] for r in audit)
    x=pd.read_csv(OUT/'current_all_stock_rankings.csv')
    assert len(x)==4436 and x['isin'].nunique()==4436 and np.isfinite(x.challenger_score).all()
    for sector,g in x.groupby('sector'):
        np.testing.assert_allclose(g.challenger_score.rank(ascending=False,method='min'),g.challenger_sector_rank)
    if needed_models(name):
        current=x.copy();current['decision_date']='2026-10-03';current=features(current)
        for selected in needed_models(name):
            model=lgb.Booster(model_file=str(OUT/f'selected_{selected}.txt'))
            raw=pd.Series(model.predict(current[predictors()],num_threads=3),index=current.index)
            current[selected]=raw.groupby(current.sector).rank(pct=True).where(current.evidence_fraction.gt(0),.5)
        replay=selected_score(current,name).where(current.evidence_fraction.gt(0),.5)
        np.testing.assert_allclose(replay,x.challenger_score,rtol=0,atol=1e-12)
    p=activity(pd.read_pickle(OUT/'predictions.pkl.gz',compression='gzip'))
    p['challenger']=selected_score(p,name)
    # Clipping returns tests whether extreme XIRR values drive reported uplift.
    bounded=p.copy();bounded['future_xirr']=bounded.future_xirr.clip(-1,1)
    q=evaluate(bounded,['challenger']);aggregate(q).to_csv(OUT/'bounded_xirr_sensitivity.csv')
    q0=pd.read_csv(OUT/'historical_query_metrics.csv.gz')
    sec=q0[q0.top_n.eq(3)].groupby(['model','period','scope','sector'])[METRICS].mean()
    delta=sec.loc['challenger']-sec.loc['sector_incumbent'];delta.to_csv(OUT/'sector_top3_deltas.csv')
    contributions=[]
    for (period,day,sector),g in p.groupby(['period','decision_date','sector']):
        if sector=='Unclassified':continue
        g=g.dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
        if g.sector_incumbent.notna().sum()<5:continue
        picked=g.sort_values(['challenger','isin'],ascending=[False,True]).head(3)
        for r in picked.itertuples():
            contributions.append({'period':period,'date':day,'sector':sector,'isin':r.isin,
                'outside_champion':pd.isna(r.sector_incumbent),'future_xirr':r.future_xirr,
                'future_drawdown':r.future_drawdown,'future_shortfall':r.future_shortfall})
    picks=pd.DataFrame(contributions);picks.to_csv(OUT/'expanded_historical_top3_selections.csv.gz',index=False)
    grouped=picks.groupby('period').agg(selections=('isin','size'),outside_champion=('outside_champion','sum'),
        median_selected_xirr=('future_xirr','median'),max_selected_xirr=('future_xirr','max'))
    grouped.to_csv(OUT/'expanded_selection_audit.csv')
    # Review current candidates against existing independent fundamental rubric, never train on it.
    judge=pd.read_csv(ROOT/'experiments/sector-independent-judge-20261005/all_stock_sector_judgments.csv',
        usecols=['isin','judge_primary','judge_coverage','judge_flags'])
    review=x.merge(judge,on='isin',validate='one_to_one')
    review[review.challenger_sector_rank.le(3)].to_csv(OUT/'current_sector_top3_review.csv',index=False)
    comparisons=[]
    for sector,g in review.groupby('sector'):
        if sector=='Unclassified':continue
        for scope in ['common','expanded']:
            cohort=g[g.judge_primary.notna()]
            if scope=='common':cohort=cohort[cohort.sector_incumbent.notna()]
            if cohort.sector_incumbent.notna().sum()<5:continue
            row={'sector':sector,'scope':scope,'stocks':len(cohort)}
            for label,col in [('champion','sector_incumbent'),('challenger','challenger_score')]:
                top=cohort[cohort[col].notna()].sort_values([col,'isin'],ascending=[False,True]).head(3)
                row[label+'_judge_top3']=float(top.judge_primary.mean())
            comparisons.append(row)
    pd.DataFrame(comparisons).to_csv(OUT/'current_independent_rubric_comparison.csv',index=False)
    confidence=x.groupby('evidence_confidence').agg(stocks=('isin','size'),sector_top3=('challenger_sector_rank',lambda s:int(s.le(3).sum())))
    confidence.to_csv(OUT/'confidence_coverage.csv')
    results={'current_stocks':len(x),'finite_scores':len(x),'chronological_training_fits_verified':len(audit),
        'selected_model_prediction_reproduction':True,'sector_ranks_reproduced':True,
        'training_future_leakage_check':'All 48 max training endpoints precede annual cutoffs',
        'coverage_not_accuracy':'Neutral or sparse-evidence scores are not fully evidenced investment recommendations',
        'model_sha256':{n:hashlib.sha256((OUT/f'selected_{n}.txt').read_bytes()).hexdigest() for n in needed_models(name)},
        'xirr_tail_review':grouped.reset_index().to_dict('records')}
    (OUT/'verification.json').write_text(json.dumps(results,indent=2,allow_nan=False))
    print(json.dumps(results,indent=2),flush=True)


if __name__=='__main__':run()
