"""Add post-selection ablations and current fixed-ensemble rankings."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import numpy as np
import pandas as pd
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from stock_research.personalized_executable_tournament import FEATURES, BASE_CANDIDATES
from stock_research.personalized_validation import ranking_metrics


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def run(args) -> None:
    output = args.tournament
    assessment = json.loads((output / "final_assessment.json").read_text(encoding="utf-8"))
    selected = assessment["strongest_fixed_ensemble_by_goal_shortfall"]
    current = pd.read_csv(output / "current_profile_rankings.csv.gz", low_memory=False)
    components = ["enhanced_goal_score", "ridge_executable_score", "lightgbm_lambdarank_score"]
    if selected != "enhanced_goal+ridge_executable+lightgbm_lambdarank@0.333-0.333-0.333":
        raise ValueError("unexpected fixed selection")
    ranks = current.groupby("profile_name")[components].rank(pct=True)
    current["selected_fixed_ensemble_score"] = ranks.mean(axis=1).where(ranks.notna().all(axis=1))
    current.to_csv(output / "current_profile_rankings.csv.gz", index=False,
                   compression={"method": "gzip", "mtime": 0})
    train = pd.read_csv(output / "training_panel.csv.gz", low_memory=False)
    validation = pd.read_csv(output / "validation_predictions.csv.gz", low_memory=False)
    train = train.loc[train.future_xirr.notna() & train.enhanced_carry_xirr_score.notna()].sort_values(
        ["decision_date", "profile_name", "isin"], kind="stable")
    features = [column for column in FEATURES if column != "price_drawdown"]
    model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(), Ridge(alpha=100.0))
    model.fit(train[features], train.future_xirr.clip(-1, 3))
    validation["ridge_without_risk_score"] = model.predict(validation[features])
    validation["ridge_without_risk_score"] = validation.ridge_without_risk_score.where(
        validation.enhanced_carry_xirr_score.notna())
    required = [*BASE_CANDIDATES, "future_xirr", "future_shortfall", "future_drawdown"]
    risk_rows = []
    for (day, profile), group in validation.groupby(["decision_date", "profile_name"], sort=True):
        common = group.dropna(subset=required)
        risk_rows.append({"decision_date": day, "profile": profile,
                          **ranking_metrics(common, "ridge_without_risk_score")})
    risk = pd.DataFrame(risk_rows)
    risk.to_csv(output / "risk_ablation_metrics.csv", index=False, lineterminator="\n")
    ablation = pd.read_csv(output / "model_ablation.csv")
    extra = []
    full = pd.read_csv(output / "candidate_metrics.csv").set_index("candidate").loc["ridge_executable_score"]
    reduced = risk.mean(numeric_only=True)
    for metric in ("rank_ic", "target_achievement_top20", "target_shortfall_top20"):
        sign = -1 if metric == "target_shortfall_top20" else 1
        extra.append({"component": "risk_feature_price_drawdown", "full": "ridge_executable_score",
                      "without": "ridge_without_risk_score", "metric": metric,
                      "improvement": sign * (full[metric] - reduced[metric])})
    ensembles = pd.read_csv(output / "ensemble_metrics.csv").set_index("candidate")
    simple = "enhanced_goal+ridge_executable@0.500-0.500"
    for metric in ("rank_ic", "target_achievement_top20", "target_shortfall_top20"):
        sign = -1 if metric == "target_shortfall_top20" else 1
        extra.append({"component": "lambda_rank_component", "full": selected,
                      "without": simple, "metric": metric,
                      "improvement": sign * (ensembles.loc[selected, metric] - ensembles.loc[simple, metric])})
    prior = pd.read_csv(output / "previous_policy_validation_comparison.csv").set_index("candidate")
    for metric in ("rank_ic", "target_achievement_top20", "target_shortfall_top20"):
        sign = -1 if metric == "target_shortfall_top20" else 1
        row = prior.loc["hist_gradient_boosting_score"]
        extra.append({"component": "corporate_action_recovery", "full": "build_03_hist_gradient_boosting",
                      "without": "build_02_hist_gradient_boosting", "metric": metric,
                      "improvement": sign * (row[metric + "_official"] - row[metric + "_old_yahoo_policy"])})
    pd.concat([ablation, pd.DataFrame(extra)], ignore_index=True).to_csv(
        output / "model_ablation.csv", index=False, lineterminator="\n")
    write_json(output / "diagnostic_methods.json", {
        "risk_ablation": "Ridge alpha 100 trained on original training dates, excluding price_drawdown, scored on original validation dates and common cohort.",
        "ml_component_ablation": "Fixed equal goal+ridge ensemble versus pre-registered equal goal+ridge+LambdaRank ensemble on same validation cohort.",
        "corporate_action_ablation": "Build-03 versus prior build-02 official-action tournament; descriptive since comparison cohort size changes.",
        "status": "POST_SELECTION_DIAGNOSTIC_NOT_USED_FOR_MODEL_SELECTION",
    })
    files = [{"path": p.name, "size": p.stat().st_size, "sha256": sha256(p.read_bytes()).hexdigest()}
             for p in sorted(output.iterdir()) if p.is_file() and p.name not in {"manifest.json", "assessment.json"}]
    write_json(output / "manifest.json", {"deterministic_artifacts": files,
        "observational_artifacts": ["assessment.json"],
        "fingerprint": sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", type=Path, required=True)
    run(parser.parse_args())
