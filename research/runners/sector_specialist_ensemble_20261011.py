"""Independent open-source return/risk/goal specialists, trained chronologically."""
import sys,json,hashlib,time,pickle,gc
from pathlib import Path
import numpy as np
import pandas as pd
import sector_tabpfn_hybrid_20261011 as h
p=h.p;ROOT=p.ROOT;OUT=ROOT/'experiments/sector-specialist-ensemble-20261011'
sys.path.insert(0,str(ROOT/'experiments/sector_ensemble_dependencies_20261011'))
from interpret.glassbox import ExplainableBoostingRegressor
from sklearn.ensemble import ExtraTreesRegressor
from sklearn.linear_model import Ridge
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import make_pipeline
import torch
from tabm import TabM
from rtdl_num_embeddings import LinearReLUEmbeddings
GROUP=['decision_date','profile_name','sector']
TARGETS=['return','risk','goal']
FAMILIES=['ebm_additive','ebm_interactions','extra_trees','ridge','tabm_compact','tabm_embedded']
SMALL=[f for f in h.FEATURES if f not in ['champion_percentile','guarded_percentile','rank_xendcg_balanced']]
FEATURES={f:(SMALL if f in ['ebm_additive','ebm_interactions','tabm_compact'] else p.COLS) for f in FAMILIES}
WEIGHTS=[.1,.3,1.]
def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(name,data):(OUT/name).write_text(json.dumps(data,indent=2),encoding='utf-8')

def protocol():
    OUT.mkdir(exist_ok=True)
    doc=dict(families=FAMILIES,features=FEATURES,targets=TARGETS,blend_weights=WEIGHTS,
      training='Use the entire guarded prepared panel, including pre-2020 history, with endpoint strictly before January1 of each annual2020-2025 fit; current cutoff2026-10-03. Known sectors, >=5 outcome-covered peers, usable features. Equal query weight. No champion predictions or company identities as model inputs. Target sector percentiles formed within the same historical query.',
      labels='Three heads: subsequent SIP-XIRR percentile, drawdown percentile, inverse goal-shortfall percentile. Balanced diagnostic=.5 return+.25 risk+.25 goal; these are objective tradeoff hypotheses, not discovered factor weights. Mean XIRR has zero selection weight.',
      models={'EBM':'interpret-core0.7.8, additive and8 learned interactions,15inputs,300rounds,LR.025,1bag,validation_size0,no early stopping,no random validation,minleaf40,L2=5,maxbins128. Three separate heads.',
      'ExtraTrees':'sklearn,128trees,depth10,minleaf120,maxfeatures.7,4threads,multioutput70inputs',
      'Ridge':'median impute,standardize from training only,alpha1000,multioutput70inputs',
      'TabM':'official tabm0.0.3,PyTorchCPU4threads,k4,2blocks,width64,dropout.1,AdamWlr.001,weightdecay.001,12epochs,batch2048,query-weighted3headMSE. Compact15inputs; embedded70inputs with LinearReLU embeddings dimension8. Median/scaling fitted on training only. Fixed predeclared epochs, no random temporal validation. Original architecture adapted, not a literal paper replication.'},
      scoring='Sector percentiles of independent specialist predictions. Test standalone specialists, champion blends, target combinations and cross-family combinations. Missing usable price evidence retains champion sector percentile. No false complete-evidence claim.',
      selection='Development2020-2023 only. Primary whole-sector rankIC, Top3 risk/achievement/shortfall/NDCG regression count secondary; mean XIRR excluded. Save full profile/sector/worst-case diagnostics. Later2024-25 dates are exposed research. Promotion requires broad verified superiority and stock-review evidence, not a flattering aggregate.',
      constraints='No production changes, no remote deployment, no current fundamentals in historical training. Current evidence and Sir are independent diagnostics, never target labels.',
      sources=['https://github.com/yandex-research/tabm','https://arxiv.org/abs/2410.24210','https://interpret.ml/docs/ebm.html','https://scikit-learn.org/stable/modules/generated/sklearn.ensemble.ExtraTreesRegressor.html','https://proceedings.neurips.cc/paper_files/paper/2022/hash/0378c7692da36807bdec87ab043cdadc-Abstract-Datasets_and_Benchmarks.html'],fresh_validation=False)
    path=OUT/'protocol.json'
    if path.exists():assert json.loads(path.read_text())==doc
    else:write('protocol.json',doc)

def panel():
    x=pd.read_pickle(p.OUT/'prepared.pkl.gz',compression='gzip')
    assert not x.duplicated(p.KEYS).any()
    return x

def training(x,cutoff):
    t=x[x.endpoint.lt(cutoff)&x.sector.ne('Unclassified')].dropna(subset=['future_xirr','future_drawdown','future_shortfall']).copy()
    t=t[t.groupby(GROUP)['isin'].transform('size').ge(5)].copy();g=t.groupby(GROUP)
    t['return_target']=g.future_xirr.rank(pct=True);t['risk_target']=g.future_drawdown.rank(pct=True);t['goal_target']=g.future_shortfall.rank(pct=True,ascending=False)
    t=t[t.evidence_fraction.gt(0)].copy();t=t[t.groupby(GROUP)['isin'].transform('size').ge(5)].copy()
    t['weight']=1/t.groupby(GROUP)['isin'].transform('size');t.weight/=t.weight.mean()
    assert len(t)>0 and t.endpoint.max()<cutoff
    return t.sort_values(GROUP+['isin']).reset_index(drop=True)

def torch_model(n,embedded):
    return TabM.make(n_num_features=n,d_out=3,k=4,n_blocks=2,d_block=64,dropout=.1,num_embeddings=LinearReLUEmbeddings(n,8) if embedded else None)

def neural_predict(model,prep,z):
    a=torch.tensor(prep.transform(z),dtype=torch.float32);out=[];model.eval()
    with torch.no_grad():
        for batch in a.split(2048):out.append(model(batch).mean(1).numpy())
    return np.concatenate(out)

def neural_fit(t,cols,y,embedded,year):
    torch.set_num_threads(4);torch.manual_seed(20261011)
    prep=make_pipeline(SimpleImputer(strategy='median',keep_empty_features=True),StandardScaler())
    a=torch.tensor(prep.fit_transform(t[cols]),dtype=torch.float32)
    labels=torch.tensor(y,dtype=torch.float32);weight=torch.tensor(t.weight.to_numpy(),dtype=torch.float32)
    model=torch_model(len(cols),embedded);opt=torch.optim.AdamW(model.parameters(),lr=.001,weight_decay=.001)
    history=[]
    for epoch in range(12):
        model.train();indices=torch.randperm(len(a));total=0.
        for ids in indices.split(2048):
            opt.zero_grad();pred=model(a[ids]);loss=((pred-labels[ids,None,:]).square().mean((1,2))*weight[ids]).mean()
            assert torch.isfinite(loss);loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),5.);opt.step();total+=float(loss.detach())*len(ids)
        history.append(total/len(a));print('EPOCH',year,'embedded' if embedded else 'compact',epoch+1,history[-1],flush=True)
    return model,prep,history

def learn():
    protocol();x=panel();audit=[]
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        cutoff=p.ASOF if year=='current' else f'{year}-01-01';t=training(x,cutoff)
        z=h.current() if year=='current' else x[x.decision_date.str.startswith(str(year))].copy()
        identity=OUT/f'training_identity_{year}.csv.gz'
        if not identity.exists():t[p.KEYS+['endpoint','sector']].to_csv(identity,index=False)
        y=t[[c+'_target' for c in TARGETS]].to_numpy();pred=z[p.KEYS+['sector','evidence_fraction']].copy()
        for family in FAMILIES:
            output=OUT/f'raw_{family}_{year}.csv.gz';receipt=OUT/f'audit_{family}_{year}.json'
            cols=FEATURES[family];started=time.time()
            if output.exists() and receipt.exists():
                info=json.loads(receipt.read_text());assert info['prediction_sha256']==digest(output)
                raw=pd.read_csv(output);assert raw[p.KEYS].equals(z[p.KEYS].reset_index(drop=True));result=raw[TARGETS].to_numpy()
            else:
                path=OUT/f'{family}_{year}.pkl';history=None
                if family.startswith('ebm'):
                    models=[]
                    for j,target in enumerate(TARGETS):
                        model=ExplainableBoostingRegressor(interactions=0 if family=='ebm_additive' else 8,max_bins=128,max_interaction_bins=32,outer_bags=1,validation_size=0,early_stopping_rounds=0,max_rounds=300,smoothing_rounds=100,interaction_smoothing_rounds=50,learning_rate=.025,min_samples_leaf=40,reg_lambda=5,n_jobs=4,random_state=20261011)
                        model.fit(t[cols],y[:,j],sample_weight=t.weight);models.append(model);print('HEAD',year,family,target,flush=True)
                    with path.open('wb') as f:pickle.dump(models,f)
                    result=np.column_stack([m.predict(z[cols]) for m in models])
                    with path.open('rb') as f:models=pickle.load(f)
                    replay=np.column_stack([m.predict(z[cols]) for m in models])
                elif family in ['extra_trees','ridge']:
                    prep=[SimpleImputer(strategy='median',keep_empty_features=True)]
                    if family=='ridge':prep.append(StandardScaler())
                    estimator=ExtraTreesRegressor(n_estimators=128,max_depth=10,min_samples_leaf=120,max_features=.7,n_jobs=4,random_state=20261011) if family=='extra_trees' else Ridge(alpha=1000)
                    model=make_pipeline(*prep,estimator);model.fit(t[cols],y,**{model.steps[-1][0]+'__sample_weight':t.weight.to_numpy()})
                    with path.open('wb') as f:pickle.dump(model,f)
                    result=model.predict(z[cols])
                    with path.open('rb') as f:model=pickle.load(f)
                    replay=model.predict(z[cols])
                else:
                    embedded=family=='tabm_embedded';model,prep,history=neural_fit(t,cols,y,embedded,year)
                    path=OUT/f'{family}_{year}.pt';torch.save(model.state_dict(),path)
                    with (OUT/f'{family}_{year}_prep.pkl').open('wb') as f:pickle.dump(prep,f)
                    result=neural_predict(model,prep,z[cols]);model=torch_model(len(cols),embedded);model.load_state_dict(torch.load(path,weights_only=True))
                    with (OUT/f'{family}_{year}_prep.pkl').open('rb') as f:prep=pickle.load(f)
                    replay=neural_predict(model,prep,z[cols])
                error=float(np.max(np.abs(result-replay)));assert error<1e-7 and np.isfinite(result).all()
                raw=z[p.KEYS].reset_index(drop=True).copy()
                for j,target in enumerate(TARGETS):raw[target]=result[:,j]
                raw.to_csv(output,index=False)
                info=dict(year=year,family=family,training_rows=len(t),training_queries=t.groupby(GROUP).ngroups,training_min_date=t.decision_date.min(),maximum_endpoint=t.endpoint.max(),cutoff=cutoff,inference_rows=len(z),seconds=time.time()-started,replay_max_error=error,model_sha256=digest(path),prediction_sha256=digest(output),training_identity_sha256=digest(identity),training_loss=history)
                write(receipt.name,info)
            for j,target in enumerate(TARGETS):pred[family+'_'+target]=result[:,j]
            audit.append(info);pd.DataFrame([{k:v for k,v in a.items() if k!='training_loss'} for a in audit]).to_csv(OUT/'training_audit.csv',index=False)
            print('COMPLETE',year,family,len(t),round(info['seconds'],1),flush=True);gc.collect()
        pred.to_csv(OUT/f'predictions_{year}.csv.gz',index=False)
        if year=='current':assert len(pred)==4436 and pred['isin'].is_unique

if __name__=='__main__':
    if sys.argv[1]=='learn':learn()
    elif sys.argv[1]=='protocol':protocol()
