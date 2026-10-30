"""Mature-outcome CatBoost pairwise correction of the sector champion."""
import sys,json,hashlib,time
import numpy as np
import pandas as pd
import sector_tabpfn_hybrid_20261011 as h
from sector_accuracy_20261010 import pair_accuracy
sys.path.insert(0,str(h.p.ROOT/'experiments/model_dependencies_20261008'))
from catboost import CatBoostRanker,Pool
p=h.p; ANCHOR=h.ANCHOR; FEATURES=h.FEATURES
OUT=p.ROOT/'experiments/sector-pair-correction-20261011'
CONFIGS=[(target,focus) for target in ['return','balanced'] for focus in ['uniform','mistakes']]
WEIGHTS=[.1,.3,.6]
NEW=[f'catpair_{t}_{f}_w{w}' for t,f in CONFIGS for w in WEIGHTS]
CONTROLS=['lgb_return_full_d3_w0.1','lgb_return_full_d3_w0.5']
NAMES=NEW+CONTROLS
GROUP=['decision_date','profile_name','sector']
def write(name,data): (OUT/name).write_text(json.dumps(data,indent=2),encoding='utf-8')
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def protocol():
    OUT.mkdir(exist_ok=True)
    doc=dict(features=FEATURES,configs=CONFIGS,weights=WEIGHTS,controls=CONTROLS,
      algorithm='CatBoost 1.2.10 PairLogit, 160 trees, depth4, LR.035, L2=20, CPU4 threads, seed20261011. Champion sector percentile supplied as training baseline; inference adds only tree correction. Existing YetiRank experiment used a different objective and role.',
      pairs='Sample up to1500 complete sector/date/profile queries with equal query probability, seed20261011. Up to64 unique unordered stock pairs per query, ties excluded. Orient by return or balanced outcome target. Equal total pair weight per query; mistakes mode doubles weights of champion misorders before query normalization.',
      training='Use completed out-of-time component predictions only, endpoint strictly before annual January1 or frozen current October3. Reuse existing guarded labels/features. Evidence>0, classified sector, >=5 usable peers. 2020/21 champion fallback. Missing current features receive zero correction.',
      selection='Development2020-23 only: select highest expanded raw whole-sector rankIC CatBoost candidate and lowest Top3 regression-count CatBoost candidate; retain both fixed LightGBM controls. Tie breaks use fewer regressions then name. Lock before evaluating exposed2024-25.',
      evaluation='Same common/expanded cohorts; raw/capped returns;9profiles;Top1/3/5;6metrics. Pair order accuracy and descriptive sector bootstrap for finalists. No-regression gate across1296cells required for promotion. All historical dates are reused research, not new holdout.',
      sources=['https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html','https://catboost.ai/docs/en/concepts/loss-functions-ranking','https://catboost.ai/docs/en/concepts/python-usages-examples'],fresh_validation=False)
    path=OUT/'protocol.json'
    # JSON normalizes tuple configs to lists.
    if path.exists():assert json.loads(path.read_text())==json.loads(json.dumps(doc))
    else:write('protocol.json',doc)

def sample_queries(t):
    t=t.sort_values(GROUP+['isin']).reset_index(drop=True)
    ids=t.groupby(GROUP,sort=False).ngroup();rng=np.random.default_rng(20261011)
    selected=rng.choice(ids.unique(),min(1500,ids.nunique()),replace=False)
    return t[ids.isin(selected)].reset_index(drop=True)

def pairs_for(t,target,focus):
    rng=np.random.default_rng(20261011);pairs=[];weights=[]
    for _,g in t.groupby(GROUP,sort=False):
        idx=g.index.to_numpy();n=len(idx);possible=n*(n-1)//2
        if possible<=64:
            a,b=np.triu_indices(n,1);chosen=list(zip(a,b))
        else:
            chosen=set()
            while len(chosen)<64:
                a,b=sorted(rng.choice(n,2,replace=False));chosen.add((int(a),int(b)))
            chosen=sorted(chosen)
        y=g[target+'_target'].to_numpy();base=g.champion_percentile.to_numpy();local=[];ww=[]
        for a,b in chosen:
            if y[a]==y[b]:continue
            win,lose=(a,b) if y[a]>y[b] else (b,a)
            local.append((int(idx[win]),int(idx[lose])))
            ww.append(2. if focus=='mistakes' and base[win]<=base[lose] else 1.)
        if local:
            pairs.extend(local);weights.extend(np.asarray(ww)/sum(ww))
    weights=np.asarray(weights);weights/=weights.mean()
    pairs=np.asarray(pairs,dtype=int)
    groups=t.groupby(GROUP,sort=False).ngroup().to_numpy()
    assert np.all(groups[pairs[:,0]]==groups[pairs[:,1]])
    labels=t[target+'_target'].to_numpy()
    assert np.all(labels[pairs[:,0]]>labels[pairs[:,1]])
    return pairs,weights,groups

def learn():
    protocol();x=h.load();audits=[]
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        receipt=OUT/f'audit_{year}.json'
        if receipt.exists():audits+=json.loads(receipt.read_text());continue
        start=time.time();cutoff=p.ASOF if year=='current' else f'{year}-01-01'
        z=h.current() if year=='current' else x[x.decision_date.str.startswith(str(year))].copy()
        t=h.train_rows(x,cutoff);pred=z[p.KEYS+['sector',ANCHOR,'evidence_fraction']].copy();rows=[]
        if t.empty:
            for name in NEW:pred[name]=z[ANCHOR]
            rows.append(dict(year=year,status='ANCHOR_FALLBACK',cutoff=cutoff,training_rows=0))
        else:
            t=sample_queries(t);assert t.endpoint.max()<cutoff
            t[p.KEYS+['sector','endpoint']].to_csv(OUT/f'training_identity_{year}.csv',index=False)
            for target,focus in CONFIGS:
                pairs,weights,groups=pairs_for(t,target,focus)
                pool=Pool(t[FEATURES],label=t[target+'_target'],group_id=groups,pairs=pairs,pairs_weight=weights,baseline=t.champion_percentile)
                model=CatBoostRanker(loss_function='PairLogit',iterations=160,depth=4,learning_rate=.035,l2_leaf_reg=20,thread_count=4,random_seed=20261011,allow_writing_files=False,verbose=False)
                model.fit(pool)
                key=f'catpair_{target}_{focus}';path=OUT/f'{key}_{year}.cbm';model.save_model(str(path))
                raw=model.predict(z[FEATURES],thread_count=4);reloaded=CatBoostRanker();reloaded.load_model(str(path))
                np.testing.assert_allclose(raw,reloaded.predict(z[FEATURES],thread_count=4),rtol=0,atol=0)
                # Verify library baseline semantics independently of our score combination.
                probe=z.iloc[:100];baseline=probe.champion_percentile.to_numpy()
                np.testing.assert_allclose(model.predict(Pool(probe[FEATURES],baseline=baseline),thread_count=4),model.predict(probe[FEATURES],thread_count=4)+baseline,atol=1e-7,rtol=0)
                for w in WEIGHTS:pred[key+f'_w{w}']=h.corrected(z,raw,w)
                rows.append(dict(year=year,model=key,cutoff=cutoff,maximum_endpoint=t.endpoint.max(),training_rows=len(t),queries=int(len(np.unique(groups))),pairs=len(pairs),model_sha256=digest(path),serialized_replay_exact=True,baseline_semantics_verified=True))
                print('FIT',year,key,len(t),len(pairs),round(time.time()-start,1),flush=True)
        controls=pd.read_csv(h.OUT/f'predictions_{year}.csv.gz',usecols=p.KEYS+CONTROLS)
        pred=pred.merge(controls,on=p.KEYS,validate='one_to_one');assert len(pred)==len(z) and np.isfinite(pred[NAMES]).all().all()
        pred.to_csv(OUT/f'predictions_{year}.csv.gz',index=False)
        if year=='current':
            cur=pred.merge(z[['isin','ticker','company','input_status','rebuilt_input_confidence','rebuilt_sector_rank']],on='isin',validate='one_to_one')
            assert len(cur)==4436 and cur['isin'].is_unique
            for name in NAMES:cur[name+'_rank']=cur[name].groupby(cur.sector).rank(method='min',ascending=False)
            cur.to_csv(OUT/'all_4436_all_candidates.csv',index=False)
        write(receipt.name,rows);audits+=rows
        pd.DataFrame(audits).to_csv(OUT/'training_audit.csv',index=False)

def evaluate(stage):
    dev=stage=='development';names=NAMES if dev else json.loads((OUT/'locked_finalists.json').read_text())['finalists']
    years=list(range(2020,2024)) if dev else [2024,2025]
    x=h.load();x=x[x.decision_date.str[:4].astype(int).isin(years)]
    scores=pd.concat([pd.read_csv(OUT/f'predictions_{y}.csv.gz',usecols=p.KEYS+names) for y in years])
    x=x.merge(scores,on=p.KEYS,validate='one_to_one');summaries=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        for cap in [False,True]:
            path=OUT/f'queries_{stage}_{scope}_{cap}.csv.gz'
            if path.exists():q=pd.read_csv(path)
            else:
                zz=z.copy()
                if cap:zz.future_xirr=zz.future_xirr.clip(-1,1)
                q=p.metrics(zz,[ANCHOR]+names,top_ns=(1,3,5));q.to_csv(path,index=False)
            assert set(q.model)==set([ANCHOR]+names)
            a=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
            a['scope']=scope;a['return_treatment']='capped' if cap else 'raw';summaries.append(a)
            print('EVALUATED',stage,scope,cap,flush=True)
    s=pd.concat(summaries);s.to_csv(OUT/f'summary_{stage}.csv',index=False)
    ix=s.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS];trials=[]
    for name in names:
        d=(ix.loc[name]-ix.loc[ANCHOR]).reset_index();d.shortfall=-d.shortfall
        v=d[p.METRICS].to_numpy();top=d[d.top_n.eq(3)][p.METRICS].to_numpy()
        ic=s[s.model.eq(name)&s.scope.eq('expanded')&s.return_treatment.eq('raw')&s.top_n.eq(3)].rank_ic.mean()
        trials.append(dict(model=name,regressions=int((v< -1e-12).sum()),improvements=int((v>1e-12).sum()),comparisons=v.size,top3_regressions=int((top< -1e-12).sum()),rank_ic=ic))
    trials=pd.DataFrame(trials);trials.to_csv(OUT/f'trials_{stage}.csv',index=False)
    if dev:
        c=trials[trials.model.isin(NEW)]
        accuracy=c.sort_values(['rank_ic','regressions','model'],ascending=[False,True,True]).iloc[0].model
        conservative=c.sort_values(['top3_regressions','regressions','model']).iloc[0].model
        write('locked_finalists.json',dict(finalists=list(dict.fromkeys([accuracy,conservative]+CONTROLS)),accuracy_leader=accuracy,conservative_leader=conservative,development_sha256=digest(OUT/'trials_development.csv')))
    print(trials.to_string(index=False),flush=True)

if __name__=='__main__':
    step=sys.argv[1]
    if step=='learn':learn()
    elif step in ['development','recent']:evaluate(step)
