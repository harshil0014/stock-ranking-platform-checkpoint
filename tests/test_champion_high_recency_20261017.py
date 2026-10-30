import sys
from pathlib import Path
import pandas as pd
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research'/'runners'))
import champion_high_recency_20261017 as r

def sample():
    x=pd.DataFrame({'isin':list('abcdef'),'decision_date':['2020-01-01']*6,'profile_name':['base']*6,'sector':['S']*6})
    for col,val in {'evidence_fraction':1,'observations':252,'history_days':500,'volume_active_fraction':1,'last_positive_volume_lag_days':0,'distance_from_52w_high':-.1,'distance_from_recorded_high':-.1,'momentum12_1':.1,r.base.ANCHOR:.5}.items():x[col]=val
    x[r.AGE]=[0,10,20,30,40,50];x['days_since_52w_closing_high']=[0,10,20,30,40,50]
    return x

def test_recency_direction_and_bounded_adjustment():
    z=r.signals(sample())
    for name,(_,w) in r.CONFIGS.items():
        assert z[name].is_monotonic_decreasing
        assert (z[name]-z[r.base.ANCHOR]).abs().le(w/2+1e-12).all()

def test_missing_age_and_untradeable_are_not_recent_highs():
    x=sample();x.loc[5,r.AGE]=np.nan;z=r.signals(x)
    assert z.loc[5,'recorded_w0.05']==.5
    x.loc[0,'volume_active_fraction']=0;x.loc[1,'evidence_fraction']=0
    z=r.signals(x)
    assert z[list(r.CONFIGS)].eq(.5).all().all() # fewer than five eligible peers

def test_future_prices_do_not_change_previous_date_ranks():
    x=sample();future=x.assign(decision_date='2021-01-01');future[r.AGE]=1000
    z=r.signals(pd.concat([x,future],ignore_index=True))
    np.testing.assert_array_equal(z.iloc[:6][list(r.CONFIGS)],r.signals(x)[list(r.CONFIGS)])
