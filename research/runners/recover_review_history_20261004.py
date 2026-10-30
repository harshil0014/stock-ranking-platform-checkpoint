"""Acquire isolated alternative-exchange receipts; never splice unchecked bases."""
from pathlib import Path
import json
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import yfinance as yf

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/closing-high-recovery-20261004/history-receipts'
TARGETS={'KPL':'KPL.BO','FRONTSP':'FRONTSP.BO','PTCIL':'PTCIL.BO','STEELCAS':'STEELCAS.BO'}

def fetch(item):
    ticker,symbol=item
    result={'ticker':ticker,'symbol':symbol,'promoted':False}
    try:
        frame=yf.Ticker(symbol).history(start='1990-01-01',end='2026-10-04',auto_adjust=False,timeout=15)
        frame.to_csv(OUT/(ticker+'.csv.gz'))
        valid=frame.dropna(subset=['Close']) if 'Close' in frame else frame
        result.update(rows=len(valid),start=str(valid.index.min()),end=str(valid.index.max()),
                      status='REQUIRES_IDENTITY_ACTION_AND_OVERLAP_VALIDATION' if len(valid) else 'NO_PROVIDER_ROWS')
    except Exception as exc:result.update(status='ACQUISITION_ERROR',error=str(exc)[:300])
    return result

if __name__=='__main__':
    OUT.mkdir(parents=True,exist_ok=True)
    yf.set_tz_cache_location(str(OUT/'provider-cache'))
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(fetch,TARGETS.items()))
    (OUT/'audit.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
