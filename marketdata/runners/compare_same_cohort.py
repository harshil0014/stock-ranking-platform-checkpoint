"""Build the frozen same-cohort Baseline V1 versus Research V2 audit."""

from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.same_cohort_comparison import (  # noqa: E402
    BLIND_FINGERPRINT,
    RANKING_DATES,
    build_same_cohort_rows,
    evaluate_same_cohort,
    export_same_cohort_comparison,
)
from stock_ranker.walk_forward_blind import _baseline_from_prices  # noqa: E402


def _accepted_directory(provider_root: Path) -> Path:
    state = json.loads((provider_root / "accepted_state.json").read_text(encoding="utf-8"))
    return provider_root / str(state["accepted_batch"])


def load_identity_map(official_root: Path, bulk_root: Path) -> tuple[pd.DataFrame, dict[str, str]]:
    official_directory = _accepted_directory(official_root)
    bulk_directory = _accepted_directory(bulk_root)
    audit_path = official_directory / "classification_audit.csv"
    bulk_path = bulk_directory / "classifications.csv"
    official = pd.read_csv(audit_path, usecols=["security", "isin"])
    official = official.rename(columns={"security": "nse_symbol"})
    official = official.drop_duplicates().sort_values("nse_symbol", kind="stable")
    bulk = pd.read_csv(bulk_path, dtype=str)
    bse = bulk.loc[
        bulk["primary_exchange"].eq("BSE")
        & bulk["official_bse_code"].fillna("").ne(""),
        ["isin", "official_bse_code"],
    ].drop_duplicates("isin")
    identity = official.merge(bse, on="isin", how="left", validate="one_to_one").rename(
        columns={"official_bse_code": "bse_code"}
    )
    identity["bse_code"] = identity["bse_code"].fillna("")
    return identity, {
        "official_identity_path": audit_path.relative_to(ROOT).as_posix(),
        "official_identity_sha256": sha256(audit_path.read_bytes()).hexdigest(),
        "bulk_bse_path": bulk_path.relative_to(ROOT).as_posix(),
        "bulk_bse_sha256": sha256(bulk_path.read_bytes()).hexdigest(),
    }


def run(blind_root: Path, evaluation_root: Path, output: Path) -> str:
    blind_manifest = json.loads((blind_root / "manifest.json").read_text(encoding="utf-8"))
    if blind_manifest.get("blind_prediction_fingerprint") != BLIND_FINGERPRINT:
        raise ValueError("frozen blind prediction fingerprint mismatch")
    if blind_manifest.get("future_outcome_data_present") is not False:
        raise ValueError("formation bundle contains outcome data")
    evaluation_manifest = json.loads((evaluation_root / "manifest.json").read_text(encoding="utf-8"))
    future_path = evaluation_root / "future_returns.csv"
    recorded = next(
        item for item in evaluation_manifest["artifacts"] if item["path"] == "future_returns.csv"
    )
    if sha256(future_path.read_bytes()).hexdigest() != recorded["sha256"]:
        raise ValueError("shared future-return artifact hash mismatch")
    outcomes = pd.read_csv(future_path)
    identity, identity_provenance = load_identity_map(
        ROOT / "data/company_facts/providers/official_exchange",
        ROOT / "data/company_facts/providers/bulk_classification",
    )
    cohorts, evaluated, exclusions = [], [], []
    for ranking_date in RANKING_DATES:
        date_root = blind_root / ranking_date
        v2 = pd.read_csv(date_root / "research_v2.csv")
        v2_tickers = set(v2["ticker"].astype(str))
        universe = pd.read_csv(date_root / "historical_universe.csv")
        comparison_universe = universe.loc[
            universe["historical_symbol"].astype(str).isin(v2_tickers)
        ].copy()
        prices = pd.read_csv(date_root / "predictor_prices.csv")
        baseline, _, _ = _baseline_from_prices(comparison_universe, prices, ranking_date)
        recorded_matched = pd.read_csv(date_root / "matched_baseline.csv")
        expected = recorded_matched.loc[
            recorded_matched["comparison_status"].isin(["MATCHED_COHORT", "SINGLE_ELIGIBLE_PEER"]),
            ["ticker", "matched_baseline_sector_rank"],
        ].sort_values("ticker", kind="stable").reset_index(drop=True)
        actual = baseline[["ticker", "sector_rank"]].rename(
            columns={"sector_rank": "matched_baseline_sector_rank"}
        ).sort_values("ticker", kind="stable").reset_index(drop=True)
        if actual["ticker"].tolist() != expected["ticker"].tolist() or not (
            pd.to_numeric(actual["matched_baseline_sector_rank"]).to_numpy()
            == pd.to_numeric(expected["matched_baseline_sector_rank"]).to_numpy()
        ).all():
            raise ValueError(f"recomputed matched Baseline ranks differ for {ranking_date}")
        cohort, observed, excluded = build_same_cohort_rows(
            ranking_date, baseline, v2, outcomes, identity,
        )
        cohorts.append(cohort)
        evaluated.append(observed)
        exclusions.append(excluded)
    result = evaluate_same_cohort(
        pd.concat(cohorts, ignore_index=True),
        pd.concat(evaluated, ignore_index=True),
        pd.concat(exclusions, ignore_index=True),
    )
    result.report["identity_provenance"] = identity_provenance
    result.report["shared_outcome_sha256"] = recorded["sha256"]
    accepted_evaluation = json.loads(
        (evaluation_root / "evaluation_summary.json").read_text(encoding="utf-8")
    )
    result.report["accepted_sector_relative_evaluation"] = {
        "primary_horizon_months": accepted_evaluation["primary_horizon_months"],
        "primary": accepted_evaluation["horizons"]["12"],
        "evaluation_fingerprint": evaluation_manifest["evaluation_fingerprint"],
    }
    return export_same_cohort_comparison(result, output)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--blind-root", type=Path, default=ROOT / "data/walk_forward/blind_predictions_v1_run_01")
    parser.add_argument("--evaluation-root", type=Path, default=ROOT / "data/walk_forward/evaluation_v1_run_01")
    parser.add_argument("--output", type=Path, default=ROOT / "data/walk_forward/same_cohort_comparison_v1")
    parser.add_argument("--replace", action="store_true", help="Replace only the named generated comparison directory.")
    args = parser.parse_args(argv)
    try:
        if args.output.exists() and args.replace:
            resolved = args.output.resolve()
            generated_root = (ROOT / "data/walk_forward").resolve()
            if resolved.parent != generated_root or resolved.name != "same_cohort_comparison_v1":
                raise ValueError("refusing to replace an unexpected output path")
            shutil.rmtree(resolved)
        fingerprint = run(args.blind_root, args.evaluation_root, args.output)
    except (OSError, ValueError, KeyError) as exc:
        print(f"same-cohort comparison failed: {exc}", file=sys.stderr)
        return 1
    print(f"same-cohort comparison: {fingerprint}")
    print(f"output: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
