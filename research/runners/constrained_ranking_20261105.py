"""Development-only constrained reranking of two saved residual objectives."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import json,pickle,hashlib,datetime,sys
import numpy as np
import pandas as pd
from stock_research.constrained_selection import select_three
from residual_challengers_20261105 import evaluator,Q
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/constrained-ranking-20261105'
OUT=ROOT/'experiments/constrained-ranking-20261105'
CANDIDATES={'constrained_residual':'residual_momentum20','constrained_high':'residual_high20'}


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')


def main():
    OUT.mkdir(exist_ok=True)
    protocol=ROOT/'research/protocols/constrained_ranking_20261105.md'
    sources=[protocol,ROOT/'work/novel-champion-20261105/development_scored.pkl.gz',ROOT/'src/stock_research/constrained_selection.py',Path(__file__)]
    save('input_receipts.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sources])
    save('frozen.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),protocol_sha256=hashlib.sha256(protocol.read_bytes()).hexdigest()))
    registry=ROOT/'research/research_variant_ledger.csv';ledger=pd.read_csv(registry);prior=set(ledger.id)
    additions=[dict(id='constrained_ranking_20261105::'+n,family='constrained_ranking_20261105',name=n,source=protocol.relative_to(ROOT).as_posix(),category='configuration') for n in CANDIDATES if 'constrained_ranking_20261105::'+n not in prior]
    ledger=pd.concat([ledger,pd.DataFrame(additions)],ignore_index=True);ledger.to_csv(registry,index=False)
    x=pd.read_pickle(sources[1],compression='gzip')
    assert x.decision_date.between('2020-01-01','2023-12-31').all()
    receipts=[]
    for date,gdate in x.groupby('decision_date',sort=True):
        for sector,g in gdate.groupby('sector',sort=True):
            g=g.sort_values('isin');champ=g.sort_values(['champion','isin'],ascending=[False,True]).head(3)
            indices=g.index.get_indexer(champ.index)
            for name,objective in CANDIDATES.items():
                score,receipt=select_three(g[objective].to_numpy(),g[Q].to_numpy(),indices)
                x.loc[g.index,name]=score
                selected=g.iloc[np.argsort(-score)[:3]]
                difference=selected[Q].sum().to_numpy()-champ[Q].sum().to_numpy()
                assert (difference>=-1e-7).all(),'Constraint violation in actual output order'
                receipts.append(dict(decision_date=date,sector=sector,model=name,optimal=receipt['optimal'],status=receipt['status'],minimum_factor_sum_gain=difference.min(),changed=set(selected['isin'])!=set(champ['isin'])))
        print('SOLVED',date,'queries',len(receipts),flush=True)
        pd.DataFrame(receipts).to_csv(OUT/'solver_receipts.csv',index=False)
    assert np.isfinite(x[list(CANDIDATES)]).all().all()
    x.to_pickle(WORK/'development_scored.pkl.gz',compression='gzip')
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:paths=pickle.load(f)
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv');actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    old=evaluator();old.OUT=OUT
    summary,perdate,pairs=old.evaluate(x,['champion']+list(CANDIDATES),'development',paths,actions)
    portfolio=pd.read_csv(OUT/'development_portfolios.csv');receipts=pd.DataFrame(receipts);decisions=[]
    for name in CANDIDATES:
        r=summary.loc[name];b=summary.loc['champion'];p=pairs[pairs.model.eq(name)&pairs.policy.eq('global_top20')].iloc[0]
        a=portfolio[portfolio.model.eq(name)&portfolio.policy.eq('global_top20')].merge(portfolio[portfolio.model.eq('champion')&portfolio.policy.eq('global_top20')],on='decision_date',suffixes=('_new','_old'))
        a['delta']=a.xirr_new-a.xirr_old;delta=a.delta.to_numpy();ordered=np.sort(delta);cut=int(len(ordered)*.1)
        winsor=np.clip(ordered,ordered[cut],ordered[-cut-1]).mean();lodo=min(np.delete(delta,k).mean() for k in range(len(delta)))
        years=a.groupby(a.decision_date.str[:4]).delta.mean();years.to_csv(OUT/(name+'_year_portfolio_delta.csv'))
        fallback=float(1-receipts[receipts.model.eq(name)].optimal.mean())
        constraints=bool(receipts[receipts.model.eq(name)].minimum_factor_sum_gain.ge(-1e-7).all())
        checks=dict(portfolio_gain=p.xirr_delta>=.01,winsor=winsor>0,lodo=lodo>0,annual=int(years.gt(0).sum())>=3,goal=r.top3_goal_hit>=b.top3_goal_hit,ic_noninferiority=r.rank_ic-b.rank_ic>=-.005,drawdown=p.drawdown_delta>=-.02,professor_constraints=constraints,fallback=fallback<=.01,support=p.matched_dates>=12 and r.supported_top3_dates>=12)
        decisions.append(dict(model=name,nominate=all(checks.values()),checks=checks,xirr_delta=p.xirr_delta,winsor_xirr_delta=winsor,worst_lodo_xirr_delta=lodo,positive_years=int(years.gt(0).sum()),fallback_fraction=fallback,ic_delta=r.rank_ic-b.rank_ic,clears_prior_head_floor=r.rank_ic-b.rank_ic>=.010134924))
    save('decision.json',dict(candidates=decisions,nominees=[d['model'] for d in decisions if d['nominate']],exposed_evaluated=False,rows=len(x),dates=x.decision_date.nunique(),documented_attempts=len(ledger),prior_registry_preserved=prior.issubset(set(ledger.id))))
    print('DECISION',json.dumps(decisions,default=lambda v:v.item() if hasattr(v,'item') else str(v)),flush=True)


if __name__=='__main__':main()
