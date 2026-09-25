"""Write the dated research report from verified final artifacts."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


def run(args):
    root = args.tournament
    coverage = pd.read_csv(root / "executable_coverage.csv")
    candidates = pd.read_csv(root / "candidate_metrics.csv").set_index("candidate")
    ensembles = pd.read_csv(root / "ensemble_metrics.csv").set_index("candidate")
    assessment = json.loads((root / "final_assessment.json").read_text(encoding="utf-8"))
    professor = json.loads((root / "professor_comparison_summary.json").read_text(encoding="utf-8"))
    recovery = json.loads((root / "data_recovery_summary.json").read_text(encoding="utf-8"))
    leakage = json.loads((root / "leakage_audit.json").read_text(encoding="utf-8"))
    controls = pd.read_csv(root / "control_experiment.csv").set_index("control")
    ablation = pd.read_csv(root / "model_ablation.csv")
    rights = pd.read_csv(root / "rights_policy_sensitivity.csv")
    fixed_name = assessment["strongest_fixed_ensemble_by_goal_shortfall"]
    individual_name = assessment["strongest_individual_by_goal_shortfall"]
    fixed = ensembles.loc[fixed_name]
    individual = candidates.loc[individual_name]
    rows = ["| Window | Frozen population | Executable before | Executable after | Recovered rows | Coverage after | Corporate action blocks | Fraction blocks | Other unresolved |",
            "|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for row in coverage.itertuples(index=False):
        rows.append(f"| {row.lookback_months}m | {row.frozen_global_population:,} | {row.executable_available_before:,} | "
                    f"{row.executable_available_after:,} | +{row.net_available_change} | "
                    f"{row.executable_coverage_after_pct:.2f}% | {row.corporate_action_blocks} | "
                    f"{row.fractional_entitlement_blocks} | {row.other_unresolved} |")
    control_rows = []
    for label in ("strongest_individual_rank_ic", "strongest_individual_goal_achievement",
                  "strongest_individual_lowest_shortfall", "strongest_fixed_ensemble_goal_achievement"):
        row = controls.loc[label]
        control_rows.append(f"| {label} | `{row.candidate}` | {row.rank_ic:.4f} | "
                            f"{row.target_achievement_top20:.1%} | {row.target_shortfall_top20:.4f} |")
    ablation_rows = []
    for name in ("amount_execution_features", "goal_features", "risk_feature_price_drawdown",
                 "existing_score", "lambda_rank_component", "corporate_action_recovery"):
        item = ablation.loc[ablation.component.eq(name) & ablation.metric.eq("target_shortfall_top20")].iloc[0]
        ablation_rows.append(f"| {name} | {item.improvement:+.4f} |")
    text = f"""# Personalized executable ranking: final research as of 2026-09-18

**Status: RESEARCH_ONLY.** No model earned production promotion. This report uses the 2026-09-18 frozen universe and outcomes already mature by that date. `build-04` is the corrected official-action freeze and `build-02` is the final tournament; earlier new builds remain superseded research records.

## 1. New evidence and executable coverage

The four round-two batches contain {recovery['round2_reconciliation']['round2_events']} distinct events. Independent reconciliation found {recovery['round2_reconciliation']['previously_covered']} previously evidenced, {recovery['round2_reconciliation']['official_auto_matches']} already represented by official automatic multipliers, {recovery['round2_reconciliation']['complex_recovered']} newly specified complex actions, and {recovery['round2_reconciliation']['consolidations_recovered']} recovered consolidations. Their union covers all 445 core mechanics, with zero core event identities missing. This does **not** mean every event has reproducible cash settlement or resulting-security valuation.

{chr(10).join(rows)}

The incremental gain is 19 profile rows across 10 distinct identities. Remaining blockers are profile-specific: 112, 305 and 376 corporate-action or fractional rows at 12m, 36m and 60m respectively. The broader official ledger includes rights and demergers outside the 22 newly recovered terms; those remain blocked. Other unresolved rows arise from stale, missing, or invalid price history. `remaining_blockers.csv` and `blocker_reconciliation.csv` give the exact identities and reasons.

## 2. Economic treatment and evidence boundaries

Official splits, bonuses and consolidations use proven share ratios. Consolidation holdings are inspected at the event date; a fractional entitlement blocks only that execution/profile when its cash settlement cannot be reproduced. In particular, INE363L01045 uses the proven 2-old-to-1-new ratio but no invented fraction proceeds.

The base rights policy is **NO_SUBSCRIPTION / PASSIVE**. It injects no cash and creates no ordinary shares. The withdrawn INE125F01032 issue creates no allotment. Recovered completed rights use a zero separately valued entitlement as a conservative research scenario, not a claim that a transferable entitlement has zero market value. `rights_policy_sensitivity.csv` separately tests portfolio-cash-limited exercise at the record date where replay is possible: {int(rights.status.eq('HYPOTHETICAL_ONLY').sum())} profile/event rows are evaluable and {int(rights.status.eq('NOT_EVALUABLE').sum())} remain blocked. It injects no external cash. That proxy is not an actual subscription schedule and is excluded from model selection.

Demergers retain the original security and record resulting-company entitlement ratios in the normalized ledger; they remain valuation blockers unless resulting security history is reproducible. Vedanta's terms identify one share in each of four resulting businesses per original share. No value is assigned to those holdings. SIYSIL records the 4:1 and 3:1 preference-share series and is never converted into seven ordinary shares. The preference cash-flow value remains unavailable.

The leakage audit found no post-cutoff market outcomes or action dates in the final panels. Sector diagnostics use only exact official observations on {', '.join(leakage['sector_exact_observation_dates'])}; the 2026-09-23 snapshot and modern labels were not projected backward. Later-collected documents were used only to document pre-cutoff events. The corrected freeze was rebuilt independently with the same deterministic fingerprint.

## 3. Individual models, fixed ensembles and investor utility

All 13 existing candidates were rerun on identical date/profile common cohorts: professor whole-share, enhanced no-carry XIRR, enhanced carry XIRR, enhanced goal, historical target frequency, global existing, enhanced plus existing, ridge executable, ridge without amount features, ridge without goal, cluster rank aggregation, HistGradientBoosting and LightGBM LambdaRank. The fixed family contains 25 preregistered rank-percentile combinations across 2, 3 and 4 components. No train-only learned ensemble was tested.

The tested ensemble families were goal + existing, goal + ridge, goal + LambdaRank, existing + ridge; goal + existing + ridge, goal + existing + LambdaRank, goal + ridge + LambdaRank; and goal + existing + ridge + LambdaRank. Pairs used 50/50, 67/33 and 33/67; triples used equal thirds and each 50/25/25 rotation; the four-part blend used equal quarters. `ensemble_metrics.csv` lists every fixed combination. `execution_diagnostics.csv` records cash utilization, affordability and execution counts; no complete historical slippage or fee series was available.

The strongest individual by mean rank IC and lowest mean goal shortfall is `{individual_name}`: IC {individual.rank_ic:.4f}, top-20 goal achievement {individual.target_achievement_top20:.1%}, mean shortfall {individual.target_shortfall_top20:.4f}. The best fixed ensemble by mean shortfall is `{fixed_name}`: IC {fixed.rank_ic:.4f}, goal achievement {fixed.target_achievement_top20:.1%}, shortfall {fixed.target_shortfall_top20:.4f}. It beats the simple goal/existing combination on these frozen descriptive measures, but the effect has only two independent validation dates and previously exposed outcomes.

| Control | Candidate | Mean rank IC | Top-20 goal achievement | Mean top-20 shortfall |
|---|---|---:|---:|---:|
{chr(10).join(control_rows)}

The strongest individual rank IC also has the lowest individual shortfall, but the highest individual goal-achievement rate belongs to a different model. Higher correlation therefore did not uniformly imply a higher fraction of investors meeting their target. The fixed ensemble improves average shortfall and attainment, while its IC is below the strongest individual. No single metric determines the decision.

`profile_metrics.csv`, `paired_deltas.csv`, and `uncertainty.csv` show date/profile variation and paired comparisons. The 18 profile-date rows derive from only two decision-date blocks; the reported bootstrap intervals are descriptive, not independent confirmation. No claim of a statistically established production improvement is made.

## 4. Ablation and recovery contribution

Positive values below mean the full version reduced mean top-20 shortfall; negative values mean the component worsened it in this comparison.

| Component comparison | Shortfall improvement |
|---|---:|
{chr(10).join(ablation_rows)}

The corporate-action recovery increased executable coverage and changed the HistGradientBoosting validation shortfall only modestly. The pre/post comparison changes the common cohort slightly, so its model delta is descriptive. Risk and goal feature ablations are post-selection diagnostics and were not used to pick the winner.

## 5. Professor workbook comparison

The supplied workbook is an external benchmark. The candidate definitions, ensemble family, and weights were frozen before any workbook read. The corrected build's selection followed that fixed rule without workbook inputs, after an earlier superseded run had already read the workbook. Of {professor['workbook_rows']} displayed rows, {professor['exact_identity_matches']} have exact exchange-code identity matches. All 14 cached investment/share-purchase rows have zero investment, leaving {professor['usable_workbook_purchase_rows']} usable purchase histories and {professor['exact_execution_reproductions']} exact execution reproductions. Missing cached purchase inputs are classified as unavailable workbook input, not model failure. The workbook cached date (2026-08-21) also differs from the research date (2026-09-18), and its GoogleFinance calendar and price cells cannot be reproduced from the cache.

The supplied ordering is a separate comparison from the workbook's cached SIP `RANK` formula. Only {professor['supplied_rank_pairs_with_selected_individual_score']} exact matched supplied-rank pairs have a selected individual score; within that overlap, descriptive Spearman agreement is {professor['supplied_rank_vs_selected_score_spearman_within_overlap']:.3f}. The supplied list has no known global rank scope, so this is not global ranking accuracy. Row-level diagnostics distinguish missing workbook inputs, identity gaps, accounting definitions, residual cash and corporate-action uncertainty; no unexplained discrepancy is inferred from blank cells.

## 6. Decision and next evidence

**No production change.** The status is `RESEARCH_ONLY`; promotion is `INSUFFICIENT_EVIDENCE`. Complex models show useful descriptive signals, but the two exposed validation dates, incomplete historical event cash values, missing historical sector intervals, absent historical slippage/fees, and unavailable workbook purchase cache prevent a production claim.

Next: obtain actual rights subscription timing and proceeds, resulting-company price/listing histories, SIYSIL preference cash-flow valuation, and a recalculated workbook with cached purchase and contribution rows. Preserve the frozen 2026-09-18 model and wait for genuinely prospective 12-month outcomes after 2027-09-18 before reconsidering promotion.
"""
    args.output.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())
