"""Regression for the absolute deadline that a socket timeout failed to enforce."""
import json
from pathlib import Path
import subprocess
import sys


def test_watchdog_aborts_blocking_worker_and_preserves_receipt(tmp_path):
    runner=Path(__file__).resolve().parents[1]/'research/runners'
    receipt=tmp_path/'timeout.json'
    code=('import sys,time;sys.path.insert(0,sys.argv[1]);'
          'from filing_probe_20261101 import start_watchdog;'
          'start_watchdog(1,sys.argv[2]);time.sleep(60)')
    process=subprocess.run([sys.executable,'-c',code,str(runner),str(receipt)],timeout=20,
                           capture_output=True)
    assert process.returncode==124
    assert json.loads(receipt.read_text())['status']=='ABORTED_WALL_BUDGET'
