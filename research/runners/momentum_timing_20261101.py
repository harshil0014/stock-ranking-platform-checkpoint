"""One preregistered preference-selection/dip/short-head combination; governed CPU."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import datetime,gc,hashlib,json,pickle
import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from stock_research.momentum_timing import entry_state,high_state,net_return,top_quartile
from delivery_probe_20261101 import BASE
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/momentum-timing-20261101';WORK=ROOT/'work/momentum-timing-20261101'


def save(name,data):
    (OUT/name).write_text(json.dumps(data,indent=2,default=lambda a:a.item() if hasattr(a,'item') else str(a)),encoding='utf-8')


def table(z):
    return '| '+' | '.join(z.columns)+' |\n| '+' | '.join(['---']*len(z.columns))+' |\n'+''.join('| '+' | '.join(map(str,r))+' |\n' for r in z.itertuples(index=False,name=None))


def liquidity(panel):
    dest=WORK/'adv20.pkl.gz'
    if dest.exists():return pd.read_pickle(dest,compression='gzip')
    root=ROOT/'experiments/current-data-recovery-20261003/yahoo-full-recovery-v1'
    mapping=pd.read_csv(root/'yahoo_symbol_map.csv').dropna(subset=['isin','yahoo_symbol'])
    lookup=dict(zip(mapping.yahoo_symbol,mapping['isin']));queries=panel.groupby('isin').decision_date.unique().to_dict()
    rows=[];receipts=[]
    for file in sorted((root/'history-cache').glob('batch_*.pkl')):
        receipts.append(dict(path=file.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
        with file.open('rb') as f:batch=pickle.load(f)
        for symbol,frame in batch['frames'].items():
            isin=lookup.get(symbol)
            if isin not in queries or not isinstance(frame,pd.DataFrame) or not {'Close','Volume'}.issubset(frame.columns):continue
            z=frame[['Close','Volume']];z=z[~z.index.duplicated(keep='last')].sort_index()
            ds=z.index.tz_localize(None).to_numpy(dtype='datetime64[D]');turnover=(z.Close*z.Volume).to_numpy(float)
            for date in queries[isin]:
                end=np.searchsorted(ds,np.datetime64(date),'left');start=end-20
                if start<0 or end==0:continue
                if int((np.datetime64(date)-ds[end-1]).astype(int))>7 or (np.diff(ds[start:end]).astype(int)>7).any():continue
                values=turnover[start:end];prices=z.Close.iloc[start:end].to_numpy(float)
                if len(values)!=20 or not np.isfinite(values).all() or (values<0).any() or not np.isfinite(prices).all() or (prices<=0).any():continue
                rows.append(dict(isin=isin,decision_date=date,adv20=float(values.mean()),provider_symbol=symbol,provider_rows=len(ds)))
        del batch;gc.collect()
        if len(receipts)%20==0:print('ADV20',len(receipts),'batches',len(rows),'rows',flush=True)
    z=pd.DataFrame(rows).sort_values('provider_rows').drop_duplicates(['isin','decision_date'],keep='last')
    z.to_pickle(dest,compression='gzip');save('liquidity_sources.json',receipts)
    return z


def summarize(z,period):
    records=[];support=[]
    for liquidity_scope in ['all','exclude_bottom_quintile']:
        a=z if liquidity_scope=='all' else z[z.liquidity_quintile.gt(1)]
        mins=(20,20,5) if liquidity_scope=='all' else (10,10,3)
        for date,g in a.groupby('decision_date'):
            dip=g[g.dip];non=g[~g.dip];overlay=g[g.overlay]
            unknown=int(g.gross_ratio.isna().sum())
            ok=len(dip)>=mins[0] and len(non)>=mins[1] and len(overlay)>=mins[2] and unknown==0
            support.append(dict(period=period,liquidity_scope=liquidity_scope,decision_date=date,dip=len(dip),non_dip=len(non),overlay=len(overlay),unknown_outcomes=unknown,eligible=ok))
            if not ok:continue
            for cost in [75,100]:
                d=float(net_return(dip.gross_ratio,cost).mean());n=float(net_return(non.gross_ratio,cost).mean());o=float(net_return(overlay.gross_ratio,cost).mean())
                records.append(dict(period=period,liquidity_scope=liquidity_scope,decision_date=date,year=int(date[:4]),cost_bps=cost,
                    dip_net=d,non_dip_net=n,overlay_net=o,dip_minus_non_dip=d-n,overlay_minus_dip=o-d))
    r=pd.DataFrame(records);pd.DataFrame(support).to_csv(OUT/f'{period}_support.csv',index=False)
    r.to_csv(OUT/f'{period}_date_returns.csv',index=False)
    if r.empty:return dict(status='INCONCLUSIVE',failures=['No supported queries'],period=period)
    metrics=['dip_net','non_dip_net','overlay_net','dip_minus_non_dip','overlay_minus_dip']
    annual=r.groupby(['liquidity_scope','cost_bps','year'])[metrics].mean().reset_index()
    annual.to_csv(OUT/f'{period}_year_returns.csv',index=False)
    pooled=r.groupby(['liquidity_scope','cost_bps'])[metrics].mean().reset_index()
    pooled.to_csv(OUT/f'{period}_pooled_returns.csv',index=False)
    minimum=8 if period=='development' else 4;years=[2021,2022,2023] if period=='development' else [2024,2025]
    insufficient=[];failures=[]
    for scope in ['all','exclude_bottom_quintile']:
        for cost in [75,100]:
            a=r[r.liquidity_scope.eq(scope)&r.cost_bps.eq(cost)]
            if a.decision_date.nunique()<minimum or any(a[a.year.eq(y)].decision_date.nunique()<2 for y in years):
                insufficient.append(f'{scope}, {cost}bp: fewer than required dates/year')
            for label,b in [('overall',a)]+[(str(y),a[a.year.eq(y)]) for y in years]:
                for metric in ['dip_net','overlay_net','dip_minus_non_dip','overlay_minus_dip']:
                    if len(b) and b[metric].mean()<=0:failures.append(dict(liquidity_scope=scope,cost_bps=cost,year=label,metric=metric,value=float(b[metric].mean())))
    from champion_market_review_20261031 import block_indices
    intervals=[]
    for (scope,cost),a in r.groupby(['liquidity_scope','cost_bps']):
        a=a.sort_values('decision_date');dates=a.decision_date.to_numpy();rng=np.random.default_rng(20261101)
        for metric in ['dip_minus_non_dip','overlay_minus_dip']:
            values=a[metric].to_numpy();boot=np.array([values[block_indices(dates,365,rng)].mean() for _ in range(2000)])
            intervals.append(dict(liquidity_scope=scope,cost_bps=cost,metric=metric,mean=float(values.mean()),low95=float(np.quantile(boot,.025)),high95=float(np.quantile(boot,.975)),dates=len(a)))
    pd.DataFrame(intervals).to_csv(OUT/f'{period}_block_intervals.csv',index=False)
    # A demonstrated kill still stands if a separate cohort lacks enough support.
    status='KILLED' if failures else 'INCONCLUSIVE' if insufficient else 'PASS_DIAGNOSTIC_ONLY'
    return dict(status=status,period=period,failures=failures,insufficient_support=insufficient,dates=int(r.decision_date.nunique()))


def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(exist_ok=True)
    protocol=ROOT/'research/protocols/momentum_timing_20261101.md'
    receipt=OUT/'protocol_receipt.json'
    if not receipt.exists():save(receipt.name,dict(sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),frozen_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),parent_commit='254c503a9c902fb3481a537514831dcf04cb2146'))
    assert json.loads(receipt.read_text())['sha256']==hashlib.sha256(protocol.read_bytes()).hexdigest()
    implementation=ROOT/'research/protocols/momentum_timing_implementation_review_20261101.md'
    if not (OUT/'implementation_receipt.json').exists():save('implementation_receipt.json',dict(sha256=hashlib.sha256(implementation.read_bytes()).hexdigest(),before_outcome_scoring_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    original=ROOT/'work/new-information-20261101/delivery_panel.pkl.gz'
    panel=pd.read_pickle(original,compression='gzip')
    scoresfile=ROOT/'experiments/professor-weight-curve-20261031/scored.pkl.gz'
    scores=pd.read_pickle(scoresfile,compression='gzip')
    scores=scores[scores.factor_eligible & scores.decision_date.ge('2021-01-01') & scores.decision_date.lt('2026-01-01')]
    selected=pd.concat([top_quartile(g,'factor20_fixed') for _,g in scores.groupby('decision_date')])[['isin','decision_date','factor20_fixed']]
    save('input_receipt.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in [original,scoresfile,ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv']])
    adv=liquidity(panel);panel=panel.merge(adv,on=['isin','decision_date'],validate='one_to_one',how='left')
    # Quintiles use all mapped NSE training/source stocks before preference selection.
    panel['liquidity_quintile']=np.ceil(panel.groupby('decision_date').adv20.rank(pct=True)*5)
    with (ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl').open('rb') as f:paths=pickle.load(f)
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv')
    actions=actions[actions.status.str.startswith('UNRESOLVED')]
    failures=[];folds=[];coefficients=[];membership=[];coverage=[];gates={}
    for period,years in [('development',range(2021,2024)),('exposed',range(2024,2026))]:
        rows=[]
        for year in years:
            train=panel[panel.label_end.lt(f'{year}-01-01')];test=panel[panel.decision_date.str.startswith(str(year))].copy()
            if train.decision_date.nunique()<3 or test.empty:continue
            model=Ridge(alpha=10);model.fit(train[BASE],train.target);test['timing_score']=model.predict(test[BASE])
            folds.append(dict(period=period,year=year,train_rows=len(train),train_dates=train.decision_date.nunique(),max_training_label_end=train.label_end.max(),test_rows=len(test)))
            coefficients.extend(dict(year=year,feature=col,coefficient=float(value)) for col,value in zip(BASE,model.coef_))
            joined=selected.merge(test,on=['isin','decision_date'],validate='one_to_one')
            for date,g in joined.groupby('decision_date'):
                count=0;asof_invalid=False
                for row in g.itertuples(index=False):
                    base=dict(isin=row.isin,decision_date=date,period=period)
                    signal_created=False
                    try:
                        if row.isin not in paths:raise ValueError('Missing path')
                        if not np.isfinite(row.adv20):raise ValueError('Missing ADV20')
                        signal=high_state(paths[row.isin],date)
                        result=dict(**base,**signal,timing_score=row.timing_score,adv20=row.adv20,liquidity_quintile=int(row.liquidity_quintile),gross_ratio=np.nan)
                        # Freeze signal membership even when future execution/action evidence fails.
                        rows.append(result)
                        signal_created=True
                        state=entry_state(paths[row.isin],date)
                        bad=actions[actions['isin'].eq(row.isin)&actions.event_date.gt(date)&actions.event_date.le(state['exit'])]
                        if len(bad):raise ValueError('Unresolved action in holding window')
                        if abs(float(net_return(state['gross_ratio'],25))-row.target)>1e-10:raise RuntimeError('Target reconstruction mismatch')
                        result.update(state)
                        count+=1
                    except ValueError as e:
                        failures.append(dict(**base,reason=str(e)))
                        if not signal_created:asof_invalid=True
                if asof_invalid:rows=[r for r in rows if r['decision_date']!=date];count=0
                coverage.append(dict(period=period,decision_date=date,global_lens_quartile=len(selected[selected.decision_date.eq(date)]),joined=len(g),valid=count,asof_quarantined=asof_invalid))
        z=pd.DataFrame(rows)
        if z.empty:gates[period]=dict(status='INCONCLUSIVE',failures=['No supported observations']);break
        z['overlay']=False
        for date,g in z[z.dip].groupby('decision_date'):
            chosen=top_quartile(g,'timing_score');z.loc[chosen.index,'overlay']=True
        membership.append(z);z.to_pickle(WORK/f'{period}_memberships.pkl.gz',compression='gzip')
        gates[period]=summarize(z,period)
        print('GATE',period,gates[period]['status'],'failures',len(gates[period].get('failures',[])),flush=True)
        if gates[period]['status']!='PASS_DIAGNOSTIC_ONLY':break
    save('gate.json',dict(gates=gates,exposed_evaluated='exposed' in gates,champion_changed=False,lens_changed=False))
    pd.DataFrame(folds).to_csv(OUT/'annual_folds.csv',index=False);pd.DataFrame(coefficients).to_csv(OUT/'head_coefficients.csv',index=False)
    pd.DataFrame(coverage).to_csv(OUT/'coverage.csv',index=False)
    # Aggregate failures only; no public stock picks.
    f=pd.DataFrame(failures)
    if len(f):f.groupby(['period','decision_date','reason']).size().rename('count').to_csv(OUT/'failure_counts.csv')
    else:pd.DataFrame(columns=['period','decision_date','reason','count']).to_csv(OUT/'failure_counts.csv',index=False)
    for period in gates:
        if not (WORK/f'{period}_memberships.pkl.gz').exists():continue
        z=pd.read_pickle(WORK/f'{period}_memberships.pkl.gz',compression='gzip')
        z.groupby(['decision_date','liquidity_quintile','dip']).agg(stocks=('isin','size'),overlay=('overlay','sum')).to_csv(OUT/f'{period}_liquidity_counts.csv')
    print('COMPLETE',gates,flush=True)


if __name__=='__main__':main()
