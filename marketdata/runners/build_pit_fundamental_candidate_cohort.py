"""Build a non-production expanded Research V2 candidate cohort from validated reports."""

from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import sys

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.pit_accounting_promotion import (  # noqa: E402
    CANDIDATE_SCHEMA, canonical_json, file_sha256, merge_candidate_fundamentals,
    validated_fundamental_candidates,
)
from stock_ranker.research_v2 import ResearchV2Inputs, calculate_research_v2  # noqa: E402
from stock_ranker.v2_config import ResearchV2Config  # noqa: E402


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validation-records", type=Path, required=True)
    parser.add_argument("--accepted-bundle", type=Path, required=True)
    parser.add_argument("--live-market", type=Path, required=True)
    parser.add_argument("--history-cache", type=Path, required=True)
    parser.add_argument("--ranking-date", type=date.fromisoformat, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.output_dir.exists():
        parser.error(f"output directory already exists: {args.output_dir}")
    records = json.loads(args.validation_records.read_text(encoding="utf-8"))
    additions, evidence, deferred = validated_fundamental_candidates(records, ranking_date=args.ranking_date)
    existing = pd.read_csv(args.accepted_bundle / "fundamentals.csv")
    combined = merge_candidate_fundamentals(existing, additions)
    accepted_universe = pd.read_csv(args.accepted_bundle / "universe.csv")[["ticker", "company", "sector"]]
    live = pd.read_csv(args.live_market)
    live_identity = live[["ticker", "company", "sector"]].drop_duplicates("ticker").set_index("ticker")
    new_tickers = sorted(set(additions["ticker"]) - set(accepted_universe["ticker"]))
    missing_identity = [ticker for ticker in new_tickers if ticker not in live_identity.index]
    if missing_identity:
        raise ValueError(f"candidate tickers absent from live exact identity universe: {missing_identity}")
    evidence_identity = {
        item["ticker"]: {"ticker": item["ticker"], "company": item["company"], "sector": item["sector"]}
        for item in evidence
    }
    new_universe = pd.DataFrame([evidence_identity[ticker] for ticker in new_tickers])
    if new_universe[["ticker", "company", "sector"]].isna().any().any():
        raise ValueError("validated evidence contains incomplete exact identity/classification")
    universe = pd.concat([accepted_universe, new_universe], ignore_index=True)
    if universe["ticker"].duplicated().any():
        raise ValueError("candidate universe contains duplicate ticker")
    price_frames: list[pd.DataFrame] = []
    for ticker in sorted(universe["ticker"].astype(str)):
        path = args.history_cache / f"{ticker}.csv"
        if not path.is_file():
            continue
        frame = pd.read_csv(path, usecols=["date", "adjusted_close"])
        frame.insert(0, "ticker", ticker)
        frame = frame.loc[frame["date"].astype(str) <= args.ranking_date.isoformat()]
        price_frames.append(frame)
    prices = pd.concat(price_frames, ignore_index=True)
    result = calculate_research_v2(
        ResearchV2Inputs(universe=universe, prices=prices, fundamentals=combined),
        ResearchV2Config(ranking_date=args.ranking_date),
    )
    eligible = result.eligibility.loc[result.eligibility["eligible"].astype(bool), "ticker"].astype(str)
    args.output_dir.mkdir(parents=True)
    _write_csv(universe.sort_values(["sector", "ticker"], kind="stable"), args.output_dir / "universe.csv")
    _write_csv(combined, args.output_dir / "fundamentals.csv")
    _write_csv(result.rankings, args.output_dir / "candidate_rankings.csv")
    _write_csv(result.eligibility, args.output_dir / "candidate_eligibility.csv")
    (args.output_dir / "validated_addition_evidence.json").write_text(canonical_json(evidence) + "\n", encoding="utf-8", newline="\n")
    summary = {
        "schema_version": CANDIDATE_SCHEMA,
        "ranking_date": args.ranking_date.isoformat(),
        "existing_accepted_fundamental_count": len(existing),
        "pre_cutoff_validated_addition_count": len(additions),
        "post_cutoff_deferred_count": len(deferred),
        "candidate_fundamental_count": len(combined),
        "candidate_engine_eligible_count": len(eligible),
        "new_candidate_tickers": new_tickers,
        "deferred": deferred,
        "production_mapping_modified": False,
        "frozen_bundle_modified": False,
        "scientific_boundary": "Versioned candidate cohort only; no accepted mapping or frozen research mutation.",
        "source_hashes": {
            "independent_validation_records": file_sha256(args.validation_records),
            "accepted_fundamentals": file_sha256(args.accepted_bundle / "fundamentals.csv"),
        },
    }
    for name in ("universe.csv", "fundamentals.csv", "candidate_rankings.csv", "candidate_eligibility.csv", "validated_addition_evidence.json"):
        summary.setdefault("output_hashes", {})[name] = file_sha256(args.output_dir / name)
    (args.output_dir / "candidate_summary.json").write_text(canonical_json(summary) + "\n", encoding="utf-8", newline="\n")
    print(canonical_json(summary))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
