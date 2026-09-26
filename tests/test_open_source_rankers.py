from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from stock_research.open_source_rankers import (
    classify_pareto, expanded_metric_contract, mature_training, multi_k_metrics,
    ordered_training, verify_ranker_run,
)
from stock_research.open_source_regimes import BASE_FEATURES


def test_matured_label_boundary_ignores_future_outcome_mutation():
    frame = pd.DataFrame({"endpoint": ["2019-01-01", "2021-01-01"], "future_xirr": [1., 2.]})
    first = mature_training(frame, "2020-01-01")
    mutated = frame.copy(); mutated.loc[1, "future_xirr"] = 999999
    second = mature_training(mutated, "2020-01-01")
    pd.testing.assert_frame_equal(first, second)
    assert first.index.tolist() == [0]


def test_query_mapping_is_contiguous_and_labels_are_graded():
    frame = pd.DataFrame({
        "decision_date": ["2018-01-01"] * 4 + ["2019-01-01"] * 3,
        "profile_name": ["p"] * 7, "isin": list("gfedcba"),
        "future_xirr": [1, 2, 3, 4, 3, 2, 1],
        "enhanced_carry_xirr_score": np.ones(7),
    })
    ordered, labels, qid, groups = ordered_training(frame)
    assert groups == [4, 3]
    assert qid.tolist() == [0, 0, 0, 0, 1, 1, 1]
    assert labels.between(0, 3).all()
    assert ordered.iloc[:4]["isin"].tolist() == sorted(ordered.iloc[:4]["isin"].tolist())


def _protocol():
    metrics = {name: "higher" for name in (
        "coverage", "precision_at_{k}", "recall_at_{k}", "ndcg_at_{k}", "pairwise_accuracy",
        "rank_ic", "goal_attainment_top{k}", "mean_xirr_top{k}", "median_xirr_top{k}",
        "terminal_wealth_top{k}", "mean_drawdown_top{k}")}
    metrics["goal_shortfall_top{k}"] = "lower"
    thresholds = {name: .01 for name in metrics}; thresholds["terminal_wealth_top{k}_relative"] = .01
    return {"evaluation": {"top_ks": [20], "protected_metric_families": metrics,
                           "material_improvement_threshold_families": thresholds,
                           "pareto_equivalence_tolerance": 1e-12}}


def test_pareto_gate_requires_material_gain_and_zero_degradation():
    directions, _ = expanded_metric_contract(_protocol())
    control = pd.Series({name: 1. for name in directions})
    candidate = control.copy(); candidate["ndcg_at_20"] += .02
    assert classify_pareto(candidate, control, _protocol())["passed"] is True
    candidate["rank_ic"] -= 1e-8
    result = classify_pareto(candidate, control, _protocol())
    assert result["passed"] is False and result["degraded"] == ["rank_ic"]


def test_multi_k_evaluation_uses_every_preregistered_cutoff():
    frame = pd.DataFrame({
        "score": np.arange(60, dtype=float),
        "future_xirr": np.arange(60, dtype=float),
        "future_shortfall": np.zeros(60),
        "future_drawdown": np.zeros(60),
        "future_terminal_wealth": np.ones(60),
        "isin": [f"i{x:03}" for x in range(60)],
    })
    result = multi_k_metrics(frame, "score", [5, 10, 20, 50])
    assert all(f"ndcg_at_{k}" in result for k in (5, 10, 20, 50))
    assert all(result[f"precision_at_{k}"] == 1 for k in (5, 10, 20, 50))


def test_official_ranker_adapters_are_deterministic():
    pytest.importorskip("catboost"); pytest.importorskip("xgboost")
    from stock_research.open_source_rankers import fit_catboost, fit_xgboost
    rng = np.random.default_rng(7); n = 80
    frame = pd.DataFrame(rng.normal(size=(n, len(BASE_FEATURES))), columns=BASE_FEATURES)
    frame["decision_date"] = np.repeat(["2018-01-01", "2019-01-01"], n // 2)
    frame["profile_name"] = "p"; frame["isin"] = [f"i{x:03}" for x in range(n)]
    frame["future_xirr"] = rng.normal(size=n)
    target = frame.iloc[:20].copy()
    cat = {"loss_function": "YetiRankPairwise", "iterations": 3, "depth": 2,
           "random_seed": 1, "thread_count": 1, "allow_writing_files": False, "verbose": False}
    xgb = {"objective": "rank:ndcg", "n_estimators": 3, "max_depth": 2, "random_state": 1,
           "n_jobs": 1, "tree_method": "hist", "lambdarank_pair_method": "topk",
           "lambdarank_num_pair_per_sample": 20}
    for fitter, parameters in ((fit_catboost, cat), (fit_xgboost, xgb)):
        first, first_audit = fitter(frame, target, parameters)
        second, second_audit = fitter(frame, target, parameters)
        np.testing.assert_array_equal(first, second)
        assert first_audit["model_sha256"] == second_audit["model_sha256"]


def test_verifier_rejects_mutation(tmp_path):
    import hashlib
    (tmp_path / "leakage_audit.json").write_text(json.dumps({"status": "PASS", "frozen_prediction_max_abs_error": 0, "frozen_aggregate_max_abs_error": 0}))
    (tmp_path / "conclusion.json").write_text(json.dumps({"production_changed": False, "frozen_control_changed": False, "selected_system": "control"}))
    artifacts = []
    for name in ("leakage_audit.json", "conclusion.json"):
        raw = (tmp_path / name).read_bytes(); artifacts.append({"path": name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()})
    fingerprint = hashlib.sha256(json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    manifest = {"artifacts": artifacts, "artifact_set_sha256": fingerprint,
                "frozen_control_commit": "d4995807163bef1ec4b297179e6c54a59c71f390"}
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    assert verify_ranker_run(tmp_path)["selected_system"] == "control"
    (tmp_path / "conclusion.json").write_text("tampered")
    with pytest.raises(ValueError, match="artifact"):
        verify_ranker_run(tmp_path)
