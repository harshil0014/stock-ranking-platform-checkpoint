"""Bounded execution repair and source acquisition; run via existing governor."""
import os
for key in ['OMP_NUM_THREADS','OPENBLAS_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:
    os.environ[key]='1'
from pathlib import Path
import argparse, datetime, gc, gzip, hashlib, io, json, pickle, zipfile
import numpy as np
import pandas as pd
import requests
from stock_research.next_open_portfolio import next_open_portfolio

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'experiments/new-information-20261101'
WORK=ROOT/'work/new-information-20261101'


def save(name,value):
    OUT.mkdir(exist_ok=True)
    (OUT/name).write_text(json.dumps(value,indent=2,default=str),encoding='utf-8')


def cache():
    WORK.mkdir(exist_ok=True)
    dest=WORK/'actual_adjusted_open_close.pkl'
    if dest.exists():
        with dest.open('rb') as f:return pickle.load(f)
    root=ROOT/'experiments/current-data-recovery-20261003/yahoo-full-recovery-v1'
    mapping=pd.read_csv(root/'yahoo_symbol_map.csv').dropna(subset=['isin','yahoo_symbol'])
    lookup=dict(zip(mapping.yahoo_symbol,mapping['isin']))
    result={}; sources=[]
    for path in sorted((root/'history-cache').glob('batch_*.pkl')):
        sources.append(dict(file=str(path.relative_to(ROOT)),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        with path.open('rb') as f:batch=pickle.load(f)
        for symbol, frame in batch['frames'].items():
            if symbol not in lookup or not isinstance(frame,pd.DataFrame):continue
            if not {'Open','Close','Adj Close'}.issubset(frame.columns):continue
            z=frame[['Open','Close','Adj Close']].copy()
            z=z[~z.index.duplicated(keep='last')].sort_index()
            # Keep missing opens as invalid observations: never silently shift through them.
            z=z.loc[np.isfinite(z['Close']) & z['Close'].gt(0) & np.isfinite(z['Adj Close']) & z['Adj Close'].gt(0)]
            if z.empty:continue
            ds=z.index.tz_localize(None).to_numpy(dtype='datetime64[D]')
            op=(z.Open*z['Adj Close']/z.Close).to_numpy(float)
            cl=z['Adj Close'].to_numpy(float)
            isin=lookup[symbol]
            if isin not in result or len(ds)>len(result[isin][0]):result[isin]=(ds,op,cl)
        del batch;gc.collect()
        print('OPEN CACHE',path.name,len(result),flush=True)
    with dest.open('wb') as f:pickle.dump(result,f,protocol=5)
    save('price_cache_receipt.json',dict(paths=len(result),cache_sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),sources=sources,
        basis='actual Open * Adj Close / Close; missing opens retained; provider-adjusted fractional-share research proxy'))
    return result


def replay():
    from champion_market_portfolio_20261031 import selection,portfolio_path
    paths=cache()
    x=pd.read_pickle(ROOT/'experiments/professor-weight-curve-20261031/scored.pkl.gz',compression='gzip')
    x=x[x.factor_eligible & x.decision_date.ge('2020-01-01') & x.decision_date.lt('2026-01-01')].copy()
    actions=pd.read_csv(ROOT/'experiments/sector-action-integrity-20261008/provider_official_alignment.csv')
    actions=actions[actions.status.str.startswith('UNRESOLVED')]
    protocol=json.loads((ROOT/'research/protocols/personalized_official_action_tournament_v1.json').read_text())['profiles']['base7500']
    rows=[];failures=[]
    for date,g in x.groupby('decision_date',sort=True):
        endpoint=str((pd.Timestamp(date)+pd.DateOffset(months=12)).date())
        bad=set(actions.loc[actions.provider_ratio.notna() & actions.event_date.ge(date) & actions.event_date.le(endpoint),'isin'])
        for model in ['active_champion','factor20_fixed']:
            for policy in ['global_top20','sector_top3_equal_sector']:
                base=dict(decision_date=date,period='development' if date<'2024-01-01' else 'exposed',model=model,policy=policy)
                ids,weights=selection(g,model,policy)
                try:
                    if not ids or set(ids)-set(paths):raise ValueError('Missing selected paths')
                    if set(ids)&bad:raise ValueError('Unresolved corporate action')
                    subset=[paths[i] for i in ids]
                    # Only inspect the holding window plus prior mark, not irrelevant ancient missing opens.
                    scoped=[]
                    for ds,op,cl in subset:
                        a=max(0,np.searchsorted(ds,np.datetime64(date))-1)
                        b=np.searchsorted(ds,np.datetime64(endpoint),side='right')
                        scoped.append((ds[a:b],op[a:b],cl[a:b]))
                    r=next_open_portfolio(scoped,weights,date,endpoint,protocol['amount'],protocol['interval_days'],25)
                    old=portfolio_path([(ds,cl) for ds,op,cl in scoped],weights,date,endpoint,protocol['amount'],protocol['interval_days'],25)
                    rows.append(dict(**base,stocks=len(ids),next_open_xirr=r['xirr'],legacy_close_xirr=old['xirr'],
                        xirr_change=r['xirr']-old['xirr'],next_open_drawdown=r['tw_max_drawdown'],
                        legacy_drawdown=old['tw_max_drawdown'],first_fill_min=min(r['first_fills']),first_fill_max=max(r['first_fills'])))
                except ValueError as e:failures.append(dict(**base,reason=str(e)))
        print('REPLAY',date,'valid',len(rows),'blocked',len(failures),flush=True)
    z=pd.DataFrame(rows);z.to_csv(OUT/'execution_replay.csv',index=False)
    pd.DataFrame(failures).to_csv(OUT/'execution_failures.csv',index=False)
    if len(z):
        z.groupby(['period','model','policy']).agg(valid_dates=('decision_date','size'),legacy_xirr=('legacy_close_xirr','mean'),next_open_xirr=('next_open_xirr','mean'),xirr_change=('xirr_change','mean'),next_open_drawdown=('next_open_drawdown','mean')).to_csv(OUT/'execution_summary.csv')
        a=z[z.model.eq('active_champion')].merge(z[z.model.eq('factor20_fixed')],on=['decision_date','period','policy'],suffixes=('_champion','_lens'),validate='one_to_one')
        a['lens_minus_champion_xirr']=a.next_open_xirr_lens-a.next_open_xirr_champion
        a['lens_minus_champion_drawdown']=a.next_open_drawdown_lens-a.next_open_drawdown_champion
        a.groupby(['period','policy']).agg(matched_dates=('decision_date','size'),lens_minus_champion_xirr=('lens_minus_champion_xirr','mean'),lens_minus_champion_drawdown=('lens_minus_champion_drawdown','mean')).to_csv(OUT/'execution_paired.csv')
    save('execution_scope.json',dict(planned=len(x.decision_date.unique())*4,valid=len(z),blocked=len(failures),cost_bps=25,model_changed=False,
        caveats=['Current survivors and historical sector labels','Provider-adjusted prices; no certified vintage','Strict next session after every scheduled deposit','No liquidity, spread, taxes, lot sizes, circuit or suspension execution model','Terminal liquidation at last close on/before known horizon; maximum seven-day mark gap','Overlapping cohorts; descriptive correction, no new holdout']))


def acquire():
    WORK.mkdir(exist_ok=True);raw=WORK/'sources';raw.mkdir(exist_ok=True)
    urls=[('historical_delivery_20200330','https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_30032020.csv'),
          ('historical_delivery_20250929','https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_29092025.csv')]
    source=ROOT/'work/prospective-ledger/raw/2026-10-31/2026-10-31T14-01-17.726895+00-00_announcements.body.gz'
    data=json.loads(gzip.decompress(source.read_bytes()))
    selected=[]
    for symbol,desc in [('RAYMONDREL','Resignation of Statutory Auditor'),('PGEL','Resignation of Statutory Auditor'),('NIITMTS','Change in Auditors'),('NIITLTD','Change in Auditors'),('CASTROLIND','Change in Auditors'),('TOLINS','Resignation')]:
        matches=[r for r in data if r.get('symbol')==symbol and desc.lower() in r.get('desc','').lower()]
        if matches:
            r=sorted(matches,key=lambda r:r.get('an_dt',''))[-1]
            selected.append(r);urls.append((f'filing_{len(selected):02}',r['attchmntFile']))
    receipts=[]
    for label,url in urls:
        rec=dict(label=label,url=url,requested_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        try:
            response=requests.get(url,timeout=(5,12),headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.nseindia.com/'})
            rec.update(status=response.status_code,bytes=len(response.content),content_type=response.headers.get('Content-Type'),sha256=hashlib.sha256(response.content).hexdigest())
            rec['observed_at_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
            response.raise_for_status()
            (raw/(label+'.body')).write_bytes(response.content)
        except requests.RequestException as e:rec['error']=str(e)
        receipts.append(rec);save('source_acquisition.json',receipts)
        print('SOURCE',label,rec.get('status'),rec.get('error',''),flush=True)
    (raw/'filing_metadata.json').write_text(json.dumps(selected,indent=2),encoding='utf-8')
    save('delivery_gate.json',dict(status='BLOCKED_PENDING_COVERAGE',reason='Two probes do not establish minimum historical date or same-session ISIN coverage; no substitute price-volume result',
        browser='NSE all-reports loaded; full-delivery download click timed out after20 seconds',new_model_fits=0))


if __name__=='__main__':
    OUT.mkdir(exist_ok=True)
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['replay','acquire']);a=p.parse_args()
    if not (OUT/'protocol_receipt.json').exists():
        save('protocol_receipt.json',dict(sha256=hashlib.sha256((ROOT/'research/protocols/new_information_20261101.md').read_bytes()).hexdigest(),started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()))
    globals()[a.stage]()
