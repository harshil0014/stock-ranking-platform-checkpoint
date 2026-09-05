"""Compare Screener history acquisition routes without making network requests."""

from __future__ import annotations

import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import sys

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from stock_ranker.screener_historical_fundamentals import (  # noqa: E402
    build_screener_pit_cohorts,
    official_clock_from_availability,
    parse_screener_historical_workbook,
    sha256_file,
)
from stock_ranker.screener_public_history import parse_cached_public_pages  # noqa: E402
from stock_ranker.screener_xbrl_reconstruction import (  # noqa: E402
    XBRL_REQUIRED_CONCEPTS,
    audit_xbrl_component_alignment,
    reconstruct_screener_methodology_from_xbrl,
)


RANKING_DATES = [
    date(2022, 8, 5), date(2023, 8, 7), date(2024, 8, 7),
    date(2025, 8, 7), date(2026, 8, 21),
]


def _write_csv(path: Path, frame: pd.DataFrame) -> None:
    frame.to_csv(
        path, index=False, encoding="utf-8", lineterminator="\n", float_format="%.17g"
    )


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, sort_keys=True, indent=2, allow_nan=False) + "\n",
        encoding="utf-8", newline="\n",
    )


def _fingerprint(frame: pd.DataFrame) -> str:
    payload = frame.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _exact_identities(availability: pd.DataFrame, bulk_paths: list[Path]) -> pd.DataFrame:
    truth = availability["pit_available"].map(
        lambda value: value is True or str(value).strip().lower() == "true"
    )
    target = availability.loc[
        truth & availability["conventional_roce_applicability"].eq("STANDARD_PROBE"),
        ["ticker", "isin"],
    ].drop_duplicates()
    target["ticker"] = target["ticker"].astype(str).str.strip().str.upper()
    target["isin"] = target["isin"].astype(str).str.strip().str.upper()
    references = []
    for path in bulk_paths:
        raw = pd.read_csv(path)
        item = raw[["Name", "NSE Code", "ISIN Code"]].rename(
            columns={"Name": "company", "NSE Code": "ticker", "ISIN Code": "isin"}
        ).dropna()
        item["ticker"] = item["ticker"].astype(str).str.strip().str.upper()
        item["isin"] = item["isin"].astype(str).str.strip().str.upper()
        references.append(item)
    reference = pd.concat(references, ignore_index=True)
    conflicts = reference.groupby("isin").agg(tickers=("ticker", "nunique"))
    if (conflicts["tickers"] > 1).any():
        raise ValueError("Screener bulk exports contain conflicting exact ISIN identities")
    reference = reference.sort_values(["isin", "ticker"], kind="stable").drop_duplicates("isin", keep="last")
    result = target.merge(reference, on=["ticker", "isin"], how="left", validate="one_to_one")
    if result["company"].isna().any():
        raise ValueError("official-clock target missing exact Screener bulk identity")
    return result.sort_values("ticker", kind="stable").reset_index(drop=True)


def _load_relevant_facts(path: Path, isins: set[str]) -> pd.DataFrame:
    columns = [
        "ticker", "isin", "statement_basis", "period_type", "period_end",
        "available_at", "filing_id", "canonical_concept", "value", "unit",
        "source_url", "source_sha256",
    ]
    frames = []
    for chunk in pd.read_csv(path, usecols=columns, chunksize=250_000):
        selected = chunk.loc[
            chunk["isin"].isin(isins)
            & chunk["statement_basis"].eq("STANDALONE")
            & chunk["canonical_concept"].isin(XBRL_REQUIRED_CONCEPTS)
        ]
        if len(selected):
            frames.append(selected)
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(columns=columns)


def _cached_manifest(cache_dir: Path, identities: pd.DataFrame) -> pd.DataFrame:
    exact = identities.set_index("ticker").to_dict("index")
    records = []
    for metadata_path in sorted((cache_dir / "pages").glob("*.json"), key=lambda path: path.name):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        ticker = str(metadata.get("ticker", "")).upper()
        if ticker not in exact or metadata.get("isin") != exact[ticker]["isin"]:
            continue
        page = metadata_path.with_suffix(".html")
        if not page.is_file() or sha256_file(page) != metadata.get("sha256"):
            raise ValueError(f"cached Screener page evidence mismatch: {ticker}")
        records.append({
            **exact[ticker], **metadata, "path": str(page), "cache_status": "CACHE_HIT",
        })
    return pd.DataFrame(records)


def _cohort_map(frame: pd.DataFrame) -> dict[str, int]:
    return {
        str(row["ranking_date"]): int(row["pit_fundamental_count"])
        for row in frame.to_dict("records")
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--availability-csv", type=Path, required=True)
    parser.add_argument("--bulk-csv", action="append", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--workbook-dir", type=Path, required=True)
    parser.add_argument("--public-cache-dir", type=Path, required=True)
    parser.add_argument("--official-facts-csv", type=Path, required=True)
    parser.add_argument("--frozen-walk-forward-root", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=False)

    availability = pd.read_csv(args.availability_csv)
    identities = _exact_identities(availability, args.bulk_csv)
    manifest = json.loads(args.manifest.read_text(encoding="utf-8"))
    workbook = pd.concat([
        parse_screener_historical_workbook(args.workbook_dir / record["filename"], record)
        for record in manifest["records"]
    ], ignore_index=True)
    clock = official_clock_from_availability(availability)
    workbook_result = build_screener_pit_cohorts(workbook, clock, RANKING_DATES)

    cache_manifest = _cached_manifest(args.public_cache_dir, identities)
    public, public_failures = parse_cached_public_pages(cache_manifest)
    combined = pd.concat([
        workbook.assign(_priority=0), public.assign(_priority=1),
    ], ignore_index=True, sort=False)
    combined = (
        combined.sort_values(["isin", "period_end", "_priority"], kind="stable")
        .drop_duplicates(["isin", "period_end"], keep="first")
        .drop(columns="_priority")
    )
    combined_result = build_screener_pit_cohorts(combined, clock, RANKING_DATES)

    facts = _load_relevant_facts(args.official_facts_csv, set(identities["isin"]))
    xbrl = reconstruct_screener_methodology_from_xbrl(facts, target_isins=identities["isin"])
    alignment = audit_xbrl_component_alignment(workbook, facts)

    truth = availability["pit_available"].map(
        lambda value: value is True or str(value).strip().lower() == "true"
    )
    capacity = (
        availability.loc[
            truth & availability["conventional_roce_applicability"].eq("STANDARD_PROBE")
        ].groupby("ranking_date")["isin"].nunique().sort_index()
    )
    capacity_map = {str(index): int(value) for index, value in capacity.items()}
    workbook_cohorts = _cohort_map(workbook_result.cohort_summary)
    combined_cohorts = _cohort_map(combined_result.cohort_summary)
    xbrl_matches = {
        name: int(alignment[f"{name}_matches_workbook_precision"].sum())
        for name in ("pbt", "interest", "pat", "equity_capital", "reserves", "borrowings")
    }
    xbrl_calibration_pass = (
        len(alignment) == len(manifest["records"])
        and all(value == len(alignment) for value in xbrl_matches.values())
        and bool(alignment["xbrl_prior_complete"].all())
    )
    route_comparison = pd.DataFrame([
        {
            "route": "SUPPORTED_COMPANY_EXCEL_EXPORT",
            "standalone_basis_explicit": True,
            "historical_depth": "10+ years",
            "current_verified_issuers": int(workbook["isin"].nunique()),
            "maximum_clock_target_issuers": len(identities),
            "manual_company_downloads_required": len(identities) - int(workbook["isin"].nunique()),
            "operational_status": "PRECISE_BUT_MANUAL",
            "selected": False,
        },
        {
            "route": "SLOW_RESUMABLE_PUBLIC_STANDALONE_PAGE",
            "standalone_basis_explicit": True,
            "historical_depth": "10-12 years where published",
            "current_verified_issuers": int(public["isin"].nunique()) if len(public) else 0,
            "maximum_clock_target_issuers": len(identities),
            "manual_company_downloads_required": 0,
            "operational_status": "SELECTED_CACHE_FIRST_BOUNDED_SCHEDULE",
            "selected": True,
        },
        {
            "route": "OFFICIAL_XBRL_SCREENER_FORMULA_TRANSFORM",
            "standalone_basis_explicit": True,
            "historical_depth": "latest annual result snapshot in current backbone",
            "current_verified_issuers": int(xbrl.candidates["isin"].nunique()) if len(xbrl.candidates) else 0,
            "maximum_clock_target_issuers": len(identities),
            "manual_company_downloads_required": 0,
            "operational_status": "CALIBRATION_FAILED_NOT_PROMOTABLE",
            "selected": False,
        },
    ])

    union_rows: list[dict[str, object]] = []
    if args.frozen_walk_forward_root:
        for ranking_date in RANKING_DATES:
            path = args.frozen_walk_forward_root / ranking_date.isoformat() / "research_v2.csv"
            if not path.is_file():
                continue
            frozen = set(pd.read_csv(path)["ticker"].astype(str))
            cached = set(
                combined_result.accepted.loc[
                    combined_result.accepted["ranking_date"].astype(str).eq(ranking_date.isoformat()),
                    "ticker",
                ].astype(str)
            )
            union_rows.append({
                "ranking_date": ranking_date.isoformat(),
                "frozen_cohort_count": len(frozen),
                "cached_screener_cohort_count": len(cached),
                "overlap_count": len(frozen & cached),
                "prospective_union_count": len(frozen | cached),
                "prospective_addition_count": len(cached - frozen),
            })
    cohort_union = pd.DataFrame(union_rows)

    outputs = {
        "route_comparison.csv": route_comparison,
        "workbook_pit_selected.csv": workbook_result.accepted,
        "cached_public_normalized.csv": public,
        "cached_public_failures.csv": public_failures,
        "combined_cached_pit_selected.csv": combined_result.accepted,
        "xbrl_reconstruction_candidates.csv": xbrl.candidates,
        "xbrl_reconstruction_rejections.csv": xbrl.rejected,
        "xbrl_component_calibration.csv": alignment,
        "frozen_to_cached_cohort_union.csv": cohort_union,
    }
    for name, frame in outputs.items():
        _write_csv(args.output_dir / name, frame)
    summary = {
        "schema_version": "screener_acquisition_route_audit_v1",
        "selected_route": "SLOW_RESUMABLE_PUBLIC_STANDALONE_PAGE",
        "selection_reason": (
            "It is the only zero-manual route that exposes explicit standalone historical "
            "Screener line items. Raw pages are immutable cached evidence; bounded scheduled "
            "requests and a failure circuit prevent hammering."
        ),
        "safe_scale_policy": {
            "cache_first": True,
            "default_new_requests_per_run": 5,
            "minimum_delay_seconds": 15,
            "stop_after_consecutive_failures": 1,
            "no_retry_or_evasion": True,
        },
        "exact_identity_target_count": len(identities),
        "official_clock_capacity_by_ranking_date": capacity_map,
        "workbook_count": int(workbook["isin"].nunique()),
        "workbook_cohorts": workbook_cohorts,
        "cached_public_page_count": len(cache_manifest),
        "cached_public_parse_success_count": int(public["isin"].nunique()) if len(public) else 0,
        "cached_public_parse_failure_count": len(public_failures),
        "combined_cached_cohorts": combined_cohorts,
        "frozen_to_cached_cohort_union": cohort_union.to_dict("records"),
        "combined_normalized_fingerprint": _fingerprint(combined),
        "combined_selected_fingerprint": _fingerprint(combined_result.accepted),
        "xbrl_relevant_fact_count": len(facts),
        "xbrl_complete_candidate_count": len(xbrl.candidates),
        "xbrl_calibration_company_count": len(alignment),
        "xbrl_component_matches_at_workbook_precision": xbrl_matches,
        "xbrl_prior_complete_count": int(alignment["xbrl_prior_complete"].sum()),
        "xbrl_calibration_status": "PASS" if xbrl_calibration_pass else "FAIL",
        "xbrl_failure_reason": (
            "The current official backbone does not retain comparable prior annual capital/PAT "
            "facts, and official BorrowingsCurrent + BorrowingsNoncurrent does not reproduce "
            "Screener's normalized Borrowings line on the calibration pack."
        ),
        "large_historical_evaluation_ready": False,
        "readiness_reason": (
            "The selected route is operationally safe but the immutable cache has not yet "
            "accumulated several hundred complete PIT records per preregistered date."
        ),
        "source_hashes": {
            "availability": sha256_file(args.availability_csv),
            "official_facts": sha256_file(args.official_facts_csv),
            "manifest": sha256_file(args.manifest),
            **{f"bulk:{path.name}": sha256_file(path) for path in args.bulk_csv},
        },
    }
    _write_json(args.output_dir / "route_audit_summary.json", summary)
    inventory = [
        {"path": path.name, "sha256": sha256_file(path), "size": path.stat().st_size}
        for path in sorted(args.output_dir.iterdir(), key=lambda item: item.name)
        if path.is_file() and path.name != "artifact_inventory.json"
    ]
    _write_json(args.output_dir / "artifact_inventory.json", inventory)
    print(json.dumps(summary, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
