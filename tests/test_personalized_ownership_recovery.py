import pandas as pd
from stock_ranker.personalized import InvestorProfile
from stock_research.personalized_official_actions import OfficialActionHistoryBook
from stock_research import personalized_executable_tournament as tournament
from test_personalized_official_actions import normalized_action, official_book


def test_walk_forward_excludes_not_yet_mature_training_labels(monkeypatch):
    train = pd.DataFrame({'endpoint':['2022-12-31','2023-06-30','2023-12-31']})
    target = pd.DataFrame({'decision_date':['2023-06-30','2023-12-31']})
    seen=[]
    def fit(training, target, protocol):
        seen.append(training.endpoint.tolist())
        return target.copy(), []
    monkeypatch.setattr(tournament,'fit_fixed_models',fit)
    _, audit=tournament.fit_matured_models(train,target,{})
    assert seen == [['2022-12-31'],['2022-12-31','2023-06-30']]
    assert all(pd.Timestamp(r['latest_training_endpoint']) < pd.Timestamp(r['decision_date']) for r in audit)


def test_intermediate_bonus_fraction_cannot_be_hidden_by_later_split(tmp_path):
    actions=pd.concat([normalized_action(numerator=3,denominator=2), normalized_action(event_date='2020-02-15',event_type='SPLIT')])
    book=official_book(tmp_path,actions,pre=100,post=100)
    row=book.simulate(InvestorProfile(amount=100,interval_days=31,lookback_months=2,whole_shares=True),'2020-03-01').iloc[0]
    assert row.status == 'UNRESOLVED_FRACTIONAL_ENTITLEMENT'
    assert row.reason == 'FRACTIONAL_BONUS_ENTITLEMENT:2020-02-01'


def test_resulting_security_is_separate_wealth_not_parent_shares(tmp_path):
    actions=normalized_action(event_type='DEMERGER',status='RESULTING_EQUITY')
    book=official_book(tmp_path,actions,pre=100,post=70)
    # Child starts trading after ex-date; no backfilled prelisting value.
    import numpy as np
    dates=np.array(['2020-02-10','2020-03-01'],dtype='datetime64[D]')
    prices=np.array([30.,40.]);book.arrays['CHILD']=(dates,prices,prices,prices,np.ones(2))
    book.resulting_terms=pd.DataFrame([dict(parent_isin='CURRENT',event_date='2020-02-01',child_isin='CHILD',child_ticker='CHILD',numerator=1,denominator=1)])
    row=book.simulate(InvestorProfile(amount=100,interval_days=31,lookback_months=2,whole_shares=True),'2020-03-01').set_index('isin').loc['CURRENT']
    assert row.status == 'AVAILABLE'
    assert row.shares_bought == 2
    assert row.resulting_security_value == 40
    assert row.total_wealth == 210


def test_resulting_fraction_blocks_instead_of_valuing_fictional_cash(tmp_path):
    book=official_book(tmp_path,normalized_action(event_type='DEMERGER',status='RESULTING_EQUITY'),pre=100,post=70)
    book.resulting_terms=pd.DataFrame([dict(parent_isin='CURRENT',event_date='2020-02-01',child_isin='CHILD',child_ticker='CHILD',numerator=1,denominator=2)])
    row=book.simulate(InvestorProfile(amount=100,interval_days=31,lookback_months=2,whole_shares=True),'2020-03-01').iloc[0]
    assert row.status == 'UNRESOLVED_CORPORATE_ACTION'
    assert row.reason == 'RESULTING_FRACTION_SETTLEMENT_UNAVAILABLE:CHILD'

def test_verified_official_nominal_prices_are_not_unadjusted_twice(tmp_path):
    actions=normalized_action()
    official_book(tmp_path,actions,provider_ratio=2)
    path=tmp_path/'history/AAA.csv';frame=pd.read_csv(path)
    frame.loc[frame.date.lt('2020-02-01'),'raw_close']=100.0
    frame.to_csv(path,index=False)
    book=OfficialActionHistoryBook(pd.DataFrame([{'isin':'CURRENT','ticker':'AAA'}]),tmp_path/'history',tmp_path/'splits',actions,as_of_date='2020-03-01',nominal_tickers={'AAA'})
    row=book.simulate(InvestorProfile(amount=100,interval_days=31,lookback_months=2,whole_shares=True),'2020-03-01').iloc[0]
    assert row.total_wealth == 200
    assert row.shares_bought == 4


def test_rights_replay_does_not_round_large_fractional_holdings():
    import numpy as np
    import pytest
    from types import SimpleNamespace
    from research.runners.rights_policy_sensitivity import replay
    dates=np.array(['2020-01-01','2020-02-01','2020-03-01'],dtype='datetime64[D]')
    prices=np.ones(3)
    actions=pd.DataFrame([{'event_date':pd.Timestamp('2020-02-01'),'mechanics_status':'AUTO_MULTIPLIER','event_type':'BONUS','total_share_multiplier':1.0000005}])
    book=SimpleNamespace(arrays={'TEST':(dates,prices,prices,prices,prices)},actions={'TEST':actions})
    profile=InvestorProfile(amount=1000000,interval_days=31,lookback_months=2,whole_shares=True)
    with pytest.raises(ValueError,match='fractional automatic action'):
        replay(book,'TEST',profile,'2020-03-01',exercise=True)


def test_provider_adjustment_stops_at_original_cache_basis_date(tmp_path):
    actions=normalized_action()
    official_book(tmp_path,actions,provider_ratio=2)
    path=tmp_path/'history/AAA.csv';frame=pd.read_csv(path)
    frame.loc[frame.date.lt('2020-02-01'),'raw_close']=100.0
    frame.to_csv(path,index=False)
    book=OfficialActionHistoryBook(pd.DataFrame([{'isin':'CURRENT','ticker':'AAA'}]),tmp_path/'history',tmp_path/'splits',actions,as_of_date='2020-03-01',adjustment_dates={'AAA':'2020-01-31'})
    row=book.simulate(InvestorProfile(amount=100,interval_days=31,lookback_months=2,whole_shares=True),'2020-03-01').iloc[0]
    assert row.total_wealth == 200
    assert row.shares_bought == 4
