"""Wait for the current activity trainer; resume receipts and evaluate in isolation."""
import sys,time,json,subprocess
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments/sector-execution-specialist-20261011'
def run(script,*args):
    key=script+'_'+('_'.join(args) or 'learn');log=OUT/(key+'.log')
    with log.open('w',encoding='utf-8') as f:result=subprocess.run([sys.executable,str(ROOT/'research/runners'/script),*args],cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    assert result.returncode==0,f'{key}: inspect {log}'
    print('COMPLETE',key,flush=True)
if __name__=='__main__':
    pid=int(sys.argv[1]);p=psutil.Process(pid);created=p.create_time()
    assert any('sector_execution_specialist_20261011.py' in c for c in p.cmdline())
    (OUT/'pipeline_process.json').write_text(json.dumps(dict(trainer_pid=pid,trainer_created=created,controller_pid=psutil.Process().pid),indent=2))
    while True:
        try:
            p=psutil.Process(pid)
            if p.create_time()!=created or not p.is_running():break
        except psutil.NoSuchProcess:break
        time.sleep(15)
    # Resume confirmed terminal process. Completed annual receipts are retained.
    # This also loads the current-input column collision fix added during the first run.
    run('sector_execution_specialist_20261011.py')
    for step in ['development','recent','replay','audit']:run('finish_sector_execution_specialist_20261011.py',step)
    (OUT/'pipeline_complete.json').write_text(json.dumps(dict(stages_complete=True,full_user_goal_complete=False),indent=2))
