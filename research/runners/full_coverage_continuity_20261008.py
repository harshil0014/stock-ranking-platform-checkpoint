"""Fourth round: soft continuity adjustment instead of binary exclusion."""
import itertools,json
import numpy as np
import pandas as pd
from full_coverage_challenger_20261008 import OUT,ROOT,write,evaluate,aggregate,METRICS,utility


def continuity(frame,activity):
    x=frame.merge(activity[['isin','decision_date','volume_active_fraction','observations_1y']],on=['isin','decision_date'],how='left',validate='many_to_one')
    # Observed continuity only; not contribution-size-dependent or a hard veto.
    rel=x.volume_active_fraction.clip(0,1).fillna(.5)*x.observations_1y.div(120).clip(0,1).fillna(.5)
    return x,rel


def run():
    choices=[{'source':s,'alpha':a,'continuity_weight':w,'name':f'{s}_blend{a}_continuity{w}'}
        for s,a,w in itertools.product(['rank_xendcg_return_15','rank_xendcg_balanced_15'],[.1,.25,.5],[.05,.1,.2,.3])]
    write('round4_protocol.json',{'candidates':choices,'reason':'Low observed volatility can reward inactive prices; add soft continuity cost without rejecting any stock.',
        'continuity':'volume_active_fraction * min(observations_1y/120,1); missing factors=.5',
        'score':'(1-alpha)*champion_or_high_strength + alpha*ranker - continuity_weight*(1-continuity)',
        'selection':'Same clipped-return gates as round2/3, previously exposed 2020-2025; no independent-validation claim.'})
    x=pd.read_pickle(OUT/'predictions.pkl.gz',compression='gzip')
    activity=pd.read_csv(ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz')
    x,rel=continuity(x,activity);x.future_xirr=x.future_xirr.clip(-1,1)
    anchor=x.sector_incumbent.groupby([x.decision_date,x.sector]).rank(pct=True).fillna(x.high_strength)
    trials=[];summaries=[]
    for start in range(0,len(choices),6):
        batch=choices[start:start+6]
        for c in batch:x[c['name']]=(1-c['alpha'])*anchor+c['alpha']*x[c['source']]-c['continuity_weight']*(1-rel)
        q=evaluate(x,[c['name'] for c in batch]);a=aggregate(q).droplevel('top_n');ref=a.loc['sector_incumbent'];summaries.append(a.reset_index())
        for c in batch:
            d=a.loc[c['name']]-ref;u=utility(d)
            strict=bool(d[['xirr','drawdown','achievement','ndcg']].ge(-1e-12).all().all() and d.shortfall.le(1e-12).all() and u.mean()>1e-12)
            gate=bool(u.ge(-1e-12).all() and d.xirr.ge(-.005).all() and d.drawdown.ge(-.005).all()
                and d.achievement.ge(-.01).all() and d.shortfall.le(.0025).all() and d.ndcg.ge(-.005).all())
            trials.append({**c,'strict_gate':strict,'secondary_gate':gate,'utility':float(u.mean()),
                **{f'{p}_{s}_{m}_delta':float(d.loc[(p,s),m]) for p,s in d.index for m in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'round4_trials.csv',index=False)
        pd.concat(summaries).drop_duplicates(['model','period','scope']).to_csv(OUT/'round4_bounded_summary.csv',index=False)
        print('CONTINUITY',len(trials),'strict',sum(t['strict_gate'] for t in trials),'secondary',sum(t['secondary_gate'] for t in trials),flush=True)
    strict=[t for t in trials if t['strict_gate']];passing=strict or [t for t in trials if t['secondary_gate']]
    chosen=sorted(passing or trials,key=lambda t:(-t['utility'],t['alpha'],t['name']))[0]
    write('round4_selection.json',{'selected':chosen,'strict_passes':len(strict),'secondary_passes':sum(t['secondary_gate'] for t in trials),
        'status':'STRICT_RETROSPECTIVE_GATE' if strict else 'TOLERANCE_RETROSPECTIVE_GATE' if passing else 'RESEARCH_ONLY_NO_GATE',
        'fresh_validation':False,'selected_after_exposure':True})


if __name__=='__main__':run()
