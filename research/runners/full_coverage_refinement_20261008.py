"""Disclosed second research round: small residuals with capped-return safeguards.

The recent dates were inspected in round one. They are now development diagnostics,
not an independent holdout. Preserve both rounds and report that selection exposure.
"""
import json
import numpy as np
import pandas as pd
from full_coverage_challenger_20261008 import OUT,write,evaluate,aggregate,METRICS,utility


def run():
    sources=['rank_xendcg_return_7','rank_xendcg_return_15','rank_xendcg_balanced_7','rank_xendcg_balanced_15']
    choices=[{'source':s,'alpha':a,'name':f'{s}_blend{a}'} for s in sources for a in [.01,.025,.05,.075,.1,.15,.25]]
    write('round2_protocol.json',{'candidates':choices,'reason':'Large learned residual lost recent common-stock returns; investigate small residuals and return-tail sensitivity.',
        'selection_exposure':'Both 2020-2023 and previously inspected 2024-2025 now used for refinement; NOT independent validation.',
        'primary_returns':'XIRR clipped to [-100%,+100%] to stop extreme observations dominating model selection; raw sensitivity separately.',
        'strict_gate':'All five Top3 metrics nonworse in both periods and both common/expanded scopes, with a strict improvement.',
        'secondary_gate':'Positive utility every period/scope; each XIRR loss <=0.5pp, drawdown loss <=0.5pp, achievement loss <=1pp, shortfall increase <=0.25pp, NDCG loss <=0.5pp.',
        'tie_break':'Highest mean utility, then smaller alpha; no gate changes after results.'})
    x=pd.read_pickle(OUT/'predictions.pkl.gz',compression='gzip')
    x.future_xirr=x.future_xirr.clip(-1,1)
    anchor=x.sector_incumbent.groupby([x.decision_date,x.sector]).rank(pct=True).fillna(x.high_strength)
    trials=[];summary=[]
    for start in range(0,len(choices),7):
        batch=choices[start:start+7]
        for c in batch:x[c['name']]=(1-c['alpha'])*anchor+c['alpha']*x[c['source']]
        q=evaluate(x,[c['name'] for c in batch]);a=aggregate(q).droplevel('top_n');ref=a.loc['sector_incumbent']
        summary.append(a.reset_index())
        for c in batch:
            d=a.loc[c['name']]-ref;u=utility(d)
            strict=bool(d[['xirr','drawdown','achievement','ndcg']].ge(-1e-12).all().all() and d.shortfall.le(1e-12).all() and u.mean()>1e-12)
            gate=bool(u.ge(-1e-12).all() and d.xirr.ge(-.005).all() and d.drawdown.ge(-.005).all()
                and d.achievement.ge(-.01).all() and d.shortfall.le(.0025).all() and d.ndcg.ge(-.005).all())
            trials.append({**c,'strict_gate':strict,'secondary_gate':gate,'utility':float(u.mean()),
                **{f'{p}_{s}_{m}_delta':float(d.loc[(p,s),m]) for p,s in d.index for m in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'round2_trials.csv',index=False)
        pd.concat(summary).drop_duplicates(['model','period','scope']).to_csv(OUT/'round2_bounded_summary.csv',index=False)
        print('REFINEMENT',len(trials),'strict',sum(t['strict_gate'] for t in trials),'secondary',sum(t['secondary_gate'] for t in trials),flush=True)
    strict=[t for t in trials if t['strict_gate']];passing=strict or [t for t in trials if t['secondary_gate']]
    ranked=sorted(passing or trials,key=lambda t:(-t['utility'],t['alpha'],t['name']))
    write('round2_selection.json',{'selected':ranked[0],'strict_passes':len(strict),'secondary_passes':sum(t['secondary_gate'] for t in trials),
        'status':'STRICT_RETROSPECTIVE_GATE' if strict else 'TOLERANCE_RETROSPECTIVE_GATE' if passing else 'RESEARCH_ONLY_NO_GATE',
        'fresh_validation':False,'selected_after_exposure':True})


if __name__=='__main__':run()
