"""Research-only successor tournament. 2025 is an exposed diagnostic, never selection.

The authoritative v3 enrichment supplies every current-date history field. Earlier
date features are recomputed from adjusted histories cut at each decision date;
the four RAW_RISK_ONLY histories are never admitted to return features.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import numpy as np
import pandas as pd
from research.runners import personalized_championship as championship
from research.runners import personalized_history_challenger as hist

OUT = ROOT / "experiments/personalized-successor-20261002/v3"
V3 = ROOT / "experiments/history-enrichment-20261002/final-data-quality-v3/history_enrichment.csv.gz"
HISTORIC = ROOT / "experiments/personalized-championship/v1/history_features.csv.gz"
SEED = 20261002
CORE = list(hist.ORIGINAL_FEATURES)
AGE = ["history_months", "history_start_cagr", "cagr_5y_observed"]
HIGH = ["days_since_recorded_high", "distance_from_recorded_high", "distance_from_52w_high"]
UNDERWATER = ["full_history_max_drawdown", "current_drawdown_duration_days", "max_drawdown_duration_days", "recovery_from_worst_trough"]
VOL = ["realized_volatility_1y", "downside_volatility_1y"]
RECIPES = {
    "high_underwater": CORE + AGE + HIGH + UNDERWATER,
    "full_risk": CORE + AGE + HIGH + UNDERWATER + VOL,
    "risk_no_3y": [c for c in CORE if c != "cagr_3y"] + AGE + HIGH + UNDERWATER + VOL,
    "risk_no_goal": [c for c in CORE if c != "enhanced_goal_score"] + AGE + HIGH + UNDERWATER + VOL,
    "duration_only": CORE + AGE + UNDERWATER,
}
PARAMS = {
    "shallow": dict(n_estimators=80, learning_rate=.04, num_leaves=7, max_depth=3,
                    min_child_samples=120, reg_lambda=15, lambdarank_truncation_level=25),
    "regularized": dict(n_estimators=100, learning_rate=.03, num_leaves=5, max_depth=3,
                        min_child_samples=160, reg_lambda=20, lambdarank_truncation_level=40),
}
METRICS = hist.METRICS


def summarize(frame, score):
    return hist.evaluate(frame, score)


def qualify(new, old):
    m = new[METRICS].mean(); b = old[METRICS].mean()
    delta = m - b
    joined = old.merge(new, on=["decision_date", "profile"], suffixes=("_old", "_new"))
    by_profile = joined.groupby("profile").mean(numeric_only=True)
    worst_shortfall = (by_profile.target_shortfall_top20_new - by_profile.target_shortfall_top20_old).max()
    worst_achievement = (by_profile.target_achievement_top20_new - by_profile.target_achievement_top20_old).min()
    # Extreme mean XIRRs receive no selection weight.
    utility = (2.0 * -delta.target_shortfall_top20 + 1.5 * delta.target_achievement_top20
               + .8 * delta.median_xirr_top20 + .8 * delta.ndcg20
               + .5 * delta.pairwise_accuracy + .35 * delta.rank_ic
               + .4 * delta.mean_asset_drawdown_top20)
    eligible = bool(delta.coverage >= -.001 and delta.target_shortfall_top20 <= .005
                    and delta.mean_asset_drawdown_top20 >= -.01
                    and worst_shortfall <= .02 and worst_achievement >= -.15)
    return {**{f"delta_{k}": float(v) for k, v in delta.items()},
            "worst_profile_shortfall_delta": float(worst_shortfall),
            "worst_profile_achievement_delta": float(worst_achievement),
            "utility": float(utility), "eligible": eligible}


def current_features(v3):
    if len(v3) != 4436 or v3["isin"].duplicated().any():
        raise ValueError("authoritative v3 identity coverage mismatch")
    if not (v3.loc[v3.history_quality.eq("RAW_RISK_ONLY"), "strict_cagr_5y"].isna().all()
            and v3.loc[v3.history_quality.eq("RAW_RISK_ONLY"), "long_term_growth_is_observed"].eq(False).all()):
        raise ValueError("RAW_RISK_ONLY provenance breached")
    selected = v3[["isin", "history_quality", "long_term_growth_source", "long_term_growth_value",
                   "history_months", "history_start_cagr", "cagr_5y_observed", *HIGH, *UNDERWATER,
                   "realized_volatility_1y_value", "downside_volatility_1y_value"]].copy()
    selected = selected.rename(columns={"long_term_growth_value": "cagr_5y",
                                "realized_volatility_1y_value": "realized_volatility_1y",
                                "downside_volatility_1y_value": "downside_volatility_1y"})
    selected["cagr_5y_source"] = selected.long_term_growth_source
    selected["decision_date"] = "2026-09-18"
    return selected


def prepare():
    raw = hist.load_panels()
    features = pd.read_csv(HISTORIC, low_memory=False).rename(
        columns={"since_listing_cagr": "history_start_cagr"})
    # Historic archive was computed from adjusted cache plus validated recovery
    # overlay with date truncation. It is not a 2026 feature backfill.
    features = features.loc[features.decision_date.lt("2026-09-18")].copy()
    # Historical sector labels in the archive came from the current company
    # snapshot. They are diagnostic only, so replace the old sector-shrunk
    # proxy with a contemporaneous global observed-5Y shrinkage estimate.
    observed = features.cagr_5y_observed.eq(1)
    global_median = features.loc[observed].groupby("decision_date").observed_cagr_5y.median()
    anchor = features.decision_date.map(global_median).fillna(0).clip(-.5, .5)
    weight = features.history_months.div(60).clip(0, 1)
    proxy = weight * features.history_start_cagr.clip(-.75, 1).fillna(0) + (1-weight) * anchor
    features.loc[~observed, "cagr_5y"] = proxy.loc[~observed]
    features.loc[~observed, "cagr_5y_source"] = "ESTIMATED_HISTORY_GLOBAL_SHRUNK"
    panels = {name: hist.attach(frame, features) for name, frame in raw.items()
              if name != "current_profile_rankings"}
    v3 = pd.read_csv(V3, low_memory=False)
    frozen = pd.read_csv(hist.FREEZE / "rankings.csv.gz", low_memory=False)
    current = frozen.drop(columns=["cagr_5y"]).merge(current_features(v3), on=["isin", "decision_date"],
                    how="left", validate="many_to_one")
    if current.cagr_5y.isna().any() or current.history_months.isna().any():
        raise ValueError("current v3 feature coverage mismatch")
    return raw, panels, current, v3, frozen


def predict_dates(panels, part, columns, label, params):
    history = pd.concat([panels["training_panel"], panels["validation_predictions"],
                         panels["supplementary_predictions"]], ignore_index=True)
    target = panels[part].copy(); target["model_score"] = np.nan
    for date, group in target.groupby("decision_date"):
        train = history.loc[pd.to_datetime(history.endpoint).lt(pd.Timestamp(date))]
        pred, _ = championship.fit_predict(train, group, columns, "lgbm", label, params, SEED)
        target.loc[group.index, "model_score"] = pred
    return target


def baseline(frame):
    frame = frame.copy()
    frame["champion_score"] = hist.blend(frame, "lightgbm_lambdarank_score", .67)
    return frame


def current_audit(frame, v3):
    base = frame.loc[frame.profile_name.eq("base7500")].copy()
    base = base.merge(v3[["isin", "ticker", "sector", "cagr_5y_observed"]], on="isin", how="left",
                      suffixes=("", "_v3"))
    flag = "cagr_5y_observed_v3" if "cagr_5y_observed_v3" in base else "cagr_5y_observed"
    out = {}
    for label, score in (("champion", "selected_ensemble_score"), ("challenger", "candidate_score")):
        ranked = base.dropna(subset=[score]).sort_values([score, "isin"], ascending=[False, True]).copy()
        ranked["rank"] = np.arange(1, len(ranked) + 1)
        nykaa = ranked.loc[ranked.ticker.eq("NYKAA")]
        retail = ranked.loc[ranked.sector.eq("Retailing")].copy()
        out[label] = {"scored": len(ranked), "universe_missing_true_5y": float(ranked[flag].ne(1).mean()),
                      "top20_missing_true_5y": float(ranked[flag].head(20).ne(1).mean()),
                      "top50_missing_true_5y": float(ranked[flag].head(50).ne(1).mean()),
                      "top100_missing_true_5y": float(ranked[flag].head(100).ne(1).mean()),
                      "nykaa_rank": int(nykaa["rank"].iloc[0]),
                      "nykaa_sector_rank": int(np.flatnonzero(retail.ticker.eq("NYKAA"))[0] + 1),
                      "nykaa_score": float(nykaa[score].iloc[0]),
                      "retailing_top10": retail.ticker.head(10).tolist(),
                      "top20_isins": ranked["isin"].head(20).tolist()}
    return out


def run():
    OUT.mkdir(parents=True, exist_ok=True)
    if any(OUT.iterdir()):
        raise ValueError("output directory must be empty")
    raw, panels, current, v3, frozen = prepare()
    base_dev = baseline(panels["validation_predictions"])
    old_dev = summarize(base_dev, "champion_score")
    rows, stored = [], {}
    for recipe, columns in RECIPES.items():
        for label in ("xirr4", "utility4"):
            for pname, params in PARAMS.items():
                key = f"{recipe}|{label}|{pname}"
                frame = predict_dates(panels, "validation_predictions", columns, label, params)
                stored[key] = frame[["isin", "profile_name", "decision_date", "model_score"]]
                for weight in (.60, .67, .73):
                    frame["candidate_score"] = hist.blend(frame, "model_score", weight)
                    q = qualify(summarize(frame, "candidate_score"), old_dev)
                    rows.append({"candidate": key, "goal_weight": weight, **q})
                print("development", key, flush=True)
    leaderboard = pd.DataFrame(rows).sort_values(["eligible", "utility"], ascending=[False, False])
    leaderboard.to_csv(OUT / "development_tournament.csv", index=False)
    # Restrained blends are evaluated only for the top distinct development fits.
    advanced = leaderboard.drop_duplicates("candidate").head(3)
    for record in advanced.itertuples():
        key = record.candidate
        frame = base_dev.merge(stored[key], on=["isin", "profile_name", "decision_date"], validate="one_to_one")
        goal = frame.groupby(["decision_date", "profile_name"]).enhanced_goal_score.rank(pct=True)
        new_rank = frame.groupby(["decision_date", "profile_name"]).model_score.rank(pct=True)
        age = (1 - frame.history_months.fillna(0).div(60).clip(0, 1)) * frame.cagr_5y_observed.ne(1)
        for alpha in (.35, .60, .85):
            for penalty in (0, .15, .30):
                frame["candidate_score"] = ((1-alpha) * frame.champion_score +
                    alpha * (.67 * goal + .33 * new_rank) - penalty * age)
                q = qualify(summarize(frame, "candidate_score"), old_dev)
                rows.append({"candidate": key, "goal_weight": .67, "alpha": alpha,
                             "age_penalty": penalty, **q})
    leaderboard = pd.DataFrame(rows).sort_values(["eligible", "utility"], ascending=[False, False])
    leaderboard.to_csv(OUT / "development_tournament.csv", index=False)
    winners = leaderboard.drop_duplicates("candidate").head(3)
    diagnostics = []
    base_exp = baseline(raw["supplementary_predictions"])
    old_exp = summarize(base_exp, "champion_score")
    for record in winners.itertuples():
        recipe, label, pname = record.candidate.split("|")
        exp = predict_dates(panels, "supplementary_predictions", RECIPES[recipe], label, PARAMS[pname])
        exp["champion_score"] = base_exp.champion_score
        if pd.isna(record.alpha):
            exp["candidate_score"] = hist.blend(exp, "model_score", record.goal_weight)
        else:
            goal = exp.groupby(["decision_date", "profile_name"]).enhanced_goal_score.rank(pct=True)
            new_rank = exp.groupby(["decision_date", "profile_name"]).model_score.rank(pct=True)
            age = (1 - exp.history_months.fillna(0).div(60).clip(0, 1)) * exp.cagr_5y_observed.ne(1)
            exp["candidate_score"] = ((1-record.alpha)*exp.champion_score +
                record.alpha*(.67*goal+.33*new_rank) - record.age_penalty*age)
        new_exp = summarize(exp, "candidate_score")
        joined = old_exp.merge(new_exp, on=["decision_date", "profile"], suffixes=("_champion", "_challenger"))
        joined.insert(0, "candidate", record.candidate)
        diagnostics.append(joined)
        print("exposed diagnostic", record.candidate, flush=True)
    pd.concat(diagnostics).to_csv(OUT / "exposed_finalist_profiles.csv", index=False)
    winner = winners.iloc[0]
    recipe, label, pname = winner.candidate.split("|")
    history = pd.concat([panels["training_panel"], panels["validation_predictions"],
                         panels["supplementary_predictions"]], ignore_index=True)
    train = history.loc[pd.to_datetime(history.endpoint).lt(pd.Timestamp("2026-09-18"))]
    pred, model = championship.fit_predict(train, current, RECIPES[recipe], "lgbm", label, PARAMS[pname], SEED)
    current["model_score"] = pred
    if pd.isna(winner.alpha):
        current["candidate_score"] = hist.blend(current, "model_score", winner.goal_weight)
    else:
        goal = current.groupby("profile_name").enhanced_goal_score.rank(pct=True)
        new_rank = current.groupby("profile_name").model_score.rank(pct=True)
        age = (1-current.history_months.div(60).clip(0,1))*current.cagr_5y_observed.ne(1)
        current["candidate_score"] = ((1-winner.alpha)*current.selected_ensemble_score +
            winner.alpha*(.67*goal+.33*new_rank)-winner.age_penalty*age)
    current.to_csv(OUT / "current_challenger.csv.gz", index=False)
    (OUT / "current_model.txt").write_bytes(model.booster_.model_to_string().encode())
    audit = current_audit(current, v3)
    # Report every profile delta for the chosen fit on both partitions.
    chosen_dev = base_dev.merge(stored[winner.candidate], on=["isin", "profile_name", "decision_date"])
    if pd.isna(winner.alpha):
        chosen_dev["candidate_score"] = hist.blend(chosen_dev, "model_score", winner.goal_weight)
    else:
        goal = chosen_dev.groupby(["decision_date", "profile_name"]).enhanced_goal_score.rank(pct=True)
        rank = chosen_dev.groupby(["decision_date", "profile_name"]).model_score.rank(pct=True)
        age = (1-chosen_dev.history_months.fillna(0).div(60).clip(0,1))*chosen_dev.cagr_5y_observed.ne(1)
        chosen_dev["candidate_score"] = ((1-winner.alpha)*chosen_dev.champion_score+
            winner.alpha*(.67*goal+.33*rank)-winner.age_penalty*age)
    dev_new = summarize(chosen_dev, "candidate_score")
    dev_join = old_dev.merge(dev_new, on=["decision_date", "profile"], suffixes=("_champion", "_challenger"))
    dev_join.insert(0,"partition","development_2023")
    exp_join = pd.concat(diagnostics).loc[lambda d: d.candidate.eq(winner.candidate)].copy()
    exp_join = exp_join.drop(columns="candidate"); exp_join.insert(0,"partition","exposed_2025")
    slices = pd.concat([dev_join,exp_join],ignore_index=True)
    slices.to_csv(OUT / "winner_profile_date_slices.csv",index=False)
    score = {}
    for partition, block in slices.groupby("partition"):
        score[partition] = {metric: {"champion":float(block[f"{metric}_champion"].mean()),
                                     "challenger":float(block[f"{metric}_challenger"].mean()),
                                     "delta":float((block[f"{metric}_challenger"]-block[f"{metric}_champion"]).mean())}
                            for metric in METRICS}
    manifest = {"winner":winner.to_dict(),"metrics":score,"current_audit":audit,
        "input_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in (V3,HISTORIC,hist.FREEZE/"rankings.csv.gz",
                                   hist.SOURCE/"training_panel.csv.gz",
                                   hist.SOURCE/"validation_predictions.csv.gz",
                                   hist.SOURCE/"supplementary_predictions.csv.gz")},
        "frozen_score_max_error":float((frozen.selected_ensemble_score-hist.blend(frozen,"lightgbm_lambdarank_score",.67)).abs().max()),
        "production_mutated":False,"frozen_champion_mutated":False,
        "selection_dates":["2023-06-30","2023-12-31"],
        "exposed_diagnostic_dates":["2025-03-31","2025-06-30"],"untouched_holdout_dates":[]}
    (OUT/"summary.json").write_text(json.dumps(manifest,indent=2,default=str),encoding="utf-8")


if __name__ == "__main__":
    run()
