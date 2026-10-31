"""Temporal familywise uncertainty, stability, coverage and mature-only calibration."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','3')
import json,argparse
import numpy as np,pandas as pd
from scipy.stats import kendalltau
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss,log_loss
import champion_market_common_20261031 as c

def block_indices(dates,span,rng):
 dates=np.asarray(dates,dtype='datetime64[D]');n=len(dates);out=[];days=(dates-dates[0]).astype(int);cycle=int(days[-1]+np.median(np.diff(days)))
 while len(out)<n:
  start=int(rng.integers(n));ordered=(np.arange(n)+start)%n;block=ordered[((days[ordered]-days[start])%cycle)<span]
  out.extend(block.tolist())
 return np.asarray(out[:n])

def familywise(q,folder):
 rows=[]
 for period in ['development','exposed']:
  sub=q[q.period.eq(period)]
  for metric in ['rank_ic','attainment3','drawdown3']:
   a=sub.groupby(['decision_date','model'])[metric].mean().unstack().sort_index();delta=a.subtract(a[c.ANCHOR],axis=0).drop(columns=c.ANCHOR);mean=delta.mean().to_numpy();center=delta.to_numpy()-mean;names=list(delta.columns)
   for span in [365,730]:
    rng=np.random.default_rng(20261031+span);boot=np.array([center[block_indices(a.index,span,rng)].mean(0) for _ in range(4000)]);hurdle=float(np.quantile(np.max(boot,axis=1),.95));lower=mean-hurdle
    for i,name in enumerate(names):rows.append(dict(period=period,metric=metric,block_days=span,model=name,delta=mean[i],familywise_noise_floor=hurdle,simultaneous_lower95=lower[i],pointwise_low95=float(mean[i]-np.quantile(boot[:,i],.975)),pointwise_high95=float(mean[i]-np.quantile(boot[:,i],.025)),dates=len(a),candidates=len(names)))
 pd.DataFrame(rows).to_csv(folder/'familywise_bounds.csv',index=False)
 lock=json.loads((folder/'development_lock.json').read_text());selected=lock['selected'];bounds=pd.DataFrame(rows);passed=False
 if selected!=c.ANCHOR:
  z=bounds[bounds.model.eq(selected)];dev=z[z.period.eq('development')];ex=z[z.period.eq('exposed')];significant=any((dev[dev.metric.eq(m)].simultaneous_lower95>0).all() for m in ['rank_ic','attainment3']);passed=bool(significant and ex.delta.ge(-1e-12).all())
 c.save(str(folder.relative_to(c.OUT)/'decision.json'),dict(selected_by_development=selected,passes_familywise_and_exposed=passed,serving_champion=c.ANCHOR,production_promoted=False,reason='Retrospective research only; even a statistical pass requires prospective and PIT validation',bootstrap='Centered paired date differences; moving date blocks sampled with replacement; simultaneous maximum across all candidates in tier; 4000 resamples; 365 and730days',exposed='Previously exposed historical period, not fresh holdout'))

def stability(x,names,folder):
 rows=[]
 for (profile,sector),g in x.groupby(['profile_name','sector'],observed=True):
  previous=None
  for date,h in g.groupby('decision_date',sort=True):
   h=h.set_index('isin')
   if previous is not None:
    olddate,old=previous;common=old.index.intersection(h.index)
    if len(common)>=5:
     for name in names:
      a=set(old[name].nlargest(3).index);b=set(h[name].nlargest(3).index)
      rows.append(dict(model=name,profile_name=profile,sector=sector,decision_date=date,previous_date=olddate,top3_churn=1-len(a&b)/3,kendall_tau=kendalltau(old.loc[common,name],h.loc[common,name]).statistic,common_stocks=len(common)))
   previous=(date,h)
 s=pd.DataFrame(rows);s.to_csv(folder/'stability_queries.csv.gz',index=False);s['period']=np.where(s.decision_date.lt('2024-01-01'),'development','exposed');s.groupby(['period','model'])[['top3_churn','kendall_tau']].mean().reset_index().to_csv(folder/'stability_summary.csv',index=False)

def calibration(x,names,folder):
 # Unseen-date predictions only; prequential fits may use previously matured exposed dates.
 rows=[];audit=[]
 for profile,g in x.groupby('profile_name',observed=True):
  for date,test in g.groupby('decision_date',sort=True):
   train=g[g.endpoint.lt(date)]
   if train.decision_date.nunique()<2 or train.goal_hit.nunique()<2:continue
   assert train.endpoint.max()<date
   w=(1/train.groupby('decision_date')['isin'].transform('size')).to_numpy(copy=True);w/=w.mean();base=float(np.average(train.goal_hit,weights=w));y=test.goal_hit.to_numpy(float)
   audit.append(dict(profile=profile,date=date,max_training_endpoint=train.endpoint.max(),oof_dates=train.decision_date.nunique(),rows=len(train),climatology=base))
   for name in names:
    a=train[name].to_numpy(float);mean=a.mean();sd=max(a.std(),1e-8);model=LogisticRegression(C=.1,max_iter=200);model.fit(((a-mean)/sd).reshape(-1,1),train.goal_hit,sample_weight=w);p=model.predict_proba(((test[name].to_numpy(float)-mean)/sd).reshape(-1,1))[:,1];bins=np.minimum((p*10).astype(int),9);ece=sum(abs(y[bins==b].mean()-p[bins==b].mean())*(bins==b).mean() for b in np.unique(bins))
    rows.append(dict(model=name,profile_name=profile,decision_date=date,brier=brier_score_loss(y,p),climatology_brier=brier_score_loss(y,np.full(len(y),base)),logloss=log_loss(y,p,labels=[0,1]),ece10=ece,n=len(y),slope=float(model.coef_[0,0])))
 z=pd.DataFrame(rows);z.to_csv(folder/'calibration_queries.csv.gz',index=False);c.save(str(folder.relative_to(c.OUT)/'calibration_maturity_audit.json'),audit)
 if len(z):
  z['period']=np.where(z.decision_date.lt('2024-01-01'),'development','exposed');z.groupby(['period','model'])[['brier','climatology_brier','logloss','ece10']].mean().reset_index().to_csv(folder/'calibration_summary.csv',index=False)

def main(tier):
 folder=c.OUT/tier;x=pd.read_pickle(folder/'scored_panel.pkl.gz',compression='gzip');names=json.loads((folder/'evaluation_support.json').read_text())['models'];q=pd.read_csv(folder/'sector_queries.csv.gz');q['period']=np.where(q.decision_date.lt('2024-01-01'),'development','exposed');familywise(q,folder);print('BOUNDS',tier,flush=True)
 stability(x,names,folder);print('STABILITY',tier,flush=True);calibration(x,names,folder);print('CALIBRATION',tier,flush=True)
 # Liquidity is a past-price/volume proxy; regimes use trailing broad-index returns only.
 if 'median_dollar_volume63' in x:liquidity='median_dollar_volume63'
 else:liquidity=next((n for n in x if 'liquid' in n or 'turnover' in n),None)
 c.save(str(folder.relative_to(c.OUT)/'coverage.json'),dict(stocks=x['isin'].nunique(),dates=x.decision_date.nunique(),profiles=x.profile_name.nunique(),sectors=x.sector.nunique(),rows=len(x),liquidity_column=liquidity,scope='Current-survivor finite guarded labels; price/volume does not establish actual market impact or PIT market cap; daily production refresh still not certified'))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('tier',choices=['full','sequence']);main(p.parse_args().tier)
