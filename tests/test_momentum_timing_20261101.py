import numpy as np
import pandas as pd
import pytest
from stock_research.momentum_timing import entry_state,high_state,net_return,top_quartile


def path():
    ds=np.arange('2020-01-01','2020-02-10',dtype='datetime64[D]')
    return ds,np.full(len(ds),90.),np.full(len(ds),90.)


def test_high_uses_prefix_not_future_peak():
    ds,op,cl=path();cl[0]=100;cl[10]=1000
    r=entry_state((ds,op,cl),'2020-01-03')
    assert r['dip']
    assert r['from_recorded_high']==pytest.approx(-.1)
    assert r['entry']=='2020-01-04'
    assert r['exit']=='2020-01-24'


def test_next_open_not_signal_close():
    ds,op,cl=path();op[3]=180
    assert entry_state((ds,op,cl),'2020-01-03')['gross_ratio']==.5


def test_missing_actual_open_is_not_substituted():
    ds,op,cl=path();op[3]=np.nan
    with pytest.raises(ValueError,match='actual open'):entry_state((ds,op,cl),'2020-01-03')


def test_signal_membership_survives_missing_future_outcome():
    ds,op,cl=path();cl[0]=100
    before=high_state((ds,op,cl),'2020-01-03')
    op[3:]=np.nan;cl[3:]=np.nan
    assert high_state((ds,op,cl),'2020-01-03')==before


def test_quartile_ties_are_deterministic():
    x=pd.DataFrame({'isin':['D','C','B','A','E'],'s':[1]*5})
    assert top_quartile(x,'s')['isin'].tolist()==['A','B']


def test_cost_test_needs_absolute_edge_not_only_relative_difference():
    assert net_return(1.01,100)<0
    assert net_return(1.01,100)-net_return(1.,100)>0
