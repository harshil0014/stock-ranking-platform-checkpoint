from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.pit_annual_report_validation import (  # noqa: E402
    export_annual_report_validation,
    validate_reviewed_annual_reports,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate reviewed PIT fundamentals against cached official NSE annual reports."
    )
    parser.add_argument(
        "--specification", type=Path,
        default=ROOT / "marketdata/specifications/pit_annual_report_validation_14.json",
    )
    parser.add_argument(
        "--coverage-matrix", type=Path,
        default=ROOT / "data/marketdata/pit-fundamental-probe-2026-08-21-50-analysis-v3/coverage_matrix.csv",
    )
    parser.add_argument(
        "--acquisition-root", type=Path,
        default=ROOT / "data/marketdata/pit-fundamental-probe-2026-08-21-50/annual_reports",
    )
    parser.add_argument(
        "--text-root", type=Path,
        default=ROOT / "data/marketdata/pit-fundamental-probe-2026-08-21-50/annual_report_audit/text",
    )
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "data/marketdata/pit-annual-report-validation-2026-08-21-v1",
    )
    parser.add_argument("--ranking-date", default="2026-08-21")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = validate_reviewed_annual_reports(
            args.specification, args.coverage_matrix, args.acquisition_root,
            args.text_root, ranking_date=args.ranking_date,
        )
        export_annual_report_validation(result, args.output_dir)
    except (OSError, ValueError, KeyError) as exc:
        print(f"annual-report validation failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"validated {result.summary['attempted_count']} reports: "
        f"{result.summary['complete_direct_disclosure_count']} complete, "
        f"{result.summary['v2_numeric_policy_usable_count']} V2-usable candidates, "
        f"{result.summary['ambiguous_or_unresolved_count']} unresolved"
    )
    print(args.output_dir.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
