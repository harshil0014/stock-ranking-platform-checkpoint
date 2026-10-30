"""Small residual pairs to test complementary learned rankers, post-exposure."""
import itertools,json
import pandas as pd
from full_coverage_challenger_20261008 import ROOT,aggregate,METRICS
from fast_sector_evaluation_20261008 import evaluate
OUT=ROOT/'experiments/full-coverage-open-models-20261008'

def run():
    x=pd.read_pickle(OUT/'predictions.pkl.gz',compression='gzip')
    sources=[f'{f}_{t}' for f in ['catboost','xgboost','extra_trees','ridge'] for t in ['return','balanced','defensive']]
    x=x[['isin','decision_date','sector','period','future_xirr','future_drawdown','future_shortfall','sector_incumbent','frozen_challenger']+sources].copy()
    choices=[{'name':f'pair__{a}__{b}__{w}','sources':[a,b],'weight':w} for (a,b),w in itertools.product(itertools.combinations(sources,2),[.05,.1,.2])]
    protocol={'candidate_count':len(choices),'formula':'(1-w)*frozen_challenger + w*(rankerA+rankerB)/2','reason':'Test complementary return/risk signals using small residual contributions. All pair choices retained, no cherry-picked pairs.','adaptive':True,'fresh_validation':False,'candidates':choices}
    (OUT/'pair_protocol.json').write_text(json.dumps(protocol,indent=2))
    summaries=[];complete=set()
    if (OUT/'pair_summary.csv').exists():
        previous=pd.read_csv(OUT/'pair_summary.csv',on_bad_lines='skip').dropna()
        valid=previous.groupby(['model','return_treatment']).filter(lambda g:len(g)==12)
        summaries.append(valid)
        complete=set(zip(valid.model,valid.return_treatment))
    for bounded in [False,True]:
        z=x.copy()
        if bounded:z.future_xirr=z.future_xirr.clip(-1,1)
        for start in range(0,len(choices),12):
            batch=[c for c in choices[start:start+12] if (c['name'],'capped' if bounded else 'raw') not in complete]
            if not batch:continue
            for c in batch:z[c['name']]=(1-c['weight'])*z.frozen_challenger+c['weight']*z[c['sources']].mean(axis=1)
            a=aggregate(evaluate(z,['frozen_challenger']+[c['name'] for c in batch],(1,3,5))).reset_index();a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
            z=z.drop(columns=[c['name'] for c in batch])
            pd.concat(summaries).drop_duplicates(['model','period','scope','top_n','return_treatment']).to_csv(OUT/'pair_summary.csv',index=False)
            print('PAIRS',bounded,start+len(batch),flush=True)
    a=pd.concat(summaries).drop_duplicates(['model','period','scope','top_n','return_treatment']).set_index(['model','period','scope','top_n','return_treatment'])[METRICS];trials=[]
    for c in choices:
        values=[]
        for ref in ['sector_incumbent','frozen_challenger']:
            d=a.loc[c['name']]-a.loc[ref];d.shortfall=-d.shortfall;values.extend(d.to_numpy().ravel())
        trials.append(dict(model=c['name'],strict_gate=all(v>=-1e-12 for v in values) and any(v>1e-12 for v in values),regressing_cells=sum(v < -1e-12 for v in values),total_cells=len(values),worst_delta=min(values),mean_delta=sum(values)/len(values)))
    t=pd.DataFrame(trials).sort_values(['strict_gate','regressing_cells','mean_delta'],ascending=[False,True,False]);t.to_csv(OUT/'pair_trials.csv',index=False);print(t.head(10).to_string(index=False),flush=True)

if __name__=='__main__':run()
