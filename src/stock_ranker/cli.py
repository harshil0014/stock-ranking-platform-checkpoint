"""Installed command-line interface for the stock-ranking engine."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from stock_ranker.baseline import (
    calculate_baseline_rankings,
    get_top_stocks_by_sector,
)
from stock_ranker.config import BaselineConfig
from stock_ranker.exporting import export_rankings
from stock_ranker.ingestion import load_stock_csv


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
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process-compatible exit code."""

    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        config = BaselineConfig(top_n=args.top_n)
        input_data = load_stock_csv(args.input_csv)
        full_rankings = calculate_baseline_rankings(input_data, config)
        top_rankings = get_top_stocks_by_sector(
            full_rankings, config.top_n
        )
        exported = export_rankings(
            full_rankings,
            top_rankings,
            args.output_dir,
            config.top_n,
        )
    except (ValueError, TypeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2

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
