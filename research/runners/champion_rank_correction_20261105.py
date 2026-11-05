"""Annual mature-label champion-error learning with two fixed ranking policies."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import json,pickle,hashlib,datetime
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from stock_research.residual_history import weekly_prices,residual_features
from stock_research.constrained_selection import select_three
from residual_challengers_20261105 import Q,evaluator
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/champion-rank-correction-20261105'
OUT=ROOT/'experiments/champion-rank-correction-20261105'
FEATURES=Q+['residual_momentum','residual_high','champion','downside252','volatility252','return21']


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(exist_ok=True)
    protocol=ROOT/'research/protocols/champion_rank_correction_20261105.md'
    save('frozen.json',dict(protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),started_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    registry=ROOT/'research/research_variant_ledger.csv'
    ledger=pd.read_csv(registry)
    additions=[]
    for name in ['error_corrected_raw','error_corrected_professor']:
        key='champion_rank_correction_20261105::'+name
        if key not in set(ledger.id):additions.append(dict(id=key,family='champion_rank_correction_20261105',name=name,source=protocol.relative_to(ROOT).as_posix(),category='configuration'))
    pd.concat([ledger,pd.DataFrame(additions)],ignore_index=True).to_csv(registry,index=False)
    source=ROOT/'work/professor-frontier-20261101/corrected_panel.pkl.gz'
    allrows=pd.read_pickle(source,compression='gzip')
    past=allrows[allrows.decision_date.between('2016-01-01','2019-12-31')].copy()
    frames=[]
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:paths=pickle.load(f)
    for date,g in past.groupby('decision_date'):
        dest=WORK/('features_'+date+'.pkl.gz')
        if dest.exists():g=pd.read_pickle(dest,compression='gzip')
        else:
            g=g.sort_values('isin').copy()
            prices=np.column_stack([weekly_prices(paths[i],date) if i in paths else np.full(157,np.nan) for i in g['isin']])
            g[['residual_momentum','residual_high']]=residual_features(np.diff(np.log(prices),axis=0),g.sector)
            g=g[np.isfinite(g[['residual_momentum','residual_high']]).all(axis=1)].copy()
            g=g[g.groupby('sector')['isin'].transform('size').ge(5)].copy()
            g['champion']=g.champion_percentile
            for col in Q+['champion','residual_momentum','residual_high']:g[col]=g.groupby('sector')[col].rank(pct=True)
            g.to_pickle(dest,compression='gzip')
        frames.append(g)
        print('PAST FEATURES',date,len(g),flush=True)
    development=pd.read_pickle(ROOT/'work/novel-champion-20261105/development_scored.pkl.gz',compression='gzip')
    combined=pd.concat(frames+[development],ignore_index=True)
    assert combined.decision_date.lt('2024-01-01').all()
    known=combined[combined.new_xirr.notna()].copy()
    known=known[known.groupby(['decision_date','sector'])['isin'].transform('size').ge(5)].copy()
    known['rank_error']=known.groupby(['decision_date','sector']).new_xirr.rank(pct=True)-known.champion
    scored=development.copy();folds=[]
    for year in range(2020,2024):
        train=known[known.new_endpoint.lt(f'{year}-01-01')].copy()
        test=scored[scored.decision_date.str.startswith(str(year))]
        assert train.new_endpoint.max()<test.decision_date.min()
        weights=1/train.groupby(['decision_date','sector'])['isin'].transform('size').to_numpy(copy=True)
        weights/=weights.mean()
        model=LGBMRegressor(objective='regression',n_estimators=80,learning_rate=.03,num_leaves=7,max_depth=3,min_child_samples=100,reg_lambda=30,random_state=20261105,n_jobs=1,deterministic=True,force_col_wise=True,verbosity=-1)
        model.fit(train[FEATURES],train.rank_error,sample_weight=weights)
        predicted=model.predict(test[FEATURES])
        scored.loc[test.index,'predicted_rank_error']=predicted
        scored.loc[test.index,'error_corrected_raw']=test.champion+.25*predicted
        file=WORK/f'model_{year}.txt';model.booster_.save_model(str(file))
        folds.append(dict(year=year,train_rows=len(train),train_dates=train.decision_date.nunique(),last_label_endpoint=train.new_endpoint.max(),first_test_date=test.decision_date.min(),model_sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
        print('FIT',year,len(train),flush=True)
    pd.DataFrame(folds).to_csv(OUT/'folds.csv',index=False)
    solver=[]
    for (date,sector),g in scored.groupby(['decision_date','sector']):
        g=g.sort_values('isin');champ=g.sort_values(['champion','isin'],ascending=[False,True]).head(3)
        score,r=select_three(g.error_corrected_raw.to_numpy(),g[Q].to_numpy(),g.index.get_indexer(champ.index))
        scored.loc[g.index,'error_corrected_professor']=score
        solver.append(dict(decision_date=date,sector=sector,optimal=r['optimal'],minimum_factor_gain=min(r['factor_sum_differences'])))
    pd.DataFrame(solver).to_csv(OUT/'solver.csv',index=False)
    scored.to_pickle(WORK/'development_scored.pkl.gz',compression='gzip')
    helper=evaluator();helper.OUT=OUT
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv');actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    helper.evaluate(scored,['champion','error_corrected_raw','error_corrected_professor'],'development',paths,actions)
    save('completion.json',dict(rows=len(scored),dates=scored.decision_date.nunique(),annual_fits=len(folds),exposed_evaluated=False,adaptive_development=True,source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),documented_attempts=len(pd.read_csv(registry))))
    print('COMPLETE',flush=True)


if __name__=='__main__':main()
