"""Profile-conditioned sector rankers: address transfer from base-only training."""
import json,gc,itertools
import numpy as np
import pandas as pd
import lightgbm as lgb
from full_coverage_challenger_20261008 import ROOT,KEYS,RAW,features,predictors,activity
from sector_championship_20261005 import metrics,METRICS
OUT=ROOT/'experiments/profile-aware-sector-20261008'
NEW=ROOT/'experiments/full-coverage-open-models-20261008'
CONFIGS=[dict(name=f'profile_{t}_{leaves}',target=t,leaves=leaves) for t,leaves in itertools.product(['balanced','defensive'],[7,15])]
PARAMS=['log_amount','lookback_months','log_interval','target_cagr']
COLS=predictors()+['volume_active_fraction','observations_1y']+PARAMS

def prepare():
    OUT.mkdir(exist_ok=True)
    protocol={'hypothesis':'Base-only ranker transfer loses across contribution, lookback and target settings. Learn all nine profiles with explicit settings and equal date/profile/sector query weights.',
      'configs':CONFIGS,'features':COLS,'feature_storage':'float32 predictor matrix; outcomes retained at source precision','trees':120,'learning_rate':.035,
      'folds':list(range(2020,2026)),'purge':'Actual outcome endpoint strictly before test-year January 1.',
      'selection':'All dates previously exposed. No fresh-holdout claim. 24 blends evaluated across all profiles, raw/capped, Top1/3/5 and rank IC.',
      'blends':[.025,.05,.1,.2,.35,.5],'anchor':'Frozen CatBoost/ridge blend from previous round; no profile-specific manual overrides.',
      'data_limits':'Current-survivor universe and current sector classifications; extreme/corporate-action label concerns remain. Nine profiles share stocks/outcomes and are not independent samples.'}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    path=OUT/'prepared.pkl.gz'
    if path.exists():return
    x=pd.read_pickle(ROOT/'experiments/sector-championship-20261005/enhanced.pkl.gz',compression='gzip')
    keep=KEYS+['sector','period','sector_incumbent','future_xirr','future_drawdown','future_shortfall']+RAW
    x=x[keep].copy();gc.collect()
    x=pd.concat([features(g) for _,g in x.groupby('profile_name')],ignore_index=True)
    x=activity(x)
    metadata=json.loads((ROOT/'research/protocols/personalized_official_action_tournament_v1.json').read_text())['profiles']
    for name in metadata:
        p=metadata[name];mask=x.profile_name.eq(name)
        x.loc[mask,PARAMS]=[np.log(p['amount']),p['lookback_months'],np.log(p['interval_days']),p['target_cagr']]
    original=pd.read_pickle(ROOT/'experiments/personalized-deep-championship-20261002/v3/prepared.pkl.gz',compression='gzip')[KEYS+['endpoint']]
    x=x.merge(original,on=KEYS,validate='one_to_one');del original;gc.collect()
    anchor=pd.concat([pd.read_csv(p,usecols=KEYS+['open_model','frozen_challenger']) for p in NEW.glob('locked_scores_*.csv.gz')],ignore_index=True)
    x=x.merge(anchor,on=KEYS,how='left',validate='one_to_one');del anchor;gc.collect()
    x=x[KEYS+['sector','period','endpoint','sector_incumbent','future_xirr','future_drawdown','future_shortfall','open_model','frozen_challenger']+COLS]
    x[COLS]=x[COLS].astype('float32')
    x.to_pickle(path,compression='gzip');print('PREPARED',len(x),flush=True)

def learn():
    x=pd.read_pickle(OUT/'prepared.pkl.gz',compression='gzip');audit=pd.read_csv(OUT/'training_audit.csv').to_dict('records') if (OUT/'training_audit.csv').exists() else []
    for year in range(2020,2026):
        output=OUT/f'predictions_{year}.csv.gz'
        if output.exists():continue
        t=x[x.endpoint.lt(f'{year}-01-01')].dropna(subset=['future_xirr','future_drawdown','future_shortfall']).copy()
        t=t[t.sector.ne('Unclassified')];t=t[t.groupby(['decision_date','profile_name','sector'])['isin'].transform('size').ge(5)]
        t=t.sort_values(['decision_date','profile_name','sector','isin']);g=t.groupby(['decision_date','profile_name','sector'],sort=False)
        r=g.future_xirr.rank(pct=True);d=g.future_drawdown.rank(pct=True);s=g.future_shortfall.rank(pct=True,ascending=False)
        w=1/g['isin'].transform('size');w=w/w.mean()
        test=x[x.decision_date.str.startswith(str(year))].copy()
        for c in CONFIGS:
            y=.5*r+.25*d+.25*s if c['target']=='balanced' else .25*r+.5*d+.25*s
            m=lgb.LGBMRanker(objective='rank_xendcg',n_estimators=120,num_leaves=c['leaves'],max_depth=5,min_child_samples=200,reg_lambda=30,learning_rate=.035,label_gain=list(range(10)),n_jobs=3,random_state=20261008,deterministic=True,force_col_wise=True,verbosity=-1)
            m.fit(t[COLS],np.floor(y*9).astype(int),group=g.size().to_numpy(),sample_weight=w)
            pred=pd.Series(m.predict(test[COLS]),index=test.index)
            test[c['name']]=pred.groupby([test.decision_date,test.profile_name,test.sector]).rank(pct=True).where(test.evidence_fraction.gt(0),.5)
            m.booster_.save_model(str(OUT/f'{c["name"]}_{year}.txt'))
            audit=[r for r in audit if not (r['year']==year and r['model']==c['name'])]
            audit.append(dict(year=year,model=c['name'],training_rows=len(t),training_profiles=t.profile_name.nunique(),max_training_endpoint=t.endpoint.max(),test_start=test.decision_date.min()))
            pd.DataFrame(audit).to_csv(OUT/'training_audit.csv',index=False);print('PROFILE FIT',year,c['name'],flush=True)
        test[KEYS+['sector','period','sector_incumbent','future_xirr','future_drawdown','future_shortfall','open_model','frozen_challenger']+[c['name'] for c in CONFIGS]].to_csv(output,index=False)

def evaluate(blend_weights=None, append=False):
    x=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    names=[]
    for c in CONFIGS:
        for w in (blend_weights if blend_weights is not None else [.025,.05,.1,.2,.35,.5]):
            n=f'{c["name"]}_blend{w}';x[n]=(1-w)*x.open_model+w*x[c['name']];names.append(n)
    summaries=[pd.read_csv(OUT/'summary.csv')] if append and (OUT/'summary.csv').exists() else []
    # Common production cohort and expanded cohort are evaluated separately.
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        # metrics() requires every compared model finite. Expanded comparisons
        # compare only full-coverage challengers, never fill missing production scores.
        refs=['open_model','frozen_challenger']+(['sector_incumbent'] if scope=='common' else [])
        for bounded in [False,True]:
            zz=z.copy()
            if bounded:zz.future_xirr=zz.future_xirr.clip(-1,1)
            for i in range(0,len(names),6):
                q=metrics(zz,refs+names[i:i+6],top_ns=(1,3,5))
                a=q.groupby(['model','period','profile','top_n','sector'])[METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
                a['scope']=scope;a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
                pd.concat(summaries).drop_duplicates(['model','period','profile','top_n','scope','return_treatment']).to_csv(OUT/'summary.csv',index=False)
                print('PROFILE EVALUATE',scope,bounded,i,flush=True)
    a=pd.concat(summaries).drop_duplicates(['model','period','profile','top_n','scope','return_treatment']).set_index(['model','period','profile','top_n','scope','return_treatment'])[METRICS];trials=[]
    for n in names:
        cells=[];top3=[]
        for ref in ['open_model','frozen_challenger','sector_incumbent']:
            d=(a.loc[n]-a.loc[ref]).dropna();d.shortfall=-d.shortfall;cells.extend(d.to_numpy().ravel());top3.extend(d.xs(3,level='top_n').to_numpy().ravel())
        trials.append(dict(model=n,strict_gate=all(v>=-1e-12 for v in cells) and any(v>1e-12 for v in cells),regressing_cells=sum(v < -1e-12 for v in cells),total_cells=len(cells),top3_regressing_cells=sum(v < -1e-12 for v in top3),top3_cells=len(top3),mean_delta=float(np.mean(cells))))
    t=pd.DataFrame(trials)
    if append and (OUT/'trials.csv').exists():t=pd.concat([pd.read_csv(OUT/'trials.csv'),t]).drop_duplicates('model',keep='last')
    t=t.sort_values(['strict_gate','top3_regressing_cells','regressing_cells'],ascending=[False,True,True]);t.to_csv(OUT/'trials.csv',index=False);print(t.head(8).to_string(index=False),flush=True)

if __name__=='__main__':prepare();learn();evaluate()
