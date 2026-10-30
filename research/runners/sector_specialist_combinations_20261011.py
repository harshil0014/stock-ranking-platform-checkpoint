"""Predeclared specialist blends and chronological constrained stacking."""
import sector_specialist_ensemble_20261011 as s
from sector_pair_correction_20261011 import OUT as PAIR
from scipy.optimize import nnls
import json,hashlib
import numpy as np
import pandas as pd
OUT=s.OUT;p=s.p;h=s.h;ANCHOR=h.ANCHOR
YEARS=[2020,2021,2022,2023,2024,2025,'current']
LEGACY=['lgb_return_full_d3_w0.1','lgb_return_full_d3_w0.5','pfn_balanced_absolute_soft1.0_d3_w0.1','catpair_return_uniform_w0.1']
PURE=[f'{f}_{t}' for f in s.FAMILIES for t in s.TARGETS]
SPECIAL=[f'{f}_{t}' for f in s.FAMILIES for t in s.TARGETS+['balanced']]
ENSEMBLES=[f'{method}_{t}' for method in ['mean','median'] for t in s.TARGETS+['balanced']]
STACK=[f'stack_{mode}_{target}' for mode in ['global','breadth'] for target in ['return','balanced']]
BLENDS=[f'{name}_w{w}' for name in SPECIAL+ENSEMBLES+STACK for w in s.WEIGHTS]
NAMES=BLENDS+LEGACY

def protocol():
    doc=dict(candidates=NAMES,stack_inputs=PURE+LEGACY,
      standalone='Each independent model output is ranked within current sector/date/profile. Balanced output=.5return+.25risk+.25goal. Zero evidence falls back to champion percentile. Each is evaluated at strength1 as well as .1/.3 blends.',
      cross_family='Equal mean and median across six families for each target. Fixed combinations are ablation baselines; no assertion these weights are optimal.',
      stack='Nonnegative least squares on specialist/legacy score differences from champion percentile, using query weights and mature out-of-time predictions only. Coefficients sum capped at1, residual mass goes to champion. Global and breadth-conditioned coefficients. Training-median breadth splits; regional coefficients shrink to global with query_count/(query_count+100). No known sector identity or company lookup.',
      timing='Stack annual cutoffJanuary1/currentOct3, endpoint strictly earlier. 2020/21 no mature out-of-time data: anchor fallback for stacks only. Independent specialists still use pre2020 history.',
      selection='Development only, no mean XIRR weight. Lock highest expanded raw rankIC within each of6families, equal-ensemble family, and learned-stack family; also fewest Top3 regressions over drawdown/achievement/shortfall/NDCG/rankIC. Keep fixed4legacy controls. Tie-break regressions then name. Recent is exposed, never fresh.',
      promotion='Full1296cells gate remains plus stability and financial evidence review. Report all regressions; no universal guarantee.',fresh_validation=False)
    path=OUT/'combination_protocol.json'
    if path.exists():assert json.loads(path.read_text())==doc
    else:s.write(path.name,doc)

def enrich(z,year):
    raw=pd.read_csv(OUT/f'predictions_{year}.csv.gz',usecols=p.KEYS+PURE)
    z=z.merge(raw,on=p.KEYS,validate='one_to_one')
    for folder,cols in [(h.OUT,LEGACY[:3]),(PAIR,LEGACY[3:])]:
        z=z.merge(pd.read_csv(folder/f'predictions_{year}.csv.gz',usecols=p.KEYS+cols),on=p.KEYS,validate='one_to_one')
    g=z.groupby(s.GROUP)
    for name in PURE+LEGACY:z[name]=g[name].rank(pct=True).where(z.evidence_fraction.gt(0),z.champion_percentile)
    return z

def load():
    x=h.load();return pd.concat([enrich(x[x.decision_date.str.startswith(str(y))].copy(),y) for y in range(2020,2026)],ignore_index=True)

def stack_fit(t,target):
    cols=PURE+LEGACY;baseline=t.champion_percentile.to_numpy();a=t[cols].to_numpy()-baseline[:,None]
    b=t[target+'_target'].to_numpy()-baseline;w=np.sqrt(t.weight.to_numpy())
    coef,_=nnls(a*w[:,None],b*w,maxiter=1000)
    if coef.sum()>1:coef/=coef.sum()
    assert (coef>=0).all() and coef.sum()<=1+1e-12
    return coef

def stack_predict(z,coef):
    baseline=z.champion_percentile.to_numpy()
    return baseline+(z[PURE+LEGACY].to_numpy()-baseline[:,None])@np.asarray(coef)

def combine():
    protocol();x=load();audit=[]
    for year in YEARS:
        z=enrich(h.current(),year) if year=='current' else x[x.decision_date.str.startswith(str(year))].copy()
        cutoff=p.ASOF if year=='current' else f'{year}-01-01'
        t=h.train_rows(x,cutoff);basis={name:z[name].to_numpy() for name in PURE}
        for family in s.FAMILIES:basis[family+'_balanced']=.5*basis[family+'_return']+.25*basis[family+'_risk']+.25*basis[family+'_goal']
        for target in s.TARGETS+['balanced']:
            a=np.column_stack([basis[f+'_'+target] for f in s.FAMILIES])
            basis['mean_'+target]=np.mean(a,axis=1);basis['median_'+target]=np.median(a,axis=1)
        fits={}
        for target in ['return','balanced']:
            if t.empty:
                for mode in ['global','breadth']:basis[f'stack_{mode}_{target}']=z.champion_percentile.to_numpy()
                fits[target]={'fallback':True};continue
            coef=stack_fit(t,target);split=float(t.sector_breadth.median())
            region=[]
            for side in [False,True]:
                tt=t[t.sector_breadth.ge(split).eq(side)];count=tt.groupby(s.GROUP).ngroups
                local=stack_fit(tt,target) if count>=10 else coef
                alpha=count/(count+100) if count>=10 else 0
                region.append((1-alpha)*coef+alpha*local)
            basis[f'stack_global_{target}']=stack_predict(z,coef)
            basis[f'stack_breadth_{target}']=np.where(z.sector_breadth.ge(split),stack_predict(z,region[1]),stack_predict(z,region[0]))
            fits[target]=dict(features=PURE+LEGACY,global_weights=coef.tolist(),breadth_split=split,regional_weights=[c.tolist() for c in region],max_endpoint=t.endpoint.max(),cutoff=cutoff,rows=len(t))
            assert t.endpoint.max()<cutoff
        s.write(f'stack_models_{year}.json',fits)
        pred=z[p.KEYS+['sector',ANCHOR,'champion_percentile','evidence_fraction']].copy()
        scores={}
        for name in SPECIAL+ENSEMBLES+STACK:
            for w in s.WEIGHTS:scores[name+f'_w{w}']=z.champion_percentile.to_numpy()+w*(basis[name]-z.champion_percentile.to_numpy())
        for name in LEGACY:scores[name]=z[name].to_numpy()
        pred=pd.concat([pred.reset_index(drop=True),pd.DataFrame(scores)],axis=1)
        assert np.isfinite(pred[NAMES]).all().all() and len(pred)==len(z)
        pred.to_csv(OUT/f'combined_{year}.csv.gz',index=False)
        audit.append(dict(year=year,cutoff=cutoff,training_rows=len(t),maximum_endpoint=None if t.empty else t.endpoint.max(),rows=len(z)))
        if year=='current':
            meta=z[['isin','ticker','company','input_status','rebuilt_input_confidence','rebuilt_sector_rank']]
            cur=pred.merge(meta,on='isin',validate='one_to_one');assert len(cur)==4436 and cur['isin'].is_unique
            ranks=pd.DataFrame({n+'_rank':cur[n].groupby(cur.sector).rank(method='min',ascending=False) for n in NAMES})
            pd.concat([cur,ranks],axis=1).to_csv(OUT/'all_4436_all_candidates.csv',index=False)
        print('COMBINED',year,len(pred),flush=True)
    pd.DataFrame(audit).to_csv(OUT/'stack_audit.csv',index=False)

def evaluate(stage):
    dev=stage=='development';names=NAMES if dev else json.loads((OUT/'locked_finalists.json').read_text())['finalists']
    years=list(range(2020,2024)) if dev else [2024,2025]
    x=h.load();x=x[x.decision_date.str[:4].astype(int).isin(years)]
    scores=pd.concat([pd.read_csv(OUT/f'combined_{y}.csv.gz',usecols=p.KEYS+names) for y in years])
    x=x.merge(scores,on=p.KEYS,validate='one_to_one');summary=[]
    for start in range(0,len(names),12):
        batch=names[start:start+12]
        for scope in ['common','expanded']:
            z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
            for cap in [False,True]:
                path=OUT/f'queries_{stage}_{scope}_{cap}_{start}.csv.gz'
                if path.exists():q=pd.read_csv(path)
                else:
                    zz=z.copy()
                    if cap:zz.future_xirr=zz.future_xirr.clip(-1,1)
                    q=p.metrics(zz,[ANCHOR]+batch,top_ns=(1,3,5));q.to_csv(path,index=False)
                assert set(q.model)==set([ANCHOR]+batch)
                a=q.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index()
                a['scope']=scope;a['return_treatment']='capped' if cap else 'raw';summary.append(a)
                print('EVAL',stage,start,scope,cap,flush=True)
    ss=pd.concat(summary).drop_duplicates(['model','period','profile','top_n','scope','return_treatment']);ss.to_csv(OUT/f'summary_{stage}.csv',index=False)
    ix=ss.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS];trials=[]
    for name in names:
        d=(ix.loc[name]-ix.loc[ANCHOR]).reset_index();d.shortfall=-d.shortfall
        v=d[p.METRICS].to_numpy();nonreturn=[m for m in p.METRICS if m!='xirr'];top=d[d.top_n.eq(3)][nonreturn].to_numpy()
        ic=ss[ss.model.eq(name)&ss.scope.eq('expanded')&ss.return_treatment.eq('raw')&ss.top_n.eq(3)].rank_ic.mean()
        trials.append(dict(model=name,improved=int((v>1e-12).sum()),regressed=int((v< -1e-12).sum()),comparisons=v.size,top3_nonreturn_regressions=int((top< -1e-12).sum()),nonreturn_regressions=int((d[nonreturn].to_numpy()< -1e-12).sum()),rank_ic=ic))
    trials=pd.DataFrame(trials);trials.to_csv(OUT/f'trials_{stage}.csv',index=False)
    if dev:
        order=trials.sort_values(['rank_ic','nonreturn_regressions','model'],ascending=[False,True,True]);chosen=[]
        for prefixes in [[f+'_'] for f in s.FAMILIES]+[['mean_','median_'],['stack_']]:
            chosen.append(order[order.model.str.startswith(tuple(prefixes))].iloc[0].model)
        conservative=trials[~trials.model.isin(LEGACY)].sort_values(['top3_nonreturn_regressions','nonreturn_regressions','model']).iloc[0].model
        chosen=list(dict.fromkeys(chosen+[conservative]+LEGACY))
        s.write('locked_finalists.json',dict(finalists=chosen,conservative=conservative,development_sha256=s.digest(OUT/'trials_development.csv'),selection_mean_xirr_weight=0))
    print(trials.sort_values('rank_ic',ascending=False).head(15).to_string(index=False),flush=True)

if __name__=='__main__':
    import sys
    if sys.argv[1]=='protocol':protocol()
    elif sys.argv[1]=='combine':combine()
    else:evaluate(sys.argv[1])
