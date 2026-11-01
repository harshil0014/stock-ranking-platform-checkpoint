import numpy as np
import pytest
from stock_research.sir_ladder import funded_stock,high_features,ALLOTMENTS


def path(value=100.):
    ds=np.arange('2019-01-01','2022-01-02',dtype='datetime64[D]');x=np.full(len(ds),value)
    return ds,x.copy(),x.copy(),np.ones(len(ds))


def test_allotments_are_workbook_money_weights():
    assert ALLOTMENTS.tolist()==[.1,.05,.2,.1,.3,.15,.1]
    assert ALLOTMENTS.sum()==pytest.approx(1.)


def test_never_triggered_keeps_whole_budget_not_missing_return():
    r=funded_stock(path(),'2020-01-01','2021-01-01','ladder')
    assert r['budget_xirr']==pytest.approx(0)
    assert r['no_fill'] and r['deployment']==0


def test_cash_scenario_is_budget_level_and_shared_by_comparator():
    r=funded_stock(path(),'2020-01-01','2021-01-01','ladder',cash_rate=.04)
    assert r['budget_xirr']==pytest.approx(.04)


def test_below_all_levels_at_entry_queues_next_open_once():
    ds,op,cl,v=path();cl[ds<np.datetime64('2020-01-01')]=200
    r=funded_stock((ds,op,cl,v),'2020-01-01','2021-01-01','ladder')
    assert r['first_fill']=='2020-01-02'
    assert r['filled_tranches']==7
    assert r['deployment']==pytest.approx(1.)
    assert r['terminal']==pytest.approx(90000*.99/1.01)


def test_later_high_never_resets_anchor():
    ds,op,cl,v=path();cl[(ds>np.datetime64('2020-01-01'))]=200
    r=funded_stock((ds,op,cl,v),'2020-01-01','2021-01-01','ladder')
    assert r['anchor']==100 and r['no_fill']


def test_sip_has_same_upfront_budget_and_twelve_installments():
    r=funded_stock(path(),'2020-01-01','2021-01-01','sip')
    assert r['filled_tranches']==12 and r['deployment']==pytest.approx(1.)
    assert r['terminal']==pytest.approx(90000*.99/1.01)


def test_ath_count_does_not_use_future_record_or_equal_highs():
    ds=np.array(['2019-01-01','2020-01-01','2020-06-01','2020-12-31','2021-01-01'],dtype='datetime64[D]')
    assert high_features(ds,np.array([10,10,11,11,1000]),'2020-12-31')['ath_count']==1


def test_unknown_execution_is_not_reported_as_cash_success():
    ds,op,cl,v=path();v[ds==np.datetime64('2020-01-02')]=0
    with pytest.raises(ValueError,match='execution'):funded_stock((ds,op,cl,v),'2020-01-01','2021-01-01','sip')
