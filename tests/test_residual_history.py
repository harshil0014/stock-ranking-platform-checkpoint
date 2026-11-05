import numpy as np
from stock_research.residual_history import weekly_prices, leave_one_out, residual_features


def test_leave_one_out_excludes_stock_and_preserves_unknown():
    x=np.array([[1.,2.,3.],[np.nan,2.,3.]])
    y=leave_one_out(x,2)
    np.testing.assert_allclose(y[0],[2.5,2.,1.5])
    assert np.isnan(y[1,1]) and y[1,0]==2.5


def test_future_prices_do_not_change_prefix():
    d=np.arange(np.datetime64('2016-01-01'),np.datetime64('2021-01-01'))
    p=np.arange(len(d),dtype=float)+100
    a=weekly_prices((d,p,p),'2020-01-01')
    p[d>np.datetime64('2020-01-01')]*=1000
    np.testing.assert_equal(a,weekly_prices((d,p,p),'2020-01-01'))


def test_missing_history_stays_missing():
    d=np.array(['2020-01-01'],dtype='datetime64[D]');p=np.array([10.])
    x=weekly_prices((d,p,p),'2020-01-01')
    assert np.isnan(x[:-2]).all() and x[-1]==10


def test_residual_signal_finite_for_independent_stock_paths():
    rng=np.random.default_rng(14)
    r=rng.normal(0,.02,(156,60));r[:,0]+=np.r_[np.full(104,-.01),np.full(52,.02)]
    v=residual_features(r,['a']*30+['b']*30)
    assert np.isfinite(v).all() and (v[:,1]<=0).all() and v[0,0]>np.median(v[1:,0])
