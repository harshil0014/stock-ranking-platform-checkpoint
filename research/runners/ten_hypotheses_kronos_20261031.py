"""Frozen Kronos hidden features; explicitly contaminated historical diagnostic."""
from pathlib import Path
import sys,json,hashlib,os,argparse,subprocess
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/ten-hypotheses-20261031'
OUT=ROOT/'experiments/ten-hypotheses-20261031'
os.environ['HF_HOME']=str(WORK/'huggingface')
sys.path.insert(0,str(WORK/'Kronos'))
import numpy as np
import pandas as pd
import torch
from huggingface_hub import snapshot_download,HfApi
from model import Kronos,KronosTokenizer

def download():
    receipt={}
    receipt['_code']=dict(repository='https://github.com/shiyu-coder/Kronos',revision=subprocess.check_output(['git','-C',str(WORK/'Kronos'),'rev-parse','HEAD'],text=True).strip())
    for name in ['Kronos-mini','Kronos-Tokenizer-2k']:
        repo='NeoQuasar/'+name;info=HfApi().model_info(repo)
        path=snapshot_download(repo,revision=info.sha,local_dir=str(WORK/name),allow_patterns=['config.json','*.safetensors','README.md'])
        receipt[name]=dict(repo=repo,revision=info.sha,path=str(path))
    OUT.mkdir(parents=True,exist_ok=True);(OUT/'kronos_weight_receipt.json').write_text(json.dumps(receipt,indent=2))
    print('KRONOS WEIGHTS',receipt,flush=True)

def extract():
    if (OUT/'kronos_embeddings.npy').exists():return
    torch.manual_seed(20261031);torch.set_num_threads(3)
    tokenizer=KronosTokenizer.from_pretrained(str(WORK/'Kronos-Tokenizer-2k')).cuda().eval()
    model=Kronos.from_pretrained(str(WORK/'Kronos-mini')).cuda().eval()
    x=np.load(OUT/'kronos_inputs.npy',mmap_mode='r');values=[]
    # No calendar embedding: representation of the normalized OHLCV path only.
    with torch.inference_mode():
        for start in range(0,len(x),64):
            t=torch.tensor(np.array(x[start:start+64]),device='cuda')
            ids=tokenizer.encode(t,half=True)
            _,hidden=model.decode_s1(ids[0],ids[1])
            vec=torch.cat([hidden[:,-1],hidden.mean(1)],dim=1).float().cpu().numpy()
            values.append(vec)
            if start%2048==0:print('KRONOS EMBED',start,len(x),flush=True)
    e=np.concatenate(values);assert np.isfinite(e).all();np.save(OUT/'kronos_embeddings.npy',e)
    print('KRONOS COMPLETE',e.shape,flush=True)

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('stage',choices=['download','extract']);args=a.parse_args();globals()[args.stage]()
