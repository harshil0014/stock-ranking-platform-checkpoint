"""Research-only history-aware LambdaRank tournament against frozen d499580.

No production modules, accepted state, or frozen artifacts are written here.
Historical labels are used only after their endpoint has matured.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

import lightgbm as lgb
import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot
from stock_ranker.runtime import validated_release
from stock_research.personalized_executable_tournament import FEATURES as ORIGINAL_FEATURES
from stock_research.personalized_validation import ranking_metrics

SOURCE = ROOT / "experiments/personalized-official-action-tournament/build-03"
FREEZE = ROOT / "research/freezes/personalized-d499580"
HISTORY = ROOT / "data/live_market/history_cache"
HISTORY_RECOVERY = ROOT / "experiments/history-enrichment-20261002/recovery_overlay_frozen_v1"
OUTPUT = ROOT / "experiments/personalized-history-challenger/v1"
METRICS = ["coverage", "rank_ic", "ndcg20", "pairwise_accuracy", "target_achievement_top20",
           "target_shortfall_top20", "mean_xirr_top20", "median_xirr_top20", "mean_asset_drawdown_top20"]
RISK = ["days_since_recorded_high", "distance_from_recorded_high", "full_history_max_drawdown",
        "history_months", "history_start_cagr", "cagr_5y_observed", "cagr_5y"]


def load_panels():
    names = ["training_panel", "validation_predictions", "supplementary_predictions", "current_profile_rankings"]
    return {name: pd.read_csv(SOURCE / f"{name}.csv.gz", low_memory=False) for name in names}


def history_features(panels, facts):
    keys = pd.concat([p[["isin", "decision_date"]] for p in panels.values()]).drop_duplicates()
    ticker = facts.drop_duplicates("isin").set_index("isin")["ticker"].to_dict()
    sector = facts.drop_duplicates("isin").set_index("isin")["derived_research_sector"].to_dict()
    dates = sorted(keys.decision_date.unique())
    repairs = pd.read_csv(ROOT / "experiments/personalized-data-freeze/build-01/terminal_repairs.csv")
    repairs = repairs.loc[repairs.snapshot_status.eq("AVAILABLE")].set_index("isin")
    wanted = set(keys["isin"])
    records = []
    for identity in sorted(wanted):
        symbol = ticker.get(identity)
        path = HISTORY / f"{symbol}.csv" if isinstance(symbol, str) else None
        if path is not None and not path.is_file():
            recovered = HISTORY_RECOVERY / f"{symbol}.csv"
            path = recovered if recovered.is_file() else path
        if path is None or not path.is_file():
            continue
        frame = pd.read_csv(path, usecols=["date", "adjusted_close"])
        observed = pd.to_datetime(frame.date, errors="coerce").to_numpy(dtype="datetime64[D]")
        price = pd.to_numeric(frame.adjusted_close, errors="coerce").to_numpy(float)
        good = ~np.isnat(observed) & np.isfinite(price) & (price > 0)
        observed, price = observed[good], price[good]
        if len(observed) < 2 or np.any(np.diff(observed).astype(int) <= 0):
            continue
        if identity in repairs.index:
            repair = repairs.loc[identity]
            repair_day = np.datetime64(repair.appended_date, "D")
            if (repair.ticker == symbol and repair_day > observed[-1]
                    and np.isfinite(repair.appended_price) and repair.appended_price > 0):
                observed = np.append(observed, repair_day)
                price = np.append(price, float(repair.appended_price))
        for day in dates:
            cutoff = np.datetime64(day, "D")
            last = np.searchsorted(observed, cutoff, side="right")
            if last < 2 or int((cutoff - observed[last - 1]).astype(int)) > 7:
                continue
            d, p = observed[:last], price[:last]
            span = int((d[-1] - d[0]).astype(int))
            if span <= 0:
                continue
            anchor = np.datetime64((pd.Timestamp(day) - pd.DateOffset(years=5)).date(), "D")
            ai = np.searchsorted(d, anchor, side="right") - 1
            true_5y = ai >= 0 and 0 <= int((anchor - d[ai]).astype(int)) <= 7 and ai < last - 1
            peak = int(np.argmax(p))
            running_peak = np.maximum.accumulate(p)
            underwater = p < running_peak * (1 - 1e-10)
            run_start = np.where(~underwater, np.arange(len(p)), 0)
            last_peak_indices = np.maximum.accumulate(run_start)
            underwater_days = (d - d[last_peak_indices]).astype(int)
            deepest = int(np.argmin(p / running_peak - 1))
            trough_price = float(p[deepest])
            year_start = np.searchsorted(d, cutoff - np.timedelta64(365, "D"))
            year_p = p[year_start:]
            year_returns = np.diff(np.log(year_p))
            daily_returns = year_returns
            vol = float(np.std(daily_returns, ddof=1) * np.sqrt(252)) if len(daily_returns) > 5 else np.nan
            downside = float(np.sqrt(np.mean(np.minimum(daily_returns, 0) ** 2)) * np.sqrt(252)) if len(daily_returns) > 5 else np.nan
            records.append({"isin": identity, "decision_date": day, "sector": sector.get(identity),
                "history_months": span / 30.4375,
                "history_start_cagr": float(np.expm1(np.log(p[-1] / p[0]) * 365 / span)),
                "days_since_recorded_high": int((d[-1] - d[peak]).astype(int)),
                "distance_from_recorded_high": float(p[-1] / p[peak] - 1),
                "distance_from_52w_high": float(p[-1] / np.max(year_p) - 1),
                "full_history_max_drawdown": float(np.min(p / np.maximum.accumulate(p) - 1)),
                "current_drawdown_duration_days": int(underwater_days[-1]),
                "max_drawdown_duration_days": int(underwater_days.max()),
                "recovery_from_worst_trough": float(p[-1] / trough_price - 1),
                "realized_volatility_1y": vol,
                "downside_volatility_1y": downside,
                "cagr_5y_observed": int(true_5y),
                "observed_cagr_5y": float(np.expm1(np.log(p[-1] / p[ai]) * 365 /
                                          int((d[-1] - d[ai]).astype(int)))) if true_5y else np.nan})
    features = pd.DataFrame(records)
    if features.empty:
        raise ValueError("no usable observed price histories")
    # The median is built from contemporaneous five-year observations only. A
    # young security's own return gets at most history_months / 60 weight.
    med = features.loc[features.cagr_5y_observed.eq(1)].groupby(["decision_date", "sector"]).observed_cagr_5y.median()
    fallback = features.loc[features.cagr_5y_observed.eq(1)].groupby("decision_date").observed_cagr_5y.median()
    features["sector_median_cagr_5y"] = [med.get((d, s), fallback.get(d, np.nan))
                                          for d, s in zip(features.decision_date, features.sector)]
    features["sector_median_cagr_5y"] = features.sector_median_cagr_5y.fillna(0).clip(-.5, .5)
    weight = (features.history_months / 60).clip(0, 1)
    # Winsorization applies to the extrapolated short-sample estimate, never prices.
    estimate = weight * features.history_start_cagr.clip(-.75, 1.0) + (1 - weight) * features.sector_median_cagr_5y
    features["cagr_5y"] = features.observed_cagr_5y.where(features.cagr_5y_observed.eq(1), estimate)
    features["cagr_5y_source"] = np.where(features.cagr_5y_observed.eq(1), "OBSERVED", "ESTIMATED")
    return features


def attach(panel, features):
    out = panel.drop(columns=["cagr_5y"]).merge(features, on=["isin", "decision_date"], how="left", validate="many_to_one")
    out["cagr_5y_observed"] = out.cagr_5y_observed.fillna(0).astype(int)
    # Missing underlying histories remain explicit; they are never rewarded by NaN.
    out["cagr_5y_source"] = out.cagr_5y_source.fillna("NO_VALID_HISTORY")
    out["cagr_5y"] = out.cagr_5y.fillna(out.sector_median_cagr_5y).fillna(0)
    return out


def blend(frame, model_score, weight):
    ranks = frame.groupby(["decision_date", "profile_name"])[["enhanced_goal_score", model_score]].rank(pct=True)
    return weight * ranks.enhanced_goal_score + (1 - weight) * ranks[model_score]


def evaluate(frame, score):
    rows = []
    for (day, profile), group in frame.groupby(["decision_date", "profile_name"], sort=True):
        rows.append({"decision_date": day, "profile": profile, **ranking_metrics(group, score)})
    return pd.DataFrame(rows)


def fit_predict(train, target, columns, params):
    ordered = train.loc[train.future_xirr.notna() & train.enhanced_carry_xirr_score.notna()].sort_values(
        ["decision_date", "profile_name", "isin"], kind="stable")
    labels = ordered.groupby(["decision_date", "profile_name"]).future_xirr.rank(pct=True).mul(4).clip(upper=3).astype(int)
    sizes = ordered.groupby(["decision_date", "profile_name"], sort=False).size().to_list()
    model = lgb.LGBMRanker(objective="lambdarank", n_estimators=params[0], learning_rate=params[1],
        num_leaves=params[2], max_depth=params[3], min_child_samples=params[4], reg_lambda=params[5],
        random_state=20260923, n_jobs=1, verbosity=-1, deterministic=True, force_col_wise=True)
    model.fit(ordered[columns], labels, group=sizes)
    prediction = pd.Series(np.nan, index=target.index)
    valid = target.enhanced_carry_xirr_score.notna()
    prediction.loc[valid] = model.predict(target.loc[valid, columns])
    return prediction, model


def score_summary(metrics):
    return metrics[METRICS].mean().to_dict()


def current_audit(champion, challenger, features, facts, model, columns, audit_ticker):
    current = challenger.loc[challenger.profile_name.eq("base7500")].copy()
    base = champion.loc[champion.profile_name.eq("base7500")].copy()
    identity = facts.drop_duplicates("isin")[["isin", "ticker", "derived_research_sector"]]
    audit_sector = identity.loc[identity.ticker.eq(audit_ticker), "derived_research_sector"].iloc[0]
    current = current.merge(identity, on="isin", how="left")
    base = base.merge(identity, on="isin", how="left")
    audits = {}
    for name, frame, score in (("champion", base, "selected_ensemble_score"),
                               ("challenger", current, "challenger_score")):
        valid = frame.dropna(subset=[score]).sort_values([score, "isin"], ascending=[False, True])
        # True 5Y availability comes from observed prices, even for the champion.
        valid = valid.merge(features.loc[features.decision_date.eq("2026-09-18"),
            ["isin", "cagr_5y_observed"]], on="isin", how="left", suffixes=("", "_history"))
        flag = valid["cagr_5y_observed_history"] if "cagr_5y_observed_history" in valid else valid["cagr_5y_observed"]
        short = flag.ne(1)
        sector_rows = valid.loc[valid.derived_research_sector.eq(audit_sector)].copy()
        sector_rows["sector_position"] = range(1, len(sector_rows) + 1)
        audited = valid.loc[valid.ticker.eq(audit_ticker)]
        audits[name] = {"universe_short_history_share": float(short.mean()),
            "top_short_history_share": {str(n): float(short.iloc[:n].mean()) for n in (20, 50, 100)},
            "audited_overall_position": int(np.flatnonzero(valid.ticker.eq(audit_ticker))[0] + 1) if len(audited) else None,
            "audited_sector_position": int(sector_rows.loc[sector_rows.ticker.eq(audit_ticker), "sector_position"].iloc[0]) if len(audited) and sector_rows.ticker.eq(audit_ticker).any() else None,
            "audited_sector": audit_sector,
            "sector_top10": sector_rows[["ticker", "sector_position", score]].head(10).to_dict("records")}
    booster = lgb.Booster(model_file=str(FREEZE / "lambdarank.txt"))
    old_row = base.loc[base.ticker.eq(audit_ticker)].iloc[0]
    new_row = current.loc[current.ticker.eq(audit_ticker)].iloc[0]
    old_contrib = booster.predict(pd.DataFrame([old_row[ORIGINAL_FEATURES].astype(float).to_dict()]), pred_contrib=True)[0]
    new_contrib = model.predict(pd.DataFrame([new_row[columns].astype(float).to_dict()]), pred_contrib=True)[0]
    audits["audited_security_contributions"] = {
        "ticker": audit_ticker,
        "champion": dict(zip([*ORIGINAL_FEATURES, "bias"], map(float, old_contrib))),
        "challenger": dict(zip([*columns, "bias"], map(float, new_contrib))),
        "original_missing_cagr_5y": bool(pd.isna(old_row.cagr_5y)),
        "new_cagr_5y_source": new_row.cagr_5y_source,
        "new_cagr_5y": float(new_row.cagr_5y),
        "missing_value_feature_contributions": {
            k: float(v) for k, v in zip(ORIGINAL_FEATURES, old_contrib[:-1])
            if pd.isna(old_row[k])}}
    scored_base = base.loc[base.selected_ensemble_score.notna()].copy()
    contributions = booster.predict(scored_base[ORIGINAL_FEATURES], pred_contrib=True)
    missing = scored_base.cagr_5y.isna().to_numpy()
    cagr_index = ORIGINAL_FEATURES.index("cagr_5y")
    audits["missing_value_contributions"] = {
        "missing_cagr_5y_count": int(missing.sum()),
        "missing_cagr_5y_mean_contribution": float(contributions[missing, cagr_index].mean()),
        "missing_cagr_5y_median_contribution": float(np.median(contributions[missing, cagr_index])),
        "observed_cagr_5y_mean_contribution": float(contributions[~missing, cagr_index].mean()),
        "challenger_missing_cagr_5y_count": int(current.loc[current.challenger_score.notna(), "cagr_5y"].isna().sum())}
    return audits


def run(output, audit_ticker):
    output.mkdir(parents=True, exist_ok=False)
    panels = load_panels()
    release = validated_release()
    fact_root = ROOT / "data/company_facts/snapshots" / (
        "2026-09-18-" + release["accepted_company_fingerprint"]
    )
    fact_bundle = load_company_fact_snapshot(fact_root)
    if fact_bundle.manifest.get("fingerprint") != release["accepted_company_fingerprint"]:
        raise ValueError("accepted company-fact fingerprint mismatch")
    facts = fact_bundle.facts
    features = history_features(panels, facts)
    features.to_csv(output / "history_features.csv.gz", index=False)
    panels = {k: attach(v, features) for k, v in panels.items()}
    val = panels["validation_predictions"]
    supp = panels["supplementary_predictions"]
    baseline = {}
    for name, frame in (("validation", val), ("supplementary", supp)):
        frame["champion_score"] = blend(frame, "lightgbm_lambdarank_score", .67)
        baseline[name] = evaluate(frame, "champion_score")
    current_frozen = pd.read_csv(FREEZE / "rankings.csv.gz", low_memory=False)
    # Preserve the sealed current Goal scores and execution features exactly.
    # The earlier tournament checkpoint is not the sealed current input panel.
    panels["current_profile_rankings"] = attach(current_frozen, features)
    check = current_frozen[["isin", "profile_name", "selected_ensemble_score",
                            "enhanced_goal_score", "lightgbm_lambdarank_score"]].copy()
    check["recomputed"] = blend(check.assign(decision_date="2026-09-18"), "lightgbm_lambdarank_score", .67)
    if (check.selected_ensemble_score - check.recomputed).abs().max() > 1e-10:
        raise ValueError("frozen current baseline differs from recomputed 67/33 blend")
    recipes = {
        "base_proxy": ORIGINAL_FEATURES + ["cagr_5y_observed", "history_months"],
        "risk_core": ORIGINAL_FEATURES + RISK[:-1],
        "risk_no_history_start": ORIGINAL_FEATURES + [x for x in RISK[:-1] if x != "history_start_cagr"],
        "risk_no_goal": [x for x in ORIGINAL_FEATURES if x != "enhanced_goal_score"] + RISK[:-1],
        "risk_no_3y": [x for x in ORIGINAL_FEATURES if x != "cagr_3y"] + RISK[:-1],
    }
    params = {
        "frozen": (60, .05, 7, 3, 80, 10.),
        "shallow": (80, .04, 7, 3, 120, 15.),
        "regularized": (100, .03, 7, 3, 160, 20.),
        "compact": (80, .04, 5, 3, 120, 20.),
    }
    rows = []
    predictions = {}
    for recipe, columns in recipes.items():
        for setting, param in params.items():
            key = f"{recipe}__{setting}"
            v = val.copy(); s = supp.copy()
            for day, group in v.groupby("decision_date"):
                mature = panels["training_panel"].loc[pd.to_datetime(panels["training_panel"].endpoint).lt(pd.Timestamp(day))]
                pred, _ = fit_predict(mature, group, columns, param)
                v.loc[group.index, "challenger_lambda"] = pred
            development = pd.concat([panels["training_panel"], val], ignore_index=True)
            for day, group in s.groupby("decision_date"):
                mature = development.loc[pd.to_datetime(development.endpoint).lt(pd.Timestamp(day))]
                pred, _ = fit_predict(mature, group, columns, param)
                s.loc[group.index, "challenger_lambda"] = pred
            for weight in (.60, .67, .73):
                for part, frame in (("validation", v), ("supplementary", s)):
                    frame["challenger_score"] = blend(frame, "challenger_lambda", weight)
                    result = score_summary(evaluate(frame, "challenger_score"))
                    rows.append({"candidate": key, "weight": weight, "partition": part, **result})
            predictions[key] = (v[["isin", "decision_date", "profile_name", "challenger_lambda"]].copy(),
                                s[["isin", "decision_date", "profile_name", "challenger_lambda"]].copy())
            print(key, flush=True)
    tournament = pd.DataFrame(rows)
    tournament.to_csv(output / "tournament.csv", index=False)
    base_sum = {part: score_summary(m) for part, m in baseline.items()}
    # Select on chronological validation; exposed supplementary is an audit only.
    selection = tournament.loc[tournament.partition.eq("validation")].copy()
    b = base_sum["validation"]
    # Mean XIRR has extreme corporate-action outliers in this retrospective
    # panel. Cap its influence so selection rests on achievement, shortfall,
    # median return, and ranking quality across profiles.
    selection["utility"] = (4 * (b["target_shortfall_top20"] - selection.target_shortfall_top20)
        + 2 * (selection.target_achievement_top20 - b["target_achievement_top20"])
        + 2 * (selection.median_xirr_top20 - b["median_xirr_top20"])
        + .1 * (selection.mean_xirr_top20 - b["mean_xirr_top20"]).clip(-.5, .5)
        + .5 * (selection.rank_ic - b["rank_ic"])
        + .5 * (selection.ndcg20 - b["ndcg20"])
        + .5 * (selection.pairwise_accuracy - b["pairwise_accuracy"]))
    selection = selection.loc[(selection.coverage >= b["coverage"] - .005)
        & (selection.target_shortfall_top20 <= b["target_shortfall_top20"] * 1.01)
        & (selection.mean_asset_drawdown_top20 >= b["mean_asset_drawdown_top20"] - .015)]
    if selection.empty:
        raise ValueError("no challenger satisfies utility guardrails")
    winner = selection.sort_values("utility", ascending=False).iloc[0]
    key, weight = winner.candidate, float(winner.weight)
    recipe, setting = key.split("__")
    columns = recipes[recipe]
    comparisons = []
    profile_rows = []
    for part, panel in (("validation", val), ("supplementary", supp)):
        pred = predictions[key][0 if part == "validation" else 1]
        frame = panel.merge(pred, on=["isin", "decision_date", "profile_name"], validate="one_to_one")
        frame["challenger_score"] = blend(frame, "challenger_lambda", weight)
        old, new = evaluate(frame, "champion_score"), evaluate(frame, "challenger_score")
        for metric in METRICS:
            comparisons.append({"partition": part, "metric": metric, "champion": old[metric].mean(),
                "challenger": new[metric].mean(), "delta": new[metric].mean() - old[metric].mean()})
        merged = old.merge(new, on=["decision_date", "profile"], suffixes=("_champion", "_challenger"))
        merged.insert(0, "partition", part)
        profile_rows.append(merged)
    current = panels["current_profile_rankings"].copy()
    mature = pd.concat([panels["training_panel"], val, supp], ignore_index=True)
    mature = mature.loc[pd.to_datetime(mature.endpoint).lt(pd.Timestamp("2026-09-18"))]
    pred, model = fit_predict(mature, current, columns, params[setting])
    current["challenger_lambda"] = pred
    current["challenger_score"] = blend(current, "challenger_lambda", weight)
    audit = current_audit(current_frozen, current, features, facts, model, columns, audit_ticker)
    pd.DataFrame(comparisons).to_csv(output / "champion_vs_challenger.csv", index=False)
    pd.concat(profile_rows).to_csv(output / "profile_slices.csv", index=False)
    current.to_csv(output / "current_challenger.csv.gz", index=False)
    # LightGBM tree_sizes are byte offsets in LF format; Windows text-mode
    # newline translation makes an otherwise valid model unreadable.
    (output / "current_lambdarank.txt").write_bytes(model.booster_.model_to_string().encode("utf-8"))
    (output / "audit.json").write_text(json.dumps({"winner": key, "goal_weight": weight, "features": columns,
        "parameters": params[setting], "frozen_reproduction_max_error": float((check.selected_ensemble_score - check.recomputed).abs().max()),
        "current": audit, "source_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in [SOURCE / "training_panel.csv.gz", SOURCE / "validation_predictions.csv.gz",
                  SOURCE / "supplementary_predictions.csv.gz", FREEZE / "rankings.csv.gz"]}}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--audit-ticker", required=True)
    arguments = parser.parse_args()
    run(arguments.output, arguments.audit_ticker)
