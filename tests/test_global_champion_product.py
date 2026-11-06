import json
import shutil
import pytest
from stock_ranker.global_champion_product import GlobalChampionSelection, DEFAULT_PACKAGE
from stock_ranker.personalized_product import parse_profile, PersonalizationError

BASE=dict(amount=7500,lookback_months=36,interval_days=30,target_cagr_percent=20,horizon_months=12)


def test_default_selection_has_unique_complete_top20():
    package=GlobalChampionSelection()
    result=package.selection(parse_profile(BASE))
    assert result['available'] and len(result['rows'])==20
    assert len({row['isin'] for row in result['rows']})==20
    assert [row['global_champion_rank'] for row in result['rows']]==list(range(1,21))
    assert result['as_of_date']=='2026-10-03' and not result['fresh_daily_inputs']


def test_other_profile_is_explicitly_unavailable():
    result=GlobalChampionSelection().selection(parse_profile(BASE|{'amount':1000}))
    assert not result['available'] and result['rows']==[] and not result['profile_supported']


def test_tampered_runtime_fails_integrity(tmp_path):
    for name in ['manifest.json','ranking.csv','model.txt']:
        shutil.copy2(DEFAULT_PACKAGE/name,tmp_path/name)
    with (tmp_path/'ranking.csv').open('a') as file:file.write('tampered\n')
    with pytest.raises(PersonalizationError,match='integrity'):
        GlobalChampionSelection(tmp_path)


def test_normal_champion_http_entry_point_returns_global_selection():
    from threading import Thread
    from urllib.request import Request, urlopen
    from stock_ranker.webapp import create_server
    server=create_server(port=0)
    thread=Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        request=Request(f'http://127.0.0.1:{server.server_address[1]}/api/sector-champion/rank',
            data=json.dumps({'profile':BASE}).encode(),headers={'Content-Type':'application/json'})
        with urlopen(request,timeout=120) as response:payload=json.load(response)
        assert payload['global_champion']['available']
        assert len(payload['global_champion']['rows'])==20
        expected=payload.get('coverage',{}).get('total_stocks',4436)
        assert len(payload['rows'])==expected
        assert len({row['isin'] for row in payload['rows']})==expected
    finally:
        server.shutdown()
        server.server_close()
