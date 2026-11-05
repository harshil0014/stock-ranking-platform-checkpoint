"""Risk-budgeted professor selections and one locked later-period comparison."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import argparse,datetime,hashlib,json,pickle
import numpy as np
import pandas as pd
from stock_research.constrained_selection import select_three
from stock_research.residual_history import weekly_prices,residual_features
from residual_challengers_20261105 import evaluator,Q

ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/champion-open-search-20261105'
OUT=ROOT/'experiments/champion-open-search-20261105'
POLICIES={
    'constrained_residual':('residual_momentum20',False),
    'constrained_high':('residual_high20',False),
    'risk_constrained_residual':('residual_momentum20',True),
    'risk_constrained_high':('residual_high20',True),
}


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def register():
    path=ROOT/'research/research_variant_ledger.csv'
    frame=pd.read_csv(path)
    prior=set(frame.id)
    rows=[]
    for name in ['risk_constrained_residual','risk_constrained_high','locked_transfer_diagnostic']:
        key='champion_open_search_20261105::'+name
        if key not in prior:
            rows.append(dict(id=key,family='champion_open_search_20261105',name=name,
                source='research/protocols/champion_open_search_20261105.md',
                category='diagnostic_or_policy_attempt' if 'diagnostic' in name else 'configuration'))
    pd.concat([frame,pd.DataFrame(rows)],ignore_index=True).to_csv(path,index=False)


def solve(frame,names,period):
    receipts=[]
    for date,dated in frame.groupby('decision_date',sort=True):
        for sector,g in dated.groupby('sector',sort=True):
            g=g.sort_values('isin')
            champion=g.sort_values(['champion','isin'],ascending=[False,True]).head(3)
            positions=g.index.get_indexer(champion.index)
            for name in names:
                objective,use_risk=POLICIES[name]
                risk=g.downside252.to_numpy() if use_risk else None
                score,r=select_three(g[objective].to_numpy(),g[Q].to_numpy(),positions,risk=risk)
                frame.loc[g.index,name]=score
                selected=g.iloc[np.argsort(-score)[:3]]
                difference=selected[Q].sum().to_numpy()-champion[Q].sum().to_numpy()
                assert (difference>=-1e-7).all()
                if use_risk:assert selected.downside252.sum()<=champion.downside252.sum()+1e-7
                receipts.append(dict(decision_date=date,sector=sector,model=name,
                    optimal=r['optimal'],minimum_factor_sum_gain=difference.min(),
                    risk_sum_delta=r['historical_risk_sum_delta']))
        print('SOLVED',period,date,len(receipts),flush=True)
        pd.DataFrame(receipts).to_csv(OUT/(period+'_solver_receipts.csv'),index=False)
    assert np.isfinite(frame[['champion']+names]).all().all()
    return frame


def evaluate(frame,names,period):
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:
        paths=pickle.load(f)
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv')
    actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    helper=evaluator()
    helper.OUT=OUT
    return helper.evaluate(frame,['champion']+names,period,paths,actions)


def development():
    register()
    protocol=ROOT/'research/protocols/champion_open_search_20261105.md'
    source=ROOT/'work/constrained-ranking-20261105/development_scored.pkl.gz'
    save('development_input_receipts.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=digest(p))
        for p in [protocol,source,Path(__file__),ROOT/'src/stock_research/constrained_selection.py']])
    save('started.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),protocol_sha256=digest(protocol)))
    frame=pd.read_pickle(source,compression='gzip')
    assert frame.decision_date.between('2020-01-01','2023-12-31').all()
    frame=solve(frame,['risk_constrained_residual','risk_constrained_high'],'development')
    frame.to_pickle(WORK/'development_scored.pkl.gz',compression='gzip')
    summary,_,pairs=evaluate(frame,list(POLICIES),'development')
    candidate=pairs[pairs.policy.eq('global_top20')&pairs.model.ne('champion')].copy()
    candidate['ic_delta']=candidate.model.map(summary.rank_ic)-summary.loc['champion','rank_ic']
    winner=candidate.sort_values(['xirr_delta','ic_delta','model'],ascending=[False,False,True]).iloc[0]['model']
    lock=dict(selected=winner,selection='Highest development matched Top20 mean XIRR gain, IC tie-breaker; exploratory tradeoffs accepted',
        locked_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        policy=POLICIES[winner],protocol_sha256=digest(protocol),
        policy_code_sha256=digest(ROOT/'src/stock_research/constrained_selection.py'),
        runner_sha256=digest(Path(__file__)),
        development_scores_sha256=digest(WORK/'development_scored.pkl.gz'),
        development_pairs_sha256=digest(OUT/'development_portfolio_pairs.csv'),
        development_summary_sha256=digest(OUT/'development_summary.csv'),
        later_period_scored=False)
    save('selection_lock.json',lock)
    print('LOCKED',json.dumps(lock),flush=True)


def transfer():
    lock=json.loads((OUT/'selection_lock.json').read_text())
    assert lock['policy_code_sha256']==digest(ROOT/'src/stock_research/constrained_selection.py')
    assert lock['runner_sha256']==digest(Path(__file__))
    assert lock['development_pairs_sha256']==digest(OUT/'development_portfolio_pairs.csv')
    winner=lock['selected']
    source=ROOT/'work/professor-frontier-20261101/corrected_panel.pkl.gz'
    allrows=pd.read_pickle(source,compression='gzip')
    x=allrows[allrows.decision_date.between('2024-01-01','2025-12-31')].copy()
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:
        paths=pickle.load(f)
    frames=[];coverage=[]
    for date,g in x.groupby('decision_date',sort=True):
        g=g.sort_values('isin').copy()
        prices=np.column_stack([weekly_prices(paths[i],date) if i in paths else np.full(157,np.nan) for i in g['isin']])
        features=residual_features(np.diff(np.log(prices),axis=0),g.sector)
        g[['residual_momentum','residual_high']]=features
        original=len(g)
        g=g[np.isfinite(g[['residual_momentum','residual_high']]).all(axis=1)].copy()
        g=g[g.groupby('sector')['isin'].transform('size').ge(5)].copy()
        g['champion']=g.champion_percentile
        for col in Q+['champion','residual_momentum','residual_high']:
            g[col]=g.groupby('sector')[col].rank(pct=True)
        g['residual_momentum20']=.8*g.champion+.2*g.residual_momentum
        g['residual_high20']=.8*g.champion+.2*g.residual_high
        frames.append(g)
        coverage.append(dict(decision_date=date,original=original,common=len(g)))
        print('TRANSFER FEATURES',date,len(g),flush=True)
    del paths
    frame=pd.concat(frames,ignore_index=True)
    pd.DataFrame(coverage).to_csv(OUT/'transfer_feature_coverage.csv',index=False)
    frame=solve(frame,[winner],'transfer')
    frame.to_pickle(WORK/'transfer_scored.pkl.gz',compression='gzip')
    evaluate(frame,[winner],'transfer')
    save('transfer_receipt.json',dict(selected=winner,selection_lock_sha256=digest(OUT/'selection_lock.json'),
        scored_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        source_sha256=digest(source),source=str(source),rows=len(frame),dates=frame.decision_date.nunique(),
        interpretation='Previously exposed historical transfer diagnostic, not fresh holdout',retuned=False))
    print('TRANSFER COMPLETE',winner,flush=True)


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    WORK.mkdir(exist_ok=True)
    parser=argparse.ArgumentParser()
    parser.add_argument('stage',choices=['development','transfer'])
    stage=parser.parse_args().stage
    development() if stage=='development' else transfer()
