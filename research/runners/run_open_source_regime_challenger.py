#!/usr/bin/env python
"""Run the preregistered causal open-source regime challenger tournament."""
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

from stock_research.open_source_regimes import (  # noqa: E402
    BASE_FEATURES, add_market_context, blended_score, comprehensive_metrics,
    file_sha256, fit_causal_regimes, fit_ranker, load_yahoo_close,
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


def turnover_rows(predictions: pd.DataFrame, candidates: list[str]) -> pd.DataFrame:
    rows = []
    for profile, group in predictions.groupby("profile_name", sort=True):
        dates = sorted(group.decision_date.unique())
        for candidate in candidates:
            previous = None
            for day in dates:
                block = group.loc[group.decision_date.eq(day)].dropna(subset=[candidate])
                selected = set(block.nlargest(20, candidate, keep="first")["isin"])
                if previous is not None:
                    rows.append({"profile": profile, "decision_date": day, "candidate": candidate,
                                 "top20_turnover": 1 - len(selected & previous) / 20})
                previous = selected
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-run", type=Path, required=True)
    parser.add_argument("--market-csv", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/open-source-regime-challenger/run-01")
    args = parser.parse_args()

    protocol_path = ROOT / "research/specifications/open_source_regime_challenger_20260926.json"
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    source = args.source_run.resolve()
    training_path, validation_path = source / "training_panel.csv.gz", source / "validation_predictions.csv.gz"
    for path in (training_path, validation_path, args.market_csv):
        if not path.is_file():
            raise FileNotFoundError(path)

    frozen = git("rev-parse", "personalized-challenger-d499580-20260926^{}")
    if not frozen.startswith("d499580"):
        raise RuntimeError("immutable control tag does not resolve to d499580")
    production_ref = git("rev-parse", "professor-railway-deploy-20260920")

    training = pd.read_csv(training_path, low_memory=False)
    validation = pd.read_csv(validation_path, low_memory=False)
    dates = sorted(set(training.decision_date.astype(str)) | set(validation.decision_date.astype(str)))
    close = load_yahoo_close(args.market_csv, protocol["market_data"]["hard_cutoff"])
    regimes = fit_causal_regimes(close, dates)

    # A second run with later observations removed proves earlier outputs do not
    # depend on the removed suffix.
    leakage_cutoff = "2022-06-30"
    earlier_dates = [day for day in dates if day <= leakage_cutoff]
    truncated = fit_causal_regimes(close.loc[:leakage_cutoff], earlier_dates)
    compare_columns = [column for column in regimes.snapshots if column not in {"market_observation_date"}]
    expected = regimes.snapshots.loc[regimes.snapshots.decision_date.isin(earlier_dates), compare_columns].reset_index(drop=True)
    actual = truncated.snapshots[compare_columns].reset_index(drop=True)
    pd.testing.assert_frame_equal(expected, actual, check_exact=False, rtol=1e-12, atol=1e-12)

    training = add_market_context(training, regimes.snapshots)
    validation = add_market_context(validation, regimes.snapshots)
    ranker_parameters = protocol["ranker"]["parameters_from_frozen_protocol"]
    challenger_features = {
        name: [*BASE_FEATURES, *extra]
        for name, extra in protocol["challengers"].items()
    }
    predictions, model_audit = [], []
    endpoint = pd.to_datetime(training.endpoint, errors="raise")
    for day, target in validation.groupby("decision_date", sort=True):
        mature = training.loc[endpoint.lt(pd.Timestamp(day))].copy()
        result = target.copy()
        for name, features in challenger_features.items():
            score, audit = fit_ranker(mature, target, features, ranker_parameters)
            result[f"{name}_ranker_score"] = score
            model_audit.append({"decision_date": day, "candidate": name, "features": features,
                                "latest_training_endpoint": str(mature.endpoint.max()), **audit})
        predictions.append(result)
    predictions = pd.concat(predictions, ignore_index=True)

    saved = predictions.lightgbm_lambdarank_score.to_numpy(float)
    rebuilt = predictions.control_ranker_score.to_numpy(float)
    control_mask = np.isfinite(saved) & np.isfinite(rebuilt)
    control_max_abs = float(np.max(np.abs(saved[control_mask] - rebuilt[control_mask])))
    if not np.array_equal(np.isnan(saved), np.isnan(rebuilt)) or control_max_abs > 1e-12:
        raise AssertionError(f"frozen control reconstruction mismatch: {control_max_abs}")

    ranker_columns = [f"{name}_ranker_score" for name in challenger_features]
    common = predictions.dropna(subset=[*BASE_CANDIDATES, *ranker_columns, "future_xirr",
                                        "future_shortfall", "future_drawdown"]).copy()
    blend_columns = [f"{name}_blend_score" for name in challenger_features]
    for name in challenger_features:
        common[f"{name}_blend_score"] = blended_score(common, f"{name}_ranker_score")
    profile_config = json.loads((source / "protocol.json").read_text(encoding="utf-8"))["profiles"]
    common["future_terminal_wealth"] = [
        terminal_wealth(row.future_xirr, row.decision_date, profile_config[row.profile_name])
        for row in common.itertuples()
    ]

    metric_rows = []
    top_rows = []
    for (day, profile), group in common.groupby(["decision_date", "profile_name"], sort=True):
        for column in blend_columns:
            candidate = column.removesuffix("_blend_score")
            metrics = comprehensive_metrics(group, column)
            top = group.sort_values([column, "isin"], ascending=[False, True], kind="stable").head(20)
            metrics["terminal_wealth_top20"] = float(top.future_terminal_wealth.mean())
            metric_rows.append({"decision_date": day, "profile": profile, "candidate": candidate, **metrics})
            for rank, row in enumerate(top.itertuples(), 1):
                top_rows.append({"decision_date": day, "profile": profile, "candidate": candidate,
                                 "rank": rank, "isin": row.isin, "score": getattr(row, column),
                                 "future_xirr": row.future_xirr, "future_shortfall": row.future_shortfall,
                                 "future_drawdown": row.future_drawdown,
                                 "future_terminal_wealth": row.future_terminal_wealth})
    metrics = pd.DataFrame(metric_rows)
    top_selections = pd.DataFrame(top_rows)
    turnover = turnover_rows(common, blend_columns)
    turnover["candidate"] = turnover.candidate.str.removesuffix("_blend_score")
    summary = metrics.groupby("candidate", sort=True).mean(numeric_only=True).reset_index()
    summary = summary.merge(turnover.groupby("candidate").top20_turnover.mean().rename("top20_turnover"),
                            on="candidate", how="left")
    summary["goal_shortfall_delta_vs_control"] = summary.goal_shortfall_top20 - float(
        summary.loc[summary.candidate.eq("control"), "goal_shortfall_top20"].iloc[0]
    )
    summary["rank_ic_delta_vs_control"] = summary.rank_ic - float(
        summary.loc[summary.candidate.eq("control"), "rank_ic"].iloc[0]
    )
    signal_rows = []
    for name in challenger_features:
        if name == "control":
            continue
        ranker_delta = common[f"{name}_ranker_score"] - common["control_ranker_score"]
        query_correlations = common.groupby(["decision_date", "profile_name"]).apply(
            lambda block: block[f"{name}_ranker_score"].corr(block["control_ranker_score"], method="spearman"),
            include_groups=False,
        )
        signal_rows.append({
            "candidate": name,
            "prediction_rows": int(ranker_delta.notna().sum()),
            "fraction_ranker_predictions_changed": float(ranker_delta.abs().gt(1e-12).mean()),
            "mean_absolute_ranker_prediction_change": float(ranker_delta.abs().mean()),
            "mean_within_query_spearman_vs_control": float(query_correlations.mean()),
        })
    incremental_signal = pd.DataFrame(signal_rows)

    control_metrics = metrics.loc[metrics.candidate.eq("control")].drop(columns="candidate")
    paired = metrics.loc[~metrics.candidate.eq("control")].merge(
        control_metrics, on=["decision_date", "profile"], suffixes=("", "_control"), validate="many_to_one"
    )
    for metric in ("goal_shortfall_top20", "goal_attainment_top20", "rank_ic", "ndcg_at_20",
                   "mean_xirr_top20", "terminal_wealth_top20"):
        paired[f"{metric}_delta_vs_control"] = paired[metric] - paired[f"{metric}_control"]

    date_stability = metrics.groupby(["candidate", "decision_date"], sort=True).mean(numeric_only=True).reset_index()
    profile_stability = metrics.groupby(["candidate", "profile"], sort=True).mean(numeric_only=True).reset_index()
    stability_summary = []
    for candidate, group in paired.groupby("candidate", sort=True):
        by_date = group.groupby("decision_date").goal_shortfall_top20_delta_vs_control.mean()
        by_profile = group.groupby("profile").goal_shortfall_top20_delta_vs_control.mean()
        stability_summary.append({
            "candidate": candidate,
            "dates_better_goal_shortfall": int(by_date.lt(0).sum()),
            "dates_worse_goal_shortfall": int(by_date.gt(0).sum()),
            "profiles_better_goal_shortfall": int(by_profile.lt(0).sum()),
            "profiles_worse_goal_shortfall": int(by_profile.gt(0).sum()),
            "query_blocks_better_goal_shortfall": int(group.goal_shortfall_top20_delta_vs_control.lt(0).sum()),
            "query_blocks_total": int(len(group)),
        })
    stability_summary = pd.DataFrame(stability_summary)
    regime_switches = {
        "jump": int(regimes.daily.jump_bear_state.dropna().diff().ne(0).sum() - 1),
        "volatility": int(regimes.daily.vol_high_state.dropna().diff().ne(0).sum() - 1),
        "adwin_detections": regimes.audit["adwin_detection_count"],
    }

    # skfolio can consume a conventional multi-asset return matrix, but this
    # tournament ranks separately simulated single-stock SIPs.  A smoke check
    # records package compatibility without changing that estimand.
    from skfolio.optimization import EqualWeighted, InverseVolatility
    synthetic_returns = pd.DataFrame({
        "a": close.pct_change(fill_method=None).dropna().tail(260),
        "b": close.pct_change(fill_method=None).dropna().tail(260).shift(1),
    }).dropna()
    equal = EqualWeighted().fit(synthetic_returns)
    inverse = InverseVolatility().fit(synthetic_returns)
    skfolio_audit = {
        "api_compatible": True,
        "equal_weight_sum": float(np.sum(equal.weights_)),
        "inverse_volatility_weight_sum": float(np.sum(inverse.weights_)),
        "integrated_into_tournament": False,
        "reason": "The frozen estimand ranks independently simulated single-stock contribution plans. A shared-budget optimizer would change the estimand and needs a point-in-time, corporate-action-consistent multi-asset return and whole-share allocation layer.",
    }

    packages = {name: importlib.metadata.version(name) for name in
                ("jumpmodels", "hmmlearn", "river", "skfolio", "scikit-learn", "lightgbm", "numpy", "pandas")}
    source_provenance = {
        "jumpmodels_repository": "https://github.com/Yizhan-Oliver-Shu/jump-models",
        "jumpmodels_upstream_commit_inspected": "d0fa00ce10126791695a259a45c5ddd41fbced80",
        "jump_model_paper_doi": "10.1016/j.eswa.2020.113307",
        "continuous_jump_model_paper_doi": "10.1007/s10479-024-06035-z",
        "hmmlearn_documentation": "https://hmmlearn.readthedocs.io/en/stable/",
        "hmm_research_doi": "10.1109/5.18626",
        "gaussian_mixture_documentation": "https://scikit-learn.org/stable/modules/mixture.html",
        "gaussian_mixture_em_research_doi": "10.1111/j.2517-6161.1977.tb01600.x",
        "river_adwin_documentation": "https://riverml.xyz/0.22.0/api/drift/ADWIN/",
        "adwin_paper": "Bifet and Gavalda (2007), Learning from Time-Changing Data with Adaptive Windowing",
        "adwin_research_doi": "10.1137/1.9781611972771.42",
        "skfolio_documentation": "https://skfolio.org/",
        "skfolio_paper": "https://arxiv.org/abs/2507.04176",
        "market_source": "Yahoo Finance ^NSEI via yfinance",
    }
    input_hashes = {
        "protocol": file_sha256(protocol_path), "market_csv": file_sha256(args.market_csv),
        "training_panel": file_sha256(training_path), "validation_predictions": file_sha256(validation_path),
        "runner": file_sha256(Path(__file__)),
        "adapter": file_sha256(ROOT / "src/stock_research/open_source_regimes.py"),
        "requirements": file_sha256(ROOT / "research/specifications/open_source_regime_requirements_20260926.txt"),
    }
    leakage_audit = {
        "status": "PASS", "suffix_truncation_cutoff": leakage_cutoff,
        "snapshots_compared": int(len(actual)), "max_market_observation_lag_days": int(
            (pd.to_datetime(regimes.snapshots.decision_date) - pd.to_datetime(regimes.snapshots.market_observation_date)).dt.days.max()
        ),
        "all_market_observations_on_or_before_decision": True,
        "all_training_endpoints_strictly_before_decision": all(
            pd.Timestamp(row["latest_training_endpoint"]) < pd.Timestamp(row["decision_date"]) for row in model_audit
        ),
        "frozen_control_prediction_max_abs_error": control_max_abs,
        "frozen_control_tag_target": frozen,
    }

    predictions_keep = ["decision_date", "profile_name", "isin", "future_xirr", "future_shortfall",
                        "future_drawdown", "future_terminal_wealth", *blend_columns,
                        *[f"{name}_ranker_score" for name in challenger_features]]
    common[predictions_keep].to_csv(output / "common_predictions.csv.gz", index=False,
                                    compression={"method": "gzip", "mtime": 0})
    metrics.to_csv(output / "query_metrics.csv", index=False)
    summary.to_csv(output / "summary_metrics.csv", index=False)
    date_stability.to_csv(output / "date_stability.csv", index=False)
    profile_stability.to_csv(output / "profile_stability.csv", index=False)
    paired.to_csv(output / "paired_deltas.csv", index=False)
    stability_summary.to_csv(output / "stability_summary.csv", index=False)
    incremental_signal.to_csv(output / "incremental_signal.csv", index=False)
    turnover.to_csv(output / "turnover.csv", index=False)
    top_selections.to_csv(output / "top20_selections.csv.gz", index=False,
                          compression={"method": "gzip", "mtime": 0})
    regimes.snapshots.to_csv(output / "market_state_snapshots.csv", index=False)
    write_json(output / "model_audit.json", model_audit)
    write_json(output / "regime_audit.json", {**regimes.audit, "switches": regime_switches})
    write_json(output / "leakage_audit.json", leakage_audit)
    write_json(output / "skfolio_compatibility.json", skfolio_audit)
    write_json(output / "source_provenance.json", source_provenance)
    write_json(output / "environment.json", packages)
    write_json(output / "inputs.json", {
        "hashes": input_hashes, "source_run": str(source), "protocol_sha256": input_hashes["protocol"],
        "experiment_definition_sha256": canonical_hash(protocol), "frozen_control_commit": frozen,
        "production_ref_before": production_ref,
    })

    best = summary.sort_values(["goal_shortfall_top20", "rank_ic"], ascending=[True, False]).iloc[0]
    outcome_map = summary.set_index("candidate").to_dict("index")
    conclusion = {
        "status": "RESEARCH_ONLY",
        "selection_rule_winner": str(best.candidate),
        "winner_goal_shortfall_top20": float(best.goal_shortfall_top20),
        "winner_rank_ic": float(best.rank_ic),
        "control_goal_shortfall_top20": float(summary.loc[summary.candidate.eq("control"), "goal_shortfall_top20"].iloc[0]),
        "control_rank_ic": float(summary.loc[summary.candidate.eq("control"), "rank_ic"].iloc[0]),
        "jump_feature_splits": int(sum(item["feature_importance"].get("jump_bear_state", 0)
                                       for item in model_audit if item["candidate"] == "jump")),
        "jump_used_by_lambdarank": bool(sum(item["feature_importance"].get("jump_bear_state", 0)
                                             for item in model_audit if item["candidate"] == "jump") > 0),
        "jump_improved_primary_metric": bool(outcome_map["jump"]["goal_shortfall_delta_vs_control"] < 0),
        "river_improved_over_jump": bool(outcome_map["jump_adwin"]["goal_shortfall_top20"] < outcome_map["jump"]["goal_shortfall_top20"]),
        "candidate_outcomes": {name: {
            "goal_shortfall_top20": float(values["goal_shortfall_top20"]),
            "goal_shortfall_delta_vs_control": float(values["goal_shortfall_delta_vs_control"]),
            "rank_ic": float(values["rank_ic"]), "ndcg_at_20": float(values["ndcg_at_20"]),
            "coverage": float(values["coverage"]),
        } for name, values in outcome_map.items()},
        "river_integrated": True,
        "skfolio_integrated": False,
        "production_changed": False,
        "frozen_control_changed": False,
        "promotion": "NONE",
    }
    write_json(output / "conclusion.json", conclusion)

    artifacts = []
    for path in sorted(output.iterdir()):
        if path.name == "manifest.json" or not path.is_file():
            continue
        artifacts.append({"path": path.name, "bytes": path.stat().st_size, "sha256": file_sha256(path)})
    manifest = {
        "schema_version": "open_source_regime_challenger_manifest_v1",
        "artifacts": artifacts, "artifact_set_sha256": canonical_hash(artifacts),
        "git_branch": git("branch", "--show-current"), "base_commit": git("merge-base", "HEAD", frozen),
        "frozen_control_commit": frozen, "production_ref_after": git("rev-parse", "professor-railway-deploy-20260920"),
    }
    if manifest["production_ref_after"] != production_ref:
        raise RuntimeError("production ref changed during research run")
    write_json(output / "manifest.json", manifest)
    print(json.dumps({"output": str(output), "winner": best.candidate,
                      "goal_shortfall": best.goal_shortfall_top20,
                      "control_goal_shortfall": conclusion["control_goal_shortfall_top20"],
                      "control_max_abs_error": control_max_abs}, indent=2))


if __name__ == "__main__":
    main()
