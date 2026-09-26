#!/usr/bin/env python
"""Run the preregistered CatBoost/XGBoost ranker Pareto tournament."""
from __future__ import annotations

import argparse
from hashlib import sha256
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_research.open_source_rankers import (  # noqa: E402
    classify_pareto, fit_catboost, fit_lightgbm, fit_xgboost, mature_training, multi_k_metrics,
)
from stock_research.open_source_regimes import (  # noqa: E402
    BASE_FEATURES, blended_score, file_sha256,
)
from stock_research.personalized_executable_tournament import BASE_CANDIDATES  # noqa: E402


def canonical_hash(value) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def git(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=ROOT, text=True).strip()


def terminal_wealth(xirr: float, decision_date: str, profile: dict) -> float:
    end = pd.Timestamp(decision_date) + pd.DateOffset(months=int(profile["horizon_months"]))
    start = end - pd.DateOffset(months=int(profile["horizon_months"]))
    dates = pd.date_range(start, end - pd.Timedelta(days=1), freq=f"{int(profile['interval_days'])}D")
    years = (end - dates).days.to_numpy() / 365
    if not np.isfinite(xirr) or xirr <= -1:
        return np.nan
    return float(float(profile["amount"]) * np.power(1 + xirr, years).sum())


def aggregate_metrics(common: pd.DataFrame, score_columns: dict[str, str], profiles: dict,
                      top_ks: list[int]):
    metric_rows, selections = [], []
    common = common.copy()
    common["future_terminal_wealth"] = [
        terminal_wealth(row.future_xirr, row.decision_date, profiles[row.profile_name])
        for row in common.itertuples()
    ]
    for (day, profile), block in common.groupby(["decision_date", "profile_name"], sort=True):
        for candidate, score in score_columns.items():
            values = multi_k_metrics(block, score, top_ks)
            top = block.sort_values([score, "isin"], ascending=[False, True], kind="stable").head(max(top_ks))
            metric_rows.append({"decision_date": day, "profile": profile, "candidate": candidate, **values})
            for rank, row in enumerate(top.itertuples(), 1):
                selections.append({"decision_date": day, "profile": profile, "candidate": candidate,
                                   "rank": rank, "isin": row.isin, "score": getattr(row, score),
                                   "future_xirr": row.future_xirr, "future_shortfall": row.future_shortfall,
                                   "future_drawdown": row.future_drawdown,
                                   "future_terminal_wealth": row.future_terminal_wealth})
    return pd.DataFrame(metric_rows), pd.DataFrame(selections), common


def stability(metrics: pd.DataFrame, selections: pd.DataFrame, top_ks: list[int]):
    control = metrics.loc[metrics.candidate.eq("control")].drop(columns="candidate")
    paired = metrics.loc[~metrics.candidate.eq("control")].merge(
        control, on=["decision_date", "profile"], suffixes=("", "_control"), validate="many_to_one"
    )
    metric_names = [column for column in metrics if column not in {"decision_date", "profile", "candidate", "n"}]
    for metric in metric_names:
        paired[f"{metric}_delta_vs_control"] = paired[metric] - paired[f"{metric}_control"]
    overlap_rows = []
    for (day, profile, candidate), chosen in selections.groupby(["decision_date", "profile", "candidate"]):
        if candidate == "control":
            continue
        baseline = selections.loc[
            selections.decision_date.eq(day) & selections.profile.eq(profile) & selections.candidate.eq("control")
        ]
        row = {"decision_date": day, "profile": profile, "candidate": candidate}
        for k in top_ks:
            row[f"top{k}_overlap_with_control"] = len(
                set(chosen.loc[chosen["rank"] <= k, "isin"]) & set(baseline.loc[baseline["rank"] <= k, "isin"])
            ) / k
        overlap_rows.append(row)
    overlap = pd.DataFrame(overlap_rows)
    severe = paired.assign(
        severe_goal_shortfall=paired.goal_shortfall_top20_delta_vs_control.gt(.02),
        severe_goal_attainment=paired.goal_attainment_top20_delta_vs_control.lt(-.05),
        severe_mean_xirr=paired.mean_xirr_top20_delta_vs_control.lt(-.05),
        severe_median_xirr=paired.median_xirr_top20_delta_vs_control.lt(-.05),
        severe_drawdown=paired.mean_drawdown_top20_delta_vs_control.lt(-.05),
    )
    return paired, overlap, severe


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/open-source-ranker-challenger/run-01")
    args = parser.parse_args()
    output, source = args.output.resolve(), args.source_run.resolve()
    output.mkdir(parents=True, exist_ok=True)
    protocol_path = ROOT / "research/specifications/open_source_ranker_challenger_20260926.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    training_path, validation_path = source / "training_panel.csv.gz", source / "validation_predictions.csv.gz"
    training, validation = pd.read_csv(training_path, low_memory=False), pd.read_csv(validation_path, low_memory=False)

    frozen = git("rev-parse", "personalized-challenger-d499580-20260926^{}")
    if frozen != protocol["frozen_control"]["commit"]:
        raise RuntimeError("frozen control identity changed")
    production_before = git("rev-parse", "professor-railway-deploy-20260920")
    if set(BASE_FEATURES) != set(protocol["shared_contract"]["features"]):
        raise RuntimeError("stock feature contract changed")
    forbidden = {column for column in BASE_FEATURES if column.startswith("future_") or "regime" in column.lower()}
    if forbidden:
        raise RuntimeError(f"forbidden features: {sorted(forbidden)}")

    ranker_specs = protocol["rankers"]
    fitters = {"control": fit_lightgbm, "catboost_yetirank_pairwise": fit_catboost,
               "xgboost_rank_ndcg": fit_xgboost}
    predictions, audits = [], []
    for day, target in validation.groupby("decision_date", sort=True):
        mature = mature_training(training, day)
        result = target.copy()
        for candidate, fitter in fitters.items():
            score, audit = fitter(mature, target, ranker_specs[candidate]["parameters"])
            result[f"{candidate}_ranker_score"] = score
            audits.append({"decision_date": day, "candidate": candidate,
                           "latest_training_endpoint": str(mature.endpoint.max()), **audit})
        predictions.append(result)
    predictions = pd.concat(predictions, ignore_index=True)

    saved, rebuilt = predictions.lightgbm_lambdarank_score.to_numpy(float), predictions.control_ranker_score.to_numpy(float)
    finite = np.isfinite(saved) & np.isfinite(rebuilt)
    max_error = float(np.max(np.abs(saved[finite] - rebuilt[finite])))
    if not np.array_equal(np.isnan(saved), np.isnan(rebuilt)) or max_error > 1e-12:
        raise AssertionError(f"frozen control reconstruction mismatch: {max_error}")

    ranker_columns = [f"{name}_ranker_score" for name in fitters]
    common = predictions.dropna(subset=[*BASE_CANDIDATES, *ranker_columns, "future_xirr",
                                        "future_shortfall", "future_drawdown"]).copy()
    scores = {}
    for candidate in fitters:
        score = f"{candidate}_blend_score"
        common[score] = blended_score(common, f"{candidate}_ranker_score")
        scores[candidate] = score
    profiles = json.loads((source / "protocol.json").read_text(encoding="utf-8"))["profiles"]
    top_ks = [int(value) for value in protocol["evaluation"]["top_ks"]]
    metrics, selections, common = aggregate_metrics(common, scores, profiles, top_ks)
    summary = metrics.groupby("candidate", sort=True).mean(numeric_only=True).reset_index()
    control_summary = summary.loc[summary.candidate.eq("control")].iloc[0]
    frozen_summary = pd.read_csv(source / "ensemble_metrics.csv").loc[
        lambda frame: frame.candidate.eq("enhanced_goal+lightgbm_lambdarank@0.670-0.330")
    ].iloc[0]
    frozen_checks = {
        "rank_ic": ("rank_ic", "rank_ic"), "ndcg_at_20": ("ndcg_at_20", "ndcg20"),
        "pairwise_accuracy": ("pairwise_accuracy", "pairwise_accuracy"),
        "goal_attainment_top20": ("goal_attainment_top20", "target_achievement_top20"),
        "goal_shortfall_top20": ("goal_shortfall_top20", "target_shortfall_top20"),
        "mean_xirr_top20": ("mean_xirr_top20", "mean_xirr_top20"),
        "median_xirr_top20": ("median_xirr_top20", "median_xirr_top20"),
        "mean_drawdown_top20": ("mean_drawdown_top20", "mean_asset_drawdown_top20"),
    }
    aggregate_errors = {name: abs(float(control_summary[left]) - float(frozen_summary[right]))
                        for name, (left, right) in frozen_checks.items()}
    if max(aggregate_errors.values()) > 1e-12:
        raise AssertionError(f"frozen aggregate mismatch: {aggregate_errors}")

    pareto = {}
    for candidate in ("catboost_yetirank_pairwise", "xgboost_rank_ndcg"):
        candidate_summary = summary.loc[summary.candidate.eq(candidate)].iloc[0]
        pareto[candidate] = classify_pareto(candidate_summary, control_summary, protocol)
    paired, overlap, severe = stability(metrics, selections, top_ks)
    stability_summary = []
    for candidate, group in paired.groupby("candidate", sort=True):
        by_date = group.groupby("decision_date").goal_shortfall_top20_delta_vs_control.mean()
        by_profile = group.groupby("profile").goal_shortfall_top20_delta_vs_control.mean()
        severe_group = severe.loc[severe.candidate.eq(candidate)]
        stability_summary.append({
            "candidate": candidate, "dates_lower_shortfall": int(by_date.lt(0).sum()),
            "dates_higher_shortfall": int(by_date.gt(0).sum()),
            "profiles_lower_shortfall": int(by_profile.lt(0).sum()),
            "profiles_higher_shortfall": int(by_profile.gt(0).sum()),
            "query_blocks_lower_shortfall": int(group.goal_shortfall_top20_delta_vs_control.lt(0).sum()),
            "query_blocks_total": int(len(group)),
            "severely_harmed_query_blocks": int(severe_group.filter(like="severe_").any(axis=1).sum()),
        })
    stability_summary = pd.DataFrame(stability_summary)
    fusion = {
        "evaluated": False,
        "reason": ("At least one individual passed; upstream fusion review required before a separate preregistration."
                   if any(value["passed"] for value in pareto.values()) else
                   "Neither individual ranker passed the Pareto gate, so rank fusion was not scientifically justified."),
    }

    keep = ["decision_date", "profile_name", "isin", "future_xirr", "future_shortfall",
            "future_drawdown", "future_terminal_wealth", *ranker_columns, *scores.values()]
    common[keep].to_csv(output / "common_predictions.csv.gz", index=False,
                        compression={"method": "gzip", "mtime": 0})
    metrics.to_csv(output / "query_metrics.csv", index=False)
    summary.to_csv(output / "summary_metrics.csv", index=False)
    selections.to_csv(output / "topk_selections.csv.gz", index=False,
                      compression={"method": "gzip", "mtime": 0})
    paired.to_csv(output / "paired_query_deltas.csv", index=False)
    overlap.to_csv(output / "topk_overlap.csv", index=False)
    metrics.groupby(["candidate", "decision_date"], sort=True).mean(numeric_only=True).reset_index().to_csv(
        output / "date_stability.csv", index=False)
    metrics.groupby(["candidate", "profile"], sort=True).mean(numeric_only=True).reset_index().to_csv(
        output / "profile_stability.csv", index=False)
    stability_summary.to_csv(output / "stability_summary.csv", index=False)
    write_json(output / "pareto_gate.json", pareto)
    write_json(output / "fusion_decision.json", fusion)
    write_json(output / "model_audit.json", audits)
    packages = {name: importlib.metadata.version(name) for name in
                ("catboost", "xgboost", "lightgbm", "numpy", "pandas", "scikit-learn")}
    write_json(output / "environment.json", packages)
    provenance = {
        "catboost_docs": "https://catboost.ai/docs/en/concepts/loss-functions-ranking",
        "catboost_paper": "https://proceedings.neurips.cc/paper/2018/hash/14491b756b3a51daac41c24863285549-Abstract.html",
        "yetirank_paper": "https://proceedings.mlr.press/v14/gulin11a.html",
        "xgboost_ltr_docs": "https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html",
        "xgboost_paper_doi": "10.1145/2939672.2939785",
    }
    write_json(output / "source_provenance.json", provenance)
    leakage = {
        "status": "PASS", "features": BASE_FEATURES, "future_or_regime_features": sorted(forbidden),
        "all_training_endpoints_strictly_before_decision": all(
            pd.Timestamp(row["latest_training_endpoint"]) < pd.Timestamp(row["decision_date"]) for row in audits
        ), "frozen_prediction_max_abs_error": max_error,
        "frozen_aggregate_max_abs_error": max(aggregate_errors.values()),
        "frozen_control_commit": frozen,
    }
    write_json(output / "leakage_audit.json", leakage)
    requirements = ROOT / "research/specifications/open_source_ranker_requirements_20260926.txt"
    inputs = {"hashes": {
        "protocol": file_sha256(protocol_path), "requirements": file_sha256(requirements),
        "training_panel": file_sha256(training_path), "validation_predictions": file_sha256(validation_path),
        "frozen_ensemble_metrics": file_sha256(source / "ensemble_metrics.csv"),
        "runner": file_sha256(Path(__file__)),
        "adapter": file_sha256(ROOT / "src/stock_research/open_source_rankers.py"),
    }, "source_run": str(source), "frozen_control_commit": frozen,
        "production_ref_before": production_before, "protocol_sha256": file_sha256(protocol_path)}
    write_json(output / "inputs.json", inputs)
    conclusion = {
        "status": "RESEARCH_ONLY", "pareto_winners": [name for name, value in pareto.items() if value["passed"]],
        "selected_system": (next((name for name, value in pareto.items() if value["passed"]), "control")),
        "fusion_evaluated": fusion["evaluated"], "production_changed": False,
        "frozen_control_changed": False, "promotion": "NONE",
    }
    write_json(output / "conclusion.json", conclusion)

    artifacts = []
    for path in sorted(output.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            artifacts.append({"path": path.name, "bytes": path.stat().st_size, "sha256": file_sha256(path)})
    manifest = {"schema_version": "open_source_ranker_challenger_manifest_v1", "artifacts": artifacts,
                "artifact_set_sha256": canonical_hash(artifacts), "git_branch": git("branch", "--show-current"),
                "frozen_control_commit": frozen, "production_ref_after": git("rev-parse", "professor-railway-deploy-20260920")}
    if manifest["production_ref_after"] != production_before:
        raise RuntimeError("production ref changed")
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output": str(output), "pareto_winners": conclusion["pareto_winners"],
                      "selected": conclusion["selected_system"]}, indent=2))


if __name__ == "__main__":
    main()
