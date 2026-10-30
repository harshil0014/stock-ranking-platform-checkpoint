"""TabPFN teachers + LightGBM residual students with temporal, full-coverage evaluation."""
import json,hashlib,subprocess,sys,gc
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import lightgbm as lgb
from sector_learned_blend_20261010 import p,load as load_base,mature,ANCHOR
OUT=p.ROOT/'experiments/sector-tabpfn-hybrid-20261011'
TEACHERS=['balanced_absolute','balanced_residual','return_residual']
FEATURES=['champion_percentile','rank_xendcg_balanced','guarded_percentile','q_high_gap252','q_high_age252','q_momentum12_1','q_downside252','q_drawdown252','q_zero_fraction','q_largest_jump_share','q_trend_r2','q_efficiency126','evidence_fraction','sector_breadth']+p.PARAMS
CONFIGS=[]
for target in ['balanced','return']:
    for data in ['pool','full']:
        for depth in [3,5]:CONFIGS.append(dict(name=f'lgb_{target}_{data}_d{depth}',teacher=None,target=target,data=data,depth=depth,alpha=0.))
for teacher in TEACHERS:
    for alpha in [.5,1.]:
        for depth in [3,5]:CONFIGS.append(dict(name=f'pfn_{teacher}_soft{alpha}_d{depth}',teacher=teacher,target=teacher.split('_')[0],data='pool',depth=depth,alpha=alpha))
WEIGHTS=[.1,.25,.5]
NAMES=[c['name']+f'_w{w}' for c in CONFIGS for w in WEIGHTS]

def write(name,value): (OUT/name).write_text(json.dumps(value,indent=2),encoding='utf-8')

def protocol():
    OUT.mkdir(exist_ok=True)
    doc={'configs':CONFIGS,'weights':WEIGHTS,'features':FEATURES,'teacher_context':768,'teacher_estimators':2,'student_pool':4096,
     'training':'Completed out-of-time component predictions only; annual endpoint cutoff January1. 2020/2021 anchor fallback. Current cutoff October3. Finite usable price features, known sector and >=5 peers in teacher/student training.',
     'teacher':'Original TabPFN v2, richer inputs, two-member internal ensemble; in-context adaptation, not gradient fine tuning. Exact batched inference, no grid. Equal-query context sample; student pool excludes context identities.',
     'student':'Open-source LightGBM residual regression. Targets mix hard historical outcome percentiles and TabPFN soft predictions. Pool-only and full-data controls isolate teacher contribution. Normalized inverse query-size sample weights.',
     'target':'Return percentile or .5 return+.25 drawdown+.25 inverse shortfall, minus point-in-time champion within-sector percentile. Absolute teacher is converted to residual by subtracting champion percentile.',
     'score':'champion sector percentile + weight*predicted residual for usable features; zero correction otherwise. Champion score retained for fallback years. All-stock finite ranking, missing evidence flagged.',
     'selection':'Evaluate all60 on development2020-23 first. Lock three finalists: best teacher/student candidate, best full-data control, best pool-only control; fewest development Top3 regressions vs champion, then all development regressions, then higher expanded raw rankIC, then name. Evaluate only these3 on exposed2024-25.',
     'benchmark':'Same common/expanded cohorts, raw/capped XIRR,9profiles,Top1/3/5 and6metrics. Pair-order diagnostic for finalists. Active years separated from fallback.',
     'promotion':'Retain champion unless development-selected hybrid passes no-regression comparison to champion in every full benchmark cell with at least one improvement. All other tradeoffs explicitly reported.',
     'fresh_validation':False,'sources':['https://www.nature.com/articles/s41586-024-08328-6','https://github.com/PriorLabs/TabPFN','https://arxiv.org/abs/1503.02531','https://lightgbm.readthedocs.io/en/latest/Parameters.html']}
    f=OUT/'protocol.json'
    if f.exists():assert json.loads(f.read_text())==doc
    else:write('protocol.json',doc)

def enrich(z):
    g=z.groupby(['decision_date','profile_name','sector'])
    z['champion_percentile']=g[ANCHOR].rank(pct=True)
    z['guarded_percentile']=g.guarded_previous.rank(pct=True)
    return z

def load():
    x=load_base();features=pd.read_pickle(p.OUT/'prepared.pkl.gz',compression='gzip')
    cols=[c for c in FEATURES if c not in x and c not in ['champion_percentile','guarded_percentile']]
    x=x.merge(features[p.KEYS+cols],on=p.KEYS,validate='one_to_one');del features
    return enrich(x)

def train_rows(x,cutoff):
    # Outcome ranks use the same mature query populations as the previous experiment.
    t=mature(x,cutoff)
    t=t[t.evidence_fraction.gt(0)].copy()
    keys=['decision_date','profile_name','sector']
    t=t[t.groupby(keys)['isin'].transform('size').ge(5)].copy()
    t['weight']=1/t.groupby(keys)['isin'].transform('size')
    for target in ['balanced','return']:t[target+'_residual']=t[target+'_target']-t.champion_percentile
    return t

def current():
    z=pd.read_csv(p.OUT/'current_all_stock_rankings.csv')
    z[ANCHOR]=z.rebuilt_score;z['guarded_previous']=z.guarded_model_score;z['rank_xendcg_balanced']=z.rebuilt_pure_score
    return enrich(z)

def corrected(z,residual,w):
    return z.champion_percentile.to_numpy()+w*np.where(z.evidence_fraction.gt(0),residual,0.)

def fit_student(t,y,c):
    m=lgb.LGBMRegressor(objective='regression_l2',n_estimators=240,num_leaves=2**c['depth']-1,max_depth=c['depth'],min_child_samples=80,reg_lambda=40,learning_rate=.025,n_jobs=3,random_state=20261011,deterministic=True,force_col_wise=True,verbosity=-1)
    m.fit(t[FEATURES],y,sample_weight=t.weight/t.weight.mean())
    return m

def learn():
    protocol();x=load();audit=[]
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        output=OUT/f'predictions_{year}.csv.gz'
        if output.exists() and (OUT/f'fit_audit_{year}.json').exists() and (year!='current' or (OUT/'all_4436_all_candidates.csv').exists()):
            audit.extend(json.loads((OUT/f'fit_audit_{year}.json').read_text()));continue
        cutoff=p.ASOF if year=='current' else f'{year}-01-01';t=train_rows(x,cutoff)
        z=current() if year=='current' else x[x.decision_date.str.startswith(str(year))].copy()
        preds=z[p.KEYS+['sector',ANCHOR,'evidence_fraction']].copy();year_audit=[]
        if t.empty:
            for name in NAMES:preds[name]=z[ANCHOR]
            year_audit.append(dict(year=year,status='NO_MATURE_OOF_ANCHOR_FALLBACK',cutoff=cutoff,training_rows=0))
        else:
            rng=np.random.default_rng(20261011)
            # One fixed pool shared by all teachers and matched controls.
            pool_ids=rng.choice(len(t),size=min(4096,len(t)),replace=False,p=(t.weight/t.weight.sum()).to_numpy())
            pool=t.iloc[pool_ids].copy();available=t.drop(index=pool.index)
            pool[p.KEYS+['endpoint']].to_csv(OUT/f'pool_identity_{year}.csv',index=False)
            soft={};pending=[];contexts={}
            for j,teacher in enumerate(TEACHERS):
                prefix=OUT/f'{teacher}_{year}';rng=np.random.default_rng(20261011+j)
                ids=rng.choice(len(available),min(768,len(available)),replace=False,p=(available.weight/available.weight.sum()).to_numpy())
                context=available.iloc[ids].copy();label=teacher.split('_')[0]+('_target' if teacher.endswith('absolute') else '_residual')
                context[FEATURES+[label]].rename(columns={label:'teacher_target'}).to_csv(str(prefix)+'_context.csv',index=False)
                context[p.KEYS+['endpoint']].to_csv(str(prefix)+'_identity.csv',index=False)
                pool[FEATURES].to_csv(str(prefix)+'_inputs.csv',index=False)
                contexts[teacher]=context
                if not (prefix.with_suffix('.npz').exists() and (OUT/f'{teacher}_{year}_audit.json').exists()):pending.append(prefix)
            def run_teacher(prefix):
                subprocess.run([sys.executable,str(p.ROOT/'research/runners/sector_tabpfn_rich_worker_20261011.py'),str(prefix)],check=True)
            # Two independent local fits, three CPU threads each, on this eight-core host.
            with ThreadPoolExecutor(max_workers=2) as executor:list(executor.map(run_teacher,pending))
            for teacher in TEACHERS:
                prefix=OUT/f'{teacher}_{year}';context=contexts[teacher]
                receipt=json.loads((OUT/f'{teacher}_{year}_audit.json').read_text())
                for kind in ['context','inputs']:assert receipt[kind+'_sha256']==hashlib.sha256((OUT/f'{teacher}_{year}_{kind}.csv').read_bytes()).hexdigest()
                with np.load(prefix.with_suffix('.npz')) as f:soft[teacher]=f['predictions'].astype(float)
                if teacher.endswith('absolute'):soft[teacher]-=pool.champion_percentile.to_numpy()
                year_audit.append(dict(year=year,model=teacher,cutoff=cutoff,maximum_endpoint=context.endpoint.max(),training_rows=len(context),teacher_seconds=receipt['seconds'],status='DIRECT_TEACHER'))
            for c in CONFIGS:
                data=t if c['data']=='full' else pool;y=data[c['target']+'_residual'].to_numpy()
                if c['teacher']:y=(1-c['alpha'])*y+c['alpha']*soft[c['teacher']]
                model=fit_student(data,y,c);path=OUT/f'{c["name"]}_{year}.txt';model.booster_.save_model(str(path))
                residual=model.predict(z[FEATURES]);replay=lgb.Booster(model_file=str(path)).predict(z[FEATURES],num_threads=2)
                np.testing.assert_allclose(residual,replay,atol=0,rtol=0)
                for w in WEIGHTS:preds[c['name']+f'_w{w}']=corrected(z,residual,w)
                year_audit.append(dict(year=year,model=c['name'],cutoff=cutoff,maximum_endpoint=data.endpoint.max(),training_rows=len(data),status='STUDENT_OR_CONTROL',replay_exact=True))
                print('STUDENT',year,c['name'],flush=True)
        assert len(preds)==len(z) and np.isfinite(preds[NAMES]).all().all()
        preds.to_csv(output,index=False);write(f'fit_audit_{year}.json',year_audit);audit.extend(year_audit)
        pd.DataFrame(audit).to_csv(OUT/'training_audit.csv',index=False)
        if year=='current':
            assert len(preds)==4436 and preds['isin'].is_unique
            meta=z[['isin','ticker','company','input_status','rebuilt_input_confidence','rebuilt_sector_rank']]
            exported=preds.merge(meta,on='isin',validate='one_to_one')
            for name in NAMES:exported[name+'_rank']=exported[name].groupby(exported.sector).rank(method='min',ascending=False)
            exported.to_csv(OUT/'all_4436_all_candidates.csv',index=False)
        print('YEAR COMPLETE',year,len(preds),flush=True)

def evaluate(stage):
    x=load();dev=stage=='development'
    years=[2020,2021,2022,2023] if dev else [2024,2025]
    names=NAMES if dev else json.loads((OUT/'locked_finalists.json').read_text())['finalists']
    x=x[x.decision_date.str[:4].astype(int).isin(years)]
    scores=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz',usecols=p.KEYS+names) for y in years],ignore_index=True)
    x=x.merge(scores,on=p.KEYS,validate='one_to_one');summaries=[]
    for start in range(0,len(names),10):
        batch=names[start:start+10]
        for scope in ['common','expanded']:
            z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
            for capped in [False,True]:
                path=OUT/f'queries_{stage}_{scope}_{capped}_{start}.csv.gz'
                q=pd.read_csv(path) if path.exists() else None
                if q is None or set(q.model.unique())!=set([ANCHOR]+batch):
                    zz=z.copy()
                    if capped:zz.future_xirr=zz.future_xirr.clip(-1,1)
                    q=p.metrics(zz,[ANCHOR]+batch,top_ns=(1,3,5));q.to_csv(path,index=False)
                a=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index();a['scope']=scope;a['return_treatment']='capped' if capped else 'raw';summaries.append(a)
                print('EVALUATED',stage,start,scope,capped,flush=True)
        gc.collect()
    s=pd.concat(summaries).drop_duplicates(['model','period','profile','top_n','scope','return_treatment']);s.to_csv(OUT/f'summary_{stage}.csv',index=False)
    index=['model','period','profile','top_n','scope','return_treatment'];a=s.set_index(index)[p.METRICS];ds=[];trials=[]
    for name in names:
        d=(a.loc[name]-a.loc[ANCHOR]).reset_index();d.shortfall=-d.shortfall;d['model']=name;ds.append(d)
        v=d[p.METRICS].to_numpy();top=d[d.top_n.eq(3)][p.METRICS].to_numpy()
        ic=s[s.model.eq(name)&s.scope.eq('expanded')&s.return_treatment.eq('raw')&s.top_n.eq(3)].rank_ic.mean()
        trials.append(dict(model=name,regressions=int((v< -1e-12).sum()),improvements=int((v>1e-12).sum()),comparisons=v.size,top3_regressions=int((top< -1e-12).sum()),rank_ic=ic,strict_gate=bool((v>=-1e-12).all() and (v>1e-12).any())))
    trials=pd.DataFrame(trials).sort_values(['top3_regressions','regressions','rank_ic','model'],ascending=[True,True,False,True]);trials.to_csv(OUT/f'trials_{stage}.csv',index=False);pd.concat(ds).to_csv(OUT/f'deltas_{stage}.csv',index=False)
    if dev:
        finalists=[]
        for mask in [trials.model.str.startswith('pfn_'),trials.model.str.startswith('lgb_')&trials.model.str.contains('_full_'),trials.model.str.startswith('lgb_')&trials.model.str.contains('_pool_')]:finalists.append(trials[mask].iloc[0].model)
        # Pre-evaluation amendment: preserve whole-sector accuracy leaders as well.
        accuracy=trials.sort_values(['rank_ic','top3_regressions','regressions','model'],ascending=[False,True,True,True])
        accuracy_leaders=[accuracy[accuracy.model.str.startswith(prefix)].iloc[0].model for prefix in ['pfn_','lgb_']]
        finalists=list(dict.fromkeys(finalists+accuracy_leaders))
        matched={}
        for hybrid in [finalists[0],accuracy_leaders[0]]:
            base,w=hybrid.rsplit('_w',1);c=next(c for c in CONFIGS if c['name']==base)
            matched[hybrid]=f'lgb_{c["target"]}_pool_d{c["depth"]}_w{w}'
        finalists=list(dict.fromkeys(finalists+list(matched.values())))
        write('locked_finalists.json',{'finalists':finalists,'accuracy_leaders':accuracy_leaders,'matched_teacher_controls':matched,'selection':'development only; includes pre-evaluation whole-sector accuracy and matched-control amendment','development_trials_sha256':hashlib.sha256((OUT/'trials_development.csv').read_bytes()).hexdigest()})
    print(trials.head(12).to_string(index=False),flush=True)

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('step',choices=['protocol','learn','development','recent']);a=parser.parse_args()
    if a.step=='protocol':protocol()
    elif a.step=='learn':learn()
    else:evaluate(a.step)
