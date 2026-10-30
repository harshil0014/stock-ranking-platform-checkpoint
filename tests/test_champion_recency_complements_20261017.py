from test_champion_high_recency_20261017 import sample
import champion_recency_complements_20261017 as r
import numpy as np
import pandas as pd

def fixture():
    x=sample()
    for c in r.FIELDS:
        if c not in x:x[c]=np.linspace(.1,.6,len(x))
    return x

def test_fixed_recency_and_complement_bounds():
    x=fixture();z=r.signals(x)
    for name,(kind,w) in r.CONFIGS.items():
        np.testing.assert_allclose(z[name]-w*z['complement_'+kind],z['dual_w0.01'],atol=1e-15)
        assert (z[name]-z['dual_w0.01']).abs().le(w/2+1e-12).all()
    x[r.h.AGE]=x[r.h.AGE][::-1].to_numpy()
    x.days_since_52w_closing_high=x.days_since_52w_closing_high[::-1].to_numpy()
    other=r.signals(x)
    for name in r.CONFIGS:
        np.testing.assert_allclose(other[name]-z[name],other['dual_w0.01']-z['dual_w0.01'],atol=1e-15)

def test_missing_complement_abstains_and_future_is_independent():
    x=fixture();x.loc[0,'downside252']=np.nan
    z=r.signals(x)
    assert z.loc[0,'risk_0.003']==z.loc[0,'dual_w0.01']
    future=fixture().assign(decision_date='2025-01-01',volatility252=100)
    both=r.signals(pd.concat([x,future],ignore_index=True))
    np.testing.assert_array_equal(z[list(r.CONFIGS)],both.iloc[:6][list(r.CONFIGS)])
