"""Run the preregistered locked global personalized ranking tournament once."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
import os
from pathlib import Path
import platform
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import numpy as np
import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import PersonalizedEngine
from stock_ranker.personalized_data import load_history_book
from stock_research.personalized_global_tournament import (
    BASE_CANDIDATES,
    FEATURES,
    add_transparent_candidates,
    common_cohort_metrics,
    fit_fixed_models,
    global_existing_evidence,
    load_frozen_memberships,
    load_protocol,
    paired_candidate_deltas,
    profile_sensitivity,
)
from stock_research.personalized_validation import block_uncertainty


PROTOCOL = ROOT / "research/protocols/personalized_global_tournament_v1.json"
EXPECTED_PROTOCOL_SHA256 = "dc2113ef684607a293596a68998cc14260bef8526ce6eef5ce8704047131f326"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def build_rows(engine, book, facts, profiles, memberships, dates, *, locked):
    rows = []
    for day in dates:
        evidence = global_existing_evidence(book, facts, day).rename(
            columns={"global_existing_score": "production_score"}
        )
        for name, profile in profiles.items():
            rank = engine.rank(profile, day, evidence).rename(columns={"production_score": "global_existing_score"})
            rank = add_transparent_candidates(rank)
            endpoint = pd.Timestamp(day) + pd.DateOffset(months=profile.horizon_months)
            future = engine.simulate(profile, endpoint, months=profile.horizon_months)[
                ["isin", "xirr", "target_shortfall", "price_drawdown"]
            ].rename(columns={"xirr": "future_xirr", "target_shortfall": "future_shortfall",
                              "price_drawdown": "future_drawdown"})
            rank = rank.merge(future, on="isin", validate="one_to_one")
            rank = rank.loc[rank.isin.isin(memberships[profile.lookback_months])].copy()
            rank["decision_date"] = day
            rank["endpoint"] = endpoint.date().isoformat()
            rank["profile_name"] = name
            rank["partition"] = "LOCKED_TEST" if locked else "PRELOCK"
            rows.append(rank)
        print(json.dumps({"partition": "LOCKED_TEST" if locked else "PRELOCK", "decision_date": day,
                          "rows": sum(len(x) for x in rows)}), flush=True)
    return pd.concat(rows, ignore_index=True)


def current_rows(engine, book, facts, profiles, memberships, day):
    evidence = global_existing_evidence(book, facts, day).rename(columns={"global_existing_score": "production_score"})
    rows = []
    for name, profile in profiles.items():
        rank = engine.rank(profile, day, evidence).rename(columns={"production_score": "global_existing_score"})
        rank = add_transparent_candidates(rank)
        rank = rank.loc[rank.isin.isin(memberships[profile.lookback_months])].copy()
        rank["decision_date"], rank["profile_name"], rank["partition"] = day, name, "CURRENT"
        rows.append(rank)
    return pd.concat(rows, ignore_index=True)


def turnover(panel):
    rows = []
    for (profile, candidate), group in panel.groupby(["profile_name", "candidate"]):
        chosen = []
        for day, one in group.groupby("decision_date", sort=True):
            chosen.append((day, set(one.nlargest(20, "score").isin)))
        for (before_day, before), (day, after) in zip(chosen, chosen[1:]):
            rows.append({"profile": profile, "candidate": candidate, "from_date": before_day,
                         "date": day, "top20_replacement_fraction": 1 - len(before & after) / 20})
    return pd.DataFrame(rows)


def long_scores(panel):
    return panel.melt(id_vars=["decision_date", "profile_name", "isin"], value_vars=BASE_CANDIDATES,
                      var_name="candidate", value_name="score")


def classify(summary: pd.DataFrame, metrics: pd.DataFrame) -> list[dict]:
    indexed = summary.set_index("candidate")
    by_date = metrics.groupby(["decision_date", "candidate"], as_index=False).mean(numeric_only=True)
    decisions = []
    professor = indexed.loc["professor_style_score"]
    existing = indexed.loc["global_existing_score"]
    for candidate in BASE_CANDIDATES:
        row = indexed.loc[candidate]
        if candidate in {"professor_style_score", "global_existing_score"}:
            status, reason = "RESEARCH ONLY", "Locked comparison baseline; not a promotion candidate."
        elif candidate == "xirr_score" and abs(row.rank_ic - professor.rank_ic) < .005:
            status, reason = "FAIL", "Economically redundant with professor profit/loss and no material locked Rank IC separation."
        else:
            shortfall = row.target_shortfall_top20 < min(professor.target_shortfall_top20, existing.target_shortfall_top20)
            ic = row.rank_ic >= min(professor.rank_ic, existing.rank_ic)
            drawdown = row.mean_asset_drawdown_top20 >= min(professor.mean_asset_drawdown_top20,
                                                            existing.mean_asset_drawdown_top20) - .03
            dates = by_date.loc[by_date.candidate.eq(candidate)].set_index("decision_date")
            prof_dates = by_date.loc[by_date.candidate.eq("professor_style_score")].set_index("decision_date")
            exist_dates = by_date.loc[by_date.candidate.eq("global_existing_score")].set_index("decision_date")
            both_dates = ((dates.target_shortfall_top20 < prof_dates.target_shortfall_top20)
                          & (dates.target_shortfall_top20 < exist_dates.target_shortfall_top20)).all()
            if shortfall and ic and drawdown and both_dates:
                status = "PASS FOR FURTHER VALIDATION"
                reason = "Cleared the preregistered locked utility, ranking, date-consistency, and drawdown gates."
            elif shortfall or row.rank_ic > max(professor.rank_ic, existing.rank_ic):
                status = "RESEARCH ONLY"
                reason = "Useful locked signal, but evidence is mixed or limited to two independent decision-date blocks."
            else:
                status = "FAIL"
                reason = "Did not improve the locked investor-utility or ranking evidence over the simple baselines."
        decisions.append({"candidate": candidate.removesuffix("_score"), "status": status, "reason": reason})
    decisions.extend([
        {"candidate": "quality_valuation_fundamentals", "status": "INSUFFICIENT EVIDENCE",
         "reason": "Equivalent effective-dated PIT fundamentals are unavailable for the locked historical decisions."},
        {"candidate": "sector_relative_models", "status": "INSUFFICIENT EVIDENCE",
         "reason": "Historical PIT sector intervals remain unavailable; current sectors were not back-projected."},
        {"candidate": "whole_share_amount_sensitive", "status": "INSUFFICIENT EVIDENCE",
         "reason": "A complete executable raw-price/action/volume ledger is unavailable across the frozen global cohorts."},
        {"candidate": "xgboost_catboost_interpretml", "status": "INSUFFICIENT EVIDENCE",
         "reason": "Optional libraries were absent; adding parallel tree learners after lock design would add multiplicity without independent features."},
    ])
    return decisions


def run(args) -> None:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("fresh tournament output required")
    output.mkdir(parents=True)
    started = time.perf_counter()
    if digest(PROTOCOL) != EXPECTED_PROTOCOL_SHA256:
        raise ValueError("preregistered protocol fingerprint drift")
    protocol, profiles = load_protocol(PROTOCOL)
    memberships = load_frozen_memberships(args.frozen_root.resolve(), protocol["frozen_cohort_fingerprint"])
    protected = [ROOT / "data/company_facts/accepted_state.json", ROOT / "data/live_market/accepted_state.json"]
    protected_before = {str(path.relative_to(ROOT)): digest(path) for path in protected}
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    book, history_hashes = load_history_book(facts, args.history_cache.resolve())
    engine = PersonalizedEngine(book, cache_size=96)

    prelock = build_rows(engine, book, facts, profiles, memberships, protocol["prelock_decision_dates"], locked=False)
    # The first construction of these rows is the one-time lockbox opening.
    locked = build_rows(engine, book, facts, profiles, memberships, protocol["locked_test_decision_dates"], locked=True)
    current = current_rows(engine, book, facts, profiles, memberships, "2026-09-18")
    combined = pd.concat([locked.assign(_target="locked"), current.assign(_target="current")], ignore_index=True)
    predicted, model_audit = fit_fixed_models(prelock, combined, protocol)
    locked = predicted.loc[predicted._target.eq("locked")].drop(columns="_target")
    current = predicted.loc[predicted._target.eq("current")].drop(columns="_target")

    metrics = common_cohort_metrics(locked)
    summary = metrics.groupby("candidate", as_index=False).mean(numeric_only=True)
    deltas = paired_candidate_deltas(metrics)
    uncertainty = block_uncertainty(metrics)
    sensitivity = profile_sensitivity(current)
    correlations = []
    correlation_columns = list(dict.fromkeys([*BASE_CANDIDATES, *FEATURES]))
    for (day, profile), group in locked.groupby(["decision_date", "profile_name"]):
        corr = group[correlation_columns].corr(method="spearman")
        for left in corr.columns:
            for right in corr.columns[corr.columns.get_loc(left) + 1:]:
                correlations.append({"decision_date": day, "profile": profile, "left": left,
                                     "right": right, "spearman": corr.loc[left, right]})
    long = long_scores(locked)
    turnover_frame = turnover(long)
    decisions = classify(summary, metrics)

    protocol_snapshot = dict(protocol)
    protocol_snapshot["protocol_sha256"] = EXPECTED_PROTOCOL_SHA256
    protocol_snapshot["locked_test_opened"] = True
    write_json(output / "protocol.json", protocol_snapshot)
    prelock.to_csv(output / "prelock_panel.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    locked.to_csv(output / "locked_predictions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    current.to_csv(output / "current_profile_rankings.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    metrics.to_csv(output / "locked_metrics.csv", index=False, lineterminator="\n")
    summary.to_csv(output / "candidate_summary.csv", index=False, lineterminator="\n")
    deltas.to_csv(output / "paired_deltas.csv", index=False, lineterminator="\n")
    uncertainty.to_csv(output / "uncertainty.csv", index=False, lineterminator="\n")
    sensitivity.to_csv(output / "profile_sensitivity.csv", index=False, lineterminator="\n")
    pd.DataFrame(correlations).to_csv(output / "redundancy.csv", index=False, lineterminator="\n")
    turnover_frame.to_csv(output / "turnover.csv", index=False, lineterminator="\n")
    write_json(output / "model_audit.json", model_audit)
    write_json(output / "candidate_decisions.json", decisions)
    write_json(output / "tool_decisions.json", {
        "adopted": ["scikit-learn Ridge", "scikit-learn HistGradientBoostingRegressor", "LightGBM LGBMRanker"],
        "rejected_or_deferred": {
            "XGBoost": "Not installed; another LambdaMART implementation would add model multiplicity without new evidence.",
            "CatBoost": "Not installed; no categorical PIT feature family exists in this tournament.",
            "InterpretML EBM": "Not installed; shallow histogram boosting supplies the preregistered nonlinear check.",
            "Qlib DoubleEnsemble": "Deferred because the five-feature panel lacks the broad noisy feature set its sample reweighting/selection is intended to address."
        },
        "official_references": [
            "https://lightgbm.readthedocs.io/en/stable/pythonapi/lightgbm.LGBMRanker.html",
            "https://xgboost.readthedocs.io/en/stable/tutorials/learning_to_rank.html",
            "https://catboost.ai/en/docs/concepts/loss-functions-ranking",
            "https://interpret.ml/docs/python/api/ExplainableBoostingRegressor.html"
        ]
    })
    protected_after = {str(path.relative_to(ROOT)): digest(path) for path in protected}
    if protected_before != protected_after:
        raise ValueError("protected state changed")
    elapsed = time.perf_counter() - started
    try:
        import psutil
        memory = psutil.Process().memory_info().rss
    except ImportError:
        memory = None
    assessment = {
        "schema_version": "personalized_global_tournament_result_v1",
        "locked_test_opened_once": True,
        "locked_test_dates": protocol["locked_test_decision_dates"],
        "candidate_decisions": decisions,
        "global_only": True,
        "historical_sector_used": False,
        "frozen_cohort_fingerprint": protocol["frozen_cohort_fingerprint"],
        "protected_state_unchanged": True,
        "runtime_seconds": elapsed,
        "resident_memory_bytes": memory,
        "python": platform.python_version(),
        "overall": "PARTIAL",
        "exact_next_milestone": "Prospectively validate the locked global candidates on new post-2026-09-18 outcomes; acquire PIT sector intervals separately before any sector-relative tournament."
    }
    write_json(output / "assessment.json", assessment)
    write_json(output / "inputs.json", {
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "frozen_manifest_sha256": digest(args.frozen_root.resolve() / "manifest.json"),
        "history_fingerprint": sha256(json.dumps(history_hashes, sort_keys=True).encode()).hexdigest(),
        "company_fact_fingerprint": load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).manifest["fingerprint"],
        "protected_state": protected_before,
        "source_sha256": {
            "research/runners/run_personalized_global_tournament.py": digest(Path(__file__)),
            "src/stock_research/personalized_global_tournament.py": digest(
                ROOT / "src/stock_research/personalized_global_tournament.py"
            ),
        },
    })
    artifacts = [{"path": path.name, "size": path.stat().st_size, "sha256": digest(path)}
                 for path in sorted(output.iterdir()) if path.is_file() and path.name != "assessment.json"]
    manifest = {"deterministic_artifacts": artifacts,
                "fingerprint": sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest(),
                "observational_artifacts": ["assessment.json"]}
    write_json(output / "manifest.json", manifest)
    print(json.dumps(assessment, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--history-cache", type=Path, required=True)
    run(parser.parse_args())
