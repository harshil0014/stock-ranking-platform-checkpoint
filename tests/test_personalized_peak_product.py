import json
from threading import Thread
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

from stock_ranker.personalized_product import parse_profile
from stock_ranker.personalized_peak_product import PeakRankingService
from stock_ranker.runtime import PROJECT_ROOT
from stock_ranker.webapp import create_server


BASE={'amount':7500,'lookback_months':36,'interval_days':30,'target_cagr_percent':20,'horizon_months':12}


def test_saved_profiles_reproduce_reviewed_research_score_and_rank():
    service=PeakRankingService(sector_tuned=False)
    expected=pd.read_csv(PROJECT_ROOT/'experiments/closing-high-recovery-20261004/reviewed_current_rankings.csv.gz',
                         usecols=['isin','profile_name','personalized_score','personalized_rank'])
    nykaa=None
    for name,frame in service.current.groupby('profile_name'):
        row=frame.iloc[0]
        payload={'amount':float(row.amount_per_contribution),'lookback_months':int(row.lookback_months),
                 'interval_days':int(row.frequency_days),'target_cagr_percent':float(row.target_cagr)*100,
                 'horizon_months':int(row.horizon_months)}
        actual,_=service._calculate(parse_profile(payload))
        target=expected[expected.profile_name.eq(name)].set_index('isin').reindex(actual['isin'])
        np.testing.assert_allclose(actual.personalized_score,target.personalized_score,rtol=0,atol=1e-9,equal_nan=True)
        np.testing.assert_allclose(actual.personalized_rank,target.personalized_rank,rtol=0,atol=0,equal_nan=True)
        if name=='base7500':nykaa=actual.loc[actual.ticker.eq('NYKAA')].iloc[0]
    assert nykaa is not None
    assert nykaa.days_since_recorded_high==1765
    assert nykaa.personalized_rank>100  # A deep drawdown does not receive near-high recovery credit.


def test_custom_profile_recalculates_and_http_mode_is_available():
    service=PeakRankingService(sector_tuned=False)
    result=service.rank({**BASE,'amount':8250},securities=['NSE:NYKAA'])
    assert result['model_id']=='closing_high_reviewed'
    assert result['row_count']==4436
    assert result['personalized_count']>1000
    assert result['evaluation_mode']=='CLOSING_HIGH_FROZEN_MODEL_RECOMPUTATION'
    assert result['rows'][0]['result_type']=='CLOSING_HIGH_REVIEWED'
    server=create_server(port=0,refresh_enabled=False)
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    root='http://127.0.0.1:'+str(server.server_address[1])
    try:
        assert urlopen(root+'/closing-high').status==200
        request=Request(root+'/api/closing-high/rank',data=json.dumps({'profile':BASE}).encode(),
                        headers={'Content-Type':'application/json'})
        response=json.load(urlopen(request))
        assert response['model_id']=='closing_high_sector'
        assert response['ranking_scope']=='WITHIN_SECTOR'
        assert response['rows'][0]['personalized_sector_rank']==1
    finally:
        server.shutdown();server.server_close();thread.join()


def test_review_evidence_and_recovered_history_reach_api_and_cache():
    service=PeakRankingService(sector_tuned=False)
    result=service.rank(BASE)
    rows={r['ticker']:r for r in result['rows']}
    for ticker in ['KPL','FRONTSP']:
        assert rows[ticker]['personalized_available']
        assert rows[ticker]['history_months']>60
        assert rows[ticker]['history_provider_symbol'].endswith('.BO')
    for ticker in ['BSE-543953','BSE-540718','BSE-543616']:
        assert not rows[ticker]['personalized_available']
        assert rows[ticker]['sme_lot_unverified']
        assert 'lot size' in rows[ticker]['blocker']
        assert rows[ticker]['xirr'] is None and rows[ticker]['shares_bought'] is None
    assert rows['LALPATHLAB']['personalized_rank']<100
    assert rows['MWL']['review_flags']
    assert rows['MWL']['terminal_price_date']=='2026-10-01'
    assert sum(r['count'] for r in result['top100_sector_concentration'])==100
    cached=service.rank(BASE)
    assert cached['cache_hit']
    assert cached['top100_sector_concentration']==result['top100_sector_concentration']


def test_frontier_bonus_uses_verified_event_date_and_nominal_prices():
    service=PeakRankingService(sector_tuned=False)
    book=service._load_book()
    dates,raw,_,nominal,factors=book.arrays['INE572D01014']
    before=dates<np.datetime64('2026-03-13')
    np.testing.assert_allclose(factors[before],3)
    np.testing.assert_allclose(factors[~before],1)
    np.testing.assert_allclose(nominal[before],raw[before]*3)
    actions=book.actions['INE572D01014']
    assert actions.iloc[0].event_date==pd.Timestamp('2026-03-13')
    assert '20260310-46' in actions.iloc[0].evidence_url
