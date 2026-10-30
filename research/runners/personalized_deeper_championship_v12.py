"""Resumable V12 development search; final evaluation delegates to locked v2 runner.

No 2024/2025 outcome is available in prepared.pkl.gz. This module never opens
the raw V12 panel in development. Final-stage reveal is guarded by a lock.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
import pandas as pd
import numpy as np
from research.runners import personalized_deeper_championship_v2 as d

RECIPES = ("age", "duration", "high_duration", "full_risk", "no_goal_risk", "risk_no_3y")
LABELS = ("utility4", "xirr4", "xirr8")
SETTINGS = ((.60, 1.0, 0.0), (.67, 1.0, 0.0), (.73, 1.0, 0.0),
            (.67, .35, 0.0), (.67, .65, 0.0), (.67, .65, .10))
AGE_ONLY = ((.67, 0.0, .02), (.67, 0.0, .05), (.67, 0.0, .10),
            (.67, 0.0, .20), (.67, 0.0, .30))


def predictions(panel, dates, key, partition):
    folder = d.OUT / "score_checkpoints"
    folder.mkdir(exist_ok=True)
    token = hashlib.sha256((partition + "|" + key).encode()).hexdigest()[:16]
    path = folder / f"{token}.pkl.gz"
    if path.exists():
        return pd.read_pickle(path, compression="gzip")
    recipe, label, pname = key.split("|")
    result = d.predict(panel, dates, d.RECIPES[recipe], label, d.PARAMS[pname], compact=True)
    temporary = path.with_name(path.name + ".tmp")
    result.to_pickle(temporary, compression="gzip")
    temporary.replace(path)
    return result


def score_settings(base, reference, scored, key, phase):
    frame = base.drop(columns=["ranker_score"]).merge(
        scored, on=["isin", "decision_date", "profile_name"], validate="one_to_one")
    rows = []
    settings = (AGE_ONLY if phase == "development" else SETTINGS + AGE_ONLY) if key == "age|utility4|top20" else SETTINGS
    for goal, alpha, penalty in settings:
        frame["candidate_score"] = d.candidate_score(frame, goal, alpha, penalty)
        measure = d.hist.evaluate(frame, "candidate_score")
        rows.append({"phase": phase, "candidate": key, "goal_weight": goal,
                     "alpha": alpha, "age_penalty": penalty,
                     **d.metric_deltas(measure, reference)})
    return rows


def development():
    if (d.OUT / "locked_selection.json").exists():
        raise FileExistsError("selection lock already exists")
    panel = pd.read_pickle(d.OUT / "prepared.pkl.gz", compression="gzip")
    p = d.protocol()
    post_dates = set(p["postlock_2024_diagnostics"] + p["untouched_final_dates"] +
                     p["postfinal_2025_diagnostics"])
    sealed = panel.decision_date.isin(post_dates)
    assert panel.loc[sealed, ["future_xirr", "future_shortfall", "future_drawdown"]].isna().all().all()
    assert set(panel.decision_date) == set(p["initial_history_dates"] + p["development_selection_dates"] + list(post_dates))
    dates = p["development_selection_dates"]
    qdates = ["2020-03-31", "2021-03-31", "2022-03-31", "2023-03-31"]
    baseline_path = d.OUT / "development_baseline.pkl.gz"
    if baseline_path.exists():
        base = pd.read_pickle(baseline_path, compression="gzip")
    else:
        base = d.baseline(panel, dates)
        temp = baseline_path.with_name(baseline_path.name + ".tmp")
        base.to_pickle(temp, compression="gzip")
        temp.replace(baseline_path)
    base_measures = d.hist.evaluate(base, "champion_score")
    base_measures.to_csv(d.OUT / "development_champion_profiles.csv", index=False)
    base_q = base.loc[base.decision_date.isin(qdates)].copy()
    q_measures = d.hist.evaluate(base_q, "champion_score")

    qualification_path = d.OUT / "qualification_tournament.partial.csv"
    completed = pd.read_csv(qualification_path) if qualification_path.exists() else pd.DataFrame()
    completed_keys = set(completed.candidate) if len(completed) else set()
    rows = completed.to_dict("records") if len(completed) else []
    for recipe in RECIPES:
        for label in LABELS:
            key = f"{recipe}|{label}|top20"
            if key in completed_keys:
                continue
            scored = predictions(panel, qdates, key, "qualification")
            rows.extend(score_settings(base_q, q_measures, scored, key, "qualification"))
            pd.DataFrame(rows).to_csv(qualification_path, index=False)
            print("qualified", key, flush=True)
    qualification = pd.DataFrame(rows).sort_values(["eligible", "utility"], ascending=[False, False])
    qualification.to_csv(d.OUT / "qualification_tournament.csv", index=False)
    leaders = qualification.drop_duplicates("candidate")
    leaders.to_csv(d.OUT / "qualification_config_leaders.csv", index=False)
    # Three utility leaders plus high/risk family representatives prevent a
    # single recipe from monopolizing the full 16-date development stage.
    finalist_keys = leaders.head(3).candidate.tolist()
    for recipe in ("high_duration", "full_risk", "risk_no_3y"):
        item = leaders.loc[leaders.candidate.str.startswith(recipe + "|")].iloc[0].candidate
        if item not in finalist_keys:
            finalist_keys.append(item)
    finalist_keys = finalist_keys[:6]

    development_path = d.OUT / "development_tournament.partial.csv"
    completed = pd.read_csv(development_path) if development_path.exists() else pd.DataFrame()
    completed_keys = set(completed.candidate) if len(completed) else set()
    rows = completed.to_dict("records") if len(completed) else []
    for key in finalist_keys:
        if key in completed_keys:
            continue
        # Alpha-zero candidates are exact champion-score policy adjustments;
        # their ranker prediction is algebraically unused.
        scored = (base[["isin", "decision_date", "profile_name", "ranker_score"]].copy()
                  if key == "age|utility4|top20" else predictions(panel, dates, key, "development"))
        rows.extend(score_settings(base, base_measures, scored, key, "development"))
        pd.DataFrame(rows).to_csv(development_path, index=False)
        print("developed", key, flush=True)
    adjustments_path = d.OUT / "development_history_adjustments.csv"
    adjustments = pd.read_csv(adjustments_path)
    adjustment_rows = []
    for row in adjustments.to_dict("records"):
        row["candidate"] = f"score_adjustment|{row.pop('signal')}|none"
        row["age_penalty"] = row.pop("penalty")
        row["goal_weight"], row["alpha"], row["phase"] = .67, 0.0, "development"
        adjustment_rows.append(row)
    combinations_path = d.OUT / "development_age_downside_combinations.csv"
    combinations = pd.read_csv(combinations_path)
    for row in combinations.to_dict("records"):
        row["candidate"] = "score_adjustment|age_downside|none"
        row["age_coefficient"] = row.pop("age_coefficient")
        row["age_penalty"] = row.pop("volatility_coefficient")
        row["goal_weight"], row["alpha"], row["phase"] = .67, 0.0, "development"
        adjustment_rows.append(row)
    table = pd.concat([pd.DataFrame(rows), pd.DataFrame(adjustment_rows)], ignore_index=True).sort_values(
        ["eligible", "utility"], ascending=[False, False])
    table.to_csv(d.OUT / "development_tournament.csv", index=False)
    winner = table.iloc[0]
    record = {
        "winner": {k: (bool(v) if k == "eligible" else float(v) if isinstance(v,(np.floating,float)) else str(v))
                   for k,v in winner.items()},
        "selection_dates": dates, "qualification_dates": qdates,
        "qualification_model_configs": len(RECIPES)*len(LABELS),
        "development_finalist_configs": finalist_keys,
        "postlock_2024_diagnostics": p["postlock_2024_diagnostics"],
        "untouched_final_dates": p["untouched_final_dates"],
        "postfinal_2025_diagnostics": p["postfinal_2025_diagnostics"],
        "protocol_sha256": d.digest(d.PROTOCOL), "panel_sha256": d.digest(d.PANEL),
        "prepared_sha256": d.digest(d.OUT / "prepared.pkl.gz"),
        "v12_integrity_audit_sha256": d.digest(d.PANEL.parent / "integrity_audit.json"),
        "qualification_tournament_sha256": d.digest(d.OUT / "qualification_tournament.csv"),
        "development_tournament_sha256": d.digest(d.OUT / "development_tournament.csv"),
        "development_history_adjustments_sha256": d.digest(adjustments_path),
        "development_age_downside_combinations_sha256": d.digest(combinations_path),
        "final_evaluated": False, "selection_uses_postlock_labels": False,
        "selection_uses_untouched_final": False,
        "search_rule": f"18 ranker configs on four annual qualification dates; {len(finalist_keys)} configs on all 16 development dates; six fixed blend settings plus five champion-only age penalties, {len(adjustments)} risk adjustments, and {len(combinations)} age/downside combinations; mean XIRR excluded",
        "production_mutated": False, "frozen_champion_mutated": False,
    }
    lock = d.OUT / "locked_selection.json"
    with lock.open("x", encoding="utf-8") as stream:
        json.dump(record, stream, indent=2)
    print("locked", winner.candidate, winner.utility, winner.eligible, flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", choices=["prepare", "development", "final", "audit"])
    parser.add_argument("--output", type=Path, default=d.OUT)
    args = parser.parse_args()
    d.OUT = args.output.resolve()
    if args.stage == "prepare": d.prepare()
    elif args.stage == "development": development()
    elif args.stage == "final": d.final()
    else:
        from research.runners import audit_personalized_deeper_championship_v2 as audit
        audit.d.OUT = d.OUT
        audit.run()
