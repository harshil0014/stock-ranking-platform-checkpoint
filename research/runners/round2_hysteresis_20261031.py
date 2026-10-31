"""Preregistered hysteresis frontier and dated daily price-component replay.

Daily output is the annual price-head contribution plus high-recency overlay.
It is NOT the full champion: open/profile/SIP components are not daily rebuilt.
"""
from pathlib import Path
import argparse,json,hashlib,gc
from functools import lru_cache
from concurrent.futures import ProcessPoolExecutor
import numpy as np
import pandas as pd
from numpy.lib.stride_tricks import sliding_window_view
from scipy.stats import rankdata,kendalltau
import lightgbm as lgb
import ten_hypotheses_20261031 as old

ROOT=old.ROOT
OUT=ROOT/'experiments/round2-hysteresis-20261031'
CACHE=ROOT/'experiments/current-data-recovery-20261003/yahoo-full-recovery-v1'
MARGINS=[0,.0025,.005,.01,.02,.03,.05,.1]
RAW=old.old.RAW

def save(name,obj):
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/name).write_text(json.dumps(obj,indent=2,default=lambda x:x.item() if hasattr(x,'item') else str(x)),encoding='utf-8')

def protocol():
    doc=dict(baseline_commit='6e9bd620e4472c8280536b6120fe86d10dca65cb',margins=MARGINS,
        quarterly_selection='2020-23 only: minimum mean Top3 membership churn subject rank-IC delta>=-.001; smaller margin breaks ties. Freeze before2024-25 metrics.',
        daily_dates='Every recovered positive-volume market session in2025-01-01 through2026-09-30; actual last data date audited. No data beyond recovered endpoint invented.',
        daily_models='Saved2025 annual head, trained on endpoints<2025-01-01. New2026 head uses exact fixed180-tree rank_xendcg_balanced recipe and endpoints<2026-01-01. Never use October2026 serving weights in2025.',
        daily_score='.25 * annual_price_head_sector_percentile + high_recency_adjustment. No frozen open/profile/SIP components inserted. This is component-only, not full-champion replay; original whole-score margins may not transfer.',
        daily_safety='Block missing/nonfinite inputs, <252 observations, <365 history days, >7 calendar-day stale close, >5 calendar-day absent positive volume, <80% active-volume fraction, unresolved-action feature windows and >50% one-session moves requiring review. Remove blocked names immediately. Known action date triggers whole-sector raw-order reset. Verified suspension data unavailable =>UNKNOWN, not inferred from zero volume.',
        events='Existing retrospective provider/official alignment event dates. Historical announcement/availability timestamps uncertified. Safety diagnostics cannot establish point-in-time detection of every actual suspension, delisting or action.',
        daily_gate={'top3_churn_reduction_min':.20,'proxy_IC_loss_max':.001,'persistent_leader_entry_p90_sessions_max':5,'known_blocked_retention_max':0},
        leader='New raw Top3 entrant persisting >=5 consecutive sessions; lag from raw entry to first smoothed entry, right-censor at episode end. An additional ex-post oracle-confirmed subset uses future12month lump-return Top3 where mature. Persistent-score leadership is not a claim of true future alpha.',
        outcomes='Quarterly frontier uses original saved SIP XIRR. Daily mature2025 outcome is forward365-calendar-day provider close return with endpoint price gap<=7 days. It is explicitly a lump-return proxy, not daily SIP labels. Later2025 and2026 outcomes censored. No2026 matured performance claim.',
        promotion='No serving changes. Daily full-champion certification remains blocked until daily open/profile/SIP components and certified historical flags are available. Report all fixed margins, do not select on exposed daily results.',
        fresh_validation=False)
    OUT.mkdir(exist_ok=True)
    p=OUT/'protocol.json'
    if p.exists():assert json.loads(p.read_text())==doc
    else:save('protocol.json',doc)

def safe_order(previous,scores,margin,blocked=(),force_reset=False):
    blocked=set(blocked)
    scores={k:float(v) for k,v in scores.items() if k not in blocked and np.isfinite(v)}
    raw=sorted(scores,key=lambda i:(-scores[i],i))
    if force_reset:return raw
    prior=[i for i in previous if i in scores];known=set(prior)
    return old.hysteresis_order(prior+[i for i in raw if i not in known],scores,margin)

def evaluate_series(snapshots,margin,daily=False):
    """Snapshots have day, scores, outcomes, blocked, reset; sorted beforehand."""
    previous=[];previous_raw=[];records=[];history=[]
    for day,scores,outcomes,blocked,reset in snapshots:
        raw=sorted((i for i in scores if i not in blocked and np.isfinite(scores[i])),key=lambda i:(-scores[i],i))
        ordered=safe_order(previous,scores,margin,blocked,reset)
        assert not(set(ordered)&set(blocked))
        present=set(ordered);common=[i for i in previous if i in present]
        if len(common)>=2 and len(ordered)>=5:
            r={v:i for i,v in enumerate(ordered)};rr={v:i for i,v in enumerate(raw)}
            raw_old=[i for i in previous_raw if i in rr]
            tau=kendalltau(np.arange(len(common)),[r[i] for i in common]).statistic
            rawtau=kendalltau(np.arange(len(raw_old)),[rr[i] for i in raw_old]).statistic if len(raw_old)>=2 else np.nan
            # Churn includes entries/exits, not just pair swaps in the bulk.
            churn=1-len(set(previous[:3])&set(ordered[:3]))/3 if len(previous)>=3 else np.nan
            rawchurn=1-len(set(previous_raw[:3])&set(raw[:3]))/3 if len(previous_raw)>=3 else np.nan
            names=[i for i in ordered if np.isfinite(outcomes.get(i,np.nan))]
            ic=rawic=np.nan
            if len(names)>=5:
                y=rankdata([outcomes[i] for i in names]);a=-np.array([r[i] for i in names]);b=np.array([scores[i] for i in names])
                ic=np.corrcoef(rankdata(a),y)[0,1] if np.std(a)*np.std(y)>0 else np.nan
                rawic=np.corrcoef(rankdata(b),y)[0,1] if np.std(b)*np.std(y)>0 else np.nan
            records.append(dict(date=day,margin=margin,kendall_tau=tau,raw_tau=rawtau,top3_churn=churn,raw_top3_churn=rawchurn,ic_delta=ic-rawic,n_common=len(common),safety_reset=reset,blocked_retained=len(set(ordered)&set(blocked))))
        history.append((day,raw[:3],ordered[:3],outcomes))
        previous=ordered;previous_raw=raw
    return records,leader_lags(history)

def leader_lags(history,min_persistence=5):
    result=[]
    for start,(day,raw,smoothed,outcome) in enumerate(history):
        prior=set(history[start-1][1]) if start else set(raw)
        for name in set(raw)-prior:
            end=start
            while end+1<len(history) and name in history[end+1][1]:end+=1
            if end-start+1<min_persistence:continue
            entry=next((i for i in range(start,end+1) if name in history[i][2]),None)
            observed=entry is not None
            allout={i:v for i,v in outcome.items() if np.isfinite(v)}
            true_top=set(sorted(allout,key=lambda i:(-allout[i],i))[:3]) if len(allout)>=5 else set()
            result.append(dict(raw_entry_date=day,isin=name,persistence_sessions=end-start+1,entry_lag_sessions=entry-start if observed else end-start+1,right_censored=not observed,oracle_confirmed=name in true_top,oracle_available=len(allout)>=5))
    return result

def quarterly():
    protocol();x=old.valid(pd.read_pickle(old.OUT/'panel.pkl.gz',compression='gzip'))
    x=x[x.decision_date.ge('2020-01-01')];records=[];lag=[]
    for (profile,sector),g in x.groupby(['profile_name','sector'],observed=True):
        snapshots=[]
        for day,h in g.groupby('decision_date',observed=True,sort=True):
            h=h.dropna(subset=[old.ANCHOR]);scores=h.set_index('isin')[old.ANCHOR].to_dict();outcome=h.set_index('isin').future_xirr.to_dict()
            if len(scores)>=5:snapshots.append((day,scores,outcome,set(),False))
        for margin in MARGINS:
            r,l=evaluate_series(snapshots,margin)
            for v in r:v.update(profile=profile,sector=sector)
            for v in l:v.update(profile=profile,sector=sector,margin=margin)
            records.extend(r);lag.extend(l)
    q=pd.DataFrame(records)
    dev=q[q.date.lt('2024-01-01')].groupby('margin')[['top3_churn','ic_delta','kendall_tau']].mean()
    eligible=dev[dev.ic_delta.ge(-.001-1e-12)].sort_values(['top3_churn','margin'])
    chosen=float(eligible.index[0]);save('development_lock.json',dict(margin=chosen,criterion='minimumTop3churn withICdelta>=-.001; smaller margin tie-break',development=dev.reset_index().to_dict('records')))
    q.to_csv(OUT/'quarterly_queries.csv.gz',index=False)
    report=q.assign(period=np.where(q.date.lt('2024-01-01'),'development','exposed')).groupby(['period','margin'])[['kendall_tau','raw_tau','top3_churn','raw_top3_churn','ic_delta']].mean().reset_index();report['selected']=report.margin.eq(chosen);report.to_csv(OUT/'quarterly_frontier.csv',index=False)
    pd.DataFrame(lag).to_csv(OUT/'quarterly_leader_lags.csv.gz',index=False)
    print('QUARTERLY',report.to_dict('records'),flush=True)

def stock_features(history,isin,sector,event_days=()):
    """Vectorized parity with original31 price fields on observed close dates."""
    h=history.dropna(subset=['Close']).copy();h=h[h.Close.gt(0)].sort_index();h=h[~h.index.duplicated()]
    if len(h)<253:return pd.DataFrame()
    dates=pd.DatetimeIndex(pd.to_datetime(h.index)).tz_localize(None);p=h.Close.to_numpy(float);volume=h.Volume.fillna(0).to_numpy(float)
    # Retain full cumulative high/history origin; compute heavy windows only near replay.
    global_high=np.maximum.accumulate(p);at_high=p>=global_high;latest=np.maximum.accumulate(np.where(at_high,np.arange(len(p)),0))
    first=dates.searchsorted(pd.Timestamp('2024-01-01'));start=max(0,first-253)
    pp=pd.Series(p[start:]);vv=pd.Series(volume[start:]);ds=dates[start:];n=len(pp)
    if n<253:return pd.DataFrame()
    windows=sliding_window_view(pp.to_numpy(),253);running=np.maximum.accumulate(windows,axis=1);simple=pp.pct_change();logs=np.log(pp);dr=logs.diff()
    f=pd.DataFrame(index=range(n));f['last_price_date']=ds;f['isin']=isin;f['sector']=sector
    for col in RAW:f[col]=np.nan
    for k in [21,63,126,252]:
        f[f'return{k}']=pp/pp.shift(k)-1;f[f'ma{k}_gap']=pp/pp.rolling(k).mean()-1
        if k!=21:f[f'high_gap{k}']=pp/pp.rolling(k).max()-1
    f['momentum12_1']=pp.shift(21)/pp.shift(252)-1
    loc=np.arange(252,n);lastmax=252-np.argmax(windows[:,::-1],axis=1)
    f.loc[loc,'high_age252']=(252-lastmax)/252
    f.loc[loc,'near_high_fraction']=(windows>=.95*running).mean(1)
    f.loc[loc,'high_hits']=(windows>=running).mean(1)
    f['breakout_strength']=pp/pp.shift(1).rolling(252).max()-1
    f['volatility252']=simple.rolling(252).std(ddof=0)*np.sqrt(252)
    f['downside252']=np.sqrt(simple.clip(upper=0).pow(2).rolling(252).mean())*np.sqrt(252)
    f.loc[loc,'drawdown252']=(windows/running-1).min(1)
    f['positive_fraction']=simple.gt(0).astype(float).rolling(252).mean();f['zero_fraction']=simple.eq(0).astype(float).rolling(252).mean()
    f['largest_jump_share']=dr.abs().rolling(252).max()/dr.abs().rolling(252).sum().clip(lower=1e-12)
    f['tail_loss']=simple.rolling(252).quantile(.05)
    mean=simple.rolling(252).mean();sd=simple.rolling(252).std(ddof=0)
    third=simple.pow(3).rolling(252).mean()-3*mean*simple.pow(2).rolling(252).mean()+2*mean.pow(3)
    f['return_skew']=(third/sd.pow(3)).where(sd>1e-12,0)
    t=np.arange(126,dtype=float);center=t-t.mean();den=np.dot(center,center)
    s=logs.rolling(126).sum();weighted=np.full(n,np.nan);weighted[125:]=np.convolve(logs.to_numpy(),center[::-1],mode='valid')
    slope=weighted/den;variance=logs.pow(2).rolling(126).sum()-s*s/126
    f['slope126']=slope*252;f['trend_r2']=(slope*slope*den/variance).where(variance>1e-12,0)
    f['efficiency126']=(logs-logs.shift(125))/dr.abs().rolling(125).sum().clip(lower=1e-12)
    f['acceleration']=f.return21-f.return126/6
    f['observations']=np.minimum(np.arange(start,start+n),252);f['stale_days']=0.
    f['history_days']=(ds-dates[0]).days
    f['days_since_recorded_high']=(ds-dates[latest[start:]]).days
    f['distance_from_recorded_high']=pp.to_numpy()/global_high[start:]-1
    highdates=ds.to_numpy()[np.clip(loc[:,None]-252+lastmax[:,None],0,n-1)].ravel()
    f['days_since_52w_closing_high']=np.nan;f.loc[loc,'days_since_52w_closing_high']=(ds.to_numpy()[loc]-highdates)/np.timedelta64(1,'D')
    f['distance_from_52w_high']=f.high_gap252
    f['volume_active_fraction']=vv.gt(0).astype(float).rolling(252).mean()
    priorpositive=np.maximum.accumulate(np.where(volume>0,np.arange(len(volume)),0));f['last_positive_volume_lag_days']=(ds-dates[priorpositive[start:]]).days
    f['large_move_flag']=simple.abs().gt(.5).to_numpy()
    f['unresolved_action_window']=False
    for event in event_days:
        event=pd.Timestamp(event);low=pd.Series(ds).shift(252)
        f['unresolved_action_window']|=low.lt(event).to_numpy()&(ds>=event)
    f.loc[f.unresolved_action_window,RAW]=np.nan
    # Independent forward lump-return proxy, only if the365-day endpoint exists.
    target=ds+pd.Timedelta(days=365);end=np.searchsorted(dates.to_numpy(),target.to_numpy(),side='right')-1
    valid=(target<=dates[-1])&(end>=0)&((target-dates[np.maximum(end,0)]).days<=7)
    future=np.full(n,np.nan);future[valid]=p[end[valid]]/p[start:][valid]-1
    f['future_lump_return365']=future
    f=f[f.last_price_date.ge('2024-12-15')&f.last_price_date.le('2026-09-30')].copy()
    for col in RAW+['days_since_recorded_high','distance_from_recorded_high','days_since_52w_closing_high','distance_from_52w_high','volume_active_fraction','last_positive_volume_lag_days','future_lump_return365']:f[col]=f[col].astype('float32')
    return f.reset_index(drop=True)

def overlay_features(history,isin):
    """Match provider-adjusted recorded highs and365-calendar-day rolling highs."""
    if 'Adj Close' not in history:return pd.DataFrame()
    h=history.dropna(subset=['Adj Close']).copy();h=h[h['Adj Close'].gt(0)].sort_index();h=h[~h.index.duplicated()]
    if h.empty:return pd.DataFrame()
    d=pd.DatetimeIndex(pd.to_datetime(h.index)).tz_localize(None);p=h['Adj Close'].to_numpy(float);high=np.maximum.accumulate(p)
    fresh=p>np.r_[-np.inf,high[:-1]];firstpeak=np.maximum.accumulate(np.where(fresh,np.arange(len(p)),0))
    start=max(0,d.searchsorted(pd.Timestamp('2023-01-01')))
    s=pd.Series(p[start:],index=d[start:]);roll=s.rolling('365D',closed='both',min_periods=40)
    lag=roll.apply(lambda a:len(a)-1-np.argmax(a[::-1]),raw=True).to_numpy()
    peak=np.arange(len(s))-np.nan_to_num(lag).astype(int)
    age=(s.index-s.index[peak]).days.to_numpy(dtype=float);age[~np.isfinite(lag)]=np.nan
    volume=pd.Series(h.Volume.fillna(0).to_numpy(float)[start:],index=s.index)
    f=pd.DataFrame(dict(isin=isin,last_price_date=s.index,days_since_recorded_high=(s.index-d[firstpeak[start:]]).days,distance_from_recorded_high=p[start:]/high[start:]-1,days_since_52w_closing_high=age,distance_from_52w_high=s.to_numpy()/roll.max().to_numpy()-1,volume_active_fraction=volume.gt(0).astype(float).rolling('365D',closed='both',min_periods=40).mean().to_numpy()))
    return f[f.last_price_date.ge('2024-12-15')&f.last_price_date.le('2026-09-30')]

@lru_cache(maxsize=1)
def batch_context():
    identity=pd.read_csv(old.old.OUT/'current_all_stock_rankings.csv',usecols=['isin','sector'])
    sectors=identity.set_index('isin').sector.to_dict()
    mapping=pd.read_csv(CACHE/'yahoo_symbol_map.csv').dropna(subset=['yahoo_symbol']).groupby('yahoo_symbol')['isin'].apply(list).to_dict()
    events=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv');bad=events[events.status.ne('ALIGNED_MULTIPLIER')].groupby('isin').event_date.apply(list).to_dict()
    return sectors,mapping,bad

def process_batch(file):
    file=Path(file);folder=OUT/'daily_features';dest=folder/(file.stem+'.pkl.gz');sectors,mapping,bad=batch_context()
    cached=pd.read_pickle(dest,compression='gzip') if dest.exists() else None
    if cached is not None and 'overlay_basis' in cached:
        return dict(rows=len(cached),days=sorted(set(cached.last_price_date.dt.strftime('%Y-%m-%d'))),source=dict(path=file.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
    obj=pd.read_pickle(file);parts=[];overlays=[]
    for symbol,h in obj['frames'].items():
        if symbol not in mapping:continue
        h=h.copy();h.columns=[str(c) for c in h.columns]
        for isin in mapping[symbol]:
            if isin not in sectors:continue
            if cached is None:
                f=stock_features(h,isin,sectors[isin],bad.get(isin,()))
                if len(f):parts.append(f)
            overlay=overlay_features(h,isin)
            if len(overlay):overlays.append(overlay)
    f=cached if cached is not None else pd.concat(parts,ignore_index=True) if parts else pd.DataFrame()
    if len(f):
        cols=['days_since_recorded_high','distance_from_recorded_high','days_since_52w_closing_high','distance_from_52w_high','volume_active_fraction']
        f=f.drop(columns=cols).merge(pd.concat(overlays,ignore_index=True),on=['isin','last_price_date'],how='left',validate='one_to_one') if overlays else f.assign(**{c:np.nan for c in cols})
        f['overlay_basis']='ADJCLOSE_365D_FIRST_RECORDED_PEAK'
        f.to_pickle(dest,compression=dict(method='gzip',compresslevel=1))
    return dict(rows=len(f),days=sorted(set(f.last_price_date.dt.strftime('%Y-%m-%d'))) if len(f) else [],source=dict(path=file.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(file.read_bytes()).hexdigest()))

def build_daily():
    protocol();folder=OUT/'daily_features';folder.mkdir(exist_ok=True)
    days=set();sources=[];rows=0;files=sorted((CACHE/'history-cache').glob('batch_*.pkl'))
    with ProcessPoolExecutor(max_workers=2) as pool:
        for file,result in zip(files,pool.map(process_batch,files)):
            rows+=result['rows'];days.update(result['days']);sources.append(result['source'])
            print('DAILY FEATURES',file.name,rows,flush=True)
    market_days=sorted(d for d in days if '2025-01-01'<=d<='2026-09-30')
    save('daily_feature_receipt.json',dict(rows=rows,market_dates=market_days,sources=sources,source_last_date=max(days),overlay_basis='Adjusted Close;365-calendar-day high and first recorded-high occurrence; pricehead remains rawClose253-observation basis',price_vintage='Recovered2026 download; historical revisions are not point-in-time certified',suspensions='UNKNOWN; no verified historical register available'))

def high_adjustment(x):
    group=[x.decision_date,x.sector]
    eligible=x.eligible&x.sector.ne('Unclassified')
    def rank(col,age=False):
        v=x[col].where(eligible&np.isfinite(x[col]));return v.groupby(group).rank(pct=True,ascending=not age)
    age=(rank('days_since_recorded_high',True)+rank('days_since_52w_closing_high',True))/2
    gap=(rank('distance_from_recorded_high')+rank('distance_from_52w_high'))/2
    value=.6*age+.25*gap+.15*rank('momentum12_1')
    return (.01*(value-.5)).where(eligible&value.groupby(group).transform('count').ge(5),0).fillna(0)

def score_daily():
    protocol();receipt=json.loads((OUT/'daily_feature_receipt.json').read_text());days=pd.to_datetime(receipt['market_dates'])
    calendar_file=OUT/'positive_volume_calendar.json'
    if calendar_file.exists():days=pd.to_datetime(json.loads(calendar_file.read_text())['dates'])
    else:
        positive=set()
        for path in sorted((CACHE/'history-cache').glob('batch_*.pkl')):
            obj=pd.read_pickle(path)
            for h in obj['frames'].values():
                if h is None or not len(h) or 'Close' not in h or 'Volume' not in h:continue
                d=pd.DatetimeIndex(pd.to_datetime(h.index)).tz_localize(None);mask=(d>=pd.Timestamp('2025-01-01'))&(d<=pd.Timestamp('2026-09-30'))&h.Close.gt(0).to_numpy()&h.Volume.gt(0).to_numpy()
                positive.update(d[mask].strftime('%Y-%m-%d'))
        save('positive_volume_calendar.json',dict(dates=sorted(positive),definition='Union of recovered Indian symbols with positive observed close and volume; not an external official exchange calendar'))
        days=pd.to_datetime(sorted(positive))
    model26=OUT/'price_head_2026.txt'
    if not model26.exists():
        train=pd.read_pickle(old.old.OUT/'prepared.pkl.gz',compression='gzip');m,t=old.old.fit(train[train.endpoint.lt('2026-01-01')],dict(loss='rank_xendcg',target='balanced'));m.booster_.save_model(str(model26));save('model2026_audit.json',dict(max_training_endpoint=t.endpoint.max(),cutoff='2026-01-01',training_rows=len(t),recipe='original180-tree fixed balanced rank_xendcg'));del train,t,m;gc.collect()
    models={2025:lgb.Booster(model_file=str(old.old.OUT/'rank_xendcg_balanced_2025.txt')),2026:lgb.Booster(model_file=str(model26))}
    features=pd.concat([pd.read_pickle(p,compression='gzip') for p in sorted((OUT/'daily_features').glob('*.pkl.gz'))],ignore_index=True).drop_duplicates(['isin','last_price_date'],keep='first')
    features['isin']=features['isin'].astype('category');features['sector']=features['sector'].astype('category')
    identity=pd.read_csv(old.old.OUT/'current_all_stock_rankings.csv',usecols=['isin','sector'])
    action=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv')
    reset=set()
    for row in action.itertuples():
        pos=days.searchsorted(pd.Timestamp(row.event_date))
        if pos<len(days) and abs((days[pos]-pd.Timestamp(row.event_date)).days)<=7:reset.add((row.isin,days[pos]))
    folder=OUT/'daily_scores';folder.mkdir(exist_ok=True)
    feature_right=features.drop(columns='sector').copy();feature_right['isin']=feature_right['isin'].astype(str)
    for period,calendar in pd.Series(days,index=days).groupby(days.to_period('M')):
        dest=folder/f'{period}.pkl.gz'
        if dest.exists():continue
        grid=pd.MultiIndex.from_product([identity['isin'],calendar.to_numpy()],names=['isin','decision_date']).to_frame(index=False).merge(identity,on='isin',validate='many_to_one')
        right=feature_right[feature_right.last_price_date.ge(calendar.min()-pd.Timedelta(days=14))&feature_right.last_price_date.le(calendar.max())].sort_values('last_price_date')
        grid['decision_date']=grid.decision_date.astype('datetime64[ns]')
        right=right.copy();right['last_price_date']=right.last_price_date.astype('datetime64[ns]')
        x=pd.merge_asof(grid.sort_values('decision_date'),right,left_on='decision_date',right_on='last_price_date',by='isin',direction='backward',tolerance=pd.Timedelta(days=14))
        stale=(x.decision_date-x.last_price_date).dt.days;x['stale_days']=stale
        for col in ['days_since_recorded_high','days_since_52w_closing_high','last_positive_volume_lag_days']:x[col]=x[col]+stale
        x['eligible']=x.observations.ge(252)&x.history_days.ge(365)&stale.le(7)&x.last_positive_volume_lag_days.le(5)&x.volume_active_fraction.ge(.8)&x.unresolved_action_window.eq(False)&x.large_move_flag.eq(False)
        # Original per-sector normalization; raw invalid-feature rows kept for parity.
        x=old.old.engineer(x)
        for k,v in [('log_amount',np.log(7500)),('lookback_months',36.),('log_interval',np.log(30)),('target_cagr',.2)]:x[k]=v
        for col in old.old.COLS:x[col]=x[col].astype('float32')
        raw=pd.Series(models[period.year].predict(x[old.old.COLS],num_threads=3),index=x.index)
        x['price_head_percentile']=raw.groupby([x.decision_date,x.sector]).rank(pct=True)
        x['high_adjustment']=high_adjustment(x)
        x['component_score']=.25*x.price_head_percentile+x.high_adjustment
        x.loc[~x.eligible,'component_score']=np.nan
        x['known_action_reset']=[(i,d) in reset for i,d in zip(x['isin'],x.decision_date)]
        # Forward proxy was observed at last_price_date; do not carry a label across missing quote dates.
        x.loc[stale.ne(0),'future_lump_return365']=np.nan
        cols=['isin','sector','decision_date','last_price_date','eligible','known_action_reset','component_score','price_head_percentile','high_adjustment','future_lump_return365']
        x[cols].to_pickle(dest,compression='gzip');print('DAILY SCORE',period,len(x),int(x.eligible.sum()),flush=True)
    save('daily_score_receipt.json',dict(formula='.25*annual_price_head_sector_percentile+high_adjustment',full_champion=False,missing_components=['open-model daily contribution','profile-defensive daily contribution','execution-correct daily trailing SIP overlay'],date_range=[str(days.min().date()),str(days.max().date())],model2025_sha256=hashlib.sha256((old.old.OUT/'rank_xendcg_balanced_2025.txt').read_bytes()).hexdigest(),model2026_sha256=hashlib.sha256(model26.read_bytes()).hexdigest(),verified_suspensions='UNKNOWN',safety_event_knowledge='Retrospective ex-date register; broadcast-time availability uncertified'))

def analyze_daily():
    protocol();locked=json.loads((OUT/'development_lock.json').read_text())['margin']
    x=pd.concat([pd.read_pickle(p,compression='gzip') for p in sorted((OUT/'daily_scores').glob('*.pkl.gz'))],ignore_index=True)
    rows=[];lags=[];coverage=x.groupby('decision_date').agg(rows=('isin','size'),eligible=('eligible','sum'),known_action_names=('known_action_reset','sum'),mature_proxy_rows=('future_lump_return365','count'));coverage.to_csv(OUT/'daily_coverage.csv')
    for sector,g in x.groupby('sector',observed=True):
        snapshots=[]
        for day,h in g.groupby('decision_date',sort=True):
            score=h.set_index('isin').component_score.to_dict();outcome=h.set_index('isin').future_lump_return365.to_dict();blocked=set(h.loc[~h.eligible,'isin'])
            snapshots.append((str(day.date()),score,outcome,blocked,bool(h.known_action_reset.any())))
        for margin in MARGINS:
            records,events=evaluate_series(snapshots,margin,daily=True)
            for a in records:a['sector']=sector
            for a in events:a.update(sector=sector,margin=margin)
            rows.extend(records);lags.extend(events)
        print('DAILY ANALYZE',sector,len(rows),flush=True)
    q=pd.DataFrame(rows);q.to_csv(OUT/'daily_queries.csv.gz',index=False);l=pd.DataFrame(lags);l.to_csv(OUT/'daily_leader_lags.csv.gz',index=False)
    summary=q.groupby('margin')[['kendall_tau','raw_tau','top3_churn','raw_top3_churn','ic_delta','blocked_retained','safety_reset']].mean().reset_index()
    summary['churn_reduction']=1-summary.top3_churn/summary.raw_top3_churn
    l['entered_within5_sessions']=~l.right_censored&l.entry_lag_sessions.le(5)
    delay=l.groupby('margin').agg(leader_events=('isin','size'),censored_fraction=('right_censored','mean'),lag_p90_lower_bound=('entry_lag_sessions',lambda s:s.quantile(.9)),lag_median_lower_bound=('entry_lag_sessions','median'),fraction_entered_within5=('entered_within5_sessions','mean'))
    summary=summary.merge(delay,on='margin',how='left');summary['selected']=summary.margin.eq(locked);summary.to_csv(OUT/'daily_frontier.csv',index=False)
    q.assign(year=pd.to_datetime(q.date).dt.year).groupby(['year','margin'])[['kendall_tau','raw_tau','top3_churn','raw_top3_churn','ic_delta']].mean().reset_index().to_csv(OUT/'daily_by_year.csv',index=False)
    selected=summary[summary.selected].iloc[0]
    save('daily_decision.json',dict(locked_margin=locked,diagnostic_churn_gate=bool(selected.churn_reduction>=.20),diagnostic_IC_gate=bool(selected.ic_delta>=-.001),diagnostic_lag_gate=bool(selected.fraction_entered_within5>=.9),known_blocked_retention=int(q.blocked_retained.sum()),production_ready=False,reason='Component-only replay; full champion and certified historic suspension/announcement-time coverage unavailable. Lag gate conservatively requires90% ofall events observed entering within5 sessions; censored episodes do not count as successes.',selected=selected.to_dict()))
    print('DAILY RESULT',summary.to_dict('records'),flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('stage',choices=['protocol','quarterly','build_daily','score_daily','analyze_daily']);args=a.parse_args();globals()[args.stage]()
