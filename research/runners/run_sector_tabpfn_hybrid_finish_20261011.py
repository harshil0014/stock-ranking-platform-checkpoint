"""Overlap completed development evaluation with later fits; finish only on receipts."""
import sys,time,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/sector-tabpfn-hybrid-20261011'

def wait_for(paths):
    deadline=time.monotonic()+12*3600
    while not all(path.exists() for path in paths):
        if time.monotonic()>deadline:raise TimeoutError('Required completed fit receipts not available')
        time.sleep(5)

def run():
    wait_for([OUT/f'fit_audit_{y}.json' for y in range(2020,2024)])
    runner=ROOT/'research/runners/sector_tabpfn_hybrid_20261011.py'
    if not (OUT/'locked_finalists.json').exists():subprocess.run([sys.executable,str(runner),'development'],check=True)
    wait_for([OUT/f'fit_audit_{y}.json' for y in [2024,2025,'current']]+[OUT/'all_4436_all_candidates.csv'])
    # Current export is written after fit receipt; ensure training completed its write.
    # Loading below will fail rather than accepting an incomplete export.
    if not (OUT/'summary_recent.csv').exists():subprocess.run([sys.executable,str(runner),'recent'],check=True)
    subprocess.run([sys.executable,str(ROOT/'research/runners/finish_sector_tabpfn_hybrid_20261011.py')],check=True)

if __name__=='__main__':run()
