"""Installed command-line interface for the stock-ranking engine."""

from __future__ import annotations

import argparse
import subprocess
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
from stock_ranker.professor_reference import (
    benchmark_professor_reference,
    export_professor_reference,
)
from stock_ranker.professor_acceptance import (
    build_professor_acceptance,
    export_professor_acceptance,
)
from stock_ranker.professor_strategy import (
    benchmark_professor_strategy,
    export_professor_strategy,
)
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
    subparsers.add_parser("personalized", help="Opt-in personalized research export; use personalized --help for profile options.", add_help=False)
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
    reference = subparsers.add_parser(
        "professor-reference",
        help="Benchmark Baseline V1 against the Baba Venkeesh workbook offline.",
    )
    reference.add_argument("--workbook", required=True, type=Path)
    reference.add_argument("--output-dir", required=True, type=Path)
    reference.add_argument("--live-market", type=Path, default=Path("data/live_market/current/live_market.csv"))
    reference.add_argument("--history-cache", type=Path, default=Path("data/live_market/history_cache"))
    reference.add_argument(
        "--evaluation-summary", type=Path,
        default=Path("data/walk_forward/evaluation_v1_run_01/evaluation_summary.json"),
    )
    acceptance = subparsers.add_parser(
        "professor-acceptance",
        help="Audit an externally supplied professor cohort without fuzzy identity matching.",
    )
    acceptance.add_argument("--request", required=True, type=Path)
    acceptance.add_argument("--identity-evidence", required=True, type=Path)
    acceptance.add_argument("--output-dir", required=True, type=Path)
    acceptance.add_argument("--live-market", type=Path, default=Path("data/live_market/current/live_market.csv"))
    acceptance.add_argument("--nse-history", type=Path, default=Path("data/live_market/history_cache"))
    acceptance.add_argument("--supplemental-nse-history", type=Path, default=Path("data/professor_reference/acceptance_nse_history"))
    acceptance.add_argument("--bse-history", type=Path, default=Path("data/professor_reference/acceptance_bse_history"))
    acceptance.add_argument(
        "--bse-snapshot", type=Path,
        default=Path("data/professor_reference/bse_bhavcopy_20260807.csv"),
    )
    strategy = subparsers.add_parser(
        "professor-strategy",
        help="Audit the OK Strategy workbook against the exact professor cohort.",
    )
    strategy.add_argument("--workbook", required=True, type=Path)
    strategy.add_argument("--request", type=Path, default=Path("data/professor_reference/acceptance_request.json"))
    strategy.add_argument("--acceptance-csv", type=Path, default=Path("data/professor_reference/acceptance_current/security_acceptance.csv"))
    strategy.add_argument("--output-dir", required=True, type=Path)
    strategy.add_argument("--screener-export", type=Path)
    strategy.add_argument("--screener-source-date")
    refresh = subparsers.add_parser(
        "refresh", help="Refresh the accepted current market state from free public sources."
    )
    refresh.add_argument("--dry-run", action="store_true")
    refresh.add_argument("--status", action="store_true")
    refresh.add_argument("--force", action="store_true")
    refresh.add_argument("--no-history-download", action="store_true")
    data_refresh = subparsers.add_parser(
        "data-refresh", help="Refresh market, secondary facts and the coherent offline fact state."
    )
    data_refresh.add_argument("--dry-run", action="store_true")
    data_refresh.add_argument("--status", action="store_true")
    data_refresh.add_argument("--full-backfill", action="store_true")
    data_refresh.add_argument("--secondary-limit", type=int, default=250)
    data_refresh.add_argument("--provider", choices=("all", "official", "yahoo", "screener"), default="all")
    backfill = subparsers.add_parser(
        "data-backfill", help="Resume the broad secondary-fact backfill and rebuild accepted facts."
    )
    backfill.add_argument("--dry-run", action="store_true")
    backfill.add_argument("--resume", action="store_true")
    backfill.add_argument("--retry-errors", action="store_true")
    backfill.add_argument("--batch-id", default="full-nse-backfill")
    backfill.add_argument("--seed-batch")
    facts = subparsers.add_parser(
        "company-facts", help="Build the accepted offline company-fact layer from cached evidence."
    )
    facts.add_argument("--dry-run", action="store_true")
    facts.add_argument("--state-root", type=Path, default=Path("data/company_facts"))
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


def _run_professor_reference(args: argparse.Namespace) -> int:
    result = benchmark_professor_reference(
        args.workbook, live_market_path=args.live_market,
        history_cache=args.history_cache,
        evaluation_summary_path=args.evaluation_summary,
    )
    manifest = export_professor_reference(result, args.output_dir)
    print(
        f"Professor reference: {result.audit['reference_verdict']} "
        f"({result.audit['exact_identity_match_count']} exact NSE identities)."
    )
    print(f"Research V2 evidence: {result.audit['research_v2_verdict']}.")
    print(f"Benchmark manifest: {manifest}")
    return 0


def _run_professor_acceptance(args: argparse.Namespace) -> int:
    result = build_professor_acceptance(
        args.request, args.identity_evidence, live_market_path=args.live_market,
        nse_history_root=args.nse_history,
        supplemental_nse_history_root=args.supplemental_nse_history,
        bse_history_root=args.bse_history,
        bse_snapshot_path=args.bse_snapshot,
    )
    manifest = export_professor_acceptance(result, args.output_dir)
    counts = result.audit["resolution_counts"]
    print(f"Professor cohort: {len(result.securities)} securities; {counts}.")
    print(f"Reference ranking: {result.audit['reference_ranking_verdict']}.")
    print(f"Acceptance manifest: {manifest}")
    return 0


def _run_professor_strategy(args: argparse.Namespace) -> int:
    source_date = _parse_ranking_date(args.screener_source_date) if args.screener_source_date else None
    result = benchmark_professor_strategy(
        args.workbook, request_path=args.request, acceptance_csv=args.acceptance_csv,
        screener_export_path=args.screener_export, screener_source_date=source_date,
    )
    manifest = export_professor_strategy(result, args.output_dir)
    print(
        f"Professor strategy: {result.audit['reference_verdict']} "
        f"({result.audit['exact_sip_rank_position_count']} exact positions)."
    )
    print(f"Research V2 evidence: {result.audit['research_v2_verdict']}.")
    print(f"Strategy manifest: {manifest}")
    return 0


def _run_refresh(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    runner = root / "marketdata" / "runners" / "refresh_live_market.py"
    market_python = root / ".venv-marketdata" / "Scripts" / "python.exe"
    interpreter = market_python if market_python.is_file() else Path(sys.executable)
    command = [str(interpreter), str(runner)]
    for flag, enabled in (
        ("--dry-run", args.dry_run), ("--status", args.status),
        ("--force", args.force), ("--no-history-download", args.no_history_download),
    ):
        if enabled:
            command.append(flag)
    return subprocess.run(command, cwd=root, check=False).returncode


def _run_company_facts(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    runner = root / "marketdata" / "runners" / "prepare_company_facts.py"
    command = [sys.executable, str(runner), "--state-root", str(args.state_root)]
    if args.dry_run:
        command.append("--dry-run")
    return subprocess.run(command, cwd=root, check=False).returncode


def _run_data_refresh(args: argparse.Namespace) -> int:
    root = Path(__file__).resolve().parents[2]
    runner = root / "marketdata" / "runners" / "refresh_company_data.py"
    market_python = root / ".venv-marketdata" / "Scripts" / "python.exe"
    interpreter = market_python if market_python.is_file() else Path(sys.executable)
    command = [str(interpreter), str(runner), "--secondary-limit", str(args.secondary_limit),
               "--provider", args.provider]
    for flag, enabled in (("--dry-run", args.dry_run), ("--status", args.status),
                          ("--full-backfill", args.full_backfill)):
        if enabled:
            command.append(flag)
    for flag in ("resume", "retry_errors"):
        if getattr(args, flag, False):
            command.append("--" + flag.replace("_", "-"))
    for option in ("batch_id", "seed_batch"):
        value = getattr(args, option, None)
        if value:
            command.extend(["--" + option.replace("_", "-"), str(value)])
    return subprocess.run(command, cwd=root, check=False).returncode


def main(argv: Sequence[str] | None = None) -> int:
    """Run the CLI and return a process-compatible exit code."""

    arguments = list(argv) if argv is not None else sys.argv[1:]
    if arguments and arguments[0] == "personalized":
        from stock_ranker.personalized_cli import main as personalized_main
        try:
            return personalized_main(arguments[1:])
        except (ValueError, TypeError, OSError) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 2
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
        if args.command == "rank":
            return _run_baseline(args)
        if args.command == "research-v2":
            return _run_research_v2(args)
        if args.command == "professor-reference":
            return _run_professor_reference(args)
        if args.command == "professor-acceptance":
            return _run_professor_acceptance(args)
        if args.command == "professor-strategy":
            return _run_professor_strategy(args)
        if args.command == "company-facts":
            return _run_company_facts(args)
        if args.command == "data-refresh":
            return _run_data_refresh(args)
        if args.command == "data-backfill":
            args.secondary_limit = 0
            args.provider = "yahoo"
            args.status = False
            args.full_backfill = True
            return _run_data_refresh(args)
        return _run_refresh(args)
    except (ValueError, TypeError, OSError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2
