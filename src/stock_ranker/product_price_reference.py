"""Dated official prior-trade references, confined to the current product."""
from __future__ import annotations

import csv
import hashlib
import io
import math
import zipfile
from pathlib import Path

import pandas as pd

REFERENCE_COLUMNS = (
    'product_price_reference', 'product_price_date', 'product_price_exchange',
    'product_price_source', 'product_price_source_sha256',
    'product_price_identity_evidence', 'product_price_status',
)


def _positive(value):
    try:
        number = float(value)
        return number if math.isfinite(number) and number > 0 else None
    except (ValueError, TypeError):
        return None


def official_prior_references(facts, evidence_root: Path):
    """Read official local bhavcopies. Never replace a same-day accepted quote.

    UDiFF uses ISIN directly. Full NSE bhavcopy requires the exact symbol/series
    AND an exact ISIN link from the dated official security master. Conflicting
    equal-priority observations are quarantined. No post-snapshot prices enter.
    """
    result = facts.copy()
    for field in REFERENCE_COLUMNS:
        result[field] = None
    missing = result.loc[pd.to_numeric(result.latest_price, errors='coerce').isna()]
    if missing.empty:
        return result, []
    wanted = missing.set_index('isin').to_dict('index')
    asof = pd.Timestamp(result.trade_date.max()).date()
    links = {}
    for path in sorted((evidence_root/'nse').glob('*/equity.csv')):
        day = pd.Timestamp(path.parent.name).date()
        if day > asof or (asof-day).days > 7:
            continue
        with path.open(encoding='utf-8-sig', newline='') as f:
            for raw in csv.DictReader(f, skipinitialspace=True):
                r = {k.strip():str(v).strip() for k,v in raw.items()}
                if r.get('ISIN NUMBER') in wanted:
                    key = (r['SYMBOL'], r['SERIES'])
                    links.setdefault(key, set()).add((r['ISIN NUMBER'], str(path), hashlib.sha256(path.read_bytes()).hexdigest()))
    observations = []
    for path in sorted(evidence_root.rglob('*bhav*')):
        if not path.is_file() or path.suffix.lower() not in {'.csv','.zip'}:
            continue
        payload = path.read_bytes()
        if path.suffix.lower() == '.zip':
            with zipfile.ZipFile(io.BytesIO(payload)) as z:
                names = [n for n in z.namelist() if n.lower().endswith('.csv')]
                if len(names) != 1:
                    continue
                text = z.read(names[0]).decode('utf-8-sig')
        else:
            text = payload.decode('utf-8-sig')
        exchange = 'BSE' if 'bse' in path.parts else 'NSE'
        for raw in csv.DictReader(io.StringIO(text), skipinitialspace=True):
            r = {k.strip():str(v).strip() for k,v in raw.items() if k}
            isin = r.get('ISIN','')
            identity = 'Exact ISIN in official UDiFF'
            full = 'SYMBOL' in r
            if full:
                candidates = links.get((r['SYMBOL'],r.get('SERIES','')),set())
                if len({x[0] for x in candidates}) != 1:
                    continue
                isin, link_path, link_hash = sorted(candidates)[-1]
                identity = f'Exact NSE symbol/series + official master ISIN; {link_path}; SHA256 {link_hash}'
            elif r.get('FinInstrmTp') != 'STK':
                continue
            elif r.get('Src') not in (None, '', exchange):
                continue
            if isin not in wanted:
                continue
            day = pd.to_datetime(r.get('TradDt') or r.get('DATE1'),errors='coerce')
            price = _positive(r.get('ClsPric') or r.get('CLOSE_PRICE'))
            volume = _positive(r.get('TtlTradgVol') or r.get('TTL_TRD_QNTY'))
            if pd.isna(day) or day.date() > asof or price is None or volume is None:
                continue
            if full and not 0 <= (pd.Timestamp(Path(link_path).parent.name).date()-day.date()).days <= 7:
                continue
            observations.append(dict(isin=isin,date=day.date().isoformat(),price=price,
                exchange=exchange, source=str(path.resolve()),
                sha256=hashlib.sha256(payload).hexdigest(),identity=identity))
    audit=[]
    for index, row in missing.iterrows():
        available = [r for r in observations if r['isin']==row['isin']]
        if not available:
            audit.append(dict(ticker=row.ticker,isin=row['isin'],status='NO_VERIFIED_PRIOR_TRADE'))
            continue
        newest=max(r['date'] for r in available)
        preferred=[r for r in available if r['date']==newest]
        primary=[r for r in preferred if r['exchange']==row.primary_exchange]
        preferred=primary or preferred
        if len({r['price'] for r in preferred}) != 1:
            audit.append(dict(ticker=row.ticker,isin=row['isin'],status='OFFICIAL_PRICE_CONFLICT'))
            continue
        chosen=sorted(preferred,key=lambda r:r['source'])[0]
        age=(asof-pd.Timestamp(chosen['date']).date()).days
        status='OFFICIAL_PRIOR_TRADE' if age<=7 else 'OFFICIAL_LAST_TRADE_STALE'
        action = pd.to_datetime(row.get('latest_corporate_action_date'), errors='coerce')
        if not pd.isna(action) and pd.Timestamp(chosen['date']) < action <= pd.Timestamp(asof):
            status='OFFICIAL_PRIOR_TRADE_ACTION_REVIEW_REQUIRED'
        values=(chosen['price'],chosen['date'],chosen['exchange'],chosen['source'],chosen['sha256'],chosen['identity'],status)
        for field,value in zip(REFERENCE_COLUMNS,values):
            result.at[index,field]=value
        audit.append(dict(ticker=row.ticker,**chosen,status=status,age_days=age))
    return result,audit
