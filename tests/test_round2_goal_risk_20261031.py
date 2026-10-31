import sys
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from round2_goal_risk_20261031 import weighted_survival,scenario_name,schedule,calendar_intervals,top3_metrics

def test_weighted_survival_is_monotone_and_bounded():
    x=np.array([-1.,0.,1.]);w=np.array([1.,2.,1.])
    p=weighted_survival(x,w,np.array([-2.,-1.,-.5,0.,.5,1.,2.]))
    np.testing.assert_allclose(p,[1,1,.75,.75,.25,.25,0])
    assert (np.diff(p)<=0).all()

def test_market_scenario_probability_increases_with_assumed_market_return():
    residual=np.linspace(-.5,.5,101);weights=np.ones(101);goal=.2
    thresholds=np.log1p(goal)-np.log1p(np.array([-.2,0,.2]))
    p=weighted_survival(residual,weights,thresholds)
    assert (np.diff(p)>=0).all()

def test_bucket_boundaries_are_fixed_and_targets_share_schedule():
    assert list(scenario_name(np.array([-.051,-.05,0,.05,.051])))==['bear','flat','flat','flat','bull']
    assert schedule('target10')==schedule('target30')==schedule('base7500')

def test_calendar_interval_keeps_zero_pair_difference_zero():
    import pandas as pd
    frame=pd.DataFrame({'effect':np.zeros(16)},index=[f'{y}-{m:02}-28' for y in range(2020,2024) for m in [3,6,9,12]])
    result=calendar_intervals(frame,replicates=100)
    assert result['effect']['lower']==result['effect']['upper']==0

def test_risk_gate_and_score_ties_use_original_champion_order():
    import pandas as pd
    x=pd.DataFrame(dict(isin=list('abcde'),decision_date='2020-03-31',profile_name='base',sector='s',active_champion=[5,4,3,2,1],candidate=[np.nan,.5,.5,.5,np.nan],goal_hit=[0,1,0,1,1],future_drawdown=[-.1,-.2,-.3,-.4,-.5],future_shortfall=[.1,0,.2,0,0],future_xirr=[0,.3,.1,.4,.5]))
    result=top3_metrics(x,['active_champion','candidate']).set_index('model')
    assert result.loc['candidate','eligible']==3
    assert result.loc['candidate','achievement']==2/3
    assert abs(result.loc['candidate','drawdown']+.3)<1e-12
    assert result.loc['active_champion','achievement']==1/3
