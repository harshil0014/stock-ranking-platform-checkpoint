"""Finish the saved tournament after its manifest appears, including interruption-safe logs."""
from pathlib import Path
import subprocess,time,sys
root=Path(__file__).resolve().parents[2]
out=root/'experiments/personalized-final-tournament/build-04'
log=root/'experiments/ownership-finalize.log'
while not (out/'manifest.json').exists():
 runlog=(root/'experiments/ownership-tournament-resume.log').read_text(errors='replace')
 if 'Traceback (most recent call last)' in runlog:raise RuntimeError('Tournament failed; inspect ownership-tournament-resume.log')
 time.sleep(10)
while 'passed' not in (root/'experiments/ownership-final-tests.log').read_text(errors='replace'):
 time.sleep(10)
(out/'rights_policy_sensitivity.csv').write_bytes((root/'experiments/personalized-final-tournament/build-03/rights_policy_sensitivity.csv').read_bytes())
with log.open('w') as handle:
 result=subprocess.run([sys.executable,str(root/'research/runners/finalize_ownership_research.py'),'--tournament',str(out),'--freeze',str(root/'experiments/personalized-official-action-freeze/build-06'),'--workbook',r'C:\Users\Harshil\Downloads\_Organized\Documents\Copy of OK Strategy - Master Sheet v4.3 (1).xlsx'],cwd=root,stdout=handle,stderr=subprocess.STDOUT)
 if result.returncode:raise RuntimeError('Finalization failed; inspect ownership-finalize.log')
print('Finalization complete',flush=True)
