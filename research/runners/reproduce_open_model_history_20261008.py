"""Restore disposable predictions from saved fits and verify all first-round metrics."""
import json,pickle,zipfile
import numpy as np
import pandas as pd
from full_coverage_open_models_20261008 import OUT,PRIOR,CONFIGS,COLS,activity,selected_score,selection,aggregate
from fast_sector_evaluation_20261008 import evaluate

def run():
    old=activity(pd.read_pickle(PRIOR/'predictions.pkl.gz',compression='gzip'))
    old['frozen_challenger']=selected_score(old,selection()['selected']['name'])
    pieces=[]
    for year in range(2020,2026):
        test=old[old.decision_date.str.startswith(str(year))].copy()
        for c in CONFIGS:
            path=OUT/f'{c["name"]}_{year}.pkl'
            if path.exists():
                with path.open('rb') as f:model=pickle.load(f)
            else:
                with zipfile.ZipFile(OUT/'extra_trees_fitted_models.zip') as z:model=pickle.loads(z.read(path.name))
            pred=pd.Series(model.predict(test[COLS]),index=test.index)
            test[c['name']]=pred.groupby([test.decision_date,test.sector]).rank(pct=True).where(test.evidence_fraction.gt(0),.5)
        test.to_pickle(OUT/f'predictions_{year}.pkl.gz',compression='gzip');pieces.append(test)
        print('REPLAYED',year,flush=True)
    x=pd.concat(pieces,ignore_index=True);names=[]
    for c in CONFIGS:
        n=c['name'];names.append(n)
        for w in [.25,.5,.75]:
            k=f'{n}_blend{w}';x[k]=(1-w)*x.frozen_challenger+w*x[n];names.append(k)
    for target in ['balanced','return']:
        n=f'ensemble_{target}';x[n]=x[[c['name'] for c in CONFIGS if c['target']==target]].mean(axis=1);names.append(n)
    x.to_pickle(OUT/'predictions.pkl.gz',compression='gzip')
    retained=pd.read_csv(OUT/'summary.csv').set_index(['model','period','scope','top_n','return_treatment'])
    checked=0
    for bounded in [False,True]:
        z=x.copy()
        if bounded:z.future_xirr=z.future_xirr.clip(-1,1)
        for start in range(0,len(names),10):
            a=aggregate(evaluate(z,['frozen_challenger']+names[start:start+10],(1,3,5))).reset_index();a['return_treatment']='capped' if bounded else 'raw'
            a=a.set_index(['model','period','scope','top_n','return_treatment'])
            np.testing.assert_allclose(a.to_numpy(),retained.loc[a.index,a.columns].to_numpy(),atol=1e-12,rtol=1e-12)
            checked+=len(a)
            print('METRICS REPLAYED',bounded,start+len(names[start:start+10]),flush=True)
    (OUT/'historical_reproduction.json').write_text(json.dumps({'annual_fits_replayed':72,'candidate_configurations':50,'metric_rows_checked_including_repeated_references':checked,'tolerance':1e-12,'match':True,'retrained':False,'prediction_caches_restored':True},indent=2))

if __name__=='__main__':run()
