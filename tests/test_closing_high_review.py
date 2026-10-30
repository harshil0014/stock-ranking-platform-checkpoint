import numpy as np
import pandas as pd

from stock_ranker.closing_high_review import recovery_freshness, high_component, review_stock


def test_old_high_crossing_is_continuous_and_recovery_is_monotonic():
    depth=pd.Series(np.linspace(-.5,0,10001))
    age=pd.Series(2000.,index=depth.index)
    values=high_component(age,depth,pd.Series(1.,index=depth.index))
    assert np.diff(values).min()>=0
    assert values.iloc[-1]==1
    assert 1-values.iloc[-2]<.0001
    # Age reset at the same high cannot create the old 12-point discontinuity.
    before=recovery_freshness(pd.Series([2000.]),pd.Series([-1e-8])).iloc[0]
    after=recovery_freshness(pd.Series([0.]),pd.Series([0.])).iloc[0]
    assert after-before<1e-12
    assert recovery_freshness(pd.Series([2000.]),pd.Series([-.5])).iloc[0]<.17


def test_age_still_matters_and_missing_high_is_not_invented():
    age=pd.Series([0.,365.,2000.,np.nan])
    result=recovery_freshness(age,pd.Series([-.2]*4))
    assert result.iloc[0]>result.iloc[1]>result.iloc[2]
    assert pd.isna(result.iloc[3])


def test_sme_gate_distinguishes_exchange_series_and_mainboard_migrations():
    for exchange,series in [('BSE','M'),('BSE','MT'),('NSE','SM'),('NSE','ST')]:
        assert review_stock({'primary_exchange':exchange,'series':series},{})['sme_lot_unverified']
    result=review_stock({'primary_exchange':'NSE','series':'EQ'}, {}, {'review_flag':'mainboard_historical_lot_review'})
    assert not result['sme_lot_unverified']
    assert any('Former SME' in flag for flag in result['review_flags'])


def test_financial_flags_are_sector_appropriate_and_missing_is_unknown():
    fact={'product_sector':'Banks','screener_operating_cash_flow_crore':-10,'screener_debt_to_equity':5}
    assert not review_stock(fact,{})['review_flags']
    fact['product_sector']='Auto Components'
    assert len(review_stock(fact,{})['review_flags'])==2
    assert not review_stock({}, {})['review_flags']
