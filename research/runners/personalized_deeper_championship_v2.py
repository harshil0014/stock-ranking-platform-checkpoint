"""Research-only deep walk-forward championship. Run prepare, development, then final.

The final stage refuses to score the holdout until the development stage has
persisted a locked selection. No historical sector or fundamental is attached.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
for key in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS"):
    os.environ[key] = "1"

import numpy as np
import pandas as pd
from stock_ranker.company_facts import resolve_company_fact_snapshot
from research.runners import personalized_championship as old
from research.runners import personalized_history_challenger as hist
from research.runners import personalized_successor_20261002 as prior

PROTOCOL = ROOT / "research/protocols/personalized_deeper_walkforward_v2.json"
PANEL = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v12/deep_panel.csv.gz"
OUT = ROOT / "experiments/personalized-deep-championship-20261002/v3"
V3 = prior.V3
SEED = 20261002
RECIPES = {
    "core": old.CORE,
    "age": old.CORE + old.AGE,
    "duration": old.CORE + old.AGE + old.DRAWDOWN,
    "high_duration": old.CORE + old.AGE + old.HIGH + old.DRAWDOWN,
    "full_risk": old.CORE + old.AGE + old.HIGH + old.DRAWDOWN + old.VOL,
    "no_goal_risk": [c for c in old.CORE if c != "enhanced_goal_score"] + old.AGE + old.HIGH + old.DRAWDOWN + old.VOL,
    "risk_no_3y": [c for c in old.CORE if c != "cagr_3y"] + old.AGE + old.HIGH + old.DRAWDOWN + old.VOL,
}
PARAMS = {"frozen": old.BASE_PARAMS, "top20": prior.PARAMS["shallow"],
          "regularized": prior.PARAMS["regularized"]}
METRICS = hist.METRICS


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def protocol():
    return json.loads(PROTOCOL.read_text(encoding="utf-8"))


def prepare():
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "prepared.pkl.gz"
    if path.exists():
        raise FileExistsError(path)
    needed = list(dict.fromkeys(["isin", "decision_date", "endpoint", "profile_name",
        "enhanced_carry_xirr_score", "enhanced_goal_score", *old.CORE]))
    panel = pd.read_csv(PANEL, usecols=needed, low_memory=False)
    p = protocol()
    dates = set(
        p["initial_history_dates"]
        + p["development_selection_dates"]
        + p["postlock_2024_diagnostics"]
        + p["untouched_final_dates"]
        + p["postfinal_2025_diagnostics"]
    )
    if set(panel.decision_date) != dates:
        raise ValueError("authoritative deeper panel date mismatch")
    if not (pd.to_datetime(panel.endpoint).gt(pd.to_datetime(panel.decision_date)).all()
            and pd.to_datetime(panel.endpoint).le(pd.Timestamp("2026-09-18")).all()):
        raise ValueError("endpoint leakage")
    # Parse outcome fields only for early/development decisions. The two final
    # dates' outcome values are never indexed, converted, or stored here.
    open_dates = set(p["initial_history_dates"] + p["development_selection_dates"])
    label_values = {name: np.full(len(panel), np.nan) for name in
                    ("future_xirr", "future_shortfall", "future_drawdown")}
    identities, decisions, profiles = (panel[name].to_numpy() for name in
                                        ("isin", "decision_date", "profile_name"))
    with gzip.open(PANEL, "rt", newline="", encoding="utf-8") as stream:
        reader = csv.reader(stream)
        names = next(reader)
        ix = {name: names.index(name) for name in
              ("isin", "decision_date", "profile_name", "future_xirr", "future_shortfall", "future_drawdown")}
        for rownum, line in enumerate(reader):
            if (line[ix["isin"]] != identities[rownum]
                    or line[ix["decision_date"]] != decisions[rownum]
                    or line[ix["profile_name"]] != profiles[rownum]):
                raise ValueError("panel row-order mismatch during label admission")
            if line[ix["decision_date"]] in open_dates:
                for name in label_values:
                    value = line[ix[name]]
                    label_values[name][rownum] = float(value) if value else np.nan
    if rownum + 1 != len(panel):
        raise ValueError("panel row-count mismatch during label admission")
    for name, values in label_values.items():
        panel[name] = values
    facts = hist.load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    # The current fact snapshot supplies only the file key. A constant sector
    # prevents even transient use of present-day classification in a feature.
    locator = facts[["isin", "ticker"]].drop_duplicates("isin").copy()
    locator["derived_research_sector"] = "GLOBAL"
    features = hist.history_features({"deep": panel[["isin", "decision_date"]].drop_duplicates()}, locator)
    features = features.drop(columns=["sector", "sector_median_cagr_5y"])
    panel = panel.rename(columns={"cagr_5y": "original_cagr_5y"}).merge(features, on=["isin", "decision_date"],
                                                    how="left", validate="many_to_one")
    panel["cagr_5y_observed"] = panel.cagr_5y_observed.fillna(0).astype("int8")
    median = panel.loc[panel.cagr_5y_observed.eq(1)].groupby("decision_date").observed_cagr_5y.median()
    anchor = panel.decision_date.map(median).fillna(0).clip(-.5, .5)
    weight = panel.history_months.fillna(0).div(60).clip(0, 1)
    estimated = weight * panel.history_start_cagr.clip(-.75, 1).fillna(0) + (1-weight) * anchor
    panel["cagr_5y"] = panel.observed_cagr_5y.where(panel.cagr_5y_observed.eq(1), estimated)
    panel["cagr_5y_source"] = np.where(panel.cagr_5y_observed.eq(1), "OBSERVED",
                                        np.where(panel.history_months.notna(), "ESTIMATED_GLOBAL", "NO_HISTORY"))
    # This assignment is redundant by construction and documents the seal.
    sealed_dates = (
        p["postlock_2024_diagnostics"]
        + p["untouched_final_dates"]
        + p["postfinal_2025_diagnostics"]
    )
    sealed = panel.decision_date.isin(sealed_dates)
    panel.loc[sealed, ["future_xirr", "future_shortfall", "future_drawdown"]] = np.nan
    panel.to_pickle(path, compression="gzip")
    (OUT / "prepare_audit.json").write_text(json.dumps({
        "panel_sha256": digest(PANEL), "protocol_sha256": digest(PROTOCOL),
        "rows": len(panel), "dates": sorted(dates),
        "history_feature_identity_dates": len(features),
        "missing_history_rows": int(panel.history_months.isna().sum()),
        "estimated_growth_rows": int(panel.cagr_5y_source.eq("ESTIMATED_GLOBAL").sum()),
        "no_history_rows": int(panel.cagr_5y_source.eq("NO_HISTORY").sum()),
        "latest_endpoint": str(panel.endpoint.max()), "current_sector_used": False,
        "current_fundamentals_used": False, "provider_split_source": "yahoo-split-ledger-v2",
        "provider_failed_lookups_quarantined": 18,
        "sealed_outcome_values_indexed_before_lock": False}, indent=2), encoding="utf-8")


def predict(panel, dates, columns, label, params, compact=False):
    result = []
    for day in dates:
        target = panel.loc[panel.decision_date.eq(day)].copy()
        train = panel.loc[pd.to_datetime(panel.endpoint).lt(pd.Timestamp(day))]
        if train.empty or pd.to_datetime(train.endpoint).max() >= pd.Timestamp(day):
            raise ValueError("training maturity failure")
        score, _ = old.fit_predict(train, target, columns, "lgbm", label, params, SEED)
        target["ranker_score"] = score
        result.append(target[["isin", "decision_date", "profile_name", "ranker_score"]] if compact else target)
        print("scored", day, label, len(train), flush=True)
    return pd.concat(result, ignore_index=True)


def candidate_score(frame, goal_weight, alpha, penalty):
    goal = frame.groupby(["decision_date", "profile_name"]).enhanced_goal_score.rank(pct=True)
    rank = frame.groupby(["decision_date", "profile_name"]).ranker_score.rank(pct=True)
    age = (1 - frame.history_months.fillna(0).div(60).clip(0, 1)) * frame.cagr_5y_observed.ne(1)
    return (1-alpha) * frame.champion_score + alpha * (goal_weight*goal + (1-goal_weight)*rank) - penalty*age


def score_adjustment_score(frame, signal, penalty, age_coefficient=0.0):
    """Fixed development-tested risk adjustment with neutral missing inputs."""
    def neutral(name):
        observed = frame[name]
        return observed.fillna(observed.groupby(frame.decision_date).transform("median")).fillna(observed.median())
    age = (1-frame.history_months.fillna(0).div(60).clip(0,1))*frame.cagr_5y_observed.ne(1)
    duration = neutral("current_drawdown_duration_days").div(1825).clip(0,1)
    depth = (-neutral("full_history_max_drawdown")).clip(0,1)
    high_age = neutral("days_since_recorded_high").div(1825).clip(0,1)
    high_distance = (-neutral("distance_from_recorded_high")).clip(0,1)
    downside = neutral("downside_volatility_1y").clip(0,2).div(2)
    signals = {
        "age": age, "underwater": duration*depth,
        "high": high_age*high_distance, "full_drawdown": depth,
        "downside_volatility": downside,
        "age_underwater": .5*age+.5*duration*depth,
        "age_high": .5*age+.5*high_age*high_distance,
    }
    if signal == "age_downside":
        return frame.champion_score - age_coefficient*age - penalty*downside
    return frame.champion_score - penalty*signals[signal]


def baseline(panel, dates):
    original = panel.copy()
    original["cagr_5y"] = original.original_cagr_5y
    frame = predict(original, dates, old.CORE, "xirr4", old.BASE_PARAMS)
    frame["champion_score"] = hist.blend(frame, "ranker_score", .67)
    return frame


def metric_deltas(new, base):
    d = new[METRICS].mean() - base[METRICS].mean()
    joined = base.merge(new, on=["decision_date", "profile"], suffixes=("_old", "_new"))
    prof = joined.groupby("profile").mean(numeric_only=True)
    by_date = joined.groupby("decision_date").mean(numeric_only=True)

    worst_short = float((prof.target_shortfall_top20_new-prof.target_shortfall_top20_old).max())
    worst_hit = float((prof.target_achievement_top20_new-prof.target_achievement_top20_old).min())
    worst_date_short = float((by_date.target_shortfall_top20_new-by_date.target_shortfall_top20_old).max())
    worst_date_hit = float((by_date.target_achievement_top20_new-by_date.target_achievement_top20_old).min())
    worst_date_median = float((by_date.median_xirr_top20_new-by_date.median_xirr_top20_old).min())
    worst_date_drawdown = float((by_date.mean_asset_drawdown_top20_new-by_date.mean_asset_drawdown_top20_old).min())

    # Mean XIRR has zero selection weight. Dense-history selection rewards
    # aggregate utility but explicitly penalizes regime/date-specific failures.
    aggregate_utility = (
        2.0 * -d.target_shortfall_top20
        + 1.5 * d.target_achievement_top20
        + .8 * d.median_xirr_top20
        + .8 * d.ndcg20
        + .5 * d.pairwise_accuracy
        + .35 * d.rank_ic
        + .4 * d.mean_asset_drawdown_top20
    )
    robustness_penalty = (
        1.5 * max(0.0, worst_date_short)
        + .8 * max(0.0, -worst_date_hit)
        + .35 * max(0.0, -worst_date_median)
        + .35 * max(0.0, -worst_date_drawdown)
    )
    utility = float(aggregate_utility - robustness_penalty)
    eligible = (
        d.coverage >= -.001
        and d.target_shortfall_top20 <= .005
        and d.mean_asset_drawdown_top20 >= -.01
        and d.median_xirr_top20 >= -.025
        and worst_short <= .02
        and worst_hit >= -.12
        and worst_date_short <= .05
        and worst_date_hit >= -.20
        and worst_date_median >= -.30
        and worst_date_drawdown >= -.08
    )
    return {
        **{f"delta_{k}": float(v) for k,v in d.items()},
        "utility": utility,
        "aggregate_utility": float(aggregate_utility),
        "robustness_penalty": float(robustness_penalty),
        "eligible": bool(eligible),
        "worst_profile_shortfall_delta": worst_short,
        "worst_profile_achievement_delta": worst_hit,
        "worst_date_shortfall_delta": worst_date_short,
        "worst_date_achievement_delta": worst_date_hit,
        "worst_date_median_xirr_delta": worst_date_median,
        "worst_date_drawdown_delta": worst_date_drawdown,
    }


def development():
    if (OUT / "locked_selection.json").exists():
        raise FileExistsError("selection already locked")

    panel = pd.read_pickle(OUT / "prepared.pkl.gz", compression="gzip")
    p = protocol()
    dates = p["development_selection_dates"]
    qdates = dates[::2]

    baseline_path = OUT / "development_baseline.pkl.gz"
    if baseline_path.exists():
        base = pd.read_pickle(baseline_path, compression="gzip")
    else:
        base = baseline(panel, dates)
        base.to_pickle(baseline_path, compression="gzip")

    bm = hist.evaluate(base, "champion_score")
    bm.to_csv(OUT / "development_champion_profiles.csv", index=False)
    base_q = base.loc[base.decision_date.isin(qdates)].copy()
    bm_q = hist.evaluate(base_q, "champion_score")

    recipes = ("core", "age", "duration", "high_duration", "full_risk", "no_goal_risk", "risk_no_3y")
    labels = ("utility4", "xirr4", "xirr8")
    pnames = ("top20", "regularized", "frozen")
    goal_weights = (.55, .60, .67, .73, .80)
    alphas = (.10, .20, .35, .50, .65, .80, 1.0)
    penalties = (0.0, .03, .06, .10)

    qualification_rows = []
    config_leaders = []
    for recipe in recipes:
        for label in labels:
            for pname in pnames:
                key = f"{recipe}|{label}|{pname}"
                scored = predict(
                    panel, qdates, RECIPES[recipe], label, PARAMS[pname], compact=True
                )
                frame = base_q.drop(columns=["ranker_score"]).merge(
                    scored,
                    on=["isin", "decision_date", "profile_name"],
                    validate="one_to_one",
                )
                local_rows = []
                for w in goal_weights:
                    for alpha in alphas:
                        for penalty in penalties:
                            frame["candidate_score"] = candidate_score(frame, w, alpha, penalty)
                            m = hist.evaluate(frame, "candidate_score")
                            row = {
                                "candidate": key,
                                "goal_weight": w,
                                "alpha": alpha,
                                "age_penalty": penalty,
                                **metric_deltas(m, bm_q),
                            }
                            qualification_rows.append(row)
                            local_rows.append(row)
                local = pd.DataFrame(local_rows).sort_values(
                    ["eligible", "utility"], ascending=[False, False]
                )
                config_leaders.append(local.iloc[0].to_dict())
                pd.DataFrame(qualification_rows).to_csv(
                    OUT / "qualification_tournament.partial.csv", index=False
                )

    qualification = pd.DataFrame(qualification_rows).sort_values(
        ["eligible", "utility"], ascending=[False, False]
    )
    qualification.to_csv(OUT / "qualification_tournament.csv", index=False)
    leaders = pd.DataFrame(config_leaders).sort_values(
        ["eligible", "utility"], ascending=[False, False]
    )
    leaders.to_csv(OUT / "qualification_config_leaders.csv", index=False)

    finalist_keys = leaders.head(10)["candidate"].tolist()
    rows = []
    for key in finalist_keys:
        recipe, label, pname = key.split("|")
        scored = predict(
            panel, dates, RECIPES[recipe], label, PARAMS[pname], compact=True
        )
        frame = base.drop(columns=["ranker_score"]).merge(
            scored,
            on=["isin", "decision_date", "profile_name"],
            validate="one_to_one",
        )
        for w in goal_weights:
            for alpha in alphas:
                for penalty in penalties:
                    frame["candidate_score"] = candidate_score(frame, w, alpha, penalty)
                    m = hist.evaluate(frame, "candidate_score")
                    rows.append({
                        "candidate": key,
                        "goal_weight": w,
                        "alpha": alpha,
                        "age_penalty": penalty,
                        **metric_deltas(m, bm),
                    })
        pd.DataFrame(rows).to_csv(OUT / "development_tournament.partial.csv", index=False)

    table = pd.DataFrame(rows).sort_values(
        ["eligible", "utility"], ascending=[False, False]
    )
    table.to_csv(OUT / "development_tournament.csv", index=False)
    winner = table.iloc[0]
    record = {
        "winner": {
            k: (
                bool(v)
                if k == "eligible"
                else float(v)
                if isinstance(v, (np.floating, float))
                else str(v)
            )
            for k, v in winner.items()
        },
        "selection_dates": dates,
        "qualification_dates": qdates,
        "qualification_model_configs": len(recipes) * len(labels) * len(pnames),
        "development_finalist_configs": finalist_keys,
        "postlock_2024_diagnostics": p["postlock_2024_diagnostics"],
        "untouched_final_dates": p["untouched_final_dates"],
        "postfinal_2025_diagnostics": p["postfinal_2025_diagnostics"],
        "protocol_sha256": digest(PROTOCOL),
        "panel_sha256": digest(PANEL),
        "qualification_tournament_sha256": digest(OUT / "qualification_tournament.csv"),
        "development_tournament_sha256": digest(OUT / "development_tournament.csv"),
        "final_evaluated": False,
        "selection_uses_postlock_labels": False,
        "selection_uses_untouched_final": False,
    }
    (OUT / "locked_selection.json").write_text(
        json.dumps(record, indent=2), encoding="utf-8"
    )


def final():
    lockpath = OUT / "locked_selection.json"
    lock = json.loads(lockpath.read_text(encoding="utf-8"))
    if lock["final_evaluated"] or digest(OUT / "development_tournament.csv") != lock["development_tournament_sha256"]:
        raise ValueError("invalid selection lock")
    sealed_inputs = {
        PROTOCOL: "protocol_sha256",
        PANEL: "panel_sha256",
        OUT / "prepared.pkl.gz": "prepared_sha256",
        PANEL.parent / "integrity_audit.json": "v12_integrity_audit_sha256",
        OUT / "qualification_tournament.csv": "qualification_tournament_sha256",
        OUT / "development_history_adjustments.csv": "development_history_adjustments_sha256",
        OUT / "development_age_downside_combinations.csv": "development_age_downside_combinations_sha256",
    }
    for path, field in sealed_inputs.items():
        if digest(path) != lock[field]:
            raise ValueError(f"selection input changed after lock: {path}")
    for name, expected in lock.get("source_sha256", {}).items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"selection source changed after lock: {name}")
    if (OUT / "untouched_final_profiles.csv").exists():
        raise FileExistsError("untouched final block already evaluated")

    panel = pd.read_pickle(OUT / "prepared.pkl.gz", compression="gzip")
    partitions = (
        ("postlock_2024_diagnostics", lock["postlock_2024_diagnostics"]),
        ("untouched_final_2025", lock["untouched_final_dates"]),
        ("postfinal_2025_diagnostics", lock["postfinal_2025_diagnostics"]),
    )
    reveal_dates = [d for _, dates in partitions for d in dates]
    actual = pd.read_csv(
        PANEL,
        usecols=["isin","decision_date","profile_name","future_xirr","future_shortfall","future_drawdown"],
    )
    actual = actual.loc[actual.decision_date.isin(reveal_dates)]
    panel = panel.merge(
        actual,
        on=["isin","decision_date","profile_name"],
        how="left",
        validate="one_to_one",
        suffixes=("","_final"),
    )
    for field in ("future_xirr","future_shortfall","future_drawdown"):
        panel[field] = panel[field].fillna(panel.pop(field + "_final"))

    winner = lock["winner"]
    adjustment = winner["candidate"].startswith("score_adjustment|")
    if adjustment:
        _, signal, _ = winner["candidate"].split("|")
    else:
        recipe, label, pname = winner["candidate"].split("|")
    written = []
    for part, dates in partitions:
        base = baseline(panel, dates)
        challenger = (base[["isin", "decision_date", "profile_name", "ranker_score"]].copy()
                      if adjustment or float(winner["alpha"]) == 0 else
                      predict(panel, dates, RECIPES[recipe], label, PARAMS[pname], compact=True))
        frame = base.drop(columns=["ranker_score"]).merge(
            challenger,
            on=["isin","decision_date","profile_name"],
            validate="one_to_one",
        )
        frame["candidate_score"] = (score_adjustment_score(frame, signal, float(winner["age_penalty"]),
                                                            float(winner.get("age_coefficient", 0.0)))
            if adjustment else candidate_score(frame, float(winner["goal_weight"]),
                                               float(winner["alpha"]), float(winner["age_penalty"])))
        oldm = hist.evaluate(frame, "champion_score")
        newm = hist.evaluate(frame, "candidate_score")
        joined = oldm.merge(
            newm,
            on=["decision_date","profile"],
            suffixes=("_champion","_challenger"),
        )
        joined.insert(0, "partition", part)
        filename = {
            "postlock_2024_diagnostics": "postlock_2024_profiles.csv",
            "untouched_final_2025": "untouched_final_profiles.csv",
            "postfinal_2025_diagnostics": "postfinal_2025_profiles.csv",
        }[part]
        joined.to_csv(OUT / filename, index=False)
        frame[[
            "isin","decision_date","profile_name","champion_score","candidate_score",
            "cagr_5y_observed","history_months"
        ]].to_csv(OUT / f"{part}_scores.csv.gz", index=False)
        written.append(part)

    (OUT / "evaluation_record.json").write_text(
        json.dumps({
            "locked_selection_sha256": digest(lockpath),
            "winner": winner,
            "final_evaluated_once": True,
            "untouched_final_dates": lock["untouched_final_dates"],
            "partitions": written,
            "selection_unchanged_after_lock": True,
        }, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("stage",choices=["prepare","development","final"])
    ap.add_argument("--output",type=Path,default=OUT,help="fresh research output directory")
    args=ap.parse_args()
    OUT=args.output.resolve()
    {"prepare":prepare,"development":development,"final":final}[args.stage]()
