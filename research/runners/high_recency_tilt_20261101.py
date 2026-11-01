"""Fixed high-recency preference sweep; no fitting or exposed evaluation."""
import os
for k in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[k]='1'
from pathlib import Path
import json,hashlib,pickle,datetime
import numpy as np
import pandas as pd
import professor_frontier_20261101 as base
ROOT=base.ROOT
OUT=ROOT/'experiments/high-recency-tilt-20261101'
WORK=ROOT/'work/high-recency-tilt-20261101'
WEIGHTS={'recency10':.10,'recency20':.20,'recency35':.35,'recency50':.50}
def save(n,v):
    (OUT/n).write_text(json.dumps(v,indent=2,default=lambda z:z.item() if hasattr(z,'item') else str(z)),encoding='utf-8')
def blend(c,q,w):return (1-w)*c+w*q
def main():
    OUT.mkdir(exist_ok=True);WORK.mkdir(exist_ok=True);base.OUT=OUT
    files=[ROOT/'research/protocols/high_recency_tilt_20261101.md',ROOT/'work/professor-frontier-20261101/development_scored.pkl.gz',ROOT/'work/new-information-20261101/actual_adjusted_open_close.pkl',ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv']
    save('input_receipts.json',[dict(path=p.relative_to(ROOT).as_posix(),sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in files])
    save('started.json',dict(utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),exposed_evaluated=False))
    x=pd.read_pickle(files[1],compression='gzip');assert x.decision_date.between('2020-01-01','2023-12-31').all()
    names=['champion']+list(WEIGHTS)
    for name,w in WEIGHTS.items():x[name]=blend(x.champion_percentile,x.q_high_recency,w)
    assert np.isfinite(x[names]).all().all()
    with files[2].open('rb') as f:paths=pickle.load(f)
    actions=pd.read_csv(files[3]);actions=actions[actions.status.ne('ALIGNED_MULTIPLIER')]
    summary,perdate,pairs=base.evaluate(x,names,'development',paths,actions)
    rows=[]
    for (date,sector),g in x.groupby(['decision_date','sector']):
        for name in names:
            h=base.selections(g,name)
            rows.append(dict(decision_date=date,sector=sector,model=name,high_percentile=h.q_high_recency.mean(),days_since_high=-h.high_recency.mean()))
    a=pd.DataFrame(rows);a.to_csv(OUT/'development_high_alignment.csv',index=False)
    align=a.groupby(['decision_date','model'])[['high_percentile','days_since_high']].mean().groupby('model').mean()
    table=summary.join(align);b=table.loc['champion'];decisions=[]
    for name,w in WEIGHTS.items():
        r=table.loc[name];p=pairs[pairs.model.eq(name)&pairs.policy.eq('global_top20')].iloc[0]
        checks=dict(high_alignment=r.high_percentile>b.high_percentile,changed=r.changed>=.2,ic=r.rank_ic-b.rank_ic>=-.02,goal=r.top3_goal_hit-b.top3_goal_hit>=-.03,stock_dd=r.top3_stock_dd-b.top3_stock_dd>=-.03,portfolio_xirr=p.xirr_delta>=-.03,portfolio_dd=p.drawdown_delta>=-.03,support=p.matched_dates>=8 and r.supported_top3_dates>=8)
        decisions.append(dict(model=name,weight=w,qualifies=all(checks.values()),checks=checks))
    passed=[d for d in decisions if d['qualifies']];winner=max(passed,key=lambda d:d['weight'])['model'] if passed else None
    table.to_csv(OUT/'summary.csv')
    ledger=ROOT/'research/research_variant_ledger.csv';reg=pd.read_csv(ledger);old=set(reg.id)
    added=[dict(id='high_recency_tilt_20261101::'+n,family='high_recency_tilt_20261101',name=n,source='research/protocols/high_recency_tilt_20261101.md',category='configuration') for n in WEIGHTS if 'high_recency_tilt_20261101::'+n not in old]
    reg=pd.concat([reg,pd.DataFrame(added)],ignore_index=True);reg.to_csv(ledger,index=False)
    tests=dict(development_only=x.decision_date.lt('2024-01-01').all(),four_candidates=len(WEIGHTS)==4,blend_endpoints=blend(.3,.8,0)==.3 and blend(.3,.8,1)==.8,direction=blend(.5,.9,.35)>blend(.5,.1,.35),bounded=all(x[n].between(0,1).all() for n in names),unique_rows=not x.duplicated(['decision_date','isin']).any(),ledger_preserved=old.issubset(set(reg.id)))
    assert all(tests.values())
    current_info=None
    if winner:
        z=pd.read_pickle(ROOT/'experiments/professor-weight-curve-20261031/scored.pkl.gz',compression='gzip')
        latest=z.decision_date.max();z=z[z.decision_date.eq(latest)&z.factor_eligible].copy()
        z['preference_score']=blend(z.champion_percentile,z.q_high_recency,WEIGHTS[winner])
        z=z.sort_values(['sector','preference_score','isin'],ascending=[True,False,True]);z['preference_rank']=z.groupby('sector').cumcount()+1
        z['champion_rank']=z.groupby('sector').champion_percentile.rank(method='first',ascending=False)
        z['days_since_high']=-z.high_recency
        cols=['isin','decision_date','sector','champion_rank','preference_rank','champion_percentile','q_high_recency','days_since_high','preference_score']
        dest=ROOT.parent.parent/'Documents/Codex/2026-10-31/you/outputs/high_recency_preference_ranking_20261101.csv'
        dest.parent.mkdir(parents=True,exist_ok=True);z[cols].to_csv(dest,index=False)
        changes=[]
        for s,g in z.groupby('sector'):
            one=set(g.loc[g.champion_rank.le(3),'isin']);two=set(g.loc[g.preference_rank.le(3),'isin']);changes.append((one!=two,len(one&two)/3))
        current_info=dict(snapshot=latest,eligible=len(z),sectors=len(changes),changed_sectors=sum(t[0] for t in changes),average_top3_overlap=np.mean([t[1] for t in changes]),file=str(dest),sha256=hashlib.sha256(dest.read_bytes()).hexdigest())
    save('decision.json',dict(selected=winner,candidates=decisions,checks=tests,current=current_info,documented_attempts=len(reg),exposed_evaluated=False,default_champion_changed=False))
    print(json.dumps(dict(selected=winner,decisions=decisions,current=current_info),default=lambda v:v.item() if hasattr(v,'item') else str(v)),flush=True)
if __name__=='__main__':main()
