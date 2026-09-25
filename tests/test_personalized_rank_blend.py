import pandas as pd
from stock_research.personalized_rank_blend import fit_matured_rank_blend,COMPONENTS

def test_rank_blend_cannot_learn_from_target_date_outcomes():
    train=pd.DataFrame({'decision_date':['2018-01-01']*3+['2021-01-01']*3,'endpoint':['2019-01-01']*3+['2022-01-01']*3,'profile_name':['base']*6,'future_shortfall':[.9,.5,0,0,.5,.9]})
    for column in COMPONENTS:train[column]=[1,2,3,1,2,3]
    target=train.iloc[:3].copy();target['decision_date']='2020-01-01'
    result,audit=fit_matured_rank_blend(train,target)
    assert audit[0]['training_rows']==3
    assert audit[0]['latest_training_endpoint']=='2019-01-01'
    assert result.learned_rank_blend_score.is_monotonic_increasing
    changed=train.copy();changed.loc[3:,'future_shortfall']=[500,10,25]
    repeat,_=fit_matured_rank_blend(changed,target)
    pd.testing.assert_series_equal(result.learned_rank_blend_score,repeat.learned_rank_blend_score)
