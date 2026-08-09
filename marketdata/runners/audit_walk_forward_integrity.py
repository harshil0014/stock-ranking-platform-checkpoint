"""Audit frozen predictor inputs without reading or producing outcomes."""

from __future__ import annotations

import argparse
import csv
from datetime import datetime
from hashlib import sha256
import json
import math
from pathlib import Path
import sys


METRICS = (
    "return_1y", "cagr_3y", "cagr_5y", "days_since_recorded_high",
    "annualized_volatility_1y", "max_drawdown_3y", "roce",
    "debt_to_equity", "profit_growth_yoy",
)
FORBIDDEN = ("future_return", "label", "rank_ic", "realized_return", "outcome")


def _rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def cohort_summary(
    signal_rows: list[dict[str, str]], matched: dict[str, dict[str, str]]
) -> tuple[dict[str, list[dict[str, object]]], int]:
    sectors: dict[str, list[dict[str, object]]] = {}
    for signal in signal_rows:
        sectors.setdefault(signal["historical_sector"], []).append({
            "ticker": signal["ticker"], "research_v2_rank": int(signal["sector_rank"]),
            "matched_baseline_rank": int(matched[signal["ticker"]]["matched_baseline_sector_rank"]),
            "original_baseline_rank": int(matched[signal["ticker"]]["original_baseline_sector_rank"]),
        })
    result = {
        sector: sorted(rows, key=lambda row: (row["research_v2_rank"], row["ticker"]))
        for sector, rows in sorted(sectors.items())
    }
    return result, sum(len(rows) >= 3 for rows in result.values())


def audit(mapping_path: Path, cache_root: Path, bundle: Path) -> dict[str, object]:
    mapping = json.loads(mapping_path.read_text(encoding="utf-8"))
    snapshots = {row["ranking_date"]: row for row in mapping["snapshots"]}
    integrity_rows = []
    cohort = {}
    possible = {}
    for ranking_date in ("2022-08-05", "2023-08-07", "2024-08-07", "2025-08-07"):
        accepted = snapshots[ranking_date]["accepted"]
        signal_rows = _rows(bundle / ranking_date / "research_v2.csv")
        signal_by_ticker = {row["ticker"]: row for row in signal_rows}
        if set(signal_by_ticker) != {row["ticker"] for row in accepted}:
            raise ValueError(f"mapping/eligible cohort mismatch: {ranking_date}")
        for signal in signal_rows:
            if any(any(token in column.lower() for token in FORBIDDEN) for column in signal):
                raise ValueError(f"forbidden outcome column: {ranking_date}")
            if not all(math.isfinite(float(signal[name])) for name in METRICS):
                raise ValueError(f"non-finite metric: {ranking_date}/{signal['ticker']}")
        matched = {row["ticker"]: row for row in _rows(bundle / ranking_date / "matched_baseline.csv")}
        cohort[ranking_date], possible[ranking_date] = cohort_summary(signal_rows, matched)

        if ranking_date[:4] not in {"2024", "2025"}:
            continue
        provenance = json.loads((cache_root / ranking_date / "annual_reports/annual_report_provenance.json").read_text(encoding="utf-8"))
        by_ticker = {row["ticker"]: row for row in provenance}
        cutoff = datetime.fromisoformat(ranking_date + "T15:30:00")
        for item in accepted:
            source = by_ticker[item["ticker"]]
            pdf = cache_root / ranking_date / "annual_reports" / source["pdf_path"]
            if sha256(pdf.read_bytes()).hexdigest() != item["pdf_sha256"]:
                raise ValueError(f"PDF hash mismatch: {ranking_date}/{item['ticker']}")
            disseminated = datetime.strptime(item["dissemination_timestamp"], "%d-%b-%Y %H:%M:%S")
            if disseminated > cutoff:
                raise ValueError(f"post-cutoff filing: {ranking_date}/{item['ticker']}")
            profit = item["profit"]
            if profit["current_period_months"] != 12 or profit["prior_period_months"] != 12:
                raise ValueError(f"noncomparable accepted periods: {ranking_date}/{item['ticker']}")
            signal = signal_by_ticker[item["ticker"]]
            if not math.isclose(float(signal["roce"]), item["roce"]["canonical_decimal"], abs_tol=1e-15):
                raise ValueError(f"ROCE unit mismatch: {ranking_date}/{item['ticker']}")
            if not math.isclose(float(signal["debt_to_equity"]), item["debt_to_equity"]["canonical_decimal"], abs_tol=1e-15):
                raise ValueError(f"debt-equity unit mismatch: {ranking_date}/{item['ticker']}")
            integrity_rows.append({
                "ranking_date": ranking_date, "ticker": item["ticker"],
                "required_fiscal_year": item["financial_year"], "pdf_sha256": item["pdf_sha256"],
                "dissemination_timestamp": item["dissemination_timestamp"],
                "reporting_basis": item["reporting_basis"], "roce": item["roce"]["canonical_decimal"],
                "debt_to_equity": item["debt_to_equity"]["canonical_decimal"],
                "profit_unit": profit["unit"], "current_period_start": profit["current_period_start"],
                "current_period_end": profit["current_period_end"], "current_period_months": 12,
                "prior_period_start": profit["prior_period_start"], "prior_period_end": profit["prior_period_end"],
                "prior_period_months": 12, "comparison_status": profit["comparison_status"],
                "all_nine_metrics_finite": True, "cutoff_check": "PASS", "unit_check": "PASS",
            })
    return {
        "schema_version": 1, "integrity_status": "PASS", "integrity_rows": integrity_rows,
        "cohorts": cohort, "possible_primary_sector_date_observations": possible,
        "possible_primary_total": sum(possible.values()), "outcome_data_used": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit outcome-blind walk-forward integrity.")
    parser.add_argument("--mapping", type=Path, required=True)
    parser.add_argument("--cache-root", type=Path, required=True)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        result = audit(args.mapping, args.cache_root, args.bundle)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        print(json.dumps({"status": result["integrity_status"], "rows": len(result["integrity_rows"]), "possible_primary_total": result["possible_primary_total"]}, sort_keys=True))
        return 0
    except Exception as exc:
        print(f"blind integrity audit failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
