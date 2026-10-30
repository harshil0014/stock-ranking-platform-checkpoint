"""Increase only high-age influence; keep active SIP overlay frozen."""
import json,hashlib
import numpy as np
import pandas as pd
import champion_high_recency_20261017 as h
import champion_double_emphasis_20261017 as previous
OUT=h.p.ROOT/'experiments/champion-age-only-20261017'
CONFIGS={f'{kind}_{w}':(kind,w) for kind in ['dual_age','rolling_age','recorded_age','near_high_age'] for w in [.001,.002,.004,.008]}

def signals(x):
    x=x.copy();group=[x[c] for c in ['decision_date','profile_name','sector']]
    valid=x.evidence_fraction.gt(0)&x.observations.ge(252)&x.history_days.ge(365)&x.volume_active_fraction.ge(.8)&x.last_positive_volume_lag_days.between(0,14)&x.sector.ne('Unclassified')
    def age(col):
        v=x[col].where(valid & np.isfinite(x[col]) & x[col].ge(0))
        q=v.groupby(group).rank(pct=True,ascending=False)-.5
        return q.where(v.groupby(group).transform('count').ge(5))
    rolling=age('days_since_52w_closing_high');recorded=age('days_since_recorded_high');dual=(rolling+recorded)/2
    # Proximity confirmation: full increment at high, linearly zero at 20% below.
    gate=(1+x.distance_from_52w_high/.2).clip(0,1).fillna(0)
    parts={'dual_age':dual,'rolling_age':rolling,'recorded_age':recorded,'near_high_age':rolling*gate}
    for kind,s in parts.items():x['age_signal_'+kind]=s.where(valid,0).fillna(0)
    for name,(kind,w) in CONFIGS.items():x[name]=x[h.base.ANCHOR]+w*x['age_signal_'+kind]
    return x

def main():
    OUT.mkdir(exist_ok=True)
    sources=[previous.SIP,h.SOURCES[0],h.SOURCES[1],h.p.OUT/'prepared.pkl.gz']
    protocol={'anchor':'Active recency plus risk-confirmed SIP champion. Only add inverse high-age percentile; SIP, proximity, momentum and learned components unchanged.',
      'configs':CONFIGS,'strength':'Extra age coefficient .001/.002/.004/.008 gives maximum extra +/- .0005/.001/.002/.004. Existing dual age coefficient .006 retained. Dual-age additions imply total .007/.008/.010/.014.',
      'signals':'Inverse within-date/profile/sector age percentile for rolling52week, recorded available-history high, equal dual, or rolling age times proximity gate max(0,min(1,1+52w_gap/.2)). Guards: >=252obs,365days,80%active volume,positive volume <=14days,usable evidence,known sector,>=5 valid peers.',
      'selection':'16 fixed candidates. 2020-23 expanded capped equal-sector/profile Top3 utility, lock one before 2024-25. Same utility weights as prior experiments.',
      'activation':'Positive utility, positive ranking-only and equal-five sensitivities in BOTH periods; XIRR/drawdown/achievement/directional-shortfall losses each <=0.001 (0.1pp). Allows small individual tradeoffs. Otherwise retain current champion.',
      'fresh_validation':False,'sources':['https://doi.org/10.1016/j.jbankfin.2013.05.025','https://doi.org/10.1111/j.1540-6261.2004.00695.x'],
      'limits':'Literature supports testing rolling-high recency/proximity, not these coefficients or a lifetime ATH-age penalty. Recorded high is limited to available history. Previously exposed historical dates, gross returns, retrospective sectors and survivor bias remain.',
      'source_hashes':{str(p.relative_to(h.p.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2));print('PROTOCOL',len(CONFIGS),flush=True)
    x=h.base.load_reference();a=pd.read_csv(previous.SIP,usecols=h.p.KEYS+['sip_risk_confirmed_0.01'])
    x=x.merge(a,on=h.p.KEYS,validate='one_to_one');x[h.base.ANCHOR]=x['sip_risk_confirmed_0.01']
    f=pd.read_pickle(h.p.OUT/'prepared.pkl.gz',compression='gzip')
    x=x.merge(f[h.p.KEYS+['observations','history_days']],on=h.p.KEYS,validate='one_to_one');del f
    x=signals(h.attach(x));h.OUT=OUT
    dev=h.evaluate(x[x.decision_date.lt('2024-01-01')],'development',list(CONFIGS))
    chosen=previous.primary(dev).sort_values(['utility','model'],ascending=[False,True]).iloc[0]
    (OUT/'development_lock.json').write_text(json.dumps(chosen.to_dict(),indent=2));print('LOCKED',chosen.model,chosen.utility,flush=True)
    recent=h.evaluate(x[x.decision_date.ge('2024-01-01')],'recent',[chosen.model]);r=previous.primary(recent).iloc[0]
    def acceptable(v):return v.utility>0 and v.ranking_utility>0 and v.equal_utility>0 and v[['xirr','drawdown','achievement','shortfall']].ge(-.001).all()
    z=pd.read_csv(h.p.ROOT/'experiments/champion-sip-profit-20261017/current_all_4436_audit.csv');z[h.base.ANCHOR]=z['sip_risk_confirmed_0.01'];z=signals(z)
    for name,(kind,w) in CONFIGS.items():
        assert np.isfinite(z[name]).all() and (z[name]-z[h.base.ANCHOR]).abs().le(w/2+1e-12).all()
        z[name+'_rank']=z[name].groupby(z.sector).rank(method='min',ascending=False)
    z.to_csv(OUT/'current_all_4436_audit.csv',index=False)
    replay=signals(pd.read_csv(OUT/'current_all_4436_audit.csv'))
    for name in CONFIGS:np.testing.assert_allclose(z[name],replay[name],atol=1e-12,rtol=0)
    decision=dict(selected=chosen.model,accept_research_patch=bool(acceptable(chosen) and acceptable(r)),development=chosen.to_dict(),recent=r.to_dict(),coverage=len(z),website_changed=False,fresh_validation=False)
    (OUT/'decision.json').write_text(json.dumps(decision,indent=2));print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':main()
