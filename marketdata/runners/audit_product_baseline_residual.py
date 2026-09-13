"""Offline evidence audit of accepted Product Baseline gaps; no promotion."""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    if path.suffix == ".zip":
        with zipfile.ZipFile(path) as archive:
            names = [n for n in archive.namelist() if n.lower().endswith('.csv')]
            if len(names) != 1:
                return []
            text = archive.read(names[0]).decode('utf-8-sig')
    else:
        text = path.read_text(encoding='utf-8-sig')
    return list(csv.DictReader(io.StringIO(text), skipinitialspace=True))


def run(output):
    import pandas as pd
    state_path = ROOT / 'data/company_facts/accepted_state.json'
    state = json.loads(state_path.read_text())
    source = state_path.parent / state['snapshot_path'] / 'company_facts.csv'
    facts = rows(source)
    missing = [r for r in facts if not r['latest_price']]
    ids = {r['isin'] for r in missing}
    symbols = {r['ticker']: r['isin'] for r in missing}
    observations = []
    candidates = sorted(set(
        list((ROOT/'data/live_market/evidence/raw').rglob('*bhav*.csv'))
        + list((ROOT/'data/live_market/evidence/raw').rglob('*bhav*.zip'))
        + list((ROOT/'data/live_market/bse_udiff_20250905_20260907/raw').rglob('*.csv'))
    ))
    for path in candidates:
        data = rows(path)
        found = []
        for r in data:
            isin = str(r.get('ISIN') or '').strip()
            symbol = str(r.get('SYMBOL') or '').strip()
            if isin not in ids and symbol not in symbols:
                continue
            day = r.get('TradDt') or r.get('DATE1')
            try:
                stamp = pd.Timestamp(day).date().isoformat()
            except (ValueError, TypeError):
                continue
            if stamp > state['trade_date']:
                continue
            found.append(dict(isin=isin, ticker=r.get('TckrSymb') or symbol,
                exchange='BSE' if 'bse' in str(path).lower() else 'NSE',
                series=r.get('SctySrs') or str(r.get('SERIES') or '').strip(),
                code=r.get('FinInstrmId') or '', date=stamp,
                close=r.get('ClsPric') or r.get('CLOSE_PRICE'),
                volume=r.get('TtlTradgVol') or r.get('TTL_TRD_QNTY'),
                source=str(path.relative_to(ROOT)), identity='EXACT_ISIN' if isin in ids else 'SYMBOL_ONLY_REQUIRES_ISIN_LINK'))
        if found:
            sha = digest(path)
            for r in found:
                r['sha256'] = sha
            observations.extend(found)
    observations.sort(key=lambda r: (r['isin'], r['ticker'], r['date'], r['source']))
    residual = []
    history_root = ROOT / 'data/live_market/history_cache'
    for row in facts:
        if row['product_baseline_reason_code'] == 'ELIGIBLE':
            continue
        history = pd.read_csv(history_root / (row['ticker']+'.csv'), usecols=['date','adjusted_close'])
        history['date'] = pd.to_datetime(history['date'], errors='coerce')
        history['adjusted_close'] = pd.to_numeric(history['adjusted_close'], errors='coerce')
        history = history.dropna().loc[lambda f: f.adjusted_close.gt(0)]
        asof = pd.Timestamp(row['trade_date'])
        history = history.loc[history.date.le(asof)].sort_values('date')
        out = {k:row[k] for k in ('ticker','isin','company','listing_date','product_baseline_reason_code')}
        for field in ('product_price_reference','product_price_date','product_price_status'):
            out[field] = row.get(field,'')
        out['history_sha256'] = digest(history_root/(row['ticker']+'.csv'))
        out['history_start'] = str(history.date.min().date()) if not history.empty else ''
        out['history_end'] = str(history.date.max().date()) if not history.empty else ''
        for years in (1,3,5):
            target = asof - pd.DateOffset(years=years)
            prior = history.loc[history.date.le(target)]
            if prior.empty:
                status = 'NO_ACCEPTED_PRE_TARGET_OBSERVATION'
            elif (target-prior.iloc[-1].date).days > 7:
                status = 'ANCHOR_OUTSIDE_EXISTING_7_DAY_TOLERANCE'
            else:
                status = 'AVAILABLE'
            out[f'{years}y_status'] = status
            out[f'{years}y_target'] = target.date().isoformat()
            out[f'{years}y_prior_date'] = prior.iloc[-1].date.date().isoformat() if not prior.empty else ''
        # Inspect preserved older caches for actual missing anchors, without
        # accepting a file on its ticker filename alone.
        alternatives=[]
        for older_root in sorted((ROOT/'data/live_market').glob('history_cache_previous_*')):
            older_path=older_root/(row['ticker']+'.csv')
            if not older_path.is_file():
                continue
            older=pd.read_csv(older_path,usecols=['date','adjusted_close'])
            older['date']=pd.to_datetime(older['date'],errors='coerce')
            older['adjusted_close']=pd.to_numeric(older.adjusted_close,errors='coerce')
            older=older.dropna().loc[lambda f:f.adjusted_close.gt(0)].sort_values('date')
            for years in (1,3,5):
                target=asof-pd.DateOffset(years=years)
                found=older.loc[older.date.le(target)].tail(1)
                if out[f'{years}y_status']!='AVAILABLE' and not found.empty and (target-found.iloc[0].date).days<=7:
                    alternatives.append(f'{years}Y:{older_path.relative_to(ROOT)}:IDENTITY_AND_ADJUSTMENT_REVALIDATION_REQUIRED')
        out['older_cache_candidate_anchors']=';'.join(alternatives)
        residual.append(out)
    output.mkdir(parents=True, exist_ok=False)
    for name, data in [('price_evidence', observations), ('baseline_residual', residual)]:
        with (output/(name+'.csv')).open('w',encoding='utf-8',newline='') as f:
            writer=csv.DictWriter(f,fieldnames=list(data[0]) if data else ['isin'],lineterminator='\n')
            writer.writeheader(); writer.writerows(data)
    summary = dict(fingerprint=state['fingerprint'], market_fingerprint=state['market_fingerprint'],
        waterfall=dict(Counter(r['product_baseline_reason_code'] for r in facts)),
        price_missing=[{k:r[k] for k in ('ticker','isin')} for r in missing],
        official_observations_found=len(observations), files_scanned=len(candidates),
        horizon_gaps={str(y):dict(Counter(r[f'{y}y_status'] for r in residual)) for y in (1,3,5)})
    (output/'summary.json').write_text(json.dumps(summary,sort_keys=True,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(summary,sort_keys=True))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    run(p.parse_args().output)
