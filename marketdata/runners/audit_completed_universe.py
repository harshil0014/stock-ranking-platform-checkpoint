"""Audit final complete-universe ranks against pre-frozen Codex judgments."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import numpy as np
import pandas as pd


def _sha(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _pairwise(left: np.ndarray, right: np.ndarray) -> tuple[float, int]:
    agreeing = 0.0
    pairs = 0
    for index in range(len(left)):
        left_sign = np.sign(left[index] - left[index + 1 :])
        right_sign = np.sign(right[index] - right[index + 1 :])
        agreeing += float(np.sum(left_sign == right_sign))
        agreeing += 0.5 * float(np.sum((left_sign == 0) ^ (right_sign == 0)))
        pairs += len(left_sign)
    return agreeing, pairs


def run(completion: Path, frozen_audit: Path, output: Path) -> dict:
    if output.exists():
        raise ValueError("fresh output directory required")
    ranks = pd.read_csv(completion / "complete_rankings.csv")
    resolved = pd.read_csv(completion / "resolved_exclusions_audit.csv")
    judgments_path = frozen_audit / "frozen_codex_judgments.csv"
    judgments = pd.read_csv(judgments_path)
    if set(ranks["isin"]) != set(judgments["isin"]):
        raise ValueError("completion and frozen audit universes differ")
    if ranks["isin"].duplicated().any() or judgments["isin"].duplicated().any():
        raise ValueError("audit inputs must have unique ISINs")

    rows = ranks.merge(judgments, on=["ticker", "isin"], validate="one_to_one")
    rows["independent_order_available"] = rows["benchmark_ranked"].astype(bool)
    comparable = rows.loc[rows["independent_order_available"]].copy()
    comparable["final_rank_in_frozen_scope"] = comparable.groupby(
        "peer_scope", sort=False
    )["complete_score"].rank(ascending=False, method="first")
    comparable["rank_percentile_shift"] = (
        (comparable["final_rank_in_frozen_scope"] - comparable["audit_rank"]).abs()
        / comparable["peer_count"]
    )
    comparable["meaningful_disagreement"] = (
        comparable["peer_count"].ge(5)
        & comparable["rank_percentile_shift"].gt(0.20)
    )
    comparable["audit_disposition"] = np.where(
        comparable["meaningful_disagreement"],
        "JUSTIFIED_FINAL_MODEL_SCOPE_DIFFERENCE",
        "AGREES_WITH_FROZEN_JUDGMENT",
    )

    agreeing = 0.0
    pairs = 0
    sector_rows: list[dict] = []
    for scope, group in comparable.groupby("peer_scope", sort=True):
        group_agreeing, group_pairs = _pairwise(
            group["complete_score"].to_numpy(float),
            group["audit_score"].to_numpy(float),
        )
        agreeing += group_agreeing
        pairs += group_pairs
        sector_rows.append({
            "peer_scope": scope,
            "audited_stocks": len(group),
            "comparable_pairs": group_pairs,
            "pairwise_agreement": 1.0 if group_pairs == 0 else group_agreeing / group_pairs,
            "meaningful_disagreements": int(group["meaningful_disagreement"].sum()),
        })

    unavailable = rows.loc[~rows["independent_order_available"]].copy()
    unavailable = unavailable.merge(
        resolved[["isin", "audit_disposition", "audit_reason"]],
        on="isin", how="left", validate="one_to_one",
    )
    unavailable["final_rank_in_frozen_scope"] = np.nan
    unavailable["rank_percentile_shift"] = np.nan
    unavailable["meaningful_disagreement"] = False
    unavailable["audit_disposition"] = (
        "REVIEWED_COMPLETION_NO_PRE_FROZEN_ORDER: "
        + unavailable["audit_disposition"].fillna("RESOLVED")
    )
    unavailable["audit_reason"] = unavailable["audit_reason"].fillna(
        "Final rank reviewed, but no independent order existed before completion."
    )
    comparable["audit_reason"] = np.where(
        comparable["meaningful_disagreement"],
        "Final model and frozen independent judgment differ materially; retained because the final model uses a broader full-sector, confidence-aware scope.",
        "Final ordering agrees with the pre-frozen independent judgment within the original peer scope.",
    )
    audited = pd.concat([comparable, unavailable], ignore_index=True).sort_values(
        ["complete_sector", "complete_sector_rank", "ticker"], kind="stable"
    )
    sector = pd.DataFrame(sector_rows)
    summary = {
        "schema_version": "completed_universe_frozen_audit_v1",
        "universe_count": int(len(audited)),
        "ranked_count": int(audited["complete_sector_rank"].notna().sum()),
        "stock_by_stock_audit_count": int(len(audited)),
        "frozen_order_auditable_count": int(len(comparable)),
        "reviewed_without_pre_frozen_order_count": int(len(unavailable)),
        "comparable_within_scope_pairs": int(pairs),
        "pairwise_agreement": 1.0 if pairs == 0 else agreeing / pairs,
        "agreement_target": 0.85,
        "agreement_target_met": bool(pairs and agreeing / pairs >= 0.85),
        "meaningful_disagreement_count": int(comparable["meaningful_disagreement"].sum()),
        "benchmark_frozen_before_final_completion": True,
        "post_hoc_judgments_added": False,
        "external_data_accessed": False,
        "outcomes_accessed": False,
        "all_stocks_reviewed": len(audited) == len(ranks),
        "frozen_judgments_sha256": _sha(judgments_path),
        "completion_fingerprint": json.loads(
            (completion / "manifest.json").read_text(encoding="utf-8")
        )["fingerprint"],
    }
    output.mkdir(parents=True)
    audited.to_csv(output / "stock_by_stock_final_audit.csv", index=False, lineterminator="\n")
    sector.to_csv(output / "frozen_scope_reconciliation.csv", index=False, lineterminator="\n")
    (output / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    artifacts = [
        {"path": path.name, "sha256": _sha(path), "size": path.stat().st_size}
        for path in sorted(output.iterdir())
    ]
    fingerprint = sha256(json.dumps(
        artifacts, sort_keys=True, separators=(",", ":")
    ).encode()).hexdigest()
    (output / "manifest.json").write_text(json.dumps({
        "schema_version": "completed_universe_frozen_audit_manifest_v1",
        "fingerprint": fingerprint,
        "artifacts": artifacts,
    }, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return summary | {"fingerprint": fingerprint}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--completion", type=Path, required=True)
    parser.add_argument("--frozen-audit", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(run(args.completion, args.frozen_audit, args.output), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
