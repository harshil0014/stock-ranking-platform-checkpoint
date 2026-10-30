"""Bounded, literature-informed closing-high recency adjustments to the champion."""
import json, hashlib
import numpy as np
import pandas as pd
import champion_peer_context_20261017 as base
import champion_tradeoff_review_20261017 as preference
p=base.p
OUT=p.ROOT/'experiments/champion-high-recency-20261017'
AGE='days_since_recorded_high'
SOURCES=[p.ROOT/'experiments/personalized-deep-championship-20261002/v3/prepared.pkl.gz',p.ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz',p.ROOT/'experiments/v17-peak-activity-20261004/priority_current_rankings.csv.gz']
CONFIGS={f'{kind}_w{w}':(kind,w) for kind in ['rolling','recorded','dual'] for w in [.01,.025,.05]}

def protocol():
    OUT.mkdir(exist_ok=True)
    doc={'configs':CONFIGS,'formula':'C + w*(H-.5); H=.60 recency percentile+.25 high-proximity percentile+.15 momentum percentile. C and all existing component weights unchanged. Recency carries most of added adjustment, not most of entire champion.',
      'recency':'Rolling: inverse calendar days since 52-week closing high. Recorded: inverse days since recorded closing high. Dual: average of both inverse-age percentiles. Within date/profile/sector eligible peers, average ties.',
      'eligibility':'Usable champion evidence, >=252 observations, >=365 history days, >=80% active volume, last positive volume <=14 days, valid nonnegative ages, valid proximity and momentum; >=5 eligible sector peers. Recorded high is available-history high, not certified lifetime ATH.',
      'missing':'Zero correction for ineligible rows; missing high age is never a recent high.',
      'selection':'2020-23 expanded capped Top3 preference utility with rankIC .4 NDCG .25 achievement .15 inverse shortfall .1 drawdown .1, normalized by .01; zero XIRR selection weight. Lock one before later evaluation. Same utility as user-authorized previous round.',
      'acceptance':'Positive development and later utility, positive later ranking-only and equal-five utility; later drawdown and achievement loss each <=1pp; report all sector/profile tradeoffs.',
      'fresh_validation':False,'sources':['https://www.sciencedirect.com/science/article/pii/S0378426613002446','https://onlinelibrary.wiley.com/doi/full/10.1111/j.1540-6261.2004.00695.x'],
      'adaptation':'Transparent signal adjustment, not paper replication or imported pretrained model. All strength/mixture choices are engineering hypotheses.',
      'source_hashes':{str(s.relative_to(p.ROOT)):hashlib.sha256(s.read_bytes()).hexdigest() for s in SOURCES}}
    f=OUT/'protocol.json'
    if f.exists():assert json.loads(f.read_text())==json.loads(json.dumps(doc))
    else:f.write_text(json.dumps(doc,indent=2))

def attach(z,current=False):
    if current:
        old=pd.read_csv(SOURCES[2],usecols=p.KEYS+[AGE,'distance_from_recorded_high','distance_from_52w_high'])
    else:
        old=pd.read_pickle(SOURCES[0],compression='gzip')[p.KEYS+[AGE,'distance_from_recorded_high','distance_from_52w_high']]
    z=z.drop(columns=[AGE,'distance_from_recorded_high','distance_from_52w_high'],errors='ignore').merge(old,on=p.KEYS,how='left',validate='one_to_one')
    fields=['days_since_52w_closing_high','volume_active_fraction','last_positive_volume_lag_days','last_observed_date']
    activity=pd.read_csv(SOURCES[1],usecols=['isin','decision_date']+fields)
    assert activity.last_observed_date.dropna().le(activity.loc[activity.last_observed_date.notna(),'decision_date']).all()
    z=z.drop(columns=fields,errors='ignore').merge(activity,on=['isin','decision_date'],how='left',validate='many_to_one')
    return z

def signals(z):
    z=z.copy();keys=['decision_date','profile_name','sector']
    eligible=z.evidence_fraction.gt(0)&z.observations.ge(252)&z.history_days.ge(365)&z.volume_active_fraction.ge(.8)&z.last_positive_volume_lag_days.between(0,14)&z.sector.ne('Unclassified')
    inputs={'roll_age':'days_since_52w_closing_high','ath_age':AGE,'roll_gap':'distance_from_52w_high','ath_gap':'distance_from_recorded_high','momentum':'momentum12_1'}
    for name,col in inputs.items():
        value=z[col].where(eligible & np.isfinite(z[col]))
        if 'age' in name:value=value.where(value.ge(0))
        z['s_'+name]=value.groupby([z[k] for k in keys]).rank(pct=True,ascending='age' not in name)
    for kind in ['rolling','recorded','dual']:
        age=z.s_roll_age if kind=='rolling' else z.s_ath_age if kind=='recorded' else (z.s_roll_age+z.s_ath_age)/2
        gap=z.s_roll_gap if kind=='rolling' else z.s_ath_gap if kind=='recorded' else (z.s_roll_gap+z.s_ath_gap)/2
        h=.6*age+.25*gap+.15*z.s_momentum
        count=h.groupby([z[k] for k in keys]).transform('count')
        z['adjust_'+kind]=(h-.5).where(eligible & count.ge(5),0).fillna(0)
    for name,(kind,w) in CONFIGS.items():z[name]=z[base.ANCHOR]+w*z['adjust_'+kind]
    return z

def evaluate(z,stage,names):
    result=[]; qs=[]
    for scope in ['common','expanded']:
        x=z.copy() if scope=='expanded' else z[z.sector_incumbent.notna()].copy()
        for treatment in ['raw','capped']:
            xx=x.copy()
            if treatment=='capped':xx.future_xirr=xx.future_xirr.clip(-1,1)
            q=p.metrics(xx,[base.ANCHOR]+names,top_ns=(1,3,5));q['scope']=scope;q['treatment']=treatment;qs.append(q)
            a=q.groupby(['model','top_n','sector','profile'])[p.METRICS].mean().groupby(['model','top_n']).mean()
            for name in names:
                for k in [1,3,5]:
                    d=a.loc[(name,k)]-a.loc[(base.ANCHOR,k)];d.shortfall=-d.shortfall
                    result.append(dict(stage=stage,scope=scope,treatment=treatment,model=name,top_n=k,utility=sum(d[c]*w/.01 for c,w in preference.WEIGHTS.items()),ranking_utility=(d.rank_ic+d.ndcg)/.02,equal_utility=sum(d[c] for c in preference.WEIGHTS)/.05,**d.to_dict()))
            print('EVALUATE',stage,scope,treatment,flush=True)
    pd.concat(qs).to_csv(OUT/f'queries_{stage}.csv.gz',index=False)
    result=pd.DataFrame(result);result.to_csv(OUT/f'deltas_{stage}.csv',index=False);return result

def main():
    protocol();ref=base.load_reference();f=pd.read_pickle(p.OUT/'prepared.pkl.gz',compression='gzip')
    cols=['observations','history_days','momentum12_1'];ref=ref.merge(f[p.KEYS+cols],on=p.KEYS,validate='one_to_one');del f
    x=signals(attach(ref));x[p.KEYS+list(CONFIGS)].to_csv(OUT/'historical_adjustments.csv.gz',index=False)
    dev=evaluate(x[x.decision_date.lt('2024-01-01')],'development',list(CONFIGS))
    chosen=dev[dev.scope.eq('expanded')&dev.treatment.eq('capped')&dev.top_n.eq(3)].sort_values(['utility','model'],ascending=[False,True]).iloc[0]
    (OUT/'development_lock.json').write_text(json.dumps(chosen.to_dict(),indent=2))
    recent=evaluate(x[x.decision_date.ge('2024-01-01')],'recent',[chosen.model]);r=recent[recent.scope.eq('expanded')&recent.treatment.eq('capped')&recent.top_n.eq(3)].iloc[0]
    accepted=bool(chosen.utility>0 and r.utility>0 and r.ranking_utility>0 and r.equal_utility>0 and r.drawdown>=-.01 and r.achievement>=-.01)
    current=pd.read_csv(p.OUT/'current_all_stock_rankings.csv');current[base.ANCHOR]=current.rebuilt_score
    current=signals(attach(current,True)); assert len(current)==4436 and current['isin'].is_unique
    for n in [base.ANCHOR]+list(CONFIGS):assert np.isfinite(current[n]).all()
    fallback=current.evidence_fraction.le(0)
    np.testing.assert_array_equal(current.loc[fallback,chosen.model],current.loc[fallback,base.ANCHOR])
    current['patch_sector_rank']=current[chosen.model].groupby(current.sector).rank(method='min',ascending=False)
    current['original_sector_rank']=current[base.ANCHOR].groupby(current.sector).rank(method='min',ascending=False)
    current.to_csv(OUT/'current_all_4436_audit.csv',index=False)
    current[current.patch_sector_rank.le(3)].to_csv(OUT/'sector_top3.csv',index=False)
    decision=dict(selected=chosen.model,accept_research_patch=accepted,development=chosen.to_dict(),recent=r.to_dict(),current_coverage=4436,unchanged_missing_evidence=int(fallback.sum()),fresh_validation=False,website_changed=False)
    (OUT/'decision.json').write_text(json.dumps(decision,indent=2)); print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':main()
