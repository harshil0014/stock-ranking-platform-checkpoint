"""Same OHLCV/profile/context inputs and mature row support as the neural cohort."""
import os
os.environ.setdefault('OPENBLAS_NUM_THREADS','3')
import numpy as np,pandas as pd,lightgbm as lgb,json
from sklearn.linear_model import Ridge
import champion_market_common_20261031 as c

def main():
 x=pd.read_pickle(c.OUT/'sequence_panel.pkl.gz',compression='gzip');raw=np.load(c.old.OUT/'kronos_inputs.npy',mmap_mode='r');a=np.asarray(raw[x.sequence_row.to_numpy(),-8:,:],dtype='float32');params=x[c.old.old.PARAMS].to_numpy('float32');a=np.concatenate([a,np.repeat(params[:,None,:],8,axis=1)],axis=2)
 context=np.empty((len(x),12),dtype='float32')
 for _,ids in x.groupby(['decision_date','profile_name'],sort=True,observed=True).indices.items():
  v=a[ids,-1,:6];context[ids]=np.r_[v.mean(0),v.std(0)]
 a=np.c_[a.reshape(len(x),-1),context];folder=c.OUT/'sequence'
 for year in range(2020,2026):
  train=(x.endpoint.lt(f'{year}-01-01')&x.loss_eligible).to_numpy();test=x.decision_date.str.startswith(str(year)).to_numpy();mean=np.nanmean(a[train],axis=0);sd=np.nanstd(a[train],axis=0);sd=np.where(sd>1e-6,sd,1.);Z=np.nan_to_num((a-mean)/sd);y=x.loc[train,'balanced_target'].to_numpy(float)
  for name,model in [('matched_ridge',Ridge(alpha=100)),('matched_lightgbm',lgb.LGBMRegressor(n_estimators=120,num_leaves=15,max_depth=5,min_child_samples=200,reg_lambda=30,learning_rate=.04,n_jobs=3,random_state=20261031,verbosity=-1,deterministic=True,force_col_wise=True))]:
   model.fit(Z[train],y);z=x.loc[test,c.KEYS].copy();z['score']=model.predict(Z[test]);z['seed_sd']=0.;z.to_csv(folder/f'{name}__balanced__{year}.csv.gz',index=False)
   c.save(f'sequence/{name}__balanced__{year}_audit.json',dict(train_rows=int(train.sum()),max_training_endpoint=x.loc[train,'endpoint'].max(),same_features='8x10OHLCV+profile and12market-context columns; same complete cohort contexts, finite mature training loss rows; deterministic fit; equal row loss like independent neural models',params=model.get_params()))
  print('MATCHED CONTROLS',year,flush=True)
if __name__=='__main__':main()
