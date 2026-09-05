"""Build the reusable exact-ISIN Screener bundle from all supplied archives."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

from stock_ranker.screener_data_bundle import ingest_screener_data_bundle


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--archive", action="append", required=True)
    result.add_argument("--operational-csv", required=True)
    result.add_argument("--snapshot-csv", required=True)
    result.add_argument("--universe-csv", required=True)
    result.add_argument("--existing-history-csv", required=True)
    result.add_argument("--availability-csv", required=True)
    result.add_argument("--checklist-csv", required=True)
    result.add_argument("--output-directory", required=True)
    result.add_argument("--source-observed-at", required=True)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        result = ingest_screener_data_bundle(
            archive_paths=args.archive,
            operational_csv=args.operational_csv,
            snapshot_csv=args.snapshot_csv,
            universe_csv=args.universe_csv,
            existing_history_csv=args.existing_history_csv,
            availability_csv=args.availability_csv,
            checklist_csv=args.checklist_csv,
            output_directory=args.output_directory,
            source_observed_at=args.source_observed_at,
        )
    except Exception as exc:
        print(f"Screener bundle ingestion failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result.summary, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
