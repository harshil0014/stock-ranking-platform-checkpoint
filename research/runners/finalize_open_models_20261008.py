"""Freeze best diagnostic challenger, export all stocks, test nine profiles."""
import json,pickle,hashlib,shutil,gc
import pandas as pd
import numpy as np
from full_coverage_open_models_20261008 import ROOT,OUT,PRIOR,CONFIGS,COLS,fit,activity,evaluate,aggregate
from full_coverage_challenger_20261008 import features,KEYS,METRICS,RAW
from fast_sector_evaluation_20261008 import evaluate

def specification(name):
    if name.startswith('pair__'):
        _,a,b,w=name.split('__')
        return [c for c in CONFIGS if c['name'] in [a,b]],float(w)
    if name.startswith('ensemble_'):
        return [c for c in CONFIGS if c['target']==name.split('_',1)[1]],1.
    source,_,weight=name.partition('_blend')
    return [c for c in CONFIGS if c['name']==source],float(weight) if weight else 1.

def score(x,models,weight,baseline):
    predictions=[]
    for model in models:
        pred=pd.Series(model.predict(x[COLS]),index=x.index)
        predictions.append(pred.groupby([x.decision_date,x.sector]).rank(pct=True).where(x.evidence_fraction.gt(0),.5))
    value=(1-weight)*baseline+weight*pd.concat(predictions,axis=1).mean(axis=1)
    return value.where(x.evidence_fraction.gt(0),.5)

def run():
    trials=pd.read_csv(OUT/'trials.csv')
    if (OUT/'pair_trials.csv').exists():trials=pd.concat([trials,pd.read_csv(OUT/'pair_trials.csv')])
    trials=trials.sort_values(['strict_gate','regressing_cells','mean_delta'],ascending=[False,True,False])
    chosen=trials.iloc[0];name=chosen.model;configs,weight=specification(name)
    assert configs
    selected={'name':name,'status':'BASE_GATE_PASS_REQUIRES_PROFILE_CHECK' if bool(chosen.strict_gate) else 'RESEARCH_CANDIDATE_WITH_REGRESSIONS','production_replaced':False,'fresh_holdout':False,'configs':configs,'weight':weight,'as_of':'2026-10-03','regressing_base_cells':int(chosen.regressing_cells)}
    (OUT/'selection.json').write_text(json.dumps(selected,indent=2))
    anchor=OUT/'frozen_anchor';anchor.mkdir(exist_ok=True)
    for source in [PRIOR/'active_selection.json',PRIOR/'current_training.json',*PRIOR.glob('selected_rank_xendcg_*.txt')]:
        shutil.copy2(source,anchor/source.name)
    current=pd.read_csv(PRIOR/'current_all_stock_rankings.csv')
    x=features(current);train=activity(pd.read_pickle(PRIOR/'historical.pkl.gz',compression='gzip'));train=train[train.endpoint.lt('2026-10-03')]
    models=[];audit=[]
    for c in configs:
        m,used=fit(train,c);models.append(m)
        with (OUT/f'current_{c["name"]}.pkl').open('wb') as f:pickle.dump(m,f)
        audit.append({'model':c['name'],'rows':len(used),'max_training_endpoint':used.endpoint.max()})
    x['open_model_score']=score(x,models,weight,x.challenger_score)
    x['open_model_sector_rank']=x.open_model_score.groupby(x.sector).rank(method='min',ascending=False)
    assert len(x)==4436 and x['isin'].nunique()==4436 and np.isfinite(x.open_model_score).all()
    assert x.loc[x.evidence_fraction.eq(0),'open_model_score'].eq(.5).all()
    x['selected_model']=name
    x.sort_values(['sector','open_model_sector_rank','isin']).to_csv(OUT/'current_all_stock_rankings.csv',index=False)
    (OUT/'current_training.json').write_text(json.dumps(audit,indent=2))
    print('CURRENT',name,len(x),flush=True)
    del train,current,x,models;gc.collect()
    raw=pd.read_pickle(ROOT/'experiments/sector-championship-20261005/enhanced.pkl.gz',compression='gzip')
    raw=raw.loc[raw.decision_date.ge('2020-01-01'),KEYS+['sector','period','sector_incumbent','future_xirr','future_drawdown','future_shortfall']+RAW].copy();gc.collect()
    frozen=pd.read_csv(PRIOR/'locked_all_profile_predictions.csv.gz',usecols=KEYS+['challenger']).rename(columns={'challenger':'frozen_challenger'})
    summaries=[]
    for profile,g in raw.groupby('profile_name'):
        g=g[g.decision_date.ge('2020-01-01')].copy();g=activity(features(g));g=g.merge(frozen,on=KEYS,validate='one_to_one')
        g['open_model']=np.nan
        for year in range(2020,2026):
            mask=g.decision_date.str.startswith(str(year));part=g.loc[mask];models=[]
            for c in configs:
                with (OUT/f'{c["name"]}_{year}.pkl').open('rb') as f:models.append(pickle.load(f))
            g.loc[mask,'open_model']=score(part,models,weight,part.frozen_challenger)
        for bounded in [False,True]:
            z=g.copy()
            if bounded:z.future_xirr=z.future_xirr.clip(-1,1)
            q=evaluate(z,['frozen_challenger','open_model'],top_ns=(1,3,5))
            if profile=='base7500':q.to_csv(OUT/f'selected_base_{"capped" if bounded else "raw"}_query_metrics.csv.gz',index=False)
            a=aggregate(q).reset_index();a['profile']=profile;a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
        pd.concat(summaries).to_csv(OUT/'all_profile_summary.csv',index=False)
        print('PROFILE',profile,flush=True)
    a=pd.concat(summaries).set_index(['model','profile','period','scope','top_n','return_treatment'])[METRICS]
    differences=[]
    for ref in ['sector_incumbent','frozen_challenger']:
        d=a.loc['open_model']-a.loc[ref];d.shortfall=-d.shortfall;d['baseline']=ref;differences.append(d.reset_index())
    d=pd.concat(differences);d.to_csv(OUT/'all_profile_improvements.csv',index=False)
    selected.update(profile_comparison_cells=int(d[METRICS].size),profile_regressing_cells=int(d[METRICS].lt(-1e-12).sum().sum()),full_coverage=4436)
    selected['status']='RETROSPECTIVE_ALL_PROFILE_GATE_PASS' if selected['regressing_base_cells']==0 and selected['profile_regressing_cells']==0 else 'RESEARCH_CANDIDATE_WITH_REGRESSIONS'
    selected['current_export_sha256']=hashlib.sha256((OUT/'current_all_stock_rankings.csv').read_bytes()).hexdigest()
    (OUT/'selection.json').write_text(json.dumps(selected,indent=2))
    print(json.dumps(selected,indent=2),flush=True)

if __name__=='__main__':run()
