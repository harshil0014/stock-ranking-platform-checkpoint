import concurrent.futures,requests,json,hashlib,datetime
from pathlib import Path
from bs4 import BeautifulSoup
out=Path('experiments/round2-universe-20261031');w=Path('work/round2-source-recovery');w.mkdir(exist_ok=True)
urls={
 'integrated_financials':'https://www.nseindia.com/companies-listing/corporate-integrated-filing',
 'historical_bhavcopy_20120131':'https://archives.nseindia.com/content/historical/EQUITIES/2012/JAN/cm31JAN2012bhav.csv.zip'}
def fetch(item):
 name,url=item;receipt=dict(source=name,url=url,attempted_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
 try:
  r=requests.get(url,headers={'User-Agent':'Mozilla/5.0'},timeout=(5,10));receipt.update(status_code=r.status_code,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest());(w/(name+'.body')).write_bytes(r.content)
  if name=='integrated_financials' and r.status_code==200:
   s=BeautifulSoup(r.text,'html.parser');receipt['scripts']=[v['src'] for v in s.find_all('script',src=True)]
 except requests.RequestException as e:receipt.update(status='SOURCE_UNAVAILABLE',error=type(e).__name__)
 return receipt
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:result=list(pool.map(fetch,urls.items()))
(out/'supplemental_source_recovery.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
