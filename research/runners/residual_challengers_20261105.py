"""Three preregistered residual-history policies, one serial development pilot."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import sys,json,pickle,hashlib,datetime,importlib.util,shutil
import numpy as np
import pandas as pd
from stock_research.residual_history import weekly_prices,residual_features
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/novel-champion-20261105'
OUT=ROOT/'experiments/residual-challengers-20261105'
NAMES=['champion','residual_momentum20','professor_residual50','residual_high20']
Q=['q_annual_consistency','q_cagr3','q_cagr5','q_high_recency','q_sip_profit']


def save(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')


def evaluator():
    sys.path.insert(0,str(WORK/'archive_sources'))
    spec=importlib.util.spec_from_file_location('archived_frontier',WORK/'archive_sources/professor_frontier_20261101.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    module.ROOT=ROOT;module.OUT=OUT
    return module


def main():
    OUT.mkdir(exist_ok=True)
    protocol=ROOT/'research/protocols/residual_challengers_20261105.md'
    files=[protocol,ROOT/'work/professor-frontier-20261101/development_scored.pkl.gz',ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl',ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv',Path(__file__),ROOT/'src/stock_research/residual_history.py']
    save('input_receipts.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files])
    receipt=OUT/'frozen_protocol.json';digest=hashlib.sha256(protocol.read_bytes()).hexdigest()
    if receipt.exists():assert json.loads(receipt.read_text())['sha256']==digest
    else:save(receipt.name,dict(sha256=digest,utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    ledger=ROOT/'research/research_variant_ledger.csv';registry=pd.read_csv(ledger);ids=set(registry.id)
    additions=[dict(id='residual_challengers_20261105::'+n,family='residual_challengers_20261105',name=n,source=protocol.relative_to(ROOT).as_posix(),category='configuration') for n in NAMES[1:] if 'residual_challengers_20261105::'+n not in ids]
    registry=pd.concat([registry,pd.DataFrame(additions)],ignore_index=True);registry.to_csv(ledger,index=False)
    with files[2].open('rb') as f:paths=pickle.load(f)
    x=pd.read_pickle(files[1],compression='gzip')
    assert x.decision_date.between('2020-01-01','2023-12-31').all()
    frames=[];coverage=[]
    for date,g in x.groupby('decision_date',sort=True):
        g=g.sort_values('isin').copy();dest=WORK/('features_'+date+'.pkl.gz')
        if dest.exists():features=pd.read_pickle(dest,compression='gzip')
        else:
            prices=np.column_stack([weekly_prices(paths[i],date) if i in paths else np.full(157,np.nan) for i in g['isin']])
            residual=residual_features(np.diff(np.log(prices),axis=0),g.sector)
            features=g[['isin','decision_date']].copy();features[['residual_momentum','residual_high']]=residual
            features.to_pickle(dest,compression='gzip')
        g=g.merge(features,on=['isin','decision_date'],validate='one_to_one')
        initial=len(g);g=g[np.isfinite(g[['residual_momentum','residual_high']]).all(axis=1)].copy()
        g=g[g.groupby('sector')['isin'].transform('size').ge(5)].copy()
        for c in Q+['champion','residual_momentum','residual_high']:
            g[c]=g.groupby('sector')[c].rank(pct=True)
        core=g[Q].mean(axis=1)
        g['residual_momentum20']=.8*g.champion+.2*g.residual_momentum
        g['professor_residual50']=.3*g.champion+.5*core+.2*g.residual_momentum
        g['residual_high20']=.8*g.champion+.2*g.residual_high
        frames.append(g);coverage.append(dict(date=date,original=initial,common=len(g),sectors=g.sector.nunique()))
        print('FEATURE',date,'common',len(g),'of',initial,flush=True)
    pd.DataFrame(coverage).to_csv(OUT/'coverage.csv',index=False)
    scored=pd.concat(frames,ignore_index=True);scored.to_pickle(WORK/'development_scored.pkl.gz',compression='gzip')
    assert np.isfinite(scored[NAMES]).all().all()
    actions=pd.read_csv(files[3]);actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    old=evaluator();summary,perdate,pairs=old.evaluate(scored,NAMES,'development',paths,actions)
    alignment=[]
    for (date,sector),g in scored.groupby(['decision_date','sector']):
        for n in NAMES:
            h=old.selections(g,n)
            alignment.append(dict(decision_date=date,sector=sector,model=n,raw_high_percentile=h.q_high_recency.mean(),days_since_high=-h.high_recency.mean()))
    alignment=pd.DataFrame(alignment);alignment.to_csv(OUT/'high_alignment.csv',index=False)
    align=alignment.groupby(['decision_date','model'])[['raw_high_percentile','days_since_high']].mean().groupby('model').mean()
    summary=summary.join(align);summary.to_csv(OUT/'summary.csv')
    from champion_market_review_20261031 import block_indices
    wide=perdate.pivot(index='decision_date',columns='model',values='rank_ic').dropna();diff=wide[NAMES[1:]].to_numpy()-wide[['champion']].to_numpy();center=diff-diff.mean(axis=0);rng=np.random.default_rng(20261105)
    boot=np.array([center[block_indices(wide.index.to_numpy(),365,rng)].mean(axis=0) for _ in range(2000)])
    hurdle=float(np.quantile(boot.max(axis=1),.95));b=summary.loc['champion'];decisions=[]
    portfolios=pd.read_csv(OUT/'development_portfolios.csv');years=perdate.assign(year=perdate.decision_date.str[:4]).groupby(['year','model']).rank_ic.mean().unstack()
    for n in NAMES[1:]:
        r=summary.loc[n];p=pairs[pairs.model.eq(n)&pairs.policy.eq('global_top20')].iloc[0]
        d=portfolios[portfolios.model.eq(n)&portfolios.policy.eq('global_top20')].merge(portfolios[portfolios.model.eq('champion')&portfolios.policy.eq('global_top20')],on='decision_date',suffixes=('_new','_old'))
        delta=(d.xirr_new-d.xirr_old).to_numpy();ordered=np.sort(delta);k=int(len(ordered)*.1)
        winsor=float(np.clip(ordered,ordered[k],ordered[-k-1]).mean());lodo=float(min(np.delete(delta,j).mean() for j in range(len(delta))))
        ic_delta=float(r.rank_ic-b.rank_ic);positive_years=int(((years[n]-years.champion)>0).sum())
        checks=dict(ic_floor=ic_delta>=.010134924,ic_familywise=ic_delta>hurdle,annual_ic=positive_years>=3,professor_alignment=r.alignment>=b.alignment,raw_high_alignment=r.raw_high_percentile>=b.raw_high_percentile,goal=r.top3_goal_hit>=b.top3_goal_hit,xirr=p.xirr_delta>0,winsor=winsor>=0,lodo=lodo>=0,drawdown=p.drawdown_delta>=-.02,support=p.matched_dates>=12 and r.supported_top3_dates>=12)
        decisions.append(dict(model=n,passes=all(checks.values()),checks=checks,ic_delta=ic_delta,positive_years=positive_years,winsor_xirr_delta=winsor,worst_lodo_xirr_delta=lodo))
    save('decision.json',dict(candidates=decisions,familywise_ic_hurdle=hurdle,development_nominees=[d['model'] for d in decisions if d['passes']],exposed_evaluated=False,documented_attempts=len(registry),prior_ids_preserved=ids.issubset(set(registry.id)),rows=len(scored),dates=scored.decision_date.nunique()))
    print('DECISION',json.dumps(decisions,default=lambda v:v.item() if hasattr(v,'item') else str(v)),flush=True)


if __name__=='__main__':main()
