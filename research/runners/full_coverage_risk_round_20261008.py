"""Third disclosed round: offset residual ranker's measured downside regression."""
import itertools,json
import pandas as pd
from full_coverage_challenger_20261008 import OUT,write,evaluate,aggregate,METRICS,utility


def run():
    choices=[{'source':s,'alpha':a,'risk':r,'name':f'{s}_blend{a}_risk{r}'}
        for s,a,r in itertools.product(['rank_xendcg_return_7','rank_xendcg_return_15'],[.05,.1,.15,.2],[.025,.05,.1])]
    write('round3_protocol.json',{'reason':'Return residual improves common returns but worsens expanded drawdown/shortfall; test explicit price-risk counterweight.',
        'candidates':choices,'selection':'Previously exposed 2020-2025, clipped XIRR, same strict and tolerance gates as round2; no new holdout claim.',
        'score':'(1-alpha-risk)*champion_or_high_strength + alpha*purged_ranker + risk*sector_risk_block',
        'risk_missing':'Neutral .5; no stock excluded','next_step':'Keep measured tradeoffs if no strict winner; do not relabel exposed dates as validation.'})
    x=pd.read_pickle(OUT/'predictions.pkl.gz',compression='gzip');x.future_xirr=x.future_xirr.clip(-1,1)
    anchor=x.sector_incumbent.groupby([x.decision_date,x.sector]).rank(pct=True).fillna(x.high_strength)
    risk=x.risk_block.fillna(.5);trials=[];summaries=[]
    for start in range(0,len(choices),6):
        batch=choices[start:start+6]
        for c in batch:x[c['name']]=(1-c['alpha']-c['risk'])*anchor+c['alpha']*x[c['source']]+c['risk']*risk
        q=evaluate(x,[c['name'] for c in batch]);a=aggregate(q).droplevel('top_n');ref=a.loc['sector_incumbent'];summaries.append(a.reset_index())
        for c in batch:
            d=a.loc[c['name']]-ref;u=utility(d)
            strict=bool(d[['xirr','drawdown','achievement','ndcg']].ge(-1e-12).all().all() and d.shortfall.le(1e-12).all() and u.mean()>1e-12)
            gate=bool(u.ge(-1e-12).all() and d.xirr.ge(-.005).all() and d.drawdown.ge(-.005).all()
                and d.achievement.ge(-.01).all() and d.shortfall.le(.0025).all() and d.ndcg.ge(-.005).all())
            trials.append({**c,'strict_gate':strict,'secondary_gate':gate,'utility':float(u.mean()),
                **{f'{p}_{s}_{m}_delta':float(d.loc[(p,s),m]) for p,s in d.index for m in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'round3_trials.csv',index=False)
        pd.concat(summaries).drop_duplicates(['model','period','scope']).to_csv(OUT/'round3_bounded_summary.csv',index=False)
        print('RISK ROUND',len(trials),'strict',sum(t['strict_gate'] for t in trials),'secondary',sum(t['secondary_gate'] for t in trials),flush=True)
    strict=[t for t in trials if t['strict_gate']];passing=strict or [t for t in trials if t['secondary_gate']]
    chosen=sorted(passing or trials,key=lambda t:(-t['utility'],t['alpha'],t['name']))[0]
    write('round3_selection.json',{'selected':chosen,'strict_passes':len(strict),'secondary_passes':sum(t['secondary_gate'] for t in trials),
        'status':'STRICT_RETROSPECTIVE_GATE' if strict else 'TOLERANCE_RETROSPECTIVE_GATE' if passing else 'RESEARCH_ONLY_NO_GATE',
        'fresh_validation':False,'selected_after_exposure':True})


if __name__=='__main__':run()
