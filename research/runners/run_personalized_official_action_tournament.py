"""Run the preregistered official-action-aware personalization rerun."""
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
sys.path.insert(0, str(ROOT))
for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[name] = "1"

import numpy as np
import pandas as pd

from research.runners.run_personalized_executable_tournament import (
    amount_by_price, build_rows, candidate_summary, execution_diagnostics,
    paired_deltas, sensitivity, turnover,
)
from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized import PersonalizedEngine
from stock_ranker.personalized_data import load_history_book
from stock_research.personalized_executable_tournament import (
    BASE_CANDIDATES, common_metrics, fit_fixed_models, load_protocol,
)
from stock_research.personalized_global_tournament import load_frozen_memberships
from stock_research.personalized_official_actions import OfficialActionHistoryBook
from stock_research.personalized_validation import block_uncertainty


PROTOCOL = ROOT / "research/protocols/personalized_official_action_tournament_v1.json"
EXPECTED_PROTOCOL_SHA256 = "4ada6978b7ed14de41fb9a550782553d0d65a25f865936965ef24c13123395fd"


def digest(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def classify(summary: pd.DataFrame) -> list[dict]:
    indexed = summary.set_index("candidate")
    professor = indexed.loc["professor_whole_share_score"]
    existing = indexed.loc["global_existing_score"]
    decisions = []
    for candidate in BASE_CANDIDATES:
        row = indexed.loc[candidate]
        if candidate in {"professor_whole_share_score", "global_existing_score"}:
            status, reason = "RESEARCH ONLY", "Fixed comparison baseline."
        else:
            useful = (row.target_shortfall_top20 < min(professor.target_shortfall_top20, existing.target_shortfall_top20)
                      or row.rank_ic > max(professor.rank_ic, existing.rank_ic))
            status = "RESEARCH ONLY" if useful else "FAIL"
            reason = ("Directionally useful on the unchanged validation dates."
                      if useful else "Did not improve validation rank or utility over both simple references.")
        decisions.append({"candidate": candidate.removesuffix("_score"), "status": status, "reason": reason})
    decisions.extend([
        {"candidate": "official_exact_date_sector_relative", "status": "SUPPLEMENTARY ONLY",
         "reason": "Exact official 2020-2022 observations support a retrospective diagnostic, with current-universe survivorship."},
        {"candidate": "transaction_cost_model", "status": "INSUFFICIENT EVIDENCE",
         "reason": "No single complete historical broker and statutory fee contract was supplied."},
        {"candidate": "liquidity_constrained_model", "status": "INSUFFICIENT EVIDENCE",
         "reason": "No complete historical order-book or volume evidence supports a reproducible cap."},
    ])
    return decisions


def run(args) -> None:
    output = args.output.resolve()
    if output.exists():
        raise FileExistsError("fresh official-action tournament output required")
    output.mkdir(parents=True)
    args.checkpoint_root.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    protocol_path = args.protocol or PROTOCOL
    expected_protocol = args.protocol_sha256 or EXPECTED_PROTOCOL_SHA256
    if digest(protocol_path) != expected_protocol:
        raise ValueError("preregistered official-action protocol fingerprint drift")
    protocol, profiles = load_protocol(protocol_path)
    memberships = load_frozen_memberships(args.frozen_root, protocol["frozen_cohort_fingerprint"])
    protected = [ROOT / "data/company_facts/accepted_state.json", ROOT / "data/live_market/accepted_state.json"]
    protected_before = {str(path.relative_to(ROOT)): digest(path) for path in protected}
    snapshot = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts"))
    facts = snapshot.facts
    identities = facts.loc[facts["isin"].isin(set.union(*memberships.values())), ["isin", "ticker"]]
    repairs_path = args.frozen_root / "terminal_repairs.csv"
    repairs = pd.read_csv(repairs_path)
    ledger_path = args.official_freeze / "normalized_official_action_ledger.csv.gz"
    ledger = pd.read_csv(ledger_path, low_memory=False)
    live_state = json.loads((ROOT / "data/live_market/accepted_state.json").read_text(encoding="utf-8"))
    live_path = ROOT / "data/live_market" / live_state["bundle_path"] / "live_market.csv"
    live = pd.read_csv(live_path, low_memory=False)
    executable = OfficialActionHistoryBook(
        identities, args.history_cache, args.split_root, ledger,
        as_of_date=protocol["current_profile_date"], terminal_repairs=repairs,
        terminal_raw_prices=live[["isin", "trade_date", "latest_price"]],
    )
    fractional_book, history_hashes = load_history_book(facts, args.history_cache, terminal_repairs=repairs)
    fractional_engine = PersonalizedEngine(fractional_book, cache_size=128)

    training = build_rows(executable, fractional_engine, fractional_book, facts, profiles, memberships,
                          protocol["training_decision_dates"], "TRAIN", args.checkpoint_root)
    validation_base = build_rows(executable, fractional_engine, fractional_book, facts, profiles, memberships,
                                 protocol["validation_decision_dates"], "VALIDATION", args.checkpoint_root)
    validation, validation_audit = fit_fixed_models(training, validation_base, protocol)
    development = pd.concat([training, validation_base], ignore_index=True)
    supplementary_base = build_rows(
        executable, fractional_engine, fractional_book, facts, profiles, memberships,
        protocol["supplementary_exposed_test_dates"], "SUPPLEMENTARY_EXPOSED_TEST", args.checkpoint_root,
    )
    current_base = build_rows(executable, fractional_engine, fractional_book, facts, profiles, memberships,
                              [protocol["current_profile_date"]], "CURRENT", args.checkpoint_root)
    combined, final_audit = fit_fixed_models(
        development,
        pd.concat([supplementary_base.assign(_part="supplementary"),
                   current_base.assign(_part="current")], ignore_index=True),
        protocol,
    )
    supplementary = combined.loc[combined._part.eq("supplementary")].drop(columns="_part")
    current = combined.loc[combined._part.eq("current")].drop(columns="_part")
    validation_metrics = common_metrics(validation)
    supplementary_metrics = common_metrics(supplementary)
    validation_summary = candidate_summary(validation_metrics)
    supplementary_summary = candidate_summary(supplementary_metrics)
    decisions = classify(validation_summary)
    all_base = pd.concat([training, validation_base, supplementary_base, current_base], ignore_index=True)

    fractional_rows = []
    for partition, frame in (("VALIDATION", validation), ("SUPPLEMENTARY_EXPOSED_TEST", supplementary)):
        for (day, profile), group in frame.groupby(["decision_date", "profile_name"]):
            pair = group[["isin", "fractional_professor_score", "professor_whole_share_score"]].dropna()
            top_fractional = set(pair.nlargest(20, "fractional_professor_score")["isin"])
            top_whole = set(pair.nlargest(20, "professor_whole_share_score")["isin"])
            fractional_rows.append({
                "partition": partition, "decision_date": day, "profile": profile, "n": len(pair),
                "spearman": pair.fractional_professor_score.corr(pair.professor_whole_share_score, method="spearman"),
                "top20_overlap": len(top_fractional & top_whole) / max(len(top_fractional), 1),
            })

    old_validation = pd.read_csv(args.previous_tournament / "validation_summary.csv")
    comparison = validation_summary.merge(
        old_validation, on="candidate", how="left", suffixes=("_official", "_old_yahoo_policy"), validate="one_to_one"
    )
    protocol_snapshot = dict(protocol)
    protocol_snapshot["protocol_sha256"] = expected_protocol
    write_json(output / "protocol.json", protocol_snapshot)
    training.to_csv(output / "training_panel.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    validation.to_csv(output / "validation_predictions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    supplementary.to_csv(output / "supplementary_predictions.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    current.to_csv(output / "current_profile_rankings.csv.gz", index=False, compression={"method": "gzip", "mtime": 0})
    frames = {
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
        "previous_policy_validation_comparison.csv": comparison,
        "executable_coverage.csv": pd.read_csv(args.official_freeze / "executable_coverage.csv"),
        "sector_pit_coverage.csv": pd.read_csv(args.official_freeze / "sector_pit_coverage.csv"),
        "sector_relative_supplementary_metrics.csv": pd.read_csv(args.official_freeze / "sector_relative_supplementary_metrics.csv"),
    }
    for name, frame in frames.items():
        frame.to_csv(output / name, index=False, lineterminator="\n")
    write_json(output / "model_audit.json", {"validation_fit": validation_audit, "final_fit": final_audit})
    write_json(output / "candidate_decisions.json", decisions)
    protected_after = {str(path.relative_to(ROOT)): digest(path) for path in protected}
    if protected_before != protected_after:
        raise ValueError("protected state changed")
    coverage = frames["executable_coverage.csv"]
    assessment = {
        "schema_version": "personalized_official_action_tournament_result_v1",
        "overall": "PARTIAL",
        "evidence_boundary": "Unchanged validation dates are reused development evidence; exposed 2025 outcomes and exact-date sectors are supplementary only.",
        "candidate_decisions": decisions,
        "frozen_cohort_fingerprint": protocol["frozen_cohort_fingerprint"],
        "official_action_freeze_fingerprint": json.loads((args.official_freeze / "manifest.json").read_text(encoding="utf-8"))["fingerprint"],
        "coverage_after": dict(zip(coverage.lookback_months.astype(str), coverage.executable_available_after.astype(int))),
        "executable_identity_count": len(executable.arrays),
        "history_error_identity_count": len(executable.errors),
        "historical_sector_used": True,
        "historical_sector_scope": "Exact official 2020-03-31, 2021-03-31, and 2022-03-31 observations only",
        "protected_state_unchanged": True,
        "runtime_seconds": time.perf_counter() - started,
        "python": platform.python_version(),
        "exact_next_milestone": "Collect prospective post-2026-09-18 outcomes and event-specific rights/merger/demerger economic terms; acquire effective-dated sector intervals before a full sector tournament.",
    }
    write_json(output / "assessment.json", assessment)
    write_json(output / "inputs.json", {
        "protocol_sha256": expected_protocol,
        "frozen_manifest_sha256": digest(args.frozen_root / "manifest.json"),
        "official_freeze_manifest_sha256": digest(args.official_freeze / "manifest.json"),
        "official_action_ledger_sha256": digest(ledger_path),
        "history_fingerprint": sha256(json.dumps(history_hashes, sort_keys=True).encode()).hexdigest(),
        "provider_split_ledger_sha256": digest(args.split_root / "split_ledger.csv"),
        "terminal_repairs_sha256": digest(repairs_path),
        "live_market_sha256": digest(live_path),
        "workbook_sha256": digest(args.workbook),
        "company_fact_fingerprint": snapshot.manifest["fingerprint"],
        "protected_state": protected_before,
        "source_sha256": {
            "runner": digest(Path(__file__)),
            "official_action_module": digest(ROOT / "src/stock_research/personalized_official_actions.py"),
            "tournament_module": digest(ROOT / "src/stock_research/personalized_executable_tournament.py"),
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
    parser.add_argument("--official-freeze", type=Path, required=True)
    parser.add_argument("--frozen-root", type=Path, required=True)
    parser.add_argument("--history-cache", type=Path, required=True)
    parser.add_argument("--split-root", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    parser.add_argument("--previous-tournament", type=Path, required=True)
    parser.add_argument("--checkpoint-root", type=Path, required=True)
    parser.add_argument("--protocol", type=Path)
    parser.add_argument("--protocol-sha256")
    run(parser.parse_args())
