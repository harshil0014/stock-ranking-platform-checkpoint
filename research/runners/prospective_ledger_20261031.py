"""Append-only prospective observations on a separate data-only Git branch.

This recorder never refreshes a frozen runtime's dates, trains a model, checks
out another branch, overwrites a record, or force-pushes. Stale snapshots are
recorded as ineligible; a timestamp is not evidence of fresh market inputs.
"""
from pathlib import Path
import argparse,datetime as dt,gzip,hashlib,json,os,re,subprocess,uuid
from zoneinfo import ZoneInfo
import numpy as np
import pandas as pd
import requests

ROOT=Path(__file__).resolve().parents[2]
BRANCH='prospective-ledger'
PROTOCOL=ROOT/'research/protocols/round2_20261031.json'
WORK=ROOT/'work/prospective-ledger'
UTC=dt.timezone.utc

def canonical(value):return (json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False)+'\n').encode()
def sha(data):return hashlib.sha256(data).hexdigest()
def git(*args,input=None,env=None,check=True):
    p=subprocess.run(['git','-c','gc.auto=0','-c','maintenance.auto=false',*args],cwd=ROOT,input=input,capture_output=True,env=env)
    if check and p.returncode:raise RuntimeError(p.stderr.decode(errors='replace'))
    return p.stdout

def normalize_events(payload,source,observed):
    rows=payload if isinstance(payload,list) else payload.get('data') if isinstance(payload,dict) else None
    if not isinstance(rows,list):raise ValueError('Expected a list of exchange records')
    result=[]
    for raw in rows:
        if not isinstance(raw,dict):continue
        timing={k:str(v)[:200] for k,v in raw.items() if v is not None and not isinstance(v,(dict,list)) and (any(s in k.lower() for s in ['date','time','period']) or k.lower() in ['an_dt','exchdisstime','dissemtime'])}
        item=dict(source=source,symbol=str(raw.get('symbol') or raw.get('sm_symbol') or '')[:80],isin=str(raw.get('isin') or '')[:40],
            subject=str(raw.get('desc') or raw.get('subject') or raw.get('relatingTo') or raw.get('type') or raw.get('companyName') or '')[:500],
            source_record_id=str(raw.get('seq_Id') or raw.get('seq_id') or '')[:100],
            exchange_timing_fields=timing,attachment_url=str(raw.get('attchmntFile') or raw.get('xbrl') or raw.get('ixbrl') or raw.get('url') or '')[:1000])
        record_id=item.pop('source_record_id')
        if source=='integrated_financials':item['source_record_id']=record_id
        item['event_id']=sha(canonical(item));item['source_record_id']=record_id;item['observed_at_utc']=observed
        item['observation_time_basis']='HTTP_RESPONSE_RECEIVED'
        item['timing_interpretation']='Exchange timestamp strings retained verbatim; first-observed time is separate. No certified lateness label.'
        result.append(item)
    return result

def capture_events(day,observed):
    start=day-dt.timedelta(days=7)
    params=f'index=equities&from_date={start:%d-%m-%Y}&to_date={day:%d-%m-%Y}'
    urls={
      'announcements':'https://www.nseindia.com/api/corporate-announcements?'+params,
      'financial_results':'https://www.nseindia.com/api/corporates-financial-results?'+params+'&period=Quarterly',
      'integrated_financials':'https://www.nseindia.com/api/integrated-filing-results?'+params+'&type=Integrated%20Filing-%20Financials&page=1&size=1000',
      'corporate_actions':'https://www.nseindia.com/api/corporates-corporateActions?'+params}
    session=requests.Session();session.headers.update({'User-Agent':'Mozilla/5.0','Accept':'application/json','Referer':'https://www.nseindia.com/'})
    receipts=[];events=[];blobs={}
    try:session.get('https://www.nseindia.com/',timeout=15)
    except requests.RequestException:pass
    for name,url in urls.items():
        receipt=dict(source=name,url=url,requested_from=start.isoformat(),requested_to=day.isoformat(),observed_at_utc=observed)
        try:
            response=session.get(url,timeout=25);body=response.content
            received=dt.datetime.now(UTC).isoformat(timespec='microseconds')
            receipt['response_observed_at_utc']=received
            receipt.update(http_status=response.status_code,response_sha256=sha(body),response_bytes=len(body),content_type=response.headers.get('Content-Type',''))
            # Raw source receipt remains local; publish only normalized timing facts.
            local=WORK/'raw'/day.isoformat()/f'{observed.replace(":","-")}_{name}.body.gz';local.parent.mkdir(parents=True,exist_ok=True)
            with local.open('xb') as f:f.write(gzip.compress(body,mtime=0))
            if response.status_code==200:
                try:
                    payload=response.json();normalized=normalize_events(payload,name,received)
                    total=payload.get('totalCount') if isinstance(payload,dict) else None
                    pages=[dict(url=url,response_sha256=sha(body),rows=len(normalized),response_observed_at_utc=received)]
                    stable=True;page=1
                    while total is not None and len(normalized)<int(total) and page<30:
                        page+=1;nexturl=url.replace('page=1&','page='+str(page)+'&')
                        if nexturl==url:break
                        extra=session.get(nexturl,timeout=25);extra.raise_for_status();timestamp=dt.datetime.now(UTC).isoformat(timespec='microseconds');data=extra.json()
                        raw=extra.content;dest=WORK/'raw'/day.isoformat()/f'{observed.replace(":","-")}_{name}_page{page}.body.gz'
                        with dest.open('xb') as stream:stream.write(gzip.compress(raw,mtime=0))
                        more=normalize_events(data,name,timestamp);pages.append(dict(url=nexturl,response_sha256=sha(raw),rows=len(more),response_observed_at_utc=timestamp))
                        stable &= data.get('totalCount')==total
                        known={r['event_id'] for r in normalized};novel=[r for r in more if r['event_id'] not in known]
                        normalized.extend(novel)
                        if not novel:break
                    events.extend(normalized)
                    complete=total is None or (stable and len(normalized)==int(total))
                    receipt.update(status='CAPTURED' if complete else 'PARTIAL_PAGE_COVERAGE',rows=len(normalized),reported_total_count=total,pages=pages,coverage='Requested seven-day range; pagination checked where counts supplied; population completeness not independently certified')
                except (ValueError,TypeError) as e:receipt.update(status='INVALID_RESPONSE_SCHEMA',error=str(e))
            else:receipt.update(status='SOURCE_UNAVAILABLE',coverage='Unknown; never interpret acquisition failure as zero announcements')
        except requests.RequestException as e:receipt.update(status='SOURCE_UNAVAILABLE',error=type(e).__name__,coverage='Unknown')
        receipts.append(receipt)
    blobs['events.json']=canonical(events);blobs['event_receipts.json']=canonical(receipts)
    return blobs,receipts

def hysteresis_state(scores,previous=None,margin=.02,fresh=False,known_blocked=()):
    # Unknown event coverage remains explicit in the record; only known flags can
    # invalidate individual identities. Stale full inputs invalidate all states.
    from ten_hypotheses_20261031 import hysteresis_order
    previous=previous or {};blocked=set(known_blocked);rows=[]
    for sector,g in scores.groupby('sector',sort=True):
        usable=g[g.evidence_fraction.gt(0)&~g['isin'].isin(blocked)] if fresh else g.iloc[0:0]
        values=usable.set_index('isin').personalized_score.to_dict()
        old=[i for i in previous.get(sector,[]) if i in values];oldset=set(old)
        incoming=sorted((i for i in values if i not in oldset),key=lambda i:(-values[i],i))
        order=hysteresis_order(old+incoming,values,margin);ranks={i:n+1 for n,i in enumerate(order)}
        for r in g.itertuples(index=False):
            status='ACTIVE' if r.isin in ranks else 'RESET_STALE_INPUT' if not fresh else 'RESET_KNOWN_EVENT' if r.isin in blocked else 'RESET_NO_PRICE_EVIDENCE'
            rows.append(dict(isin=r.isin,sector=sector,raw_rank=int(r.personalized_sector_rank),hysteresis_rank=ranks.get(r.isin),status=status))
    return rows

def score_snapshot(day,observed):
    from stock_ranker.sector_champion_product import ChampionScorer
    from stock_ranker.personalized_product import parse_profile
    scorer=ChampionScorer();profile=parse_profile(dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12))
    x=scorer.score(profile);e=scorer.sip_profiles[scorer.sip_profiles.profile_name.eq('base7500')]
    x=scorer.add_sip(x,profile,e).sort_values('isin')
    # Explicit immutable issue time; source date is never replaced with today.
    asof=scorer.manifest['as_of_date'];actual=dt.datetime.now(ZoneInfo('Asia/Kolkata')).date()
    fresh=(asof==day.isoformat() and day==actual)
    cols=['isin','sector','decision_date','personalized_score','personalized_sector_rank','original_champion_score','recency_adjustment','sip_profit_adjustment','evidence_fraction']
    csv=x[cols].to_csv(index=False,lineterminator='\n').encode()
    metadata=dict(stream='complete_champion_frozen_runtime_v1',profile=dict(amount=7500,interval_days=30,lookback_months=36,target_cagr=.20,horizon_months=12),
      source_as_of=asof,requested_issue_date=day.isoformat(),recorded_at_utc=observed,backfilled_requested_date=day!=actual,
      eligible_for_fresh_holdout=fresh,eligibility_reason='Date-aligned issue; event/source coverage must still be checked' if fresh else 'STALE_OR_BACKFILLED_INPUTS: recording a frozen October3 snapshot does not create a current-date forecast',
      rows=len(x),evidence_fallbacks=int(x.evidence_fraction.le(0).sum()),model_manifest_sha256=sha((scorer.package/'manifest.json').read_bytes()),runtime_hashes=scorer.manifest['files'],
      full_daily_champion_refresh_available=False,suspension_coverage='UNKNOWN',corporate_action_point_in_time_coverage='UNKNOWN',
      hysteresis_policy='margin0.02; all stale states reset; known event/data flags override retention')
    return x,gzip.compress(csv,mtime=0),metadata

def read_blob(ref,path,default=None):
    p=subprocess.run(['git','show',ref+':'+path],cwd=ROOT,capture_output=True)
    if p.returncode:return default
    return p.stdout

def previous_orders():
    found=git('ls-remote','origin','refs/heads/'+BRANCH).decode().split()
    if found:git('fetch','origin','refs/heads/'+BRANCH+':refs/remotes/origin/'+BRANCH)
    local=git('rev-parse','--verify','refs/heads/'+BRANCH,check=False).decode().strip()
    head=local or (found[0] if found else None)
    if not head:return {}
    message=git('log','-1','--format=%B',head).decode();match=re.search(r'^Record-Path: (.+)$',message,re.M)
    if not match:return {}
    payload=read_blob(head,match.group(1)+'/hysteresis_state.json')
    if payload is None:return {}
    rows=json.loads(payload)['rows'];orders={}
    for row in sorted((r for r in rows if r['status']=='ACTIVE'),key=lambda r:r['hysteresis_rank']):orders.setdefault(row['sector'],[]).append(row['isin'])
    return orders


def retain_first_observations(events):
    """First seen by this recorder, never substituted for exchange publication."""
    local=git('rev-parse','--verify','refs/heads/'+BRANCH,check=False).decode().strip()
    seen={}
    if local:
        for path in git('ls-tree','-r','--name-only',local,'--','prospective/records').decode().splitlines():
            if path.endswith('/events.json'):
                for event in json.loads(read_blob(local,path)):
                    t=event.get('first_observed_at_utc',event['observed_at_utc'])
                    key=event['event_id']
                    candidate=(t,event.get('first_observed_time_basis',event.get('observation_time_basis','LEGACY_CAPTURE_START_BOUND')))
                    if key not in seen or t<seen[key][0]:seen[key]=candidate
    for event in events:
        t,basis=seen.get(event['event_id'],(event['observed_at_utc'],event.get('observation_time_basis','LEGACY_CAPTURE_START_BOUND')))
        event['first_observed_at_utc']=t;event['first_observed_time_basis']=basis
    return events

def append_record(blobs,path,metadata,protocol,publish=False):
    if not re.fullmatch(r'prospective/records/\d{4}-\d{2}-\d{2}/[a-zA-Z0-9_-]+',path):raise ValueError('Invalid record path')
    ref='refs/heads/'+BRANCH;remote='refs/remotes/origin/'+BRANCH
    found=git('ls-remote','origin','refs/heads/'+BRANCH).decode().split()
    if found:
        git('fetch','origin','refs/heads/'+BRANCH+':'+remote)
    local=git('rev-parse','--verify',ref,check=False).decode().strip()
    remote_head=found[0] if found else None
    if local and remote_head and local!=remote_head:
        if subprocess.run(['git','merge-base','--is-ancestor',remote_head,local],cwd=ROOT).returncode:
            if subprocess.run(['git','merge-base','--is-ancestor',local,remote_head],cwd=ROOT).returncode:raise RuntimeError('Ledger heads diverged; never rewrite or discard either history')
            git('update-ref',ref,remote_head,local);local=remote_head
    parent=local or remote_head
    if parent:
        existing=read_blob(parent,path+'/manifest.json')
        if existing is not None:
            obj=json.loads(existing)
            # Idempotent retries verify every previously recorded byte, not only
            # the existence of a filename.
            for name,h in obj['files'].items():
                payload=read_blob(parent,path+'/'+name)
                if payload is None or sha(payload)!=h:raise RuntimeError('Existing record integrity failure')
            if publish:git('push','origin',ref+':refs/heads/'+BRANCH)
            return dict(status='ALREADY_RECORDED',commit=parent,record_path=path,manifest_sha256=sha(existing),record_metadata=obj['metadata'])
        modified=git('log','--format=','--name-status','--diff-filter=MD',parent,'--','prospective/records').decode().strip()
        if modified:raise RuntimeError('Existing ledger history contains record modifications/deletions')
        registered=read_blob(parent,'prospective/registration.json')
        if registered is None or json.loads(registered)['protocol_sha256']!=sha(protocol):raise RuntimeError('Ledger protocol differs; fork a new stream instead of silently changing it')
        message=git('log','-1','--format=%B',parent).decode();match=re.search(r'^Record-Path: (.+)$',message,re.M)
        if not match:raise RuntimeError('Ledger head lacks a recorder chain marker')
        previous_path=match.group(1);previous_bytes=read_blob(parent,previous_path+'/manifest.json')
        if previous_bytes is None:raise RuntimeError('Broken previous manifest link')
    else:previous_path=None;previous_bytes=None
    manifest=dict(schema_version=1,record_path=path,previous_record_path=previous_path,previous_manifest_sha256=sha(previous_bytes) if previous_bytes else None,
        protocol_sha256=sha(protocol),metadata=metadata,files={name:sha(data) for name,data in sorted(blobs.items())})
    payloads={path+'/'+name:data for name,data in blobs.items()};payloads[path+'/manifest.json']=canonical(manifest)
    if not parent:payloads['prospective/registration.json']=canonical(dict(protocol_sha256=sha(protocol),protocol=json.loads(protocol),source_code_commit=git('rev-parse','HEAD').decode().strip()))
    WORK.mkdir(parents=True,exist_ok=True);index=WORK/f'index-{uuid.uuid4().hex}'
    env=os.environ.copy();env['GIT_INDEX_FILE']=str(index)
    try:
        git('read-tree',parent or '--empty',env=env)
        updates=[]
        for name,data in payloads.items():
            if parent and read_blob(parent,name) is not None:raise RuntimeError('Refusing to overwrite an existing ledger path')
            oid=git('hash-object','-w','--stdin',input=data).decode().strip();updates.append(f'100644 {oid}\t{name}\n')
        git('update-index','--index-info',input=''.join(updates).encode(),env=env)
        tree=git('write-tree',env=env).decode().strip()
        message=f'Append prospective observation {path}\n\nRecord-Path: {path}\nManifest-SHA256: {sha(payloads[path+"/manifest.json"])}\n'
        args=['commit-tree',tree]+(['-p',parent] if parent else [])
        commit=git(*args,input=message.encode()).decode().strip()
        if parent:
            changes=git('diff-tree','--no-commit-id','--name-status','-r',parent,commit).decode().splitlines()
            if any(not line.startswith('A\t') for line in changes):raise RuntimeError('Ledger update was not append-only')
        git('update-ref',ref,commit,local or '0'*40)
        if publish:git('push','origin',ref+':refs/heads/'+BRANCH)
    finally:
        if index.exists():index.unlink()
    return dict(status='APPENDED',commit=commit,record_path=path,manifest_sha256=sha(payloads[path+'/manifest.json']),published=publish,record_metadata=metadata)

def verify_ledger(ref=BRANCH,expected_protocol=None):
    head=git('rev-parse','--verify',ref).decode().strip()
    changed=git('log','--format=','--name-status','--diff-filter=MD',head,'--','prospective/records').decode().strip()
    if changed:raise RuntimeError('Ledger history modified or deleted records')
    registration=json.loads(read_blob(head,'prospective/registration.json'))
    if expected_protocol is not None and (sha(expected_protocol)!=registration['protocol_sha256'] or json.loads(expected_protocol)!=registration['protocol']):raise RuntimeError('Registered protocol differs from expected protocol')
    paths=git('ls-tree','-r','--name-only',head,'--','prospective/records').decode().splitlines()
    manifests={p[:-len('/manifest.json')] for p in paths if p.endswith('/manifest.json')}
    message=git('log','-1','--format=%B',head).decode();marker=re.search(r'^Record-Path: (.+)$',message,re.M)
    if not marker:raise RuntimeError('Missing ledger head marker')
    path=marker.group(1);seen=set();blobs=0
    while path:
        if path in seen or path not in manifests:raise RuntimeError('Broken or cyclic manifest chain')
        seen.add(path);m=json.loads(read_blob(head,path+'/manifest.json'))
        if m['record_path']!=path or m['protocol_sha256']!=registration['protocol_sha256']:raise RuntimeError('Manifest registration mismatch')
        for name,digest in m['files'].items():
            payload=read_blob(head,path+'/'+name)
            if payload is None or sha(payload)!=digest:raise RuntimeError('Record blob hash mismatch')
            blobs+=1
        previous=m['previous_record_path']
        if previous:
            payload=read_blob(head,previous+'/manifest.json')
            if payload is None or sha(payload)!=m['previous_manifest_sha256']:raise RuntimeError('Manifest chain hash mismatch')
        elif m['previous_manifest_sha256'] is not None:raise RuntimeError('Invalid root manifest link')
        path=previous
    if seen!=manifests:raise RuntimeError('Unlinked ledger records')
    return dict(status='VERIFIED',head=head,records=len(seen),record_blobs=blobs,append_only_history=True)

def main():
    p=argparse.ArgumentParser();p.add_argument('--date',default=None);p.add_argument('--slot',default='daily-1930');p.add_argument('--publish',action='store_true');p.add_argument('--no-events',action='store_true');p.add_argument('--verify',action='store_true');args=p.parse_args()
    if args.verify:
        print(json.dumps(verify_ledger(expected_protocol=PROTOCOL.read_bytes()),indent=2));return
    day=dt.date.fromisoformat(args.date) if args.date else dt.datetime.now(ZoneInfo('Asia/Kolkata')).date()
    observed=dt.datetime.now(UTC).isoformat(timespec='microseconds')
    scores,scorebytes,metadata=score_snapshot(day,observed)
    path=f'prospective/records/{day.isoformat()}/{args.slot}'
    blobs={'scores.csv.gz':scorebytes}
    if args.no_events:
        receipts=[dict(status='NOT_REQUESTED',coverage='Unknown')];blobs['events.json']=canonical([]);blobs['event_receipts.json']=canonical(receipts)
    else:
        event_blobs,receipts=capture_events(day,observed);blobs.update(event_blobs)
    prior=previous_orders()
    events=retain_first_observations(json.loads(blobs['events.json']))
    blobs['events.json']=canonical(events)
    metadata['event_capture_status']={r.get('source','all'):r['status'] for r in receipts}
    metadata['eligible_for_fresh_holdout'] &= all(r['status']=='CAPTURED' for r in receipts)
    # Full feed date coverage is not certified by one HTTP success. Future
    # activation requires a documented complete daily input pipeline.
    if not metadata['full_daily_champion_refresh_available']:metadata['eligible_for_fresh_holdout']=False
    known_blocked={e['isin'] for e in events if e['source']=='corporate_actions' and e.get('isin')}
    metadata['known_event_blocked_isins']=sorted(known_blocked)
    state=hysteresis_state(scores,previous=prior,margin=.02,fresh=metadata['eligible_for_fresh_holdout'],known_blocked=known_blocked)
    blobs['hysteresis_state.json']=canonical(dict(stream=metadata['stream'],margin=.02,rows=state))
    blobs['score_receipt.json']=canonical(metadata)
    metadata['recorder_sha256']=sha(Path(__file__).read_bytes());metadata['recording_code_commit']=git('rev-parse','HEAD').decode().strip()
    result=append_record(blobs,path,metadata,PROTOCOL.read_bytes(),args.publish)
    recorded=result.pop('record_metadata')
    print(json.dumps(dict(**result,eligible_for_fresh_holdout=recorded['eligible_for_fresh_holdout'],source_as_of=recorded['source_as_of'],event_capture_status=recorded['event_capture_status']),indent=2))

if __name__=='__main__':main()
