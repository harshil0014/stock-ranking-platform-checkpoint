from __future__ import annotations

import argparse
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sys
from zoneinfo import ZoneInfo

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from marketdata.runners.acquire_nse_annual_reports import acquire  # noqa: E402
from stock_ranker.pit_fundamental_scale import (  # noqa: E402
    audit_historical_report_availability,
    build_pit_fundamental_population,
    select_report_download_batch,
    summarize_annual_report_metadata,
)


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8", newline="\n",
    )


def _accepted_company_facts() -> Path:
    state = json.loads((ROOT / "data/company_facts/accepted_state.json").read_text(encoding="utf-8"))
    return ROOT / "data/company_facts" / state["snapshot_path"] / "company_facts.csv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Discover official annual-report availability for the complete PIT fundamental population."
    )
    parser.add_argument("--company-facts", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ranking-date", default="2026-08-21")
    parser.add_argument("--financial-year-start", default="2025")
    parser.add_argument("--financial-year-end", default="2026")
    parser.add_argument("--download-batch-size", type=int, default=250)
    parser.add_argument("--reuse-metadata", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.exists():
            raise ValueError(f"output already exists: {args.output}")
        facts_path = args.company_facts or _accepted_company_facts()
        population = build_pit_fundamental_population(pd.read_csv(facts_path, low_memory=False))
        args.output.mkdir(parents=True)
        population_path = args.output / "population.csv"
        population.to_csv(population_path, index=False, encoding="utf-8", lineterminator="\n")
        metadata_root = args.output / "annual_report_metadata"
        if args.reuse_metadata:
            metadata_root = args.reuse_metadata.resolve()
        else:
            cutoff = datetime.fromisoformat(args.ranking_date).replace(
                hour=23, minute=59, second=59, tzinfo=ZoneInfo("Asia/Kolkata")
            )
            acquire(
                population_path, metadata_root, None, cutoff=cutoff,
                from_year=args.financial_year_start, to_year=args.financial_year_end,
                download_pdfs=False,
            )
        matrix, summary = summarize_annual_report_metadata(
            population, metadata_root / "annual_report_provenance.json"
        )
        batch = select_report_download_batch(matrix, args.download_batch_size)
        matrix.to_csv(args.output / "metadata_coverage.csv", index=False, encoding="utf-8", lineterminator="\n")
        batch.to_csv(args.output / "download_batch.csv", index=False, encoding="utf-8", lineterminator="\n")
        summary.update({
            "schema_version": "pit_fundamental_scale_discovery_v1",
            "ranking_date": args.ranking_date,
            "financial_year": f"{args.financial_year_start}-{args.financial_year_end[-2:]}",
            "download_batch_count": len(batch),
            "population_sha256": sha256(population_path.read_bytes()).hexdigest(),
            "frozen_research_modified": False,
        })
        historical_dates = {
            "2021-2022": "2022-08-05",
            "2022-2023": "2023-08-07",
            "2023-2024": "2024-08-07",
            "2024-2025": "2025-08-07",
            "2025-2026": args.ranking_date,
        }
        historical, historical_summary = audit_historical_report_availability(
            population, metadata_root / "metadata", historical_dates,
        )
        historical.to_csv(
            args.output / "historical_report_availability.csv", index=False,
            encoding="utf-8", lineterminator="\n",
        )
        _write_json(args.output / "historical_report_availability_summary.json", historical_summary)
        summary["historical_availability_fingerprint"] = historical_summary["availability_fingerprint"]
        _write_json(args.output / "discovery_summary.json", summary)
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"PIT fundamental scale discovery failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
