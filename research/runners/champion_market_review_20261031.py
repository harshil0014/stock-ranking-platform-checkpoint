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
   querykeys=[k for k in c.GROUP if k in sub.columns];a=sub.pivot(index=querykeys,columns='model',values=metric);delta=a.subtract(a[c.ANCHOR],axis=0).groupby('decision_date').mean().sort_index().drop(columns=c.ANCHOR).dropna(axis=1,how='all').dropna(axis=0,how='any');dates=delta.index;mean=delta.mean().to_numpy();center=delta.to_numpy()-mean;names=list(delta.columns)
   for span in [365,730]:
    observed=(np.asarray(dates,dtype='datetime64[D]')[-1]-np.asarray(dates,dtype='datetime64[D]')[0]).astype(int)
    if len(dates)<4 or observed<span:
     for i,name in enumerate(names):rows.append(dict(period=period,metric=metric,block_days=span,model=name,delta=mean[i],familywise_noise_floor=np.nan,simultaneous_lower95=np.nan,joint_primary_noise_floor=np.nan,joint_primary_lower95=np.nan,pointwise_low95=np.nan,pointwise_high95=np.nan,dates=len(dates),candidates=len(names),status='INSUFFICIENT_TEMPORAL_SPAN'))
     continue
    rng=np.random.default_rng(20261031+span);boot=np.array([center[block_indices(dates,span,rng)].mean(0) for _ in range(4000)]);hurdle=float(np.quantile(np.max(boot,axis=1),.95));lower=mean-hurdle;joint=float(np.quantile(np.max(boot,axis=1),.975)) if metric in ['rank_ic','attainment3'] else hurdle
    for i,name in enumerate(names):rows.append(dict(period=period,metric=metric,block_days=span,model=name,delta=mean[i],familywise_noise_floor=hurdle,simultaneous_lower95=lower[i],joint_primary_noise_floor=joint,joint_primary_lower95=mean[i]-joint,pointwise_low95=float(mean[i]-np.quantile(boot[:,i],.975)),pointwise_high95=float(mean[i]-np.quantile(boot[:,i],.025)),dates=len(dates),candidates=len(names),status='CONDITIONAL_AVAILABLE'))
 pd.DataFrame(rows).to_csv(folder/'familywise_bounds.csv',index=False)
 lock=json.loads((folder/'development_lock.json').read_text());selected=lock['selected'];bounds=pd.DataFrame(rows);passed=False
 if selected!=c.ANCHOR:
  z=bounds[bounds.model.eq(selected)];dev=z[z.period.eq('development')];ex=z[z.period.eq('exposed')];significant=any((dev[dev.metric.eq(m)].joint_primary_lower95>0).all() for m in ['rank_ic','attainment3']);passed=bool(significant and ex.delta.ge(-1e-12).all())
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
     oldall=old[names].to_numpy(float);newall=h[names].to_numpy(float);oi=np.argsort(-oldall,axis=0,kind='stable')[:3];ni=np.argsort(-newall,axis=0,kind='stable')[:3];oa=old.loc[common,names].to_numpy(float);na=h.loc[common,names].to_numpy(float);oid=old.index.to_numpy();nid=h.index.to_numpy()
     for j,name in enumerate(names):
      a=set(oid[oi[:,j]]);b=set(nid[ni[:,j]])
      rows.append(dict(model=name,profile_name=profile,sector=sector,decision_date=date,previous_date=olddate,top3_churn=1-len(a&b)/3,kendall_tau=kendalltau(oa[:,j],na[:,j]).statistic,common_stocks=len(common)))
   previous=(date,h)
 s=pd.DataFrame(rows);s.to_csv(folder/'stability_queries.csv.gz',index=False);s['period']=np.where(s.decision_date.lt('2024-01-01'),'development','exposed');s.groupby(['period','model'])[['top3_churn','kendall_tau']].mean().reset_index().to_csv(folder/'stability_summary.csv',index=False)

def binary_labels(values):
 y=pd.to_numeric(values,errors='raise').to_numpy(dtype=float)
 if not np.isfinite(y).all() or not np.isin(y,[0,1]).all():raise ValueError('Calibration requires finite binary goal labels')
 return y.astype('int32')

def calibration(x,names,folder):
 # Unseen-date predictions only; prequential fits may use previously matured exposed dates.
 rows=[];audit=[]
 for profile,g in x.groupby('profile_name',observed=True):
  for date,test in g.groupby('decision_date',sort=True):
   train=g[g.endpoint.lt(date)]
   if train.decision_date.nunique()<2 or train.goal_hit.nunique()<2:continue
   assert train.endpoint.max()<date
   w=(1/train.groupby('decision_date')['isin'].transform('size')).to_numpy(copy=True);w/=w.mean();train_y=binary_labels(train.goal_hit);base=float(np.average(train_y,weights=w));y=binary_labels(test.goal_hit)
   audit.append(dict(profile=profile,date=date,max_training_endpoint=train.endpoint.max(),oof_dates=train.decision_date.nunique(),rows=len(train),climatology=base))
   for name in names:
    a=train[name].to_numpy(float);mean=a.mean();sd=max(a.std(),1e-8);model=LogisticRegression(C=.1,max_iter=200);model.fit(((a-mean)/sd).reshape(-1,1),train_y,sample_weight=w);p=model.predict_proba(((test[name].to_numpy(float)-mean)/sd).reshape(-1,1))[:,1];bins=np.minimum((p*10).astype(int),9);ece=sum(abs(y[bins==b].mean()-p[bins==b].mean())*(bins==b).mean() for b in np.unique(bins))
    rows.append(dict(model=name,profile_name=profile,decision_date=date,brier=brier_score_loss(y,p),climatology_brier=brier_score_loss(y,np.full(len(y),base)),logloss=log_loss(y,p,labels=[0,1]),ece10=ece,n=len(y),slope=float(model.coef_[0,0])))
 z=pd.DataFrame(rows);z.to_csv(folder/'calibration_queries.csv.gz',index=False);c.save(str(folder.relative_to(c.OUT)/'calibration_maturity_audit.json'),audit)
 if len(z):
  z['period']=np.where(z.decision_date.lt('2024-01-01'),'development','exposed');z.groupby(['period','model'])[['brier','climatology_brier','logloss','ece10']].mean().reset_index().to_csv(folder/'calibration_summary.csv',index=False)

def feature_only_stability_panel(tier,names):
 source='panel.pkl.gz' if tier=='full' else 'sequence_panel.pkl.gz';z=pd.read_pickle(c.OUT/source,compression='gzip');z=z[z.decision_date.ge('2020-01-01')].copy()
 for name in names:
  if name.startswith('ml__'):
   _,algorithm,target=name.split('__');files=[c.OUT/'inference'/f'{algorithm}__{target}__{year}.csv.gz' for year in range(2020,2026)]
  elif name.startswith('sequence__'):
   algorithm=name.split('__')[1];files=[c.OUT/'sequence'/f'{algorithm}__balanced__{year}.csv.gz' for year in range(2020,2026)]
  elif name.startswith('ensemble__'):continue
  else:continue
  pred=pd.concat([pd.read_csv(p,usecols=c.KEYS+['score']) for p in files]);z=z.merge(pred.rename(columns={'score':name}),on=c.KEYS,how='left',validate='one_to_one')
 from champion_market_evaluate_20261031 import add_ensembles
 add_ensembles(z,tier)
 for name in names:
  if not np.isfinite(z[name]).all():raise ValueError('Incomplete feature-only stability '+name)
 return z

def personalization(x,names,folder):
 rows=[]
 for date,g in x.groupby('decision_date',sort=True):
  base=g[g.profile_name.eq('base7500')].set_index('isin')
  for profile in ['target10','target30','amount1000','amount50000','weekly','quarterly','lookback12','lookback60']:
   other=g[g.profile_name.eq(profile)].set_index('isin');common=base.index.intersection(other.index)
   if len(common)<5:continue
   for name in names:
    a=base.loc[common,name];b=other.loc[common,name];rows.append(dict(decision_date=date,profile=profile,model=name,common_stocks=len(common),kendall_tau=kendalltau(a,b).statistic,top20_overlap=len(set(a.nlargest(20).index)&set(b.nlargest(20).index))/min(20,len(common)),mean_absolute_percentile_change=float((a.rank(pct=True)-b.rank(pct=True)).abs().mean())))
 z=pd.DataFrame(rows);z.to_csv(folder/'personalization_queries.csv.gz',index=False);z.groupby(['profile','model'])[['kendall_tau','top20_overlap','mean_absolute_percentile_change']].mean().reset_index().to_csv(folder/'personalization_summary.csv',index=False)

def confidence_curve(full,valid,tier,folder):
 from champion_market_evaluate_20261031 import metrics
 if tier=='full':
  algorithms=json.loads((c.OUT/'protocol.json').read_text())['ml_algorithms'];cols=[f'ml__{n}__{target}' for n in algorithms for target in ['return','balanced']];ranks=full[cols].groupby([full[k] for k in c.GROUP],observed=True).rank(pct=True);votes=np.column_stack([ranks[[f'ml__{n}__return',f'ml__{n}__balanced']].mean(axis=1).to_numpy() for n in algorithms]);scores=[c.ANCHOR,'ensemble__return','ensemble__balanced']
 else:
  cols=[f'sequence__{n}' for n in ['gru','alstm','transformer','gats','hist','master']];votes=full[cols].groupby([full[k] for k in c.GROUP],observed=True).rank(pct=True).to_numpy();scores=[c.ANCHOR,'ensemble__neural']
 conf=full[c.KEYS].copy();conf['disagreement']=np.std(votes,axis=1);z=valid.merge(conf,on=c.KEYS,validate='one_to_one');rows=[]
 for key,g in z.groupby(c.GROUP,observed=True,sort=True):
  if len(g)<5:continue
  ordered=g.sort_values(['disagreement','isin'],kind='stable')
  for fraction in [.25,.5,.75,1.]:
   h=ordered.iloc[:max(1,int(np.ceil(len(g)*fraction)))];
   if len(h)<5:continue
   for result in metrics(h,scores):result.update(dict(zip(c.GROUP,key)));result.update(retained_fraction=fraction,eligible_stocks=len(g),mean_disagreement=float(h.disagreement.mean()));rows.append(result)
 z=pd.DataFrame(rows);z['period']=np.where(z.decision_date.lt('2024-01-01'),'development','exposed');z.groupby(['period','retained_fraction','model']).agg(pair_accuracy=('pair_accuracy','mean'),rank_ic=('rank_ic','mean'),attainment3=('attainment3','mean'),drawdown3=('drawdown3','mean'),queries=('n','size'),retained_stocks=('n','sum'),eligible_stocks=('eligible_stocks','sum')).reset_index().to_csv(folder/'confidence_abstention_curve.csv',index=False)

def coverage_challenge(full,names,folder):
 from champion_market_evaluate_20261031 import metrics
 finite=full.evidence_fraction.gt(0)&np.isfinite(full.future_xirr)&np.isfinite(full.future_drawdown)&np.isfinite(full.future_shortfall);z=full[finite].copy();counts=z.groupby(c.GROUP,observed=True)['isin'].transform('size');z['coverage_group']=np.where(z.sector.eq('Unclassified'),'unclassified',np.where(counts.lt(5),'classified_fewer_than5','classified_at_least5'));rows=[]
 for key,g in z.groupby(['decision_date','profile_name','coverage_group'],observed=True,sort=True):
  if len(g)<5:continue
  for result in metrics(g,names):result.update(dict(zip(['decision_date','profile_name','coverage_group'],key)));rows.append(result)
 result=pd.DataFrame(rows);result['period']=np.where(result.decision_date.lt('2024-01-01'),'development','exposed');result.groupby(['period','coverage_group','model']).agg(rank_ic=('rank_ic','mean'),pair_accuracy=('pair_accuracy','mean'),attainment3=('attainment3','mean'),drawdown3=('drawdown3','mean'),rows=('n','sum'),queries=('n','size')).reset_index().to_csv(folder/'coverage_challenge.csv',index=False)
 c.save(str(folder.relative_to(c.OUT)/'feature_coverage_counts.json'),dict(full_feature_rows=len(full),full_feature_issuers=full['isin'].nunique(),finite_guarded_outcome_rows=int(finite.sum()),groups=z.groupby('coverage_group',observed=True).size().to_dict(),unknown_or_tiny_sector_diagnostic='Pooled across coverage group within date/profile; supplementary cross-sectional diagnostic, not validated within-sector rank or primary promotion evidence'))

def main(tier,resume=False):
 folder=c.OUT/tier;x=pd.read_pickle(folder/'scored_panel.pkl.gz',compression='gzip');names=json.loads((folder/'evaluation_support.json').read_text())['models'];q=pd.read_csv(folder/'sector_queries.csv.gz');q['period']=np.where(q.decision_date.lt('2024-01-01'),'development','exposed')
 if not(resume and all((folder/f).exists() for f in ['familywise_bounds.csv','decision.json'])):familywise(q,folder)
 print('BOUNDS',tier,flush=True)
 completed=['stability_summary.csv','personalization_summary.csv','confidence_abstention_curve.csv','coverage_challenge.csv','feature_coverage_counts.json']
 if not(resume and all((folder/f).exists() for f in completed)):
  full=feature_only_stability_panel(tier,names);stability(full,names,folder);personalization(full,names,folder);confidence_curve(full,x,tier,folder);coverage_challenge(full,names,folder);del full
 print('STABILITY',tier,flush=True);calibration(x,names,folder);print('CALIBRATION',tier,flush=True)
 regime_slices(x,q,names,folder)
 # Liquidity is a past-price/volume proxy; regimes use trailing broad-index returns only.
 if 'log_dollar_volume' in x:liquidity='log_dollar_volume'
 else:liquidity=next((n for n in x if 'liquid' in n or 'turnover' in n),None)
 c.save(str(folder.relative_to(c.OUT)/'coverage.json'),dict(stocks=x['isin'].nunique(),dates=x.decision_date.nunique(),profiles=x.profile_name.nunique(),sectors=x.sector.nunique(),rows=len(x),liquidity_column=liquidity,scope='Current-survivor finite guarded labels; price/volume does not establish actual market impact or PIT market cap; daily production refresh still not certified'))

def regime_slices(x,q,names,folder):
 from champion_market_evaluate_20261031 import metrics
 idx=pd.read_csv(c.OUT/'NIFTY_500_TRI.csv');idx['date']=pd.to_datetime(idx.Date,format='%d %b %Y');idx=idx.sort_values('date');idx['past_return252']=pd.to_numeric(idx.TotalReturnsIndex).pct_change(252);regimes=[]
 for day in sorted(x.decision_date.unique()):
  past=idx[idx.date.le(day)].iloc[-1];v=float(past.past_return252);regimes.append(dict(decision_date=day,regime='bear_trailing12m' if v<-.1 else ('bull_trailing12m' if v>.1 else 'flat_trailing12m'),trailing_index_return=v,latest_input_date=str(past.date.date())))
 r=pd.DataFrame(regimes);r.to_csv(folder/'regime_definitions.csv',index=False);z=q.merge(r,on='decision_date',validate='many_to_one');z.groupby(['period','regime','model'])[['rank_ic','pair_accuracy','attainment3','drawdown3']].mean().reset_index().to_csv(folder/'regime_slices.csv',index=False)
 # Thin trading is observable from past zero-return days; no fabricated PIT market caps.
 x=x.copy();rank=x.groupby(['decision_date','profile_name'],observed=True).zero_fraction.rank(pct=True);x['trading_activity']=np.where(rank.le(1/3),'most_active_proxy',np.where(rank.le(2/3),'middle_proxy','least_active_proxy'));rows=[]
 for key,g in x.groupby(['decision_date','profile_name','trading_activity'],observed=True,sort=True):
  if len(g)<5:continue
  for result in metrics(g,names):result.update(dict(zip(['decision_date','profile_name','trading_activity'],key)));rows.append(result)
 z=pd.DataFrame(rows);z['period']=np.where(z.decision_date.lt('2024-01-01'),'development','exposed');z.groupby(['period','trading_activity','model'])[['rank_ic','pair_accuracy','attainment3','drawdown3']].mean().reset_index().to_csv(folder/'trading_activity_slices.csv',index=False)
 if 'log_dollar_volume' in x:
  rank=x.groupby(['decision_date','profile_name'],observed=True).log_dollar_volume.rank(pct=True);x['liquidity_proxy']=np.where(rank.isna(),'missing_volume',np.where(rank.le(1/3),'low_turnover',np.where(rank.le(2/3),'middle_turnover','high_turnover')));rows=[]
  for key,g in x.groupby(['decision_date','profile_name','liquidity_proxy'],observed=True,sort=True):
   if len(g)<5:continue
   for result in metrics(g,names):result.update(dict(zip(['decision_date','profile_name','liquidity_proxy'],key)));rows.append(result)
  z=pd.DataFrame(rows);z['period']=np.where(z.decision_date.lt('2024-01-01'),'development','exposed');z.groupby(['period','liquidity_proxy','model'])[['rank_ic','pair_accuracy','attainment3','drawdown3']].mean().reset_index().to_csv(folder/'liquidity_slices.csv',index=False)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('tier',choices=['full','sequence']);p.add_argument('--resume',action='store_true');args=p.parse_args();main(args.tier,args.resume)
