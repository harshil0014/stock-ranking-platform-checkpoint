"""Compact evidence inventory; excludes raw exchange filings and price panels."""
from pathlib import Path
import ast,datetime,hashlib,json,platform,shutil
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/new-information-20261101';WORK=ROOT/'work/new-information-20261101'


def main():
    log=WORK/'low-load-final-tests.log'
    if '17 passed' not in log.read_text():raise RuntimeError('Final local test receipt missing')
    receipt=dict(passed=True,tests=17,external_ci=False,log_sha256=hashlib.sha256(log.read_bytes()).hexdigest(),
        tests_files=['tests/test_next_open_20261101.py','tests/test_filing_watchdog_20261101.py','tests/test_professor_factor_model_20261031.py'])
    (OUT/'test_receipt.json').write_text(json.dumps(receipt,indent=2))
    files=[ROOT/'src/stock_research/next_open_portfolio.py',ROOT/'tests/test_next_open_20261101.py',ROOT/'tests/test_filing_watchdog_20261101.py']
    files+=list((ROOT/'research/runners').glob('*information*20261101.py'))
    files+=[ROOT/'research/runners/delivery_probe_20261101.py',ROOT/'research/runners/filing_probe_20261101.py']
    for p in files:ast.parse(p.read_text(encoding='utf-8'))
    import numpy,pandas,scipy,sklearn,requests
    (OUT/'environment.json').write_text(json.dumps(dict(python=platform.python_version(),numpy=numpy.__version__,pandas=pandas.__version__,scipy=scipy.__version__,sklearn=sklearn.__version__,requests=requests.__version__,compute_threads=1,cpu_cap_percent=12.5,cpu_active_seconds=4,cpu_rest_seconds=2,gpu_used=False,syntax_files_checked=len(files)),indent=2))
    logs=[]
    for p in sorted(WORK.glob('*.log')):logs.append(dict(path=str(p.relative_to(ROOT)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()))
    (OUT/'local_log_inventory.json').write_text(json.dumps(logs,indent=2))
    files+=list((ROOT/'research/protocols').glob('*20261101.md'))
    files+=[ROOT/'research/reports/new_information_20261101.md']
    files+=sorted(p for p in OUT.iterdir() if p.is_file() and p.name!='manifest.json')
    rows=[dict(path=p.relative_to(ROOT).as_posix(),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(set(files))]
    (OUT/'manifest.json').write_text(json.dumps(dict(created_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat(),files=rows,scope='Compact research evidence; raw model responses, filing bodies and price caches remain local'),indent=2))
    output=Path(r'C:\Users\Harshil\Documents\Codex\2026-10-31\you\outputs')
    shutil.copyfile(OUT/'manifest.json',output/'new_information_20261101_manifest.json')
    shutil.copyfile(OUT/'execution_summary.csv',output/'next_open_execution_summary_20261101.csv')
    shutil.copyfile(OUT/'delivery_gate.json',output/'delivery_pilot_20261101.json')
    print('BUNDLE',len(rows),'artifacts;17local tests verified; syntax checked',len(files),flush=True)


if __name__=='__main__':main()
