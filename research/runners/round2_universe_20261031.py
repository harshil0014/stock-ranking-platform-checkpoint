"""Official NIFTY500 membership acquisition and survivorship-readiness audit.

Never uses a current-constituent filter to erase former members. Historical
membership effective dates, announcement dates and observation dates are distinct.
"""
from pathlib import Path
import argparse,concurrent.futures,datetime,hashlib,io,json,re,sys,time,unicodedata
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'work/round2-universe-deps'))
import numpy as np
import pandas as pd
import requests
from bs4 import BeautifulSoup

OUT=ROOT/'experiments/round2-universe-20261031'
RAW=OUT/'raw';TEXT=OUT/'text'
UA={'User-Agent':'Mozilla/5.0','Accept':'*/*'}
XLS='https://archives.nseindia.com/content/indices/IndexInclExcl.xls'
CURRENT='https://archives.nseindia.com/content/indices/ind_nifty500list.csv'
ARCHIVE='https://niftyindices.com/press-release'
NOW=lambda:datetime.datetime.now(datetime.timezone.utc).isoformat()

def write_json(name,obj):
    OUT.mkdir(parents=True,exist_ok=True);(OUT/name).write_text(json.dumps(obj,indent=2,default=str),encoding='utf-8')

def key(name):
    name=unicodedata.normalize('NFKC',str(name)).upper().replace('\ufffd','')
    return re.sub(r'[^A-Z0-9]','',re.sub(r'\b(?:LTD|LIMITED)\b','',name))

def protocol():
    OUT.mkdir(parents=True,exist_ok=True)
    doc=dict(question='Does a causally fitted champion retain rank IC above the prespecified operational hurdle in older 2012-2019 regimes on a complete point-in-time NIFTY500 universe?',
      baseline_commit='6e9bd620e4472c8280536b6120fe86d10dca65cb',
      primary_period='2012-01-01 through2019-12-31, monthly decisions; twelve-month whole-share SIP outcomes; all historical constituents including removals, suspensions and delistings',
      pass_threshold={'mean_rank_ic':0.01013492400721767,'lower_95_year_block_bound':'must exceed0.01013492400721767','bootstrap_replicates':4000},
      threshold_caveat='The0.01013 hurdle came from incremental maximum selection gains among35 related policies. It is NOT a valid null/significance threshold for raw cross-sectional IC. We preserve the requested raw-IC operational target while additionally requiring paired incremental assessment and disclosure of estimand mismatch.',
      estimator='Frozen architecture and fixed hyperparameters, refitted annually with every outcome ending strictly before each test-year January1. Never backcast2020-2026 fitted weights into2012. Same-row incumbent/control comparison where legitimately reconstructible.',
      membership='Official historical event workbook and original dated CSV observations; include entry at its effective instant and exclude at exclusion effective instant, using half-open intervals. Announcement/observation/effective dates separate. No midpoint interpolation across snapshot gaps.',
      identity='Company-name normalization is only an audit key. Price-series linkage needs verified symbol/ISIN evidence. Unknown aliases and corporate actions remain unresolved; no successor histories or survivor-only denominators substituted.',
      missing_outcomes='Retain every member-month in the coverage matrix, distinguish absence of provider symbol, insufficient lookback, unavailable horizon, unresolved corporate action and unverified terminal delisting/merger cashflows. Never use complete-case IC to claim a survivorship-free result.',
      older_regimes=['2013','2015-2016','2018','2020 supplementary stress only'],
      evaluation_gate='Do not calculate the primary model IC unless dated membership completeness, issuer identity, historical feature vintages, mature labels and delisting terminal treatment are all verified. Missing prerequisites produce a blocked-primary result, never a negative or a passed survivorship-free backtest.',
      exposed_policy='No new parameter choices based on2024-2025 results; this work is registry acquisition/readiness before any fresh model evaluation.',
      fresh_holdout=False)
    p=OUT/'protocol.json'
    if p.exists():assert json.loads(p.read_text())==doc
    else:write_json('protocol.json',doc)

def fetch(url,name,refresh=False):
    RAW.mkdir(parents=True,exist_ok=True);p=RAW/name;receipt=p.with_suffix(p.suffix+'.receipt.json')
    if p.exists() and receipt.exists() and not refresh:return json.loads(receipt.read_text())
    record=dict(url=url,retrieved_at_utc=NOW(),path=p.relative_to(ROOT).as_posix())
    try:
        r=requests.get(url,headers=UA,timeout=(10,25));record.update(status_code=r.status_code,content_type=r.headers.get('content-type'),last_modified=r.headers.get('last-modified'),final_url=r.url)
        p.write_bytes(r.content);record.update(bytes=len(r.content),sha256=hashlib.sha256(r.content).hexdigest(),success=r.status_code==200)
    except requests.RequestException as e:record.update(success=False,error=type(e).__name__+': '+str(e))
    receipt.write_text(json.dumps(record,indent=2));return record

def acquire():
    protocol();receipts=[]
    for url,name in [(ARCHIVE,'press-release.html'),(XLS,'IndexInclExcl.xls'),(CURRENT,'current_nifty500.csv'),('https://archives.nseindia.com/content/equities/namechange.csv','namechange.csv'),('https://archives.nseindia.com/content/equities/symbolchange.csv','symbolchange.csv')]:
        r=fetch(url,name);receipts.append(r);print('SOURCE',name,r.get('status_code'),r.get('bytes'),flush=True)
    soup=BeautifulSoup((RAW/'press-release.html').read_bytes(),'html.parser');catalog=[]
    for item in soup.select('.pressItem'):
        a=item.find('a',href=True)
        if not a:continue
        announced=pd.to_datetime(item.get('data-date'),errors='coerce');title=a.get_text(' ',strip=True)
        if pd.isna(announced):continue
        plausible=bool(re.search(r'\b500\b|index changes|changes? in indices|replacements? in (?:various )?(?:nifty )?indices',title,re.I))
        if not plausible or not (pd.Timestamp('2010-01-01')<=announced<=pd.Timestamp('2020-12-31')):continue
        url=requests.compat.urljoin('https://niftyindices.com',a['href'])
        catalog.append(dict(announcement_date=str(announced.date()),title=title,url=url,filename=url.split('/')[-1]))
    catalog=pd.DataFrame(catalog).drop_duplicates('url');catalog.to_csv(OUT/'press_release_catalog.csv',index=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as pool:
        jobs={pool.submit(fetch,r.url,'press_'+r.filename):r for r in catalog.itertuples()}
        for job in concurrent.futures.as_completed(jobs):
            result=job.result();receipts.append(result)
    # Archive only original exchange constituent CSV captures. CDX is discovery,
    # and its timestamps are observations, never precise reconstitution dates.
    snapshot_rows=[]
    for i,url in enumerate(['nseindia.com/content/indices/ind_cnx500list.csv','www.nseindia.com/content/indices/ind_nifty500list.csv','niftyindices.com/IndexConstituent/ind_nifty500list.csv']):
        endpoint='https://web.archive.org/cdx/search/cdx?'+requests.compat.urlencode(dict(url=url,output='json',filter='statuscode:200',collapse='digest'))
        rec=fetch(endpoint,f'cdx_{i}.json');receipts.append(rec)
        if not rec['success']:continue
        try:
            data=json.loads((RAW/f'cdx_{i}.json').read_text());header=data[0]
            for row in data[1:]:
                d=dict(zip(header,row));year=int(d['timestamp'][:4])
                if 2010<=year<=2020:snapshot_rows.append(d)
        except (ValueError,KeyError,IndexError):continue
    captures=pd.DataFrame(snapshot_rows).drop_duplicates(['timestamp','original']) if snapshot_rows else pd.DataFrame()
    captures.to_csv(OUT/'archive_capture_catalog.csv',index=False)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        jobs=[]
        for row in captures.itertuples():
            url=f'https://web.archive.org/web/{row.timestamp}id_/{row.original}'
            jobs.append(pool.submit(fetch,url,f'snapshot_{row.timestamp}.csv'))
        for job in concurrent.futures.as_completed(jobs):receipts.append(job.result())
    pd.DataFrame(receipts).to_csv(OUT/'source_receipts.csv',index=False)
    write_json('acquisition_summary.json',dict(press_catalog=len(catalog),snapshots_requested=len(captures),retrievals=len(receipts),successful=sum(bool(x['success']) for x in receipts)))
    print('ACQUIRED',len(catalog),len(captures),flush=True)

def extract_pdf_events(text,announcement_date,source_url):
    """Conservative symbol rows only; all unmatched sections stay in review log."""
    lines=text.splitlines();events=[];in500=False;mode=None;effective=None
    match=re.search(r'effective\s+(?:from|w\.?e\.?f\.?)\s*[:\-]?\s*([A-Za-z]+\s+\d{1,2},?\s+\d{4}|\d{1,2}\s+[A-Za-z]+\s+\d{4})',text,re.I)
    if match:
        dt=pd.to_datetime(match.group(1),errors='coerce')
        if not pd.isna(dt):effective=str(dt.date())
    for line in lines:
        clean=re.sub(r'\s+',' ',line).strip()
        if re.search(r'(?:S\s*&\s*P\s*)?(?:CNX|NIFTY)\s*500\b',clean,re.I) and not re.search(r'shariah|multicap|quality|momentum|industry',clean,re.I):
            in500=True;mode=None
        elif re.match(r'^\(?[A-Za-z0-9]+[.)]\s*(?:S\s*&\s*P\s*)?(?:CNX|NIFTY)\b',clean,re.I):
            in500=False;mode=None
        if not in500:continue
        if re.search(r'following compan.*(?:excluded|exclusion)',clean,re.I):mode='EXCLUDE';continue
        if re.search(r'following compan.*(?:included|inclusion)',clean,re.I):mode='INCLUDE';continue
        if mode:
            m=re.match(r'^\s*(\d+)\s+(.+?)\s{2,}([A-Z0-9&.\-]+)\s*$',line)
            if not m:m=re.match(r'^\s*(\d+)\s+(.+?)\s+([A-Z0-9&.\-]+)\s*$',line)
            if m and len(m.group(3))>1:
                events.append(dict(company=m.group(2).strip(),company_key=key(m.group(2)),symbol=m.group(3),action=mode,announcement_date=announcement_date,effective_date=effective,source_url=source_url))
    return events

def extract():
    from pypdf import PdfReader
    protocol();TEXT.mkdir(exist_ok=True)
    x=pd.read_excel(RAW/'IndexInclExcl.xls',sheet_name='Nifty 500');x.columns=x.columns.str.strip()
    x=x.rename(columns={'Scrip Name':'company','Description':'description'})
    x['effective_date']=pd.to_datetime(x['Event Date'],dayfirst=True,format='mixed',errors='raise').dt.strftime('%Y-%m-%d')
    x['company_key']=x.company.map(key);x['action']=np.where(x.description.str.contains('Inclusion'),'INCLUDE','EXCLUDE')
    x['source_url']=XLS;x['announcement_date']=None;x['symbol']=None;x['identity_status']='NAME_ONLY_UNVERIFIED_ISSUER'
    pdf=[];review=[]
    catalog=pd.read_csv(OUT/'press_release_catalog.csv')
    for row in catalog.itertuples():
        p=RAW/('press_'+row.filename)
        if not p.exists() or not p.read_bytes().startswith(b'%PDF'):continue
        try:
            text='\n'.join(page.extract_text(extraction_mode='layout') or '' for page in PdfReader(p).pages)
            (TEXT/(row.filename+'.txt')).write_text(text,encoding='utf-8')
            found=extract_pdf_events(text,row.announcement_date,row.url);pdf.extend(found)
            if '500' in text and not found:review.append(dict(url=row.url,reason='500_MENTION_WITHOUT_VALIDATED_TABLE_ROWS'))
        except Exception as e:review.append(dict(url=row.url,reason=type(e).__name__+': '+str(e)))
    p=pd.DataFrame(pdf);p.to_csv(OUT/'pdf_event_candidates.csv',index=False)
    # A PDF row receives validated status only if effective-date/action/name agrees
    # with the original workbook. No unmatched parser output enters the registry.
    matched=0
    for row in p.itertuples():
        mask=x.company_key.eq(row.company_key)&x.action.eq(row.action)&x.effective_date.eq(row.effective_date)
        if mask.sum()==1:
            x.loc[mask,'announcement_date']=row.announcement_date;x.loc[mask,'symbol']=row.symbol;x.loc[mask,'identity_status']='OFFICIAL_EVENT_SYMBOL_VERIFIED';matched+=1
        else:review.append(dict(url=row.source_url,reason=f'PDF_WORKBOOK_MATCH_COUNT_{int(mask.sum())}',company=row.company,effective_date=row.effective_date))
    x['event_id']=[hashlib.sha256(f'{a}|{b}|{d}'.encode()).hexdigest()[:20] for a,b,d in zip(x.company_key,x.action,x.effective_date)]
    x[['event_id','company','company_key','symbol','action','announcement_date','effective_date','identity_status','source_url']].to_csv(OUT/'official_membership_events.csv',index=False)
    pd.DataFrame(review).to_csv(OUT/'parser_review_queue.csv',index=False)
    write_json('event_extraction_summary.json',dict(workbook_events=len(x),min_date=x.effective_date.min(),max_date=x.effective_date.max(),pdf_candidates=len(p),workbook_pdf_matched=matched,unique_symbol_verified_events=int(x.symbol.notna().sum()),review_items=len(review)))
    print('EXTRACTED',len(x),matched,flush=True)

def reconstruct(events):
    """Return event-derived intervals with unresolved sequence errors retained."""
    active={};intervals=[];errors=[];counts=[]
    for day,g in events.groupby('effective_date',sort=True):
        for action in ['EXCLUDE','INCLUDE']:
            for row in g[g.action.eq(action)].to_dict('records'):
                issuer=row['company_key']
                if action=='EXCLUDE':
                    if issuer not in active:errors.append(dict(effective_date=day,company_key=issuer,error='EXCLUSION_WITHOUT_VERIFIED_ACTIVE_IDENTITY'));continue
                    previous=active.pop(issuer);previous['end_exclusive']=day;previous['exit_event_id']=row.get('event_id');intervals.append(previous)
                elif issuer in active:errors.append(dict(effective_date=day,company_key=issuer,error='DUPLICATE_INCLUSION'))
                else:active[issuer]=dict(company_key=issuer,company=row['company'],start_inclusive=day,end_exclusive=None,entry_event_id=row.get('event_id'),exit_event_id=None)
        counts.append(dict(effective_date=day,member_count=len(active),sequence_errors_so_far=len(errors)))
    intervals+=list(active.values())
    return pd.DataFrame(intervals),pd.DataFrame(errors),pd.DataFrame(counts)

def members_on(intervals,day):
    return intervals[intervals.start_inclusive.le(day)&(intervals.end_exclusive.isna()|intervals.end_exclusive.gt(day))].copy()

def audit():
    protocol();events=pd.read_csv(OUT/'official_membership_events.csv');intervals,errors,counts=reconstruct(events)
    intervals['completeness_status']='EVENT_DERIVED_NAME_REGISTRY_NOT_CERTIFIED_FULL_PIT'
    intervals.to_csv(OUT/'membership_intervals.csv',index=False);errors.to_csv(OUT/'identity_sequence_errors.csv',index=False);counts.to_csv(OUT/'membership_count_by_change.csv',index=False)
    # Current identities are only a coverage reference, never the universe itself.
    current=pd.read_csv(ROOT/'experiments/sector-price-rebuild-20261010/current_all_stock_rankings.csv',usecols=['isin','ticker','company']);current['company_key']=current.company.map(key)
    unique=current[~current.company_key.duplicated(keep=False)].set_index('company_key')
    symbols=events.dropna(subset=['symbol']).groupby('company_key').symbol.agg(lambda s:'|'.join(sorted(set(s))))
    registry=intervals[['company_key','company']].drop_duplicates('company_key').copy();registry['verified_event_symbols']=registry.company_key.map(symbols)
    registry['candidate_current_isin']=registry.company_key.map(unique['isin']);registry['candidate_current_ticker']=registry.company_key.map(unique.ticker)
    registry['price_identity_status']=np.where(registry.candidate_current_isin.notna(),'NAME_MATCH_ONLY_REQUIRES_ISSUER_VERIFICATION','NO_CURRENT_NAME_MATCH_KEEP_IN_DENOMINATOR')
    registry.to_csv(OUT/'historical_identity_registry.csv',index=False)
    # Exact-year source coverage matrix. A name match does not establish issuer
    # continuity or a price path and is never promoted to VERIFIED_PRICE.
    priceaudit=pd.read_csv(ROOT/'experiments/sector-price-rebuild-20261010/history_source_audit.csv')
    known=priceaudit.set_index('isin').status.to_dict();matrix=[]
    refs=registry.set_index('company_key')
    for day in pd.date_range('2012-01-31','2019-12-31',freq='ME'):
        d=str(day.date())
        for row in members_on(intervals,d).itertuples():
            ref=refs.loc[row.company_key];isin=ref.candidate_current_isin
            matrix.append(dict(decision_date=d,company_key=row.company_key,company=row.company,candidate_current_isin=isin,candidate_current_ticker=ref.candidate_current_ticker,existing_history_receipt=known.get(isin,'NO_MATCH'),price_status='UNVERIFIED_IDENTITY_OR_ACTION_CONTINUITY',future_outcome_status='NOT_REBUILT_NO_TERMINAL_ASSUMPTION',membership_certified=not bool(len(errors[errors.effective_date.le(d)]))))
    matrix=pd.DataFrame(matrix);matrix.to_csv(OUT/'member_month_price_outcome_coverage.csv.gz',index=False)
    coverage=matrix.groupby('decision_date').agg(event_derived_members=('company_key','size'),name_matched_current=('candidate_current_isin','count'),membership_certified=('membership_certified','all')).reset_index();coverage['unmatched_members']=coverage.event_derived_members-coverage.name_matched_current;coverage['verified_terminal_outcomes']=0;coverage.to_csv(OUT/'monthly_readiness_coverage.csv',index=False)
    write_json('primary_evaluation_status.json',dict(status='BLOCKED_PREREQUISITES_NOT_A_FAILED_MODEL',primary_ic=None,reason=['Official workbook has no issuer identifiers; historical names must be linked with official symbol/ISIN histories','Unresolved renamed-issuer and temporary-inclusion sequence conflicts must be reconciled against dated snapshots','All member-months are retained; delisted/merged/suspended identities need verified prices and terminal proceeds rather than survivor-only complete cases','Original prepared labels begin2016 and fitted champion folds begin2020; older causal full-champion training/label pipeline has not yet been reconstructed'],monthly_rows=len(matrix),historic_name_keys=registry.company_key.nunique(),unmatched_name_keys=int(registry.candidate_current_isin.isna().sum()),sequence_conflicts=len(errors),reconstruction_source='Official NSE Nifty500 inclusion/exclusion workbook through2020-09-14',literature_scaffold_has_historical_snapshots=False))
    print('AUDIT',len(matrix),len(errors),int(registry.candidate_current_isin.isna().sum()),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['protocol','acquire','extract','audit']);a=p.parse_args();globals()[a.stage]()
