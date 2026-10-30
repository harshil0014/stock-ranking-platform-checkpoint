"""Verify the live isolated install, then train/evaluate registered neural budgets."""
import json
import subprocess
import sys
import time
from pathlib import Path
import psutil
from resume_major_research_20261011 import identity,wait_for,digest

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/sector-tabm-continuation-20261011'
PYTHON=ROOT/'.venv-gpu-research-20261011/Scripts/python.exe'


def stage(script,arg):
    source=ROOT/'research/runners'/script
    receipt=OUT/f'{script}_{arg}.done.json'
    if receipt.exists():
        saved=json.loads(receipt.read_text())
        assert saved['source_sha256']==digest(source)
        return
    log=OUT/f'{script}_{arg}.{time.time_ns()}.log'
    command=[str(PYTHON),'-W','ignore',str(source),arg]
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    assert result.returncode==0,(command,result.returncode,str(log))
    receipt.write_text(json.dumps(dict(command=command,exit_code=0,source_sha256=digest(source),log=str(log),log_sha256=digest(log)),indent=2),encoding='utf-8')
    print('COMPLETE',script,arg,flush=True)


if __name__=='__main__':
    info=identity(int(sys.argv[1]),'pip')
    assert any('cu128' in value for value in info['command'])
    OUT.mkdir(exist_ok=True)
    (OUT/'pipeline_process.json').write_text(json.dumps(dict(pid=psutil.Process().pid,created=psutil.Process().create_time(),dependency=info),indent=2))
    wait_for(info)
    check="import torch,json;assert torch.cuda.is_available();x=torch.arange(16,device='cuda',dtype=torch.float32);assert x.square().sum().item()==1240;print(json.dumps(dict(torch=torch.__version__,cuda=torch.version.cuda,gpu=torch.cuda.get_device_name(),tensor_check=True)))"
    result=subprocess.run([str(PYTHON),'-c',check],cwd=ROOT,capture_output=True,text=True)
    assert result.returncode==0,(result.stdout,result.stderr)
    receipt=json.loads(result.stdout.strip())
    (OUT/'gpu_verification.json').write_text(json.dumps(receipt,indent=2))
    print('GPU VERIFIED',receipt,flush=True)
    stage('sector_tabm_continuation_20261011.py','learn')
    stage('evaluate_tabm_continuation_20261011.py','development')
    stage('evaluate_tabm_continuation_20261011.py','recent')
    (OUT/'pipeline_complete.json').write_text(json.dumps(dict(fits_and_evaluation_complete=True,full_goal_complete=False,remaining='Independent replay, full historical/current financial/robustness comparisons, matched original12epoch controls and final conclusion'),indent=2))
