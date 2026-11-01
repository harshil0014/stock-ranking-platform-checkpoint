"""Static fixed-anchor research proxy approved by user; not a daily-reset ladder."""
import numpy as np
import pandas as pd
LEVELS=np.array([.10,.15,.20,.25,.30,.35,.40])
ALLOTMENTS=np.array([.10,.05,.20,.10,.30,.15,.10])


def high_features(dates,closes,decision):
    day=np.datetime64(decision,'D');stop=np.searchsorted(dates,day,side='right')
    ds=np.asarray(dates)[:stop];p=np.asarray(closes,float)[:stop]
    if not len(p) or int((day-ds[-1]).astype(int))>7 or not np.isfinite(p).all() or (p<=0).any():
        raise ValueError('Unavailable recorded high prefix')
    prior=np.r_[np.inf,np.maximum.accumulate(p)[:-1]]
    records=p>prior*(1+1e-10)
    start=np.datetime64((pd.Timestamp(decision)-pd.DateOffset(years=1)).date())
    peak=p.max();latest=np.flatnonzero(np.isclose(p,peak,rtol=1e-10,atol=0))[-1]
    return dict(ath_count=int(records[ds>start].sum()),ath_gap=float(p[-1]/peak-1),
                ath_recency=-int((day-ds[latest]).astype(int)),anchor=float(peak))


def funded_stock(path,start,end,policy,budget=90000.,cash_rate=0.,cost_bps=100,calendar=None):
    ds,op,cl,vol=path;ds=np.asarray(ds,dtype='datetime64[D]')
    op,cl,vol=map(lambda a:np.asarray(a,float),(op,cl,vol))
    start,end=np.datetime64(start,'D'),np.datetime64(end,'D')
    if policy not in ['ladder','sip'] or budget<=0 or cash_rate<0 or not 0<=cost_bps<10000:
        raise ValueError('Invalid funded simulation parameters')
    if not(len(ds)==len(op)==len(cl)==len(vol)) or (np.diff(ds).astype(int)<=0).any():raise ValueError('Invalid source path')
    info=high_features(ds,cl,start);anchor=info['anchor']
    a=np.searchsorted(ds,start,side='right')-1;b=np.searchsorted(ds,end,side='right')
    if a<0 or b<=a or int((end-ds[b-1]).astype(int))>7 or (np.diff(ds[a:b]).astype(int)>7).any():
        raise ValueError('Incomplete daily horizon')
    if not np.isfinite(cl[a:b]).all() or (cl[a:b]<=0).any():raise ValueError('Missing daily close')
    cal=np.unique(np.r_[start,ds[(ds>=start)&(ds<=end)],end]) if calendar is None else np.asarray(calendar,dtype='datetime64[D]')
    if cal[0]!=start or cal[-1]!=end or (np.diff(cal).astype(int)<=0).any():raise ValueError('Invalid mark calendar')
    cost=cost_bps/10000;cash=float(budget);units=0.;spent=0.;previous=start
    queued=np.zeros(7,bool);filled=np.zeros(7,bool);signals=np.full(7,np.datetime64('NaT','D'),dtype='datetime64[D]')
    if policy=='ladder':
        queued=cl[a]<=anchor*(1-LEVELS)+1e-10*anchor;signals[queued]=start
    schedule=np.array([(pd.Timestamp(start)+pd.DateOffset(months=k)).date() for k in range(12)],dtype='datetime64[D]');sip_filled=np.zeros(12,bool)
    wealth=[];cash_values=[];equity=[];fills=[]
    for day in cal:
        cash*=(1+cash_rate)**(int((day-previous).astype(int))/365.25);previous=day
        pos=np.searchsorted(ds,day,side='right')-1;actual=pos>=0 and ds[pos]==day
        if pos<0 or int((day-ds[pos]).astype(int))>7:raise ValueError('Stale daily mark')
        if actual and day>start:
            if policy=='ladder':which=np.flatnonzero(queued&~filled&(signals<day));capital=budget*ALLOTMENTS[which].sum()
            else:which=np.flatnonzero(~sip_filled&(schedule<day));capital=budget*len(which)/12
            if len(which):
                signal_days=signals[which] if policy=='ladder' else schedule[which]
                if ((day-signal_days).astype(int)>7).any():raise ValueError('Delayed execution')
                if not np.isfinite(op[pos]) or op[pos]<=0 or not np.isfinite(vol[pos]) or vol[pos]<=0:
                    raise ValueError('Unknown open or zero-volume execution')
                if capital>cash+1e-7:raise ValueError('Negative cash would be required')
                units+=capital/(op[pos]*(1+cost));cash-=capital;spent+=capital
                fills.extend([str(day)]*len(which))
                if policy=='ladder':filled[which]=True
                else:sip_filled[which]=True
        value=units*cl[pos]
        if day==end:value*=1-cost
        equity.append(value);cash_values.append(cash);wealth.append(cash+value)
        if actual and policy=='ladder' and day<end:
            new=(~queued)&(cl[pos]<=anchor*(1-LEVELS)+1e-10*anchor)
            queued[new]=True;signals[new]=day
    wealth=np.asarray(wealth);nav=wealth/budget;dd=nav/np.maximum.accumulate(nav)-1
    return dict(budget_xirr=float((wealth[-1]/budget)**(365.25/int((end-start).astype(int)))-1),
        terminal=float(wealth[-1]),deployment=spent/budget,no_fill=spent==0,
        filled_tranches=int(filled.sum()) if policy=='ladder' else int(sip_filled.sum()),
        trap=bool(policy=='ladder' and filled.sum()>=5 and equity[-1]<spent),drawdown=float(dd.min()),
        first_fill=min(fills) if fills else None,anchor=anchor,_wealth=wealth,_calendar=cal)
