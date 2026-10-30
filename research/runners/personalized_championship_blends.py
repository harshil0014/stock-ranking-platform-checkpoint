"""Conservative Goal/LambdaRank blends selected without exposed 2025 outcomes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import numpy as np
import pandas as pd

from research.runners import personalized_championship as c
from research.runners import personalized_history_challenger as h

FAMILIES = [
    ("lgbm", "high_core", "xirr8", "frozen"),
    ("lgbm", "drawdown_core", "xirr8", "regularized"),
    ("lgbm", "drawdown_core", "utility4", "top20"),
]
GOAL_WEIGHTS = (.63, .67, .70, .73)
NEW_RANKER_WEIGHTS = (.10, .20, .30, .40, .50)


def make_scores(frame, goal_weight, new_weight):
    query = frame.groupby(["decision_date", "profile_name"])
    goal = query.enhanced_goal_score.rank(pct=True)
    old = query.lightgbm_lambdarank_score.rank(pct=True)
    new = query.new_lambda.rank(pct=True)
    return goal_weight * goal + (1 - goal_weight) * ((1 - new_weight) * old + new_weight * new)


def fit_family(raw, augmented, family, recipe, mode, params_name, dates, protocol, current=False):
    history = pd.concat([augmented["training_panel"], augmented["validation_predictions"],
                         augmented["supplementary_predictions"]], ignore_index=True)
    output = []
    for day in dates:
        if current:
            target = h.attach(pd.read_csv(h.FREEZE / "rankings.csv.gz"),
                              pd.read_csv(protocol["feature_path"]))
        else:
            panel_name = "supplementary_predictions" if day.startswith("2025") else "validation_predictions"
            target = augmented[panel_name].loc[augmented[panel_name].decision_date.eq(day)].copy()
        pred, _ = c.fit_predict(c.mature_before(history, day), target, c.RECIPES[recipe],
            family, mode, protocol["round2_parameter_sets"][params_name], int(protocol["seed"]))
        target["new_lambda"] = pred
        output.append(target)
    return pd.concat(output, ignore_index=True)


def run(championship, output):
    output.mkdir(parents=True, exist_ok=False)
    protocol = json.loads(c.PROTOCOL.read_text())
    protocol["feature_path"] = str(championship / "history_features.csv.gz")
    raw = h.load_panels()
    features = pd.read_csv(protocol["feature_path"])
    augmented = {name: h.attach(panel, features) for name, panel in raw.items()}
    rows, predictions = [], {}
    base = raw["validation_predictions"].copy()
    base["champion_score"] = h.blend(base, "lightgbm_lambdarank_score", .67)
    base_metrics = h.evaluate(base, "champion_score")
    base_profile = base_metrics.groupby("profile").mean(numeric_only=True)
    for family in FAMILIES:
        name = "|".join(family)
        frame = fit_family(raw, augmented, *family, protocol["development_dates"], protocol)
        predictions[name] = frame
        for goal in GOAL_WEIGHTS:
            for alpha in NEW_RANKER_WEIGHTS:
                frame["challenger_score"] = make_scores(frame, goal, alpha)
                metric = h.evaluate(frame, "challenger_score")
                summary = c.summarize_measures(metric)
                profile = metric.groupby("profile").mean(numeric_only=True)
                rows.append({"family": name, "goal_weight": goal, "new_ranker_weight": alpha,
                    **summary, "utility_vs_champion": c.utility(summary, c.summarize_measures(base_metrics)),
                    "worst_profile_shortfall_delta": (profile.target_shortfall_top20 - base_profile.target_shortfall_top20).max(),
                    "worst_profile_achievement_delta": (profile.target_achievement_top20 - base_profile.target_achievement_top20).min()})
        print("development", name, flush=True)
    leaderboard = pd.DataFrame(rows)
    leaderboard["profile_guard"] = (leaderboard.worst_profile_shortfall_delta <= .01) & (
        leaderboard.worst_profile_achievement_delta >= -.10)
    leaderboard = c.rank_frontier(leaderboard, c.summarize_measures(base_metrics))
    leaderboard.sort_values(["profile_guard", "utility_vs_champion"], ascending=[False, False]).to_csv(
        output / "development_leaderboard.csv", index=False)
    # Select by 2023 alone. The exposed period is scored once for the top
    # guarded candidate and the highest-NDCG contender on the Pareto frontier.
    guarded = leaderboard.loc[leaderboard.profile_guard]
    best = guarded.sort_values("utility_vs_champion", ascending=False).iloc[0] if len(guarded) else leaderboard.sort_values(
        "utility_vs_champion", ascending=False).iloc[0]
    ndcg = leaderboard.loc[leaderboard.pareto_frontier].sort_values("ndcg20", ascending=False).iloc[0]
    conservative_high = leaderboard.loc[(leaderboard.family.eq("lgbm|high_core|xirr8|frozen"))
        & (leaderboard.goal_weight.eq(.70)) & (leaderboard.new_ranker_weight.eq(.10))].iloc[0]
    finalists = pd.DataFrame([best, ndcg, conservative_high]).drop_duplicates(
        ["family", "goal_weight", "new_ranker_weight"])
    finalists.to_csv(output / "finalists.csv", index=False)
    comparisons, profile_rows, current_rows = [], [], []
    for row in finalists.itertuples():
        family = tuple(row.family.split("|"))
        for part, dates in (("development", protocol["development_dates"]),
                            ("exposed", protocol["contaminated_diagnostic_dates"])):
            frame = predictions[row.family].copy() if part == "development" else fit_family(
                raw, augmented, *family, dates, protocol)
            frame["challenger_score"] = make_scores(frame, row.goal_weight, row.new_ranker_weight)
            frame["champion_score"] = h.blend(frame, "lightgbm_lambdarank_score", .67)
            old, new = h.evaluate(frame, "champion_score"), h.evaluate(frame, "challenger_score")
            joined = old.merge(new, on=["decision_date", "profile"], suffixes=("_champion", "_challenger"))
            joined.insert(0, "partition", part)
            joined.insert(0, "family", row.family)
            joined.insert(2, "goal_weight", row.goal_weight)
            joined.insert(3, "new_ranker_weight", row.new_ranker_weight)
            profile_rows.append(joined)
            for metric in h.METRICS:
                comparisons.append({"family": row.family, "goal_weight": row.goal_weight,
                    "new_ranker_weight": row.new_ranker_weight, "partition": part, "metric": metric,
                    "champion": old[metric].mean(), "challenger": new[metric].mean(),
                    "delta": new[metric].mean() - old[metric].mean()})
        current = fit_family(raw, augmented, *family, ["2026-09-18"], protocol, current=True)
        current["challenger_score"] = make_scores(current, row.goal_weight, row.new_ranker_weight)
        base_current = current.loc[current.profile_name.eq("base7500")].dropna(subset=["challenger_score"])
        ranked = base_current.sort_values(["challenger_score", "isin"], ascending=[False, True])
        current_rows.append({"family": row.family, "goal_weight": row.goal_weight,
            "new_ranker_weight": row.new_ranker_weight,
            "universe_short_history_share": base_current.cagr_5y_observed.ne(1).mean(),
            **{f"top{n}_short_history_share": ranked.head(n).cagr_5y_observed.ne(1).mean()
               for n in (20, 50, 100)}})
    pd.DataFrame(comparisons).to_csv(output / "champion_vs_blends.csv", index=False)
    pd.concat(profile_rows).to_csv(output / "profile_blocks.csv", index=False)
    pd.DataFrame(current_rows).to_csv(output / "current_short_history.csv", index=False)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--championship", type=Path, default=c.OUTPUT)
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/personalized-championship/blends-v1")
    args = parser.parse_args()
    run(args.championship, args.output)
