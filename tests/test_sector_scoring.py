import numpy as np
import pandas as pd
from stock_ranker.sector_scoring import components,score

CHOICE=dict(high=.5,downside=.2,momentum=.05,goal=0,relative_high=.5)

def fixture():
    return pd.DataFrame({'isin':list('abcdefghij'),'decision_date':['2026-10-03']*10,
        'profile_name':['test']*10,'sector':['Banks']*5+['Software']*5,
        'current_score':np.linspace(.1,.9,10),'repair_score':np.linspace(.1,.9,10),
        'closing_high_component':np.linspace(.1,.9,10),'momentum_12_1':np.linspace(.1,.9,10),
        'downside_volatility_1y':np.linspace(.1,.9,10),'enhanced_goal_score':np.linspace(.1,.9,10)})

def test_other_sectors_cannot_change_peer_score():
    x=fixture();before=score(components(x),CHOICE)
    x.loc[x.sector.eq('Software'),['repair_score','momentum_12_1','downside_volatility_1y']]=10000
    after=score(components(x),CHOICE)
    np.testing.assert_allclose(before.iloc[:5],after.iloc[:5])

def test_small_unknown_and_ineligible_fallbacks():
    x=fixture();x.loc[0,'current_score']=np.nan;x.loc[5:,'sector']='Unclassified'
    actual=score(components(x),CHOICE)
    np.testing.assert_allclose(actual,x.current_score,equal_nan=True)

def test_higher_closing_high_strength_cannot_reduce_own_score():
    x=fixture();before=score(components(x),CHOICE)
    x.loc[2,'closing_high_component']+=.1
    after=score(components(x),CHOICE)
    assert after.loc[2]>=before.loc[2]

def test_independent_weight_arithmetic():
    x=fixture();actual=score(components(x),CHOICE)
    for sector,g in x.groupby('sector'):
        expected=(.25*g.repair_score.rank(pct=True)+.25*g.closing_high_component
            +.25*g.closing_high_component.rank(pct=True)+.2*g.downside_volatility_1y.rank(pct=True,ascending=False)
            +.05*g.momentum_12_1.rank(pct=True))
        np.testing.assert_allclose(actual.loc[g.index],expected)
