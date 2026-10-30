"""Recover current-only raw price inputs using retained verified identity mappings."""
import json,hashlib
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import pandas as pd
import yfinance as yf
from sector_price_rebuild_20261010 import OUT,ROOT,ASOF,RAW,snapshot

DEST=OUT/'current_input_rescue'

def run():
    DEST.mkdir(exist_ok=True)
    f=pd.read_pickle(OUT/'price_features.pkl.gz',compression='gzip')
    missing=f[f.decision_date.eq(ASOF)&f.input_status.eq('NO_PRICE')]['isin']
    facts_path=ROOT/'experiments/current-data-recovery-20261003/current_company_facts_recovered_v8_yahoo_rescued.csv.gz'
    facts=pd.read_csv(facts_path,usecols=['isin','ticker','yahoo_symbol','yahoo_symbol_method'])
    target=facts[facts['isin'].isin(missing)&facts.yahoo_symbol.notna()]
    official=pd.read_csv(ROOT/'research/runtime/personalized-v17/actions.csv.gz')
    official.event_date=pd.to_datetime(official.event_date)
    def fetch(row):
        record=dict(isin=row.isin,ticker=row.ticker,symbol=row.yahoo_symbol,identity_basis=row.yahoo_symbol_method)
        path=DEST/(row.isin+'.csv.gz')
        try:
            if path.exists():h=pd.read_csv(path,index_col=0,parse_dates=True)
            else:
                h=yf.Ticker(row.yahoo_symbol).history(start='2025-05-01',end='2026-10-04',auto_adjust=False,actions=True,timeout=20)
                if h.empty:raise ValueError('Provider returned no observations')
                h.to_csv(path)
            h.index=pd.to_datetime(h.index,utc=True).tz_convert('Asia/Kolkata').tz_localize(None).normalize()
            h=h[h.index<=pd.Timestamp(ASOF)].dropna(subset=['Close'])
            h=h[h.Close.gt(0)];assert h.index.is_unique and h.index.is_monotonic_increasing
            pending=[]
            if 'Stock Splits' in h:
                for day,ratio in h.loc[h['Stock Splits'].ne(0),'Stock Splits'].items():
                    near=official[official['isin'].eq(row.isin)&official.mechanics_status.eq('AUTO_MULTIPLIER')&official.event_date.between(day-pd.Timedelta(days=7),day+pd.Timedelta(days=7))]
                    if near.empty or not np.isclose(near.total_share_multiplier.prod(),ratio,rtol=.002,atol=1e-9):pending.append(day.date().isoformat())
            result=snapshot(h.index.to_numpy(dtype='datetime64[D]'),h.Close.to_numpy(float),ASOF,pending)
            record.update(status=result['input_status'],observations=len(h),unresolved_actions=pending,receipt_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
            features=dict(isin=row.isin,decision_date=ASOF,**result)
            return record,features
        except Exception as exc:
            record.update(status='NOT_RECOVERED',reason=str(exc)[:300]);return record,None
    with ThreadPoolExecutor(max_workers=3) as pool:results=list(pool.map(fetch,target.itertuples(index=False)))
    audit=[a for a,_ in results];accepted=[f for a,f in results if f is not None and a['status']=='USABLE_PROVIDER_BASIS']
    pd.DataFrame(accepted,columns=['isin','decision_date']+RAW+['input_status','last_price_date']).to_csv(DEST/'accepted_features.csv',index=False)
    (DEST/'audit.json').write_text(json.dumps({'as_of':ASOF,'retrieval_date':'2026-10-10','requested':len(target),'accepted':len(accepted),'historical_training_modified':False,'identity_source_sha256':hashlib.sha256(facts_path.read_bytes()).hexdigest(),'receipts':audit},indent=2))
    print('RECOVERY',len(target),'requested;',len(accepted),'usable;',pd.Series([r['status'] for r in audit]).value_counts().to_dict(),flush=True)

if __name__=='__main__':run()
