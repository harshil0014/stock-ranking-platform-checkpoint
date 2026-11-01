"""One delivery-information head against a matched price/volume control."""
import os
for key in ['OPENBLAS_NUM_THREADS','OMP_NUM_THREADS','MKL_NUM_THREADS','NUMEXPR_NUM_THREADS']:os.environ[key]='1'
from pathlib import Path
import datetime,hashlib,io,json,pickle,zipfile
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
ROOT=Path(__file__).resolve().parents[2]
WORK=ROOT/'work/new-information-20261101';OUT=ROOT/'experiments/new-information-20261101'
BASE=['return21','return63','return126','return252','volatility252','downside252','log_quantity','log_turnover']
EXTRA=['delivery_fraction','delivery_momentum']


def main():
    protocol=ROOT/'research/protocols/delivery_implementation_20261101.md'
    receipt=OUT/'delivery_protocol_receipt.json'
    if not receipt.exists():receipt.write_text(json.dumps(dict(sha256=hashlib.sha256(protocol.read_bytes()).hexdigest(),started_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat()),indent=2))
    with (WORK/'actual_adjusted_open_close.pkl').open('rb') as f:paths=pickle.load(f)
    mapping=pd.read_csv(ROOT/'experiments/current-data-recovery-20261003/yahoo-full-recovery-v1/yahoo_symbol_map.csv')
    rel=mapping.loc[mapping.yahoo_symbol.eq('RELIANCE.NS'),'isin'].iloc[0]
    sessions=paths[rel][0]
    features=pd.read_pickle(ROOT/'experiments/sector-price-rebuild-20261010/price_features.pkl.gz',compression='gzip')
    features=features[features.decision_date.lt('2026-01-01')].copy()
    raw=WORK/'delivery';raw.mkdir(exist_ok=True)
    receipts=[];frames=[];coverage=[]
    def fetch(label,url):
        dest=raw/label
        r=dict(label=label,url=url,requested_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
        try:
            if dest.exists():body=dest.read_bytes();r['cached']=True
            else:
                response=requests.get(url,timeout=(5,12),headers={'User-Agent':'Mozilla/5.0','Referer':'https://www.nseindia.com/'})
                r['http_status']=response.status_code;response.raise_for_status();body=response.content;dest.write_bytes(body)
            r.update(bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),observed_at_utc=datetime.datetime.now(datetime.timezone.utc).isoformat())
            return body
        except requests.RequestException as e:r['error']=str(e);return None
        finally:
            receipts.append(r);(OUT/'delivery_source_receipts.json').write_text(json.dumps(receipts,indent=2))
    for date,g in features.groupby('decision_date',sort=True):
        d=pd.Timestamp(sessions[np.searchsorted(sessions,np.datetime64(date),'left')-1]);stamp=d.strftime('%d%m%Y')
        a=fetch(f'delivery_{stamp}.csv',f'https://nsearchives.nseindia.com/products/content/sec_bhavdata_full_{stamp}.csv')
        if d<pd.Timestamp('2024-07-08'):
            name=f'cm{d:%d%b%Y}bhav.csv.zip';name=name[:4]+name[4:7].upper()+name[7:]
            url=f'https://nsearchives.nseindia.com/content/historical/EQUITIES/{d:%Y}/{d:%b}'.upper()
            # Preserve hostname/path case; only exchange month abbreviation is uppercase.
            url=f'https://nsearchives.nseindia.com/content/historical/EQUITIES/{d:%Y}/{d.strftime("%b").upper()}/{name}'
        else:
            name=f'BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip';url=f'https://nsearchives.nseindia.com/content/cm/{name}'
        b=fetch(name,url)
        rec=dict(decision_date=date,source_session=str(d.date()),matched=0)
        try:
            if a is None or b is None:raise ValueError('Source unavailable')
            delivery=pd.read_csv(io.BytesIO(a));delivery.columns=delivery.columns.str.strip()
            delivery['SYMBOL']=delivery.SYMBOL.str.strip();delivery['SERIES']=delivery.SERIES.str.strip()
            # Validate historical date inside file, not merely its URL.
            dates=pd.to_datetime(delivery.DATE1.str.strip(),format='%d-%b-%Y',errors='raise')
            if not dates.eq(d).all():raise ValueError('Wrong delivery session')
            with zipfile.ZipFile(io.BytesIO(b)) as z:
                csvs=[n for n in z.namelist() if n.lower().endswith('.csv')]
                if len(csvs)!=1:raise ValueError('Ambiguous bhavcopy members')
                identities=pd.read_csv(z.open(csvs[0]))
            identities.columns=identities.columns.str.strip()
            identities=identities.rename(columns={'TckrSymb':'SYMBOL','SctySrs':'SERIES','ISIN':'isin'})
            if 'TIMESTAMP' in identities:
                observed=pd.to_datetime(identities.TIMESTAMP,format='%d-%b-%Y',errors='raise')
            else:observed=pd.to_datetime(identities['TradDt'],errors='raise')
            if not observed.eq(d).all():raise ValueError('Wrong identity session')
            for col in ['SYMBOL','SERIES','isin']:identities[col]=identities[col].str.strip()
            identities=identities.loc[identities.SERIES.eq('EQ'),['SYMBOL','SERIES','isin']]
            h=delivery.merge(identities,on=['SYMBOL','SERIES'],validate='one_to_one')
            h=h[h.SERIES.eq('EQ')].copy()
            for col in ['DELIV_PER','TTL_TRD_QNTY','TURNOVER_LACS']:h[col]=pd.to_numeric(h[col],errors='coerce')
            h['delivery_fraction']=h.DELIV_PER/100
            h['log_quantity']=np.log1p(h.TTL_TRD_QNTY.clip(lower=0))
            h['log_turnover']=np.log1p(h.TURNOVER_LACS.clip(lower=0))
            h=g.merge(h[['isin','delivery_fraction','log_quantity','log_turnover']],on='isin',validate='one_to_one')
            h['delivery_momentum']=h.delivery_fraction*h.return21
            targets=[];ends=[]
            for isin in h['isin']:
                if isin not in paths:targets.append(np.nan);ends.append(None);continue
                ds,op,cl=paths[isin];buy=np.searchsorted(ds,np.datetime64(date),side='right');exit_=buy+20
                if exit_>=len(ds) or int((ds[buy]-np.datetime64(date)).astype(int))>7 or not np.isfinite(op[buy]) or op[buy]<=0:
                    targets.append(np.nan);ends.append(None);continue
                if (np.diff(ds[buy:exit_+1]).astype(int)>7).any():targets.append(np.nan);ends.append(None);continue
                targets.append(cl[exit_]*(1-.0025)/(op[buy]*(1+.0025))-1);ends.append(str(ds[exit_]))
            h['target']=targets;h['label_end']=ends
            h=h.dropna(subset=BASE+EXTRA+['target','label_end'])
            h=h[h.delivery_fraction.between(0,1) & h.evidence_fraction.gt(0)]
            rec['matched']=len(h)
            if len(h)<500:raise ValueError('Fewer than500 matched complete stocks')
            for col in BASE+EXTRA:h[col]=h[col].rank(pct=True)-.5
            frames.append(h[['isin','decision_date','label_end','target']+BASE+EXTRA])
            rec['status']='COMPLETE'
        except (ValueError,KeyError,zipfile.BadZipFile,pd.errors.ParserError) as e:rec.update(status='BLOCKED',reason=str(e))
        coverage.append(rec);pd.DataFrame(coverage).to_csv(OUT/'delivery_coverage.csv',index=False)
        print('DELIVERY',date,rec,flush=True)
    z=pd.concat(frames,ignore_index=True) if frames else pd.DataFrame()
    if z.empty:return gate('BLOCKED','No valid date coverage')
    z.to_pickle(WORK/'delivery_panel.pkl.gz',compression='gzip')
    counts=z.loc[z.decision_date.ge('2020-01-01')].assign(period=lambda a:np.where(a.decision_date.lt('2024-01-01'),'development','exposed')).groupby('period').decision_date.nunique().to_dict()
    if counts.get('development',0)<8 or counts.get('exposed',0)<4:return gate('BLOCKED','Insufficient development/exposed source coverage',counts=counts)
    scored=[];fits=0
    # Development first. Do not produce exposed scores if the development kill gate fails.
    for year in range(2020,2024):
        train=z[z.label_end.lt(f'{year}-01-01')];test=z[z.decision_date.str.startswith(str(year))]
        if train.decision_date.nunique()<3 or test.empty:continue
        for name,cols in [('control',BASE),('delivery',BASE+EXTRA)]:
            model=Ridge(alpha=10);model.fit(train[cols],train.target);fits+=1
            test=test.copy();test[name]=model.predict(test[cols])
        scored.append(test[['isin','decision_date','target','control','delivery']])
    if not scored:return gate('BLOCKED','No mature annual training folds')
    scored=pd.concat(scored,ignore_index=True)
    ics=[]
    for date,g in scored.groupby('decision_date'):
        ics.append(dict(decision_date=date,n=len(g),control_ic=g.control.corr(g.target,method='spearman'),delivery_ic=g.delivery.corr(g.target,method='spearman')))
    ic=pd.DataFrame(ics);ic['delta_ic']=ic.delivery_ic-ic.control_ic;ic.to_csv(OUT/'delivery_development_ic.csv',index=False)
    from champion_market_review_20261031 import block_indices
    dates=np.sort(ic.decision_date.unique());diff=ic.set_index('decision_date').loc[dates,'delta_ic'].to_numpy();rng=np.random.default_rng(20261101)
    centered=diff-diff.mean();boot=np.array([centered[block_indices(dates,365,rng)].mean() for _ in range(2000)])
    hurdle=max(.0101349,float(np.quantile(boot,.95)));passed=bool(diff.mean()>hurdle)
    # No exposed tuning even on a pass; a separate locked diagnostic can be scheduled then.
    gate('DEVELOPMENT_PASS_PENDING_LOCKED_DIAGNOSTIC' if passed else 'KILLED_DEVELOPMENT',
        'One prespecified candidate; exposed performance unopened',counts=counts,fits=fits,development_dates=len(ic),
        control_ic=float(ic.control_ic.mean()),delivery_ic=float(ic.delivery_ic.mean()),delta_ic=float(diff.mean()),hurdle=hurdle,
        exposed_evaluated=False,source_basis='Official lagged NSE delivery plus same-session official ISIN; current survivors')


def gate(status,reason,**kwargs):
    (OUT/'delivery_gate.json').write_text(json.dumps(dict(status=status,reason=reason,**kwargs),indent=2))
    print('GATE',status,reason,kwargs,flush=True)


if __name__=='__main__':main()
