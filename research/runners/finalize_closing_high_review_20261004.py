"""Independently reproduce reviewed scoring, exports and comparison populations."""
from pathlib import Path
import sys, json, hashlib
import numpy as np
import pandas as pd

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'src'))
from stock_ranker.personalized_peak_product import PeakRankingService
from stock_ranker.personalized_product import parse_profile

OUT=ROOT/'experiments/closing-high-recovery-20261004'

def run():
    service=PeakRankingService(sector_tuned=False)
    facts=service.facts.set_index('isin')
    parts=[]
    for name,group in service.current.groupby('profile_name'):
        r=group.iloc[0]
        payload={'amount':float(r.amount_per_contribution),'lookback_months':int(r.lookback_months),
                 'interval_days':int(r.frequency_days),'target_cagr_percent':float(r.target_cagr)*100,'horizon_months':int(r.horizon_months)}
        actual,_=service._calculate(parse_profile(payload))
        # Independent arithmetic from the saved V17 evidence and static receipt.
        z=group.copy()
        static=service.peak_features.reindex(z['isin'])
        age=np.exp(-z.days_since_recorded_high.clip(lower=0)/1095.75)
        distance=z.distance_from_recorded_high.clip(-1,0)
        recovery=np.exp(-(distance/.05)**2)
        momentum=pd.Series(static.momentum_12_1.to_numpy(),index=z.index).rank(pct=True).fillna(.5)
        risk=z.downside_volatility_1y.rank(pct=True,ascending=False).fillna(.5)
        score=.5*z.winner_score+.15*(age+(1-age)*recovery)+.09*(1+distance)+.06*static.high52_freshness.to_numpy()+.1*momentum+.1*risk
        aligned=facts.reindex(z['isin'])
        sme=((aligned.primary_exchange.eq('BSE')&aligned.series.isin(['M','MT']))|
             (aligned.primary_exchange.eq('NSE')&aligned.series.isin(['SM','ST']))).to_numpy()
        eligible=(static.volume_active_fraction.ge(.8)&np.expm1(static.traded_value).ge(100*payload['amount'])&
                  static.observations_1y.ge(120)&static.quote_freshness.ge(30/37)&static.last_positive_volume_lag_days.le(7)).to_numpy()&~sme
        score=score.where(eligible)
        np.testing.assert_allclose(actual.personalized_score,score,atol=1e-12,rtol=0,equal_nan=True)
        ordered=z.assign(score=score).dropna(subset=['score']).sort_values(['score','isin'],ascending=[False,True])
        expected_rank=pd.Series(np.arange(1,len(ordered)+1),index=ordered.index).reindex(z.index)
        np.testing.assert_allclose(actual.personalized_rank,expected_rank,atol=0,rtol=0,equal_nan=True)
        parts.append(actual)
    data=pd.concat(parts,ignore_index=True)
    data.to_csv(OUT/'reviewed_current_rankings.csv.gz',index=False)
    for n in [20,50,100]:
        top=data[data.personalized_rank.le(n)].sort_values(['profile_name','personalized_rank'])
        assert len(top)==9*n
        top.to_csv(OUT/f'reviewed_top{n}.csv',index=False)
    base=data[data.profile_name.eq('base7500')]
    old=pd.read_csv(ROOT/'experiments/v17-peak-confirmation-20261004/current_rankings.csv.gz',usecols=['isin','profile_name','new_rank','new_score'])
    changes=base[['isin','ticker','personalized_rank','personalized_score','history_months','days_since_recorded_high','activity_filter_reason']].merge(old[old.profile_name.eq('base7500')],on='isin',validate='one_to_one')
    changes.to_csv(OUT/'default_rank_changes.csv',index=False)
    common=base[base.personalized_rank.notna()&base.professor_whole_share_score.notna()].copy()
    common['reviewed_common_rank']=common.personalized_rank.rank(method='min')
    common['professor_common_rank']=common.professor_whole_share_score.rank(ascending=False,method='min')
    common[['isin','ticker','reviewed_common_rank','professor_common_rank']].to_csv(OUT/'professor_common_comparison.csv',index=False)
    metrics=pd.read_csv(OUT/'metrics.csv')
    pair=metrics[metrics.model.eq('old_score')].merge(metrics[metrics.model.eq('recovery_score')],on=['period','decision_date','profile'],suffixes=('_old','_new'),validate='one_to_one')
    assert len(pair)==396 and (pair.n_old==pair.n_new).all()
    pair.to_csv(OUT/'paired_historical_metrics.csv',index=False)
    delta_columns=[]
    for col in ['median_xirr_top20','mean_asset_drawdown_top20','target_achievement_top20','target_shortfall_top20','ndcg20']:
        name=col+'_delta'
        pair[name]=pair[col+'_new']-pair[col+'_old'];delta_columns.append(name)
    pair.groupby(['period','profile'])[delta_columns].mean().to_csv(OUT/'profile_tradeoffs.csv')
    report=service.rank({'amount':7500,'lookback_months':36,'interval_days':30,'target_cagr_percent':20,'horizon_months':12})
    (OUT/'default_api_response.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    result={'profiles_reproduced':9,'universe':len(base),'eligible':int(base.personalized_rank.notna().sum()),
            'paired_historical_comparisons':396,'identical_historical_populations':True,
            'professor_common_population':len(common),
            'professor_top100_overlap':len(set(common.loc[common.reviewed_common_rank.le(100),'isin'])&set(common.loc[common.professor_common_rank.le(100),'isin'])),
            'professor_spearman':common.reviewed_common_rank.corr(common.professor_common_rank,method='spearman'),
            'sme_gate_count':int(base.activity_filter_reason.eq('SME_LOT_SIZE_UNVERIFIED').sum()),
            'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in OUT.glob('*.csv*')}}
    (OUT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k!='files'},indent=2))
    print(changes[changes.ticker.isin(['NYKAA','LALPATHLAB','NAZARA','ONEPOINT','KPL','FRONTSP','MWL','PTCIL','STEELCAS'])].to_string(index=False))

if __name__=='__main__':run()
