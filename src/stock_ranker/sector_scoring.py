"""Sector-relative features shared by research and the serving adapter."""
import numpy as np
import pandas as pd


def components(frame):
    """Normalize only eligible peers; small/unknown groups retain incumbent scores."""
    x=frame.copy()
    groups=['decision_date','profile_name','sector']
    valid=x.current_score.notna()
    x['sector_peer_count']=valid.groupby([x[c] for c in groups]).transform('sum')
    for output,source,ascending in [('sector_base','repair_score',True),
                                   ('sector_high','closing_high_component',True),
                                   ('sector_momentum','momentum_12_1',True),
                                   ('sector_downside','downside_volatility_1y',False),
                                   ('sector_goal','enhanced_goal_score',True)]:
        x[output]=x[source].where(valid).groupby([x[c] for c in groups]).rank(pct=True,ascending=ascending).fillna(.5)
    return x


def score(x,choice):
    h,d,m,g,r=[choice[k] for k in ['high','downside','momentum','goal','relative_high']]
    high=(1-r)*x.closing_high_component+r*x.sector_high
    value=(1-h-d-m-g)*x.sector_base+h*high+d*x.sector_downside+m*x.sector_momentum+g*x.sector_goal
    fallback=x.sector_peer_count.lt(5)|x.sector.isna()|x.sector.eq('Unclassified')
    return value.where(~fallback,x.current_score).where(x.current_score.notna())
