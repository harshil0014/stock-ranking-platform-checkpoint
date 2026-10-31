"""Low-memory majority-factor experiment; no production promotion or fresh claims."""
import os
for key in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS']:
    os.environ[key] = '1'
from pathlib import Path
import argparse, datetime as dt, gc, hashlib, json
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from sklearn.linear_model import Ridge
from stock_research.professor_factor_model import FACTOR_COLUMNS, price_features, normalize_factors, constrained_weights, score

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT/'experiments/professor-majority-20261031'
PROTOCOL = ROOT/'research/protocols/professor_majority_20261031.json'
KEYS = ['isin', 'decision_date', 'profile_name']
NAMES = ['active_champion', 'factor80_fixed', 'factor90_fixed', 'factor90_learned']


def save(name, value):
    (OUT/name).write_text(json.dumps(value, indent=2, default=lambda v: v.item() if hasattr(v, 'item') else str(v), allow_nan=False)+'\n')


def read_base(path, cols):
    rows = []
    for chunk in pd.read_csv(path, usecols=list(dict.fromkeys(KEYS+cols)), chunksize=20000):
        rows.append(chunk.loc[chunk.profile_name.eq('base7500')].copy())
    result = pd.concat(rows, ignore_index=True)
    if result.duplicated(KEYS).any():
        raise ValueError('Duplicate source key: '+str(path))
    print('READ', path.name, len(result), flush=True)
    return result


def prepare():
    if (OUT/'prepared.pkl.gz').exists():
        return
    protocol = json.loads(PROTOCOL.read_text())
    scorepath = ROOT/'experiments/champion-sip-profit-20261017/historical_scores.csv.gz'
    panelpath = ROOT/'experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz'
    history = ROOT/'research/runtime/personalized-v17/history.npz'
    currentpath = ROOT/'experiments/champion-double-emphasis-20261017/current_all_4436_audit.csv'
    x = read_base(scorepath, ['sip_risk_confirmed_0.01']).rename(columns={'sip_risk_confirmed_0.01':'champion_score'})
    deep = read_base(panelpath, ['professor_whole_share_score', 'unused_cash_excluded_by_professor', 'amount_contributed',
                               'future_xirr', 'future_drawdown', 'future_shortfall', 'endpoint'])
    x = x.merge(deep, on=KEYS, how='left', validate='one_to_one'); del deep; gc.collect()
    current = pd.read_csv(currentpath)
    identities = current[['isin', 'sector', 'evidence_fraction']].copy()
    # Evidence fraction is later replaced by dated trading-activity coverage.
    x = x.merge(identities[['isin','sector']], on='isin', how='left', validate='many_to_one')
    current['champion_score'] = current['sip_risk_confirmed_0.01']
    current = current[KEYS+['sector','champion_score','professor_whole_share_score',
                             'unused_cash_excluded_by_professor','amount_contributed']].copy()
    current['endpoint'] = None
    for col in ['future_xirr','future_drawdown','future_shortfall']:
        current[col] = np.nan
    x = pd.concat([x, current], ignore_index=True)
    x['sip_profit'] = x.professor_whole_share_score
    x['sip_invested_fraction'] = 1-x.unused_cash_excluded_by_professor/x.amount_contributed.where(x.amount_contributed.gt(0))
    activitypath = ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz'
    activity = pd.read_csv(activitypath, usecols=['isin','decision_date','volume_active_fraction','last_positive_volume_lag_days'])
    x = x.merge(activity, on=['isin','decision_date'], how='left', validate='many_to_one')
    x['evidence_fraction'] = x.volume_active_fraction.notna().astype(float)
    events_path = ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv'
    events = pd.read_csv(events_path); events = events.loc[events.status.ne('ALIGNED_MULTIPLIER')]
    x['sip_action_blocked'] = False
    dates = pd.to_datetime(x.decision_date); starts = dates-pd.DateOffset(months=36)
    for identity, group in events.groupby('isin'):
        ids = x.index[x['isin'].eq(identity)]
        for day in pd.to_datetime(group.event_date):
            x.loc[ids, 'sip_action_blocked'] |= (starts.loc[ids].lt(day) & dates.loc[ids].ge(day)).to_numpy()
            endpoint = pd.to_datetime(x.loc[ids,'endpoint'])
            blocked = dates.loc[ids].lt(day) & endpoint.ge(day)
            x.loc[ids[blocked.to_numpy()], ['future_xirr','future_drawdown','future_shortfall']] = np.nan
    required_dates = sorted(x.decision_date.unique()); rows = []
    unresolved = {i:np.array(g.event_date, dtype='datetime64[D]') for i,g in events.groupby('isin')}
    with np.load(history, allow_pickle=False) as a:
        ids = a['identities'].astype(str); offsets = a['offsets']; ds = a['dates'].astype('datetime64[D]'); prices = a['raw']
        for n, identity in enumerate(ids):
            d = ds[int(offsets[n]):int(offsets[n+1])]; p = prices[int(offsets[n]):int(offsets[n+1])]
            for day in required_dates:
                features = price_features(d,p,day)
                # Available-history high needs an intact historical adjustment basis.
                bad = unresolved.get(identity, np.array([], dtype='datetime64[D]'))
                if len(d) and np.any((bad>=d[0]) & (bad<=np.datetime64(day))):
                    features = {c:np.nan for c in features}
                rows.append(dict(isin=identity,decision_date=day,**features))
            if (n+1)%500==0: print('PRICE FEATURES',n+1,flush=True)
    x = x.merge(pd.DataFrame(rows), on=['isin','decision_date'], how='left', validate='many_to_one')
    x = normalize_factors(x)
    if x.duplicated(KEYS).any(): raise ValueError('Duplicate prepared key')
    x.to_pickle(OUT/'prepared.pkl.gz', compression='gzip')
    coverage = x.groupby('decision_date').agg(rows=('isin','size'), factor_eligible=('factor_eligible','sum'))
    coverage.to_csv(OUT/'coverage.csv')
    save('source_receipt.json', dict(protocol_sha256=hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
         source_sha256={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [scorepath,panelpath,history,currentpath,activitypath,events_path]},
         rows=len(x), eligible=int(x.factor_eligible.sum()), profile='base7500', future_prices_not_used=True,
         price_basis='Frozen provider Close, already split-adjusted; not dividend TRI or certified point-in-time source',
         lifetime_high_claim=False, sectors='Current retrospective sectors; not point-in-time', complete_fundamentals=False))
    print('PREPARED',x.shape,'eligible',int(x.factor_eligible.sum()),flush=True)


def fit_and_score():
    if (OUT/'scored.pkl.gz').exists(): return
    x = pd.read_pickle(OUT/'prepared.pkl.gz', compression='gzip')
    x['active_champion'] = x.champion_percentile
    x['factor80_fixed'] = score(x,np.ones(5)/5,.8)
    x['factor90_fixed'] = score(x,np.ones(5)/5,.9)
    x['factor90_learned'] = np.nan
    cols = ['q_'+c for c in FACTOR_COLUMNS]; audits=[]
    for year in list(range(2020,2026))+[2026]:
        cutoff=f'{year}-01-01' if year<2026 else '2026-10-03'
        train=x.loc[x.factor_eligible & x.endpoint.notna() & x.endpoint.lt(cutoff)].dropna(subset=['future_xirr','future_drawdown','future_shortfall']).copy()
        train=train.loc[train.groupby(['decision_date','sector'])['isin'].transform('size').ge(5)]
        groups=train.groupby(['decision_date','sector'])
        y=.5*groups.future_xirr.rank(pct=True)+.25*groups.future_drawdown.rank(pct=True)+.25*groups.future_shortfall.rank(pct=True,ascending=False)
        weights=1/groups['isin'].transform('size'); weights=weights/weights.mean()
        model=Ridge(alpha=10,positive=True,max_iter=2000,tol=1e-6)
        if len(train)<100 or train.decision_date.nunique()<2: raise ValueError('Insufficient mature training support')
        model.fit(train[cols],y,sample_weight=weights)
        core=constrained_weights(model.coef_)
        mask=x.decision_date.str.startswith(str(year)) if year<2026 else x.decision_date.eq('2026-10-03')
        x.loc[mask,'factor90_learned']=score(x.loc[mask],core,.9)
        audits.append(dict(year=year,cutoff=cutoff,max_training_endpoint=train.endpoint.max(),training_dates=train.decision_date.nunique(),training_rows=len(train),
                           core_weights=dict(zip(FACTOR_COLUMNS,core.tolist())),final_factor_weights=dict(zip(FACTOR_COLUMNS,(.9*core).tolist())),champion_weight=.1,
                           ridge_raw_coefficients=model.coef_.tolist()))
        print('FITTED',year,len(train),flush=True)
    save('fit_audits.json',audits)
    x.to_pickle(OUT/'scored.pkl.gz',compression='gzip')
    current=x.loc[x.decision_date.eq('2026-10-03')].copy()
    for name in NAMES:
        current[name+'_rank']=current[name].groupby(current.sector).rank(method='min',ascending=False)
    current.to_csv(OUT/'current_rankings.csv.gz',index=False)


def evaluate_period(x,period):
    from champion_market_evaluate_20261031 import metrics
    x=x.loc[x.factor_eligible & x.decision_date.ge('2020-01-01')]
    x=x.loc[x.decision_date.lt('2024-01-01') if period=='development' else x.decision_date.ge('2024-01-01') & x.decision_date.lt('2026-01-01')]
    rows=[];alignment=[];support=[];factors=['q_'+c for c in FACTOR_COLUMNS]
    for (day,sector),g in x.groupby(['decision_date','sector']):
        g=g.sort_values('isin'); picks={n:g.sort_values([n,'isin'],ascending=[False,True]).head(3) for n in NAMES}
        baseline=set(picks['active_champion']['isin'])
        for n,h in picks.items():
            alignment.append(dict(period=period,decision_date=day,sector=sector,model=n,alignment=float(h[factors].mean().mean()),
                                   changed=set(h['isin'])!=baseline,shared=len(set(h['isin'])&baseline),**h[factors].mean().to_dict()))
        valid=g.dropna(subset=['future_xirr','future_drawdown','future_shortfall'])
        top_valid=all(h[['future_xirr','future_drawdown','future_shortfall']].notna().all().all() for h in picks.values())
        support.append(dict(period=period,decision_date=day,sector=sector,feature_rows=len(g),valid_outcome_rows=len(valid),all_model_top3_outcomes_available=bool(top_valid)))
        if len(valid)<5: continue
        z=valid.copy();z['goal_hit']=z.future_xirr+1e-7>=.2
        for r in metrics(z,NAMES):
            n=r['model'];h=picks[n]
            # Never reselect after dropping missing forward outcomes.
            for k in list(r):
                if k.endswith(('3','10','20')): r[k]=np.nan
            if top_valid:
                r['attainment3']=float((h.future_xirr+1e-7>=.2).mean())
                r['drawdown3']=float(h.future_drawdown.mean());r['xirr3']=float(h.future_xirr.median());r['shortfall3']=float(h.future_shortfall.mean())
            r.update(period=period,decision_date=day,sector=sector);rows.append(r)
    q=pd.DataFrame(rows);a=pd.DataFrame(alignment);s=pd.DataFrame(support)
    q.to_csv(OUT/f'queries_{period}.csv.gz',index=False);a.to_csv(OUT/f'alignment_{period}.csv.gz',index=False);s.to_csv(OUT/f'support_{period}.csv',index=False)
    metrics_cols=['rank_ic','pair_accuracy','attainment3','drawdown3','xirr3','shortfall3']
    summary=q.groupby(['model','decision_date'])[metrics_cols].mean().groupby('model').mean()
    aa=a.groupby(['model','decision_date'])[['alignment','changed','shared']+factors].mean().groupby('model').mean()
    result=summary.join(aa);result['period']=period
    result.to_csv(OUT/f'summary_{period}.csv')
    return result


def evaluate():
    x=pd.read_pickle(OUT/'scored.pkl.gz',compression='gzip')
    dev=evaluate_period(x,'development');delta=dev.drop(columns='period')-dev.loc['active_champion'].drop('period')
    eligible=[n for n in NAMES[1:] if delta.loc[n,'alignment']>=.02 and delta.loc[n,'rank_ic']>=-.01 and delta.loc[n,'drawdown3']>=-.02 and dev.loc[n,'changed']>=.10]
    winner=max(eligible,key=lambda n:(delta.loc[n,'alignment'],n)) if eligible else None
    save('development_lock.json',dict(selected=winner,eligible=eligible,locked_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),selection='Development-only alignment gain subject to fixed point risk/IC limits. All history previously exposed. No investment/production pass without portfolio cashflow evidence.'))
    exp=evaluate_period(x,'exposed')
    result=pd.concat([dev,exp]);result.to_csv(OUT/'summary.csv')
    save('decision.json',dict(selected_by_development=winner,production_promoted=False,fresh_holdout=False,portfolio_noninferiority='UNTESTED_IN_THIS_ROUND',
                             final_status='RESEARCH_CANDIDATE_ONLY' if winner else 'NO_CANDIDATE_PASSED_DEVELOPMENT_LIMITS'))
    print(result[['period','alignment','changed','rank_ic','attainment3','drawdown3']].to_string(),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['prepare','fit','evaluate']);a=p.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    if not PROTOCOL.exists(): raise RuntimeError('Freeze protocol first')
    {'prepare':prepare,'fit':fit_and_score,'evaluate':evaluate}[a.stage]()


if __name__=='__main__':main()
