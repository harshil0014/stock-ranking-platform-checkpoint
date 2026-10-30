import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import champion_double_emphasis_20261017 as r

def test_double_bounds_and_disagreement():
    x=pd.DataFrame({r.h.base.ANCHOR:[.5]*5,'high_delta':[.005,-.005,.004,0,.001],'sip_delta':[.005,-.005,-.004,0,.001]})
    a=r.candidates(x)
    np.testing.assert_allclose(a.double_both,[.51,.49,.5,.5,.502])
    for name in r.CONFIGS:
        assert (a[name]-.5).abs().le(.01+1e-12).all()
        assert a.loc[3,name]==.5
    assert a.loc[2,'agree_only']==.5
    assert a.loc[4,'strong_both']==.5
    assert .5<a.loc[4,'agree_soft']<a.loc[4,'double_both']

def test_no_outcome_or_company_dependence():
    x=pd.DataFrame({r.h.base.ANCHOR:[.7],'high_delta':[.003],'sip_delta':[.004]})
    for name in r.CONFIGS:
        np.testing.assert_array_equal(r.candidates(x)[name],r.candidates(x.assign(ticker='NYKAA',future_xirr=999))[name])
