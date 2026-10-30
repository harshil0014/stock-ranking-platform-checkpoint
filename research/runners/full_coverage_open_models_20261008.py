"""Expanded, endpoint-purged open-source model comparison. Research only."""
import sys,json,itertools,pickle
from pathlib import Path
import numpy as np
import pandas as pd
from full_coverage_challenger_20261008 import ROOT,OUT as PRIOR,predictors,activity,selected_score,selection,evaluate,aggregate,METRICS
sys.path.insert(0,str(ROOT/'experiments/model_dependencies_20261008'))
from catboost import CatBoostRanker
from xgboost import XGBRanker
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

OUT=ROOT/'experiments/full-coverage-open-models-20261008'
CONFIGS=[dict(name=f'{family}_{target}',family=family,target=target) for family,target in itertools.product(['catboost','xgboost','extra_trees','ridge'],['return','balanced','defensive'])]
COLS=predictors()+['volume_active_fraction','observations_1y']

def fit(train,c):
    t=train.dropna(subset=['future_xirr','future_drawdown','future_shortfall']).copy()
    t=t[t.sector.ne('Unclassified')]
    t=t[t.groupby(['decision_date','sector']).isin.transform('size').ge(5)].sort_values(['decision_date','sector','isin'])
    g=t.groupby(['decision_date','sector'],sort=False)
    ret=g.future_xirr.rank(pct=True);risk=g.future_drawdown.rank(pct=True);short=g.future_shortfall.rank(pct=True,ascending=False)
    y={'return':ret,'balanced':.5*ret+.25*risk+.25*short,'defensive':.25*ret+.5*risk+.25*short}[c['target']]
    X=t[COLS].replace([np.inf,-np.inf],np.nan)
    if c['family']=='catboost':
        m=CatBoostRanker(iterations=160,depth=5,learning_rate=.04,loss_function='YetiRank',l2_leaf_reg=20,thread_count=3,random_seed=20261008,verbose=False,allow_writing_files=False)
        m.fit(X,y,group_id=g.ngroup().to_numpy())
    elif c['family']=='xgboost':
        m=XGBRanker(objective='rank:ndcg',n_estimators=160,max_depth=4,learning_rate=.04,min_child_weight=50,reg_lambda=20,n_jobs=3,random_state=20261008)
        m.fit(X,np.floor(y*9).astype(int),group=g.size().to_numpy())
    else:
        estimator=ExtraTreesRegressor(n_estimators=160,max_depth=10,min_samples_leaf=70,max_features=.8,n_jobs=3,random_state=20261008) if c['family']=='extra_trees' else Ridge(alpha=100)
        m=make_pipeline(SimpleImputer(strategy='median',add_indicator=True),StandardScaler(),estimator)
        m.fit(X,y)
    return m,t

def run():
    OUT.mkdir(exist_ok=True)
    protocol={'configs':CONFIGS,'features':COLS,'folds':list(range(2020,2026)),
      'training':'Outcome endpoint strictly before test-year January 1; base7500 only; all dates previously exposed.',
      'strict_gate':'All five metrics nonworse versus BOTH production champion and frozen full-coverage challenger, across two periods, two scopes, Top1/3/5, raw and capped[-1,1] XIRR. Strict improvement required.',
      'candidates':'Each model standalone and 25/50/75 percent blend with frozen challenger; two equal family ensembles. All results retained.',
      'promotion':'No automatic production replacement. Any passing result requires all-profile transfer checks.',
      'sources':['https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html','https://doi.org/10.1007/s10994-006-6226-1','https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html']}
    p=OUT/'protocol.json'
    if p.exists():assert json.loads(p.read_text())==protocol
    p.write_text(json.dumps(protocol,indent=2))
    x=activity(pd.read_pickle(PRIOR/'historical.pkl.gz',compression='gzip'))
    old=activity(pd.read_pickle(PRIOR/'predictions.pkl.gz',compression='gzip'))
    old['frozen_challenger']=selected_score(old,selection()['selected']['name'])
    pieces=[];audit=pd.read_csv(OUT/'training_audit.csv').to_dict('records') if (OUT/'training_audit.csv').exists() else []
    for year in range(2020,2026):
        test=old[old.decision_date.str.startswith(str(year))].copy()
        train=x[x.endpoint.lt(f'{year}-01-01')]
        path=OUT/f'predictions_{year}.pkl.gz'
        if path.exists():pieces.append(pd.read_pickle(path,compression='gzip'));continue
        for c in CONFIGS:
            m,t=fit(train,c)
            assert t.endpoint.max()<f'{year}-01-01'
            pred=pd.Series(m.predict(test[COLS]),index=test.index)
            test[c['name']]=pred.groupby([test.decision_date,test.sector]).rank(pct=True).where(test.evidence_fraction.gt(0),.5)
            with (OUT/f'{c["name"]}_{year}.pkl').open('wb') as f:pickle.dump(m,f)
            audit=[r for r in audit if not (r['year']==year and r['model']==c['name'])]
            audit.append(dict(year=year,model=c['name'],rows=len(t),max_endpoint=t.endpoint.max(),test_start=test.decision_date.min()))
            pd.DataFrame(audit).to_csv(OUT/'training_audit.csv',index=False)
            print('FIT',year,c['name'],flush=True)
        test.to_pickle(path,compression='gzip');pieces.append(test)
    x=pd.concat(pieces,ignore_index=True)
    names=[]
    for c in CONFIGS:
        n=c['name'];names.append(n)
        for w in [.25,.5,.75]:
            k=f'{n}_blend{w}';x[k]=(1-w)*x.frozen_challenger+w*x[n];names.append(k)
    for target in ['balanced','return']:
        n=f'ensemble_{target}';x[n]=x[[c['name'] for c in CONFIGS if c['target']==target]].mean(axis=1);names.append(n)
    x.to_pickle(OUT/'predictions.pkl.gz',compression='gzip')
    summaries=[]
    for bounded in [False,True]:
        z=x.copy()
        if bounded:z.future_xirr=z.future_xirr.clip(-1,1)
        for start in range(0,len(names),5):
            a=aggregate(evaluate(z,['frozen_challenger']+names[start:start+5],top_ns=(1,3,5))).reset_index()
            a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
            pd.concat(summaries).drop_duplicates(['model','period','scope','top_n','return_treatment']).to_csv(OUT/'summary.csv',index=False)
            print('EVALUATE',bounded,start+len(names[start:start+5]),flush=True)
    a=pd.concat(summaries).drop_duplicates(['model','period','scope','top_n','return_treatment']).set_index(['model','period','scope','top_n','return_treatment'])[METRICS]
    trials=[]
    for n in names:
        differences=[]
        for ref in ['sector_incumbent','frozen_challenger']:
            d=a.loc[n]-a.loc[ref];d.shortfall=-d.shortfall;differences.extend(d.to_numpy().ravel())
        d=np.asarray(differences)
        trials.append(dict(model=n,strict_gate=bool((d>=-1e-12).all() and (d>1e-12).any()),regressing_cells=int((d < -1e-12).sum()),total_cells=len(d),worst_delta=float(d.min()),mean_delta=float(d.mean())))
    t=pd.DataFrame(trials).sort_values(['strict_gate','regressing_cells','mean_delta'],ascending=[False,True,False]);t.to_csv(OUT/'trials.csv',index=False)
    print(t.head(12).to_string(index=False),flush=True)

if __name__=='__main__':run()
