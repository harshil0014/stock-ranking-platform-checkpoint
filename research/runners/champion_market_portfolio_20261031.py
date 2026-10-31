"""Complete-feature selections and actual fractional SIP cashflows on recovered paths.

This is a provider-adjusted-price research proxy, not a certified executable fund NAV.
Missing selected paths or unresolved actions invalidate the entire portfolio observation.
"""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','3')
from pathlib import Path
import json,pickle,gc,argparse
import numpy as np,pandas as pd
import champion_market_common_20261031 as c
from champion_market_indices_20261031 import xirr

def price_cache():
 dest=c.ROOT/'work/champion-vs-market-20261031/adjusted_paths.pkl'
 if dest.exists():
  with dest.open('rb') as f:cached=pickle.load(f)
  if cached:return cached
 root=c.ROOT/'experiments/current-data-recovery-20261003/yahoo-full-recovery-v1';mapping=pd.read_csv(root/'yahoo_symbol_map.csv').dropna(subset=['isin','yahoo_symbol']);lookup=dict(zip(mapping.yahoo_symbol,mapping['isin']));result={}
 for path in sorted((root/'history-cache').glob('batch_*.pkl')):
  with path.open('rb') as f:batch=pickle.load(f)
  for symbol,frame in batch['frames'].items():
   if symbol not in lookup or not isinstance(frame,pd.DataFrame) or 'Adj Close' not in frame:continue
   s=frame['Adj Close'].dropna();s=s[~s.index.duplicated(keep='last')].sort_index();s=s[s.gt(0)]
   if len(s):result[lookup[symbol]]=(s.index.tz_localize(None).to_numpy(dtype='datetime64[D]'),s.to_numpy(float))
  del batch;gc.collect()
 if not result:raise ValueError('No recovered adjusted paths; refusing an empty cache')
 with dest.open('wb') as f:pickle.dump(result,f,protocol=5)
 print('CACHED PATHS',len(result),flush=True);return result

def portfolio_path(paths,weights,start,end,amount,interval,cost_bps):
 start=np.datetime64(start,'D');end=np.datetime64(end,'D');schedule=np.arange(start,end,np.timedelta64(interval,'D'));calendar=np.unique(np.concatenate([ds[(ds>=start)&(ds<=end)] for ds,p in paths]));cost=cost_bps/10000
 if len(calendar)<20:raise ValueError('Insufficient portfolio daily calendar')
 wealth=np.zeros(len(calendar));flow=np.zeros(len(calendar));first_trade=[]
 for (ds,p),weight in zip(paths,weights):
  buy=np.searchsorted(ds,schedule);last=np.searchsorted(ds,end,side='right')-1
  if last<0 or (buy>last).any() or (buy>=len(ds)).any():raise ValueError('Selected stock missing contribution/terminal observation')
  if ((ds[buy]-schedule).astype(int)>7).any() or int((end-ds[last]).astype(int))>7:raise ValueError('Selected stock execution gap')
  obs=np.searchsorted(ds,calendar,side='right')-1
  if (obs<0).any() or ((calendar-ds[obs]).astype(int)>7).any():raise ValueError('Selected stock stale daily mark')
  units=amount*weight/(1+cost)/p[buy];loc=np.searchsorted(calendar,ds[buy]);dailyunits=np.zeros(len(calendar));np.add.at(dailyunits,loc,units);wealth+=np.cumsum(dailyunits)*p[obs];np.add.at(flow,loc,amount*weight);first_trade.append(int(loc.min()))
 wealth[-1]*=(1-cost);terminal=float(wealth[-1]);first=max(first_trade)
 # Start once all initial orders have executed; initial staggered cash is not treated as alpha.
 w=wealth[first:];f=flow[first:];ret=np.divide(w[1:]-f[1:],w[:-1],out=np.ones(len(w)-1),where=w[:-1]>0)-1;initial=wealth[first]/flow[:first+1].sum();nav=np.r_[initial,initial*np.cumprod(1+ret)];dd=nav/np.maximum.accumulate(np.r_[1.,nav])[1:]-1;vol=float(np.std(ret)*np.sqrt(252));avg=float(np.mean(ret)*252);down=float(np.sqrt(np.mean(np.minimum(ret,0)**2))*np.sqrt(252))
 return dict(xirr=xirr(np.r_[schedule,end],np.r_[np.full(len(schedule),-amount),terminal]),terminal=terminal,contributed=amount*len(schedule),tw_max_drawdown=float(dd.min()),tw_volatility=vol,tw_sharpe_rf0=avg/vol if vol>0 else np.nan,tw_sortino_rf0=avg/down if down>0 else np.nan,daily_cvar5=float(np.sort(ret)[:max(1,int(np.ceil(.05*len(ret))))].mean()),stocks=len(paths),initial_execution_days=int((calendar[first]-start).astype(int)),_daily_dates=calendar[first+1:],_daily_returns=ret)

def attribution(dates,returns,factors):
 z=pd.DataFrame(dict(Date=pd.to_datetime(dates),portfolio_return=returns)).merge(factors,on='Date',how='inner').dropna()
 if len(z)<100:return dict(factor_observations=len(z),factor_status='INSUFFICIENT_MATCHED_HISTORY')
 # IIMA source units are daily percent returns; portfolio returns are decimal.
 X=np.c_[np.ones(len(z)),z[['MF','SMB','HML','WML']].to_numpy(float)/100];y=z.portfolio_return.to_numpy()-z.RF.to_numpy(float)/100;coef=np.linalg.lstsq(X,y,rcond=None)[0];res=y-X@coef
 return dict(factor_observations=len(z),factor_status='DESCRIPTIVE_OLS_NOT_ALPHA_PROOF',factor_alpha_annual_arithmetic=float(coef[0]*252),factor_market_beta=float(coef[1]),factor_size_beta=float(coef[2]),factor_value_beta=float(coef[3]),factor_momentum_beta=float(coef[4]),factor_r2=float(1-res@res/np.sum((y-y.mean())**2)))

def selection(g,name,policy):
 g=g[g.evidence_fraction.gt(0)&g[name].notna()].sort_values('isin')
 if policy=='global_top20':
  z=g.nlargest(20,name);return z['isin'].tolist(),np.full(len(z),1/len(z))
 selected=[];weights=[];groups=[h for _,h in g.groupby('sector',observed=True) if len(h)>=5]
 for h in groups:
  z=h.nlargest(3,name);selected.extend(z['isin'].tolist());weights.extend([1/len(groups)/len(z)]*len(z))
 return selected,np.asarray(weights)

def main():
 x=pd.read_pickle(c.OUT/'panel.pkl.gz',compression='gzip');x=x[x.decision_date.ge('2020-01-01')&x.profile_name.eq('base7500')].copy();registry=json.loads((c.OUT/'score_registry.json').read_text());names=list(dict.fromkeys([c.ANCHOR]+registry['factors']+registry['controls']+registry['prior_policies']))
 for name in json.loads((c.OUT/'protocol.json').read_text())['ml_algorithms']:
  for target in ['return','balanced']:
   files=[c.OUT/'inference'/f'{name}__{target}__{year}.csv.gz' for year in range(2020,2026)]
   if not all(p.exists() for p in files):raise RuntimeError('Missing full feature inference '+name)
   z=pd.concat([pd.read_csv(p).query("profile_name == 'base7500'") for p in files]);col='ml__'+name+'__'+target;x=x.merge(z[c.KEYS+['score']].rename(columns={'score':col}),on=c.KEYS,how='left',validate='one_to_one');names.append(col)
 from champion_market_evaluate_20261031 import add_ensembles
 names.extend(add_ensembles(x,'full'))
 paths=price_cache();actions=pd.read_csv(c.ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv');actions=actions[actions.status.str.startswith('UNRESOLVED')];profiles=json.loads((c.ROOT/'research/protocols/personalized_official_action_tournament_v1.json').read_text())['profiles'];params=profiles['base7500'];rows=[];fail=[];selections=[]
 factorfile=c.ROOT/'work/champion-vs-market-20261031/iima_daily.csv';factors=pd.read_csv(factorfile,parse_dates=['Date']) if factorfile.exists() else None
 for date,g in x.groupby('decision_date',sort=True):
  endpoint=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date());bad=set(actions.loc[actions.provider_ratio.notna()&actions.event_date.ge(date)&actions.event_date.le(endpoint),'isin'])
  for name in names:
   for policy in ['global_top20','sector_top3_equal_sector']:
    ids,weights=selection(g,name,policy);missing=[i for i in ids if i not in paths];unresolved=sorted(set(ids)&bad);reason=''
    selections.extend(dict(model=name,policy=policy,decision_date=date,isin=i,weight=float(w)) for i,w in zip(ids,weights))
    if not ids:reason='No eligible selections'
    elif missing:reason='Missing selected price histories'
    elif unresolved:reason='Unresolved provider/official corporate action'
    if reason:fail.append(dict(model=name,policy=policy,date=date,reason=reason,missing=missing,unresolved=unresolved));continue
    for cost in [0,10,25,50]:
     try:r=portfolio_path([paths[i] for i in ids],weights,date,endpoint,params['amount'],params['interval_days'],cost)
     except ValueError as e:fail.append(dict(model=name,policy=policy,date=date,cost=cost,reason=str(e)));continue
     ds=r.pop('_daily_dates');ret=r.pop('_daily_returns')
     if factors is not None and cost==0:r.update(attribution(ds,ret,factors))
     r.update(model=name,policy=policy,decision_date=date,profile_name='base7500',cost_bps=cost,goal_hit=bool(r['xirr']+1e-7>=params['target_cagr']));rows.append(r)
  print('PORTFOLIO',date,len(rows),'failures',len(fail),flush=True)
 z=pd.DataFrame(rows)
 if z.empty:z=pd.DataFrame(columns=['model','policy','decision_date','profile_name','cost_bps','xirr','goal_hit','tw_max_drawdown','tw_volatility','tw_sharpe_rf0','daily_cvar5'])
 z.to_csv(c.OUT/'portfolio_cashflow_results.csv.gz',index=False);pd.DataFrame(selections).to_csv(c.OUT/'portfolio_selections.csv.gz',index=False);c.save('portfolio_failures.json',fail)
 if len(z):
  z['period']=np.where(z.decision_date.lt('2024-01-01'),'development','exposed');z.groupby(['period','model','policy','cost_bps'])[['xirr','goal_hit','tw_max_drawdown','tw_volatility','tw_sharpe_rf0','daily_cvar5']].agg(['mean','count']).to_csv(c.OUT/'portfolio_summary.csv')
 else:pd.DataFrame(columns=['period','model','policy','cost_bps','xirr','goal_hit','tw_max_drawdown']).to_csv(c.OUT/'portfolio_summary.csv',index=False)
 if len(z):paired_comparisons(z)
 else:pd.DataFrame(columns=['model','policy','cost_bps','benchmark','period','matched_dates','xirr_delta','goal_hit_delta','tw_max_drawdown_delta','tw_sharpe_rf0_delta']).to_csv(c.OUT/'portfolio_paired_comparisons.csv',index=False)
 c.save('portfolio_scope.json',dict(basis='Yahoo provider Adj Close research proxy; fractional units; unresolved official action windows block entire portfolio; no silent removal of missing selected stocks',universe='Full feature-available current-survivor panel, including unknown outcome rows; not PIT survivorship-free',profile='base7500; all9profiles evaluated separately in individual-stock ranking and index SIP panels',policy='Forward12month fixed selection, constant capital weights per contribution, no intermediate rebalancing; overlapping cohorts not chainable CAGR',risk='Daily flow-adjusted returns; RF0 Sharpe; first incomplete execution days excluded from risk stats; cost per buy and final sale',planned_queries=len(names)*2*x.decision_date.nunique(),models=len(names),completed_cost_rows=len(z),failure_records=len(fail)))

def paired_comparisons(z):
 metrics=['xirr','goal_hit','tw_max_drawdown','tw_volatility','tw_sharpe_rf0','daily_cvar5'];index=pd.read_csv(c.OUT/'index_sip_cashflow_results.csv.gz');index=index[index.profile_name.eq('base7500')];rows=[]
 for (model,policy,cost),g in z.groupby(['model','policy','cost_bps']):
  anchor=z[z.model.eq(c.ANCHOR)&z.policy.eq(policy)&z.cost_bps.eq(cost)]
  for label,other in [(c.ANCHOR,anchor)]+[(name,h) for name,h in index[index.cost_bps.eq(cost)].groupby('index')]:
   a=g.merge(other[['decision_date']+metrics],on='decision_date',suffixes=('_candidate','_benchmark'),validate='one_to_one');a['period']=np.where(a.decision_date.lt('2024-01-01'),'development','exposed')
   for period,b in a.groupby('period'):
    result=dict(model=model,policy=policy,cost_bps=cost,benchmark=label,period=period,matched_dates=len(b))
    for metric in metrics:result[metric+'_delta']=float(b[metric+'_candidate'].astype(float).mean()-b[metric+'_benchmark'].astype(float).mean())
    if cost==25 and label in [c.ANCHOR,'NIFTY_500']:
     from champion_market_review_20261031 import block_indices
     dates=np.sort(b.decision_date.unique());ordered=b.set_index('decision_date').loc[dates];days=np.asarray(dates,dtype='datetime64[D]');span_days=int((days[-1]-days[0]).astype(int))
     for span in [365,730]:
      if len(dates)<4 or span_days<span:result[f'xirr_delta_low95_{span}d']=np.nan;result[f'xirr_delta_high95_{span}d']=np.nan;continue
      rng=np.random.default_rng(20261031+span);difference=ordered.xirr_candidate.to_numpy()-ordered.xirr_benchmark.to_numpy();center=difference-difference.mean();boot=np.array([center[block_indices(dates,span,rng)].mean() for _ in range(4000)]);result[f'xirr_delta_low95_{span}d']=float(difference.mean()-np.quantile(boot,.975));result[f'xirr_delta_high95_{span}d']=float(difference.mean()-np.quantile(boot,.025))
    rows.append(result)
 pd.DataFrame(rows).to_csv(c.OUT/'portfolio_paired_comparisons.csv',index=False)
if __name__=='__main__':main()
