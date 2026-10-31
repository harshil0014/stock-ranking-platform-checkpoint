"""Fixed group-size sector placebo: recompute every downstream sector normalization."""
from pathlib import Path
import sys,json,pickle,gc,hashlib
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/"experiments/model_dependencies_20261008"))
import numpy as np
import pandas as pd
import lightgbm as lgb
import full_coverage_challenger_20261008 as legacy
import sector_price_rebuild_20261010 as price
import ten_hypotheses_20261031 as base
import champion_high_recency_20261017 as high
import champion_sip_profit_20261017 as sip
from stock_ranker.sector_scoring import components,score as sector_score
from stock_ranker.sip_profit_signal import adjustments
ROOT=legacy.ROOT;OUT=ROOT/'experiments/round2-sector-placebo-20261031'
sys.path.insert(0,str(ROOT/'experiments/model_dependencies_20261008'))
SEED=2026103101;N=50

def save(name,obj):
 OUT.mkdir(exist_ok=True);(OUT/name).write_text(json.dumps(obj,indent=2,default=lambda v:v.item() if hasattr(v,'item') else str(v)),encoding='utf-8')

def assignment(sectors,dates,seed):
 rng=np.random.default_rng(seed);result=sectors.astype(str).copy()
 for day,ids in dates.groupby(dates,sort=True).groups.items():result.loc[ids]=rng.permutation(result.loc[ids].to_numpy())
 return result

def prepare():
 OUT.mkdir(exist_ok=True)
 doc=json.loads((ROOT/'research/protocols/round2_20261031.json').read_text())['sector_placebo']
 f=OUT/'protocol.json'
 if f.exists():assert json.loads(f.read_text())==doc
 else:save('protocol.json',doc)
 if (OUT/'inputs.pkl.gz').exists():return
 f=pd.read_pickle(legacy.OUT/'historical.pkl.gz',compression='gzip');f=legacy.activity(f);f=f[f.decision_date.ge('2020-01-01')].copy().reset_index(drop=True)
 p=pd.read_pickle(base.OUT/'panel.pkl.gz',compression='gzip');p=p[p.profile_name.eq('base7500')&p.decision_date.ge('2020-01-01')].copy()
 # Main panel contains the full base-profile normalization population, including unavailable outcomes.
 p=p.set_index(base.KEYS).reindex(pd.MultiIndex.from_frame(f[base.KEYS])).reset_index()
 assert len(p)==len(f) and p.sector.notna().all()
 p=high.attach(p);p=sip.attach_profit(p)
 p.sector=p.sector.astype(str);f.sector=f.sector.astype(str)
 pd.to_pickle((f,p),OUT/'inputs.pkl.gz',compression='gzip');print('INPUTS',len(f),flush=True)

def load_models(year):
 root=ROOT/'experiments';result={}
 for name in ['rank_xendcg_balanced_15','rank_xendcg_return_15']:result[name]=lgb.Booster(model_file=str(legacy.OUT/f'{name}_{year}.txt'))
 for name in ['catboost_defensive','ridge_defensive']:
  with (root/'full-coverage-open-models-20261008'/f'{name}_{year}.pkl').open('rb') as stream:result[name]=pickle.load(stream)
 result['profile']=lgb.Booster(model_file=str(price.OLD/f'profile_defensive_15_{year}.txt'))
 result['price']=lgb.Booster(model_file=str(price.OUT/f'rank_xendcg_balanced_{year}.txt'))
 return result

def percentile(raw,x,evidence):return pd.Series(raw,index=x.index).groupby([x.decision_date,x.sector]).rank(pct=True).where(evidence.gt(0),.5)

def frozen_ridge_predict(pipeline,frame):
 # Evaluate stored 1.7 parameters directly: current sklearn 1.9 cannot load its
 # SimpleImputer.transform ABI. No refitting or parameter adaptation occurs.
 imputer,scaler,ridge=[step for name,step in pipeline.steps]
 x=frame.to_numpy(dtype=float,copy=True);missing=np.isnan(x)
 stats=imputer.statistics_;keep=~np.isnan(stats)
 assert imputer.strategy=='median' and not imputer.keep_empty_features
 x=np.where(missing,stats,x)[:,keep]
 if imputer.add_indicator:x=np.column_stack([x,missing[:,imputer.indicator_.features_]])
 x=(x-scaler.mean_)/scaler.scale_
 return x@ridge.coef_+ridge.intercept_

def rescore(f,p,models,price_population):
 f=legacy.features(components(f))
 choice=json.loads((ROOT/'experiments/sector-tuning-20261005/selection_lock.json').read_text())['winner']
 f['sector_incumbent']=sector_score(f,choice)
 for name in ['rank_xendcg_balanced_15','rank_xendcg_return_15']:
  f[name]=percentile(models[name].predict(f[legacy.predictors()],num_threads=2),f,f.evidence_fraction)
 baseline=legacy.selected_score(f,'dual_b0.35_r0.15_c0.4')
 cols=legacy.predictors()+['volume_active_fraction','observations_1y']
 a=percentile(models['catboost_defensive'].predict(f[cols]),f,f.evidence_fraction)
 b=percentile(frozen_ridge_predict(models['ridge_defensive'],f[cols]),f,f.evidence_fraction)
 opened=(.95*baseline+.05*(a+b)/2).where(f.evidence_fraction.gt(0),.5)
 prof=f[cols].copy()
 for c in price.PARAMS:prof[c]=p[c].to_numpy()
 prof=prof.astype('float32')
 defended=percentile(models['profile'].predict(prof,num_threads=2),f,f.evidence_fraction)
 # Raw price basis is independent of sectors; recalculate percentile/context inputs.
 px=p.copy()
 engineered=price.engineer(price_population).set_index(['isin','decision_date'])
 selected=engineered.reindex(pd.MultiIndex.from_frame(p[['isin','decision_date']]))
 for col in price.COLS:
  if col not in price.PARAMS:px[col]=selected[col].to_numpy()
 px[price.COLS]=px[price.COLS].astype('float32')
 pure=percentile(models['price'].predict(px[price.COLS].astype('float32'),num_threads=2),px,px.evidence_fraction)
 px['evidence_fraction']=p.evidence_fraction
 px[high.base.ANCHOR]=.60*opened.to_numpy()+.15*defended.to_numpy()+.25*pure.to_numpy()
 # high.attach carries the original high-price basis, independently of the new head.
 for c in ['days_since_recorded_high','distance_from_recorded_high','distance_from_52w_high']:px[c]=p[c]
 px=high.signals(px)
 out=px['dual_w0.01']+.01*adjustments(px)['risk_confirmed']
 return out,dict(open=opened,profile=defended,price=pure)

def run():
 prepare();f,p=pd.read_pickle(OUT/'inputs.pkl.gz',compression='gzip');models={y:load_models(y) for y in range(2020,2026)}
 full=pd.read_pickle(price.OUT/'price_features.pkl.gz',compression='gzip')
 full=full[full.decision_date.isin(f.decision_date.unique())].copy();full.sector=full.sector.astype(str)
 control=pd.Series(index=p.index,dtype=float);parts=[]
 for year in models:
  mask=p.decision_date.str.startswith(str(year));s,c=rescore(f.loc[mask].copy(),p.loc[mask].copy(),models[year],full[full.decision_date.str.startswith(str(year))]);control.loc[mask]=s
  for k,v in c.items():parts.append(dict(year=year,component=k,minimum=float(v.min()),maximum=float(v.max())))
 error=float((control-p[base.ANCHOR]).abs().max());save('control.json',dict(max_absolute_error=error,threshold=1e-10,passed=error<=1e-10,components=parts))
 pd.DataFrame(dict(saved=p[base.ANCHOR],replayed=control,decision_date=p.decision_date,isin=p['isin'])).to_csv(OUT/'control_scores.csv.gz',index=False)
 print('CONTROL',error,flush=True)
 if error>1e-10:raise RuntimeError('Full champion replay does not meet control tolerance; no placebo claim')
 valid=base.valid(p);cols=[base.ANCHOR];results=[]
 for k in range(N):
  dest=OUT/f'queries_{k:02}.csv.gz'
  if dest.exists():continue
  sectors=assignment(f.sector,f.decision_date,SEED+k);scores=pd.Series(index=f.index,dtype=float)
  # Preserve exact counts in both legacy scoring and full price-normalization
  # populations by permuting the additional identities separately.
  full_shuffled=full.copy();lookup=pd.Series(sectors.to_numpy(),index=pd.MultiIndex.from_frame(f[['isin','decision_date']]))
  mapped=lookup.reindex(pd.MultiIndex.from_frame(full[['isin','decision_date']])).to_numpy();inside=pd.notna(mapped)
  full_shuffled.loc[inside,'sector']=mapped[inside]
  full_shuffled.loc[~inside,'sector']=assignment(full.loc[~inside,'sector'],full.loc[~inside,'decision_date'],SEED+k+1000000)
  for year in models:
   mask=f.decision_date.str.startswith(str(year));ff=f.loc[mask].copy();pp=p.loc[mask].copy();ff.sector=sectors.loc[mask];pp.sector=sectors.loc[mask]
   scores.loc[mask]=rescore(ff,pp,models[year],full_shuffled[full_shuffled.decision_date.str.startswith(str(year))])[0]
  z=valid.copy();z['placebo']=scores.reindex(z.index);q=base.metrics(z,[base.ANCHOR,'placebo']);q['permutation']=k;q.to_csv(dest,index=False)
  print('PERMUTATION',k,flush=True)
 q=pd.concat([pd.read_csv(OUT/f'queries_{k:02}.csv.gz') for k in range(N)],ignore_index=True)
 q.to_csv(OUT/'queries.csv.gz',index=False)
 summary=[];decisions={}
 for period,g in q.groupby(np.where(q.decision_date.lt('2024-01-01'),'development','exposed')):
  daily=g.groupby(['permutation','model','decision_date'])[['rank_ic','achievement']].mean();avg=daily.groupby(['permutation','model']).mean();real=avg.xs(base.ANCHOR,level='model');fake=avg.xs('placebo',level='model')
  for k in range(N):summary.append(dict(period=period,permutation=k,real_ic=real.loc[k,'rank_ic'],shuffled_ic=fake.loc[k,'rank_ic'],real_attainment=real.loc[k,'achievement'],shuffled_attainment=fake.loc[k,'achievement']))
  diff=(daily.xs(base.ANCHOR,level='model')-daily.xs('placebo',level='model')).groupby('decision_date').mean()[['rank_ic']]
  from round2_goal_risk_20261031 import calendar_intervals
  bound=calendar_intervals(diff)['rank_ic'];gap=float(real.rank_ic.mean()-np.quantile(fake.rank_ic,.95))
  decisions[period]=dict(real_ic=float(real.rank_ic.mean()),shuffle_mean_ic=float(fake.rank_ic.mean()),shuffle95_ic=float(np.quantile(fake.rank_ic,.95)),real_minus_shuffle95=gap,paired_interval=bound,passes=bool(gap>=.01013492400721767 and bound['lower']>0))
 pd.DataFrame(summary).to_csv(OUT/'summary.csv',index=False);save('decision.json',dict(periods=decisions,sector_structure_gate=bool(decisions['development']['passes'] and decisions['exposed']['real_ic']>decisions['exposed']['shuffle_mean_ic']),fresh_validation=False,limitations=['base7500 only','current-survivor universe','current retrospective sectors','fixed fitted weights, not retrained sector-free comparison']))

if __name__=='__main__':run()
