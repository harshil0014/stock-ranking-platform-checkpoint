"""Prepare hash-pinned Screener standalone history with an official PIT clock."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import shutil
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.data_state import atomic_write_json  # noqa: E402
from stock_ranker.screener_historical_fundamentals import (  # noqa: E402
    SCREENER_HISTORICAL_CONTRACT_VERSION,
    build_screener_pit_cohorts,
    calibrate_screener_against_gold,
    official_clock_from_availability,
    parse_screener_historical_workbook,
)
from stock_ranker.screener_premium_reference import reconcile_screener_exports  # noqa: E402


DEFAULT_RANKING_DATES = [
    date(2022, 8, 5), date(2023, 8, 7), date(2024, 8, 7),
    date(2025, 8, 7), date(2026, 8, 21),
]


def _fingerprint(frame: pd.DataFrame, columns: list[str]) -> str:
    stable = frame.loc[:, columns].copy()
    for column in stable.columns:
        if pd.api.types.is_datetime64_any_dtype(stable[column]):
            stable[column] = stable[column].map(lambda value: value.isoformat())
    payload = stable.to_csv(index=False, lineterminator="\n", float_format="%.17g").encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workbook-dir", type=Path, required=True)
    parser.add_argument("--availability-csv", type=Path, required=True)
    parser.add_argument("--gold-validation", type=Path, required=True)
    parser.add_argument("--bulk-export", action="append", type=Path, default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ranking-date", action="append", default=[])
    args = parser.parse_args(argv)

    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    if manifest.get("contract_version") != SCREENER_HISTORICAL_CONTRACT_VERSION:
        raise ValueError("unexpected Screener historical contract version")
    frames = []
    for record in manifest.get("records", []):
        frames.append(
            parse_screener_historical_workbook(args.workbook_dir / record["filename"], record)
        )
    if not frames:
        raise ValueError("manifest contains no workbooks")
    normalized = pd.concat(frames, ignore_index=True)
    availability_raw = pd.read_csv(args.availability_csv)
    clock = official_clock_from_availability(availability_raw)
    ranking_dates = (
        [date.fromisoformat(item) for item in args.ranking_date]
        if args.ranking_date else DEFAULT_RANKING_DATES
    )
    result = build_screener_pit_cohorts(normalized, clock, ranking_dates)
    gold = json.loads(args.gold_validation.read_text(encoding="utf-8"))
    calibration, calibration_summary = calibrate_screener_against_gold(
        result.normalized, gold["records"]
    )
    if calibration_summary["calibration_status"] != "PASS":
        raise ValueError("Screener calibration failed; no PIT outputs written")

    args.output_dir.mkdir(parents=True, exist_ok=False)
    cache_dir = args.output_dir / "source_workbooks"
    cache_dir.mkdir()
    cached_sources: list[dict[str, object]] = []
    for record in manifest["records"]:
        source = args.workbook_dir / record["filename"]
        destination = cache_dir / f"{record['isin']}__{record['workbook_sha256']}.xlsx"
        shutil.copyfile(source, destination)
        copied_hash = hashlib.sha256(destination.read_bytes()).hexdigest()
        if copied_hash != record["workbook_sha256"]:
            raise ValueError(f"cached workbook hash mismatch: {record['filename']}")
        cached_sources.append({
            "isin": record["isin"], "ticker": record["ticker"],
            "source_filename": record["filename"],
            "cached_relative_path": destination.relative_to(args.output_dir).as_posix(),
            "sha256": copied_hash, "source_observed_at": record["source_observed_at"],
            "reporting_basis": record["reporting_basis"],
        })
    csv_options = {"index": False, "encoding": "utf-8", "lineterminator": "\n", "float_format": "%.17g"}
    result.normalized.to_csv(args.output_dir / "normalized_screener_history.csv", **csv_options)
    result.accepted.to_csv(args.output_dir / "pit_selected_fundamentals.csv", **csv_options)
    result.rejected.to_csv(args.output_dir / "pit_rejected_periods.csv", **csv_options)
    result.cohort_summary.to_csv(args.output_dir / "pit_cohort_summary.csv", **csv_options)
    calibration.to_csv(args.output_dir / "calibration_details.csv", **csv_options)
    atomic_write_json(args.output_dir / "source_cache_manifest.json", {
        "schema_version": "screener_workbook_cache_v1", "records": cached_sources,
    })
    bulk_summary: dict[str, object] = {
        "provided": False,
        "historical_standalone_usable": False,
        "reason": "No bulk exports supplied.",
    }
    if args.bulk_export:
        bulk = reconcile_screener_exports(args.bulk_export)
        bulk.rows.to_csv(args.output_dir / "bulk_reference_rows.csv", **csv_options)
        bulk.conflicts.to_csv(args.output_dir / "bulk_reference_conflicts.csv", **csv_options)
        manifest_isins = {str(record["isin"]) for record in manifest["records"]}
        exact = set(bulk.rows["isin"].astype(str)) & manifest_isins
        bulk_summary = {
            "provided": True,
            "row_count": len(bulk.rows),
            "conflict_count": len(bulk.conflicts),
            "fingerprint": bulk.manifest["fingerprint"],
            "calibration_manifest_exact_isin_matches": len(exact),
            "historical_standalone_usable": False,
            "reason": (
                "The supplied bulk columns have no explicit financial period or reporting basis; "
                "they remain current/default-basis secondary reference evidence."
            ),
        }
        truth = availability_raw["pit_available"].map(
            lambda value: value is True or str(value).strip().lower() == "true"
        )
        queue = availability_raw.loc[truth].copy()
        queue = queue.loc[~queue["isin"].astype(str).isin(manifest_isins)]
        queue = queue.merge(
            bulk.rows[["isin", "reference_company", "reference_nse_code"]],
            on="isin", how="left", validate="many_to_one",
        )
        queue["acquisition_status"] = "AWAITING_HASH_PINNED_STANDALONE_WORKBOOK"
        queue["required_basis"] = "STANDALONE"
        queue = queue[[
            "ranking_date", "financial_year", "ticker", "isin", "reference_company",
            "reference_nse_code", "dissemination_timestamp", "source_url",
            "required_basis", "acquisition_status",
        ]].sort_values(["ranking_date", "ticker", "isin"], kind="stable")
        queue.to_csv(args.output_dir / "standalone_workbook_acquisition_queue.csv", **csv_options)
        priority = queue.loc[queue["ranking_date"].astype(str).eq("2025-08-07")]
        bulk_summary["verified_clock_rows_awaiting_workbook"] = len(queue)
        bulk_summary["fy2025_priority_issuers_awaiting_workbook"] = int(priority["isin"].nunique())
    summary = {
        "schema_version": "screener_historical_pit_build_v1",
        "contract_version": SCREENER_HISTORICAL_CONTRACT_VERSION,
        "workbook_count": len(manifest["records"]),
        "normalized_period_count": len(result.normalized),
        "calibration": calibration_summary,
        "bulk_exports": bulk_summary,
        "cohorts": result.cohort_summary.to_dict("records"),
        "normalized_fingerprint": _fingerprint(
            result.normalized,
            ["isin", "period_end", "roce", "debt_to_equity", "current_pat", "prior_pat", "source_workbook_sha256"],
        ),
        "selected_fingerprint": _fingerprint(
            result.accepted,
            ["ranking_date", "isin", "period_end", "roce", "debt_to_equity", "current_pat", "prior_pat", "official_available_at"],
        ),
        "historical_evaluation_ready": False,
        "readiness_reason": (
            "The calibration pack proves the contract but does not provide hundreds of hash-pinned standalone company histories."
        ),
    }
    atomic_write_json(args.output_dir / "build_summary.json", summary)
    print(
        f"Prepared {len(result.normalized)} periods from {len(manifest['records'])} workbooks; "
        f"calibration {calibration_summary['calibration_status']}; historical evaluation not started."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
