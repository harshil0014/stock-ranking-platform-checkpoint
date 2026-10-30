"""Exact TabPFN-v2 ensemble teacher inference; isolated dependencies, local CPU."""
import sys,os,json,time,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
os.environ['TABPFN_DISABLE_TELEMETRY']='1';os.environ['HF_HUB_DISABLE_TELEMETRY']='1'
sys.path.insert(0,str(ROOT/'experiments/premodel_dependencies_20261010'))
import torch,numpy as np,pandas as pd
from tabpfn import TabPFNRegressor

def run(prefix):
    start=time.monotonic();torch.set_num_threads(3)
    t=pd.read_csv(str(prefix)+'_context.csv');x=pd.read_csv(str(prefix)+'_inputs.csv');cols=x.columns.tolist()
    checkpoint=ROOT/'experiments/sector-learned-blend-20261010/tabpfn-v2-regressor.ckpt'
    model=TabPFNRegressor(n_estimators=2,device='cpu',n_jobs=1,model_path=checkpoint,random_state=20261011,fit_mode='fit_with_cache')
    model.fit(t[cols].to_numpy(),t.teacher_target.to_numpy());pred=[]
    for i in range(0,len(x),256):
        pred.append(model.predict(x.iloc[i:i+256].to_numpy()).astype(float))
        if i%1024==0:print('TEACHER',prefix.name,i,len(x),round(time.monotonic()-start,1),flush=True)
    pred=np.concatenate(pred);assert np.isfinite(pred).all()
    replay=model.predict(x.iloc[:256].to_numpy()).astype(float);np.testing.assert_allclose(pred[:256],replay,atol=1e-7,rtol=0)
    np.savez_compressed(prefix.with_suffix('.npz'),predictions=pred)
    audit={'rows':len(x),'context_rows':len(t),'features':cols,'estimators':2,'checkpoint_sha256':hashlib.sha256(checkpoint.read_bytes()).hexdigest(),'seconds':time.monotonic()-start,'replay_256_max_error':float(np.max(np.abs(pred[:256]-replay))),'context_sha256':hashlib.sha256(Path(str(prefix)+'_context.csv').read_bytes()).hexdigest(),'inputs_sha256':hashlib.sha256(Path(str(prefix)+'_inputs.csv').read_bytes()).hexdigest(),'mode':'DIRECT_ENSEMBLE_NO_GRID','telemetry_disabled':True}
    Path(str(prefix)+'_audit.json').write_text(json.dumps(audit,indent=2));print('TEACHER COMPLETE',prefix.name,audit['seconds'],flush=True)

if __name__=='__main__':run(Path(sys.argv[1]))
