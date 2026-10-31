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
    with pytest.raises(RuntimeError,match='protocol differs'):
        p.append_record({'scores.csv.gz':b'three'},'prospective/records/2026-11-02/test',{},b'{"protocol":2}')
