import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import champion_age_only_20261017 as r

def sample():
    return pd.DataFrame({'decision_date':['2020-01-01']*6,'profile_name':['base']*6,'sector':['S']*6,
      'evidence_fraction':[1]*6,'observations':[252]*6,'history_days':[500]*6,
      'volume_active_fraction':[1]*6,'last_positive_volume_lag_days':[0]*6,
      'days_since_52w_closing_high':[0,10,20,30,40,50],'days_since_recorded_high':[0,10,20,30,40,50],
      'distance_from_52w_high':[-.05]*6,r.h.base.ANCHOR:[.5]*6})

def test_recency_direction_bounds_and_proximity():
    x=r.signals(sample())
    for name,(_,w) in r.CONFIGS.items():
        assert x[name].is_monotonic_decreasing
        assert (x[name]-.5).abs().le(w/2+1e-12).all()
    z=r.signals(sample().assign(distance_from_52w_high=-.3))
    assert z['near_high_age_0.008'].eq(.5).all()

def test_missing_and_future_independence():
    x=sample();x.loc[0,'days_since_recorded_high']=np.nan
    a=r.signals(x);assert a.loc[0,'dual_age_0.008']==.5
    future=sample().assign(decision_date='2025-01-01',days_since_recorded_high=999)
    b=r.signals(pd.concat([x,future],ignore_index=True))
    np.testing.assert_array_equal(a[list(r.CONFIGS)],b.iloc[:6][list(r.CONFIGS)])
    x.loc[:2,'evidence_fraction']=0
    assert r.signals(x)[list(r.CONFIGS)].eq(.5).all().all()
