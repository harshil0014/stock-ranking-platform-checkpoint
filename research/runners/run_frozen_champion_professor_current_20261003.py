"""Score the frozen d499580 champion on missing-only professor current data.

No fitting, coefficient change, runtime-pack rebuild, or production write.
The original frozen score must reproduce before the data-only variant runs.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import lightgbm as lgb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
FREEZE = ROOT / "research/freezes/personalized-d499580"
SOURCE = ROOT / "experiments/professor-current-fallback-20261003/equal-priority-v2"
OUT = ROOT / "experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1"
COMMIT = "d4995807163bef1ec4b297179e6c54a59c71f390"
FEATURES = ["enhanced_carry_xirr_score", "enhanced_goal_score", "price_drawdown",
            "cagr_3y", "cagr_5y", "cash_utilization", "unaffordable_rate"]
PROFILE_ORDER = ["amount1000", "amount50000", "base7500", "lookback12", "lookback60",
                 "quarterly", "target10", "target30", "weekly"]
MAPPING = {"product_baseline_cagr_3y": "cagr_3y", "product_baseline_cagr_5y": "cagr_5y"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def score(frame: pd.DataFrame, model: lgb.Booster) -> pd.DataFrame:
    result = frame.copy()
    result["ranker_score"] = np.nan
    valid = result["enhanced_carry_xirr_score"].notna()
    result.loc[valid, "ranker_score"] = model.predict(result.loc[valid, FEATURES])
    ranks = result.groupby("profile_name")[["enhanced_goal_score", "ranker_score"]].rank(pct=True)
    result["goal_percentile"] = ranks["enhanced_goal_score"]
    result["ranker_percentile"] = ranks["ranker_score"]
    result["champion_score"] = result.goal_percentile * .67 + result.ranker_percentile * .33
    result["champion_rank"] = pd.Series(pd.NA, index=result.index, dtype="Int64")
    for profile, block in result.groupby("profile_name", sort=False):
        ranked = block.dropna(subset=["champion_score"]).sort_values(
            ["champion_score", "isin"], ascending=[False, True], kind="stable"
        )
        result.loc[ranked.index, "champion_rank"] = np.arange(1, len(ranked) + 1)
    return result


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    config = json.loads((FREEZE / "config.json").read_text(encoding="utf-8"))
    assert config["challenger_commit"] == COMMIT and config["weights"] == [.67, .33]
    assert config["features"] == FEATURES
    from stock_research.personalized_shadow import verify
    freeze_manifest = verify(FREEZE)
    frozen_path = FREEZE / "rankings.csv.gz"
    model_path = FREEZE / "lambdarank.txt"
    original = pd.read_csv(frozen_path, low_memory=False)
    assert set(original.profile_name) == set(PROFILE_ORDER)
    assert set(original.decision_date) == {config["prediction_as_of"]}
    assert not original.duplicated(["profile_name", "isin"]).any()
    model = lgb.Booster(model_file=str(model_path))
    baseline = score(original, model)
    pred_diff = np.nanmax(np.abs(baseline.ranker_score - original.lightgbm_lambdarank_score))
    blend_diff = np.nanmax(np.abs(baseline.champion_score - original.selected_ensemble_score))
    assert pred_diff < 1e-12 and blend_diff < 1e-12, (pred_diff, blend_diff)
    assert baseline.champion_score.notna().equals(original.selected_ensemble_score.notna())

    fill_path = SOURCE / "direct_filled_cells.csv"
    overlay_path = SOURCE / "current_company_facts_equal_priority.csv.gz"
    direct = pd.read_csv(fill_path)
    assert direct.provenance.eq("PROFESSOR_EXCEL").all()
    assert direct["policy"].eq("EQUAL_PRIORITY_CURRENT_FALLBACK").all()
    current = pd.read_csv(overlay_path, usecols=["isin", "ticker", "company", *MAPPING], low_memory=False)
    assert current["isin"].is_unique
    current = current.set_index("isin")
    candidate = original.copy()
    changed = {}
    for target, feature in MAPPING.items():
        identity = set(direct.loc[direct.target_field.eq(target), "isin"])
        values = candidate["isin"].map(current[target])
        mask = candidate["isin"].isin(identity) & candidate[feature].isna() & values.notna()
        candidate.loc[mask, feature] = values.loc[mask].to_numpy()
        changed[feature] = mask
    refreshed = score(candidate, model)
    assert baseline.champion_score.notna().equals(refreshed.champion_score.notna())
    for column in FEATURES:
        if column not in {"cagr_3y", "cagr_5y"}:
            assert baseline[column].equals(refreshed[column]), column
    assert baseline.enhanced_goal_score.equals(refreshed.enhanced_goal_score)
    assert baseline.goal_percentile.equals(refreshed.goal_percentile)

    comparison = pd.DataFrame({
        "decision_date": original.decision_date, "profile_name": original.profile_name,
        "isin": original["isin"], "ticker": original["isin"].map(current.ticker),
        "company": original["isin"].map(current.company),
        "old_rank": baseline.champion_rank, "new_rank": refreshed.champion_rank,
        "old_score": baseline.champion_score, "new_score": refreshed.champion_score,
        "old_ranker_score": baseline.ranker_score, "new_ranker_score": refreshed.ranker_score,
        "old_cagr_3y": baseline.cagr_3y, "new_cagr_3y": refreshed.cagr_3y,
        "old_cagr_5y": baseline.cagr_5y, "new_cagr_5y": refreshed.cagr_5y,
        "filled_cagr_3y": changed["cagr_3y"], "filled_cagr_5y": changed["cagr_5y"],
    })
    comparison["directly_filled"] = comparison.filled_cagr_3y | comparison.filled_cagr_5y
    comparison["rank_change"] = comparison.old_rank - comparison.new_rank
    comparison["absolute_rank_change"] = comparison.rank_change.abs()
    comparison.to_csv(OUT / "all_profile_rank_comparison.csv.gz", index=False,
                      compression={"method": "gzip", "mtime": 0})

    old_top, new_top, top_summary, top_changes, profile_summary = {}, {}, [], [], []
    for profile in PROFILE_ORDER:
        block = comparison.loc[comparison.profile_name.eq(profile)]
        old_sorted = block.dropna(subset=["old_rank"]).sort_values("old_rank")
        new_sorted = block.dropna(subset=["new_rank"]).sort_values("new_rank")
        old_top[profile] = old_sorted
        new_top[profile] = new_sorted
        for n in (20, 50, 100):
            a, b = set(old_sorted.head(n)["isin"]), set(new_sorted.head(n)["isin"])
            top_summary.append({"profile": profile, "top_n": n, "overlap": len(a & b),
                                "entries": len(b - a), "exits": len(a - b),
                                "old_top_isins": ";".join(old_sorted.head(n)["isin"]),
                                "new_top_isins": ";".join(new_sorted.head(n)["isin"])})
            for identity in sorted(a ^ b):
                row = block.loc[block["isin"].eq(identity)].iloc[0]
                top_changes.append({"profile": profile, "top_n": n,
                                    "change": "ENTRY" if identity in b else "EXIT",
                                    "isin": identity, "ticker": row.ticker,
                                    "old_rank": row.old_rank, "new_rank": row.new_rank,
                                    "filled_cagr_3y": bool(row.filled_cagr_3y),
                                    "filled_cagr_5y": bool(row.filled_cagr_5y)})
        profile_summary.append({
            "profile": profile, "cohort_rows": len(block), "scored_old": int(block.old_rank.notna().sum()),
            "scored_new": int(block.new_rank.notna().sum()),
            "rows_with_3y_filled": int(block.filled_cagr_3y.sum()),
            "rows_with_5y_filled": int(block.filled_cagr_5y.sum()),
            "directly_filled_rows": int(block.directly_filled.sum()),
            "directly_filled_scored_rows": int((block.directly_filled & block.new_rank.notna()).sum()),
            "rank_changed_rows": int(block.rank_change.fillna(0).ne(0).sum()),
            "directly_filled_rank_changed": int((block.directly_filled & block.rank_change.fillna(0).ne(0)).sum()),
            "indirect_rank_changed": int((~block.directly_filled & block.rank_change.fillna(0).ne(0)).sum()),
            "median_abs_rank_change": float(block.absolute_rank_change.median()),
            "max_abs_rank_change": int(block.absolute_rank_change.max()),
        })
    pd.DataFrame(top_summary).to_csv(OUT / "top_set_comparison.csv", index=False)
    pd.DataFrame(top_changes).to_csv(OUT / "top_membership_changes.csv", index=False)
    pd.DataFrame(profile_summary).to_csv(OUT / "profile_summary.csv", index=False)
    for n in (20, 50, 100):
        top = pd.concat([new_top[p].head(n) for p in PROFILE_ORDER], ignore_index=True)
        top.to_csv(OUT / f"new_top{n}.csv", index=False)
    movers = comparison.dropna(subset=["old_rank", "new_rank"]).sort_values(
        ["absolute_rank_change", "profile_name", "isin"], ascending=[False, True, True]
    ).head(200)
    movers.to_csv(OUT / "largest_rank_moves.csv", index=False)
    nykaa = comparison.loc[comparison["isin"].eq("INE388Y01029")].copy()
    nykaa.to_csv(OUT / "nykaa_diagnostic.csv", index=False)
    totals = pd.DataFrame(profile_summary)
    result = {
        "schema": "frozen_d499580_professor_current_data_only_v1",
        "frozen_champion_commit": COMMIT,
        "freeze_manifest_fingerprint": freeze_manifest["fingerprint"],
        "freeze_manifest_sha256": sha(FREEZE / "manifest.json"),
        "frozen_rankings_sha256": sha(frozen_path),
        "frozen_lightgbm_sha256": sha(model_path),
        "equal_priority_overlay_sha256": sha(overlay_path),
        "direct_fill_ledger_sha256": sha(fill_path),
        "baseline_reproduction_max_prediction_error": float(pred_diff),
        "baseline_reproduction_max_blend_error": float(blend_diff),
        "model_trained_or_coefficients_changed": False,
        "goal_execution_price_and_other_features_changed": False,
        "one_year_growth_is_champion_feature": False,
        "three_and_five_year_missing_only_fills": True,
        "decision_date": config["prediction_as_of"],
        "profiles": profile_summary,
        "total_profile_rows": len(comparison),
        "total_filled_3y_profile_rows": int(comparison.filled_cagr_3y.sum()),
        "total_filled_5y_profile_rows": int(comparison.filled_cagr_5y.sum()),
        "unique_directly_affected_stocks": int(comparison.loc[comparison.directly_filled, "isin"].nunique()),
        "total_scored_ranks_changed": int(totals.rank_changed_rows.sum()),
        "unique_stocks_with_any_rank_change": int(comparison.loc[comparison.rank_change.fillna(0).ne(0), "isin"].nunique()),
        "production_changed": False,
    }
    write_json(OUT / "summary.json", result)
    print(json.dumps({key: result[key] for key in (
        "baseline_reproduction_max_prediction_error", "baseline_reproduction_max_blend_error",
        "total_profile_rows", "total_filled_3y_profile_rows", "total_filled_5y_profile_rows",
        "unique_directly_affected_stocks", "total_scored_ranks_changed",
        "unique_stocks_with_any_rank_change")}, indent=2))


if __name__ == "__main__":
    main()
