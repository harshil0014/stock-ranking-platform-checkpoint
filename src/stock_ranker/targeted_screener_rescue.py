"""Deterministic preparation of targeted Screener workbook and official-clock inputs."""

from __future__ import annotations

from datetime import datetime
import hashlib
import json
from pathlib import Path, PurePosixPath
import tempfile
from urllib.parse import urlparse
from zipfile import ZipFile

import pandas as pd

from .screener_historical_fundamentals import inspect_screener_historical_workbook
from .screener_manual_batch import _export_key, _legal_name_key, _validate_zip_members


OFFICIAL_HOSTS = {"www.nseindia.com", "nsearchives.nseindia.com", "archives.nseindia.com"}


def targeted_checklist(targets: pd.DataFrame, archive_path: str | Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Map every workbook to one exact target legal identity and build the batch checklist."""

    required = {"ticker", "company", "isin", "screener_url", "historical_dates_helped"}
    missing = sorted(required - set(targets.columns))
    if missing:
        raise ValueError(f"target list missing columns: {missing}")
    target = targets.copy(deep=True)
    target["legal_key"] = target["company"].map(_legal_name_key)
    if target["legal_key"].duplicated().any():
        raise ValueError("target legal identities are ambiguous")
    by_legal = target.set_index("legal_key")
    checklist_rows: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    with ZipFile(archive_path) as archive:
        for member in _validate_zip_members(archive, len(target)):
            payload = archive.read(member)
            handle = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
            temporary = Path(handle.name)
            handle.write(payload)
            handle.close()
            try:
                inspection = inspect_screener_historical_workbook(temporary)
            finally:
                temporary.unlink(missing_ok=True)
            key = _legal_name_key(inspection.company)
            if key not in by_legal.index:
                raise ValueError(f"workbook company is not an exact target identity: {inspection.company!r}")
            row = by_legal.loc[key]
            filename = PurePosixPath(member.filename).name
            checklist_rows.append({
                "priority": len(checklist_rows) + 1,
                "ticker": row["ticker"],
                "company_name": PurePosixPath(filename).stem,
                "ISIN": row["isin"],
                "screener_url": row["screener_url"],
                "historical_dates_helped": row["historical_dates_helped"],
                "downloaded": "yes",
            })
            audit_rows.append({
                "ticker": row["ticker"], "isin": row["isin"],
                "input_filename": filename, "workbook_company": inspection.company,
                "workbook_version": inspection.version, "identity_status": "EXACT_LEGAL_NAME_MATCH",
            })
    checklist = pd.DataFrame(checklist_rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    checklist["priority"] = range(1, len(checklist) + 1)
    audit = pd.DataFrame(audit_rows).sort_values("ticker", kind="stable").reset_index(drop=True)
    if set(checklist["ticker"]) != set(target["ticker"]):
        raise ValueError("workbook package does not map one-to-one to all targeted tickers")
    return checklist, audit


def _clock_row(
    *, ticker: str, isin: str, financial_year: str, timestamp: str,
    source_url: str, status: str, evidence_path: str,
) -> dict[str, object]:
    parsed = urlparse(source_url)
    if parsed.scheme != "https" or parsed.hostname not in OFFICIAL_HOSTS:
        raise ValueError(f"clock evidence is not an official NSE URL: {source_url}")
    available = pd.to_datetime(timestamp, format="mixed", errors="raise")
    if available.tzinfo is None:
        available = available.tz_localize("Asia/Kolkata")
    return {
        "ticker": ticker, "isin": isin, "financial_year": financial_year,
        "ranking_date": "", "pit_available": True,
        "availability_status": status,
        "dissemination_timestamp": available.isoformat(), "source_url": source_url,
        "evidence_path": evidence_path,
    }


def merge_official_clock_evidence(
    targets: pd.DataFrame, base_availability: pd.DataFrame,
    annual_metadata_root: str | Path, rescue_root: str | Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge only explicit official NSE dissemination clocks; never infer from filenames."""

    identity = targets.set_index("ticker")["isin"].to_dict()
    rows = base_availability.to_dict("records")
    evidence: list[dict[str, object]] = []
    metadata_root = Path(annual_metadata_root)
    for ticker, isin in sorted(identity.items()):
        path = metadata_root / f"{ticker}.json"
        if not path.is_file():
            continue
        payload = json.loads(path.read_text(encoding="utf-8"))
        for item in payload.get("data", []):
            timestamp = str(item.get("disseminationDateTime", "")).strip()
            url = str(item.get("fileName", "")).strip()
            if not timestamp or timestamp == "-" or not url:
                continue
            financial_year = f"{item.get('fromYr')}-{item.get('toYr')}"
            row = _clock_row(
                ticker=ticker, isin=isin, financial_year=financial_year,
                timestamp=timestamp, source_url=url,
                status="EXPLICIT_NSE_ANNUAL_REPORT_TIMESTAMP",
                evidence_path=path.as_posix(),
            )
            rows.append(row); evidence.append(row)
    rescue = Path(rescue_root)
    for path in sorted(rescue.glob("*/availability_rescue_provenance.json")):
        for item in json.loads(path.read_text(encoding="utf-8")):
            ticker = str(item.get("ticker", ""))
            if ticker not in identity:
                continue
            detail = item.get("availability_rescue") or {}
            if detail.get("evidence_status") != "RESCUED_EXACT_NSE_DISSEMINATION":
                continue
            required = str(item["required_fiscal_year"])
            start, end = required.split("-")
            financial_year = f"{start}-{start[:2]}{end}"
            row = _clock_row(
                ticker=ticker, isin=identity[ticker], financial_year=financial_year,
                timestamp=str(detail["exchange_dissemination_timestamp"]),
                source_url=str(detail["attachment_url"]),
                status="RESCUED_EXACT_NSE_ANNOUNCEMENT_TIMESTAMP",
                evidence_path=path.as_posix(),
            )
            rows.append(row); evidence.append(row)
    combined = pd.DataFrame(rows)
    combined["_clock"] = pd.to_datetime(
        combined["dissemination_timestamp"], format="mixed", errors="coerce", utc=True
    )
    combined = combined.sort_values(
        ["isin", "financial_year", "_clock", "source_url"], kind="stable", na_position="last"
    ).drop(columns="_clock")
    combined = combined.drop_duplicates(
        ["isin", "financial_year", "dissemination_timestamp", "source_url"], keep="first"
    ).reset_index(drop=True)
    audit = pd.DataFrame(evidence).sort_values(
        ["ticker", "financial_year", "dissemination_timestamp"], kind="stable"
    ).reset_index(drop=True)
    return combined, audit
