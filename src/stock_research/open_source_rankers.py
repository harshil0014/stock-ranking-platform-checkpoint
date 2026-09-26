"""Minimal adapters for the preregistered open-source ranker tournament."""
from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd

from stock_research.open_source_regimes import BASE_FEATURES


def mature_training(training: pd.DataFrame, decision_date: str) -> pd.DataFrame:
    maturity = pd.to_datetime(training["endpoint"], errors="raise")
    result = training.loc[maturity.lt(pd.Timestamp(decision_date))].copy()
    if result.empty or pd.to_datetime(result.endpoint).ge(pd.Timestamp(decision_date)).any():
        raise ValueError("matured-label boundary failed")
    return result


def ordered_training(training: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series, np.ndarray, list[int]]:
    ordered = training.loc[
        training.future_xirr.notna() & training.enhanced_carry_xirr_score.notna()
    ].sort_values(["decision_date", "profile_name", "isin"], kind="stable")
    labels = ordered.groupby(["decision_date", "profile_name"]).future_xirr.rank(
        pct=True
    ).mul(4).clip(upper=3).astype(int)
    groups = ordered.groupby(["decision_date", "profile_name"], sort=False).size()
    qid = np.repeat(np.arange(len(groups), dtype=np.int32), groups.to_numpy())
    return ordered, labels, qid, groups.astype(int).tolist()


def _valid_prediction_target(target: pd.DataFrame) -> pd.Series:
    return target.enhanced_carry_xirr_score.notna()


def fit_lightgbm(training: pd.DataFrame, target: pd.DataFrame, parameters: dict):
    from lightgbm import LGBMRanker
    ordered, labels, _, groups = ordered_training(training)
    model = LGBMRanker(**parameters)
    model.fit(ordered[BASE_FEATURES], labels, group=groups)
    valid = _valid_prediction_target(target)
    prediction = pd.Series(np.nan, index=target.index, dtype=float)
    prediction.loc[valid] = model.predict(target.loc[valid, BASE_FEATURES])
    raw = model.booster_.model_to_string().encode("utf-8")
    return prediction, {
        "training_rows": int(len(ordered)), "query_count": len(groups),
        "model_sha256": sha256(raw).hexdigest(),
        "feature_importance": dict(zip(BASE_FEATURES, model.feature_importances_.astype(int).tolist())),
    }


def fit_catboost(training: pd.DataFrame, target: pd.DataFrame, parameters: dict):
    from catboost import CatBoostRanker
    ordered, labels, qid, groups = ordered_training(training)
    model = CatBoostRanker(**parameters)
    model.fit(ordered[BASE_FEATURES], labels, group_id=qid)
    valid = _valid_prediction_target(target)
    prediction = pd.Series(np.nan, index=target.index, dtype=float)
    prediction.loc[valid] = model.predict(target.loc[valid, BASE_FEATURES]).reshape(-1)
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "model.json"
        model.save_model(path, format="json")
        payload = json.loads(path.read_text(encoding="utf-8"))
        # CatBoost embeds training timestamps in model_info.  Hash only the
        # predictive structure so identical models have identical hashes.
        raw = json.dumps({key: payload[key] for key in ("features_info", "oblivious_trees")},
                         sort_keys=True, separators=(",", ":")).encode("utf-8")
    return prediction, {
        "training_rows": int(len(ordered)), "query_count": len(groups),
        "model_sha256": sha256(raw).hexdigest(),
        "feature_importance": dict(zip(BASE_FEATURES, np.asarray(model.get_feature_importance(
            type="PredictionValuesChange"
        )).tolist())),
    }


def fit_xgboost(training: pd.DataFrame, target: pd.DataFrame, parameters: dict):
    from xgboost import XGBRanker
    ordered, labels, qid, groups = ordered_training(training)
    model = XGBRanker(**parameters)
    model.fit(ordered[BASE_FEATURES], labels, qid=qid, verbose=False)
    valid = _valid_prediction_target(target)
    prediction = pd.Series(np.nan, index=target.index, dtype=float)
    prediction.loc[valid] = model.predict(target.loc[valid, BASE_FEATURES])
    raw = bytes(model.get_booster().save_raw(raw_format="json"))
    return prediction, {
        "training_rows": int(len(ordered)), "query_count": len(groups),
        "model_sha256": sha256(raw).hexdigest(),
        "feature_importance": {key: float(value) for key, value in model.get_booster().get_score(
            importance_type="gain"
        ).items()},
    }


def expanded_metric_contract(protocol: dict) -> tuple[dict[str, str], dict[str, float]]:
    evaluation = protocol["evaluation"]
    directions, thresholds = {}, {}
    for template, direction in evaluation["protected_metric_families"].items():
        keys = [template.format(k=k) for k in evaluation["top_ks"]] if "{k}" in template else [template]
        directions.update({key: direction for key in keys})
    for template, threshold in evaluation["material_improvement_threshold_families"].items():
        keys = [template.format(k=k) for k in evaluation["top_ks"]] if "{k}" in template else [template]
        thresholds.update({key: float(threshold) for key in keys})
    return directions, thresholds


def multi_k_metrics(frame: pd.DataFrame, score: str, top_ks: list[int]) -> dict:
    columns = [score, "future_xirr", "future_shortfall", "future_drawdown",
               "future_terminal_wealth", "isin"]
    usable = frame[columns].dropna()
    result = {"n": int(len(usable)), "coverage": float(len(usable) / max(len(frame), 1))}
    if len(usable) < max(top_ks):
        raise ValueError("query is smaller than preregistered maximum K")
    x, y = usable[score].to_numpy(), usable.future_xirr.to_numpy()
    sample = np.linspace(0, len(usable) - 1, min(len(usable), 400), dtype=int)
    dx, dy = x[sample, None] - x[None, sample], y[sample, None] - y[None, sample]
    mask = np.triu(np.ones_like(dx, dtype=bool), 1) & (dy != 0)
    pairs = np.where(dx * dy > 0, 1., np.where(dx == 0, .5, 0.))[mask]
    result["pairwise_accuracy"] = float(pairs.mean()) if len(pairs) else np.nan
    result["rank_ic"] = float(usable[score].rank().corr(usable.future_xirr.rank()))
    predicted_order = usable.sort_values([score, "isin"], ascending=[False, True], kind="stable")
    actual_order = usable.sort_values(["future_xirr", "isin"], ascending=[False, True], kind="stable")
    relevance = usable.future_xirr.rank(pct=True)
    for k in top_ks:
        predicted, actual = predicted_order.head(k), actual_order.head(k)
        overlap = len(set(predicted["isin"]) & set(actual["isin"]))
        gains = relevance.loc[predicted.index].to_numpy()
        ideal = relevance.nlargest(k).to_numpy()
        discount = np.log2(np.arange(2, k + 2))
        result.update({
            f"precision_at_{k}": float(overlap / k), f"recall_at_{k}": float(overlap / k),
            f"ndcg_at_{k}": float((gains / discount).sum() / (ideal / discount).sum()),
            f"goal_attainment_top{k}": float(predicted.future_shortfall.eq(0).mean()),
            f"goal_shortfall_top{k}": float(predicted.future_shortfall.mean()),
            f"mean_xirr_top{k}": float(predicted.future_xirr.mean()),
            f"median_xirr_top{k}": float(predicted.future_xirr.median()),
            f"terminal_wealth_top{k}": float(predicted.future_terminal_wealth.mean()),
            f"mean_drawdown_top{k}": float(predicted.future_drawdown.mean()),
        })
    return result


def classify_pareto(candidate: pd.Series, control: pd.Series, protocol: dict) -> dict:
    directions, thresholds = expanded_metric_contract(protocol)
    tolerance = float(protocol["evaluation"]["pareto_equivalence_tolerance"])
    rows, degraded, material = [], [], []
    for metric, direction in directions.items():
        control_value, candidate_value = float(control[metric]), float(candidate[metric])
        improvement = candidate_value - control_value
        if direction == "lower":
            improvement *= -1
        threshold = thresholds.get(metric)
        if metric.startswith("terminal_wealth_top"):
            threshold = abs(control_value) * float(thresholds[metric + "_relative"])
        threshold = float(threshold)
        if improvement < -tolerance:
            status = "DEGRADED"; degraded.append(metric)
        elif abs(improvement) <= tolerance:
            status = "TIED"
        elif improvement >= threshold:
            status = "MATERIALLY_IMPROVED"; material.append(metric)
        else:
            status = "IMPROVED_BELOW_MATERIAL_THRESHOLD"
        rows.append({"metric": metric, "direction": direction, "control": control_value,
                     "candidate": candidate_value, "directional_improvement": improvement,
                     "material_threshold": threshold, "status": status})
    return {"passed": not degraded and bool(material), "degraded": degraded,
            "materially_improved": material, "metrics": rows}


def verify_ranker_run(directory: str | Path) -> dict:
    import json
    root = Path(directory).resolve()
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    artifacts = manifest["artifacts"]
    expected = sha256(json.dumps(artifacts, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    if expected != manifest.get("artifact_set_sha256"):
        raise ValueError("ranker artifact inventory mismatch")
    for item in artifacts:
        path = (root / item["path"]).resolve()
        if path.parent != root or not path.is_file() or path.stat().st_size != item["bytes"]:
            raise ValueError("unsafe or missing ranker artifact")
        if sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError(f"ranker artifact changed: {item['path']}")
    leakage = json.loads((root / "leakage_audit.json").read_text(encoding="utf-8"))
    conclusion = json.loads((root / "conclusion.json").read_text(encoding="utf-8"))
    if leakage.get("status") != "PASS" or leakage.get("frozen_prediction_max_abs_error", 1) > 1e-12:
        raise ValueError("leakage or frozen prediction audit failed")
    if leakage.get("frozen_aggregate_max_abs_error", 1) > 1e-12:
        raise ValueError("frozen aggregate audit failed")
    if conclusion.get("production_changed") is not False or conclusion.get("frozen_control_changed") is not False:
        raise ValueError("immutable boundary failed")
    if manifest.get("frozen_control_commit") != "d4995807163bef1ec4b297179e6c54a59c71f390":
        raise ValueError("frozen control identity failed")
    return conclusion
