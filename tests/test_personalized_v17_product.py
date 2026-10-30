import json
from threading import Thread
from urllib.request import Request, urlopen

import numpy as np
import pytest

from stock_ranker.personalized_product import parse_profile
from stock_ranker.personalized_v17_product import V17RankingService
from stock_ranker.webapp import create_server

BASE={'amount':7500,'lookback_months':36,'interval_days':30,'target_cagr_percent':20,'horizon_months':12}

@pytest.fixture(scope='module')
def service():
    return V17RankingService()

def test_all_nine_profiles_reproduce_research_and_preserve_global_ranks(service):
    for name,frame in service.current.groupby('profile_name'):
        row=frame.iloc[0]
        payload={'amount':float(row.amount_per_contribution),'lookback_months':int(row.lookback_months),
            'interval_days':int(row.frequency_days),'target_cagr_percent':round(float(row.target_cagr)*100,5),'horizon_months':12}
        result=service.rank(payload,securities=['NSE:NYKAA'])
        assert result['row_count']==4436
        assert result['model_id']=='personalized_v17_refined'
        actual={r['isin']:r for r in result['rows']}
        for stock in frame.itertuples():
            got=actual[stock.isin]
            if np.isfinite(stock.winner_score):
                assert got['personalized_rank']==stock.winner_rank
                assert got['personalized_score']==stock.winner_score
                assert got['result_type']=='PERSONALIZED_V17'
            else:
                assert got['personalized_rank'] is None
        x=frame.copy();x[service.float_features]=x[service.float_features].astype('float32')
        for col in x:
            if col.startswith(('q_','u_','market_')):x[col]=x[col].astype('float32')
        pred=service.score(x,service.reference[service.reference.profile_name.eq(name)])
        np.testing.assert_allclose(pred,x.winner_score,atol=1e-9,rtol=0,equal_nan=True)

def test_execution_replay_and_custom_profile_are_real(service):
    replay,_=service._calculate(parse_profile(BASE),use_stored_frozen_profile=False)
    expected=service.current[service.current.profile_name.eq('base7500')].set_index('isin')
    replay=replay.set_index('isin').reindex(expected.index)
    np.testing.assert_allclose(replay.winner_score,expected.winner_score,atol=1e-9,rtol=0,equal_nan=True)
    custom={**BASE,'amount':8250,'interval_days':21,'target_cagr_percent':18}
    result=service.rank(custom)
    assert result['evaluation_mode']=='V17_FROZEN_MODEL_RECOMPUTATION'
    assert result['profile']['amount']==8250
    assert result['row_count']==4436
    stocks={r['isin']:r for r in result['rows']}
    assert any(r['personalized_available'] and abs(r['personalized_score']-expected.loc[i,'winner_score'])>1e-6 for i,r in stocks.items())
    assert service.rank(custom)['cache_hit']
    sectors={r['sector'] for r in result['rows']}
    for sector in sectors:
        ranked=[r for r in result['rows'] if r['sector']==sector and r['personalized_available']]
        assert [r['personalized_sector_rank'] for r in ranked]==list(range(1,len(ranked)+1))

def test_v17_http_routes_are_separate(monkeypatch,service):
    import stock_ranker.personalized_v17_product as module
    monkeypatch.setattr(module,'_SERVICE',service)
    server=create_server(port=0,refresh_enabled=False)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    root='http://127.0.0.1:'+str(server.server_address[1])
    try:
        assert urlopen(root+'/personalized-v17').status==200
        request=Request(root+'/api/personalized-v17/rank',data=json.dumps({'profile':BASE}).encode(),headers={'Content-Type':'application/json'})
        response=json.load(urlopen(request))
        assert response['model_id']=='personalized_v17_refined'
        assert response['rows'][0]['ticker']=='MWL'
    finally:
        server.shutdown();server.server_close();thread.join()
