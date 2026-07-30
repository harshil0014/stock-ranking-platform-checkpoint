"""Installed command-line interface for the stock-ranking engine."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

from stock_ranker.baseline import (
    calculate_baseline_rankings,
    get_top_stocks_by_sector,
)
from stock_ranker.config import BaselineConfig
from stock_ranker.exporting import export_rankings
from stock_ranker.ingestion import load_stock_csv
from stock_ranker.research_v2 import (
    calculate_research_v2,
    get_top_research_v2_by_sector,
    load_research_v2_inputs,
)
from stock_ranker.v2_config import ResearchV2Config
from stock_ranker.v2_exporting import export_research_v2_results


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="stock-ranker",
        description="Offline stock-ranking research engine.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    rank = subparsers.add_parser(
        "rank", help="Generate Baseline V1 full and top-N rankings."
    )
    rank.add_argument("--input", required=True, type=Path, dest="input_csv")
    rank.add_argument("--output-dir", required=True, type=Path)
    rank.add_argument("--top-n", default=5, type=int)
    research_v2 = subparsers.add_parser(
        "research-v2",
        help="Generate point-in-time Research V2 rankings.",
    )
    research_v2.add_argument("--universe", required=True, type=Path)
    research_v2.add_argument("--prices", required=True, type=Path)
    research_v2.add_argument("--fundamentals", required=True, type=Path)
    research_v2.add_argument("--ranking-date", required=True)
    research_v2.add_argument("--output-dir", required=True, type=Path)
    research_v2.add_argument("--top-n", default=5, type=int)
    return parser


def _run_baseline(args: argparse.Namespace) -> int:
    config = BaselineConfig(top_n=args.top_n)
    input_data = load_stock_csv(args.input_csv)
    full_rankings = calculate_baseline_rankings(input_data, config)
    top_rankings = get_top_stocks_by_sector(full_rankings, config.top_n)
    exported = export_rankings(
        full_rankings, top_rankings, args.output_dir, config.top_n
    )
    print(
        f"Processed {len(full_rankings)} stocks across "
        f"{full_rankings['sector'].nunique()} sectors."
    )
    print(
        f"Selected {len(top_rankings)} stocks "
        f"(up to {config.top_n} per sector)."
    )
    print(f"Full rankings: {exported.full_rankings_path}")
    print(f"Top rankings: {exported.top_rankings_path}")
    return 0


def _parse_ranking_date(value: str):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError as exc:
        raise ValueError("ranking_date must use valid ISO YYYY-MM-DD format") from exc


def _run_research_v2(args: argparse.Namespace) -> int:
    config = ResearchV2Config(
        ranking_date=_parse_ranking_date(args.ranking_date),
        top_n=args.top_n,
    )
    inputs = load_research_v2_inputs(
        args.universe, args.prices, args.fundamentals
    )
    result = calculate_research_v2(inputs, config)
    top_rankings = get_top_research_v2_by_sector(
        result.rankings, config.top_n
    )
    exported = export_research_v2_results(
        result, top_rankings, args.output_dir, config.top_n
    )
    eligible_count = len(result.rankings)
    ineligible_count = int((~result.eligibility["eligible"]).sum())
    print(
        f"Evaluated {len(result.eligibility)} stocks: "
        f"{eligible_count} eligible, {ineligible_count} ineligible."
    )
    print(
        f"Selected {len(top_rankings)} stocks "
        f"(up to {config.top_n} per sector)."
    )
    print(f"Full rankings: {exported.full_rankings_path}")
    print(f"Top rankings: {exported.top_rankings_path}")
    print(f"Eligibility report: {exported.eligibility_report_path}")
    if result.rankings.empty:
        print("Error: No stocks are eligible for Research V2.", file=sys.stderr)
        return 3
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process-compatible exit code."""

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "rank":
            return _run_baseline(args)
        return _run_research_v2(args)
    except (ValueError, TypeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
