from pathlib import Path
import sys
import numpy as np
import pandas as pd

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import sector_independent_judge_20261005 as m


def sample():
    rows=[]
    for i in range(6):
        rows.append({'product_sector':'Industrial Products','screener_profit_after_tax_crore':100,
            'screener_pe_ratio':10+i,'screener_roe_3y_avg_pct':10+i,'screener_roce_3y_avg_pct':10+i,
            'screener_sales_growth_3y_pct':5+i,'screener_profit_growth_3y_pct':5+i,
            'screener_debt_to_equity':1-i/10,'screener_pledged_pct':0,
            'screener_operating_cash_flow_crore':100+i*10})
    return pd.DataFrame(rows)


def test_sensitivity_does_not_overwrite_growth_block():
    x=m.judge(sample())
    expected=(x.judge_profitability+x.judge_growth+x.judge_safety+x.judge_cash+x.judge_valuation)/5
    np.testing.assert_allclose(x.judge_primary,expected)
    assert 'judge_variant_growth' in x
    assert x.judge_growth.iloc[-1]==1


def test_judge_does_not_depend_on_competitor_scores():
    f=sample(); a=m.judge(f)
    f['current_score']=np.arange(6); f['sir_score']=-np.arange(6)
    b=m.judge(f)
    np.testing.assert_allclose(a.judge_primary,b.judge_primary)


def test_finance_does_not_penalize_corporate_leverage_or_cashflow():
    f=sample(); f['product_sector']='Banks'; a=m.judge(f)
    f['screener_debt_to_equity']=1000;f['screener_operating_cash_flow_crore']=-10000
    b=m.judge(f)
    np.testing.assert_allclose(a.judge_primary,b.judge_primary)
    assert b.judge_cash.isna().all()


def test_missing_data_not_scored_as_full_evidence():
    f=sample()
    for c in f:
        if c!='product_sector':f[c]=np.nan
    x=m.judge(f)
    assert x.judge_primary.isna().all()
    assert (x.judge_coverage==0).all()


def test_window_adapter_does_not_search_past_requested_span():
    days=np.array([100,103,105]); prices=np.array([10.,20.,30.])
    assert m.window_price(days,prices,101,200)==(None,None)
    assert m.window_price(days,prices,102,200)==(103,20.)
    assert m.window_price(days,prices,102,102)==(None,None)


def test_every_sector_retained_when_no_comparable_stocks():
    x=pd.DataFrame({'product_sector':['A','B'],'current_score':[1,np.nan],
                    'sir_score':[1,1],'judge_primary':[.5,.5],'isin':['1','2']})
    out=m.compare(x)
    assert len(out)==2
    assert out.verdict.eq('INSUFFICIENT_COMPARABLE_STOCKS').all()
