import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import round2_hysteresis_20261031 as r

def test_safety_block_cannot_keep_old_leader():
    assert r.safe_order(['a','b','c'],dict(a=.9,b=.5,c=.4,d=.3),.1,{'a'})==['b','c','d']

def test_known_event_reset_bypasses_inertia():
    prior=['a','b','c'];scores=dict(a=.5,b=.51,c=.52)
    assert r.safe_order(prior,scores,.1)==prior
    assert r.safe_order(prior,scores,.1,force_reset=True)==['c','b','a']

def test_nonfinite_leader_removed_even_without_explicit_flag():
    assert r.safe_order(['a','b'],dict(a=np.nan,b=.5),.1)==['b']

def test_leader_lag_and_censoring_are_reported():
    history=[('0',['a','b','c'],['a','b','c'],{})]
    for i in range(1,7):history.append((str(i),['d','b','c'],['d','b','c'] if i>=3 else ['a','b','c'],{}))
    a=r.leader_lags(history)[0];assert a['entry_lag_sessions']==2;assert not a['right_censored']
    history=[(d,raw,['a','b','c'],outcome) for d,raw,_,outcome in history]
    assert r.leader_lags(history)[0]['right_censored']

def test_vectorized_features_match_original_dated_snapshot():
    rng=np.random.default_rng(8);dates=pd.bdate_range('2022-01-01','2026-09-30');prices=100*np.exp(np.cumsum(rng.normal(0,.012,len(dates))))
    history=pd.DataFrame(dict(Close=prices,Volume=rng.integers(100,100000,len(prices))),index=dates)
    f=r.stock_features(history,'TEST','SECTOR').set_index('last_price_date')
    for day in ['2025-03-31','2025-12-31','2026-09-30']:
        expected=r.old.old.snapshot(dates.to_numpy(dtype='datetime64[D]'),prices,day)
        actual=f.loc[pd.Timestamp(day)]
        for col in r.RAW:
            np.testing.assert_allclose(actual[col],expected[col],rtol=2e-5,atol=1e-7,err_msg=col)

def test_unresolved_action_masks_price_features():
    dates=pd.bdate_range('2022-01-01','2026-09-30');prices=np.linspace(100,200,len(dates));h=pd.DataFrame(dict(Close=prices,Volume=1000),index=dates)
    f=r.stock_features(h,'TEST','SECTOR',['2025-03-01']).set_index('last_price_date')
    assert f.loc['2025-03-31',r.RAW].isna().all()
    assert f.loc['2026-09-30',r.RAW].notna().all()
