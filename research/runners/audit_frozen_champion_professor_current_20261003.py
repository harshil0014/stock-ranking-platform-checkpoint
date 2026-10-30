"""Independently check the research-only d499580 current-data comparison."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "experiments/professor-current-fallback-20261003/champion-data-refresh-research-v1"
FREEZE = ROOT / "research/freezes/personalized-d499580"
SOURCE = ROOT / "experiments/professor-current-fallback-20261003/equal-priority-v2"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> None:
    summary = json.loads((OUT / "summary.json").read_text(encoding="utf-8"))
    assert sha(FREEZE / "manifest.json") == summary["freeze_manifest_sha256"]
    assert sha(FREEZE / "rankings.csv.gz") == summary["frozen_rankings_sha256"]
    assert sha(FREEZE / "lambdarank.txt") == summary["frozen_lightgbm_sha256"]
    assert sha(SOURCE / "current_company_facts_equal_priority.csv.gz") == summary["equal_priority_overlay_sha256"]
    assert sha(SOURCE / "direct_filled_cells.csv") == summary["direct_fill_ledger_sha256"]
    comparison = pd.read_csv(OUT / "all_profile_rank_comparison.csv.gz", low_memory=False)
    profiles = pd.read_csv(OUT / "profile_summary.csv")
    tops = pd.read_csv(OUT / "top_set_comparison.csv")
    source = pd.read_csv(SOURCE / "direct_filled_cells.csv")
    allowed = {
        "cagr_3y": set(source.loc[source.target_field.eq("product_baseline_cagr_3y"), "isin"]),
        "cagr_5y": set(source.loc[source.target_field.eq("product_baseline_cagr_5y"), "isin"]),
    }
    assert len(comparison) == summary["total_profile_rows"]
    assert not comparison.duplicated(["profile_name", "isin"]).any()
    for feature in ("cagr_3y", "cagr_5y"):
        flag = comparison[f"filled_{feature}"]
        assert (comparison.loc[flag, f"old_{feature}"].isna()).all()
        assert (comparison.loc[flag, f"new_{feature}"].notna()).all()
        assert set(comparison.loc[flag, "isin"]).issubset(allowed[feature])
        same = comparison.loc[~flag, [f"old_{feature}", f"new_{feature}"]]
        assert np.allclose(same.iloc[:, 0], same.iloc[:, 1], equal_nan=True, rtol=0, atol=0)
    unchanged = ~comparison.directly_filled
    assert np.allclose(comparison.loc[unchanged, "old_ranker_score"],
                       comparison.loc[unchanged, "new_ranker_score"], equal_nan=True, atol=1e-12)
    assert comparison.old_rank.notna().equals(comparison.new_rank.notna())
    for block in (comparison.groupby("profile_name")):
        profile, frame = block
        ranks = sorted(frame.new_rank.dropna().astype(int))
        assert ranks == list(range(1, len(ranks) + 1)), profile
        assert (tops.loc[tops.profile.eq(profile), "overlap"] <= tops.loc[tops.profile.eq(profile), "top_n"]).all()
    for n in (20, 50, 100):
        top = pd.read_csv(OUT / f"new_top{n}.csv")
        assert len(top) == 9 * n
        assert top.groupby("profile_name").size().eq(n).all()
        assert top.new_rank.le(n).all()
    assert int(profiles.rank_changed_rows.sum()) == summary["total_scored_ranks_changed"]
    assert int(comparison.loc[comparison.directly_filled, "isin"].nunique()) == summary["unique_directly_affected_stocks"]
    assert summary["baseline_reproduction_max_prediction_error"] < 1e-12
    assert summary["baseline_reproduction_max_blend_error"] < 1e-12
    audit = {
        "schema": "frozen_d499580_professor_current_audit_v1",
        "status": "PASS",
        "frozen_champion_sha256_unchanged": True,
        "baseline_scores_reproduced": True,
        "only_missing_cagr_3y_and_cagr_5y_changed": True,
        "rank_coverage_preserved": True,
        "all_top20_top50_top100_lists_verified": True,
        "profile_rows": len(comparison),
        "directly_affected_unique_stocks": summary["unique_directly_affected_stocks"],
        "model_or_production_modified": False,
    }
    (OUT / "audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
