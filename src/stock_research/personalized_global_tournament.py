"""Preregistered global personalized ranking tournament utilities."""
from __future__ import annotations

from dataclasses import fields
import json
from pathlib import Path

import numpy as np
import pandas as pd

from stock_ranker.personalized import InvestorProfile


FEATURES = ["xirr_score", "goal_score", "price_drawdown", "cagr_3y", "cagr_5y"]
BASE_CANDIDATES = [
    "professor_style_score", "xirr_score", "goal_score",
    "historical_target_frequency_score", "global_existing_score",
    "goal_plus_global_existing_score", "ridge_personalized_score",
    "ridge_without_risk_score", "ridge_without_goal_score",
    "cluster_rank_aggregation_score", "hist_gradient_boosting_score",
    "lightgbm_lambdarank_score",
]


def load_protocol(path: str | Path) -> tuple[dict, dict[str, InvestorProfile]]:
    value = json.loads(Path(path).read_text(encoding="utf-8"))
    if value.get("scope") != "GLOBAL_ONLY_NO_HISTORICAL_SECTOR_GROUPS":
        raise ValueError("global-only protocol required")
    allowed = {item.name for item in fields(InvestorProfile)}
    profiles = {
        name: InvestorProfile(**{key: raw[key] for key in raw if key in allowed})
        for name, raw in value["profiles"].items()
    }
    if {p.lookback_months for p in profiles.values()} - {12, 36, 60}:
        raise ValueError("profile has no frozen lookback cohort")
    latest = pd.Timestamp(value["latest_prelock_outcome_maturity"])
    locked = pd.to_datetime(value["locked_test_decision_dates"])
    if not (locked > latest).all() or not locked.is_monotonic_increasing:
        raise ValueError("locked decisions must follow all prelock outcome maturity")
    return value, profiles


def load_frozen_memberships(root: str | Path, expected_fingerprint: str) -> dict[int, set[str]]:
    root = Path(root)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("fingerprint") != expected_fingerprint:
        raise ValueError("frozen cohort fingerprint drift")
    result = {}
    for months in (12, 36, 60):
        frame = pd.read_csv(root / f"frozen_cohort_{months}m.csv.gz", usecols=["isin", "freeze_status"])
        if frame["isin"].duplicated().any():
            raise ValueError("duplicate frozen identity")
        result[months] = set(frame.loc[frame.freeze_status.eq("INCLUDE_GLOBAL"), "isin"])
    return result


def global_existing_evidence(book, facts: pd.DataFrame, day: str) -> pd.DataFrame:
    """Global analogue of the existing 1y/3y/5y/recency price formula."""
    rows = []
    terminal = np.datetime64(pd.Timestamp(day).date(), "D")
    anchors = [np.datetime64((pd.Timestamp(day) - pd.DateOffset(years=y)).date(), "D") for y in (1, 3, 5)]
    for identity, (dates, prices) in book.arrays.items():
        last = np.searchsorted(dates, terminal, side="right") - 1
        indices = [np.searchsorted(dates, anchor, side="right") - 1 for anchor in anchors]
        if last < 0 or min(indices) < 0 or int((terminal - dates[last]).astype(int)) > 7:
            continue
        if any(int((anchor - dates[index]).astype(int)) > 7 for anchor, index in zip(anchors, indices)):
            continue
        returns = [prices[last] / prices[index] - 1 for index in indices]
        since_high = -int((dates[last] - dates[np.argmax(prices[:last + 1])]).astype(int))
        rows.append({"isin": identity, "return1": returns[0], "return3": returns[1],
                     "return5": returns[2], "recency": since_high})
    evidence = facts[["isin"]].merge(pd.DataFrame(rows), on="isin", how="left", validate="one_to_one")
    columns = ["return1", "return3", "return5", "recency"]
    complete = evidence[columns].notna().all(axis=1)
    ranks = evidence.loc[complete, columns].rank(pct=True)
    evidence.loc[complete, "global_existing_score"] = ranks.mean(axis=1)
    return evidence[["isin", "global_existing_score"]]


def add_transparent_candidates(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["historical_target_frequency_score"] = result["historical_target_frequency"]
    ranked = result[["goal_score", "global_existing_score"]].rank(pct=True)
    result["goal_plus_global_existing_score"] = ranked.mean(axis=1).where(ranked.notna().all(axis=1))
    return result


def fit_fixed_models(prelock: pd.DataFrame, locked: pd.DataFrame, protocol: dict) -> tuple[pd.DataFrame, list[dict]]:
    """Fit only on matured pre-lock outcomes and predict the untouched lockbox."""
    from sklearn.ensemble import HistGradientBoostingRegressor
    from sklearn.impute import SimpleImputer
    from sklearn.inspection import permutation_importance
    from sklearn.linear_model import Ridge
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler

    config = protocol["candidate_policy"]
    training = prelock.loc[prelock.future_xirr.notna() & prelock.xirr_score.notna()].sort_values(
        ["decision_date", "profile_name", "isin"], kind="mergesort"
    ).copy()
    if pd.to_datetime(training.endpoint).max() > pd.Timestamp(protocol["latest_prelock_outcome_maturity"]):
        raise ValueError("training includes outcome beyond preregistered maturity")
    output = locked.copy()
    audits = []
    ridge_groups = {
        "ridge_personalized": FEATURES,
        "ridge_without_risk": ["xirr_score", "goal_score", "cagr_3y", "cagr_5y"],
        "ridge_without_goal": ["xirr_score", "price_drawdown", "cagr_3y", "cagr_5y"],
    }
    for name, ridge_features in ridge_groups.items():
        ridge = make_pipeline(SimpleImputer(strategy="median", add_indicator=True), StandardScaler(),
                              Ridge(alpha=float(config["ridge_alpha"])))
        ridge.fit(training[ridge_features], training.future_xirr.clip(-1, 3))
        output[name + "_score"] = ridge.predict(output[ridge_features])
        audits.append({"candidate": name, "features": ridge_features,
                       "train_rows": len(training), "alpha": config["ridge_alpha"]})

    correlation = training[FEATURES].corr(method="spearman").abs()
    clusters, pending = [], set(FEATURES)
    threshold = float(config["correlation_cluster_threshold"])
    while pending:
        component = {min(pending)}
        while True:
            enlarged = component | {c for c in pending if any(correlation.loc[c, k] >= threshold for k in component)}
            if enlarged == component:
                break
            component = enlarged
        clusters.append(sorted(component)); pending -= component
    normalized = output.groupby(["decision_date", "profile_name"])[FEATURES].rank(pct=True)
    votes = pd.concat([normalized[group].mean(axis=1).where(normalized[group].notna().all(axis=1))
                       for group in clusters], axis=1)
    output["cluster_rank_aggregation_score"] = votes.mean(axis=1).where(votes.notna().all(axis=1))
    audits.append({"candidate": "cluster_rank_aggregation", "clusters": clusters, "threshold": threshold})

    hist_config = config["hist_gradient_boosting"]
    imputer = SimpleImputer(strategy="median", add_indicator=False)
    train_x = imputer.fit_transform(training[FEATURES])
    test_x = imputer.transform(output[FEATURES])
    hist = HistGradientBoostingRegressor(**hist_config, random_state=int(config["seed"]))
    train_y = training.future_xirr.clip(-1, 3)
    hist.fit(train_x, train_y)
    output["hist_gradient_boosting_score"] = hist.predict(test_x)
    sample = np.linspace(0, len(training) - 1, min(5000, len(training)), dtype=int)
    importance = permutation_importance(hist, train_x[sample], train_y.iloc[sample], n_repeats=3,
                                        random_state=int(config["seed"]), n_jobs=1)
    audits.append({"candidate": "hist_gradient_boosting", "features": FEATURES, "train_rows": len(training),
                   "parameters": hist_config,
                   "permutation_importance": dict(zip(FEATURES, importance.importances_mean.tolist()))})

    try:
        from lightgbm import LGBMRanker
        sorted_training = training.sort_values(["decision_date", "profile_name", "isin"], kind="mergesort")
        labels = sorted_training.groupby(["decision_date", "profile_name"]).future_xirr.rank(pct=True).mul(4).clip(upper=3).astype(int)
        params = config["lightgbm_lambdarank"]
        ranker = LGBMRanker(**params, random_state=int(config["seed"]), n_jobs=1, verbosity=-1,
                            deterministic=True, force_col_wise=True)
        sizes = sorted_training.groupby(["decision_date", "profile_name"], sort=False).size().to_list()
        ranker.fit(sorted_training[FEATURES], labels, group=sizes)
        output["lightgbm_lambdarank_score"] = ranker.predict(output[FEATURES])
        audits.append({"candidate": "lightgbm_lambdarank", "features": FEATURES,
                       "train_rows": len(sorted_training), "parameters": params,
                       "importance": dict(zip(FEATURES, ranker.feature_importances_.tolist()))})
    except ImportError:
        output["lightgbm_lambdarank_score"] = np.nan
        audits.append({"candidate": "lightgbm_lambdarank", "status": "INSUFFICIENT EVIDENCE",
                       "reason": "isolated optional dependency absent"})
    return output, audits


def common_cohort_metrics(panel: pd.DataFrame, candidates: list[str] = BASE_CANDIDATES) -> pd.DataFrame:
    from stock_research.personalized_validation import ranking_metrics
    rows = []
    required = [*candidates, "future_xirr", "future_shortfall", "future_drawdown"]
    for (day, profile), group in panel.groupby(["decision_date", "profile_name"], sort=True):
        common = group.dropna(subset=required)
        for candidate in candidates:
            rows.append({"decision_date": day, "profile": profile, "candidate": candidate,
                         "cohort": "common", **ranking_metrics(common, candidate)})
    return pd.DataFrame(rows)


def paired_candidate_deltas(metrics: pd.DataFrame, references=("professor_style_score", "global_existing_score")) -> pd.DataFrame:
    keys = ["decision_date", "profile"]
    indexed = metrics.set_index([*keys, "candidate"])
    rows = []
    for candidate in sorted(metrics.candidate.unique()):
        if candidate in references:
            continue
        for reference in references:
            for metric in ("rank_ic", "ndcg20", "pairwise_accuracy", "target_achievement_top20",
                           "target_shortfall_top20", "mean_xirr_top20", "mean_asset_drawdown_top20"):
                left = indexed.xs(candidate, level="candidate")[metric]
                right = indexed.xs(reference, level="candidate")[metric]
                pair = pd.concat([left.rename("candidate"), right.rename("reference")], axis=1).dropna()
                delta = pair.candidate - pair.reference
                if metric in {"target_shortfall_top20"}:
                    delta = -delta
                rows.append({"candidate": candidate, "reference": reference, "metric": metric,
                             "blocks": len(delta), "mean_improvement": delta.mean(),
                             "median_improvement": delta.median(), "win_rate": delta.gt(0).mean()})
    return pd.DataFrame(rows)


def profile_sensitivity(current: pd.DataFrame, candidates: list[str] = BASE_CANDIDATES) -> pd.DataFrame:
    base = current.loc[current.profile_name.eq("base36")].set_index("isin")
    rows = []
    for profile, group in current.groupby("profile_name"):
        other = group.set_index("isin")
        for candidate in candidates:
            pair = pd.concat([base[candidate].rename("base"), other[candidate].rename("other")], axis=1).dropna()
            top_base = set(pair.nlargest(20, "base").index)
            top_other = set(pair.nlargest(20, "other").index)
            rows.append({"profile": profile, "candidate": candidate, "pairs": len(pair),
                         "spearman_with_base": pair.base.corr(pair.other, method="spearman"),
                         "top20_overlap": len(top_base & top_other) / max(len(top_base), 1)})
    return pd.DataFrame(rows)
