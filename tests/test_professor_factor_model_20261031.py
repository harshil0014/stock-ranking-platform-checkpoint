import numpy as np
import pandas as pd
import pytest
from stock_research.professor_factor_model import price_features, normalize_factors, constrained_weights, score, FACTOR_COLUMNS


def frame():
    n=8
    x=pd.DataFrame(dict(isin=[str(i) for i in range(n)],sector=['s']*n,decision_date=['2020-12-31']*n,
                        evidence_fraction=[1.]*n,volume_active_fraction=[1.]*n,last_positive_volume_lag_days=[0]*n,
                        sip_action_blocked=[False]*n,sip_invested_fraction=[1.]*n,champion_score=np.linspace(1,0,n)))
    for c in ['cagr3','cagr5','high_recency','sip_profit']+[f'annual{i}' for i in range(1,6)]:x[c]=np.arange(n)/10
    return x


def test_prefix_prices_and_annual_boundaries():
    dates=pd.bdate_range('2010-01-01','2022-01-01').to_numpy(dtype='datetime64[D]')
    prices=np.exp(np.arange(len(dates))/10000)
    result=price_features(dates,prices,'2020-06-30')
    changed=prices.copy();changed[dates>np.datetime64('2020-06-30')]=1e9
    assert result==price_features(dates,changed,'2020-06-30')
    assert np.isfinite(list(result.values())).all()
    # Mid-year latest completed annual return ends2019, notJune2020.
    i=np.searchsorted(dates,np.datetime64('2019-12-31'),side='right')-1
    j=np.searchsorted(dates,np.datetime64('2018-12-31'),side='right')-1
    assert result['annual1']==pytest.approx(prices[i]/prices[j]-1)


def test_missing_price_boundary_not_shortened_to_available_history():
    dates=pd.bdate_range('2019-01-01','2020-12-31').to_numpy(dtype='datetime64[D]')
    r=price_features(dates,np.ones(len(dates)),'2020-12-31')
    assert np.isnan(r['cagr3']) and np.isnan(r['cagr5']) and np.isnan(r['annual5'])


def test_weights_enforce_majority_and_no_factor_can_disappear():
    w=constrained_weights([100,0,-1,0,0])
    assert w.sum()==pytest.approx(1) and (w>=.1).all()
    x=normalize_factors(frame());s=score(x,w,.9)
    core=x[['q_'+c for c in FACTOR_COLUMNS]].to_numpy()@w
    assert np.allclose(s,.9*core+.1*x.champion_percentile)
    assert np.allclose(.9*w.sum(),.9)
    with pytest.raises(ValueError):score(x,w,.02)


def test_missing_factor_is_unavailable_not_silently_reweighted():
    x=frame();x.loc[0,'annual5']=np.nan
    z=normalize_factors(x)
    assert not z.loc[0,'factor_eligible'] and np.isnan(score(z,np.ones(5)/5,.9).iloc[0])
    x['future_xirr']=np.arange(len(x))[::-1]
    assert normalize_factors(x).q_cagr3.equals(z.q_cagr3)


def test_unresolved_action_and_affordability_fail_closed():
    x=frame();x.loc[0,'sip_action_blocked']=True;x.loc[1,'sip_invested_fraction']=.1
    z=normalize_factors(x)
    assert not z.loc[:1,'factor_eligible'].any()


def test_unknown_selected_outcome_blocks_all_top3_metrics_without_reselection(tmp_path,monkeypatch):
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
    import professor_majority_20261031 as runner
    monkeypatch.setattr(runner,'OUT',tmp_path)
    x=normalize_factors(frame())
    for name in runner.NAMES:x[name]=np.arange(len(x),dtype=float)
    x['future_xirr']=np.arange(len(x))/10
    x['future_drawdown']=-.2;x['future_shortfall']=.1
    # Stock7 remains a top-three selection despite an unknown future outcome.
    x.loc[7,'future_xirr']=np.nan
    result=runner.evaluate_period(x,'development')
    assert result.attainment3.isna().all() and result.drawdown3.isna().all()
    assert result.rank_ic.notna().all()


def test_early_mature_training_rows_survive_later_champion_archive():
    import sys
    from pathlib import Path
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'research/runners'))
    import professor_majority_20261031 as runner
    scores=pd.DataFrame(dict(isin=['a'],decision_date=['2020-12-31'],profile_name=['base7500'],champion_score=[.5]))
    history=pd.DataFrame(dict(isin=['a','a'],decision_date=['2016-12-31','2020-12-31'],profile_name=['base7500']*2,future_xirr=[.1,.2]))
    combined=runner.combine_sources(scores,history)
    assert len(combined)==2
    early=combined.loc[combined.decision_date.eq('2016-12-31')].iloc[0]
    assert early.future_xirr==.1 and pd.isna(early.champion_score)
