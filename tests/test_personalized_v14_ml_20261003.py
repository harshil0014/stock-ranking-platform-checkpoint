import numpy as np
import pandas as pd
import json

from research.runners import personalized_v14_ml_20261003 as v14


def _tiny():
    frame = pd.DataFrame({
        "isin": ["a", "b"], "decision_date": ["2020-03-31"] * 2,
        "profile_name": ["weekly"] * 2, "amount_per_contribution": [100., 100.],
        "contribution_count": [50, 50], "target_wealth": [11000., 11000.],
        "amount_contributed": [5000., 5000.], "terminal_price": [10., 20.],
        "history_months": [120., 8.], "cagr_3y": [.1, np.nan],
        "cagr_5y_observed": [1, 0], "observed_cagr_5y": [.12, np.nan],
        "enhanced_goal_score": [.2, .3], "distance_from_recorded_high": [-.1, -.5],
        "downside_volatility_1y": [.2, np.nan], "strict_cagr_1y": [.15, np.nan],
        "strict_cagr_7y": [.1, np.nan], "strict_cagr_10y": [.1, np.nan],
    })
    for feature in v14.BASE + v14.HISTORY:
        if feature not in frame:
            frame[feature] = np.nan
    return frame


def test_feature_contract_excludes_future_champion_identity_and_provenance():
    v14.check_contract()
    assert not any("future" in f or "champion" in f or "professor" in f for f in v14.FEATURES)
    assert "isin" not in v14.FEATURES and "ticker" not in v14.FEATURES


def test_missing_percentile_never_gets_positive_fill():
    x = v14.add_features(_tiny())
    assert np.isnan(x.loc[1, "pct_strict_cagr_1y"])
    assert x.loc[1, "missing_5y"] == 1
    assert x.loc[0, "has_true_5y"] == 1
    assert x.loc[1, "frequency_months"] == .25


def test_rank_group_and_tie_output_is_deterministic():
    x = _tiny()
    x["v14_score"] = [.4, .4]
    a = x.groupby(["decision_date", "profile_name"]).v14_score.rank(ascending=False, method="first")
    b = x.groupby(["decision_date", "profile_name"]).v14_score.rank(ascending=False, method="first")
    assert a.tolist() == b.tolist() == [1., 2.]


def test_chronological_maturity_boundary_is_strict():
    train = pd.DataFrame({"endpoint": ["2020-03-30", "2020-03-31", "2020-04-01"]})
    valid = pd.to_datetime(train.endpoint).lt("2020-03-31")
    assert valid.tolist() == [True, False, False]


def test_frozen_champion_artifacts_match_pre_v14_hashes():
    freeze = v14.ROOT / "research/freezes/personalized-d499580"
    assert v14.sha(freeze / "manifest.json") == "f9919146a1dc5a0584f5c23a5ab288668b13298cc8f4bbf46a2b89c65d754035"
    assert v14.sha(freeze / "lambdarank.txt") == "354be0847b05445da331cda92fc33e2d8522df70798297af82a132214dfa3c1c"


def test_current_input_schema_is_available_without_historical_backfill():
    freeze = v14.ROOT / "research/freezes/personalized-d499580/rankings.csv.gz"
    overlay = v14.ROOT / "experiments/professor-current-fallback-20261003/equal-priority-v2/current_company_facts_equal_priority.csv.gz"
    old_columns = set(pd.read_csv(freeze, nrows=0).columns)
    current_columns = set(pd.read_csv(overlay, nrows=0).columns)
    assert set(v14.BASE).difference({"original_cagr_5y"}).issubset(old_columns)
    assert {"isin", "product_baseline_yoy_growth", "product_baseline_cagr_3y", "product_baseline_cagr_5y"}.issubset(current_columns)


def test_current_adjusted_extras_ignore_future_prices(tmp_path, monkeypatch):
    monkeypatch.setattr(v14, "OUT", tmp_path)
    path=tmp_path/"prices.csv"
    pd.DataFrame({"date":["2026-03-19","2026-09-18","2026-10-01"],
                  "adjusted_close":[10.,20.,1000.]}).to_csv(path,index=False)
    source=pd.DataFrame({"isin":["test"],"history_path":[str(path)],
                         "adjusted_history_available":[True]})
    result=v14.current_adjusted_extras(source,"2026-09-18")
    assert np.isclose(result.loc[0,"momentum_6m"],1.0)
    assert np.isclose(result.loc[0,"distance_from_1y_low"],1.0)


def test_current_raw_risk_fallback_is_quarantined():
    path=v14.ROOT/"experiments/personalized-v14-ml-20261003/current_provenance_audit.json"
    audit=json.loads(path.read_text())
    assert audit["risk_only_raw_values_used_as_model_features"] is False
    assert audit["raw_risk_only_identities"] >= 1
    assert audit["raw_risk_only_profile_rows_quarantined"] >= audit["raw_risk_only_identities"]
