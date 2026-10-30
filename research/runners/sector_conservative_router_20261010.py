"""Completed-feedback, baseline-preserving sector routing; no theoretical guarantee."""
import json,itertools
import numpy as np
import pandas as pd
import sector_price_rebuild_20261010 as p
BASE=p.OUT;OUT=p.ROOT/'experiments/sector-conservative-router-20261010'
ANCHOR='rank_xendcg_balanced_blend0.25'
EXPERTS=[ANCHOR,'guarded_previous','lambdarank_balanced_blend0.25','lambdarank_return_blend0.1','regression_l1_balanced_blend0.25','yeti_ndcg3_balanced_blend0.1']
CONFIGS=[dict(name=f'conservative_n{n}_w{w}',minimum=n,weight=w,guard=True) for n,w in itertools.product([4,8],[.5,1.])]+[dict(name=f'utility_n8_w{w}',minimum=8,weight=w,guard=False) for w in [.5,1.]]

def choose(past,c):
    if past.empty:return ANCHOR
    # Every date contributes one observation per metric. No stock-count weighting.
    wide=past.pivot(index='date',columns='model',values=p.METRICS)
    candidates=[]
    for model in EXPERTS:
        if model==ANCHOR:continue
        d=pd.DataFrame({m:wide[(m,model)]-wide[(m,ANCHOR)] for m in p.METRICS}).dropna()
        if len(d)<c['minimum']:continue
        d.shortfall=-d.shortfall;mean=d.mean()
        # Shrink toward no benefit; conservative gate also demands each metric's
        # paired lower margin be nonnegative. Not an independence-based CI claim.
        lower=mean-d.std(ddof=1).fillna(0)/np.sqrt(len(d))
        if c['guard'] and (lower < -1e-12).any():continue
        utility=mean.xirr+.5*mean.drawdown+.5*mean.achievement+mean.shortfall+.2*mean.ndcg+.2*mean.rank_ic
        if utility>0:candidates.append((utility*len(d)/(len(d)+8),model))
    return sorted(candidates,key=lambda z:(-z[0],z[1]))[0][1] if candidates else ANCHOR

def run():
    OUT.mkdir(exist_ok=True)
    (OUT/'protocol.json').write_text(json.dumps({'configs':CONFIGS,'experts':EXPERTS,'anchor':ANCHOR,'feedback':'Expanded cohort, capped outcomes, Top3. Only same-profile/same-sector query outcomes with maximum endpoint strictly earlier than decision. Latest five years.', 'selection':'Fewest development Top3 regressions then all development regressions; recent period excluded. All dates previously exposed.', 'scope':'Original four references plus current anchor, raw/capped, common/expanded, all9profiles Top1/3/5 sixmetrics.', 'sources':['https://proceedings.mlr.press/v97/laroche19a.html','https://proceedings.mlr.press/v128/korotin20a.html'],'guarantee':False},indent=2))
    x=pd.concat([pd.read_csv(BASE/f'predictions_{y}.csv.gz') for y in range(2020,2026)],ignore_index=True)
    old=pd.concat([pd.read_csv(p.OLD/f'predictions_{y}.csv.gz',usecols=p.KEYS+['profile_defensive_15']) for y in range(2020,2026)],ignore_index=True)
    x=x.merge(old,on=p.KEYS,validate='one_to_one');x['guarded_previous']=.8*x.open_model+.2*x.profile_defensive_15
    yeti=p.ROOT/'experiments/sector-yetirank-20261010'
    y=pd.concat([pd.read_csv(yeti/f'predictions_{y}.csv.gz',usecols=p.KEYS+['yeti_ndcg3_balanced']) for y in range(2020,2026)],ignore_index=True)
    x=x.merge(y,on=p.KEYS,validate='one_to_one')
    for name in EXPERTS:
        if '_blend' in name:
            col,w=name.split('_blend');w=float(w);x[name]=(1-w)*x.guarded_previous+w*x[col]
    feedback=[]
    for folder in [BASE,yeti]:
        for path in folder.glob('queries_expanded_True_*.csv.gz'):
            q=pd.read_csv(path);feedback.append(q[q.top_n.eq(3)&q.model.isin(EXPERTS)])
    q=pd.concat(feedback).drop_duplicates(['date','profile','sector','model'])
    endpoints=x.groupby(['decision_date','profile_name','sector']).endpoint.max().rename('endpoint').reset_index().rename(columns={'decision_date':'date','profile_name':'profile'})
    q=q.merge(endpoints,on=['date','profile','sector'],validate='many_to_one')
    audits=[]
    for c in CONFIGS:x[c['name']]=x[ANCHOR]
    for (profile,sector),g in x.groupby(['profile_name','sector']):
        history=q[q.profile.eq(profile)&q.sector.eq(sector)]
        for day,cohort in g.groupby('decision_date'):
            cutoff=(pd.Timestamp(day)-pd.DateOffset(years=5)).date().isoformat()
            past=history[history.endpoint.lt(day)&history.endpoint.ge(cutoff)]
            assert past.empty or past.endpoint.max()<day
            for c in CONFIGS:
                expert=choose(past,c);x.loc[cohort.index,c['name']]=(1-c['weight'])*cohort[ANCHOR]+c['weight']*cohort[expert]
                audits.append(dict(profile=profile,sector=sector,date=day,model=c['name'],expert=expert,completed_dates=past.date.nunique(),maximum_endpoint=past.endpoint.max() if len(past) else None))
    pd.DataFrame(audits).to_csv(OUT/'routing_audit.csv.gz',index=False)
    x[p.KEYS+['sector','period']+[c['name'] for c in CONFIGS]].to_csv(OUT/'candidate_scores.csv.gz',index=False)
    summaries=[]
    for scope in ['common','expanded']:
        z=x[x.sector_incumbent.notna()].copy() if scope=='common' else x.copy()
        refs=['guarded_previous','open_model','frozen_challenger',ANCHOR]+(['sector_incumbent'] if scope=='common' else [])
        for bounded in [False,True]:
            zz=z.copy()
            if bounded:zz.future_xirr=zz.future_xirr.clip(-1,1)
            v=p.metrics(zz,refs+[c['name'] for c in CONFIGS],top_ns=(1,3,5))
            v.to_csv(OUT/f'queries_{scope}_{bounded}.csv.gz',index=False)
            a=v.groupby(['model','period','profile','top_n','sector'])[p.METRICS].mean().groupby(['model','period','profile','top_n']).mean().reset_index();a['scope']=scope;a['return_treatment']='capped' if bounded else 'raw';summaries.append(a)
            print('ROUTER EVALUATED',scope,bounded,flush=True)
    summary=pd.concat(summaries);summary.to_csv(OUT/'summary.csv',index=False)
    a=summary.set_index(['model','period','profile','top_n','scope','return_treatment'])[p.METRICS];trials=[];deltas=[]
    for c in CONFIGS:
        parts=[]
        for ref in ['guarded_previous','open_model','frozen_challenger','sector_incumbent',ANCHOR]:
            d=(a.loc[c['name']]-a.loc[ref]).dropna();d.shortfall=-d.shortfall;d['reference']=ref;parts.append(d.reset_index())
        d=pd.concat(parts);d['model']=c['name'];deltas.append(d);dev=d[d.period.eq('development')];vals=d[p.METRICS].to_numpy().ravel();parent=d[d.reference.eq(ANCHOR)][p.METRICS].to_numpy().ravel()
        trials.append(dict(model=c['name'],strict_gate=bool((vals>=-1e-12).all() and (vals>1e-12).any()),regressions=int((vals < -1e-12).sum()),comparisons=len(vals),parent_regressions=int((parent < -1e-12).sum()),parent_improvements=int((parent>1e-12).sum()),development_top3_regressions=int(dev[dev.top_n.eq(3)][p.METRICS].lt(-1e-12).sum().sum()),development_regressions=int(dev[p.METRICS].lt(-1e-12).sum().sum())))
    trials=pd.DataFrame(trials).sort_values(['development_top3_regressions','development_regressions','model']);trials.to_csv(OUT/'trials.csv',index=False);pd.concat(deltas).to_csv(OUT/'directional_deltas.csv',index=False)
    (OUT/'selection.json').write_text(json.dumps(trials.iloc[0].to_dict(),indent=2));print(trials.to_string(index=False),flush=True)
    audit=pd.DataFrame(audits);print('Switch counts',audit.assign(switched=audit.expert.ne(ANCHOR)).groupby('model').switched.sum().to_dict(),flush=True)

if __name__=='__main__':run()
