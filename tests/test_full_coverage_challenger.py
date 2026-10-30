"""Coverage and leakage boundaries for full-universe research challenger."""
from pathlib import Path
import sys
import numpy as np
import pandas as pd
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
import full_coverage_challenger_20261008 as m


def data():
    rows=[]
    for i in range(12):
        rows.append({'isin':str(i),'decision_date':'2023-01-01','sector':'A' if i<6 else 'B',
                     **{c:float(i+1) for c in m.RAW}})
    return pd.DataFrame(rows)


def test_all_missing_produces_neutral_score_not_fake_order():
    x=data()
    x[m.RAW]=np.nan
    x=m.features(x)
    for name in ['high_strength','balanced_strength','risk_strength']:
        assert x[name].eq(.5).all()
    assert x.evidence_fraction.eq(0).all()


def test_relative_features_do_not_depend_on_other_sectors():
    x=data();a=m.features(x)
    x.loc[x.sector.eq('B'),m.RAW]=100000
    b=m.features(x)
    np.testing.assert_allclose(a[a.sector.eq('A')].high_strength,b[b.sector.eq('A')].high_strength)


def test_trade_eligibility_never_removes_rank_score():
    x=data();x['purchase_eligibility_reason']='SME_LOT_SIZE_UNVERIFIED'
    assert m.features(x).high_strength.notna().all()


def test_predictors_exclude_labels_and_models():
    assert not any(c.startswith('future_') or c in ['endpoint','sector_incumbent','champion_score','judge_primary'] for c in m.predictors())


def test_common_comparison_keeps_same_stocks_and_expanded_adds():
    x=data();x['sector']='A';x['period']='development'
    x['sector_incumbent']=[1,.9,.8,.7,.6,.5]+[np.nan]*6
    x['test']=np.arange(12)
    x['future_xirr']=np.arange(12)/10
    x['future_drawdown']=-.2;x['future_shortfall']=.1
    q=m.evaluate(x,['test'])
    assert set(q.scope)=={'common','expanded'}
    assert q[q.scope.eq('common')].cohort_size.eq(6).all()
    assert q[q.scope.eq('expanded')].cohort_size.eq(12).all()
    assert q[(q.model.eq('sector_incumbent'))].xirr.nunique()==1


def test_deterministic_ties_independent_of_row_order():
    x=data();x['sector']='A';x['period']='development';x['sector_incumbent']=.5;x['test']=.5
    x['future_xirr']=np.arange(12)/10;x['future_drawdown']=-.2;x['future_shortfall']=.1
    pd.testing.assert_frame_equal(m.evaluate(x,['test']),m.evaluate(x.sample(frac=1,random_state=42),['test']))


def test_risk_blend_uses_declared_convex_weights():
    x=m.features(data());x['sector_incumbent']=np.arange(12);x['learned']=.7
    actual=m.selected_score(x,'learned_blend0.1_risk0.05')
    base=x.sector_incumbent.groupby([x.decision_date,x.sector]).rank(pct=True)
    np.testing.assert_allclose(actual,.85*base+.1*.7+.05*x.risk_block)


def test_dual_continuity_is_soft_and_finite_for_zero_trading():
    x=m.features(data());x['sector_incumbent']=np.arange(12)
    x['rank_xendcg_balanced_15']=.6;x['rank_xendcg_return_15']=.7
    x['volume_active_fraction']=0.;x['observations_1y']=0.
    result=m.selected_score(x,'dual_b0.35_r0.15_c0.4')
    base=x.sector_incumbent.groupby([x.decision_date,x.sector]).rank(pct=True)
    np.testing.assert_allclose(result,.5*base+.35*.6+.15*.7-.4)
    assert result.notna().all()
