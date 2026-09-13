from pathlib import Path
import pandas as pd
import pytest

from stock_ranker.product_price_reference import official_prior_references
from stock_ranker.product_classification import add_product_classification_and_baseline
from stock_ranker.live_website import _product_market_view


def facts():
    return pd.DataFrame([dict(ticker='EXACT',isin='INE000A01011',company='Example',series='EQ',
        primary_exchange='NSE',trade_date='2026-09-07',latest_price=None,
        official_sector=None,secondary_identity_status='EXCHANGE_SYMBOL_MATCH',secondary_sector='Sector',
        listing_date='2000-01-01',v2_eligible=False,research_v2_score=None)])


def quote(tmp_path, *, day='2026-09-04', price=100, isin='INE000A01011', volume=5):
    path=tmp_path/'nse'/day/'bhavcopy.csv';path.parent.mkdir(parents=True,exist_ok=True)
    pd.DataFrame([dict(TradDt=day,Src='NSE',FinInstrmTp='STK',ISIN=isin,TckrSymb='EXACT',
        SctySrs='EQ',ClsPric=price,TtlTradgVol=volume)]).to_csv(path,index=False)
    return path


def test_exact_official_quote_has_date_hash_and_does_not_mutate_market_or_pit(tmp_path):
    quote(tmp_path)
    source=facts(); result,audit=official_prior_references(source,tmp_path)
    pd.testing.assert_frame_equal(result[source.columns],source)
    assert result.iloc[0].product_price_reference==100
    assert result.iloc[0].product_price_date=='2026-09-04'
    assert len(result.iloc[0].product_price_source_sha256)==64
    assert audit[0]['identity']=='Exact ISIN in official UDiFF'
    view=_product_market_view(source,result)
    assert view.iloc[0].latest_price==100
    assert view.iloc[0].trade_date=='2026-09-04'
    assert not view.iloc[0].v2_eligible
    assert source.latest_price.isna().all()


@pytest.mark.parametrize('kwargs',[{'isin':'INE000B01011'},{'day':'2026-09-08'},{'price':0},{'price':float('inf')},{'volume':0}])
def test_wrong_identity_future_invalid_or_nontraded_quote_rejected(tmp_path,kwargs):
    quote(tmp_path,**kwargs)
    result,_=official_prior_references(facts(),tmp_path)
    assert result.product_price_reference.isna().all()


def test_official_current_price_wins_and_conflicting_duplicate_is_quarantined(tmp_path):
    first=quote(tmp_path)
    pd.read_csv(first).assign(ClsPric=101).to_csv(first.with_name('bhavcopy_conflict.csv'),index=False)
    result,audit=official_prior_references(facts(),tmp_path)
    assert result.product_price_reference.isna().all()
    assert audit[0]['status']=='OFFICIAL_PRICE_CONFLICT'
    source=facts().assign(latest_price=99)
    result,_=official_prior_references(source,tmp_path)
    assert result.iloc[0].latest_price==99
    assert result.product_price_reference.isna().all()


def test_full_bhavcopy_requires_exact_official_master_link(tmp_path):
    directory=tmp_path/'nse'/'2026-09-04';directory.mkdir(parents=True)
    pd.DataFrame([dict(SYMBOL='EXACT',SERIES='EQ',DATE1='04-Sep-2026',CLOSE_PRICE=100,TTL_TRD_QNTY=5)]).to_csv(directory/'full_bhav.csv',index=False)
    assert official_prior_references(facts(),tmp_path)[0].product_price_reference.isna().all()
    pd.DataFrame([{'SYMBOL':'EXACT','SERIES':'EQ','ISIN NUMBER':'INE000A01011'}]).to_csv(directory/'equity.csv',index=False)
    result,_=official_prior_references(facts(),tmp_path)
    assert result.iloc[0].product_price_reference==100
    pd.DataFrame([{'SYMBOL':'EXACT','SERIES':'BE','ISIN NUMBER':'INE000A01011'}]).to_csv(directory/'equity.csv',index=False)
    assert official_prior_references(facts(),tmp_path)[0].product_price_reference.isna().all()


@pytest.mark.parametrize('day,action,status',[('2026-08-28',None,'OFFICIAL_LAST_TRADE_STALE'),
    ('2026-09-04','2026-09-07','OFFICIAL_PRIOR_TRADE_ACTION_REVIEW_REQUIRED')])
def test_stale_or_post_quote_action_remains_visible_but_not_rankable(tmp_path,day,action,status):
    quote(tmp_path,day=day)
    source=facts().assign(latest_corporate_action_date=action)
    result,_=official_prior_references(source,tmp_path)
    assert result.iloc[0].product_price_reference==100
    assert result.iloc[0].product_price_status==status
    ranked=add_product_classification_and_baseline(result,history_root=tmp_path)
    assert not ranked.iloc[0].product_baseline_eligible


def test_prior_quote_uses_existing_metrics_and_conflict_cannot_use_future_screener(tmp_path):
    quote(tmp_path)
    result,_=official_prior_references(facts(),tmp_path)
    dates=['2021-09-07','2023-09-07','2025-09-05','2026-09-04']
    pd.DataFrame({'date':dates,'adjusted_close':[50,70,90,100]}).to_csv(tmp_path/'EXACT.csv',index=False)
    ranked=add_product_classification_and_baseline(result,history_root=tmp_path).iloc[0]
    assert ranked.product_baseline_eligible
    assert ranked.product_baseline_yoy_growth==100/90-1
    assert ranked.product_baseline_days_since_recorded_high==3
    result['product_price_reference']=150
    result['screener_current_price']=150
    result['screener_current_status']='ACCEPTED_EXACT_ISIN_CURRENT_REFERENCE'
    ranked=add_product_classification_and_baseline(result,history_root=tmp_path).iloc[0]
    assert not ranked.product_baseline_eligible
    assert ranked.product_baseline_reason_code=='CURRENT_PRICE_MISMATCH'
