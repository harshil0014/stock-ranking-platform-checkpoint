"""Final ensemble round: return/defensive rankers have complementary regressions."""
import itertools
import pandas as pd
from full_coverage_challenger_20261008 import OUT,ROOT,write,evaluate,aggregate,METRICS,utility
from full_coverage_continuity_20261008 import continuity


def run():
    choices=[{'balanced':b,'returns':r,'continuity_weight':c,'name':f'dual_b{b}_r{r}_c{c}'}
        for b,r,c in itertools.product([.15,.25,.35],[.05,.1,.15],[.2,.3,.4])]
    write('round5_protocol.json',{'candidates':choices,'reason':'Balanced ranker lowers drawdown but sometimes misses target attainment; return ranker has complementary strengths. Test convex blend with continuity.',
        'formula':'(1-b-r)*anchor + b*balanced15 + r*return15 - c*(1-continuity)',
        'selection':'Same clipped-return gates; all periods exposed; no independent-validation claim.',
        'stopping':'Complete this prespecified ensemble round, select best passing strict/tolerance candidate across rounds 2-5. Retain challenger only if diagnostics regress.'})
    x=pd.read_pickle(OUT/'predictions.pkl.gz',compression='gzip')
    x,rel=continuity(x,pd.read_csv(ROOT/'experiments/v17-peak-activity-20261004/dated_features.csv.gz'))
    x.future_xirr=x.future_xirr.clip(-1,1)
    anchor=x.sector_incumbent.groupby([x.decision_date,x.sector]).rank(pct=True).fillna(x.high_strength)
    trials=[];summaries=[]
    for start in range(0,len(choices),6):
        batch=choices[start:start+6]
        for c in batch:x[c['name']]=(1-c['balanced']-c['returns'])*anchor+c['balanced']*x.rank_xendcg_balanced_15+c['returns']*x.rank_xendcg_return_15-c['continuity_weight']*(1-rel)
        q=evaluate(x,[c['name'] for c in batch]);a=aggregate(q).droplevel('top_n');ref=a.loc['sector_incumbent'];summaries.append(a.reset_index())
        for c in batch:
            d=a.loc[c['name']]-ref;u=utility(d)
            strict=bool(d[['xirr','drawdown','achievement','ndcg']].ge(-1e-12).all().all() and d.shortfall.le(1e-12).all() and u.mean()>1e-12)
            gate=bool(u.ge(-1e-12).all() and d.xirr.ge(-.005).all() and d.drawdown.ge(-.005).all()
                and d.achievement.ge(-.01).all() and d.shortfall.le(.0025).all() and d.ndcg.ge(-.005).all())
            trials.append({**c,'strict_gate':strict,'secondary_gate':gate,'utility':float(u.mean()),
                **{f'{p}_{s}_{m}_delta':float(d.loc[(p,s),m]) for p,s in d.index for m in METRICS}})
        pd.DataFrame(trials).to_csv(OUT/'round5_trials.csv',index=False)
        pd.concat(summaries).drop_duplicates(['model','period','scope']).to_csv(OUT/'round5_bounded_summary.csv',index=False)
        print('DUAL',len(trials),'strict',sum(t['strict_gate'] for t in trials),'secondary',sum(t['secondary_gate'] for t in trials),flush=True)
    strict=[t for t in trials if t['strict_gate']];passing=strict or [t for t in trials if t['secondary_gate']]
    chosen=sorted(passing or trials,key=lambda t:(-t['utility'],t['name']))[0]
    write('round5_selection.json',{'selected':chosen,'strict_passes':len(strict),'secondary_passes':sum(t['secondary_gate'] for t in trials),
        'status':'STRICT_RETROSPECTIVE_GATE' if strict else 'TOLERANCE_RETROSPECTIVE_GATE' if passing else 'RESEARCH_ONLY_NO_GATE',
        'fresh_validation':False,'selected_after_exposure':True})


if __name__=='__main__':run()
