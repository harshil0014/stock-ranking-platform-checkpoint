"""Audit a data-only repair of the frozen 67/33 personalized architecture.

The model family, seven input features, LightGBM hyperparameters, and 67/33 blend
remain unchanged. The only research intervention is replacing genuinely
unavailable 5Y CAGR inputs with the provenance-aware long-term proxy produced by
personalized_history_challenger history features. This is research-only and does
not mutate the frozen champion or production.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import lightgbm as lgb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "research/runners"))

import personalized_history_challenger as history
from stock_ranker.company_facts import load_company_fact_snapshot
from stock_ranker.runtime import validated_release
from stock_research.personalized_executable_tournament import FEATURES
from stock_research.personalized_validation import ranking_metrics

PARAMS = (60, 0.05, 7, 3, 80, 10.0)
GOAL_WEIGHT = 0.67
DEFAULT_OUTPUT = ROOT / "experiments/history-enrichment-20261002/data-repaired-champion-v2"
METRICS = (
    "coverage", "rank_ic", "ndcg20", "pairwise_accuracy",
    "target_achievement_top20", "target_shortfall_top20",
    "mean_xirr_top20", "median_xirr_top20", "mean_asset_drawdown_top20",
)


def blend(frame: pd.DataFrame, model_score: str) -> pd.Series:
    ranks = frame.groupby(["decision_date", "profile_name"])[
        ["enhanced_goal_score", model_score]
    ].rank(pct=True)
    return GOAL_WEIGHT * ranks["enhanced_goal_score"] + (1 - GOAL_WEIGHT) * ranks[model_score]


def evaluate(frame: pd.DataFrame, score: str) -> pd.DataFrame:
    rows = []
    for (day, profile), group in frame.groupby(["decision_date", "profile_name"], sort=True):
        rows.append({"decision_date": day, "profile": profile, **ranking_metrics(group, score)})
    return pd.DataFrame(rows)


def compare_partition(frame: pd.DataFrame, partition: str) -> tuple[dict, pd.DataFrame]:
    champion = evaluate(frame, "champion_score")
    repaired = evaluate(frame, "repaired_score")
    summary = {}
    for metric in METRICS:
        old = float(champion[metric].mean())
        new = float(repaired[metric].mean())
        summary[metric] = {"champion": old, "repaired": new, "delta": new - old}
    slices = champion.merge(
        repaired, on=["decision_date", "profile"], suffixes=("_champion", "_repaired")
    )
    slices.insert(0, "partition", partition)
    return summary, slices


def current_audit(current: pd.DataFrame, facts: pd.DataFrame) -> dict:
    ids = facts.drop_duplicates("isin")[["isin", "ticker", "derived_research_sector"]]
    base = current.loc[current["profile_name"].eq("base7500")].merge(ids, on="isin", how="left")
    result = {}
    for label, score in (
        ("champion", "selected_ensemble_score"),
        ("repaired_retrained", "repaired_retrained_score"),
        ("repaired_frozen_tree", "repaired_frozen_tree_score"),
    ):
        ranked = base.loc[base[score].notna()].sort_values(
            [score, "isin"], ascending=[False, True], kind="stable"
        ).copy()
        ranked["rank"] = range(1, len(ranked) + 1)
        short = ranked["cagr_5y_observed"].ne(1)
        retail = ranked.loc[ranked["derived_research_sector"].eq("Retailing")].copy()
        retail["sector_rank"] = range(1, len(retail) + 1)
        nykaa = ranked.loc[ranked["ticker"].eq("NYKAA")]
        result[label] = {
            "scored": int(len(ranked)),
            "short_history_universe_share": float(short.mean()),
            "top20_short_history_share": float(short.iloc[:20].mean()),
            "top50_short_history_share": float(short.iloc[:50].mean()),
            "top100_short_history_share": float(short.iloc[:100].mean()),
            "nykaa_global_rank": int(nykaa["rank"].iloc[0]) if len(nykaa) else None,
            "nykaa_retail_rank": (
                int(retail.loc[retail["ticker"].eq("NYKAA"), "sector_rank"].iloc[0])
                if retail["ticker"].eq("NYKAA").any() else None
            ),
            "nykaa_score": float(nykaa[score].iloc[0]) if len(nykaa) else None,
        }
    return result


def run(output: Path) -> None:
    output.mkdir(parents=True, exist_ok=False)
    panels = history.load_panels()
    release = validated_release()
    fact_root = ROOT / "data/company_facts/snapshots" / (
        "2026-09-18-" + release["accepted_company_fingerprint"]
    )
    fact_bundle = load_company_fact_snapshot(fact_root)
    if fact_bundle.manifest.get("fingerprint") != release["accepted_company_fingerprint"]:
        raise ValueError("accepted company-fact fingerprint mismatch")
    facts = fact_bundle.facts
    hist_features = history.history_features(panels, facts)
    panels = {name: history.attach(frame, hist_features) for name, frame in panels.items()}

    validation = panels["validation_predictions"].copy()
    validation["champion_score"] = blend(validation, "lightgbm_lambdarank_score")
    validation["repaired_lambda"] = np.nan
    for day, group in validation.groupby("decision_date"):
        mature = panels["training_panel"].loc[
            pd.to_datetime(panels["training_panel"]["endpoint"]).lt(pd.Timestamp(day))
        ]
        prediction, _ = history.fit_predict(mature, group, FEATURES, PARAMS)
        validation.loc[group.index, "repaired_lambda"] = prediction
    validation["repaired_score"] = blend(validation, "repaired_lambda")

    supplementary = panels["supplementary_predictions"].copy()
    supplementary["champion_score"] = blend(supplementary, "lightgbm_lambdarank_score")
    supplementary["repaired_lambda"] = np.nan
    development = pd.concat(
        [panels["training_panel"], panels["validation_predictions"]], ignore_index=True
    )
    for day, group in supplementary.groupby("decision_date"):
        mature = development.loc[
            pd.to_datetime(development["endpoint"]).lt(pd.Timestamp(day))
        ]
        prediction, _ = history.fit_predict(mature, group, FEATURES, PARAMS)
        supplementary.loc[group.index, "repaired_lambda"] = prediction
    supplementary["repaired_score"] = blend(supplementary, "repaired_lambda")

    summary = {
        "schema_version": "personalized_data_repair_audit_v1",
        "intervention": "same 67/33 architecture and hyperparameters; repaired cagr_5y input only",
        "production_mutated": False,
        "frozen_champion_mutated": False,
    }
    val_summary, val_slices = compare_partition(validation, "validation_2023")
    supp_summary, supp_slices = compare_partition(supplementary, "exposed_2025")
    summary["validation_2023"] = val_summary
    summary["exposed_2025"] = supp_summary
    pd.concat([val_slices, supp_slices]).to_csv(output / "profile_slices.csv", index=False)

    frozen = pd.read_csv(ROOT / "research/freezes/personalized-d499580/rankings.csv.gz", low_memory=False)
    current = history.attach(frozen, hist_features)
    mature = pd.concat(
        [
            panels["training_panel"],
            panels["validation_predictions"],
            panels["supplementary_predictions"],
        ],
        ignore_index=True,
    )
    mature = mature.loc[pd.to_datetime(mature["endpoint"]).lt(pd.Timestamp("2026-09-18"))]
    prediction, _ = history.fit_predict(mature, current, FEATURES, PARAMS)
    current["repaired_retrained_lambda"] = prediction
    current["repaired_retrained_score"] = blend(
        current.assign(decision_date="2026-09-18"), "repaired_retrained_lambda"
    )

    frozen_tree = lgb.Booster(
        model_file=str(ROOT / "research/freezes/personalized-d499580/lambdarank.txt")
    )
    valid = current["enhanced_carry_xirr_score"].notna()
    current["repaired_frozen_tree_lambda"] = np.nan
    current.loc[valid, "repaired_frozen_tree_lambda"] = frozen_tree.predict(
        current.loc[valid, FEATURES]
    )
    current["repaired_frozen_tree_score"] = blend(
        current.assign(decision_date="2026-09-18"), "repaired_frozen_tree_lambda"
    )
    summary["current_base7500"] = current_audit(current, facts)

    current.to_csv(output / "current_repaired.csv.gz", index=False, compression="gzip")
    (output / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    run(args.output)
