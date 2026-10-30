"""Recompute annual scores from serialized models and original historical inputs."""
import argparse,json
import numpy as np
import pandas as pd
import lightgbm as lgb
import sector_price_rebuild_20261010 as p

def run(family):
    base=p.OUT;folder=base if family=='rebuilt' else p.ROOT/'experiments/sector-yetirank-20261010'
    if family=='yeti':
        from sector_yetirank_20261010 import CatBoostRanker,CONFIGS
    else:CONFIGS=p.CONFIGS
    x=pd.read_pickle(base/'prepared.pkl.gz',compression='gzip');rows=[]
    for year in range(2020,2026):
        test=x[x.decision_date.str.startswith(str(year))].copy()
        saved=pd.read_csv(folder/f'predictions_{year}.csv.gz').set_index(p.KEYS)
        for c in CONFIGS:
            if family=='rebuilt':
                m=lgb.Booster(model_file=str(folder/f'{c["name"]}_{year}.txt'))
                raw=pd.Series(m.predict(test[p.COLS],num_threads=2),index=test.index)
                scores=raw.groupby([test.decision_date,test.profile_name,test.sector]).rank(pct=True).where(test.evidence_fraction.gt(0),.5)
            else:
                m=CatBoostRanker();m.load_model(str(folder/f'{c["name"]}_{year}.cbm'));scores=p.rank_prediction(m,test)
            a=test[p.KEYS].copy();a['score']=scores
            expected=saved[c['name']];actual=a.set_index(p.KEYS).score.reindex(expected.index)
            error=float(np.max(np.abs(expected-actual)));assert actual.notna().all() and error<=1e-15
            rows.append(dict(year=year,model=c['name'],rows=len(test),maximum_absolute_error=error))
        print('REPLAY',family,year,flush=True)
    pd.DataFrame(rows).to_csv(folder/'historical_model_replay.csv',index=False)
    doc={'annual_models_verified':len(rows),'prediction_values_verified':sum(r['rows'] for r in rows),'maximum_absolute_error':max(r['maximum_absolute_error'] for r in rows),'tolerance':1e-15,'source':'Original prepared historical inputs; saved annual models; entire annual test cohorts.'}
    (folder/'historical_model_replay.json').write_text(json.dumps(doc,indent=2));print(json.dumps(doc),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--family',choices=['rebuilt','yeti'],default='rebuilt');run(a.parse_args().family)
