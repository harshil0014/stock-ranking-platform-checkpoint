"""Immutable public exchange evidence for research-only V17 refinement."""
import sys,json,time,hashlib,threading
from pathlib import Path
from datetime import datetime,timezone,date
from concurrent.futures import ThreadPoolExecutor,as_completed
import requests
import pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path[:0]=[str(ROOT),str(ROOT/'src')]
from marketdata.runners.download_bse_structured_corporate_actions import normalize_row
O=ROOT/'experiments/v17-refinement-20261004/actions';O.mkdir(parents=True,exist_ok=True)
START='2026-09-19';END='2026-10-04'
HEADERS={'User-Agent':'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131.0.0.0 Safari/537.36','Accept':'application/json,text/plain,*/*'}
LOCAL=threading.local()
def fetch(name,url,referer,params=None):
    path=O/'raw'/f'{name}.json';path.parent.mkdir(exist_ok=True)
    if path.exists():return json.loads(path.read_text())
    errors=[]
    for attempt in range(3):
        try:
            if not hasattr(LOCAL,'session'):
                LOCAL.session=requests.Session();LOCAL.session.headers.update({**HEADERS,'Origin':'https://www.bseindia.com' if 'bseindia' in url else 'https://www.nseindia.com'});LOCAL.session.get(referer,timeout=25)
            r=LOCAL.session.get(url,headers={'Referer':referer},params=params,timeout=25);r.raise_for_status();data=r.json();assert isinstance(data,list),type(data);path.write_bytes(r.content);return data
        except Exception as exc:errors.append(str(exc));time.sleep(attempt+1)
    raise RuntimeError('; '.join(errors))
def main():
    facts=pd.read_csv(ROOT/'experiments/current-data-recovery-20261003/current_company_facts_recovered_v7_full_yahoo.csv.gz',low_memory=False);receipts=[];events=[]
    nse='https://www.nseindia.com/api/corporates-corporateActions';bse='https://api.bseindia.com/BseIndiaAPI/api/DefaultData/w'
    try:
        data=fetch('nse',nse,'https://www.nseindia.com/companies-listing/corporate-filings-actions',{'index':'equities','from_date':'19-09-2026','to_date':'04-10-2026'});receipts.append({'exchange':'NSE','status':'SUCCESS','rows':len(data)})
        for item in data:
            day=pd.to_datetime(item.get('exDate'),dayfirst=True,errors='coerce');subject=str(item.get('subject',''));lower=subject.lower();kind=('BONUS' if 'bonus' in lower else 'SPLIT' if 'split' in lower or 'sub-div' in lower else 'RIGHTS' if 'right' in lower else 'DEMERGER' if 'demerger' in lower else 'SCHEME_OR_MERGER' if any(t in lower for t in ['merger','scheme','consolidation','reduction']) else None)
            if kind and pd.notna(day) and START<=day.date().isoformat()<=END:events.append({'exchange':'NSE','isin':item.get('isin'),'ticker_or_code':item.get('symbol'),'event_date':item.get('exDate'),'record_date':item.get('recDate'),'source_text':subject,'event_type':kind,'event_date_parsed':day.date().isoformat()})
    except Exception as exc:receipts.append({'exchange':'NSE','status':'FAILED','reason':str(exc)})
    codes=sorted(facts.loc[facts.primary_exchange.eq('BSE'),'ticker'].str.replace('BSE-','',regex=False).unique())
    def job(code):
        try:
            data=fetch('bse_'+code,bse,'https://www.bseindia.com/corporates/corporates_act.html?scripcode='+code,{'ddlcategorys':'E','ddlindustrys':'','segment':'0','strSearch':'D','Fdate':'20260919','TDate':'20261004','scripcode':code});out=[]
            for item in data:
                row=normalize_row(item,code,(date(2026,9,19),date(2026,10,4)))
                if row['event_type'] in ['SPLIT','BONUS','RIGHTS','MERGER_DEMERGER_SCHEME']:
                    day=pd.to_datetime(row['ex_date'],dayfirst=True,errors='coerce')
                    if pd.notna(day) and START<=day.date().isoformat()<=END:out.append({'exchange':'BSE','isin':None,'ticker_or_code':code,'event_date':row['ex_date'],'record_date':row['record_date'],'source_text':row['purpose'],'event_type':row['event_type'],'event_date_parsed':day.date().isoformat()})
            return {'exchange':'BSE','code':code,'status':'SUCCESS','rows':len(data)},out
        except Exception as exc:return {'exchange':'BSE','code':code,'status':'FAILED','reason':str(exc)},[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i,future in enumerate(as_completed([pool.submit(job,c) for c in codes]),1):
            receipt,rows=future.result();receipts.append(receipt);events.extend(rows)
            if i%100==0:print('BSE',i,'/',len(codes),'success',sum(r['status']=='SUCCESS' for r in receipts),flush=True);pd.DataFrame(receipts).to_csv(O/'acquisition.csv',index=False)
    pd.DataFrame(receipts).to_csv(O/'acquisition.csv',index=False);pd.DataFrame(events,columns=['exchange','isin','ticker_or_code','event_date','record_date','source_text','event_type','event_date_parsed']).to_csv(O/'source_events.csv',index=False)
    summary={'retrieved_at':datetime.now(timezone.utc).isoformat(),'start':START,'end':END,'receipts':len(receipts),'failed':sum(r['status']!='SUCCESS' for r in receipts),'events':len(events),'public_sources':[nse,bse],'raw_hashes':{str(p.relative_to(O)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (O/'raw').glob('*.json')}};(O/'summary.json').write_text(json.dumps(summary,indent=2));print({k:v for k,v in summary.items() if k!='raw_hashes'},flush=True)
def splits():
    """Verify provider price-basis history for every V7 symbol, with immutable receipts."""
    import calendar
    out=O.parent/'provider_splits';(out/'raw').mkdir(parents=True,exist_ok=True);facts=pd.read_csv(ROOT/'experiments/current-data-recovery-20261003/current_company_facts_recovered_v7_full_yahoo.csv.gz',low_memory=False);audits=[];events=[]
    def job(row):
        symbol=row.yahoo_symbol;path=out/'raw'/f'{row.isin}.json';url=f'https://query1.finance.yahoo.com/v8/finance/chart/{symbol}'
        if not isinstance(symbol,str) or not symbol.endswith(('.NS','.BO')):return {'isin':row.isin,'status':'FAILED','reason':'NO_VERIFIED_YAHOO_SYMBOL'},[]
        error=''
        for attempt in range(3):
            try:
                if path.exists():raw=path.read_bytes()
                else:
                    response=requests.get(url,params={'period1':0,'period2':calendar.timegm(datetime(2026,10,4).timetuple()),'interval':'3mo','events':'splits','includeAdjustedClose':'false'},headers=HEADERS,timeout=25);response.raise_for_status();raw=response.content
                result=json.loads(raw)['chart']['result'][0];meta=result['meta'];assert meta['symbol'].upper()==symbol.upper();assert meta.get('instrumentType')=='EQUITY';assert result.get('timestamp');path.write_bytes(raw);digest=hashlib.sha256(raw).hexdigest();rows=[]
                for item in result.get('events',{}).get('splits',{}).values():
                    num=float(item['numerator']);den=float(item['denominator']);assert num>0 and den>0;day=datetime.fromtimestamp(item['date'],timezone.utc).date().isoformat();assert day<=END;rows.append({'isin':row.isin,'ticker':row.ticker,'provider_symbol':symbol,'event_date':day,'numerator':num,'denominator':den,'split_ratio':num/den,'source_url':url,'response_sha256':digest})
                return {'isin':row.isin,'ticker':row.ticker,'provider_symbol':symbol,'status':'SUCCESS','response_sha256':digest,'events':len(rows),'last_timestamp':max(result['timestamp'])},rows
            except Exception as exc:error=str(exc);time.sleep(attempt+1)
        return {'isin':row.isin,'ticker':row.ticker,'provider_symbol':symbol,'status':'FAILED','reason':error},[]
    with ThreadPoolExecutor(max_workers=6) as pool:
        for i,future in enumerate(as_completed([pool.submit(job,row) for row in facts.itertuples(index=False)]),1):
            au,rows=future.result();audits.append(au);events.extend(rows)
            if i%200==0:print('SPLITS',i,len(facts),'success',sum(a['status']=='SUCCESS' for a in audits),flush=True);pd.DataFrame(audits).to_csv(out/'acquisition_audit.csv',index=False)
    pd.DataFrame(audits).to_csv(out/'acquisition_audit.csv',index=False);pd.DataFrame(events).to_csv(out/'split_ledger.csv',index=False);(out/'summary.json').write_text(json.dumps({'retrieved_at':datetime.now(timezone.utc).isoformat(),'through':END,'rows':len(audits),'success':sum(a['status']=='SUCCESS' for a in audits),'events':len(events),'identity_checked':'Exact approved V7 Yahoo symbol and EQUITY type; current-only research receipt.'},indent=2));print('SPLITS COMPLETE',flush=True)
if __name__=='__main__':splits() if len(sys.argv)>1 and sys.argv[1]=='splits' else main()
