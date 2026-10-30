"""Fixed high-recency patch plus bounded continuity/risk complements."""
import json
import numpy as np
import pandas as pd
import champion_high_recency_20261017 as h

OUT=h.p.ROOT/'experiments/champion-recency-complements-20261017'
FIELDS=['observations','history_days','momentum12_1','efficiency126','trend_r2','largest_jump_share','downside252','volatility252','drawdown252']
CONFIGS={f'{kind}_{w}':(kind,w) for kind in ['continuity','risk','combined'] for w in [.001,.003]}

def signals(x):
    z=h.signals(x)
    group=[z.decision_date,z.profile_name,z.sector]
    eligible=z.evidence_fraction.gt(0)&z.observations.ge(252)&z.history_days.ge(365)&z.volume_active_fraction.ge(.8)&z.last_positive_volume_lag_days.between(0,14)&z.sector.ne('Unclassified')
    def rank(c,ascending=True):
        v=z[c].where(eligible & np.isfinite(z[c]))
        return v.groupby(group).rank(pct=True,ascending=ascending)
    # Continuity proxy, not the paper's exact information-discreteness estimator.
    smooth=(rank('efficiency126')+rank('trend_r2')+rank('largest_jump_share',False))/3
    risk=(rank('downside252',False)+rank('volatility252',False)+rank('drawdown252'))/3
    for kind,v in [('continuity',smooth),('risk',risk),('combined',(smooth+risk)/2)]:
        n=v.groupby(group).transform('count')
        z['complement_'+kind]=(v-.5).where(eligible & n.ge(5),0).fillna(0)
    for name,(kind,w) in CONFIGS.items():
        z[name]=z['dual_w0.01']+w*z['complement_'+kind]
    return z

def main():
    OUT.mkdir(exist_ok=True)
    protocol={'fixed_patch':'C + .01*(.60 dual recency + .25 dual proximity + .15 momentum - .5); unchanged from prior round',
      'configs':CONFIGS,'complements':'Within date/profile/sector percentiles. Continuity: equal efficiency126, trend_r2, inverse largest_jump_share. Risk: equal inverse downside252, inverse volatility252, drawdown252. Combined: equal continuity/risk.',
      'weight_constraint':'Added total weight <=.003, less than fixed recency coefficient .006; no normalization or dilution of recency.',
      'sources':['https://doi.org/10.1093/rfs/hhu003','https://doi.org/10.1016/j.jfineco.2015.12.002'],
      'adaptation':'Continuity and stock-level risk proxies motivated by literature; not exact paper replication or portfolio volatility targeting.',
      'selection':'Same development 2020-23 equal-sector/profile capped Top3 utility as previous round; six fixed candidates, lock one before 2024-25. Previously exposed historical dates.',
      'acceptance':'Same tradeoff rule as previous round; positive development/recent weighted utility, positive recent ranking-only and equal-five utility, no >1pp drawdown/achievement loss.',
      'fresh_validation':False,'website_changed':False}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    ref=h.base.load_reference()
    f=pd.read_pickle(h.p.OUT/'prepared.pkl.gz',compression='gzip')
    ref=ref.merge(f[h.p.KEYS+FIELDS],on=h.p.KEYS,validate='one_to_one');del f
    x=signals(h.attach(ref))
    x[h.p.KEYS+list(CONFIGS)].to_csv(OUT/'historical_adjustments.csv.gz',index=False)
    h.OUT=OUT
    dev=h.evaluate(x[x.decision_date.lt('2024-01-01')],'development',list(CONFIGS))
    primary=lambda a:a[a.scope.eq('expanded')&a.treatment.eq('capped')&a.top_n.eq(3)]
    chosen=primary(dev).sort_values(['utility','model'],ascending=[False,True]).iloc[0]
    (OUT/'development_lock.json').write_text(json.dumps(chosen.to_dict(),indent=2))
    recent=h.evaluate(x[x.decision_date.ge('2024-01-01')],'recent',[chosen.model,'dual_w0.01'])
    r=primary(recent).set_index('model').loc[chosen.model]
    accepted=bool(chosen.utility>0 and r.utility>0 and r.ranking_utility>0 and r.equal_utility>0 and r.drawdown>=-.01 and r.achievement>=-.01)
    current=pd.read_csv(h.p.OUT/'current_all_stock_rankings.csv');current[h.base.ANCHOR]=current.rebuilt_score
    current=signals(h.attach(current,True))
    assert len(current)==4436 and current['isin'].is_unique
    for n,(kind,w) in CONFIGS.items():
        assert np.isfinite(current[n]).all()
        assert (current[n]-current['dual_w0.01']).abs().max()<=w/2+1e-12
        mask=current.evidence_fraction.le(0)
        np.testing.assert_array_equal(current.loc[mask,n],current.loc[mask,h.base.ANCHOR])
    current['patch_sector_rank']=current[chosen.model].groupby(current.sector).rank(method='min',ascending=False)
    current.to_csv(OUT/'current_all_4436_audit.csv',index=False)
    replay=signals(pd.read_csv(OUT/'current_all_4436_audit.csv'))
    for n in CONFIGS:np.testing.assert_allclose(current[n],replay[n],atol=1e-12,rtol=0)
    decision={'selected':chosen.model,'accept_research_patch':accepted,'development':chosen.to_dict(),'recent':r.to_dict(),'coverage':len(current),'fresh_validation':False,'website_changed':False}
    (OUT/'decision.json').write_text(json.dumps(decision,indent=2))
    print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':main()
