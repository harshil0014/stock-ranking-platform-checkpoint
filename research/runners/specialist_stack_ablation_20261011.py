"""Inference component removals with learned mass returned to the reference."""
import json
import numpy as np
import pandas as pd
import sector_specialist_combinations_20261011 as c

OUT=c.OUT/'stack_ablation'
STACK='stack_breadth_balanced_w1.0'
REMOVALS={family:[name for name in c.PURE if name.startswith(family+'_')] for family in c.s.FAMILIES}
REMOVALS.update(tabpfn=[name for name in c.LEGACY if name.startswith('pfn_')],legacy_controls=c.LEGACY,risk_heads=[name for name in c.PURE if name.endswith('_risk')],goal_heads=[name for name in c.PURE if name.endswith('_goal')])
NAMES=['without_'+name for name in REMOVALS]


def main():
    OUT.mkdir(exist_ok=True)
    protocol=dict(stack=STACK,removals=REMOVALS,
        method='Use saved annual learned weights. Set removed coefficients to zero and return their mass to champion percentile; no reoptimization or renormalization. Breadth thresholds and regional shrinkage remain fixed. Use no new future labels for weights. This tests reliance of the fitted architecture, not optimal retrained importance.',
        comparison='All already-exposed periods,9profiles,matched common/expanded populations,raw/capped,Top1/3/5. Reference is the intact stack; positive oriented delta means removal helps. No finalist reselection.',fresh_validation=False)
    path=OUT/'protocol.json'
    if path.exists():
        assert json.loads(path.read_text())==protocol
    else:
        path.write_text(json.dumps(protocol,indent=2),encoding='utf-8')
    x=c.load();pieces=[];replay=[]
    for year in range(2020,2026):
        z=x[x.decision_date.str.startswith(str(year))].copy()
        model=json.loads((c.OUT/f'stack_models_{year}.json').read_text())['balanced']
        saved=pd.read_csv(c.OUT/f'combined_{year}.csv.gz',usecols=c.p.KEYS+[STACK])
        z=z.merge(saved,on=c.p.KEYS,validate='one_to_one')
        if model.get('fallback'):
            original=z.champion_percentile.to_numpy()
            for name in NAMES:
                z[name]=original
        else:
            assert model['max_endpoint']<model['cutoff']
            region=[np.array(weights) for weights in model['regional_weights']]
            high=z.sector_breadth.ge(model['breadth_split'])
            original=np.where(high,c.stack_predict(z,region[1]),c.stack_predict(z,region[0]))
            for label,removed in REMOVALS.items():
                weights=[a.copy() for a in region]
                for j,name in enumerate(model['features']):
                    if name in removed:
                        for a in weights:
                            a[j]=0.
                z['without_'+label]=np.where(high,c.stack_predict(z,weights[1]),c.stack_predict(z,weights[0]))
        error=float(abs(original-z[STACK]).max())
        assert error<1e-12,(year,error)
        replay.append(dict(year=year,original_stack_replay_error=error,rows=len(z)))
        pieces.append(z)
        print('ABLATION SCORED',year,flush=True)
    x=pd.concat(pieces,ignore_index=True);summaries=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        for cap in [False,True]:
            path=OUT/f'queries_{scope}_{cap}.csv.gz'
            if path.exists():
                q=pd.read_csv(path)
            else:
                zz=z.copy()
                if cap:
                    zz.future_xirr=zz.future_xirr.clip(-1,1)
                q=c.p.metrics(zz,[STACK]+NAMES,top_ns=(1,3,5))
                q.to_csv(path,index=False)
            a=q.groupby(['model','period','profile','top_n','sector'])[c.p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
            a['scope']=scope;a['return_treatment']='capped' if cap else 'raw';summaries.append(a)
            print('ABLATION EVALUATED',scope,cap,flush=True)
    summary=pd.concat(summaries);summary.to_csv(OUT/'summary.csv',index=False)
    indexed=summary.set_index(['model','period','profile','top_n','scope','return_treatment'])[c.p.METRICS]
    deltas=[];trials=[]
    for name in NAMES:
        d=indexed.loc[name]-indexed.loc[STACK];d.shortfall=-d.shortfall;d=d.reset_index();d['model']=name;deltas.append(d)
        a=d[c.p.METRICS].to_numpy()
        trials.append(dict(removal=name,improved=int((a>1e-12).sum()),regressed=int((a< -1e-12).sum()),ties=int((abs(a)<=1e-12).sum())))
    pd.concat(deltas).to_csv(OUT/'oriented_removal_deltas.csv',index=False)
    pd.DataFrame(trials).to_csv(OUT/'trials.csv',index=False)
    pd.DataFrame(replay).to_csv(OUT/'original_stack_replay.csv',index=False)
    print(pd.DataFrame(trials).to_string(index=False),flush=True)


if __name__=='__main__':
    main()
