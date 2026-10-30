"""Finalize the locked V13 prospective comparison without rerunning outcomes.

This reads only persisted reveal and post-reveal sensitivity records. It does not
call the simulator, alter scores, or touch accepted market data.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
V13 = ROOT / "experiments/personalized-v13-20261002"
OUT = V13 / "prospective-2025-09-30"
REPAIR = OUT / "post_reveal_price_repair_20260901_18"
REPORT = ROOT / "research/reports/personalized_v13_prospective_20261003.md"
LOCK_SHA = "dad3ce68b22a1f744650e501505a3ebc78dc7c4bd39c3247982c4ed84bcac13b"
SCORE_SHA = "5040171dd8a88f9202a89dadba4538537a3571d0eba6bcec0f631634c5a49926"
FIRST_SHA = "a714c2a994ea64f624aa3dae6e70ef001024ba245fe49d78d75a728bcfef17ca"
EXPECTED_HEAD = "c12dd9b189bc71684bfac52606eb89abd5e383c7"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def pp(v: float) -> str:
    return f"{v * 100:+.2f} pp"


def metrics_table(record: dict) -> str:
    names = [
        ("coverage", "Coverage", "pct"),
        ("rank_ic", "Rank IC", "num"),
        ("ndcg20", "NDCG@20", "num"),
        ("pairwise_accuracy", "Pairwise accuracy", "pct"),
        ("target_achievement_top20", "Top-20 target achievement", "pct"),
        ("target_shortfall_top20", "Top-20 target shortfall", "pct"),
        ("median_xirr_top20", "Median Top-20 XIRR", "pct"),
        ("mean_asset_drawdown_top20", "Mean Top-20 asset drawdown", "pct"),
    ]
    lines = ["| Metric | Champion | V13 | V13 − champion |", "|---|---:|---:|---:|"]
    for key, label, unit in names:
        x = record["aggregate"][key]
        if unit == "num":
            a, b, d = (f"{x[k]:.6f}" for k in ("champion", "v13", "delta"))
        else:
            a, b, d = pct(x["champion"]), pct(x["v13"]), pp(x["delta"])
        lines.append(f"| {label} | {a} | {b} | {d} |")
    return "\n".join(lines)


def main() -> None:
    lock = V13 / "locked_selection.json"
    scores = OUT / "scores_before_reveal.csv.gz"
    first = OUT / "evaluation_record.json"
    repaired = REPAIR / "repaired_evaluation_record.json"
    assert sha(lock) == LOCK_SHA
    assert sha(scores) == SCORE_SHA
    assert sha(first) == FIRST_SHA
    old, new = read(first), read(repaired)
    assert new["first_reveal_sha256"] == FIRST_SHA
    assert new["scores_before_reveal_sha256"] == SCORE_SHA
    assert old["outcomes_revealed_once"] and not old["selection_changed_after_reveal"]
    assert new["scores_changed"] is False and new["selection_changed"] is False
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    assert head == EXPECTED_HEAD
    prereveal = read(OUT / "pre_reveal_integrity_audit.json")
    repair_audit = read(REPAIR / "structural_audit.json")
    assert prereveal["outcome_values_loaded"] is False
    assert prereveal["outcome_file_exists"] is False
    assert prereveal["accepted_data_mutated"] is False
    assert repair_audit["outcome_metrics_used_for_repair"] is False
    assert repair_audit["first_reveal_overwritten"] is False

    # The locked, prospectively tested model fails the safety gate once daily
    # price coverage is repaired. Do not promote or use this to retune V13.
    weekly = new["profile_deltas"]["weekly"]
    short = new["profile_deltas"]["lookback12"]
    assert weekly["mean_asset_drawdown_top20"] < -0.03
    assert short["target_shortfall_top20"] > 0.01
    verdict = "FROZEN CHAMPION RETAINS"

    decision = {
        "schema": "v13_prospective_decision_v1",
        "verdict": verdict,
        "decision_date": "2025-09-30",
        "outcome_endpoint": "2026-09-30",
        "frozen_production_champion": "d499580",
        "selection_lock_sha256": LOCK_SHA,
        "scores_before_reveal_sha256": SCORE_SHA,
        "first_reveal_record_sha256": FIRST_SHA,
        "selection_or_coefficients_changed": False,
        "first_reveal": {
            "status": "one_time_reveal_with_incomplete_daily_execution_price_coverage",
            "outcome_available_rows": old["outcome_available_rows"],
            "aggregate": old["aggregate"],
            "profile_deltas": old["profile_deltas"],
        },
        "official_price_repair": {
            "status": "POST_REVEAL_STRUCTURAL_DATA_REPAIR_NOT_FRESH_BLIND_VALIDATION",
            "reason": "Sep 1-18 daily exchange bhavcopies fill weekly execution-price gaps",
            "official_source_files": repair_audit["official_source_files_verified"],
            "weekly_date_gap_identities_before": repair_audit["weekly_date_gap_identities_before"],
            "weekly_date_gap_identities_after": repair_audit["weekly_date_gap_identities_after"],
            "outcome_metrics_used_for_repair": False,
            "repaired_evaluation_sha256": sha(repaired),
            "outcome_available_rows": new["outcome_available_rows"],
            "aggregate": new["aggregate"],
            "profile_deltas": new["profile_deltas"],
        },
        "promotion_blockers": [
            "Repaired weekly Top-20 mean asset drawdown deteriorates by 3.49 percentage points.",
            "The 12M profile loses 5 percentage points of achievement, gains 1.42 points of shortfall, and loses 14.79 points of median XIRR.",
            "The daily-price-complete evaluation is post-reveal sensitivity, not an untouched blind validation.",
        ],
        "production_changed": False,
        "production_head": head,
    }
    decision_path = OUT / "prospective_decision.json"
    write(decision_path, decision)

    profile_names = ["amount1000", "amount50000", "base7500", "lookback12", "lookback60", "quarterly", "target10", "target30", "weekly"]
    profile_lines = ["| Profile | NDCG Δ | Achievement Δ | Shortfall Δ | Median XIRR Δ | Drawdown Δ | Top-20 overlap | Missing true 5Y, champion → V13 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for p in profile_names:
        d = new["profile_deltas"][p]
        ch, v = new["top20_history_champion"][p], new["top20_history_v13"][p]
        overlap = len(set(ch["top20_isins"]) & set(v["top20_isins"]))
        profile_lines.append(
            f"| {p} | {d['ndcg20']:+.4f} | {pp(d['target_achievement_top20'])} | {pp(d['target_shortfall_top20'])} | {pp(d['median_xirr_top20'])} | {pp(d['mean_asset_drawdown_top20'])} | {overlap}/20 | {pct(ch['top20_missing_true_5y_share'])} → {pct(v['top20_missing_true_5y_share'])} |"
        )

    rel = "../.."
    report = f"""# Locked V13 prospective validation — 2025-09-30 decision

**Verdict: {verdict}.** V13 improves several aggregate measures, but the repaired official-price run shows a material weekly drawdown regression and a 12M profile shortfall/return regression. Keep production champion `d499580` frozen. No production, Railway, or website change was made.

## What was tested and when

The V13 policy and coefficients were fixed in [`locked_selection.json`]({rel}/experiments/personalized-v13-20261002/locked_selection.json) (SHA256 `{LOCK_SHA}`). The 30,305 champion/V13 decision scores were persisted before the outcome was read (SHA256 `{SCORE_SHA}`); [`pre_reveal_record.json`]({rel}/experiments/personalized-v13-20261002/prospective-2025-09-30/pre_reveal_record.json) and the pre-reveal audit state that no prospective outcome values were loaded. The 2025-09-30 decision was then simulated once through 2026-09-30. Original reveal record SHA256: `{FIRST_SHA}`. Scores and coefficients stayed fixed afterward.

The first reveal exposed a *data coverage* problem: old daily histories missed many September 2026 execution prices. Official NSE/BSE bhavcopies for September 1–18 were acquired **after the first reveal** to repair those dates. This repair used date/identity gaps, not outcome metrics, and retained the first reveal unchanged. Its comparison is explicitly a **post-reveal sensitivity analysis, not a second fresh blind test**. The repaired result is the more complete execution-price assessment and is decisive for risk, but its timing limits any promotion claim.

## One-time reveal, original evidence

{metrics_table(old)}

Outcome-available rows: {old['outcome_available_rows']:,} / {old['rows']:,}. The weekly profile had only 33.9% score-and-outcome coverage because 2,416 rows had `MISSING_EXECUTION_PRICE`; its apparent drawdown improvement was therefore unreliable. Both rankers had identical coverage.

## Official-price repair sensitivity (post-reveal)

{metrics_table(new)}

Outcome-available rows: {new['outcome_available_rows']:,} / {new['rows']:,}; score-and-outcome coverage {pct(new['aggregate']['coverage']['champion'])} for both models. The repaired weekly coverage is about 91.6%, with `MISSING_EXECUTION_PRICE` reduced from 2,416 to 10. The repair audit verified 26 official source files and reduced identities with weekly schedule date gaps from 2,139 to 51. It did not change scores or selections.

NDCG@20 rises by {new['aggregate']['ndcg20']['delta']:+.4f}, Top-20 achievement rises {pp(new['aggregate']['target_achievement_top20']['delta'])}, and shortfall falls {pp(new['aggregate']['target_shortfall_top20']['delta'])}. Rank IC and pairwise accuracy slip slightly. Aggregate drawdown improves only {pp(new['aggregate']['mean_asset_drawdown_top20']['delta'])}. Mean Top-20 XIRR is excluded from selection because extreme stock-level annualizations dominate it; the median moves only {pp(new['aggregate']['median_xirr_top20']['delta'])}.

## All profile trade-offs (official-price repair)

Positive drawdown delta means a less negative drawdown. Negative shortfall delta is favorable.

{"\n".join(profile_lines)}

The decisive regressions are weekly drawdown **{pp(weekly['mean_asset_drawdown_top20'])}**, despite weekly achievement {pp(weekly['target_achievement_top20'])} and shortfall {pp(weekly['target_shortfall_top20'])}; and 12M achievement **{pp(short['target_achievement_top20'])}**, shortfall **{pp(short['target_shortfall_top20'])}**, median XIRR **{pp(short['median_xirr_top20'])}**, and NDCG {short['ndcg20']:+.4f}. The 10% target drawdown worsens {pp(new['profile_deltas']['target10']['mean_asset_drawdown_top20'])}; the 30% target shortfall worsens {pp(new['profile_deltas']['target30']['target_shortfall_top20'])}. These are one decision date with overlapping profiles, not nine independent holdouts.

## History, concentration, and diagnostics

On this 2025-09-30 decision, V13 reduces top-20 missing observed true-5Y CAGR for the small-amount profile from 15% to 10%, 12M from 5% to 0%, and quarterly from 10% to 5%; most other profiles stay at 5% or 0%. The profile table gives every count. The previously frozen *current-universe* diagnostic at 2026-09-18 was V12 vs V13 missing true-5Y share of Top-20 **75% → 50%**, Top-50 **46% → 38%**, and Top-100 **28% → 24%**. These are distinct universes/dates.

Top-20 membership overlap ranges from 8/20 (12M) to 17/20 (60M), so the 12M regression coincides with substantial turnover. NYKAA was diagnostic only: in the 2025-09-30 base profile its score rank moved 1,063 → 1,112 of 3,114 scored; weekly 1,142 → 1,145 of 3,111. It was not used in fitting or selection.

## Evidence and limits

The decision evidence combines a frozen historical panel, the validated adjusted-history overlay, V2 Yahoo split provenance, new Yahoo price responses, official NSE/BSE daily bhavcopies, and official action responses. The original 2,517 official-action rows and 1,816 split rows were preserved; 4 official action rows and 2 Yahoo split events were appended. Three BSE action codes (511664, 511692, 526373) failed with HTTP 403 and were quarantined. The score audit retains observed, estimated, adjusted-history, and `RAW_RISK_ONLY` distinctions. No missing prices or actions were fabricated.

The initial 16 official bhavcopy files support September 21–30; the 26 repair files support September 1–18. September 14 was absent from both official exchange archives and was not fabricated. The first reveal outcome file, repair outcome file, source receipts, overlays, scripts, audits, and decision are individually hashed in [`artifact_manifest.json`]({rel}/experiments/personalized-v13-20261002/prospective-2025-09-30/artifact_manifest.json). The repair's post-reveal timing and the weekly/12M regressions prevent promotion. Existing prior V13 blind and exposed-2025 diagnostics remain separate; no model search or retuning followed this prospective result.

Production HEAD remains `{head}`. The [`prospective_decision.json`]({rel}/experiments/personalized-v13-20261002/prospective-2025-09-30/prospective_decision.json) contains exact machine-readable values and promotion blockers.
"""
    REPORT.write_text(report, encoding="utf-8")

    final_audit = {
        "schema": "v13_prospective_final_integrity_audit_v1",
        "selection_lock_sha256": sha(lock),
        "scores_before_reveal_sha256": sha(scores),
        "first_reveal_record_sha256": sha(first),
        "repaired_evaluation_sha256": sha(repaired),
        "pre_reveal_record_sha256": sha(OUT / "pre_reveal_record.json"),
        "pre_reveal_audit_sha256": sha(OUT / "pre_reveal_integrity_audit.json"),
        "post_reveal_repair_audit_sha256": sha(REPAIR / "structural_audit.json"),
        "original_reveal_preserved": True,
        "scores_and_selection_unchanged": True,
        "repair_is_post_reveal_not_fresh_blind": True,
        "production_head": head,
        "production_head_unchanged": True,
        "production_mutated": False,
        "decision_sha256": sha(decision_path),
        "report_sha256": sha(REPORT),
    }
    write(OUT / "final_integrity_audit.json", final_audit)
    print(f"Wrote {decision_path}, {REPORT}, and final integrity audit")


if __name__ == "__main__":
    main()
