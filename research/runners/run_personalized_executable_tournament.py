"""Run the preregistered whole-share personalization tournament."""
from __future__ import annotations

import argparse
from dataclasses import replace
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
from stock_research.personalized_executable_tournament import (
    BASE_CANDIDATES, FEATURES, ExecutableHistoryBook, common_metrics,
    fit_fixed_models, load_protocol, rank_executable,
)
from stock_research.personalized_global_tournament import global_existing_evidence, load_frozen_memberships
from stock_research.personalized_validation import block_uncertainty


PROTOCOL = ROOT / "research/protocols/personalized_executable_tournament_v1.json"
EXPECTED_PROTOCOL_SHA256 = "55c4314fd9d6a2ecf8644669665d1de8d557f0e085dbf5a20175e27c86c0a916"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def build_rows(executable, fractional_engine, fractional_book, facts, profiles, memberships, dates, partition,
               checkpoint_root: Path):
    rows = []
    for day in dates:
        checkpoint = checkpoint_root / f"{partition.lower()}-{day}.csv.gz"
        if checkpoint.is_file():
            frame = pd.read_csv(checkpoint)
            rows.append(frame)
            print(json.dumps({"partition": partition, "decision_date": day,
                              "rows": sum(len(item) for item in rows), "checkpoint": "REUSED"}), flush=True)
            continue
        evidence = global_existing_evidence(fractional_book, facts, day)
        day_rows = []
        for name, profile in profiles.items():
            rank = rank_executable(executable, profile, day, evidence)
            fractional = fractional_engine.rank(replace(profile, whole_shares=False), day)[
                ["isin", "professor_style_score"]
            ].rename(columns={"professor_style_score": "fractional_professor_score"})
            rank = rank.merge(fractional, on="isin", how="left", validate="one_to_one")
            endpoint = pd.Timestamp(day) + pd.DateOffset(months=profile.horizon_months)
            future = executable.simulate(
                profile, endpoint, months=profile.horizon_months, mode="enhanced_carry", include_journal=False
            )[["isin", "xirr", "target_shortfall", "price_drawdown"]].rename(columns={
                "xirr": "future_xirr", "target_shortfall": "future_shortfall",
                "price_drawdown": "future_drawdown",
            })
            rank = rank.merge(future, on="isin", validate="one_to_one")
            rank = rank.loc[rank["isin"].isin(memberships[profile.lookback_months])].copy()
            rank["decision_date"], rank["endpoint"] = day, endpoint.date().isoformat()
            rank["profile_name"], rank["partition"] = name, partition
            rank = rank.drop(columns=["journal"], errors="ignore")
            day_rows.append(rank)
        frame = pd.concat(day_rows, ignore_index=True)
        frame.to_csv(checkpoint, index=False, compression={"method": "gzip", "mtime": 0})
        rows.append(frame)
        print(json.dumps({"partition": partition, "decision_date": day,
                          "rows": sum(len(frame) for frame in rows)}), flush=True)
    return pd.concat(rows, ignore_index=True)


def candidate_summary(metrics):
    return metrics.groupby("candidate", as_index=False).mean(numeric_only=True)


def paired_deltas(metrics, references=("professor_whole_share_score", "global_existing_score")):
    indexed = metrics.set_index(["decision_date", "profile", "candidate"])
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
                if metric == "target_shortfall_top20":
                    delta = -delta
                rows.append({"candidate": candidate, "reference": reference, "metric": metric,
                             "blocks": len(delta), "mean_improvement": delta.mean(),
                             "median_improvement": delta.median(), "win_rate": delta.gt(0).mean()})
    return pd.DataFrame(rows)


def sensitivity(current):
    base = current.loc[current.profile_name.eq("base7500")].set_index("isin")
    rows = []
    for profile, group in current.groupby("profile_name"):
        other = group.set_index("isin")
        for candidate in BASE_CANDIDATES:
            pair = pd.concat([base[candidate].rename("base"), other[candidate].rename("other")], axis=1).dropna()
            top_base, top_other = set(pair.nlargest(20, "base").index), set(pair.nlargest(20, "other").index)
            rows.append({"profile": profile, "candidate": candidate, "pairs": len(pair),
                         "spearman_with_base": pair.base.corr(pair.other, method="spearman"),
                         "top20_overlap": len(top_base & top_other) / max(len(top_base), 1)})
    return pd.DataFrame(rows)


def execution_diagnostics(panel):
    available = panel.loc[panel.status.eq("AVAILABLE")]
    return available.groupby(["partition", "decision_date", "profile_name"], as_index=False).agg(
        securities=("isin", "size"), mean_cash_utilization=("cash_utilization", "mean"),
        median_cash_utilization=("cash_utilization", "median"),
        mean_unaffordable_rate=("unaffordable_rate", "mean"),
        fully_unaffordable=("execution_count", lambda x: int(x.eq(0).sum())),
        mean_execution_count=("execution_count", "mean"),
        mean_residual_cash=("residual_cash", "mean"),
        mean_professor_excluded_cash=("unused_cash_excluded_by_professor", "mean"),
    )


def amount_by_price(current):
    base = current.loc[current.profile_name.eq("base7500")].set_index("isin")
    rows = []
    for profile in ("amount1000", "amount50000"):
        other = current.loc[current.profile_name.eq(profile)].set_index("isin")
        pair = base[["terminal_price", "enhanced_carry_xirr_score", "professor_whole_share_score"]].join(
            other[["enhanced_carry_xirr_score", "professor_whole_share_score", "cash_utilization", "unaffordable_rate"]],
            how="inner", lsuffix="_base", rsuffix="_other"
        ).dropna()
        pair["price_bin"] = pd.qcut(pair.terminal_price, 4, labels=["Q1 cheapest", "Q2", "Q3", "Q4 most expensive"])
        for candidate in ("enhanced_carry_xirr_score", "professor_whole_share_score"):
            pair["rank_base"] = pair[candidate + "_base"].rank(pct=True)
            pair["rank_other"] = pair[candidate + "_other"].rank(pct=True)
            for price_bin, group in pair.groupby("price_bin", observed=True):
                rows.append({"profile": profile, "candidate": candidate, "price_bin": str(price_bin),
                             "n": len(group), "mean_absolute_percentile_rank_change":
                             (group.rank_base - group.rank_other).abs().mean(),
                             "mean_cash_utilization": group.cash_utilization.mean(),
                             "mean_unaffordable_rate": group.unaffordable_rate.mean()})
    return pd.DataFrame(rows)


def turnover(panel):
    long = panel.melt(id_vars=["decision_date", "profile_name", "isin"], value_vars=BASE_CANDIDATES,
                      var_name="candidate", value_name="score")
    rows = []
    for (profile, candidate), group in long.groupby(["profile_name", "candidate"]):
        chosen = [(day, set(one.nlargest(20, "score")["isin"]))
                  for day, one in group.groupby("decision_date", sort=True)]
        for (before_day, before), (day, after) in zip(chosen, chosen[1:]):
            rows.append({"profile": profile, "candidate": candidate, "from_date": before_day, "date": day,
                         "top20_replacement_fraction": 1 - len(before & after) / 20})
    return pd.DataFrame(rows)


def classify(validation_summary):
    indexed = validation_summary.set_index("candidate")
    professor, existing = indexed.loc["professor_whole_share_score"], indexed.loc["global_existing_score"]
    decisions = []
    for candidate in BASE_CANDIDATES:
        row = indexed.loc[candidate]
        if candidate in {"professor_whole_share_score", "global_existing_score"}:
            status, reason = "RESEARCH ONLY", "Validation comparison baseline."
        else:
            useful = (row.target_shortfall_top20 < min(professor.target_shortfall_top20, existing.target_shortfall_top20)
                      or row.rank_ic > max(professor.rank_ic, existing.rank_ic))
            status = "RESEARCH ONLY" if useful else "FAIL"
            reason = ("Directionally useful on the preregistered validation dates; exposed test remains supplementary."
                      if useful else "Did not improve validation ranking or investor utility over the simple references.")
        decisions.append({"candidate": candidate.removesuffix("_score"), "status": status, "reason": reason})
    decisions.extend([
        {"candidate": "transaction_cost_model", "status": "INSUFFICIENT EVIDENCE",
         "reason": "Broker and statutory schedules are time-varying; no single historical fee contract was imposed."},
        {"candidate": "liquidity_constrained_model", "status": "INSUFFICIENT EVIDENCE",
         "reason": "The frozen cache has no complete historical volume series."},
        {"candidate": "sector_relative_models", "status": "INSUFFICIENT EVIDENCE",
         "reason": "Historical PIT sector intervals remain unavailable."},
    ])
    return decisions


def run(args):
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("fresh executable tournament output required")
    output.mkdir(parents=True)
    args.checkpoint_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    if digest(PROTOCOL) != EXPECTED_PROTOCOL_SHA256:
        raise ValueError("preregistered executable protocol fingerprint drift")
    protocol, profiles = load_protocol(PROTOCOL)
    memberships = load_frozen_memberships(args.frozen_root, protocol["frozen_cohort_fingerprint"])
    protected = [ROOT / "data/company_facts/accepted_state.json", ROOT / "data/live_market/accepted_state.json"]
    protected_before = {str(path.relative_to(ROOT)): digest(path) for path in protected}
    snapshot = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts"))
    facts = snapshot.facts
    identities = facts.loc[facts["isin"].isin(set.union(*memberships.values())), ["isin", "ticker"]]
    executable = ExecutableHistoryBook(identities, args.history_cache, args.split_root,
                                       as_of_date=protocol["current_profile_date"])
    fractional_book, history_hashes = load_history_book(facts, args.history_cache)
    fractional_engine = PersonalizedEngine(fractional_book, cache_size=128)

    training = build_rows(executable, fractional_engine, fractional_book, facts, profiles, memberships,
                          protocol["training_decision_dates"], "TRAIN", args.checkpoint_root)
    validation_base = build_rows(executable, fractional_engine, fractional_book, facts, profiles, memberships,
                                 protocol["validation_decision_dates"], "VALIDATION", args.checkpoint_root)
    validation, validation_audit = fit_fixed_models(training, validation_base, protocol)
    development = pd.concat([training, validation_base], ignore_index=True)
    supplementary_base = build_rows(executable, fractional_engine, fractional_book, facts, profiles, memberships,
                                    protocol["supplementary_exposed_test_dates"], "SUPPLEMENTARY_EXPOSED_TEST",
                                    args.checkpoint_root)
    current_base = build_rows(executable, fractional_engine, fractional_book, facts, profiles, memberships,
                              [protocol["current_profile_date"]], "CURRENT", args.checkpoint_root)
    combined, final_audit = fit_fixed_models(
        development, pd.concat([supplementary_base.assign(_part="supplementary"),
                                current_base.assign(_part="current")], ignore_index=True), protocol
    )
    supplementary = combined.loc[combined._part.eq("supplementary")].drop(columns="_part")
    current = combined.loc[combined._part.eq("current")].drop(columns="_part")
    validation_metrics, supplementary_metrics = common_metrics(validation), common_metrics(supplementary)
    validation_summary, supplementary_summary = candidate_summary(validation_metrics), candidate_summary(supplementary_metrics)
    decisions = classify(validation_summary)
    all_base = pd.concat([training, validation_base, supplementary_base, current_base], ignore_index=True)

    fractional_rows = []
    for partition, frame in (("VALIDATION", validation), ("SUPPLEMENTARY_EXPOSED_TEST", supplementary)):
        for (day, profile), group in frame.groupby(["decision_date", "profile_name"]):
            pair = group[["fractional_professor_score", "professor_whole_share_score"]].dropna()
            top_fractional = set(pair.nlargest(20, "fractional_professor_score").index)
            top_whole = set(pair.nlargest(20, "professor_whole_share_score").index)
            fractional_rows.append({"partition": partition, "decision_date": day, "profile": profile,
                                    "n": len(pair), "spearman": pair.corr(method="spearman").iloc[0, 1],
                                    "top20_overlap": len(top_fractional & top_whole) / max(len(top_fractional), 1)})

    prior_summary = pd.read_csv(args.previous_tournament / "candidate_summary.csv")
    previous_cluster = prior_summary.loc[prior_summary.candidate.eq("cluster_rank_aggregation_score")].iloc[0].to_dict()
    comparison = {
        "previous_fractional_cluster": previous_cluster,
        "new_validation_cluster": validation_summary.loc[validation_summary.candidate.eq("cluster_rank_aggregation_score")].iloc[0].to_dict(),
        "new_supplementary_cluster": supplementary_summary.loc[supplementary_summary.candidate.eq("cluster_rank_aggregation_score")].iloc[0].to_dict(),
    }
    for value in comparison.values():
        for key, item in list(value.items()):
            if isinstance(item, (np.integer, np.floating)):
                value[key] = item.item()

    protocol_snapshot = dict(protocol); protocol_snapshot["protocol_sha256"] = EXPECTED_PROTOCOL_SHA256
    write_json(output / "protocol.json", protocol_snapshot)
    training.to_csv(output / "training_panel.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    validation.to_csv(output / "validation_predictions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    supplementary.to_csv(output / "supplementary_predictions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    current.to_csv(output / "current_profile_rankings.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    for name, frame in {
        "validation_metrics.csv": validation_metrics,
        "validation_summary.csv": validation_summary,
        "supplementary_metrics.csv": supplementary_metrics,
        "supplementary_summary.csv": supplementary_summary,
        "validation_paired_deltas.csv": paired_deltas(validation_metrics),
        "supplementary_paired_deltas.csv": paired_deltas(supplementary_metrics),
        "validation_uncertainty.csv": block_uncertainty(validation_metrics),
        "supplementary_uncertainty.csv": block_uncertainty(supplementary_metrics),
        "profile_sensitivity.csv": sensitivity(current),
        "execution_diagnostics.csv": execution_diagnostics(all_base),
        "amount_effect_by_price.csv": amount_by_price(current),
        "fractional_vs_whole_professor.csv": pd.DataFrame(fractional_rows),
        "supplementary_turnover.csv": turnover(supplementary),
    }.items():
        frame.to_csv(output / name, index=False, lineterminator="\n")
    write_json(output / "model_audit.json", {"validation_fit": validation_audit, "final_fit": final_audit})
    write_json(output / "candidate_decisions.json", decisions)
    write_json(output / "previous_cluster_comparison.json", comparison)
    write_json(output / "workbook_benchmark.json", {
        "workbook_sha256": protocol["workbook_sha256"], "amount": 7500, "lookback_months": 36,
        "interval_days": 30, "target_cagr": .2, "purchase_formula": "ROUNDDOWN(amount / execution_price, 0)",
        "rank_basis": "profit/loss divided by actual amount spent", "source_is_instruction": False,
    })
    protected_after = {str(path.relative_to(ROOT)): digest(path) for path in protected}
    if protected_before != protected_after:
        raise ValueError("protected state changed")
    split_audit = pd.read_csv(args.split_root / "acquisition_audit.csv")
    assessment = {
        "schema_version": "personalized_executable_tournament_result_v1",
        "overall": "PARTIAL",
        "evidence_boundary": "Validation is pre-existing matured development evidence; 2025 locked outcomes were previously exposed and are supplementary only.",
        "candidate_decisions": decisions,
        "frozen_cohort_fingerprint": protocol["frozen_cohort_fingerprint"],
        "split_acquisition_status_counts": split_audit.status.value_counts().sort_index().to_dict(),
        "executable_identity_count": len(executable.arrays), "quarantined_identity_count": len(executable.errors),
        "transaction_cost_model": None, "liquidity_model": None, "historical_sector_used": False,
        "protected_state_unchanged": True, "runtime_seconds": time.perf_counter() - started,
        "resident_memory_bytes": None, "python": platform.python_version(),
        "exact_next_milestone": "Prospectively validate the frozen executable candidates on new post-2026-09-18 outcomes; separately acquire historical PIT sector intervals.",
    }
    try:
        import psutil
        assessment["resident_memory_bytes"] = psutil.Process().memory_info().rss
    except ImportError:
        pass
    write_json(output / "assessment.json", assessment)
    write_json(output / "inputs.json", {
        "protocol_sha256": EXPECTED_PROTOCOL_SHA256,
        "frozen_manifest_sha256": digest(args.frozen_root / "manifest.json"),
        "history_fingerprint": sha256(json.dumps(history_hashes, sort_keys=True).encode()).hexdigest(),
        "split_audit_sha256": digest(args.split_root / "acquisition_audit.csv"),
        "split_ledger_sha256": digest(args.split_root / "split_ledger.csv"),
        "workbook_sha256": digest(args.workbook), "company_fact_fingerprint": snapshot.manifest["fingerprint"],
        "protected_state": protected_before,
        "source_sha256": {
            "runner": digest(Path(__file__)),
            "module": digest(ROOT / "src/stock_research/personalized_executable_tournament.py"),
        },
    })
    artifacts = [{"path": path.name, "size": path.stat().st_size, "sha256": digest(path)}
                 for path in sorted(output.iterdir()) if path.is_file() and path.name != "assessment.json"]
    write_json(output / "manifest.json", {
        "deterministic_artifacts": artifacts,
        "fingerprint": sha256(json.dumps(artifacts, sort_keys=True).encode()).hexdigest(),
        "observational_artifacts": ["assessment.json"],
    })
    print(json.dumps(assessment, indent=2, sort_keys=True), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--history-cache", type=Path, required=True)
    parser.add_argument("--split-root", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--previous-tournament", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    run(parser.parse_args())
