"""Bounded doubling of the active high/SIP overlays; frozen component replay."""
import json,hashlib
import numpy as np
import pandas as pd
import champion_high_recency_20261017 as h
OUT=h.p.ROOT/'experiments/champion-double-emphasis-20261017'
HIGH=h.p.ROOT/'experiments/champion-high-recency-20261017/historical_adjustments.csv.gz'
SIP=h.p.ROOT/'experiments/champion-sip-profit-20261017/historical_scores.csv.gz'
CONFIGS=['double_both','agree_only','agree_soft','strong_both']

def candidates(x):
    x=x.copy();a=x.high_delta;b=x.sip_delta
    agreement=(a*b>0).astype(float)
    gates={'double_both':1.,'agree_only':agreement,
           'agree_soft':agreement*np.minimum(a.abs(),b.abs())/.005,
           'strong_both':((a.abs()>=.0025)&(b.abs()>=.0025)&(agreement>0)).astype(float)}
    for name,g in gates.items():x[name]=x[h.base.ANCHOR]+g*(a+b)
    return x

def primary(a):return a[a.scope.eq('expanded')&a.treatment.eq('capped')&a.top_n.eq(3)]

def main():
    OUT.mkdir(exist_ok=True)
    protocol={'anchor':'Active dual_w0.01 + sip_risk_confirmed_0.01',
      'candidates':CONFIGS,'formula':'active + gate*(original high adjustment + original SIP adjustment). Each overlay now bounded +/-0.01. gate=1, same-sign agreement, same-sign times weaker absolute signal/.005, or same-sign and both absolute signals >=.0025.',
      'interpretation':'Double both everywhere or condition the extra weight on confirmation. Existing coefficients are never reduced. Conditional versions do not double every stock.',
      'sources':['https://doi.org/10.1016/j.jbankfin.2013.05.025','https://doi.org/10.1016/j.jfineco.2004.10.006'],
      'literature_boundary':'Recency/proximity conditioning and gains-relative-to-acquisition-cost motivate confirmation experiments. These gates and weights are engineering hypotheses, not paper replications.',
      'selection':'Four fixed candidates; 2020-23 capped expanded equal-sector/profile Top3 utility, then lock before 2024-25. Same .4 IC/.25 NDCG/.15 achievement/.1 inverse shortfall/.1 drawdown weights, deltas/.01.',
      'activation':'Positive utility and all six primary aggregate metrics nonworse in both periods. Otherwise keep active website unchanged. No stock-specific tuning.',
      'fresh_validation':False,'source_hashes':{str(p.relative_to(h.p.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [HIGH,SIP]}}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    x=h.base.load_reference()
    a=pd.read_csv(HIGH,usecols=h.p.KEYS+['dual_w0.01'])
    b=pd.read_csv(SIP,usecols=h.p.KEYS+['sip_risk_confirmed_0.01'])
    x=x.merge(a,on=h.p.KEYS,validate='one_to_one').merge(b,on=h.p.KEYS,validate='one_to_one')
    x['high_delta']=x['dual_w0.01']-x[h.base.ANCHOR]
    x['sip_delta']=x['sip_risk_confirmed_0.01']-x['dual_w0.01']
    x[h.base.ANCHOR]=x['sip_risk_confirmed_0.01'];x=candidates(x)
    for c in ['high_delta','sip_delta']:assert x[c].abs().max()<=.005+1e-12
    h.OUT=OUT
    dev=h.evaluate(x[x.decision_date.lt('2024-01-01')],'development',CONFIGS)
    chosen=primary(dev).sort_values(['utility','model'],ascending=[False,True]).iloc[0]
    (OUT/'development_lock.json').write_text(json.dumps(chosen.to_dict(),indent=2));print('LOCKED',chosen.model,flush=True)
    recent=h.evaluate(x[x.decision_date.ge('2024-01-01')],'recent',[chosen.model]);r=primary(recent).iloc[0]
    accepted=bool(chosen.utility>0 and r.utility>0 and chosen[h.p.METRICS].ge(-1e-12).all() and r[h.p.METRICS].ge(-1e-12).all())
    z=pd.read_csv(h.p.ROOT/'experiments/champion-sip-profit-20261017/current_all_4436_audit.csv')
    z['high_delta']=z['dual_w0.01']-z.rebuilt_score;z['sip_delta']=z['sip_risk_confirmed_0.01']-z['dual_w0.01']
    z[h.base.ANCHOR]=z['sip_risk_confirmed_0.01'];z=candidates(z)
    for name in CONFIGS:
        assert np.isfinite(z[name]).all()
        z[name+'_rank']=z[name].groupby(z.sector).rank(method='min',ascending=False)
    z.to_csv(OUT/'current_all_4436_audit.csv',index=False)
    decision={'selected':chosen.model,'accept_research_patch':accepted,'development':chosen.to_dict(),'recent':r.to_dict(),'coverage':len(z),'website_changed':False,'fresh_validation':False}
    (OUT/'decision.json').write_text(json.dumps(decision,indent=2));print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':main()
