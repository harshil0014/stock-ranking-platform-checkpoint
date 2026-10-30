"""Isolated TabPFN-v2 dependencies; pretrained inference with audited grid approximation."""
import os,sys,json,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.environ['TABPFN_DISABLE_TELEMETRY']='1'
os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
sys.path.insert(0,str(ROOT/'experiments/premodel_dependencies_20261010'))
import numpy as np
import pandas as pd
import torch
from scipy.interpolate import RegularGridInterpolator
from tabpfn import TabPFNRegressor

def run(prefix,verify_only=False):
    torch.set_num_threads(3)
    start=time.monotonic()
    cols=['guarded_previous','rank_xendcg_balanced']
    t=pd.read_csv(str(prefix)+'_context.csv');x=pd.read_csv(str(prefix)+'_inputs.csv')[cols].to_numpy()
    checkpoint=prefix.parent/'tabpfn-v2-regressor.ckpt'
    m=TabPFNRegressor(n_estimators=1,device='cpu',model_path=checkpoint,n_jobs=1,random_state=20261010,fit_mode='fit_with_cache')
    m.fit(t[cols].to_numpy(),t.balanced_target.to_numpy())
    print('TABPFN LOADED',prefix.name,'context',len(t),flush=True)
    def predict(v):
        out=[]
        for i in range(0,len(v),256):
            out.append(m.predict(v[i:i+256]))
            if len(v)>20000 and i%20480==0:print('DIRECT PROGRESS',prefix.name,i,len(v),flush=True)
        return np.concatenate(out)
    if verify_only:
        direct=predict(x)
        with np.load(prefix.with_suffix('.npz')) as saved:approx=saved['predictions']
        errors=np.abs(direct-approx)
        np.savez_compressed(str(prefix)+'_direct_replay.npz',predictions=direct)
        doc={'rows':len(x),'mean_absolute_error':float(errors.mean()),'max_absolute_error':float(errors.max()),'seconds':time.monotonic()-start}
        Path(str(prefix)+'_direct_replay.json').write_text(json.dumps(doc,indent=2))
        print('DIRECT REPLAY',prefix.name,doc,flush=True)
        return
    rng=np.random.default_rng(20261010)
    # Training inputs only: grid and quality decisions cannot use later test dates.
    tx=t[cols].to_numpy()
    probes=tx[rng.choice(len(tx),min(128,len(tx)),replace=False)]
    direct=predict(probes)
    lo=np.minimum(np.array([-1.,0.]),tx.min(axis=0));hi=np.maximum(np.array([1.,1.]),tx.max(axis=0))
    audit=[]
    for size in [33,65,129]:
        axes=[np.linspace(a,b,size) for a,b in zip(lo,hi)]
        mesh=np.stack(np.meshgrid(*axes,indexing='ij'),axis=-1).reshape(-1,2)
        values=predict(mesh).reshape(size,size)
        fn=RegularGridInterpolator(tuple(axes),values,bounds_error=True)
        errors=np.abs(fn(probes)-direct)
        audit.append(dict(grid=size,probe_mae=float(errors.mean()),probe_max=float(errors.max())))
        print('TABPFN GRID',prefix.name,audit[-1],round(time.monotonic()-start,1),flush=True)
        if errors.mean()<=.003 and errors.max()<=.02:break
    if errors.mean()>.003 or errors.max()>.02:
        # Quality gate cannot silently accept a poor approximation.
        predictions=predict(x);mode='DIRECT_GRID_REJECTED'
    else:
        inside=((x>=lo)&(x<=hi)).all(axis=1)
        predictions=np.empty(len(x));predictions[inside]=fn(x[inside])
        if (~inside).any():predictions[~inside]=predict(x[~inside])
        mode='BILINEAR_GRID'
    assert np.isfinite(predictions).all()
    np.savez_compressed(prefix.with_suffix('.npz'),predictions=predictions,axis0=axes[0],axis1=axes[1],values=values,probes=probes,direct=direct,inside=((x>=lo)&(x<=hi)).all(axis=1))
    doc={'mode':mode,'grid_trials':audit,'rows':len(x),'context_rows':len(t),'n_estimators':1,'seconds':time.monotonic()-start,'torch':torch.__version__,'device':'cpu','tabpfn':'2.2.1','checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),'context_sha256':hashlib.sha256(Path(str(prefix)+'_context.csv').read_bytes()).hexdigest(),'inputs_sha256':hashlib.sha256(Path(str(prefix)+'_inputs.csv').read_bytes()).hexdigest(),'telemetry_disabled':True}
    Path(str(prefix)+'_audit.json').write_text(json.dumps(doc,indent=2))
    print('TABPFN COMPLETE',prefix.name,doc['seconds'],flush=True)

if __name__=='__main__':run(Path(sys.argv[1]),'--verify-only' in sys.argv)
