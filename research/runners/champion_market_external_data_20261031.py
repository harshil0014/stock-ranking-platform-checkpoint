"""Public BSE price and IIMA factor acquisition, with explicit unavailable TRI receipt."""
from pathlib import Path
import requests,json,hashlib,datetime
import champion_market_common_20261031 as c

def acquire(url,params,dest):
 headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.bseindia.com/'};r=requests.get(url,params=params,headers=headers,timeout=(8,45));dest.write_bytes(r.content)
 return dict(url=r.url,http_status=r.status_code,bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest(),retrieved_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())

def main():
 work=c.ROOT/'work/champion-vs-market-20261031';work.mkdir(parents=True,exist_ok=True)
 for name,ticker in [('price','BSE500'),('tri','BSE500T')]:
  receipt=acquire('https://api.bseindia.com/BseIndiaAPI/api/ProduceCSVForDate/w',dict(strIndex=ticker,dtFromDate='01/01/2015',dtToDate='30/09/2026',period='D'),work/f'bse500-{name}.body');receipt['basis']='PRICE_ONLY_NOT_TRI' if name=='price' else 'EMPTY_UNAVAILABLE' if not receipt['bytes'] else 'REQUIRES_SCHEMA_VALIDATION';c.save('bse_acquisition_receipt.json' if name=='price' else 'bse_tri_acquisition_receipt.json',receipt)
 url='https://faculty.iima.ac.in/iffm/Indian-Fama-French-Momentum/DATA/2025-12_FourFactors_and_Market_Returns_Daily_SurvivorshipBiasAdjusted.csv';receipt=acquire(url,None,work/'iima_daily.csv');receipt['attribution']='Agarwalla, S.K., Jacob, J., and Varma, J.R.(2013). Four factor model in Indian equities market. IIMA W.P.2013-09-05. Source release2025-12; retrospectively revised underlying data.';c.save('iima_acquisition_receipt.json',receipt)
if __name__=='__main__':main()
