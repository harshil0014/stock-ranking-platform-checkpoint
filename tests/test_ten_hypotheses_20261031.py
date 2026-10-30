"""Causal-order and statistical controls for the research pilot."""
import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from ten_hypotheses_20261031 import block_floor,hysteresis_order

def test_identical_policies_have_zero_selection_noise():
    result=block_floor(np.zeros((16,35)),[f'{y}-{m:02}-28' for y in range(2020,2024) for m in [3,6,9,12]],365,200)
    assert result['familywise_95']==0

def test_maximum_over_correlated_trials_has_positive_noise_floor():
    rng=np.random.default_rng(1);z=rng.normal(size=(16,35))
    r=block_floor(z,[f'{y}-{m:02}-28' for y in range(2020,2024) for m in [3,6,9,12]],365,500)
    assert r['familywise_95']>r['median_lucky_win']>0

def test_hysteresis_preserves_small_score_changes_and_accepts_large_ones():
    previous=['a','b','c'];scores={'a':.5,'b':.501,'c':.7}
    assert hysteresis_order(previous,scores,.01)==['c','a','b']
    assert hysteresis_order(previous,scores,0)==['c','b','a']

def test_equal_scores_preserve_previous_order():
    assert hysteresis_order(['c','a','b'],dict(a=.5,b=.5,c=.5),0)==['c','a','b']

def test_block_covering_entire_history_is_not_false_zero_uncertainty():
    result=block_floor(np.ones((4,35)),['2024-03-31','2024-06-30','2024-09-30','2024-12-31'],730,200)
    assert np.isnan(result['familywise_95'])
    assert result['replicates']==0

def test_batched_metrics_match_scipy_rank_correlation_with_ties():
    import pandas as pd
    from scipy.stats import spearmanr
    from ten_hypotheses_20261031 import metrics
    y=np.array([.1,.3,.3,-.2,.5]);scores=np.array([1,2,2,4,5])
    frame=pd.DataFrame(dict(isin=list('abcde'),decision_date='2020-03-31',profile_name='base',sector='s',future_xirr=y,future_drawdown=-.2,future_shortfall=[.1,0,0,.4,0],goal_hit=[0,1,1,0,1],score=scores))
    result=metrics(frame,['score']).iloc[0]
    assert abs(result.rank_ic-spearmanr(y,scores).statistic)<1e-12
    assert result.achievement==2/3

def test_negative_calibration_slope_becomes_valid_constant_probability():
    from sklearn.linear_model import LogisticRegression
    from ten_hypotheses_20261031 import constrain_calibrator
    model=LogisticRegression(C=1000).fit(np.array([-3,-2,-1,1,2,3]).reshape(-1,1),[1,1,1,0,0,0])
    assert model.coef_[0,0]<0
    model=constrain_calibrator(model,np.array([1,1,1,0,0,0]),np.ones(6))
    np.testing.assert_allclose(model.predict_proba(np.array([-5,5]).reshape(-1,1))[:,1],[.5,.5])
