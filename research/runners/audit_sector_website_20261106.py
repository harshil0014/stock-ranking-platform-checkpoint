"""Read-only HTTP audit against the low-load local website; no parallel fitting."""
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import json
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'work/sector-ranking-audit-20261106'
URL='http://127.0.0.1:8765'
BASE=dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12)


def request(path,body=None,content_type='application/json'):
    req=Request(URL+path,data=json.dumps(body).encode() if body is not None else None,
                headers={'Content-Type':content_type})
    try:
        with urlopen(req,timeout=240) as response:return response.status,response.read()
    except HTTPError as exc:return exc.code,exc.read()


def main():
    for attempt in range(15):
        try:
            assert request('/sector-champion')[0]==200
            break
        except URLError:
            if attempt==14:raise
            time.sleep(2)
    pages=['/','/dashboard','/sector-champion','/closing-high','/personalized','/personalized-v17',
        '/live','/overview','/rankings','/historical','/validation','/provenance','/methodology','/status','/quant-lab','/app.js','/styles.css']
    routes=[]
    for path in pages:
        status,raw=request(path)
        assert status==200,(path,status)
        routes.append(dict(path=path,http=status))
        if path=='/app.js':
            text=raw.decode()
            assert 'async function openChampionStock' in text
            assert 'currentRankingRecovery' in text
            assert 'Ranking unavailable:' not in text
    # Include correct query parameters for historical/provenance requests.
    archive_routes=['/api/health','/api/live/dashboard','/api/live/overview',
        '/api/live/stock?ticker=NYKAA','/api/live/data-status','/api/research/overview',
        '/api/research/rankings','/api/research/historical?year=2023','/api/research/validation',
        '/api/research/provenance?ticker=RELIANCE','/api/research/methodology','/api/research/status',
        '/api/research/model-candidates','/api/research/quant-lab','/api/research/professor-reference',
        '/api/research/professor-acceptance']
    for path in archive_routes:
        status,raw=request(path);payload=json.loads(raw)
        routes.append(dict(path=path,http=status,available=payload.get('available'),
            status=payload.get('status'),message=payload.get('message') or payload.get('error')))
    (OUT/'after_routes.json').write_text(json.dumps(routes,indent=2),encoding='utf-8')
    # The nine profiles are the saved runtime profiles, not new fitted models.
    import csv,gzip
    with gzip.open(ROOT/'research/runtime/personalized-v17/current.csv.gz','rt',encoding='utf-8') as stream:
        profiles={}
        for row in csv.DictReader(stream):
            profiles.setdefault(row['profile_name'],dict(amount=float(row['amount_per_contribution']),
                lookback_months=int(float(row['lookback_months'])),interval_days=int(float(row['frequency_days'])),
                target_cagr_percent=round(float(row['target_cagr'])*100,5),horizon_months=12))
    assert len(profiles)==9
    results=[]
    for name,profile in profiles.items():
        status,raw=request('/api/sector-champion/rank',{'profile':profile})
        assert status==200,(name,status,raw[:150])
        payload=json.loads(raw);rows=payload['rows']
        assert len(rows)==len({r['isin'] for r in rows})==5547
        assert payload['sector_unranked_count']==0 and payload['sector_ranked_count']==5547
        assert all(r['personalized_available'] and r['sector_rank_available'] and
            1<=r['personalized_sector_rank']<=r['sector_security_count'] for r in rows)
        assert all(r['personalized_sector_peer_count']==r['sector_security_count'] for r in rows)
        quality=[r for r in rows if r['coverage_tier']=='FUNDAMENTALS_FALLBACK']
        assert {r['ticker'] for r in quality}=={'BSE-545020','BSE-545021','HGSINDIALT'}
        assert all(r['days_since_recorded_high'] is None and r['xirr'] is None and not r['execution_available'] for r in quality)
        assert any(r['ticker']=='NYKAA' and r['personalized_sector_rank']>=1 for r in rows)
        json.dumps(payload,allow_nan=False)
        results.append(dict(profile_name=name,ranked=5547,missing_sector_ranks=0,
            tiers=dict(Counter(r['coverage_tier'] for r in rows))))
        print('PASS',name,'5547 sector ranks',flush=True)
        if name=='base7500':
            (OUT/'current_response.json').write_bytes(raw)
    assert request('/api/sector-champion/rank',{'profile':BASE|{'amount':0}})[0]==400
    assert request('/api/sector-champion/rank',{'profile':BASE},content_type='text/plain')[0]==415
    status,raw=request('/api/sector-champion/rank',{'profile':BASE,'securities':['BSE:545020','HGSINDIALT','NSE:NYKAA']})
    assert status==200
    selected=[r for r in json.loads(raw)['rows'] if r['requested_code']]
    assert len(selected)==3 and all(r['personalized_sector_rank'] is not None for r in selected)
    receipt=dict(passed=True,checked_at_utc=datetime.now(timezone.utc).isoformat(),
        page_asset_routes_passed=len(pages),saved_profiles=results,all_stocks_ranked=5547,
        missing_sector_ranks=0,quality_only_stocks=3,invalid_request_checks_passed=True,
        alias_requests_passed=True,browser_visual_check=False,
        browser_limitation='Local browser use disabled in Work settings',
        archive_limitations=[r for r in routes if r['http']>=400 or r.get('available') is False])
    (OUT/'http_verification.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    print('PASS all sector profiles and current search; archived limitations:',len(receipt['archive_limitations']),flush=True)


if __name__=='__main__':main()
