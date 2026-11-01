"""Deterministic cohort selection and strictly next-open 21-session outcomes."""
import numpy as np


def top_quartile(frame, score):
    z=frame.sort_values([score,'isin'],ascending=[False,True])
    return z.head(int(np.ceil(len(z)/4)))


def high_state(path, decision):
    ds,op,cl=path
    d=np.datetime64(decision,'D')
    last=np.searchsorted(ds,d,side='right')-1
    if last<0 or int((d-ds[last]).astype(int))>7:raise ValueError('Missing signal close')
    prefix=np.asarray(cl[:last+1],float)
    if not np.isfinite(prefix).all() or (prefix<=0).any():raise ValueError('Invalid high history')
    drawdown=float(cl[last]/prefix.max()-1)
    return dict(dip=bool(drawdown<=-.10+1e-12),from_recorded_high=drawdown)


def entry_state(path, decision):
    ds,op,cl=path
    d=np.datetime64(decision,'D')
    state=high_state(path,decision)
    buy=np.searchsorted(ds,d,side='right');end=buy+20
    if end>=len(ds):raise ValueError('Missing entry or exit history')
    if int((ds[buy]-d).astype(int))>7:
        raise ValueError('Entry boundary gap')
    if (np.diff(ds[buy:end+1]).astype(int)>7).any():raise ValueError('Holding gap')
    if not np.isfinite(op[buy]) or op[buy]<=0 or not np.isfinite(cl[end]) or cl[end]<=0:
        raise ValueError('Missing actual open or exit close')
    return dict(**state,
                entry=str(ds[buy]),exit=str(ds[end]),gross_ratio=float(cl[end]/op[buy]))


def net_return(gross_ratio,cost_bps):
    c=cost_bps/10000
    if not 0<=c<1:raise ValueError('Invalid cost')
    return np.asarray(gross_ratio)*(1-c)/(1+c)-1
