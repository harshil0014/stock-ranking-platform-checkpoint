"""Delayed-feedback sector expert aggregation; all outcomes must mature first."""
import json,itertools,gc
import numpy as np
import pandas as pd
from full_coverage_challenger_20261008 import ROOT,KEYS
from sector_championship_20261005 import metrics,METRICS
NEW=ROOT/'experiments/full-coverage-open-models-20261008'
PRO=ROOT/'experiments/profile-aware-sector-20261008'
OUT=ROOT/'experiments/sector-expert-router-20261008'
EXPERTS=['new_expert','prior_expert','v17_expert','professor_expert','balanced_expert','defensive_expert']
CONFIGS=[dict(name=f'router_y{years}_s{shrink}_t{temp}_w{weight}',years=years,shrink=shrink,temp=temp,weight=weight)
    for years,shrink,temp,weight in itertools.product([2,5],[8,24],[.03,.1],[.1,.25])]

def weights(past,sector,c):
    if past.empty:return np.array([1.,0,0,0,0,0])
    # Equal sector means form the prior, not a stock-count weighted global return.
    global_mean=past.groupby('sector')[EXPERTS].mean().mean().to_numpy()
    local=past[past.sector.eq(sector)]
    local_sum=local[EXPERTS].sum().to_numpy()
    merit=(local_sum+c['shrink']*global_mean)/(len(local)+c['shrink'])
    value=np.exp((merit-merit.max())/c['temp']);return value/value.sum()

def run():
    OUT.mkdir(exist_ok=True)
    protocol={'configs':CONFIGS,'experts':EXPERTS,'primary':'Within-sector Top3, with Top1/5 and all nine profiles as safeguards.',
      'weight_rule':'Softmax of sector mean completed Top3 utility, shrunk toward equal-sector mean utility. Earlier outcomes only; no same-date or uncompleted feedback.',
      'utility':'capped XIRR + .5 drawdown + .5 achievement - shortfall + .2 NDCG; fit routing on common production universe.',
      'fallback':'No completed feedback: new expert only. Missing individual expert score: new expert sector percentile. Every identity remains scored.',
      'selection_exposure':'Expert families and hyperparameters researched after prior outcomes seen. Endpoint filtering prevents direct future-feedback use but does not establish fresh validation.',
      'source':'https://proceedings.mlr.press/v128/korotin20a.html','relationship':'Inspired by expert aggregation with delayed feedback, not a replication or claimed regret bound.'}
    (OUT/'protocol.json').write_text(json.dumps(protocol,indent=2))
    specs=json.loads((ROOT/'research/reports/all-models-audit-20261004/comparison_sources.json').read_text());spec=next(s for s in specs if s['opponent']=='V17')
    v17=pd.concat([pd.read_csv(ROOT/p,usecols=KEYS+['v17_score']) for p in spec['artifacts']],ignore_index=True)
    endpoints=pd.read_pickle(PRO/'prepared.pkl.gz',compression='gzip')[KEYS+['endpoint']]
    learned=pd.concat([pd.read_csv(PRO/f'predictions_{y}.csv.gz',usecols=KEYS+['profile_balanced_15','profile_defensive_15']) for y in range(2020,2026)],ignore_index=True)
    summaries=[pd.read_csv(OUT/'summary.csv')] if (OUT/'summary.csv').exists() else []
    audits=pd.read_csv(OUT/'feedback_audit.csv').to_dict('records') if (OUT/'feedback_audit.csv').exists() else []
    for path in sorted(NEW.glob('locked_scores_*.csv.gz')):
        profile=path.name.removeprefix('locked_scores_').removesuffix('.csv.gz')
        if summaries and profile in set(pd.concat(summaries).profile):continue
        x=pd.read_csv(path).merge(v17,on=KEYS,validate='one_to_one').merge(endpoints,on=KEYS,validate='one_to_one').merge(learned,on=KEYS,validate='one_to_one')
        group=[x.decision_date,x.sector]
        anchor=x.open_model.groupby(group).rank(pct=True)
        for name,col in zip(EXPERTS,['open_model','frozen_challenger','v17_score','professor_whole_share_score','profile_balanced_15','profile_defensive_15']):
            x[name]=x[col].groupby(group).rank(pct=True).fillna(anchor)
        z=x[x.sector_incumbent.notna()].copy();z.future_xirr=z.future_xirr.clip(-1,1)
        q=metrics(z,EXPERTS,top_ns=(3,));q['utility']=q.xirr+.5*q.drawdown+.5*q.achievement-q.shortfall+.2*q.ndcg
        endpoint_by_date=x.groupby('decision_date').endpoint.max()
        history=q.pivot(index=['date','sector'],columns='model',values='utility').reset_index();history['endpoint']=history.date.map(endpoint_by_date)
        history.to_csv(OUT/f'completed_feedback_{profile}.csv.gz',index=False)
        for c in CONFIGS:x[c['name']]=np.nan
        for day,g in x.groupby('decision_date'):
            completed=history[history.endpoint.lt(day)]
            audits.append(dict(profile=profile,decision_date=day,feedback_rows=len(completed),max_feedback_endpoint=completed.endpoint.max() if len(completed) else None))
            assert completed.empty or completed.endpoint.max()<day
            for c in CONFIGS:
                cutoff=(pd.Timestamp(day)-pd.DateOffset(years=c['years'])).date().isoformat()
                past=completed[completed.endpoint.ge(cutoff)]
                if past.empty:
                    x.loc[g.index,c['name']]=g.new_expert
                    continue
                by_sector=past.groupby('sector')[EXPERTS]
                global_mean=by_sector.mean().mean()
                counts=by_sector.size();sums=by_sector.sum()
                merit=(sums+c['shrink']*global_mean).div(counts+c['shrink'],axis=0)
                merit=merit.reindex(g.sector).fillna(global_mean)
                values=merit.to_numpy();soft=np.exp((values-values.max(axis=1,keepdims=True))/c['temp']);soft/=soft.sum(axis=1,keepdims=True)
                x.loc[g.index,c['name']]=(1-c['weight'])*g.new_expert+c['weight']*(g[EXPERTS].to_numpy()*soft).sum(axis=1)
        assert np.isfinite(x[[c['name'] for c in CONFIGS]]).all().all()
        x[KEYS+['sector','period','endpoint','sector_incumbent','open_model','frozen_challenger','future_xirr','future_drawdown','future_shortfall']+[c['name'] for c in CONFIGS]].to_csv(OUT/f'predictions_{profile}.csv.gz',index=False)
        for scope in ['common','expanded']:
            z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
            refs=['open_model','frozen_challenger']+(['sector_incumbent'] if scope=='common' else [])
            for bounded in [False,True]:
                zz=z.copy()
                if bounded:zz.future_xirr=zz.future_xirr.clip(-1,1)
                q=metrics(zz,refs+[c['name'] for c in CONFIGS],top_ns=(1,3,5))
                a=q.groupby(['model','period','profile','top_n','sector'])[METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index();a['scope']=scope;a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
        pd.concat(summaries).to_csv(OUT/'summary.csv',index=False);pd.DataFrame(audits).to_csv(OUT/'feedback_audit.csv',index=False)
        print('ROUTER',profile,flush=True);del x;gc.collect()
    a=pd.concat(summaries).set_index(['model','period','profile','top_n','scope','return_treatment'])[METRICS];trials=[]
    for c in CONFIGS:
        values=[];top3=[]
        for ref in ['open_model','frozen_challenger','sector_incumbent']:
            d=(a.loc[c['name']]-a.loc[ref]).dropna();d.shortfall=-d.shortfall;values.extend(d.to_numpy().ravel());top3.extend(d.xs(3,level='top_n').to_numpy().ravel())
        trials.append(dict(**c,strict_gate=all(v>=-1e-12 for v in values) and any(v>1e-12 for v in values),regressing_cells=sum(v < -1e-12 for v in values),total_cells=len(values),top3_regressing_cells=sum(v < -1e-12 for v in top3),top3_cells=len(top3),mean_delta=float(np.mean(values))))
    t=pd.DataFrame(trials).sort_values(['strict_gate','top3_regressing_cells','regressing_cells'],ascending=[False,True,True]);t.to_csv(OUT/'trials.csv',index=False);print(t.head().to_string(index=False),flush=True)

if __name__=='__main__':run()
