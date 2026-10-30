"""Partially pooled sector-specific experts, using only completed earlier outcomes."""
import json,pickle
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
from threadpoolctl import threadpool_limits
from full_coverage_challenger_20261008 import ROOT,OUT as PRIOR,activity,predictors,selected_score,selection,evaluate,aggregate,METRICS
OUT=ROOT/'experiments/sector-local-experts-20261008'
COLS=predictors()+['volume_active_fraction','observations_1y']

def run():
    OUT.mkdir(exist_ok=True)
    protocol={'hypothesis':'Sector-specific feature effects can improve within-sector ordering; shrink local predictions toward a global ridge model to reduce small-sector variance.',
        'targets':['return','balanced','defensive'],'local_weights':[.25,.5,.75],
        'minimum_local_rows':120,'minimum_local_dates':4,'ridge_alpha':100,'training':'Annual endpoint-purged 2020–2025; base7500; no future/current fundamentals.',
        'candidate_blends':[.25,.5,1.],'comparison':'Both prior champions, raw/capped, two periods/scopes, Top1/3/5, five metrics. All dates previously exposed; no fresh holdout.'}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    x=activity(pd.read_pickle(PRIOR/'historical.pkl.gz',compression='gzip'))
    old=activity(pd.read_pickle(PRIOR/'predictions.pkl.gz',compression='gzip'))
    old['frozen_challenger']=selected_score(old,selection()['selected']['name'])
    pieces=[];audits=[]
    for year in range(2020,2026):
        test=old[old.decision_date.str.startswith(str(year))].copy()
        train=x[x.endpoint.lt(f'{year}-01-01')].dropna(subset=['future_xirr','future_drawdown','future_shortfall']).copy()
        train=train[train.sector.ne('Unclassified')]
        train=train[train.groupby(['decision_date','sector'])['isin'].transform('size').ge(5)]
        group=train.groupby(['decision_date','sector']);r=group.future_xirr.rank(pct=True);d=group.future_drawdown.rank(pct=True);s=group.future_shortfall.rank(pct=True,ascending=False)
        for target,y in [('return',r),('balanced',.5*r+.25*d+.25*s),('defensive',.25*r+.5*d+.25*s)]:
            global_model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler(),Ridge(alpha=100))
            # Equal total regression weight per date-sector query.
            weight=1/group['isin'].transform('size');weight=weight/weight.mean()
            global_model.fit(train[COLS],y,ridge__sample_weight=weight)
            gp=pd.Series(global_model.predict(test[COLS]),index=test.index);lp=gp.copy();locals={}
            for sector,part in train.groupby('sector'):
                mask=test.sector.eq(sector)
                if len(part)<120 or part.decision_date.nunique()<4 or not mask.any():continue
                model=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler(),Ridge(alpha=100))
                model.fit(part[COLS],y.loc[part.index],ridge__sample_weight=weight.loc[part.index])
                lp.loc[mask]=model.predict(test.loc[mask,COLS]);locals[sector]=model
            for w in [.25,.5,.75]:
                pred=(1-w)*gp+w*lp
                test[f'local_{target}_{w}']=pred.groupby([test.decision_date,test.sector]).rank(pct=True)
            with (OUT/f'{target}_{year}.pkl').open('wb') as f:pickle.dump({'global':global_model,'local':locals},f)
            audits.append({'year':year,'target':target,'rows':len(train),'local_models':len(locals),'max_endpoint':train.endpoint.max()})
            pd.DataFrame(audits).to_csv(OUT/'training_audit.csv',index=False)
            print('LOCAL',year,target,len(locals),flush=True)
        pieces.append(test)
    x=pd.concat(pieces,ignore_index=True);names=[]
    for target in ['return','balanced','defensive']:
        for local in [.25,.5,.75]:
            source=f'local_{target}_{local}'
            for blend in [.25,.5,1.]:
                name=f'{source}_blend{blend}';x[name]=(1-blend)*x.frozen_challenger+blend*x[source];names.append(name)
    x.to_pickle(OUT/'predictions.pkl.gz',compression='gzip');summaries=[]
    for bounded in [False,True]:
        z=x.copy()
        if bounded:z.future_xirr=z.future_xirr.clip(-1,1)
        for i in range(0,len(names),5):
            a=aggregate(evaluate(z,['frozen_challenger']+names[i:i+5],top_ns=(1,3,5))).reset_index();a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
            pd.concat(summaries).drop_duplicates(['model','period','scope','top_n','return_treatment']).to_csv(OUT/'summary.csv',index=False)
            print('LOCAL EVALUATE',bounded,i,flush=True)
    a=pd.concat(summaries).drop_duplicates(['model','period','scope','top_n','return_treatment']).set_index(['model','period','scope','top_n','return_treatment'])[METRICS];trials=[]
    for n in names:
        cells=[]
        for baseline in ['sector_incumbent','frozen_challenger']:
            d=a.loc[n]-a.loc[baseline];d.shortfall=-d.shortfall;cells.extend(d.to_numpy().ravel())
        c=np.asarray(cells);trials.append({'model':n,'strict_gate':bool((c>=-1e-12).all() and (c>1e-12).any()),'regressing_cells':int((c < -1e-12).sum()),'total_cells':len(c),'worst_delta':float(c.min()),'mean_delta':float(c.mean())})
    t=pd.DataFrame(trials).sort_values(['strict_gate','regressing_cells','mean_delta'],ascending=[False,True,False]);t.to_csv(OUT/'trials.csv',index=False);print(t.head().to_string(index=False),flush=True)

if __name__=='__main__':
    with threadpool_limits(limits=1):run()
