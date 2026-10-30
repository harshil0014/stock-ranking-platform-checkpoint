import sys
from pathlib import Path
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
from sector_conservative_router_20261010 import choose,ANCHOR,EXPERTS

def history(n=8,risk_regression=False):
    rows=[]
    for date in range(n):
        for model in EXPERTS:
            better=model==EXPERTS[2]
            rows.append(dict(date=str(date),model=model,xirr=.1+.1*better,drawdown=-.2+(-.1 if risk_regression else .05)*better,achievement=.5+.1*better,shortfall=.1-.05*better,ndcg=.6+.1*better,rank_ic=.1+.05*better))
    return pd.DataFrame(rows)

def test_retains_anchor_without_sufficient_completed_dates():
    assert choose(pd.DataFrame(),dict(minimum=8,guard=True))==ANCHOR
    assert choose(history(7),dict(minimum=8,guard=True))==ANCHOR

def test_multimetric_guard_rejects_risk_regression():
    assert choose(history(),dict(minimum=8,guard=True))==EXPERTS[2]
    assert choose(history(risk_regression=True),dict(minimum=8,guard=True))==ANCHOR
