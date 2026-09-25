"""Score preregistered fixed ensembles after the official-action rerun finishes."""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

import pandas as pd

from research.runners.run_personalized_executable_tournament import candidate_summary, paired_deltas
from stock_research.personalized_executable_tournament import BASE_CANDIDATES
from stock_research.personalized_validation import ranking_metrics, block_uncertainty


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def score_ensembles(panel: pd.DataFrame, protocol: dict) -> pd.DataFrame:
    family = protocol["fixed_ensemble_family"]
    components = [*BASE_CANDIDATES, "future_xirr", "future_shortfall", "future_drawdown"]
    rows = []
    for (day, profile), group in panel.groupby(["decision_date", "profile_name"], sort=True):
        common = group.dropna(subset=components).copy()
        ranks = common[BASE_CANDIDATES].rank(pct=True)
        for kind, weights in (("pairs", family["pair_weights"]),
                              ("triples", family["triple_weights"]),
                              ("quad", family["quad_weights"])):
            for members in family[kind]:
                columns = members.split("|")
                for weight in weights:
                    name = "+".join(c.removesuffix("_score") for c in columns) + "@" + "-".join(f"{x:.3f}" for x in weight)
                    common[name] = sum(ranks[column] * value for column, value in zip(columns, weight))
                    rows.append({"decision_date": day, "profile": profile, "candidate": name,
                                 "cohort": "common", **ranking_metrics(common, name)})
    return pd.DataFrame(rows)


def run(args) -> None:
    output, freeze = args.tournament, args.freeze
    protocol = json.loads((output / "protocol.json").read_text(encoding="utf-8"))
    if protocol["current_profile_date"] != "2026-09-18":
        raise ValueError("research cutoff drift")
    validation = pd.read_csv(output / "validation_predictions.csv.gz", low_memory=False)
    base_metrics = pd.read_csv(output / "validation_metrics.csv")
    ensemble_metrics = score_ensembles(validation, protocol)
    candidate_summary(base_metrics).to_csv(output / "candidate_metrics.csv", index=False, lineterminator="\n")
    candidate_summary(ensemble_metrics).to_csv(output / "ensemble_metrics.csv", index=False, lineterminator="\n")
    combined = pd.concat([base_metrics, ensemble_metrics], ignore_index=True)
    combined.groupby(["profile", "candidate"], as_index=False).mean(numeric_only=True).to_csv(
        output / "profile_metrics.csv", index=False, lineterminator="\n")
    paired_deltas(combined).to_csv(output / "paired_deltas.csv", index=False, lineterminator="\n")
    block_uncertainty(combined).to_csv(output / "uncertainty.csv", index=False, lineterminator="\n")
    recovery = json.loads((freeze / "summary.json").read_text(encoding="utf-8"))
    write_json(output / "data_recovery_summary.json", {
        "round2_reconciliation": recovery["residual_reconciliation"],
        "recovered_action_application": recovery["recovered_action_application"],
        "coverage": recovery["executable_coverage"],
        "rights_policy": "PASSIVE_NO_SUBSCRIPTION_ZERO_SEPARATELY_VALUED_ENTITLEMENT",
        "fractional_settlement_policy": "BLOCK_WHEN_CASH_PROCEEDS_CANNOT_BE_REPRODUCED",
    })
    audit = pd.read_csv(freeze / "all_profile_recovery_audit.csv.gz", low_memory=False)
    blockers = audit.loc[audit.status.ne("AVAILABLE")].copy()
    blockers[["lookback_months", "isin", "status", "reason"]].to_csv(
        output / "remaining_blockers.csv", index=False, lineterminator="\n")
    ablations = []
    summary = candidate_summary(combined).set_index("candidate")
    pairs = [
        ("amount_execution_features", "ridge_executable_score", "ridge_without_amount_features_score"),
        ("goal_features", "ridge_executable_score", "ridge_without_goal_score"),
        ("existing_score", "enhanced_plus_existing_score", "enhanced_goal_score"),
    ]
    for label, full, reduced in pairs:
        for metric in ("rank_ic", "target_achievement_top20", "target_shortfall_top20"):
            sign = -1 if metric == "target_shortfall_top20" else 1
            ablations.append({"component": label, "full": full, "without": reduced,
                              "metric": metric, "improvement": sign * (summary.loc[full, metric] - summary.loc[reduced, metric])})
    pd.DataFrame(ablations).to_csv(output / "model_ablation.csv", index=False, lineterminator="\n")
    individual = summary.loc[BASE_CANDIDATES]
    ensemble = summary.loc[ensemble_metrics.candidate.unique()]
    best_ic = individual.rank_ic.idxmax()
    best_goal = individual.target_shortfall_top20.idxmin()
    best_fixed = ensemble.target_shortfall_top20.idxmin()
    write_json(output / "final_assessment.json", {
        "status": "RESEARCH_ONLY", "as_of_date": "2026-09-18",
        "strongest_individual_by_rank_ic": best_ic,
        "strongest_individual_by_goal_shortfall": best_goal,
        "strongest_fixed_ensemble_by_goal_shortfall": best_fixed,
        "independent_validation_date_blocks": int(validation.decision_date.nunique()),
        "promotion": "INSUFFICIENT_EVIDENCE",
        "reason": "Previously exposed validation and only two independent decision dates cannot establish prospective benefit.",
        "professor_comparison_status": "PENDING_AFTER_TOURNAMENT_FREEZE",
    })
    (output / "executable_coverage.csv").write_bytes((freeze / "executable_coverage.csv").read_bytes())
    files = [{"path": p.name, "size": p.stat().st_size,
              "sha256": sha256(p.read_bytes()).hexdigest()}
             for p in sorted(output.iterdir()) if p.is_file() and p.name != "manifest.json"]
    write_json(output / "manifest.json", {"deterministic_artifacts": files,
        "fingerprint": sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tournament", type=Path, required=True)
    parser.add_argument("--freeze", type=Path, required=True)
    run(parser.parse_args())
