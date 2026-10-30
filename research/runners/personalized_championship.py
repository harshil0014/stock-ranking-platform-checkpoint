"""Staged, maturity-purged Personalized championship; research outputs only."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[name] = "1"

import lightgbm as lgb
import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from research.runners import personalized_history_challenger as h

PROTOCOL = ROOT / "research/protocols/personalized_championship_v1.json"
OUTPUT = ROOT / "experiments/personalized-championship/v1"
CORE = list(h.ORIGINAL_FEATURES)
AGE = ["history_months", "history_start_cagr", "cagr_5y_observed"]
HIGH = ["days_since_recorded_high", "distance_from_recorded_high", "distance_from_52w_high"]
DRAWDOWN = ["full_history_max_drawdown", "current_drawdown_duration_days",
            "max_drawdown_duration_days", "recovery_from_worst_trough"]
VOL = ["realized_volatility_1y", "downside_volatility_1y"]
RECIPES = {
    "proxy_age": CORE + AGE,
    "high_core": CORE + AGE + HIGH,
    "drawdown_core": CORE + AGE + DRAWDOWN,
    "high_drawdown": CORE + AGE + HIGH + DRAWDOWN,
    "high_vol": CORE + AGE + HIGH + VOL,
    "full_risk": CORE + AGE + HIGH + DRAWDOWN + VOL,
    "no_growth": [x for x in CORE if x not in ("cagr_3y", "cagr_5y")] + AGE + HIGH + DRAWDOWN,
    "no_goal_in_ranker": [x for x in CORE if x != "enhanced_goal_score"] + AGE + HIGH + DRAWDOWN,
}
LABELS = ("xirr4", "xirr8", "utility4")
BASE_PARAMS = dict(n_estimators=60, learning_rate=.05, num_leaves=7, max_depth=3,
                   min_child_samples=80, reg_lambda=10, lambdarank_truncation_level=30)


def outcome_labels(frame, mode):
    grouped = frame.groupby(["decision_date", "profile_name"], sort=False)
    pct_xirr = grouped.future_xirr.rank(pct=True)
    if mode == "xirr4":
        value, levels = pct_xirr, 4
    elif mode == "xirr8":
        value, levels = pct_xirr, 8
    elif mode == "utility4":
        # Percentile ranks bound extreme XIRRs. Goal success resolves most
        # ties; within equal shortfall, return order still matters.
        pct_shortfall = grouped.future_shortfall.rank(pct=True, ascending=False)
        value, levels = .55 * pct_xirr + .45 * pct_shortfall, 4
    else:
        raise ValueError(mode)
    return np.minimum((value * levels).astype(int), levels - 1)


def fit_predict(training, target, columns, family, mode, params, seed):
    train = training.loc[training.future_xirr.notna() & training.future_shortfall.notna()
                         & training.enhanced_carry_xirr_score.notna()].sort_values(
        ["decision_date", "profile_name", "isin"], kind="stable")
    valid = target.enhanced_carry_xirr_score.notna()
    output = pd.Series(np.nan, index=target.index)
    if family == "lgbm":
        labels = outcome_labels(train, mode)
        sizes = train.groupby(["decision_date", "profile_name"], sort=False).size().to_list()
        model = lgb.LGBMRanker(objective="lambdarank", random_state=seed, n_jobs=1,
            verbosity=-1, deterministic=True, force_col_wise=True, **params)
        model.fit(train[columns], labels, group=sizes)
        output.loc[valid] = model.predict(target.loc[valid, columns])
    else:
        # Robust percentile targets stop extreme annualized returns from
        # controlling regression models.
        y = train.groupby(["decision_date", "profile_name"]).future_xirr.rank(pct=True)
        if family == "ridge":
            model = make_pipeline(SimpleImputer(strategy="median", add_indicator=True),
                                  StandardScaler(), Ridge(alpha=100))
        elif family == "hist":
            model = make_pipeline(SimpleImputer(strategy="median"),
                HistGradientBoostingRegressor(max_iter=100, learning_rate=.04,
                    max_leaf_nodes=7, min_samples_leaf=120, l2_regularization=15, random_state=seed))
        else:
            raise ValueError(family)
        model.fit(train[columns], y)
        output.loc[valid] = model.predict(target.loc[valid, columns])
    return output, model


def prepared_panels():
    raw = h.load_panels()
    facts = h.load_company_fact_snapshot(h.resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    features = h.history_features(raw, facts)
    # Sector-relative features are never used for finalist selection because
    # accepted current sector labels are not guaranteed to be historical PIT.
    augmented = {name: h.attach(frame, features) for name, frame in raw.items()}
    return raw, augmented, features, facts


def mature_before(panel, date):
    subset = panel.loc[pd.to_datetime(panel.endpoint).lt(pd.Timestamp(date))]
    if subset.empty or pd.to_datetime(subset.endpoint).max() >= pd.Timestamp(date):
        raise ValueError(f"maturity-purged training unavailable at {date}")
    return subset


def score_fold(frame, model_score, weight):
    frame = frame.copy()
    frame["candidate_score"] = h.blend(frame, model_score, weight)
    return h.evaluate(frame, "candidate_score")


def utility(summary, base):
    # Relative changes use stable denominators and cap mean-return influence.
    return (2.0 * (base["target_shortfall_top20"] - summary["target_shortfall_top20"])
        + 1.5 * (summary["target_achievement_top20"] - base["target_achievement_top20"])
        + .8 * (summary["median_xirr_top20"] - base["median_xirr_top20"])
        + .8 * (summary["ndcg20"] - base["ndcg20"])
        + .5 * (summary["pairwise_accuracy"] - base["pairwise_accuracy"])
        + .35 * (summary["rank_ic"] - base["rank_ic"])
        + .4 * (summary["mean_asset_drawdown_top20"] - base["mean_asset_drawdown_top20"]))


def evaluate_candidate(candidate, dates, augmented, params, weights, seed):
    family, recipe, mode = candidate
    history = pd.concat([augmented["training_panel"], augmented["validation_predictions"]], ignore_index=True)
    outcomes = []
    predictions = []
    for day in dates:
        target = history.loc[history.decision_date.eq(day)].copy()
        train = mature_before(history, day)
        pred, _ = fit_predict(train, target, RECIPES[recipe], family, mode, params, seed)
        target["model_score"] = pred
        predictions.append(target)
    frame = pd.concat(predictions, ignore_index=True)
    for weight in weights:
        measures = score_fold(frame, "model_score", weight)
        measures["candidate"], measures["goal_weight"] = "|".join(candidate), weight
        outcomes.append(measures)
    return pd.concat(outcomes, ignore_index=True), frame


def baseline_on_dates(raw, dates, seed):
    history = pd.concat([raw["training_panel"], raw["validation_predictions"]], ignore_index=True)
    result = []
    for day in dates:
        target = history.loc[history.decision_date.eq(day)].copy()
        train = mature_before(history, day)
        pred, _ = fit_predict(train, target, CORE, "lgbm", "xirr4", BASE_PARAMS, seed)
        target["old_lambda"] = pred
        target["champion_score"] = h.blend(target, "old_lambda", .67)
        result.append(target)
    return pd.concat(result, ignore_index=True)


def summarize_measures(frame):
    return frame[h.METRICS].mean().to_dict()


def rank_frontier(table, baseline):
    directions = {"ndcg20": 1, "rank_ic": 1, "pairwise_accuracy": 1,
                  "target_achievement_top20": 1, "target_shortfall_top20": -1,
                  "median_xirr_top20": 1, "mean_asset_drawdown_top20": 1, "coverage": 1}
    points = table[list(directions)].to_numpy(float) * np.array(list(directions.values()))
    nondominated = []
    for i, point in enumerate(points):
        nondominated.append(not np.any(np.all(points >= point - 1e-12, axis=1)
            & np.any(points > point + 1e-12, axis=1)))
    table = table.copy()
    table["pareto_frontier"] = nondominated
    table["utility_vs_champion"] = [utility(row, baseline) for _, row in table.iterrows()]
    return table


def run(output: Path, audit_ticker: str):
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(PROTOCOL.read_text())
    seed = int(protocol["seed"])
    raw, augmented, features, facts = prepared_panels()
    features.to_csv(output / "history_features.csv.gz", index=False)
    (output / "protocol.json").write_bytes(PROTOCOL.read_bytes())
    qualification_dates = protocol["qualification_dates"]
    development_dates = protocol["development_dates"]
    baseline_qual = baseline_on_dates(raw, qualification_dates, seed)
    baseline_qual_metrics = h.evaluate(baseline_qual, "champion_score")
    qual_base = summarize_measures(baseline_qual_metrics)
    candidates = [("lgbm", recipe, mode) for recipe in RECIPES for mode in LABELS]
    candidates += [(family, recipe, "percentile") for family in ("ridge", "hist")
                   for recipe in ("proxy_age", "high_drawdown", "full_risk")]
    round1 = []
    for candidate in candidates:
        measures, _ = evaluate_candidate(candidate, qualification_dates, augmented,
                                         BASE_PARAMS, [.67], seed)
        summary = summarize_measures(measures)
        round1.append({"candidate": "|".join(candidate), **summary,
                       "utility_vs_champion": utility(summary, qual_base),
                       "worst_date_shortfall_delta": max(
                           measures.groupby("decision_date").target_shortfall_top20.mean()
                           - baseline_qual_metrics.groupby("decision_date").target_shortfall_top20.mean())})
        print("round1", "|".join(candidate), flush=True)
    round1 = pd.DataFrame(round1).sort_values("utility_vs_champion", ascending=False)
    round1.to_csv(output / "round1_leaderboard.csv", index=False)
    # Advance broad families on qualification only; retain the strongest
    # history/high, duration, and full-risk recipe even when one is not top 6.
    advanced = list(round1.head(6).candidate)
    for token in ("high_core", "high_drawdown", "full_risk"):
        item = round1.loc[round1.candidate.str.contains("\\|" + token + "\\|", regex=True)].iloc[0].candidate
        if item not in advanced:
            advanced.append(item)
    (output / "round1_eliminations.json").write_text(json.dumps({
        "advanced": advanced,
        "eliminated": [{"candidate": row.candidate,
                        "reason": "Lower qualification utility or larger worst-date shortfall than advancing families"}
                       for row in round1.itertuples() if row.candidate not in advanced]}, indent=2))
    # Exact original chronological predictions on the 2023 dates anchor the
    # champion; reconstructed fit is checked separately for agreement.
    base_dev = raw["validation_predictions"].copy()
    base_dev["champion_score"] = h.blend(base_dev, "lightgbm_lambdarank_score", .67)
    base_dev_metrics = h.evaluate(base_dev, "champion_score")
    dev_base = summarize_measures(base_dev_metrics)
    round2_rows = []
    finalist_predictions = {}
    for key in advanced:
        candidate = tuple(key.split("|"))
        for param_name, params in protocol["round2_parameter_sets"].items():
            if candidate[0] != "lgbm" and param_name != "frozen":
                continue
            measures, frame = evaluate_candidate(candidate, development_dates, augmented,
                params, protocol["round2_goal_weights"], seed)
            for weight, block in measures.groupby("goal_weight"):
                summary = summarize_measures(block)
                by_profile = block.groupby("profile").mean(numeric_only=True)
                base_profile = base_dev_metrics.groupby("profile").mean(numeric_only=True)
                shortfall_delta = by_profile.target_shortfall_top20 - base_profile.target_shortfall_top20
                achievement_delta = by_profile.target_achievement_top20 - base_profile.target_achievement_top20
                round2_rows.append({"candidate": key, "params": param_name, "goal_weight": weight,
                    **summary, "utility_vs_champion": utility(summary, dev_base),
                    "worst_profile_shortfall_delta": shortfall_delta.max(),
                    "worst_profile_achievement_delta": achievement_delta.min(),
                    "profile_shortfall_regressions": int(shortfall_delta.gt(.01).sum())})
            finalist_predictions[(key, param_name)] = frame
        print("round2", key, flush=True)
    round2 = pd.DataFrame(round2_rows)
    round2["eligible"] = (round2.coverage >= dev_base["coverage"] - .001) & (
        round2.worst_profile_shortfall_delta <= .02) & (round2.worst_profile_achievement_delta >= -.15)
    round2 = rank_frontier(round2, dev_base).sort_values(
        ["eligible", "utility_vs_champion"], ascending=[False, False])
    round2.to_csv(output / "round2_leaderboard.csv", index=False)
    # Keep three distinct contenders, not three weights of one fitted model.
    finalists = round2.loc[round2.eligible].drop_duplicates("candidate").head(3)
    if finalists.empty:
        finalists = round2.drop_duplicates("candidate").head(3)
    finalists.to_csv(output / "finalists.csv", index=False)
    # A single diagnostic evaluation of the already exposed 2025 dates follows
    # all candidate and parameter choices.
    exposed = raw["supplementary_predictions"].copy()
    exposed["champion_score"] = h.blend(exposed, "lightgbm_lambdarank_score", .67)
    exposed_base_metrics = h.evaluate(exposed, "champion_score")
    final_blocks, date_blocks, profile_blocks = [], [], []
    for row in finalists.itertuples():
        candidate = tuple(row.candidate.split("|"))
        params = protocol["round2_parameter_sets"][row.params]
        weight = float(row.goal_weight)
        development = finalist_predictions[(row.candidate, row.params)].copy()
        development["candidate_score"] = h.blend(development, "model_score", weight)
        for part, target in (("development", development), ("exposed", exposed.copy())):
            if part == "exposed":
                history = pd.concat([augmented["training_panel"], augmented["validation_predictions"],
                                     augmented["supplementary_predictions"]], ignore_index=True)
                target = augmented["supplementary_predictions"].copy()
                target["model_score"] = np.nan
                for day, group in target.groupby("decision_date"):
                    pred, _ = fit_predict(mature_before(history, day), group, RECIPES[candidate[1]],
                        candidate[0], candidate[2], params, seed)
                    target.loc[group.index, "model_score"] = pred
                target["candidate_score"] = h.blend(target, "model_score", weight)
            old = base_dev_metrics if part == "development" else exposed_base_metrics
            new = h.evaluate(target, "candidate_score")
            joined = old.merge(new, on=["decision_date", "profile"], suffixes=("_champion", "_challenger"))
            joined.insert(0, "candidate", row.candidate)
            joined.insert(1, "params", row.params)
            joined.insert(2, "goal_weight", weight)
            joined.insert(3, "partition", part)
            final_blocks.append(joined)
            for metric in h.METRICS:
                date_means = joined.groupby("decision_date")[[metric + "_champion", metric + "_challenger"]].mean()
                for day, values in date_means.iterrows():
                    date_blocks.append({"candidate": row.candidate, "params": row.params,
                        "goal_weight": weight, "partition": part, "decision_date": day,
                        "metric": metric, "champion": values.iloc[0], "challenger": values.iloc[1],
                        "delta": values.iloc[1] - values.iloc[0]})
            profile_blocks.append(joined)
    all_blocks = pd.concat(final_blocks, ignore_index=True)
    all_blocks.to_csv(output / "finalist_profile_blocks.csv", index=False)
    pd.DataFrame(date_blocks).to_csv(output / "finalist_date_metrics.csv", index=False)
    summary = []
    for (name, params, weight, part), group in all_blocks.groupby(
            ["candidate", "params", "goal_weight", "partition"]):
        for metric in h.METRICS:
            old, new = group[metric + "_champion"].mean(), group[metric + "_challenger"].mean()
            summary.append({"candidate": name, "params": params, "goal_weight": weight,
                            "partition": part, "metric": metric, "champion": old,
                            "challenger": new, "delta": new - old})
    pd.DataFrame(summary).to_csv(output / "championship_scoreboard.csv", index=False)
    # Current rankings for each finalist use the sealed champion input rows.
    frozen = pd.read_csv(h.FREEZE / "rankings.csv.gz", low_memory=False)
    current = h.attach(frozen, features)
    history = pd.concat([augmented["training_panel"], augmented["validation_predictions"],
                         augmented["supplementary_predictions"]], ignore_index=True)
    current_rows = []
    for row in finalists.itertuples():
        candidate = tuple(row.candidate.split("|"))
        pred, model = fit_predict(mature_before(history, protocol["current_date"]), current,
            RECIPES[candidate[1]], candidate[0], candidate[2],
            protocol["round2_parameter_sets"][row.params], seed)
        frame = current.copy()
        frame["model_score"] = pred
        frame["candidate_score"] = h.blend(frame, "model_score", float(row.goal_weight))
        frame["candidate"], frame["params"] = row.candidate, row.params
        frame["goal_weight"] = row.goal_weight
        current_rows.append(frame)
        if candidate[0] == "lgbm":
            model_path = output / ("model_" + sha256(f"{row.candidate}|{row.params}|{row.goal_weight}".encode()).hexdigest()[:12] + ".txt")
            model_path.write_bytes(model.booster_.model_to_string().encode())
    current_all = pd.concat(current_rows, ignore_index=True)
    current_all.to_csv(output / "current_finalists.csv.gz", index=False)
    # Exact frozen score reproduction is independent of the historical model.
    ranks = frozen.groupby("profile_name")[["enhanced_goal_score", "lightgbm_lambdarank_score"]].rank(pct=True)
    frozen_error = (frozen.selected_ensemble_score - (.67 * ranks.iloc[:, 0] + .33 * ranks.iloc[:, 1])).abs().max()
    audit = {"frozen_score_max_error": float(frozen_error),
        "qualification_dates": qualification_dates, "development_dates": development_dates,
        "contaminated_dates": protocol["contaminated_diagnostic_dates"],
        "genuinely_untouched_dates": [], "audit_ticker": audit_ticker,
        "source_hashes": {str(path.relative_to(ROOT)): sha256(path.read_bytes()).hexdigest() for path in
            [PROTOCOL, h.SOURCE / "training_panel.csv.gz", h.SOURCE / "validation_predictions.csv.gz",
             h.SOURCE / "supplementary_predictions.csv.gz", h.FREEZE / "rankings.csv.gz"]}}
    (output / "audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--audit-ticker", required=True)
    arguments = parser.parse_args()
    run(arguments.output, arguments.audit_ticker)
