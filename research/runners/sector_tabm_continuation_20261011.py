"""Isolated fixed-budget neural continuation; annual outcome cutoffs retained."""
import json
import pickle
import sys
import time
from pathlib import Path
import numpy as np
import pandas as pd
import torch
import sector_specialist_ensemble_20261011 as s

OUT=s.p.ROOT/'experiments/sector-tabm-continuation-20261011'
FAMILIES=['tabm_compact','tabm_embedded']
CHECKPOINTS=[24,48]
NAMES=[f'{family}_e{epoch}_{target}_w{weight}' for family in FAMILIES for epoch in CHECKPOINTS for target in s.TARGETS+['balanced'] for weight in [.1,.3,1.]]


def write(name,value):
    (OUT/name).write_text(json.dumps(value,indent=2),encoding='utf-8')


def protocol():
    OUT.mkdir(exist_ok=True)
    doc=dict(families=FAMILIES,checkpoints_total_epochs=CHECKPOINTS,initial_epochs=12,
        hypothesis='Original twelve-epoch training losses continued decreasing; that alone does not prove underfitting. Compare fixed additional training budgets before rejecting TabM. No inference labels control optimization or stopping.',
        training='Load original frozen model/preprocessor, verify hashes and exact training identities. Restart AdamW at lr.0003, weight_decay.001; 36additional epochs, checkpoints after12/36. Batch4096, query-weighted three-head MSE, clip_grad_norm1. Seed20261011. Same original annual endpoint cutoff and full valid training rows.',
        controls='Original CPU twelve-epoch predictions remain controls. GPU PyTorch2.11 versus original CPU2.12 is disclosed; before optimization compare GPU inference to saved base on each annual query and record native differences. This is a continuation with a new optimizer, not uninterrupted original training.',
        scoring='Sector percentiles per target; balanced=.5return+.25risk+.25goal retained as a target-tradeoff hypothesis. Weights .1/.3/1 relative to reference percentile; no company-specific tuning. Missing primary evidence falls back to reference.',
        selection='Development2020-23 only: lock highest expanded raw Top3 rankIC per family/checkpoint; tie-break non-return regressions then name. Also lock candidate with fewest development Top3 non-return regressions. MeanXIRR selection weight0. Recent2024-25 exposed; no fresh validation.',
        status='Adaptive research after viewing original specialist outcomes. Full gates, global calibration sensitivity and financial review still required.',
        sources=['https://github.com/yandex-research/tabm','https://pytorch.org/get-started/locally/'],production_change=False,fresh_validation=False)
    path=OUT/'protocol.json'
    if path.exists():
        assert json.loads(path.read_text())==doc
    else:
        write(path.name,doc)


def predict(model,values):
    model.eval();out=[]
    with torch.no_grad():
        for batch in values.split(2048):
            out.append(model(batch).mean(1).cpu().numpy())
    return np.concatenate(out)


def learn():
    protocol()
    assert torch.cuda.is_available(),'Requires verified isolated CUDA environment'
    torch.set_num_threads(2)
    torch.backends.cuda.matmul.allow_tf32=False
    torch.backends.cudnn.allow_tf32=False
    device=torch.device('cuda')
    x=s.panel();anchor=s.h.load()
    for year in [2020,2021,2022,2023,2024,2025,'current']:
        cutoff=s.p.ASOF if year=='current' else f'{year}-01-01'
        t=s.training(x,cutoff)
        pd.testing.assert_frame_equal(pd.read_csv(s.OUT/f'training_identity_{year}.csv.gz'),t[s.p.KEYS+['endpoint','sector']],check_dtype=False)
        z=s.h.current() if year=='current' else x[x.decision_date.str.startswith(str(year))].merge(anchor[s.p.KEYS+[s.h.ANCHOR,'champion_percentile']],on=s.p.KEYS,validate='one_to_one')
        pred=z[s.p.KEYS+['sector',s.h.ANCHOR,'champion_percentile','evidence_fraction']].copy()
        y=torch.tensor(t[[name+'_target' for name in s.TARGETS]].to_numpy(),dtype=torch.float32,device=device)
        weight=torch.tensor(t.weight.to_numpy(),dtype=torch.float32,device=device)
        for family in FAMILIES:
            receipt=OUT/f'{family}_{year}_audit.json'
            rawpath=OUT/f'{family}_{year}_raw.csv.gz'
            if receipt.exists():
                audit=json.loads(receipt.read_text())
                assert audit['raw_sha256']==s.digest(rawpath)
                raw=pd.read_csv(rawpath)
                pd.testing.assert_frame_equal(raw[s.p.KEYS],z[s.p.KEYS].reset_index(drop=True),check_dtype=False)
            else:
                torch.manual_seed(20261011);torch.cuda.manual_seed_all(20261011)
                cols=s.FEATURES[family];source=s.OUT/f'{family}_{year}.pt'
                old=json.loads((s.OUT/f'audit_{family}_{year}.json').read_text())
                assert old['model_sha256']==s.digest(source)
                with (s.OUT/f'{family}_{year}_prep.pkl').open('rb') as stream:
                    prep=pickle.load(stream)
                a=torch.tensor(prep.transform(t[cols]),dtype=torch.float32,device=device)
                b=torch.tensor(prep.transform(z[cols]),dtype=torch.float32,device=device)
                model=s.torch_model(len(cols),family=='tabm_embedded').to(device)
                model.load_state_dict(torch.load(source,map_location=device,weights_only=True))
                saved=pd.read_csv(s.OUT/f'raw_{family}_{year}.csv.gz')[s.TARGETS].to_numpy().astype(np.float32)
                start_error=float(np.max(abs(predict(model,b)-saved)))
                assert start_error<1e-4,(family,year,start_error)
                optimizer=torch.optim.AdamW(model.parameters(),lr=.0003,weight_decay=.001)
                history=[];artifacts={};started=time.time()
                raw=z[s.p.KEYS].reset_index(drop=True).copy()
                for epoch in range(13,49):
                    model.train();indices=torch.randperm(len(a),device=device);total=0.
                    for ids in indices.split(4096):
                        optimizer.zero_grad();value=model(a[ids]);loss=((value-y[ids,None,:]).square().mean((1,2))*weight[ids]).mean()
                        assert torch.isfinite(loss)
                        loss.backward();torch.nn.utils.clip_grad_norm_(model.parameters(),1.);optimizer.step()
                        total+=float(loss.detach())*len(ids)
                    history.append(dict(epoch=epoch,training_loss=total/len(a)))
                    print('EPOCH',year,family,epoch,history[-1]['training_loss'],flush=True)
                    if epoch in CHECKPOINTS:
                        output=predict(model,b);path=OUT/f'{family}_e{epoch}_{year}.pt'
                        torch.save({key:value.cpu() for key,value in model.state_dict().items()},path)
                        replay=s.torch_model(len(cols),family=='tabm_embedded').to(device)
                        replay.load_state_dict(torch.load(path,map_location=device,weights_only=True))
                        np.testing.assert_array_equal(output,predict(replay,b));del replay
                        artifacts[path.name]=s.digest(path)
                        for j,target in enumerate(s.TARGETS):
                            raw[f'e{epoch}_{target}']=output[:,j]
                raw.to_csv(rawpath,index=False)
                write(receipt.name,dict(family=family,year=year,cutoff=cutoff,max_endpoint=t.endpoint.max(),training_rows=len(t),training_identity_sha256=s.digest(s.OUT/f'training_identity_{year}.csv.gz'),source_model_sha256=s.digest(source),preprocessor_sha256=s.digest(s.OUT/f'{family}_{year}_prep.pkl'),gpu_baseline_max_error=start_error,torch_version=torch.__version__,gpu=torch.cuda.get_device_name(),history=history,models_sha256=artifacts,raw_sha256=s.digest(rawpath),seconds=time.time()-started))
                del a,b,model,optimizer;torch.cuda.empty_cache()
            for epoch in CHECKPOINTS:
                basis={target:pd.Series(raw[f'e{epoch}_{target}'].to_numpy(),index=z.index).groupby([z[k] for k in s.GROUP]).rank(pct=True).to_numpy() for target in s.TARGETS}
                basis['balanced']=.5*basis['return']+.25*basis['risk']+.25*basis['goal']
                for target,values in basis.items():
                    for strength in [.1,.3,1.]:
                        pred[f'{family}_e{epoch}_{target}_w{strength}']=z.champion_percentile+strength*np.where(z.evidence_fraction.gt(0),values-z.champion_percentile,0.)
        assert np.isfinite(pred[NAMES]).all().all()
        pred.to_csv(OUT/f'predictions_{year}.csv.gz',index=False)
        if year=='current':
            cur=pred.merge(z[['isin','ticker','company','input_status','rebuilt_input_confidence','rebuilt_sector_rank']],on='isin',validate='one_to_one')
            for name in NAMES:
                cur[name+'_rank']=cur[name].groupby(cur.sector).rank(method='min',ascending=False)
            cur.to_csv(OUT/'all_4436_all_candidates.csv',index=False)
        print('YEAR COMPLETE',year,len(pred),flush=True)


if __name__=='__main__':
    {'protocol':protocol,'learn':learn}[sys.argv[1]]()
