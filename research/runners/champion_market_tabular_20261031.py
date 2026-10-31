"""Frozen-budget, purged annual international tabular baselines."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','3');os.environ.setdefault('OMP_NUM_THREADS','3')
from pathlib import Path
import sys,argparse,time,json,pickle,hashlib,gc,warnings
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT/'experiments/model_dependencies_20261008'))
import numpy as np,pandas as pd
import lightgbm as lgb
from sklearn.linear_model import Ridge,ElasticNet
from sklearn.ensemble import ExtraTreesRegressor,RandomForestRegressor,HistGradientBoostingRegressor
from catboost import CatBoostRanker
from xgboost import XGBRanker
import champion_market_common_20261031 as c
SEEDS=[20261031,20261032,20261033]

def transform_fit(train,test,scaled=False):
 a=train[c.FEATURES].to_numpy(float);b=test[c.FEATURES].to_numpy(float)
 with warnings.catch_warnings():warnings.simplefilter('ignore');median=np.nanmedian(a,axis=0)
 median=np.nan_to_num(median);a=np.where(np.isfinite(a),a,median);b=np.where(np.isfinite(b),b,median)
 mean=a.mean(0) if scaled else np.zeros(a.shape[1]);sd=a.std(0) if scaled else np.ones(a.shape[1]);sd=np.where(sd>1e-10,sd,1.)
 return ((a-mean)/sd).astype('float32'),((b-mean)/sd).astype('float32'),dict(median=median,mean=mean,sd=sd)

def fit(name,objective,seed,train,test):
 y=train[objective+'_target'].to_numpy(float);w=(1/train.groupby(c.GROUP,observed=True)['isin'].transform('size')).to_numpy(copy=True);w/=w.mean();groups=train.groupby(c.GROUP,observed=True,sort=False).size().to_numpy()
 X,Z,pre=transform_fit(train,test,scaled=name in ['ridge','elasticnet'])
 if name=='ridge':m=Ridge(alpha=100)
 elif name=='elasticnet':m=ElasticNet(alpha=.001,l1_ratio=.5,max_iter=1000,random_state=seed)
 elif name=='hist_gradient_boosting':m=HistGradientBoostingRegressor(max_iter=120,max_leaf_nodes=15,max_depth=5,min_samples_leaf=200,l2_regularization=30,learning_rate=.04,random_state=seed,early_stopping=False)
 elif name in ['extra_trees','random_forest']:
  cls=ExtraTreesRegressor if name=='extra_trees' else RandomForestRegressor
  m=cls(n_estimators=120,max_depth=5,max_leaf_nodes=15,min_samples_leaf=200,max_features=.8,n_jobs=3,random_state=seed)
 elif name=='lightgbm_regression':m=lgb.LGBMRegressor(n_estimators=120,num_leaves=15,max_depth=5,min_child_samples=200,reg_lambda=30,learning_rate=.04,n_jobs=3,random_state=seed,verbosity=-1,deterministic=True,force_col_wise=True)
 elif name=='lightgbm_lambdarank':
  m=lgb.LGBMRanker(objective='lambdarank',n_estimators=120,num_leaves=15,max_depth=5,min_child_samples=200,reg_lambda=30,learning_rate=.04,n_jobs=3,random_state=seed,verbosity=-1,deterministic=True,force_col_wise=True,label_gain=list(range(20)),lambdarank_truncation_level=20)
  m.fit(X,np.floor(y*19).astype(int),group=groups,sample_weight=w);return m.predict(Z),m,pre
 elif name=='catboost_yetirank':
  m=CatBoostRanker(iterations=120,depth=5,learning_rate=.04,loss_function='YetiRank',l2_leaf_reg=30,thread_count=3,random_seed=seed,verbose=False,allow_writing_files=False)
  m.fit(X,y,group_id=np.repeat(np.arange(len(groups)),groups),group_weight=w);return m.predict(Z),m,pre
 elif name=='xgboost_rankndcg':
  m=XGBRanker(objective='rank:ndcg',n_estimators=120,max_depth=5,learning_rate=.04,reg_lambda=30,n_jobs=3,random_state=seed,tree_method='hist',min_child_weight=200)
  m.fit(X,np.floor(y*19).astype(int),group=groups);return m.predict(Z),m,pre
 else:raise ValueError(name)
 m.fit(X,y,sample_weight=w);return m.predict(Z),m,pre

def main(name):
 c.prepare();x=pd.read_pickle(c.OUT/'valid_panel.pkl.gz',compression='gzip');folder=c.OUT/'tabular';folder.mkdir(exist_ok=True);audits=[]
 deterministic=name in ['ridge','elasticnet','hist_gradient_boosting','lightgbm_regression','lightgbm_lambdarank','xgboost_rankndcg']
 for year in range(2020,2026):
  train=c.sample_queries(x[x.endpoint.lt(f'{year}-01-01')]);test=x[x.decision_date.str.startswith(str(year))].copy()
  assert train.endpoint.max()<f'{year}-01-01' and not set(train.index)&set(test.index)
  for objective in ['return','balanced']:
   dest=folder/f'{name}__{objective}__{year}.csv.gz'
   if dest.exists():continue
   predictions=[];times=[]
   for seed in ([SEEDS[0]] if deterministic else SEEDS):
    start=time.perf_counter();pred,model,pre=fit(name,objective,seed,train,test);elapsed=time.perf_counter()-start;assert np.isfinite(pred).all()
    predictions.append(pred);times.append(elapsed)
    audit=dict(algorithm=name,objective=objective,year=year,seed=seed,train_rows=len(train),training_queries=train.groupby(c.GROUP,observed=True).ngroups,max_training_endpoint=train.endpoint.max(),test_rows=len(test),seconds=elapsed,train_key_hash=hashlib.sha256(pd.util.hash_pandas_object(train[c.KEYS],index=False).to_numpy().tobytes()).hexdigest(),params=model.get_params())
    c.save(f'tabular/{name}__{objective}__{year}__{seed}_audit.json',audit);audits.append(audit)
    if hasattr(model,'booster_'):model.booster_.save_model(str(folder/f'{name}__{objective}__{year}__{seed}.txt'))
    elif name=='catboost_yetirank':model.save_model(str(folder/f'{name}__{objective}__{year}__{seed}.cbm'))
    elif name=='xgboost_rankndcg':model.save_model(str(folder/f'{name}__{objective}__{year}__{seed}.json'))
    else:
     with (folder/f'{name}__{objective}__{year}__{seed}.pkl').open('wb') as stream:pickle.dump(dict(model=model,preprocessing=pre),stream,protocol=5)
    del model;gc.collect();print('FIT',name,objective,year,seed,round(elapsed,2),flush=True)
   z=test[c.KEYS].copy();z['score']=np.mean(predictions,axis=0);z['seed_sd']=np.std(predictions,axis=0)
   z.to_csv(dest,index=False);c.save(f'tabular/{name}__{objective}__{year}_receipt.json',dict(unique_fits=len(predictions),seeds=SEEDS if not deterministic else SEEDS[:1],deterministic=deterministic,mean_seed_sd=float(z.seed_sd.mean()),seconds=sum(times)))
  del train,test;gc.collect()
 c.save('tabular/'+name+'_complete.json',dict(algorithm=name,folds=6,objectives=2,complete=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('algorithm',choices=['ridge','elasticnet','hist_gradient_boosting','extra_trees','random_forest','lightgbm_regression','lightgbm_lambdarank','catboost_yetirank','xgboost_rankndcg']);a=p.parse_args();main(a.algorithm)
