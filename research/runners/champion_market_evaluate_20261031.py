"""Matched ranking, goal, risk and product scorecard without model selection leakage."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','3')
from pathlib import Path
import json,math,argparse,gc,time
import numpy as np,pandas as pd
from scipy.stats import rankdata,kendalltau
import champion_market_common_20261031 as c
TOP=[3,10,20]

def pair_accuracy(y,s):
 n=len(y);total=n*(n-1)/2
 if total==0:return np.nan
 cy=np.unique(y,return_counts=True)[1];ty=np.sum(cy*(cy-1)/2);cs=np.unique(s,return_counts=True)[1];ts=np.sum(cs*(cs-1)/2)
 if total==ty:return np.nan
 if total==ts:return .5
 tau=kendalltau(y,s,method='asymptotic').statistic
 return float(.5+.5*tau*np.sqrt((total-ts)/(total-ty)))

def metrics(g,names):
 y=g.future_xirr.to_numpy(float);a=g[names].to_numpy(float);yr=rankdata(y);rank=rankdata(a,axis=0);center=rank-rank.mean(0);yc=yr-yr.mean();den=np.linalg.norm(center,axis=0)*np.linalg.norm(yc)
 ic=np.divide(yc@center,den,out=np.full(len(names),np.nan),where=den>0);order=np.argsort(-a,axis=0,kind='stable');relevance=yr/len(y);hit=g.goal_hit.to_numpy(float);dd=g.future_drawdown.to_numpy(float);short=g.future_shortfall.to_numpy(float)
 rows=[]
 for j,name in enumerate(names):
  r=dict(model=name,n=len(g),rank_ic=ic[j],pair_accuracy=pair_accuracy(y,a[:,j]),universe_hit=float(hit.mean()),universe_xirr=float(np.median(y)),universe_drawdown=float(dd.mean()))
  for k in TOP:
   if len(g)<k:r.update({f'{m}{k}':np.nan for m in ['attainment','xirr','drawdown','shortfall','ndcg','negative','tail10']});continue
   ids=order[:k,j];discount=1/np.log2(np.arange(k)+2);ideal=np.dot(np.sort(relevance)[-k:][::-1],discount)
   r.update({f'attainment{k}':float(hit[ids].mean()),f'xirr{k}':float(np.median(y[ids])),f'drawdown{k}':float(dd[ids].mean()),f'shortfall{k}':float(short[ids].mean()),f'ndcg{k}':float(np.dot(relevance[ids],discount)/ideal),f'negative{k}':float((y[ids]<0).mean()),f'tail10{k}':float(np.sort(y[ids])[:max(1,int(np.ceil(.1*k)))].mean())})
  rows.append(r)
 return rows

def assemble(tier='full'):
 x=pd.read_pickle(c.OUT/'valid_panel.pkl.gz',compression='gzip');x=x[x.decision_date.ge('2020-01-01')].copy();registry=json.loads((c.OUT/'score_registry.json').read_text());names=[c.ANCHOR]+registry['factors']+registry['controls']+registry['prior_policies'];names=list(dict.fromkeys(names))
 if tier=='sequence':
  keys=pd.read_csv(c.old.OUT/'kronos_input_keys.csv');x=x.merge(keys,on=['isin','decision_date'],how='inner',validate='many_to_one');folder=c.OUT/'sequence';new=['gru','alstm','transformer','gats','hist','master','matched_ridge','matched_lightgbm'];suffix='balanced'
  for name in new:
   paths=[folder/f'{name}__balanced__{y}.csv.gz' for y in range(2020,2026)]
   if not all(p.exists() for p in paths):raise RuntimeError('Incomplete sequence family '+name)
   z=pd.concat([pd.read_csv(p,usecols=c.KEYS+['score']) for p in paths]);col='sequence__'+name;x=x.merge(z.rename(columns={'score':col}),on=c.KEYS,how='left',validate='one_to_one');names.append(col)
 else:
  for name in json.loads((c.OUT/'protocol.json').read_text())['ml_algorithms']:
   for target in ['return','balanced']:
    paths=[c.OUT/'tabular'/f'{name}__{target}__{y}.csv.gz' for y in range(2020,2026)]
    if not all(p.exists() for p in paths):raise RuntimeError('Incomplete tabular family '+name+' '+target)
    z=pd.concat([pd.read_csv(p,usecols=c.KEYS+['score']) for p in paths]);col='ml__'+name+'__'+target;x=x.merge(z.rename(columns={'score':col}),on=c.KEYS,how='left',validate='one_to_one');names.append(col)
 for name in names:
  if not np.isfinite(x[name]).all():raise ValueError('Missing prediction support '+name)
 x=x.sort_values('isin').reset_index(drop=True);c.save(f'{tier}/evaluation_support.json',dict(rows=len(x),dates=x.decision_date.nunique(),models=names,complete_case='Matched finite guarded-label retrospective support, not exante investability or survivorship-free certification'))
 return x,names

def evaluate(tier):
 folder=c.OUT/tier;folder.mkdir(exist_ok=True);x,names=assemble(tier);x.to_pickle(folder/'scored_panel.pkl.gz',compression='gzip');rows=[]
 # Calculate development first and persist the selection before touching exposed metrics.
 for key,g in x[x.decision_date.lt('2024-01-01')].groupby(c.GROUP,observed=True,sort=True):
  for r in metrics(g,names):r.update(dict(zip(c.GROUP,key)));rows.append(r)
 q=pd.DataFrame(rows);q.to_csv(folder/'sector_queries.csv.gz',index=False);del rows;gc.collect()
 q['period']=np.where(q.decision_date.lt('2024-01-01'),'development','exposed');columns=['rank_ic','pair_accuracy','universe_hit']+[m+str(k) for k in TOP for m in ['attainment','xirr','drawdown','shortfall','ndcg','negative','tail10']]
 summary=q.groupby(['period','model','decision_date'])[columns].mean().groupby(['period','model']).mean().reset_index();summary.to_csv(folder/'sector_summary.csv',index=False)
 # Selection uses development only, then is written before exposed diagnostics.
 dev=q[q.period.eq('development')];wide={metric:dev.pivot(index=c.GROUP,columns='model',values=metric).dropna(axis=1,how='all').dropna() for metric in ['rank_ic','attainment3','drawdown3']};deltas={k:v.subtract(v[c.ANCHOR],axis=0).groupby('decision_date').mean().mean().reindex(names) for k,v in wide.items()}
 decisions=[]
 for name in names:
  if name==c.ANCHOR:continue
  values={m:float(v[name]) for m,v in deltas.items()};gate=(values['drawdown3']>=-1e-12 and values['rank_ic']>=-1e-12 and values['attainment3']>=-1e-12 and (values['rank_ic']>=.01013492400721767 or values['attainment3']>=.0063048666044885245));decisions.append(dict(model=name,development_point_gate=gate,**values))
 table=pd.DataFrame(decisions).sort_values(['development_point_gate','attainment3','rank_ic','model'],ascending=[False,False,False,True]);winner=table.loc[table.development_point_gate,'model'].iloc[0] if table.development_point_gate.any() else c.ANCHOR
 c.save(f'{tier}/development_lock.json',dict(selected=winner,point_gate_candidates=table[table.development_point_gate].to_dict('records'),selection='Attainment thenIC among development-gate passers; current35policy variants previously searched; final pass additionally requires new familywise temporal bound and locked exposed gate',exposed_not_used_for_selection=True));table.to_csv(folder/'development_deltas.csv',index=False)
 exposedrows=[]
 for key,g in x[x.decision_date.ge('2024-01-01')].groupby(c.GROUP,observed=True,sort=True):
  for r in metrics(g,names):r.update(dict(zip(c.GROUP,key)));exposedrows.append(r)
 e=pd.DataFrame(exposedrows);e['period']='exposed';q=pd.concat([q,e],ignore_index=True);q.to_csv(folder/'sector_queries.csv.gz',index=False)
 q.groupby(['period','model','decision_date'])[columns].mean().groupby(['period','model']).mean().reset_index().to_csv(folder/'sector_summary.csv',index=False)
 globalrows=[]
 for key,g in x.groupby(['decision_date','profile_name'],observed=True,sort=True):
  for r in metrics(g,names):r.update(dict(zip(['decision_date','profile_name'],key)));globalrows.append(r)
 globalq=pd.DataFrame(globalrows);globalq.to_csv(folder/'global_queries.csv.gz',index=False);globalq['period']=np.where(globalq.decision_date.lt('2024-01-01'),'development','exposed');globalq.groupby(['period','model'])[columns].mean().reset_index().to_csv(folder/'global_summary.csv',index=False)
 for dim in ['profile_name','sector']:
  q.groupby(['period',dim,'model'])[columns].mean().reset_index().to_csv(folder/(dim+'_slices.csv'),index=False)
 q.assign(year=q.decision_date.str[:4]).groupby(['year','model'])[columns].mean().reset_index().to_csv(folder/'year_slices.csv',index=False)
 # Date-level ranking strength is descriptive ICIR, not annualized Sharpe.
 ic=q.groupby(['period','model','decision_date']).rank_ic.mean().groupby(['period','model']).agg(mean='mean',sd='std',dates='size');ic['icir']=ic['mean']/ic.sd.where(ic.sd.gt(0));ic.to_csv(folder/'icir.csv')
 print('EVALUATED',tier,len(names),len(q),winner,flush=True)

if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('tier',choices=['full','sequence']);a=p.parse_args();evaluate(a.tier)
