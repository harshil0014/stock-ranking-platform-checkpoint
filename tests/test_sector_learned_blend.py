"""Protect temporal meta-training and replacement weight semantics."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from sector_learned_blend_20261010 import mature,fit_nnls,infer_nnls

def test_mature_excludes_boundary_and_future_outcomes():
    rows=[]
    for day,end in [('2020-03-31','2021-03-31'),('2021-01-01','2022-01-01'),('2021-03-31','2022-03-31')]:
        for i in range(6):rows.append(dict(isin=str(i),decision_date=day,endpoint=end,profile_name='p',sector='s',open_model=i/6,profile_defensive_15=i/6,rank_xendcg_balanced=i/6,future_xirr=i/6,future_drawdown=-i/6,future_shortfall=i/6))
    x=pd.DataFrame(rows);t=mature(x,'2022-01-01')
    assert len(t)==6 and t.endpoint.max()=='2021-03-31'
    x.loc[x.endpoint.ge('2022-01-01'),'future_xirr']=1e10
    pd.testing.assert_frame_equal(t,mature(x,'2022-01-01'))
    assert mature(x,'2021-01-01').empty

def test_nnls_recovers_known_blend_and_preserves_row_order():
    rng=np.random.default_rng(3);x=pd.DataFrame(rng.random((100,2)),columns=['guarded_previous','rank_xendcg_balanced'])
    x['return_target']=.2*x.guarded_previous+.8*x.rank_xendcg_balanced;x['weight']=1.
    m=fit_nnls(x,dict(scope='outer',target='return'))
    np.testing.assert_allclose(m['weights'],[.2,.8],atol=1e-12)
    np.testing.assert_allclose(infer_nnls(x.iloc[::-1],m),x.return_target.iloc[::-1],atol=1e-12)
