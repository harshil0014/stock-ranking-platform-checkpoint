import sys,json,subprocess
from pathlib import Path
import pandas as pd
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import prospective_ledger_20261031 as p

def test_exchange_time_is_not_replaced_with_observation_time():
    r=p.normalize_events([dict(symbol='ABC',an_dt='30-Oct-2026 17:10',subject='Result')],'announcements','2026-10-31T12:00:00+00:00')[0]
    assert r['exchange_timing_fields']['an_dt']=='30-Oct-2026 17:10'
    assert r['observed_at_utc']=='2026-10-31T12:00:00+00:00'

def test_invalid_feed_schema_is_not_empty_clean_feed():
    with pytest.raises(ValueError):p.normalize_events({'error':'blocked'},'announcements','today')

def test_stale_or_known_invalidated_stock_cannot_retain_rank():
    x=pd.DataFrame(dict(isin=['a','b'],sector=['s','s'],personalized_score=[.9,.8],personalized_sector_rank=[1,2],evidence_fraction=[1,1]))
    assert all(r['hysteresis_rank'] is None for r in p.hysteresis_state(x,{'s':['a','b']},fresh=False))
    rows=p.hysteresis_state(x,{'s':['a','b']},fresh=True,known_blocked=['a'])
    assert rows[0]['status']=='RESET_KNOWN_EVENT' and rows[0]['hysteresis_rank'] is None
    assert rows[1]['hysteresis_rank']==1

def test_append_only_cas_and_idempotence(tmp_path,monkeypatch):
    repo=tmp_path/'repo';repo.mkdir();remote=tmp_path/'remote.git'
    def g(*args):return subprocess.check_output(['git',*args],cwd=repo,stderr=subprocess.DEVNULL)
    g('init');g('config','user.email','ledger-test@example.invalid');g('config','user.name','Ledger Test');g('commit','--allow-empty','-m','seed')
    subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True);g('remote','add','origin',str(remote))
    monkeypatch.setattr(p,'ROOT',repo);monkeypatch.setattr(p,'WORK',tmp_path/'work')
    first=p.append_record({'scores.csv.gz':b'one'},'prospective/records/2026-10-31/test',{'eligible':False},b'{"protocol":1}\n')
    retry=p.append_record({'scores.csv.gz':b'changed'},'prospective/records/2026-10-31/test',{'eligible':True},b'{"protocol":1}\n')
    assert retry['status']=='ALREADY_RECORDED' and retry['record_metadata']=={'eligible':False}
    assert g('show',first['commit']+':prospective/records/2026-10-31/test/scores.csv.gz')==b'one'
    second=p.append_record({'scores.csv.gz':b'two'},'prospective/records/2026-11-01/test',{'eligible':False},b'{"protocol":1}\n')
    manifest=json.loads(g('show',second['commit']+':prospective/records/2026-11-01/test/manifest.json'))
    assert manifest['previous_manifest_sha256']==first['manifest_sha256']
    assert g('merge-base','--is-ancestor',first['commit'],second['commit'])==b''
    assert p.verify_ledger()['records']==2
    with pytest.raises(RuntimeError,match='protocol differs'):
        p.append_record({'scores.csv.gz':b'three'},'prospective/records/2026-11-02/test',{},b'{"protocol":2}')

def test_paginated_financial_metadata_preserves_revision_and_source_times():
    raw={'data':[dict(seq_Id='123',symbol='ABC',type='Integrated Filing- Financials',broadcast_Date='30-Oct-2026 14:00',revised_Date='31-Oct-2026 11:00',qe_Date='30-SEP-2026',xbrl='https://example.invalid/123.xml')],'totalCount':1,'size':20,'page':0}
    event=p.normalize_events(raw,'integrated_financials','2026-10-31T12:00:00+00:00')[0]
    assert event['source_record_id']=='123' and event['attachment_url'].endswith('123.xml')
    assert event['exchange_timing_fields']['revised_Date']=='31-Oct-2026 11:00'
    assert event['observation_time_basis']=='HTTP_RESPONSE_RECEIVED'

def test_first_seen_time_is_carried_without_claiming_old_capture_bound_is_exact(monkeypatch):
    older=dict(event_id='same',observed_at_utc='2026-10-30T12:00:00Z')
    monkeypatch.setattr(p,'git',lambda *args,**kwargs: b'head' if args[0]=='rev-parse' else b'prospective/records/2026-10-30/day/events.json\n')
    monkeypatch.setattr(p,'read_blob',lambda *args:json.dumps([older]).encode())
    current=dict(event_id='same',observed_at_utc='2026-10-31T12:00:00Z',observation_time_basis='HTTP_RESPONSE_RECEIVED')
    event=p.retain_first_observations([current])[0]
    assert event['first_observed_at_utc']==older['observed_at_utc']
    assert event['first_observed_time_basis']=='LEGACY_CAPTURE_START_BOUND'

def test_repeated_pagination_page_never_counts_as_complete_coverage(tmp_path,monkeypatch):
    class Response:
        status_code=200
        headers={'Content-Type':'application/json'}
        def __init__(self,payload):self.payload=payload;self.content=json.dumps(payload).encode()
        def json(self):return self.payload
        def raise_for_status(self):pass
    class Session:
        headers={}
        def get(self,url,timeout):
            if 'integrated-filing-results' in url:
                return Response({'data':[dict(seq_Id='1',symbol='ABC',creation_Date='31-Oct-2026 11:00')],'totalCount':2,'page':0,'size':1})
            return Response([])
    monkeypatch.setattr(p.requests,'Session',Session);monkeypatch.setattr(p,'WORK',tmp_path)
    blobs,receipts=p.capture_events(p.dt.date(2026,10,31),'2026-10-31T12:00:00+00:00')
    integrated=next(r for r in receipts if r['source']=='integrated_financials')
    assert integrated['status']=='PARTIAL_PAGE_COVERAGE' and integrated['rows']==1
    assert len(integrated['pages'])==2
