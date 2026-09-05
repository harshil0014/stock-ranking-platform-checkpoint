"""Cache and normalize public Screener standalone history at PIT-safe scale."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from stock_ranker.screener_historical_fundamentals import (  # noqa: E402
    build_screener_pit_cohorts,
    official_clock_from_availability,
    sha256_file,
)
from stock_ranker.screener_public_history import (  # noqa: E402
    acquire_public_company_pages,
    parse_cached_public_pages,
)


RANKING_DATES = [
    date(2022, 8, 5), date(2023, 8, 7), date(2024, 8, 7),
    date(2025, 8, 7), date(2026, 8, 21),
]


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g")


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8", newline="\n")


def _fingerprint(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _identities(availability: pd.DataFrame, bulk_paths: list[Path]) -> tuple[pd.DataFrame, dict[str, str]]:
    available = availability.loc[
        availability["pit_available"].map(lambda x: x is True or str(x).lower() == "true")
        & availability["conventional_roce_applicability"].eq("STANDARD_PROBE")
    ][["ticker", "isin"]].drop_duplicates()
    available["ticker"] = available["ticker"].astype(str).str.strip().str.upper()
    available["isin"] = available["isin"].astype(str).str.strip().str.upper()
    bulk_frames: list[pd.DataFrame] = []
    hashes: dict[str, str] = {}
    for path in bulk_paths:
        raw = pd.read_csv(path)
        required = {"Name", "NSE Code", "ISIN Code"}
        if not required.issubset(raw.columns):
            raise ValueError(f"{path.name}: missing bulk identity columns")
        item = raw[["Name", "NSE Code", "ISIN Code"]].rename(
            columns={"Name": "company", "NSE Code": "ticker", "ISIN Code": "isin"}
        )
        item = item.dropna(subset=["ticker", "isin"])
        item["ticker"] = item["ticker"].astype(str).str.strip().str.upper()
        item["isin"] = item["isin"].astype(str).str.strip().str.upper()
        bulk_frames.append(item)
        hashes[path.name] = sha256_file(path)
    bulk = pd.concat(bulk_frames, ignore_index=True).sort_values(["isin", "ticker"], kind="stable")
    conflicts = bulk.groupby("isin").agg(tickers=("ticker", "nunique"), companies=("company", "nunique"))
    if (conflicts["tickers"] > 1).any():
        raise ValueError("bulk exports disagree on ISIN-to-NSE identity")
    bulk = bulk.drop_duplicates("isin", keep="last")
    merged = available.merge(bulk, on=["ticker", "isin"], how="left", validate="one_to_one")
    if merged["company"].isna().any():
        missing = merged.loc[merged["company"].isna(), "ticker"].tolist()
        raise ValueError(f"official-clock identities absent from exact Screener bulk mapping: {missing[:20]}")
    return merged[["ticker", "isin", "company"]].sort_values("ticker", kind="stable").reset_index(drop=True), hashes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--availability-csv", type=Path, required=True)
    parser.add_argument("--bulk-csv", type=Path, action="append", required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--delay-seconds", type=float, default=15.0)
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--request-budget", type=int, default=5)
    parser.add_argument("--max-consecutive-failures", type=int, default=1)
    args = parser.parse_args()
    if (args.delay_seconds < 0 or (args.max_records is not None and args.max_records < 1)
            or args.request_budget < 0 or args.max_consecutive_failures < 1):
        parser.error("invalid delay, record, request-budget, or failure-circuit setting")

    availability = pd.read_csv(args.availability_csv)
    identities, bulk_hashes = _identities(availability, args.bulk_csv)
    if args.max_records:
        identities = identities.head(args.max_records).copy()
    manifest = acquire_public_company_pages(
        identities, args.cache_dir, delay_seconds=args.delay_seconds, refresh=args.refresh,
        request_budget=args.request_budget,
        max_consecutive_failures=args.max_consecutive_failures,
    )
    normalized, page_failures = parse_cached_public_pages(manifest)
    clock = official_clock_from_availability(availability)
    result = build_screener_pit_cohorts(normalized, clock, RANKING_DATES)

    outputs = {
        "acquisition_manifest.csv": manifest,
        "normalized_financials.csv": result.normalized,
        "page_failures.csv": page_failures,
        "pit_selected.csv": result.accepted,
        "pit_rejected.csv": result.rejected,
        "cohort_summary.csv": result.cohort_summary,
    }
    for name, frame in outputs.items():
        _write_csv(args.output / name, frame)
    statuses = (
        result.rejected.groupby(["ranking_date", "period_status"], dropna=False).size()
        .rename("count").reset_index()
    ) if len(result.rejected) else pd.DataFrame(columns=["ranking_date", "period_status", "count"])
    _write_csv(args.output / "rejection_summary.csv", statuses)
    summary = {
        "schema_version": "screener_public_history_build_v1",
        "identity_count": len(identities),
        "acquired_or_cached_count": len(manifest),
        "page_parse_success_count": int(result.normalized["isin"].nunique()) if len(result.normalized) else 0,
        "page_parse_failure_count": int(
            (~page_failures.get("status", pd.Series(dtype=str)).eq("DEFERRED_REQUEST_BUDGET")).sum()
        ),
        "page_deferred_count": int(
            page_failures.get("status", pd.Series(dtype=str)).eq("DEFERRED_REQUEST_BUDGET").sum()
        ),
        "acquisition_status_counts": manifest["cache_status"].value_counts().sort_index().to_dict(),
        "normalized_period_count": len(result.normalized),
        "precision_pass_period_count": int(result.normalized.get("source_precision_status", pd.Series(dtype=str)).eq("PASS").sum()),
        "cohorts": result.cohort_summary.to_dict("records"),
        "bulk_source_hashes": bulk_hashes,
        "availability_sha256": sha256_file(args.availability_csv),
        "normalized_fingerprint": _fingerprint(result.normalized),
        "selected_fingerprint": _fingerprint(result.accepted),
        "policy": (
            "Exact ISIN comes from supplied Screener Premium bulk exports; public standalone "
            "statement values use visible rounded crore data with interval quality gates; exact "
            "official exchange timestamps provide the PIT clock. No value is backdated or imputed."
        ),
    }
    _write_json(args.output / "build_summary.json", summary)
    inventory = []
    for path in sorted(args.output.iterdir(), key=lambda item: item.name):
        if path.is_file() and path.name != "artifact_inventory.json":
            inventory.append({"path": path.name, "sha256": sha256_file(path), "size": path.stat().st_size})
    _write_json(args.output / "artifact_inventory.json", inventory)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
