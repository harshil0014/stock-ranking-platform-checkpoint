"""Test explicit trailing SIP profit emphasis against the active recency champion."""
import json,hashlib
import pandas as pd
import numpy as np
import champion_high_recency_20261017 as h
from stock_ranker.sip_profit_signal import adjustments

OUT=h.p.ROOT/'experiments/champion-sip-profit-20261017'
PANEL=h.p.ROOT/'experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz'
EVENTS=h.p.ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv'
CURRENT=h.p.ROOT/'research/runtime/personalized-v17/peak_current.csv.gz'
PROFILES=h.p.ROOT/'research/protocols/personalized_official_action_tournament_v1.json'
CONFIGS={f'sip_{kind}_{w}':(kind,w) for kind in ['plain','invested','risk_confirmed'] for w in [.01,.025,.05,.1,.2]}
FIELDS=['professor_whole_share_score','unused_cash_excluded_by_professor','amount_contributed']

def attach_profit(x,current=False):
    source=CURRENT if current else PANEL
    s=pd.read_csv(source,usecols=h.p.KEYS+FIELDS)
    x=x.merge(s,on=h.p.KEYS,how='left',validate='one_to_one')
    x['sip_invested_fraction']=1-x.unused_cash_excluded_by_professor/x.amount_contributed.where(x.amount_contributed.gt(0))
    metadata=json.loads(PROFILES.read_text())['profiles']
    x['sip_action_blocked']=False
    dates=pd.to_datetime(x.decision_date)
    starts=dates.copy()
    for name,p in metadata.items():
        mask=x.profile_name.eq(name);starts.loc[mask]=dates.loc[mask]-pd.DateOffset(months=p['lookback_months'])
    e=pd.read_csv(EVENTS);e=e[e.status.ne('ALIGNED_MULTIPLIER')]
    for isin,g in e.groupby('isin'):
        ids=x.index[x['isin'].eq(isin)]
        for day in pd.to_datetime(g.event_date):
            x.loc[ids,'sip_action_blocked'] |= starts.loc[ids].lt(day)&dates.loc[ids].ge(day)
    return x

def signals(x):
    x=x.copy()
    for kind,s in adjustments(x).items():
        x['signal_'+kind]=s
    for n,(kind,w) in CONFIGS.items():x[n]=x[h.base.ANCHOR]+w*x['signal_'+kind]
    return x

def primary(a):return a[a.scope.eq('expanded')&a.treatment.eq('capped')&a.top_n.eq(3)]

def main():
    OUT.mkdir(exist_ok=True)
    protocol={'anchor':'Active dual_w0.01, not original champion. Recency adjustment and all original component coefficients stay fixed.',
      'configs':CONFIGS,'formula':'active_champion + w * centered sector SIP-profit percentile; optional reliability multiplier. w is an additive coefficient, not a normalized total weight.',
      'profit':'Stored trailing professor-mode gain / actual amount spent, excluding unused cash. Uses project schedule and corporate-action treatment; not exact Google Sheets price/date replication.',
      'reliability':'invested: multiply adjustment by invested budget fraction. risk_confirmed: additionally multiply by inverse downside percentile. Never changes sign of SIP preference.',
      'guard':'No usable price evidence, missing profit, profit below -100%, unclassified, inactive volume, stale positive volume, fewer than five peers, or unresolved provider/official event in trailing lookback => zero SIP adjustment.',
      'selection':'15 fixed configs. Select maximum 2020-23 equal-sector/profile expanded capped Top3 utility; lock before 2024-25. Same utility weights .4 rankIC .25 NDCG .15 achievement .1 inverse shortfall .1 drawdown.',
      'activation':'Positive weighted utility AND all six primary aggregate metrics nonworse in BOTH periods (tolerance 1e-12), full finite current coverage. Otherwise retain active champion. All profiles/raw/common/Top1/5 diagnostics reported.',
      'fresh_validation':False,'source_hashes':{str(p.relative_to(h.p.ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [PANEL,EVENTS,CURRENT,PROFILES]},
      'sources':['https://www.sciencedirect.com/science/article/pii/S0304405X05000747','https://www.finra.org/sites/default/files/2020-06/Regulatory-Notice-20-21.pdf'],
      'limits':'Previously exposed dates, current-survivor universe and retrospective sectors. Gross SIP outcomes, incomplete corporate-action certification. Hypothesis adaptation, not a paper replication.'}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2));print('PROTOCOL LOCKED',flush=True)
    ref=h.base.load_reference();f=pd.read_pickle(h.p.OUT/'prepared.pkl.gz',compression='gzip')
    ref=ref.merge(f[h.p.KEYS+['observations','history_days','momentum12_1','downside252']],on=h.p.KEYS,validate='one_to_one');del f
    x=h.signals(h.attach(ref));x['original_champion']=x[h.base.ANCHOR];x[h.base.ANCHOR]=x['dual_w0.01']
    x=signals(attach_profit(x));print('FEATURES',len(x),'nonzero',int(x.signal_plain.ne(0).sum()),flush=True)
    x[h.p.KEYS+[h.base.ANCHOR]+list(CONFIGS)].to_csv(OUT/'historical_scores.csv.gz',index=False)
    x.groupby(['profile_name','decision_date']).agg(rows=('isin','size'),available_profit=('professor_whole_share_score','count'),action_blocked=('sip_action_blocked','sum'),nonzero_signal=('signal_plain',lambda s:int(s.ne(0).sum()))).to_csv(OUT/'coverage.csv')
    h.OUT=OUT
    dev=h.evaluate(x[x.decision_date.lt('2024-01-01')],'development',list(CONFIGS))
    chosen=primary(dev).sort_values(['utility','model'],ascending=[False,True]).iloc[0]
    (OUT/'development_lock.json').write_text(json.dumps(chosen.to_dict(),indent=2));print('LOCKED',chosen.model,chosen.utility,flush=True)
    recent=h.evaluate(x[x.decision_date.ge('2024-01-01')],'recent',[chosen.model]);r=primary(recent).iloc[0]
    accepted=bool(chosen.utility>0 and r.utility>0 and chosen[h.p.METRICS].ge(-1e-12).all() and r[h.p.METRICS].ge(-1e-12).all())
    current=pd.read_csv(h.p.ROOT/'experiments/champion-high-recency-20261017/current_all_4436_audit.csv')
    current[h.base.ANCHOR]=current['dual_w0.01'];current=signals(attach_profit(current,True))
    assert len(current)==4436 and current['isin'].is_unique
    for n,(kind,w) in CONFIGS.items():
        assert np.isfinite(current[n]).all()
        assert (current[n]-current[h.base.ANCHOR]).abs().le(w/2+1e-12).all()
        np.testing.assert_array_equal(current.loc[current.evidence_fraction.le(0),n],current.loc[current.evidence_fraction.le(0),h.base.ANCHOR])
    current['candidate_sector_rank']=current[chosen.model].groupby(current.sector).rank(method='min',ascending=False)
    current.to_csv(OUT/'current_all_4436_audit.csv',index=False)
    replay=signals(pd.read_csv(OUT/'current_all_4436_audit.csv'))
    np.testing.assert_allclose(current[chosen.model],replay[chosen.model],atol=1e-12,rtol=0)
    decision={'selected':chosen.model,'accept_research_patch':accepted,'development':chosen.to_dict(),'recent':r.to_dict(),
      'current_coverage':len(current),'current_nonzero_sip_adjustment':int(current['signal_'+CONFIGS[chosen.model][0]].ne(0).sum()),'website_changed':False,'fresh_validation':False}
    (OUT/'decision.json').write_text(json.dumps(decision,indent=2));print(json.dumps(decision,indent=2),flush=True)

if __name__=='__main__':main()
