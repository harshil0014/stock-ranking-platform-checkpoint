"""Research-only deep walk-forward championship. Run prepare, development, then final.

The final stage refuses to score the holdout until the development stage has
persisted a locked selection. No historical sector or fundamental is attached.
"""
from __future__ import annotations

import argparse
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

PROTOCOL = ROOT / "research/protocols/personalized_deep_walkforward_v1.json"
PANEL = ROOT / "experiments/personalized-deep-history-20261002/real-panel-v7/deep_panel.csv.gz"
OUT = ROOT / "experiments/personalized-deep-championship-20261002/v1"
V3 = prior.V3
SEED = 20261002
RECIPES = {
    "core": old.CORE,
    "age": old.CORE + old.AGE,
    "duration": old.CORE + old.AGE + old.DRAWDOWN,
    "high_duration": old.CORE + old.AGE + old.HIGH + old.DRAWDOWN,
    "full_risk": old.CORE + old.AGE + old.HIGH + old.DRAWDOWN + old.VOL,
    "no_goal_risk": [c for c in old.CORE if c != "enhanced_goal_score"] + old.AGE + old.HIGH + old.DRAWDOWN + old.VOL,
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
        "enhanced_carry_xirr_score", "enhanced_goal_score", "future_xirr",
        "future_shortfall", "future_drawdown", *old.CORE]))
    panel = pd.read_csv(PANEL, usecols=needed, low_memory=False)
    p = protocol()
    dates = set(p["initial_history_dates"] + p["development_selection_dates"]
                + p["clean_holdout_dates"] + p["exposed_diagnostic_dates"])
    if set(panel.decision_date) != dates or len(panel) != 601730:
        raise ValueError("authoritative deep panel mismatch")
    if not (pd.to_datetime(panel.endpoint).gt(pd.to_datetime(panel.decision_date)).all()
            and pd.to_datetime(panel.endpoint).le(pd.Timestamp("2026-09-18")).all()):
        raise ValueError("endpoint leakage")
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
    # Seal final labels until after the development selection has been written.
    sealed = panel.decision_date.isin(p["clean_holdout_dates"] + p["exposed_diagnostic_dates"])
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
        "current_fundamentals_used": False, "provider_split_source": "reacquired Yahoo ledger",
        "provider_failed_lookups_quarantined": 104}, indent=2), encoding="utf-8")


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
    worst_short = float((prof.target_shortfall_top20_new-prof.target_shortfall_top20_old).max())
    worst_hit = float((prof.target_achievement_top20_new-prof.target_achievement_top20_old).min())
    # Only bounded/robust metrics enter selection. Mean XIRR is reporting only.
    utility = (2*-d.target_shortfall_top20 + 1.5*d.target_achievement_top20
               + .8*d.median_xirr_top20 + .8*d.ndcg20 + .5*d.pairwise_accuracy
               + .35*d.rank_ic + .4*d.mean_asset_drawdown_top20)
    eligible = (d.coverage >= -.001 and d.target_shortfall_top20 <= .005
                and d.mean_asset_drawdown_top20 >= -.01 and d.median_xirr_top20 >= -.025
                and worst_short <= .02 and worst_hit >= -.15)
    return {**{f"delta_{k}": float(v) for k,v in d.items()}, "utility": float(utility),
            "eligible": bool(eligible), "worst_profile_shortfall_delta": worst_short,
            "worst_profile_achievement_delta": worst_hit}


def development():
    if (OUT / "locked_selection.json").exists():
        raise FileExistsError("selection already locked")
    panel = pd.read_pickle(OUT / "prepared.pkl.gz", compression="gzip")
    dates = protocol()["development_selection_dates"]
    baseline_path = OUT / "development_baseline.pkl.gz"
    if baseline_path.exists():
        base = pd.read_pickle(baseline_path, compression="gzip")
    else:
        base = baseline(panel, dates)
        base.to_pickle(baseline_path, compression="gzip")
    bm = hist.evaluate(base, "champion_score")
    bm.to_csv(OUT / "development_champion_profiles.csv", index=False)
    rows = []
    # Search feature families, target definitions, and regularization. The
    # strongest fits then receive a restrained score/age blend search.
    for recipe in ("age", "duration", "high_duration", "full_risk", "no_goal_risk"):
        cols = RECIPES[recipe]
        for label in ("utility4",):
            for pname in ("top20",):
                params = PARAMS[pname]
                key = f"{recipe}|{label}|{pname}"
                scored = predict(panel, dates, cols, label, params, compact=True)
                frame = base.drop(columns=["ranker_score"]).merge(
                    scored, on=["isin", "decision_date", "profile_name"], validate="one_to_one")
                for w in (.60, .67, .73):
                    for alpha in (.35, .65, 1.0):
                        for penalty in (0, .10):
                            frame["candidate_score"] = candidate_score(frame, w, alpha, penalty)
                            m = hist.evaluate(frame, "candidate_score")
                            rows.append({"candidate":key,"goal_weight":w,"alpha":alpha,"age_penalty":penalty,
                                         **metric_deltas(m,bm)})
                pd.DataFrame(rows).to_csv(OUT / "development_tournament.partial.csv", index=False)
    table = pd.DataFrame(rows).sort_values(["eligible","utility"],ascending=[False,False])
    table.to_csv(OUT / "development_tournament.csv", index=False)
    winner = table.iloc[0]
    record = {"winner": {k: (bool(v) if k=="eligible" else float(v) if isinstance(v,(np.floating,float)) else str(v))
                         for k,v in winner.items()}, "selection_dates": dates,
              "holdout_dates": protocol()["clean_holdout_dates"],
              "exposed_diagnostic_dates": protocol()["exposed_diagnostic_dates"],
              "protocol_sha256":digest(PROTOCOL), "panel_sha256":digest(PANEL),
              "development_tournament_sha256":digest(OUT / "development_tournament.csv"),
              "holdout_evaluated":False, "selection_uses_holdout":False,
              "selection_uses_exposed_2025":False}
    (OUT / "locked_selection.json").write_text(json.dumps(record,indent=2),encoding="utf-8")


def final():
    lockpath = OUT / "locked_selection.json"
    lock = json.loads(lockpath.read_text(encoding="utf-8"))
    if lock["holdout_evaluated"] or digest(OUT / "development_tournament.csv") != lock["development_tournament_sha256"]:
        raise ValueError("invalid selection lock")
    if (OUT / "holdout_profiles.csv").exists():
        raise FileExistsError("holdout already evaluated")
    panel = pd.read_pickle(OUT / "prepared.pkl.gz",compression="gzip")
    final_dates = lock["holdout_dates"] + lock["exposed_diagnostic_dates"]
    actual = pd.read_csv(PANEL, usecols=["isin","decision_date","profile_name","future_xirr","future_shortfall","future_drawdown"])
    actual = actual.loc[actual.decision_date.isin(final_dates)]
    panel = panel.merge(actual,on=["isin","decision_date","profile_name"],
                        how="left",validate="one_to_one",suffixes=("","_final"))
    for field in ("future_xirr","future_shortfall","future_drawdown"):
        panel[field] = panel[field].fillna(panel.pop(field + "_final"))
    winner = lock["winner"]
    recipe, label, pname = winner["candidate"].split("|")
    allprofiles = []
    for part, dates in (("clean_2024_holdout",lock["holdout_dates"]),
                        ("exposed_2025_diagnostic",lock["exposed_diagnostic_dates"])):
        base = baseline(panel,dates)
        challenger = predict(panel,dates,RECIPES[recipe],label,PARAMS[pname],compact=True)
        frame = base.drop(columns=["ranker_score"]).merge(
            challenger,on=["isin","decision_date","profile_name"],validate="one_to_one")
        frame["candidate_score"] = candidate_score(frame,float(winner["goal_weight"]),
                                                    float(winner["alpha"]),float(winner["age_penalty"]))
        oldm = hist.evaluate(frame,"champion_score")
        newm = hist.evaluate(frame,"candidate_score")
        joined = oldm.merge(newm,on=["decision_date","profile"],suffixes=("_champion","_challenger"))
        joined.insert(0,"partition",part)
        joined.to_csv(OUT / ("holdout_profiles.csv" if part.startswith("clean") else "exposed_profiles.csv"),index=False)
        frame[["isin","decision_date","profile_name","champion_score","candidate_score",
               "cagr_5y_observed","history_months"]].to_csv(OUT / f"{part}_scores.csv.gz",index=False)
        allprofiles.append(joined)
    lock["holdout_evaluated"] = True
    (OUT / "evaluation_record.json").write_text(json.dumps({"locked_selection_sha256":digest(lockpath),
        "winner":winner,"holdout_evaluated_once":True,"partitions": ["clean_2024_holdout","exposed_2025_diagnostic"]},indent=2),encoding="utf-8")


if __name__ == "__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("stage",choices=["prepare","development","final"])
    ap.add_argument("--output",type=Path,default=OUT,help="fresh research output directory")
    args=ap.parse_args()
    OUT=args.output.resolve()
    {"prepare":prepare,"development":development,"final":final}[args.stage]()
