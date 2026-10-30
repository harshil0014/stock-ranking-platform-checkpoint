"""Temporal and convex-stack safeguards for independent specialist research."""
import sys
from pathlib import Path
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import sector_specialist_ensemble_20261011 as s
import sector_specialist_combinations_20261011 as c

def test_training_rejects_unmatured_labels_and_unusable_inputs():
    frame=pd.DataFrame(dict(isin=[str(i) for i in range(18)],decision_date=['2018-01-01']*6+['2019-01-01']*6+['2017-01-01']*6,profile_name=['p']*18,sector=['A']*12+['Unclassified']*6,endpoint=['2019-01-01']*6+['2020-01-01']*6+['2018-01-01']*6,evidence_fraction=[1]*5+[0]+[1]*12,future_xirr=np.arange(18),future_drawdown=np.arange(18),future_shortfall=np.arange(18)))
    t=s.training(frame,'2020-01-01')
    assert len(t)==5 and t.endpoint.max()<'2020-01-01'
    assert t.evidence_fraction.gt(0).all()
    assert t.return_target.is_monotonic_increasing and t.goal_target.is_monotonic_decreasing
    np.testing.assert_allclose(t.weight,1)

def test_stack_is_convex_and_ignores_future_unknown_values():
    n=30;base=np.linspace(.1,.9,n);expert=base[::-1]
    t=pd.DataFrame({name:expert for name in c.PURE+c.LEGACY})
    t['champion_percentile']=base;t['return_target']=expert;t['weight']=1
    coef=c.stack_fit(t,'return')
    assert np.all(coef>=0) and coef.sum()<=1+1e-12
    pred=c.stack_predict(t,coef)
    assert np.all(pred>=np.minimum(base,expert)-1e-12)
    assert np.all(pred<=np.maximum(base,expert)+1e-12)
    np.testing.assert_allclose(pred,expert,atol=1e-10)

def test_no_champion_or_identity_features_in_independent_learners():
    for features in s.FEATURES.values():
        assert not set(features)&{'isin','ticker','company','future_xirr','future_drawdown','future_shortfall','champion_percentile','current_champion'}
