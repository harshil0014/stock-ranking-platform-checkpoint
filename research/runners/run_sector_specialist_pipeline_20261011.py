"""Resume after an identified live trainer, then execute dependent research stages."""
import sys,time,json,subprocess,hashlib
from pathlib import Path
import psutil
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/sector-specialist-ensemble-20261011'
FAMILIES=['ebm_additive','ebm_interactions','extra_trees','ridge','tabm_compact','tabm_embedded']
YEARS=[2020,2021,2022,2023,2024,2025,'current']
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def run(script,arg):
    key=script+'_'+arg;receipt=OUT/(key+'.done.json')
    if receipt.exists():return
    log=OUT/(key+'.log');command=[sys.executable,str(ROOT/'research/runners'/script),arg]
    with log.open('w',encoding='utf-8') as f:
        result=subprocess.run(command,cwd=ROOT,stdout=f,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'{key} exit{result.returncode}; inspect {log}')
    receipt.write_text(json.dumps(dict(command=command,exit_code=result.returncode,log_sha256=sha(log)),indent=2),encoding='utf-8')
    print('STAGE COMPLETE',key,flush=True)
def main():
    pid=int(sys.argv[1]);proc=psutil.Process(pid);created=proc.create_time()
    assert any('sector_specialist_ensemble_20261011.py' in a for a in proc.cmdline()),'Wrong trainer process'
    identity=dict(trainer_pid=pid,trainer_created=created,command=proc.cmdline(),controller_pid=psutil.Process().pid)
    (OUT/'pipeline_process.json').write_text(json.dumps(identity,indent=2),encoding='utf-8')
    print('WAITING FOR LIVE TRAINER',pid,flush=True)
    while True:
        try:
            current=psutil.Process(pid)
            if current.create_time()!=created or not current.is_running():break
        except psutil.NoSuchProcess:break
        time.sleep(15)
    for year in YEARS:
        assert (OUT/f'predictions_{year}.csv.gz').exists(),f'Missing completed training year {year}'
        for family in FAMILIES:
            receipt=json.loads((OUT/f'audit_{family}_{year}.json').read_text())
            assert receipt['prediction_sha256']==sha(OUT/f'raw_{family}_{year}.csv.gz')
    print('TRAINING COMPLETE AND OUTPUTS VERIFIED',flush=True)
    run('sector_specialist_combinations_20261011.py','combine')
    run('sector_specialist_combinations_20261011.py','development')
    run('sector_specialist_combinations_20261011.py','recent')
    run('audit_sector_specialist_ensemble_20261011.py','replay')
    run('audit_sector_specialist_ensemble_20261011.py','evaluate')
    run('audit_sector_specialist_ensemble_20261011.py','company')
    (OUT/'pipeline_complete.json').write_text(json.dumps(dict(stages_complete=True,full_user_goal_complete=False,manual_financial_review_and_final_synthesis_pending=True),indent=2))
if __name__=='__main__':main()
