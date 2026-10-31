"""Pinned Qlib/MASTER networks adapted to Indian past-only OHLCV and SIP labels."""
from pathlib import Path
import os,sys,ast,math,argparse,json,time,gc,hashlib
os.environ.setdefault('OMP_NUM_THREADS','3')
import numpy as np,pandas as pd,torch
from torch import nn
import champion_market_common_20261031 as c
CODE=c.ROOT/'research/literature/20261031/code';DEVICE=torch.device('cuda' if torch.cuda.is_available() else 'cpu');torch.set_num_threads(3)
SPECS={'gru':('pytorch_gru.py',['GRUModel']),'alstm':('pytorch_alstm.py',['ALSTMModel']),'transformer':('pytorch_transformer.py',['PositionalEncoding','Transformer']),'gats':('pytorch_gats.py',['GATModel']),'hist':('pytorch_hist.py',['HISTModel'])}

def source_classes(path,names):
 tree=ast.parse(path.read_text(encoding='utf-8'));nodes=[n for n in tree.body if isinstance(n,ast.ClassDef) and n.name in names]
 if len(nodes)!=len(names):raise ValueError('Pinned source classes differ')
 module=ast.Module(body=nodes,type_ignores=[]);env=dict(torch=torch,nn=nn,np=np,math=math,Linear=nn.Linear,Dropout=nn.Dropout,LayerNorm=nn.LayerNorm)
 exec(compile(module,str(path),'exec'),env)
 return env

def make_model(name):
 if name=='master':
  path=CODE/'SJTU-DMTai__MASTER__master.py';g=source_classes(path,['PositionalEncoding','SAttention','TAttention','Gate','TemporalAttention','MASTER']);return g['MASTER'](d_feat=10,d_model=32,t_nhead=4,s_nhead=4,gate_input_start_index=10,gate_input_end_index=22,T_dropout_rate=0.,S_dropout_rate=0.,beta=1.)
 suffix,classes=SPECS[name];path=CODE/('microsoft__qlib__qlib__contrib__model__'+suffix);g=source_classes(path,classes)
 if name=='transformer':return g['Transformer'](d_feat=10,d_model=32,nhead=4,num_layers=2,dropout=0.,device=DEVICE)
 return g[classes[-1]](d_feat=10,hidden_size=32,num_layers=2,dropout=0.)

def prepare():
 f=c.OUT/'sequence_panel.pkl.gz'
 if f.exists():return
 x=pd.read_pickle(c.OUT/'panel.pkl.gz',compression='gzip');valid=pd.read_pickle(c.OUT/'valid_panel.pkl.gz',compression='gzip')[c.KEYS+['return_target','balanced_target']]
 keys=pd.read_csv(c.old.OUT/'kronos_input_keys.csv');keys['sequence_row']=np.arange(len(keys));x=x.merge(keys,on=['isin','decision_date'],how='inner',validate='many_to_one').merge(valid,on=c.KEYS,how='left',validate='one_to_one');x=x.sort_values(['decision_date','profile_name','isin']).reset_index(drop=True)
 x['loss_eligible']=x.evidence_fraction.gt(0)&x.return_target.notna()&x.balanced_target.notna();x.to_pickle(f,compression='gzip')
 c.save('sequence_data_receipt.json',dict(rows=len(x),issuer_windows=len(keys),issuers=keys['isin'].nunique(),features='Last8of252-window normalizedOHLCV+tradedvalue6columns;4investorparameters;12cross-stock input-only market context features',loss_and_inference='Full feature-available512-source issuer cohort in inference; unknown/excluded outcomes retained as context, masked only in training loss and evaluation',source_sha256=hashlib.sha256((c.old.OUT/'kronos_inputs.npy').read_bytes()).hexdigest(),architecture='Original pinned model classes extracted unchanged by AST; Qlib plumbing and original Chinese data loaders excluded',adaptation='Indian SIP12-month labels and reducedOHLCV input, not Alpha158 or exact paper replication'))

def inputs(x,fitmask):
 candle=np.load(c.old.OUT/'kronos_inputs.npy',mmap_mode='r');a=np.asarray(candle[x.sequence_row.to_numpy(),-8:,:],dtype='float32')
 params=x[c.old.old.PARAMS].to_numpy('float32');a=np.concatenate([a,np.repeat(params[:,None,:],8,axis=1)],axis=2)
 mean=a[fitmask].mean(axis=(0,1));sd=a[fitmask].std(axis=(0,1));sd=np.where(sd>1e-6,sd,1.);a=np.nan_to_num((a-mean)/sd).astype('float32')
 concepts=pd.get_dummies(x.sector,dtype=float).to_numpy('float32');context=np.empty((len(x),12),dtype='float32')
 for _,ids in x.groupby(['decision_date','profile_name'],sort=True,observed=True).indices.items():
  raw=a[ids,-1,:6];context[ids]=np.r_[raw.mean(axis=0),raw.std(axis=0)]
 return a,context,concepts,dict(mean=mean.tolist(),sd=sd.tolist())

def forward(model,name,a,market,concepts):
 if name=='master':return model(torch.cat([a,market[:,None,:].repeat(1,a.shape[1],1)],dim=2)).reshape(-1)
 flat=a.transpose(1,2).reshape(len(a),-1)
 return (model(flat,concepts) if name=='hist' else model(flat)).reshape(-1)

def main(name):
 prepare();x=pd.read_pickle(c.OUT/'sequence_panel.pkl.gz',compression='gzip');folder=c.OUT/'sequence';folder.mkdir(exist_ok=True)
 for year in range(2020,2026):
  training=x.endpoint.lt(f'{year}-01-01')&x.loss_eligible;test=x.decision_date.str.startswith(str(year));dest=folder/f'{name}__balanced__{year}.csv.gz'
  if dest.exists():continue
  assert x.loc[training,'endpoint'].max()<f'{year}-01-01'
  a,market,concepts,scaler=inputs(x,training.to_numpy());train_groups=[]
  for key,ids in x.groupby(['decision_date','profile_name'],sort=True,observed=True).indices.items():
   eligible=training.iloc[ids].to_numpy()
   if eligible.sum()>=5:train_groups.append((ids,eligible))
  test_groups=list(x[test].groupby(['decision_date','profile_name'],sort=True,observed=True).groups.values());predictions=[]
  for seed in [20261031,20261032,20261033]:
   torch.manual_seed(seed);np.random.seed(seed);torch.cuda.manual_seed_all(seed);model=make_model(name).to(DEVICE);optim=torch.optim.Adam(model.parameters(),lr=.001,weight_decay=.0001);start=time.perf_counter();losses=[]
   aa_all=torch.tensor(a,device=DEVICE);mm_all=torch.tensor(market,device=DEVICE);cc_all=torch.tensor(concepts,device=DEVICE)
   target_all=torch.tensor(x.balanced_target.fillna(0).to_numpy('float32'),device=DEVICE)
   train_ids=np.flatnonzero(training.to_numpy())
   grouped=[(torch.tensor(ids,device=DEVICE),torch.tensor(eligible,device=DEVICE)) for ids,eligible in train_groups]
   for epoch in range(20):
    model.train();loss_sum=0.
    if name in ['gru','alstm','transformer']:
     ordered=np.random.permutation(train_ids);batches=[(torch.tensor(ordered[i:i+1024],device=DEVICE),None) for i in range(0,len(ordered),1024)]
    else:batches=[grouped[pos] for pos in np.random.permutation(len(grouped))]
    for ids,mask in batches:
     out=forward(model,name,aa_all[ids],mm_all[ids],cc_all[ids]);target=target_all[ids]
     loss=((out-target)**2).mean() if mask is None else ((out[mask]-target[mask])**2).mean()
     if not torch.isfinite(loss):raise ValueError('Nonfinite training loss')
     optim.zero_grad();loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),3.);optim.step();loss_sum+=float(loss.detach().cpu())
    losses.append(loss_sum/len(batches))
   model.eval();pred=pd.Series(index=x.index[test],dtype=float)
   with torch.no_grad():
    for ids in test_groups:
     ids=np.asarray(ids);out=forward(model,name,torch.tensor(a[ids],device=DEVICE),torch.tensor(market[ids],device=DEVICE),torch.tensor(concepts[ids],device=DEVICE));pred.loc[ids]=out.cpu().numpy()
   assert np.isfinite(pred).all();predictions.append(pred.to_numpy());seconds=time.perf_counter()-start
   torch.save(dict(state_dict=model.cpu().state_dict(),scaler=scaler,year=year,seed=seed),folder/f'{name}__balanced__{year}__{seed}.pt')
   c.save(f'sequence/{name}__balanced__{year}__{seed}_audit.json',dict(architecture=name,year=year,seed=seed,epochs=20,training_loss=losses,train_rows=int(training.sum()),training_date_profile_groups=len(train_groups),max_training_endpoint=x.loc[training,'endpoint'].max(),test_rows=int(test.sum()),seconds=seconds,device=str(DEVICE),pretrained_weights=False,original_class_source='Pinned MITQlib/MASTER, see code_receipts.json'))
   del model,optim,aa_all,mm_all,cc_all,target_all,grouped,batches;gc.collect();torch.cuda.empty_cache();print('SEQUENCE',name,year,seed,round(seconds,2),flush=True)
  z=x.loc[test,c.KEYS].copy();z['score']=np.mean(predictions,axis=0);z['seed_sd']=np.std(predictions,axis=0);z.to_csv(dest,index=False)
 c.save('sequence/'+name+'_complete.json',dict(architecture=name,folds=6,seeds=3,complete=True))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('architecture',choices=['gru','alstm','transformer','gats','hist','master']);p.add_argument('--lease-owner',action='store_true');p.add_argument('--cpu-threads',type=int,default=3);args=p.parse_args();torch.set_num_threads(args.cpu_threads)
 lease=c.ROOT/'work/champion-vs-market-20261031'/(args.architecture+'.sequence_external_job_lease')
 if lease.exists() and not args.lease_owner:
  start=time.time()
  while not (c.OUT/'sequence'/(args.architecture+'_complete.json')).exists():
   if time.time()-start>10800:raise RuntimeError('External sequence worker did not complete '+args.architecture)
   time.sleep(10)
 else:main(args.architecture)
