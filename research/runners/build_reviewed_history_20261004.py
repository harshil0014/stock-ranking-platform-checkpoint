"""Validate BSE overlaps and rebuild current inference without altering V17."""
from pathlib import Path
import sys, json, hashlib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'research/runners')]
from stock_ranker.personalized_v17_product import V17RankingService
from stock_ranker.personalized_product import parse_profile
import personalized_v15_20261003 as v
from yahoo_full_recovery_v1_20261003 import metrics

OUT=ROOT/'experiments/closing-high-recovery-20261004'
RECEIPTS=OUT/'history-receipts'
# Do not pass unverified old corporate actions into SIP or price features.
START={'KPL':'2018-01-01','FRONTSP':'2000-01-01','PTCIL':'2022-07-25','STEELCAS':'2020-01-01'}
NOTICE='https://www.bseindia.com/markets/MarketInfo/DispNewNoticesCirculars.aspx?page=20260310-46'

def run():
    service=V17RankingService()
    book=service._load_book()
    facts=service.facts.copy().set_index('ticker',drop=False)
    original=service.current.copy()
    frames={}
    for path in v.YAHOO.glob('*.pkl'):
        for symbol,frame in pd.read_pickle(path).get('frames',{}).items():
            if symbol in {t+'.NS' for t in START}:frames[symbol]=frame
    notice=(RECEIPTS/'frontier_bonus_notice.html').read_text(encoding='utf-8')
    assert '522195' in notice and '13/03/2026' in notice and '20260310-46' in notice
    audit=[];feature_rows=[];audit_history=pd.read_csv(ROOT/'research/runtime/personalized-v17/current_plan_history_audit.csv')
    for ticker,start in START.items():
        identity=facts.loc[ticker,'isin']
        f=pd.read_csv(RECEIPTS/(ticker+'.csv.gz'),index_col=0)
        f.index=pd.to_datetime(f.index).tz_localize(None)
        f=f.loc[start:'2026-10-03'].dropna(subset=['Close','Adj Close'])
        assert f.index.is_unique and f.index.is_monotonic_increasing and len(f)>750
        prior=frames[ticker+'.NS'].Close.dropna()
        aligned=pd.concat([prior.rename('nse'),f.Close.rename('bse')],axis=1).dropna()
        deviation=(aligned.bse/aligned.nse-1).abs()
        assert len(aligned)>=30 and deviation.median()<.01 and deviation.quantile(.95)<.05,(ticker,deviation.describe())
        # Any retained provider split must match a verified action, including date.
        actions=book.actions.get(identity,pd.DataFrame()).copy()
        if ticker=='FRONTSP':
            template=pd.read_csv(service.package/'actions.csv.gz').iloc[0].copy()
            template.update(pd.Series({'isin':identity,'ticker':ticker,'exchange':'BSE','event_date':pd.Timestamp('2026-03-13'),
                'source_text':'2 bonus shares for each existing share; BSE 20260310-46','event_type':'BONUS',
                'source_event_type':'BONUS','mechanics_status':'AUTO_MULTIPLIER','block_reason':None,
                'total_share_multiplier':3.,'multiplier_numerator':2.,'multiplier_denominator':1.,
                'evidence_url':NOTICE,'mapping_basis':'EXACT_BSE_SECURITY_CODE','policy_assumption':False}))
            actions=pd.DataFrame([template]);book.actions[identity]=actions
        splits=f[f['Stock Splits'].ne(0)]['Stock Splits']
        for day,ratio in splits.items():
            matched=actions[pd.to_datetime(actions.event_date).eq(day)]
            assert len(matched)==1 and abs(float(matched.iloc[0].total_share_multiplier)-ratio)<1e-9,(ticker,day)
        dates=f.index.to_numpy(dtype='datetime64[D]')
        factor=np.ones(len(f))
        for day,ratio in splits.items():factor[dates<np.datetime64(day.date())]*=ratio
        raw=f.Close.to_numpy(float);nominal=raw*factor
        book.arrays[identity]=(dates,raw,raw,nominal,factor)
        book.errors.pop(identity,None)
        stats,status=metrics(f)
        assert status=='CURRENT_HISTORY'
        for col,value in stats.items():
            if col in facts:facts.loc[ticker,col]=value
        for years in [1,3,5,7,10]:
            facts.loc[ticker,f'current_has_true_{years}y']=pd.notna(stats.get(f'yahoo_strict_cagr_{years}y'))
        adj=f['Adj Close'];span=(adj.index[-1]-adj.index[0]).days
        audit_history.loc[audit_history['isin'].eq(identity),'history_start_cagr']=np.expm1(np.log(adj.iloc[-1]/adj.iloc[0])*365/span)
        yr=f.loc['2025-10-03':];p=yr['Adj Close'];day=p[p.eq(p.max())].index[-1]
        last_trade=f.loc[f.Volume.gt(0)].index[-1]
        feature_rows.append({'isin':identity,'decision_date':'2026-10-03','high52_freshness':365/(365+(pd.Timestamp('2026-10-03')-day).days),
            'momentum_12_1':adj.loc[:'2026-09-03'].iloc[-1]/adj.loc[:'2025-10-03'].iloc[-1]-1,
            'volume_active_fraction':yr.Volume.gt(0).mean(),'traded_value':np.log1p((yr.Close*yr.Volume).median()),
            'observations_1y':len(yr),'quote_freshness':30/(30+(pd.Timestamp('2026-10-03')-f.index[-1]).days),
            'last_positive_volume_lag_days':(pd.Timestamp('2026-10-03')-last_trade).days,
            'last_observed_date':str(f.index[-1].date())})
        audit.append({'ticker':ticker,'isin':identity,'bse_code':int(facts.loc[ticker,'screener_bse_code']),
            'provider_symbol':ticker+'.BO','overlap_observations':len(aligned),'median_close_difference':float(deviation.median()),
            'p95_close_difference':float(deviation.quantile(.95)),'usable_start':start,'observed_months':stats['yahoo_history_months'],
            'scope':'Continuous BSE series; not spliced. History before retained start is not certified.',
            'excluded_older_action':{'KPL':'2017 bonus','PTCIL':'2022 rights subscription','STEELCAS':'2012 split','FRONTSP':None}[ticker],
            'verified_actions':[str(day.date()) for day in splits.index]})
    v.OUT=OUT
    audit_history.to_csv(OUT/'current_plan_history_audit.csv',index=False)
    updated=v.current_features(original,facts.reset_index(drop=True))
    # Restrict changes to the four repaired identities; keep all other evidence exact.
    recovered=set(facts.loc[list(START),'isin'])
    mask=original['isin'].isin(recovered)
    for col in updated.columns:
        if col in service.current:service.current.loc[mask,col]=updated.loc[mask,col]
    parts=[]
    for name,group in service.current.groupby('profile_name'):
        r=group.iloc[0]
        profile=parse_profile({'amount':float(r.amount_per_contribution),'lookback_months':int(r.lookback_months),
            'interval_days':int(r.frequency_days),'target_cagr_percent':float(r.target_cagr)*100,'horizon_months':int(r.horizon_months)})
        current,_=service._calculate(profile,use_stored_frozen_profile=False)
        current['profile_name']=name
        parts.append(current)
        print('REBUILT',name,flush=True)
    pd.concat(parts,ignore_index=True).to_csv(OUT/'peak_current.csv.gz',index=False)
    feature=pd.read_csv(service.package/'peak_features.csv.gz').set_index(['isin','decision_date'])
    add=pd.DataFrame(feature_rows).set_index(['isin','decision_date'])
    feature=feature.reindex(feature.index.union(add.index))
    feature.update(add)
    feature.reset_index().to_csv(OUT/'peak_features_reviewed.csv.gz',index=False)
    pd.concat(book.actions.values(),ignore_index=True).to_csv(OUT/'peak_actions.csv.gz',index=False)
    names=sorted(recovered);offsets=[0];arrays=[[] for _ in range(5)]
    for identity in names:
        values=book.arrays[identity]
        for dest,value in zip(arrays,values):dest.append(value)
        offsets.append(offsets[-1]+len(values[0]))
    np.savez_compressed(OUT/'peak_history.npz',identities=np.asarray(names),offsets=np.asarray(offsets),
        dates=np.concatenate(arrays[0]).astype('datetime64[D]').astype(np.int32),
        **{n:np.concatenate(a) for n,a in zip(['raw','adjusted','nominal','factor'],arrays[1:])})
    (OUT/'history_validation.json').write_text(json.dumps(audit,indent=2))
    (OUT/'history_build_manifest.json').write_text(json.dumps({'files':{n:hashlib.sha256((OUT/n).read_bytes()).hexdigest()
        for n in ['peak_current.csv.gz','peak_features_reviewed.csv.gz','peak_actions.csv.gz','peak_history.npz','history_validation.json']},
        'source_receipts':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RECEIPTS.glob('*.csv.gz')},
        'bonus_notice_sha256':hashlib.sha256((RECEIPTS/'frontier_bonus_notice.html').read_bytes()).hexdigest()},indent=2))

if __name__=='__main__':run()
