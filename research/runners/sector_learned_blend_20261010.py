"""Replace champion's fixed blend using completed out-of-time predictions only."""
import json, hashlib, subprocess, sys
import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
import sector_price_rebuild_20261010 as p

BASE=p.OUT
OUT=p.ROOT/'experiments/sector-learned-blend-20261010'
ANCHOR='current_champion'
FEATURES=['guarded_previous','rank_xendcg_balanced']
INNER=['open_model','profile_defensive_15','rank_xendcg_balanced']
CONFIGS=[dict(name=f'nnls_{scope}_{target}',scope=scope,target=target,kind='nnls') for scope in ['outer','nested'] for target in ['return','balanced']]+[dict(name=f'tabpfn_v2_context{n}',kind='tabpfn',target='balanced',context=n) for n in [256,768]]

def load():
    x=pd.concat([pd.read_csv(BASE/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    old=pd.concat([pd.read_csv(p.OLD/f'predictions_{y}.csv.gz',usecols=p.KEYS+['profile_defensive_15']) for y in range(2020,2026)],ignore_index=True)
    x=x.merge(old,on=p.KEYS,validate='one_to_one')
    x['guarded_previous']=.8*x.open_model+.2*x.profile_defensive_15
    x[ANCHOR]=.75*x.guarded_previous+.25*x.rank_xendcg_balanced
    return x

def mature(x,cutoff):
    t=x[x.endpoint.lt(cutoff)&x.sector.ne('Unclassified')].dropna(subset=INNER+['future_xirr','future_drawdown','future_shortfall']).copy()
    keys=['decision_date','profile_name','sector']
    t=t[t.groupby(keys).isin.transform('size').ge(5)].copy()
    g=t.groupby(keys)
    t['return_target']=g.future_xirr.rank(pct=True)
    t['balanced_target']=.5*t.return_target+.25*g.future_drawdown.rank(pct=True)+.25*g.future_shortfall.rank(pct=True,ascending=False)
    t['weight']=1/g.isin.transform('size')
    assert t.empty or t.endpoint.max()<cutoff
    return t

def fit_nnls(t,c):
    cols=FEATURES if c['scope']=='outer' else INNER
    m=LinearRegression(positive=True,fit_intercept=False).fit(t[cols],t[c['target']+'_target'],sample_weight=t.weight)
    coef=m.coef_.copy()
    if coef.sum()<=0:raise ValueError('Degenerate learned weights')
    return {'features':cols,'weights':(coef/coef.sum()).tolist(),'raw_weights':coef.tolist()}

def infer_nnls(x,model):return x[model['features']].to_numpy()@np.array(model['weights'])

def protocol():
    OUT.mkdir(exist_ok=True)
    doc={'champion':'.75*(.8*open_model+.2*profile_defensive_15)+.25*rank_xendcg_balanced','configs':CONFIGS,
      'scope':'Only replace blending of retained champion components. Feature/price safeguards retained.',
      'training':'Annual meta fits use saved out-of-time component predictions whose outcomes end strictly before January1. 2020 and 2021 retain anchor because no mature out-of-time labels exist. Current fit cutoff October3.',
      'nnls':'scikit-learn nonnegative least squares, normalized coefficients; temporal stacking inspired by Super Learner, not a literal reproduction of its CV protocol.',
      'tabpfn':'Original pretrained v2 regressor, local CPU, one ensemble member, balanced target, equal-query weighted context sampling without replacement. No gradient fine tuning. Two component scores as inputs; replaces outer blend.',
      'tabpfn_scaling':'Evaluate pretrained function on 33x33 score grid, refine to65/129 if direct prediction MAE on128 training-input probe points exceeds .003 or max error exceeds .02; scipy bilinear interpolation. Bounds use fixed [-1,1] x [0,1], expanded by training inputs only. Explicit approximation, not direct per-row foundation inference. Exact direct prediction for out-of-grid rows or a rejected grid. Pilot using test-feature range archived without outcome evaluation.',
      'selection':'Fewest development Top3 regressions against current champion, then all development regressions, then name. Evaluate common/expanded raw/capped Top1/3/5 all9profiles six metrics. Recent results do not select.',
      'promotion':'Only replace retained champion if no metric/profile/scope/period comparison regresses and at least one improves. Otherwise retain champion and export research challenger separately.',
      'fresh_validation':False,'sources':['https://www.nature.com/articles/s41586-024-08328-6','https://github.com/PriorLabs/TabPFN','https://biostats.bepress.com/ucbbiostat/paper222/']}
    path=OUT/'protocol.json'
    if path.exists():assert json.loads(path.read_text())==doc
    else:path.write_text(json.dumps(doc,indent=2))

def learn():
    protocol();x=load();audit=[]
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        cutoff=p.ASOF if year=='current' else f'{year}-01-01'
        t=mature(x,cutoff)
        if year=='current':
            z=pd.read_csv(BASE/'current_all_stock_rankings.csv')
            z['guarded_previous']=z.guarded_model_score;z['open_model']=z.open_model_score;z['profile_defensive_15']=z.guarded_pure_score;z['rank_xendcg_balanced']=z.rebuilt_pure_score;z[ANCHOR]=z.rebuilt_score
        else:z=x[x.decision_date.str.startswith(str(year))].copy()
        for c in CONFIGS:
            name=c['name'];prefix=OUT/f'{name}_{year}'
            if t.empty:z[name]=z[ANCHOR];status='NO_MATURE_OOF_ANCHOR_FALLBACK'
            elif c['kind']=='nnls':
                m=fit_nnls(t,c);prefix.with_suffix('.json').write_text(json.dumps(m,indent=2));z[name]=infer_nnls(z,m)
                replay=infer_nnls(z,json.loads(prefix.with_suffix('.json').read_text()));np.testing.assert_array_equal(z[name],replay);status='FIT'
            else:
                # Probe rows use inputs only. Test labels are never passed to worker.
                rng=np.random.default_rng(20261010+c['context'])
                ids=rng.choice(len(t),size=min(c['context'],len(t)),replace=False,p=(t.weight/t.weight.sum()).to_numpy())
                context=t.iloc[ids]
                context[FEATURES+['balanced_target']].to_csv(str(prefix)+'_context.csv',index=False)
                z[FEATURES].to_csv(str(prefix)+'_inputs.csv',index=False)
                context[p.KEYS+['endpoint']].to_csv(str(prefix)+'_context_identity.csv',index=False)
                result=prefix.with_suffix('.npz')
                if not result.exists():
                    subprocess.run([sys.executable,str(p.ROOT/'research/runners/sector_tabpfn_worker_20261010.py'),str(prefix)],check=True)
                receipt=json.loads((OUT/f'{name}_{year}_audit.json').read_text())
                assert receipt['context_sha256']==hashlib.sha256((OUT/f'{name}_{year}_context.csv').read_bytes()).hexdigest()
                assert receipt['inputs_sha256']==hashlib.sha256((OUT/f'{name}_{year}_inputs.csv').read_bytes()).hexdigest()
                with np.load(result) as f:z[name]=f['predictions']
                assert len(z[name])==len(z) and np.isfinite(z[name]).all();status=receipt['mode']
            audit.append(dict(year=year,model=name,training_rows=len(t),maximum_endpoint=None if t.empty else t.endpoint.max(),cutoff=cutoff,status=status,rows=len(z)))
            pd.DataFrame(audit).to_csv(OUT/'training_audit.csv',index=False)
            print('LEARNED',year,name,status,flush=True)
        cols=p.KEYS+['sector',ANCHOR]+[c['name'] for c in CONFIGS]
        if year=='current':
            for c in CONFIGS:z[c['name']+'_sector_rank']=z[c['name']].groupby(z.sector).rank(method='min',ascending=False)
            z.to_csv(OUT/'current_all_4436_rankings.csv',index=False)
        else:z[cols].to_csv(OUT/f'predictions_{year}.csv.gz',index=False)

def evaluate():
    x=load();names=[c['name'] for c in CONFIGS]
    scores=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz',usecols=p.KEYS+names) for y in range(2020,2026)],ignore_index=True)
    x=x.merge(scores,on=p.KEYS,validate='one_to_one');summaries=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()] if scope=='common' else x
        for bounded in [False,True]:
            path=OUT/f'queries_{scope}_{bounded}.csv.gz'
            if path.exists():q=pd.read_csv(path)
            else:
                zz=z.copy()
                if bounded:zz.future_xirr=zz.future_xirr.clip(-1,1)
                q=p.metrics(zz,[ANCHOR]+names,top_ns=(1,3,5));q.to_csv(path,index=False)
            a=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index();a['scope']=scope;a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
            print('EVALUATED',scope,bounded,flush=True)
    s=pd.concat(summaries);s.to_csv(OUT/'summary.csv',index=False)
    a=s.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS];rows=[];ds=[]
    for name in names:
        d=(a.loc[name]-a.loc[ANCHOR]).dropna();d.shortfall=-d.shortfall;d=d.reset_index();d['model']=name;ds.append(d)
        v=d[p.METRICS].to_numpy();dev=d[d.period.eq('development')]
        rows.append(dict(model=name,regressions=int((v < -1e-12).sum()),improvements=int((v>1e-12).sum()),comparisons=v.size,strict_gate=bool((v>=-1e-12).all() and (v>1e-12).any()),development_top3_regressions=int(dev[dev.top_n.eq(3)][p.METRICS].lt(-1e-12).sum().sum()),development_regressions=int(dev[p.METRICS].lt(-1e-12).sum().sum())))
    trials=pd.DataFrame(rows).sort_values(['development_top3_regressions','development_regressions','model']);trials.to_csv(OUT/'trials.csv',index=False);pd.concat(ds).to_csv(OUT/'directional_deltas.csv',index=False)
    selected=trials.iloc[0].to_dict();selected.update(fresh_validation=False,production_replaced=False)
    (OUT/'selection.json').write_text(json.dumps(selected,indent=2));print(trials.to_string(index=False),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('step',choices=['learn','evaluate','protocol']);args=parser.parse_args()
    {'learn':learn,'evaluate':evaluate,'protocol':protocol}[args.step]()
