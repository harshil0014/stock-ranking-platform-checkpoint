"""Shared immutable data preparation for the external champion benchmark."""
from pathlib import Path
import sys,json,hashlib,gc
import numpy as np
import pandas as pd
import ten_hypotheses_20261031 as old
ROOT=old.ROOT;OUT=ROOT/'experiments/champion-vs-market-20261031';KEYS=old.KEYS;GROUP=old.GROUP;ANCHOR=old.ANCHOR;FEATURES=old.old.COLS

def save(name,value):
 (OUT/name).parent.mkdir(parents=True,exist_ok=True);(OUT/name).write_text(json.dumps(value,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')

def stable_random(x,seed=20261031):
 return np.array([int(hashlib.sha256(f'{i}|{d}|{p}|{seed}'.encode()).hexdigest()[:13],16)/16**13 for i,d,p in x[KEYS].itertuples(index=False,name=None)])

def pct(x,value,global_scope=False):
 keys=['decision_date','profile_name'] if global_scope else GROUP
 return pd.Series(value,index=x.index).groupby([x[c] for c in keys],observed=True).rank(pct=True).fillna(.5)

def sample_queries(x,cap=120000):
 groups=x.groupby(GROUP,observed=True,sort=True).indices
 ordered=sorted(groups,key=lambda k:hashlib.sha256(('|'.join(map(str,k))+'|20261031').encode()).hexdigest())
 ids=[]
 for key in ordered:
  g=groups[key]
  if len(ids)+len(g)<=cap:ids.extend(g.tolist())
 return x.iloc[np.array(ids,dtype=int)].sort_values(GROUP+['isin']).copy()

def prepare():
 if all((OUT/p).exists() for p in ['panel.pkl.gz','valid_panel.pkl.gz','panel_receipt.json']):return
 x=pd.read_pickle(old.OUT/'panel.pkl.gz',compression='gzip')
 oldnames=json.loads((old.OUT/'model_registry.json').read_text())['models']
 keep=list(dict.fromkeys(KEYS+['sector','endpoint','period','future_xirr','future_drawdown','future_shortfall','goal_hit',ANCHOR,'original','rank_xendcg_balanced']+FEATURES+oldnames))
 x=x[keep].copy();x['sector']=x.sector.astype(str);x['profile_name']=x.profile_name.astype(str)
 vol=pd.read_pickle(old.OUT/'volume_features.pkl.gz',compression='gzip');x=x.merge(vol,on=['isin','decision_date'],how='left',validate='many_to_one');del vol;gc.collect()
 factors={
 'momentum_12_1':pct(x,x.momentum12_1),'momentum_6':pct(x,x.return126),
 'risk_adjusted_momentum_6_12':(pct(x,x.return126/x.volatility252.where(x.volatility252.gt(0)))+pct(x,x.momentum12_1/x.volatility252.where(x.volatility252.gt(0))))/2,
 'high52_proximity':pct(x,x.high_gap252),'high52_recency':pct(x,-x.high_age252),
 'low_volatility':pct(x,-x.volatility252),'low_downside':pct(x,-x.downside252),
 'short_term_reversal':pct(x,-x.return21),'trend_slope':pct(x,x.slope126),'trend_efficiency':pct(x,x.efficiency126),
 'global_momentum_no_sector':pct(x,x.momentum12_1,True),'global_lowvol_no_sector':pct(x,-x.volatility252,True)}
 factors['momentum_lowvol_equal']=(factors['momentum_12_1']+factors['low_volatility'])/2
 factors['momentum_high_lowvol_equal']=(factors['momentum_12_1']+factors['high52_proximity']+factors['low_volatility'])/3
 factors['volume_high_confirmation']=.5*factors['momentum_12_1']+.25*factors['high52_proximity']+.25*pct(x,x.abnormal_volume21.where(x.high_gap252.ge(-.05)))
 for name,values in factors.items():x['factor__'+name]=values.where(x.evidence_fraction.gt(0),.5)
 x['control__neutral']=.5;x['control__random']=stable_random(x);x['control__price_head']=x.rank_xendcg_balanced;x['control__original']=x.original
 registry=dict(anchor=ANCHOR,factors=['factor__'+n for n in factors],controls=['control__neutral','control__random','control__price_head','control__original'],prior_policies=[n for n in oldnames if n!=ANCHOR],factor_replication='Price-feature heuristics inspired by literature, not exact factor-index replication; no PIT quality/value accounting data substituted',dataset='Current-survivor44-date9-profile guarded SIP panel; preserve unlabeled normalization rows')
 save('score_registry.json',registry)
 for c in FEATURES+old.VOL:x[c]=x[c].astype('float32')
 x=x.sort_values(KEYS).reset_index(drop=True);x.to_pickle(OUT/'panel.pkl.gz',compression='gzip')
 valid=old.valid(x).dropna(subset=['future_drawdown','future_shortfall']);valid['return_target']=valid.groupby(GROUP,observed=True).future_xirr.rank(pct=True);valid['balanced_target']=.5*valid.return_target+.25*valid.groupby(GROUP,observed=True).future_drawdown.rank(pct=True)+.25*valid.groupby(GROUP,observed=True).future_shortfall.rank(pct=True,ascending=False)
 valid.to_pickle(OUT/'valid_panel.pkl.gz',compression='gzip')
 save('panel_receipt.json',dict(rows=len(x),valid_rows=len(valid),profiles=sorted(valid.profile_name.unique()),dates=sorted(valid.decision_date.unique()),primary_dates=sorted(valid.loc[valid.decision_date.ge('2020-01-01'),'decision_date'].unique()),features=FEATURES,source_panel_sha256=hashlib.sha256((old.OUT/'panel.pkl.gz').read_bytes()).hexdigest(),frozen_anchor_finite=bool(np.isfinite(valid[ANCHOR]).all())))
 print('PREPARED',len(x),len(valid),flush=True)

if __name__=='__main__':prepare()
