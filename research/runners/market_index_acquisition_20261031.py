from pathlib import Path
import requests,json,hashlib,datetime,concurrent.futures,time
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'experiments/champion-vs-market-20261031';RAW=ROOT/'work/champion-vs-market-20261031/index-raw';RAW.mkdir(exist_ok=True)
names=json.loads((OUT/'protocol.json').read_text())['official_indices'];receipts=[]
def acquire(name):
 if name=='BSE 500':return dict(name=name,status='SEPARATE_BSE_ENDPOINT_REQUIRED')
 url='https://www.niftyindices.com/Backpage/getTotalReturnIndexString';receipt=dict(name=name,url=url,requested_start='01-Jan-2015',requested_end='30-Sep-2026',retrieved_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 dest=RAW/(name.replace(' ','_')+'_v2.json')
 try:
  if dest.exists():body=dest.read_bytes();receipt['http_status']='CACHED'
  else:
   payload={'cinfo':json.dumps(dict(name=name,startDate='01-Jan-2015',endDate='30-Sep-2026',indexName=name))}
   r=requests.post(url,json=payload,headers={'User-Agent':'Mozilla/5.0','Content-Type':'application/json; charset=UTF-8','X-Requested-With':'XMLHttpRequest','Referer':'https://www.niftyindices.com/reports/historical-data'},timeout=(8,35));body=r.content;receipt['http_status']=r.status_code
   if r.status_code!=200:return dict(receipt,status='SOURCE_UNAVAILABLE',response_sha256=hashlib.sha256(body).hexdigest())
   dest.write_bytes(body)
  text=body.decode('utf-8-sig').strip()
  try:raw=json.loads(text)
  except ValueError:raw=json.loads(text.replace('\\"','"'))
  if isinstance(raw,dict):raw=raw.get('d')
  rows=json.loads(raw) if isinstance(raw,str) else raw
  receipt.update(response_sha256=hashlib.sha256(body).hexdigest(),rows=len(rows) if isinstance(rows,list) else None)
  if not isinstance(rows,list) or not rows:return dict(receipt,status='NO_ROWS_NOT_AN_INDEX_FAILURE')
  import pandas as pd
  x=pd.DataFrame(rows);receipt['columns']=list(x.columns);x.to_csv(OUT/(name.replace(' ','_')+'_TRI.csv'),index=False);receipt['status']='ACQUIRED_SCHEMA_TO_VALIDATE';return receipt
 except (requests.RequestException,ValueError,KeyError) as e:return dict(receipt,status='SOURCE_UNAVAILABLE',error=type(e).__name__)
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
 for r in pool.map(acquire,names):receipts.append(r);print(r['name'],r['status'],r.get('rows'),flush=True)
(OUT/'index_acquisition_receipts.json').write_text(json.dumps(receipts,indent=2))
