"""Finish the saved tournament after its manifest appears, including interruption-safe logs."""
from pathlib import Path
import subprocess,time,sys
root=Path(__file__).resolve().parents[2]
out=root/'experiments/personalized-final-tournament/build-04'
log=root/'experiments/ownership-finalize.log'
def read_log(path):
 data=path.read_bytes()
 return data.decode('utf-16' if data.startswith(b'\xff\xfe') else 'utf-8',errors='replace')
while not (out/'manifest.json').exists():
 runlog=read_log(root/'experiments/ownership-tournament-resume.log')
 if 'Traceback (most recent call last)' in runlog:raise RuntimeError('Tournament failed; inspect ownership-tournament-resume.log')
 time.sleep(10)
while 'passed' not in read_log(root/'experiments/ownership-final-tests.log'):
 time.sleep(10)
(out/'rights_policy_sensitivity.csv').write_bytes((root/'experiments/personalized-final-tournament/build-03/rights_policy_sensitivity.csv').read_bytes())
with log.open('w') as handle:
 result=subprocess.run([sys.executable,str(root/'research/runners/finalize_ownership_research.py'),'--tournament',str(out),'--freeze',str(root/'experiments/personalized-official-action-freeze/build-06'),'--workbook',r'C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx'],cwd=root,stdout=handle,stderr=subprocess.STDOUT)
 if result.returncode:raise RuntimeError('Finalization failed; inspect ownership-finalize.log')
print('Finalization complete',flush=True)
