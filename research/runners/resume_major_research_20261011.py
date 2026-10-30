"""Attach to verified live stages, then run the remaining isolated audits."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import psutil

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/sector-specialist-ensemble-20261011'
EXECUTION=ROOT/'experiments/sector-execution-specialist-20261011'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def identity(pid, fragment):
    proc=psutil.Process(pid)
    command=proc.cmdline()
    assert any(fragment in arg for arg in command), (pid,command)
    return dict(pid=pid,created=proc.create_time(),command=command)


def wait_for(info):
    print('WAIT',info['pid'],info['command'],flush=True)
    while True:
        try:
            proc=psutil.Process(info['pid'])
            if proc.create_time()!=info['created'] or not proc.is_running():
                break
        except psutil.NoSuchProcess:
            break
        time.sleep(10)
    print('TERMINAL',info['pid'],flush=True)


def run(script,stage):
    source=ROOT/'research/runners'/script
    key=script+'_'+stage
    receipt=OUT/(key+'.resume.done.json')
    if receipt.exists():
        saved=json.loads(receipt.read_text())
        assert saved['script_sha256']==digest(source),'Changed source requires explicit audit of the saved stage'
        assert saved['exit_code']==0
        print('VERIFIED RECEIPT',key,flush=True)
        return
    log=OUT/(key+f'.resume.{time.time_ns()}.log')
    command=[sys.executable,'-W','ignore',str(source),stage]
    print('START',command,flush=True)
    with log.open('w',encoding='utf-8') as stream:
        result=subprocess.run(command,cwd=ROOT,stdout=stream,stderr=subprocess.STDOUT)
    assert result.returncode==0,(command,result.returncode,str(log))
    receipt.write_text(json.dumps(dict(command=command,script_sha256=digest(source),log=str(log),log_sha256=digest(log),exit_code=0),indent=2),encoding='utf-8')
    print('COMPLETE',key,flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--combination-pid',type=int,required=True)
    parser.add_argument('--execution-audit-pid',type=int,required=True)
    args=parser.parse_args()
    jobs=[identity(args.combination_pid,'sector_specialist_combinations_20261011.py'),identity(args.execution_audit_pid,'finish_sector_execution_specialist_20261011.py')]
    (OUT/'resume_controller.json').write_text(json.dumps(dict(controller_pid=psutil.Process().pid,controller_created=psutil.Process().create_time(),dependencies=jobs,goal_complete=False),indent=2),encoding='utf-8')
    for job in jobs:
        wait_for(job)
    # A terminal process is not evidence of success. Require completed artifacts.
    import pandas as pd
    stack=pd.read_csv(OUT/'stack_audit.csv')
    assert set(stack.year.astype(str))=={'2020','2021','2022','2023','2024','2025','current'}
    assert int(stack.loc[stack.year.astype(str).eq('current'),'rows'].iloc[0])==4436
    assert int(stack.loc[stack.year.astype(str).ne('current'),'rows'].sum())==797443
    execution=json.loads((EXECUTION/'evaluation_verification.json').read_text())
    assert execution['historical_rows']==797443 and execution['benchmark_cohorts_verified']
    assert (EXECUTION/'financial_audit_sources.json').exists()
    assert (EXECUTION/'activity_feature_contribution.csv').exists()
    run('supplemental_global_specialist_audit_20261011.py','execution')
    for stage in ['development','recent']:
        run('sector_specialist_combinations_20261011.py',stage)
    for stage in ['replay','evaluate','company']:
        run('audit_sector_specialist_ensemble_20261011.py',stage)
    run('supplemental_global_specialist_audit_20261011.py','specialist')
    run('audit_sector_specialist_ensemble_20261011.py','ledger')
    (OUT/'resume_stages_complete.json').write_text(json.dumps(dict(stages_complete=True,full_user_goal_complete=False,remaining='Independent final review, follow-ups justified by results, ablations/synthesis and complete requirements audit'),indent=2),encoding='utf-8')


if __name__=='__main__':
    main()
