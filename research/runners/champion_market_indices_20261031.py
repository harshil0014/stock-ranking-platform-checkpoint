"""Actual-index forward SIP cashflows; stock rank accuracy is not defined for an index."""
from pathlib import Path
import json,datetime,hashlib,math
import numpy as np,pandas as pd
from scipy.optimize import brentq
import champion_market_common_20261031 as c
LAUNCH={'NIFTY_500':'1999-06-07','NIFTY_50':'1996-04-22','NIFTY_MIDCAP_150':'2016-04-01','NIFTY_SMALLCAP_250':'2016-04-01','NIFTY500_MOMENTUM_50':'2024-06-04','NIFTY500_QUALITY_50':'2024-12-20','NIFTY500_LOW_VOLATILITY_50':'2024-12-20','NIFTY500_VALUE_50':'2018-10-24','NIFTY500_MULTIFACTOR_MQVLV_50':'2025-02-06','NIFTY200_MOMENTUM_30':'2020-08-25','BSE500_PRICE_ONLY':'1999-08-09'}

def xirr(dates,flows):
 dates=np.asarray(dates,dtype='datetime64[D]');flows=np.asarray(flows,float);years=(dates-dates[0]).astype(float)/365.25
 def f(loggross):return np.sum(flows*np.exp(-loggross*years))
 try:return float(np.expm1(brentq(f,-20,20)))
 except (ValueError,OverflowError):return np.nan

def sip_path(dates,prices,start,end,amount,interval,cost_bps=0):
 dates=np.asarray(dates,dtype='datetime64[D]');prices=np.asarray(prices,float);start=np.datetime64(start,'D');end=np.datetime64(end,'D');schedule=np.arange(start,end,np.timedelta64(interval,'D'));buy=np.searchsorted(dates,schedule,side='left');last=np.searchsorted(dates,end,side='right')-1
 if last<0 or len(schedule)==0 or (buy>last).any() or (buy>=len(dates)).any():raise ValueError('Missing contribution/terminal observations')
 if ((dates[buy]-schedule).astype(int)>7).any() or int((end-dates[last]).astype(int))>7:raise ValueError('Unacceptable index execution gap')
 if not np.isfinite(prices).all() or (prices<=0).any() or len(np.unique(dates))!=len(dates):raise ValueError('Invalid index observations')
 cost=cost_bps/10000;units=amount/(1+cost)/prices[buy];terminal=prices[last]*units.sum()*(1-cost)
 flowdates=np.r_[schedule,end];flows=np.r_[np.full(len(schedule),-amount),terminal]
 first=int(buy.min());d=dates[first:last+1];p=prices[first:last+1];units_by_day=np.zeros(len(d));flow_by_day=np.zeros(len(d));np.add.at(units_by_day,buy-first,units);np.add.at(flow_by_day,buy-first,amount)
 wealth=np.cumsum(units_by_day)*p;wealth[-1]=terminal;ret=np.divide(wealth[1:]-flow_by_day[1:],wealth[:-1],out=np.zeros(len(d)-1),where=wealth[:-1]>0)-1
 initial=wealth[0]/flow_by_day[0];nav=np.r_[initial,initial*np.cumprod(1+ret)];dd=nav/np.maximum.accumulate(np.r_[1.,nav])[1:]-1;sd=np.std(ret)*np.sqrt(252);mean=np.mean(ret)*252;down=np.sqrt(np.mean(np.minimum(ret,0)**2))*np.sqrt(252)
 return dict(xirr=xirr(flowdates,flows),terminal=terminal,contributed=amount*len(schedule),tw_max_drawdown=float(dd.min()),tw_volatility=float(sd),tw_sharpe_rf0=float(mean/sd) if sd>0 else np.nan,tw_sortino_rf0=float(mean/down) if down>0 else np.nan,daily_cvar5=float(np.sort(ret)[:max(1,int(np.ceil(.05*len(ret))))].mean()),trading_observations=len(d),contributions=len(schedule),endpoint_observed=str(d[-1]))

def load_indices():
 result={};audits=[]
 for path in sorted(c.OUT.glob('*_TRI.csv')):
  raw=pd.read_csv(path);name=path.name[:-len('_TRI.csv')];norm=lambda a:''.join(ch for ch in a.upper() if ch.isalnum())
  if not raw['Index Name'].map(norm).eq(norm(name)).all():raise ValueError('Index identity mismatch '+name)
  x=pd.DataFrame(dict(date=pd.to_datetime(raw.Date,format='%d %b %Y'),value=pd.to_numeric(raw.TotalReturnsIndex))).sort_values('date');assert x.date.is_unique and x.value.gt(0).all()
  result[name]=(x.date.to_numpy(dtype='datetime64[D]'),x.value.to_numpy(float),'OFFICIAL_GROSS_TRI');audits.append(dict(index=name,rows=len(x),start=str(x.date.min().date()),end=str(x.date.max().date()),series='OFFICIAL_GROSS_TRI',launch_date=LAUNCH.get(name),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
 bse=c.ROOT/'work/champion-vs-market-20261031/bse500-price.body'
 if bse.exists():
  raw=pd.read_csv(bse);x=pd.DataFrame(dict(date=pd.to_datetime(raw.Date,format='%d-%B-%Y'),value=pd.to_numeric(raw.Close))).sort_values('date');assert x.date.is_unique and x.value.gt(0).all();result['BSE500_PRICE_ONLY']=(x.date.to_numpy(dtype='datetime64[D]'),x.value.to_numpy(float),'OFFICIAL_PRICE_INDEX_NOT_TRI');x.to_csv(c.OUT/'BSE500_PRICE_ONLY.csv',index=False);audits.append(dict(index='BSE500_PRICE_ONLY',rows=len(x),series='OFFICIAL_PRICE_INDEX_NOT_TRI',tri_status='BSE500T official ticker returnedempty; current public UI offers price graph and client access',sha256=hashlib.sha256(bse.read_bytes()).hexdigest()))
 c.save('index_series_validation.json',audits);return result

def main():
 indices=load_indices();profiles=json.loads((c.ROOT/'research/protocols/personalized_official_action_tournament_v1.json').read_text())['profiles'];panel=pd.read_pickle(c.OUT/'valid_panel.pkl.gz',compression='gzip');dates=sorted(panel.loc[panel.decision_date.ge('2020-01-01'),'decision_date'].unique());rows=[];failures=[]
 for name,(ds,prices,basis) in indices.items():
  for day in dates:
   endpoint=str((pd.Timestamp(day)+pd.DateOffset(months=12)).date())
   for profile,params in profiles.items():
    for cost in [0,10,25,50]:
     try:
      r=sip_path(ds,prices,day,endpoint,params['amount'],params['interval_days'],cost);r.update(index=name,decision_date=day,profile_name=profile,cost_bps=cost,goal_hit=bool(r['xirr']+1e-7>=params['target_cagr']),basis=basis,live_history_only=day>=LAUNCH.get(name,'9999-01-01'));rows.append(r)
     except ValueError as e:failures.append(dict(index=name,day=day,profile=profile,reason=str(e)))
 x=pd.DataFrame(rows);x.to_csv(c.OUT/'index_sip_cashflow_results.csv.gz',index=False);c.save('index_execution_failures.json',failures)
 x['period']=np.where(x.decision_date.lt('2024-01-01'),'development','exposed');x.groupby(['period','index','cost_bps','basis'])[['xirr','goal_hit','tw_max_drawdown','tw_volatility','tw_sharpe_rf0','daily_cvar5']].mean().reset_index().to_csv(c.OUT/'index_sip_summary.csv',index=False)
 x[x.live_history_only].groupby(['period','index','cost_bps'])[['xirr','goal_hit','tw_max_drawdown']].mean().reset_index().to_csv(c.OUT/'index_live_only_summary.csv',index=False)
 print('INDEX CASHFLOWS',len(x),'FAILURES',len(failures),'SERIES',len(indices),flush=True)
if __name__=='__main__':main()
