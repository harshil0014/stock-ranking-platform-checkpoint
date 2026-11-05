"""Frozen professor-preserving rank correction on later historical dates."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import json,pickle,hashlib,datetime
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from stock_research.constrained_selection import select_three
from residual_challengers_20261105 import evaluator,Q
from champion_rank_correction_20261105 import FEATURES
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/rank-correction-transfer-20261106'
OUT=ROOT/'experiments/rank-correction-transfer-20261106'
NAME='error_corrected_professor'


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(exist_ok=True)
    protocol=ROOT/'research/protocols/rank_correction_transfer_20261106.md'
    files=list((ROOT/'work/champion-rank-correction-20261105').glob('features_*.pkl.gz'))
    dev=ROOT/'work/novel-champion-20261105/development_scored.pkl.gz'
    transfer=ROOT/'work/champion-open-search-20261105/transfer_scored.pkl.gz'
    receipts=[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files+[dev,transfer,protocol,Path(__file__),ROOT/'src/stock_research/constrained_selection.py']]
    save('frozen_input_receipts.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),candidate=NAME,files=receipts))
    registry=ROOT/'research/research_variant_ledger.csv';ledger=pd.read_csv(registry)
    key='rank_correction_transfer_20261106::locked_professor_transfer'
    if key not in set(ledger.id):
        ledger=pd.concat([ledger,pd.DataFrame([dict(id=key,family='rank_correction_transfer_20261106',name='locked_professor_transfer',source=protocol.relative_to(ROOT).as_posix(),category='diagnostic_or_policy_attempt')])],ignore_index=True)
        ledger.to_csv(registry,index=False)
    frames=[pd.read_pickle(p,compression='gzip') for p in files+[dev,transfer]]
    allrows=pd.concat(frames,ignore_index=True)
    assert not allrows.duplicated(['isin','decision_date']).any()
    known=allrows[allrows.new_xirr.notna()].copy()
    known=known[known.groupby(['decision_date','sector'])['isin'].transform('size').ge(5)].copy()
    known['rank_error']=known.groupby(['decision_date','sector']).new_xirr.rank(pct=True)-known.champion
    scored=allrows[allrows.decision_date.between('2024-01-01','2025-12-31')].copy()
    folds=[]
    for year in [2024,2025]:
        train=known[known.new_endpoint.lt(f'{year}-01-01')].copy()
        test=scored[scored.decision_date.str.startswith(str(year))]
        assert train.new_endpoint.max()<f'{year}-01-01'<=test.decision_date.min()
        weight=1/train.groupby(['decision_date','sector'])['isin'].transform('size').to_numpy(copy=True)
        weight/=weight.mean()
        model=LGBMRegressor(objective='regression',n_estimators=80,learning_rate=.03,num_leaves=7,max_depth=3,min_child_samples=100,reg_lambda=30,random_state=20261105,n_jobs=1,deterministic=True,force_col_wise=True,verbosity=-1)
        model.fit(train[FEATURES],train.rank_error,sample_weight=weight)
        predicted=model.predict(test[FEATURES])
        scored.loc[test.index,'predicted_rank_error']=predicted
        scored.loc[test.index,'error_corrected_raw']=test.champion+.25*predicted
        path=WORK/f'model_{year}.txt';model.booster_.save_model(str(path))
        folds.append(dict(year=year,train_rows=len(train),train_dates=train.decision_date.nunique(),last_label_endpoint=train.new_endpoint.max(),first_test_date=test.decision_date.min(),model_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        print('FIT',year,len(train),flush=True)
    pd.DataFrame(folds).to_csv(OUT/'folds.csv',index=False)
    receipts=[]
    for (date,sector),g in scored.groupby(['decision_date','sector']):
        g=g.sort_values('isin');champ=g.sort_values(['champion','isin'],ascending=[False,True]).head(3)
        score,r=select_three(g.error_corrected_raw.to_numpy(),g[Q].to_numpy(),g.index.get_indexer(champ.index))
        scored.loc[g.index,NAME]=score
        selected=g.iloc[np.argsort(-score)[:3]]
        receipts.append(dict(decision_date=date,sector=sector,optimal=r['optimal'],minimum_factor_gain=min(r['factor_sum_differences']),changed=set(selected['isin'])!=set(champ['isin'])))
    pd.DataFrame(receipts).to_csv(OUT/'solver_receipts.csv',index=False)
    scored.to_pickle(WORK/'transfer_scored.pkl.gz',compression='gzip')
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:paths=pickle.load(f)
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv');actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    helper=evaluator();helper.OUT=OUT
    helper.evaluate(scored,['champion',NAME],'transfer',paths,actions)
    save('completion.json',dict(candidate=NAME,rows=len(scored),dates=scored.decision_date.nunique(),fits=2,parameters_changed=False,source_cohort='Saved feature-only residual cohort',fresh_holdout=False,documented_attempts=len(pd.read_csv(registry))))
    print('TRANSFER COMPLETE',flush=True)


if __name__=='__main__':main()
