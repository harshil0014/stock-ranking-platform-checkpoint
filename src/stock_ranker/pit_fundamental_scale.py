"""Deterministic scale-up boundaries for PIT-safe annual-report fundamentals."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import json
import re
from typing import Any

import pandas as pd


FINANCIAL_SECTORS = {"Financial Services"}
_ISIN = re.compile(r"^INE[A-Z0-9]{9}$")


def build_pit_fundamental_population(company_facts: pd.DataFrame) -> pd.DataFrame:
    """Return every exact-identity NSE Baseline-ready strict-V2 gap."""

    required = {
        "ticker", "company", "isin", "primary_exchange", "product_sector",
        "product_baseline_eligible", "v2_eligible",
    }
    missing = sorted(required.difference(company_facts.columns))
    if missing:
        raise ValueError(f"company facts missing columns: {', '.join(missing)}")
    source = company_facts.copy(deep=True)
    population = source.loc[
        source["primary_exchange"].eq("NSE")
        & source["product_baseline_eligible"].eq(True)
        & source["v2_eligible"].ne(True)
        & source["isin"].astype(str).map(lambda value: bool(_ISIN.fullmatch(value))),
        ["ticker", "company", "isin", "product_sector"],
    ].rename(columns={"product_sector": "sector"})
    if population[["ticker", "isin"]].duplicated().any(axis=None):
        raise ValueError("PIT fundamental population has duplicate ticker or ISIN")
    population["selection_key"] = population["isin"].map(
        lambda value: sha256(str(value).encode("ascii")).hexdigest()
    )
    population["conventional_roce_applicability"] = population["sector"].map(
        lambda value: "REVIEW_FINANCIAL_ENTITY" if value in FINANCIAL_SECTORS else "STANDARD_PROBE"
    )
    return population.sort_values(["selection_key", "isin"], kind="mergesort").reset_index(drop=True)


def summarize_annual_report_metadata(
    population: pd.DataFrame, provenance_path: str | Path,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    payload = json.loads(Path(provenance_path).read_text(encoding="utf-8"))
    by_ticker = {str(item["ticker"]): item for item in payload}
    if len(by_ticker) != len(payload):
        raise ValueError("annual-report metadata provenance has duplicate tickers")
    rows: list[dict[str, Any]] = []
    for item in population.to_dict("records"):
        source = by_ticker.get(str(item["ticker"]), {})
        selected = source.get("selected_metadata") or {}
        rows.append({
            **item,
            "metadata_status": source.get("metadata_status", "MISSING"),
            "selection_status": source.get("selection_status", "MISSING"),
            "dissemination_timestamp": selected.get("disseminationDateTime"),
            "source_url": source.get("source_url"),
            "pdf_filename": source.get("pdf_filename"),
            "metadata_sha256": source.get("metadata_sha256"),
        })
    result = pd.DataFrame(rows)
    selected = result["selection_status"].eq("SELECTED")
    standard = result["conventional_roce_applicability"].eq("STANDARD_PROBE")
    summary = {
        "population_count": len(result),
        "sector_count": int(result["sector"].nunique()),
        "metadata_fetched_count": int(result["metadata_status"].eq("FETCHED").sum()),
        "report_available_count": int(selected.sum()),
        "report_available_rate": float(selected.mean()),
        "standard_probe_count": int(standard.sum()),
        "standard_probe_report_available_count": int((selected & standard).sum()),
        "financial_entity_review_count": int((~standard).sum()),
        "financial_entity_report_available_count": int((selected & ~standard).sum()),
        "selection_status_counts": {
            str(key): int(value)
            for key, value in result["selection_status"].value_counts().sort_index().items()
        },
    }
    return result, summary


def select_report_download_batch(metadata: pd.DataFrame, batch_size: int = 250) -> pd.DataFrame:
    """Choose a deterministic, sector-diverse non-financial report batch."""

    if batch_size <= 0:
        raise ValueError("batch_size must be positive")
    required = {
        "ticker", "company", "isin", "sector", "selection_key", "selection_status",
        "conventional_roce_applicability", "source_url",
    }
    missing = sorted(required.difference(metadata.columns))
    if missing:
        raise ValueError(f"metadata matrix missing columns: {', '.join(missing)}")
    candidates = metadata.loc[
        metadata["selection_status"].eq("SELECTED")
        & metadata["conventional_roce_applicability"].eq("STANDARD_PROBE")
        & metadata["source_url"].notna(),
    ].copy()
    candidates = candidates.sort_values(["sector", "selection_key", "isin"], kind="mergesort")
    candidates["sector_order"] = candidates.groupby("sector", sort=False).cumcount()
    selected = candidates.sort_values(
        ["sector_order", "selection_key", "isin"], kind="mergesort"
    ).head(batch_size)
    return selected.drop(columns=["sector_order"]).reset_index(drop=True)


def audit_historical_report_availability(
    population: pd.DataFrame,
    metadata_directory: str | Path,
    ranking_dates: dict[str, str],
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Audit historical report availability using explicit NSE timestamps only.

    Archive filenames can contain date-like text, but that is not treated as an
    availability timestamp.  This deliberately understates coverage when the
    exchange API omits dissemination metadata.
    """

    required = {"ticker", "isin", "sector", "conventional_roce_applicability"}
    missing = sorted(required.difference(population.columns))
    if missing:
        raise ValueError(f"population missing columns: {', '.join(missing)}")
    if not ranking_dates:
        raise ValueError("ranking_dates must not be empty")
    targets: dict[str, pd.Timestamp] = {}
    for financial_year, ranking_date in ranking_dates.items():
        if not re.fullmatch(r"\d{4}-\d{4}", str(financial_year)):
            raise ValueError(f"invalid financial year: {financial_year}")
        parsed = pd.to_datetime(ranking_date, format="%Y-%m-%d", errors="raise")
        targets[str(financial_year)] = parsed

    metadata_root = Path(metadata_directory)
    rows: list[dict[str, Any]] = []
    for identity in population.sort_values("ticker", kind="mergesort").to_dict("records"):
        metadata_path = metadata_root / f"{identity['ticker']}.json"
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
        reports = payload.get("data")
        if not isinstance(reports, list):
            raise ValueError(f"{identity['ticker']} annual-report metadata is not a list")
        for financial_year, cutoff in targets.items():
            from_year, to_year = financial_year.split("-")
            matching = [
                report for report in reports
                if str(report.get("fromYr")) == from_year
                and str(report.get("toYr")) == to_year
            ]
            explicitly_timed: list[tuple[pd.Timestamp, dict[str, Any]]] = []
            malformed_timestamp_count = 0
            for report in matching:
                raw = str(report.get("disseminationDateTime", "")).strip()
                timestamp = pd.to_datetime(raw, format="%d-%b-%Y %H:%M:%S", errors="coerce")
                if pd.isna(timestamp):
                    malformed_timestamp_count += 1
                elif timestamp <= cutoff + pd.Timedelta(hours=23, minutes=59, seconds=59):
                    explicitly_timed.append((timestamp, report))
            selected = max(explicitly_timed, key=lambda pair: pair[0]) if explicitly_timed else None
            rows.append({
                "ticker": identity["ticker"], "isin": identity["isin"],
                "sector": identity["sector"],
                "conventional_roce_applicability": identity["conventional_roce_applicability"],
                "financial_year": financial_year, "ranking_date": cutoff.strftime("%Y-%m-%d"),
                "matching_report_count": len(matching),
                "missing_explicit_timestamp_count": malformed_timestamp_count,
                "pit_available": selected is not None,
                "availability_status": (
                    "EXPLICIT_NSE_TIMESTAMP_AVAILABLE" if selected is not None
                    else "REPORT_PRESENT_TIMESTAMP_UNRESOLVED" if matching
                    else "NO_REPORT_IN_NSE_METADATA"
                ),
                "dissemination_timestamp": (
                    selected[0].strftime("%Y-%m-%dT%H:%M:%S+05:30") if selected else None
                ),
                "source_url": selected[1].get("fileName") if selected else None,
            })
    result = pd.DataFrame(rows).sort_values(
        ["ranking_date", "ticker"], kind="mergesort"
    ).reset_index(drop=True)
    by_date: dict[str, Any] = {}
    for ranking_date, group in result.groupby("ranking_date", sort=True):
        available = group["pit_available"].eq(True)
        standard = group["conventional_roce_applicability"].eq("STANDARD_PROBE")
        by_date[str(ranking_date)] = {
            "population_count": len(group),
            "explicitly_timed_report_count": int(available.sum()),
            "standard_probe_explicitly_timed_report_count": int((available & standard).sum()),
            "timestamp_unresolved_report_count": int(
                group["availability_status"].eq("REPORT_PRESENT_TIMESTAMP_UNRESOLVED").sum()
            ),
        }
    summary = {
        "schema_version": "pit_historical_report_availability_v1",
        "strict_availability_rule": "Explicit NSE disseminationDateTime on or before ranking date; filenames are never timestamps.",
        "by_ranking_date": by_date,
    }
    summary["availability_fingerprint"] = sha256(
        result.to_csv(index=False, lineterminator="\n").encode("utf-8")
    ).hexdigest()
    return result, summary
