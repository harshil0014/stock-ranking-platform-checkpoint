"""Official month-end bhavcopy identity inventory; not adjusted SIP outcomes."""
from pathlib import Path
import concurrent.futures,datetime,hashlib,io,json,time,zipfile
import pandas as pd
import requests
from round2_universe_20261031 import OUT,ROOT
RAW=ROOT/'work/round2-historical-bhavcopy'

def validate_zip(body,day):
 with zipfile.ZipFile(io.BytesIO(body)) as z:
  names=[n for n in z.namelist() if n.lower().endswith('.csv')]
  if len(names)!=1:raise ValueError('Expected one bhavcopy CSV')
  x=pd.read_csv(z.open(names[0]))
 required=['SYMBOL','SERIES','ISIN','CLOSE','TOTTRDQTY','TIMESTAMP']
 if not set(required)<=set(x):raise ValueError('Unexpected exchange schema')
 actual=pd.to_datetime(x.TIMESTAMP,format='%d-%b-%Y',errors='raise')
 if not actual.eq(pd.Timestamp(day)).all():raise ValueError('Filename and exchange observation date disagree')
 if x.duplicated(['SYMBOL','SERIES']).any():raise ValueError('Ambiguous symbol/series rows')
 return x[required]

def acquire_month(month):
 target=pd.Timestamp(month);receipts=[]
 for delta in range(7):
  day=target-pd.Timedelta(days=delta)
  if day.weekday()>=5:continue
  name=day.strftime('cm%d%b%Ybhav.csv.zip');name=name[:4]+name[4:7].upper()+name[7:]
  url=f'https://nsearchives.nseindia.com/content/historical/EQUITIES/{day.year}/{day:%b}/{name}'.replace(f'/{day:%b}/',f'/{day:%b}/'.upper())
  path=RAW/name;receipt=dict(target_month_end=str(target.date()),observed_session=str(day.date()),url=url,attempted_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
  try:
   if path.exists():body=path.read_bytes();receipt['http_status']='CACHED'
   else:
    response=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=(5,15));receipt['http_status']=response.status_code;body=response.content
    if response.status_code!=200:
     receipts.append(receipt)
     if response.status_code==404:continue
     break
    path.write_bytes(body)
   receipt.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest());x=validate_zip(body,str(day.date()));receipt.update(status='VALIDATED_OFFICIAL_DAILY_IDENTITY_ROWS',rows=len(x));receipts.append(receipt)
   x['target_month_end']=str(target.date());x['observed_session']=str(day.date());x['source_sha256']=receipt['sha256'];return x,receipts
  except (requests.RequestException,ValueError,zipfile.BadZipFile) as e:
   receipt.update(status='SOURCE_UNAVAILABLE_OR_INVALID',error=type(e).__name__);receipts.append(receipt);break
 return pd.DataFrame(),receipts

def main():
 RAW.mkdir(parents=True,exist_ok=True)
 protocol=dict(scope='Inventory exact dated NSE symbol/series/ISIN/close/volume observations for month ends2012-2019; retrieve latest available weekday within7calendar days. No interpolated prices, adjusted returns or terminal proceeds. Retain acquisition failures. No ranking/performance claim.',raw_directory=str(RAW.relative_to(ROOT)),source='Official NSE nsearchives daily bhavcopy archive',close_basis='Official nominal observed session close; not split/merger/dividend adjusted',primary_SIP_outcome_status='NOT_BUILT')
 p=OUT/'bhavcopy_protocol.json'
 if p.exists():assert json.loads(p.read_text())==protocol
 else:p.write_text(json.dumps(protocol,indent=2))
 months=pd.date_range('2012-01-31','2019-12-31',freq='ME');frames=[];receipts=[]
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  for x,r in pool.map(acquire_month,months):
   if len(x):frames.append(x)
   receipts.extend(r);print('BHAVCOPY',r[-1]['target_month_end'],r[-1].get('status',r[-1].get('http_status')),flush=True)
 allrows=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame();pd.DataFrame(receipts).to_csv(OUT/'bhavcopy_source_receipts.csv',index=False)
 if len(allrows):
  allrows.to_csv(OUT/'monthly_bhavcopy_identity_inventory.csv.gz',index=False)
  current=pd.read_csv(ROOT/'experiments/sector-price-rebuild-20261010/current_all_stock_rankings.csv',usecols=['isin'])
  allrows['outside_current_survivor_universe']=~allrows.ISIN.isin(current['isin'])
  summary=allrows.groupby('target_month_end').agg(rows=('SYMBOL','size'),unique_isins=('ISIN','nunique'),outside_current_survivor_universe=('outside_current_survivor_universe','sum'));summary.to_csv(OUT/'bhavcopy_monthly_inventory_summary.csv')
  info=dict(requested_months=len(months),recovered_months=allrows.target_month_end.nunique(),rows=len(allrows),unique_isins=allrows.ISIN.nunique(),unique_isins_outside_current_survivors=allrows.loc[allrows.outside_current_survivor_universe,'ISIN'].nunique(),verified_SIP_outcomes=0,limitations=['Full exchange inventory, not independently reconstructed NIFTY500 membership','A symbol/ISIN observation does not certify adjusted price continuity or delisting proceeds','Monthly observations cannot establish monthly whole-share execution or daily drawdown','Historical sector assignments and causal pre2020 champion training remain unbuilt'])
 else:info=dict(requested_months=len(months),recovered_months=0,verified_SIP_outcomes=0)
 (OUT/'bhavcopy_inventory_receipt.json').write_text(json.dumps(info,indent=2,default=int));print(json.dumps(info),flush=True)
if __name__=='__main__':main()
