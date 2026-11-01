"""Three explicit-majority factor architectures with corrected SIP labels."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import datetime,hashlib,json,pickle
import numpy as np
import pandas as pd
from lightgbm import LGBMRegressor
from stock_research.professor_factor_model import FACTOR_COLUMNS
from stock_research.professor_frontier import geometric_core,outranking_core
from stock_research.next_open_portfolio import next_open_portfolio
from filing_probe_20261101 import start_watchdog
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/professor-frontier-20261101';WORK=ROOT/'work/professor-frontier-20261101'
Q=['q_'+c for c in FACTOR_COLUMNS];FEATS=Q+['downside252','volatility252','return21']
REFERENCES=['champion','lens20','linear75'];CHALLENGERS=['balanced75','outrank75','tail75']


def save(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')


def scope_path(path,date,end):
    ds,op,cl=path;a=max(0,np.searchsorted(ds,np.datetime64(date))-1);b=np.searchsorted(ds,np.datetime64(end),side='right')
    return ds[a:b],op[a:b],cl[a:b]


def outcomes(x,paths,actions):
    folder=WORK/'labels';folder.mkdir(exist_ok=True);frames=[];coverage=[]
    for date,g in x.groupby('decision_date',sort=True):
        dest=folder/f'{date}.pkl.gz'
        if dest.exists():z=pd.read_pickle(dest,compression='gzip')
        else:
            end=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date())
            bad=set(actions.loc[actions.event_date.gt(date)&actions.event_date.le(end),'isin']);rows=[]
            for isin in g['isin']:
                row=dict(isin=isin,decision_date=date,new_endpoint=end,new_xirr=np.nan,new_dd=np.nan,error='')
                try:
                    if isin in bad:raise ValueError('Unresolved action in holding window')
                    if isin not in paths:raise ValueError('Missing selected path')
                    r=next_open_portfolio([scope_path(paths[isin],date,end)],[1.],date,end,7500,30,100)
                    if not np.isfinite(r['xirr']):raise ValueError('Undefined XIRR')
                    row.update(new_xirr=r['xirr'],new_dd=r['tw_max_drawdown'],first_fill=r['first_fills'][0])
                except ValueError as e:row['error']=str(e)
                rows.append(row)
            z=pd.DataFrame(rows);z.to_pickle(dest,compression='gzip')
        if set(z['isin'])!=set(g['isin']):raise RuntimeError('Checkpoint cohort mismatch')
        coverage.append(dict(decision_date=date,feature_rows=len(g),valid_outcomes=int(z.new_xirr.notna().sum()),unknown_outcomes=int(z.new_xirr.isna().sum())))
        frames.append(z);pd.DataFrame(coverage).to_csv(OUT/'label_coverage.csv',index=False)
        print('LABELS',date,len(z),'valid',z.new_xirr.notna().sum(),flush=True)
    labels=pd.concat(frames,ignore_index=True)
    labels.loc[labels.error.ne('')].groupby(['decision_date','error']).size().rename('count').to_csv(OUT/'label_failure_counts.csv')
    return x.merge(labels,on=['isin','decision_date'],validate='one_to_one')


def score_period(allrows,years,names):
    x=allrows[allrows.decision_date.str[:4].astype(int).isin(years)&allrows.champion_percentile.notna()].copy()
    counts=x.groupby(['decision_date','sector'])['isin'].transform('size');x=x[counts.ge(5)].copy()
    x['champion']=x.champion_percentile;core=x[Q].mean(axis=1)
    x['lens20']=.2*core+.8*x.champion_percentile
    x['linear75']=.75*core+.25*x.champion_percentile
    if 'balanced75' in names:x['balanced75']=.75*geometric_core(x[Q])+.25*x.champion_percentile
    if 'outrank75' in names:
        x['outrank75']=np.nan
        for _,g in x.groupby(['decision_date','sector']):
            vote=pd.Series(outranking_core(g[Q]),index=g.index).rank(pct=True)
            x.loc[g.index,'outrank75']=.75*vote+.25*g.champion_percentile
    if 'tail75' in names:
        folds=[];folder=WORK/'models';folder.mkdir(exist_ok=True)
        for year in years:
            train=allrows[allrows.new_endpoint.lt(f'{year}-01-01')&allrows.new_xirr.notna()]
            test=x[x.decision_date.str.startswith(str(year))]
            if len(train)<100 or train.decision_date.nunique()<2:raise RuntimeError('Insufficient mature training support')
            model=LGBMRegressor(objective='quantile',alpha=.8,n_estimators=100,learning_rate=.03,num_leaves=7,max_depth=3,min_child_samples=50,reg_lambda=10,
                random_state=20261101,n_jobs=1,deterministic=True,force_col_wise=True,verbosity=-1)
            model.fit(train[FEATS],np.log1p(train.new_xirr.clip(-.95,3)))
            raw=model.predict(test[FEATS]);pred=pd.Series(raw,index=test.index).groupby([test.decision_date,test.sector]).rank(pct=True)
            x.loc[test.index,'tail75']=.75*core.loc[test.index]+.25*pred
            dest=folder/f'tail75_{year}.txt';model.booster_.save_model(str(dest))
            folds.append(dict(year=year,train_rows=len(train),train_dates=train.decision_date.nunique(),latest_label_endpoint=train.new_endpoint.max(),test_rows=len(test),model_sha256=hashlib.sha256(dest.read_bytes()).hexdigest()))
            print('FIT tail75',year,len(train),flush=True)
        pd.DataFrame(folds).to_csv(OUT/f'folds_{min(years)}_{max(years)}.csv',index=False)
    if not np.isfinite(x[names].to_numpy()).all():raise RuntimeError('Missing candidate score')
    return x


def selections(g,name,n=3):
    return g.sort_values([name,'isin'],ascending=[False,True]).head(n)


def evaluate(x,names,period,paths,actions):
    rows=[];overlap=[];blocked=[]
    for (date,sector),g in x.groupby(['decision_date','sector'],sort=True):
        tops={name:selections(g,name) for name in names};known=g.new_xirr.notna()
        complete=all(h.new_xirr.notna().all() for h in tops.values())
        for name,h in tops.items():
            ids=set(h['isin']);anchor=set(tops['champion']['isin'])
            overlap.append(dict(decision_date=date,sector=sector,model=name,changed=ids!=anchor,overlap=len(ids&anchor)/3))
            valid=g.loc[known]
            ic=float(valid[name].corr(valid.new_xirr,method='spearman')) if len(valid)>=5 and valid.new_xirr.nunique()>1 else np.nan
            rows.append(dict(decision_date=date,sector=sector,model=name,alignment=float(h[Q].mean(axis=1).mean()),rank_ic=ic,
                top3_goal_hit=float(h.new_xirr.ge(.20).mean()) if complete else np.nan,
                top3_stock_dd=float(h.new_dd.mean()) if complete else np.nan,top3_complete=complete,valid_stock_outcomes=len(valid)))
        if not complete:blocked.append(dict(decision_date=date,sector=sector,reason='A selected stock has unknown outcome; all models blocked'))
    q=pd.DataFrame(rows);q.to_csv(OUT/f'{period}_sector_metrics.csv',index=False)
    ov=pd.DataFrame(overlap);ov.to_csv(OUT/f'{period}_overlap.csv',index=False)
    pd.DataFrame(blocked).to_csv(OUT/f'{period}_blocked_queries.csv',index=False)
    numeric=['alignment','rank_ic','top3_goal_hit','top3_stock_dd']
    perdate=q.groupby(['decision_date','model'])[numeric].mean().reset_index()
    # Date metrics retain their own counts; incomplete Top3 queries never get neutral values.
    perdate.to_csv(OUT/f'{period}_date_metrics.csv',index=False)
    summary=perdate.groupby('model')[numeric].mean();summary['dates']=perdate.groupby('model').decision_date.nunique()
    coverage=q[q.top3_complete].groupby('decision_date').sector.nunique()
    summary['supported_top3_dates']=int(coverage.ge(20).sum())
    change=ov.groupby(['decision_date','model'])[['changed','overlap']].mean().groupby('model').mean();summary=summary.join(change)
    summary.to_csv(OUT/f'{period}_summary.csv')
    portfolios=[];fail=[]
    for date,g in x.groupby('decision_date',sort=True):
        end=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date());bad=set(actions.loc[actions.event_date.gt(date)&actions.event_date.le(end),'isin'])
        for name in names:
            for policy in ['global_top20','sector_top3']:
                if policy=='global_top20':h=selections(g,name,20);ids=h['isin'].tolist();weights=np.full(len(h),1/len(h))
                else:
                    groups=[selections(h,name) for _,h in g.groupby('sector') if len(h)>=5]
                    ids=[i for h in groups for i in h['isin']];weights=np.full(len(ids),1/len(ids))
                    # Every sector has exactly3stocks, so this equals equal-sector weighting.
                base=dict(decision_date=date,model=name,policy=policy)
                try:
                    if not ids or set(ids)-set(paths):raise ValueError('Missing selected paths')
                    if set(ids)&bad:raise ValueError('Unresolved holding-window action')
                    r=next_open_portfolio([scope_path(paths[i],date,end) for i in ids],weights,date,end,7500,30,100)
                    if not np.isfinite(r['xirr']):raise ValueError('Undefined portfolio XIRR')
                    portfolios.append(dict(**base,xirr=r['xirr'],drawdown=r['tw_max_drawdown'],stocks=len(ids)))
                except ValueError as e:fail.append(dict(**base,reason=str(e)))
        print('PORTFOLIO',period,date,len(portfolios),'blocked',len(fail),flush=True)
    p=pd.DataFrame(portfolios);p.to_csv(OUT/f'{period}_portfolios.csv',index=False);pd.DataFrame(fail).to_csv(OUT/f'{period}_portfolio_failures.csv',index=False)
    pairs=[]
    for name in names:
        for policy in ['global_top20','sector_top3']:
            a=p[p.model.eq(name)&p.policy.eq(policy)].merge(p[p.model.eq('champion')&p.policy.eq(policy)],on='decision_date',suffixes=('_model','_champion'),validate='one_to_one')
            pairs.append(dict(model=name,policy=policy,matched_dates=len(a),xirr_delta=float((a.xirr_model-a.xirr_champion).mean()),drawdown_delta=float((a.drawdown_model-a.drawdown_champion).mean())))
    pairs=pd.DataFrame(pairs);pairs.to_csv(OUT/f'{period}_portfolio_pairs.csv',index=False)
    perdate.assign(year=perdate.decision_date.str[:4]).groupby(['year','model'])[numeric].mean().to_csv(OUT/f'{period}_year_metrics.csv')
    return summary,perdate,pairs


def decide(summary,perdate,pairs):
    baseline=summary.loc['champion'];results=[]
    for name in CHALLENGERS:
        row=summary.loc[name];p=pairs[pairs.model.eq(name)&pairs.policy.eq('global_top20')].iloc[0]
        tests=dict(alignment_gain=row.alignment-baseline.alignment>=.05,ic_budget=row.rank_ic-baseline.rank_ic>=-.02,
            goal_budget=row.top3_goal_hit-baseline.top3_goal_hit>=-.03,stock_drawdown_budget=row.top3_stock_dd-baseline.top3_stock_dd>=-.05,
            changed_fraction=row.changed>=.25,stock_support=row.dates>=8 and row.supported_top3_dates>=8,
            portfolio_support=p.matched_dates>=8,portfolio_xirr_budget=p.xirr_delta>=-.03,portfolio_drawdown_budget=p.drawdown_delta>=-.05)
        results.append(dict(model=name,pass_preference_budget=all(tests.values()),checks=tests,
            alignment_gain=float(row.alignment-baseline.alignment),ic_delta=float(row.rank_ic-baseline.rank_ic)))
    passed=[r for r in results if r['pass_preference_budget']]
    winner=sorted(passed,key=lambda r:(-r['alignment_gain'],r['model']))[0]['model'] if passed else None
    from champion_market_review_20261031 import block_indices
    wide=perdate.pivot(index='decision_date',columns='model',values='rank_ic').dropna()
    dates=wide.index.to_numpy();diff=wide[CHALLENGERS].to_numpy()-wide[['champion']].to_numpy();center=diff-diff.mean(axis=0);rng=np.random.default_rng(20261101)
    boot=np.array([center[block_indices(dates,365,rng)].mean(axis=0) for _ in range(2000)])
    hurdle=float(np.quantile(boot.max(axis=1),.95));intervals=[]
    for i,name in enumerate(CHALLENGERS):
        intervals.append(dict(model=name,ic_delta=float(diff[:,i].mean()),low95=float(diff[:,i].mean()-np.quantile(boot[:,i],.975)),high95=float(diff[:,i].mean()-np.quantile(boot[:,i],.025)),familywise_ic_hurdle=hurdle,
            clears_predictive_hurdle=bool(diff[:,i].mean()>hurdle and summary.loc[name,'rank_ic']>0)))
    pd.DataFrame(intervals).to_csv(OUT/'development_ic_uncertainty.csv',index=False)
    save('decision.json',dict(candidates=results,locked_preference_candidate=winner,automatic_promotion=False,exposed_evaluated=False))
    return winner


def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(exist_ok=True);watchdog=start_watchdog(1200,OUT/'timeout.json')
    try:
        protocol=ROOT/'research/protocols/professor_frontier_20261101.md';receipt=OUT/'protocol_receipt.json'
        if not receipt.exists():save(receipt.name,dict(sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),frozen_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
        assert json.loads(receipt.read_text())['sha256']==hashlib.sha256(protocol.read_bytes()).hexdigest()
        source=ROOT/'experiments/professor-weight-curve-20261031/scored.pkl.gz';prices=ROOT/'experiments/sector-price-rebuild-20261010/price_features.pkl.gz';pathfile=ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl';actionfile=ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv'
        save('input_receipts.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [source,prices,pathfile,actionfile]])
        x=pd.read_pickle(source,compression='gzip');f=pd.read_pickle(prices,compression='gzip')[['isin','decision_date','downside252','volatility252','return21']]
        x=x.merge(f,on=['isin','decision_date'],how='left',validate='one_to_one')
        x=x[x.factor_eligible&x.decision_date.ge('2016-01-01')&x.decision_date.lt('2026-01-01')&np.isfinite(x[FEATS]).all(axis=1)].copy()
        x=x[x.groupby(['decision_date','sector'])['isin'].transform('size').ge(5)].copy()
        with pathfile.open('rb') as file:paths=pickle.load(file)
        actions=pd.read_csv(actionfile);actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
        x=outcomes(x,paths,actions);x.to_pickle(WORK/'corrected_panel.pkl.gz',compression='gzip')
        names=REFERENCES+CHALLENGERS;development=score_period(x,range(2020,2024),names);development.to_pickle(WORK/'development_scored.pkl.gz',compression='gzip')
        summary,perdate,pairs=evaluate(development,names,'development',paths,actions);winner=decide(summary,perdate,pairs)
        print('LOCKED CANDIDATE',winner,flush=True)
        if winner:
            names=REFERENCES+[winner];exposed=score_period(x,range(2024,2026),names);exposed.to_pickle(WORK/'exposed_scored.pkl.gz',compression='gzip')
            evaluate(exposed,names,'exposed',paths,actions)
            receipt=json.loads((OUT/'decision.json').read_text());receipt['exposed_evaluated']=True;save('decision.json',receipt)
    finally:watchdog.cancel()


if __name__=='__main__':main()
