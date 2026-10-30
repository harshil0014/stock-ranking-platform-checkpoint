import numpy as np
import pandas as pd
from stock_ranker.sip_profit_signal import adjustments

def sample():
    return pd.DataFrame(dict(decision_date=['2020-01-01']*6,profile_name=['base']*6,sector=['S']*6,
       evidence_fraction=[1]*6,sip_action_blocked=[False]*6,volume_active_fraction=[1]*6,
       last_positive_volume_lag_days=[0]*6,professor_whole_share_score=[-.5,0,.1,.2,.5,1],
       sip_invested_fraction=[.8]*6,downside252=[.2]*6))

def test_profit_direction_bounds_and_reliability():
    s=adjustments(sample())
    assert s['plain'].is_monotonic_increasing
    for v in s.values():assert v.abs().le(.5).all()
    np.testing.assert_allclose(s['invested'],s['plain']*.8)

def test_blocked_missing_and_small_groups_abstain():
    x=sample();x.loc[0,'sip_action_blocked']=True
    assert adjustments(x)['plain'].iloc[0]==0
    x.loc[1,'professor_whole_share_score']=np.nan
    assert adjustments(x)['plain'].eq(0).all()

def test_future_outcomes_cannot_change_signal():
    x=sample();future=x.assign(decision_date='2025-01-01',professor_whole_share_score=999)
    for k,v in adjustments(pd.concat([x,future],ignore_index=True)).items():
        np.testing.assert_array_equal(v.iloc[:6],adjustments(x)[k])
    np.testing.assert_array_equal(adjustments(x.assign(future_xirr=-999))['plain'],adjustments(x)['plain'])
