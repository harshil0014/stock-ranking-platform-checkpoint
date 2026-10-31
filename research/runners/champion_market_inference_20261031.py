"""Replay saved tabular fits on the complete feature cohort, without outcome filtering."""
import sys,pickle,json,gc,argparse
import numpy as np,pandas as pd
import champion_market_tabular_20261031 as t
c=t.c

def main(allow_incomplete=False):
 x=pd.read_pickle(c.OUT/'panel.pkl.gz',compression='gzip');valid=pd.read_pickle(c.OUT/'valid_panel.pkl.gz',compression='gzip');folder=c.OUT/'inference';folder.mkdir(exist_ok=True);audits=[]
 for year in range(2020,2026):
  train=c.sample_queries(valid[valid.endpoint.lt(f'{year}-01-01')]);test=x[x.decision_date.str.startswith(str(year))]
  for name in json.loads((c.OUT/'protocol.json').read_text())['ml_algorithms']:
   for target in ['return','balanced']:
    dest=folder/f'{name}__{target}__{year}.csv.gz'
    if dest.exists():continue
    receipt=c.OUT/'tabular'/f'{name}__{target}__{year}_receipt.json'
    if not receipt.exists():
     if allow_incomplete:continue
     raise RuntimeError('Incomplete training '+str(receipt))
    _,Z,pre=t.transform_fit(train,test,name in ['ridge','elasticnet']);preds=[]
    for seed in json.loads(receipt.read_text())['seeds']:
     stem=c.OUT/'tabular'/f'{name}__{target}__{year}__{seed}'
     if name.startswith('lightgbm'):model=t.lgb.Booster(model_file=str(stem)+'.txt',params={'num_threads':3})
     elif name=='catboost_yetirank':model=t.CatBoostRanker();model.load_model(str(stem)+'.cbm')
     elif name=='xgboost_rankndcg':model=t.XGBRanker();model.load_model(str(stem)+'.json')
     else:
      with open(str(stem)+'.pkl','rb') as f:saved=pickle.load(f)
      model=saved['model']
      for key in pre:np.testing.assert_allclose(pre[key],saved['preprocessing'][key],rtol=0,atol=0)
     prediction=model.predict(Z,thread_count=3) if name=='catboost_yetirank' else model.predict(Z,num_threads=3) if name.startswith('lightgbm') else model.predict(Z)
     preds.append(prediction);del model;gc.collect()
    z=test[c.KEYS].copy();z['score']=np.mean(preds,axis=0);z['seed_sd']=np.std(preds,axis=0)
    old=pd.read_csv(c.OUT/'tabular'/dest.name);matched=old.merge(z,on=c.KEYS,validate='one_to_one');error=float(np.abs(matched.score_x-matched.score_y).max());np.testing.assert_allclose(matched.score_x,matched.score_y,rtol=1e-6,atol=1e-6,err_msg=name+' float32 replay')
    z.to_csv(dest,index=False);audit=dict(model=name,target=target,year=year,rows=len(z),matched_valid_rows=len(matched),max_replay_error=error);c.save('inference/'+dest.name.replace('.csv.gz','_replay.json'),audit);print('REPLAY',name,target,year,len(z),error,flush=True)
 audits=[json.loads(p.read_text()) for p in sorted(folder.glob('*_replay.json'))];c.save('inference/replay_audit.json',audits)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--allow-incomplete',action='store_true');main(p.parse_args().allow_incomplete)
