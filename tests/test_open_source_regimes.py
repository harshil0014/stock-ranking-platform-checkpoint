from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from stock_research.open_source_regimes import (
    add_market_context, author_example_features, blended_score,
    comprehensive_metrics, load_yahoo_close, verify_regime_run,
)


def test_author_example_features_are_prefix_invariant():
    dates = pd.date_range("2010-01-01", periods=500, freq="D")
    returns = pd.Series(np.where(np.arange(500) % 2, .01, -.01), index=dates)
    full = author_example_features(returns)
    truncated = author_example_features(returns.iloc[:350])
    pd.testing.assert_frame_equal(full.loc[truncated.index], truncated)


def test_market_loader_enforces_hard_cutoff_without_imputation(tmp_path):
    path = tmp_path / "market.csv"
    dates = pd.date_range("2010-01-01", periods=1001, freq="D")
    columns = pd.MultiIndex.from_tuples([("Close", "TEST")])
    pd.DataFrame(np.arange(1001) + 1.0, index=dates, columns=columns).to_csv(path)
    close = load_yahoo_close(path, str(dates[-2].date()))
    assert close.index.max() == dates[-2]
    assert len(close) == 1000


def test_market_context_requires_every_decision_and_blend_stays_within_query():
    panel = pd.DataFrame({
        "decision_date": ["2020-01-01"] * 3, "profile_name": ["p"] * 3,
        "enhanced_goal_score": [1., 2., 3.], "ranker": [3., 2., 1.],
    })
    snapshots = pd.DataFrame({"decision_date": ["2020-01-01"], "jump_bear_state": [1]})
    merged = add_market_context(panel, snapshots)
    assert merged.jump_bear_state.eq(1).all()
    assert blended_score(merged, "ranker").round(6).tolist() == [.553333, .666667, .78]
    with pytest.raises(ValueError, match="missing"):
        add_market_context(panel.assign(decision_date="2021-01-01"), snapshots)


def test_comprehensive_ranking_metrics_have_exact_top_k_overlap():
    frame = pd.DataFrame({
        "isin": [f"i{i}" for i in range(30)], "score": np.arange(30),
        "future_xirr": np.arange(30), "future_shortfall": np.zeros(30),
        "future_drawdown": np.full(30, -.1),
    })
    result = comprehensive_metrics(frame, "score", 20)
    assert result["precision_at_20"] == result["recall_at_20"] == 1
    assert result["rank_ic"] == result["pairwise_accuracy"] == 1


def test_verifier_rejects_artifact_mutation(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    import hashlib
    artifact = {"path": "a.txt", "bytes": 1, "sha256": hashlib.sha256(b"a").hexdigest()}
    artifacts = [artifact]
    fingerprint = hashlib.sha256(json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (tmp_path / "leakage_audit.json").write_text(json.dumps({"status": "PASS", "frozen_control_prediction_max_abs_error": 0}))
    (tmp_path / "conclusion.json").write_text(json.dumps({"production_changed": False, "frozen_control_changed": False, "selection_rule_winner": "control", "control_goal_shortfall_top20": 0.07627221047547905}))
    # Include audit files in the real artifact inventory, as the runner does.
    artifacts = []
    for name in ("a.txt", "leakage_audit.json", "conclusion.json"):
        raw = (tmp_path / name).read_bytes()
        artifacts.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    fingerprint = hashlib.sha256(json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (tmp_path / "manifest.json").write_text(json.dumps({"artifacts": artifacts, "artifact_set_sha256": fingerprint, "frozen_control_commit": "d499580"}))
    assert verify_regime_run(tmp_path)["selection_rule_winner"] == "control"
    (tmp_path / "a.txt").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        verify_regime_run(tmp_path)
