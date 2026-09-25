"""Compare frozen selected research with cached professor workbook evidence."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

import pandas as pd

from stock_ranker.company_facts import load_company_fact_snapshot, resolve_company_fact_snapshot
from stock_ranker.personalized_benchmark import professor_benchmark


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def run(args) -> None:
    output = args.tournament
    selection = json.loads((output / "selection_freeze.json").read_text(encoding="utf-8"))
    if not selection["selection"]["strongest_individual_by_goal_shortfall"]:
        raise ValueError("model selection was not frozen")
    benchmark, workbook_audit = professor_benchmark(args.workbook)
    if workbook_audit["amount"] != 7500 or workbook_audit["lookback_months"] != 36:
        raise ValueError("unexpected workbook profile")
    facts = load_company_fact_snapshot(resolve_company_fact_snapshot(ROOT / "data/company_facts")).facts
    exact = facts[["isin", "ticker", "primary_exchange", "professor_supplied_rank"]].copy()
    exact["requested_code"] = exact.apply(
        lambda row: ("NSE:" + str(row.ticker)) if row.primary_exchange == "NSE"
        else ("BOM:" + str(row.ticker).removeprefix("BSE-")), axis=1)
    matched = benchmark.merge(exact[["requested_code", "isin", "ticker", "professor_supplied_rank"]],
                              on="requested_code", how="left", validate="many_to_one")
    current = pd.read_csv(output / "current_profile_rankings.csv.gz", low_memory=False)
    current = current.loc[current.profile_name.eq("base7500")].copy()
    keep = ["isin", "status", "reason", "shares_bought", "amount_invested", "residual_cash",
            "current_holding_value", "total_wealth", "profit_loss", "profit_loss_pct", "enhanced_carry_xirr_score",
            "target_attainment", "enhanced_goal_score", "global_existing_score",
            "hist_gradient_boosting_score"]
    current = current[keep].rename(columns={key: "research_" + key for key in keep if key != "isin"})
    matched = matched.merge(current, on="isin", how="left", validate="many_to_one")
    matched["research_as_of_date"] = "2026-09-18"
    matched["workbook_cached_date"] = "2026-08-21"
    matched["comparison_status"] = "UNAVAILABLE_WORKBOOK_INPUT"
    matched.loc[matched["isin"].isna(), "comparison_status"] = "NO_EXACT_IDENTITY_MATCH"
    matched.loc[matched["isin"].notna() & matched["research_status"].ne("AVAILABLE"),
                "comparison_status"] = "RESEARCH_PROFILE_BLOCKED_OR_UNAVAILABLE"
    matched["shares_delta"] = matched.research_shares_bought - matched.shares_bought
    matched["invested_delta_inr"] = matched.research_amount_invested - matched.amount_invested
    matched["holding_value_delta_inr"] = matched.research_current_holding_value - matched.current_value
    matched["profit_loss_delta_inr"] = matched.research_profit_loss - matched.profit_loss
    matched.to_csv(output / "professor_workbook_comparison.csv", index=False, lineterminator="\n")
    diagnostics = []
    for row in matched.itertuples(index=False):
        if pd.isna(row.isin):
            reason = "NO_EXACT_IDENTITY_MATCH"
        elif row.research_status != "AVAILABLE":
            reason = "RESEARCH_PROFILE_BLOCKED_OR_UNAVAILABLE"
        elif row.status == "UNUSABLE_ZERO_INVESTMENT_CACHE":
            reason = "UNAVAILABLE_WORKBOOK_PURCHASE_AND_INVESTMENT_CACHE"
        else:
            reason = "DATE_PRICE_AND_ACCOUNTING_BASIS_DIFFER"
        diagnostics.append({"workbook_row": row.workbook_row, "requested_code": row.requested_code,
                            "isin": row.isin, "diagnostic": reason,
                            "workbook_source_cells": row.source_cells,
                            "missing_purchase_inputs": row.status == "UNUSABLE_ZERO_INVESTMENT_CACHE",
                            "whole_share_policy_difference": "NOT_IDENTIFIABLE_FROM_CACHE",
                            "residual_cash_policy_difference": "WORKBOOK_EXCLUDES; RESEARCH_INCLUDES",
                            "corporate_action_difference": "NOT_IDENTIFIABLE_FROM_CACHE",
                            "unexplained_discrepancy": False})
    pd.DataFrame(diagnostics).to_csv(output / "professor_mismatch_diagnostics.csv", index=False, lineterminator="\n")
    valid = matched.dropna(subset=["professor_supplied_rank", "research_hist_gradient_boosting_score"])
    rank_agreement = ((-valid.professor_supplied_rank).corr(valid.research_hist_gradient_boosting_score,
                                                        method="spearman") if len(valid) > 2 else None)
    write_json(output / "professor_comparison_summary.json", {
        "workbook_sha256": workbook_audit["workbook_sha256"],
        "workbook_rows": len(matched), "exact_identity_matches": int(matched["isin"].notna().sum()),
        "usable_workbook_purchase_rows": int(matched.status.eq("CACHED_ARITHMETIC_ONLY").sum()),
        "exact_execution_reproductions": 0,
        "supplied_rank_pairs_with_selected_individual_score": len(valid),
        "supplied_rank_vs_selected_score_spearman_within_overlap": rank_agreement,
        "rank_scope": "Only exact matched supplied identities; supplied list has no known global rank scope.",
        "date_boundary": "Workbook cached date 2026-08-21 and research cutoff 2026-09-18 differ.",
        "workbook_input_boundary": workbook_audit["unknowns"],
        "selection_rule_and_fixed_ensemble_family_frozen_before_workbook_read": True,
        "corrected_selection_used_no_workbook_inputs": True,
        "corrected_selection_after_earlier_workbook_read": True,
    })
    assessment_path = output / "final_assessment.json"
    assessment = json.loads(assessment_path.read_text(encoding="utf-8"))
    assessment["professor_comparison_status"] = "INSUFFICIENT_WORKBOOK_EXECUTION_CACHE"
    assessment["professor_workbook_exact_identity_matches"] = int(matched["isin"].notna().sum())
    write_json(assessment_path, assessment)
    files = [{"path": p.name, "size": p.stat().st_size,
              "sha256": sha256(p.read_bytes()).hexdigest()}
             for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"]
    write_json(output / "manifest.json", {"deterministic_artifacts": files,
        "fingerprint": sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", type=Path, required=True)
    parser.add_argument("--workbook", type=Path, required=True)
    run(parser.parse_args())
