"""Deterministic ingestion of manually exported Screener company workbooks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Final
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZipFile

import pandas as pd

from .screener_historical_fundamentals import (
    SCREENER_HISTORICAL_CONTRACT_VERSION,
    build_screener_pit_cohorts,
    inspect_screener_historical_workbook,
    parse_screener_historical_workbook,
    sha256_file,
)


BATCH_SCHEMA_VERSION: Final = "screener_manual_workbook_batch_v1"
_ISIN = re.compile(r"^INE[A-Z0-9]{9}$")
_TICKER = re.compile(r"^[A-Z0-9&-]+$")
_MAX_FILE_BYTES = 10 * 1024 * 1024
_MAX_TOTAL_BYTES = 250 * 1024 * 1024


@dataclass(frozen=True, slots=True)
class ScreenerManualBatchResult:
    file_audit: pd.DataFrame
    normalized: pd.DataFrame
    accepted: pd.DataFrame
    rejected_periods: pd.DataFrame
    cohort_summary: pd.DataFrame
    manifest_records: tuple[dict[str, object], ...]


def _export_key(value: object) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value).upper())


def _legal_name_key(value: object) -> str:
    text = str(value).upper().replace("&", " AND ")
    tokens = re.findall(r"[A-Z0-9]+", text)
    aliases = {
        "LIMITED": "LTD", "COMPANY": "CO", "CORPORATION": "CORP",
        "CORPN": "CORP",
        "INDUSTRIES": "INDS", "TECHNOLOGIES": "TECH",
        "LIFESCIENCES": "LIFESCI", "LOGISTICS": "LOGIS",
    }
    normalized = [aliases.get(token, token) for token in tokens if token != "THE"]
    return "".join(normalized)


def _validate_zip_members(archive: ZipFile, expected_count: int) -> list[object]:
    files = [item for item in archive.infolist() if not item.is_dir()]
    if len(files) != expected_count:
        raise ValueError(f"batch archive must contain exactly {expected_count} files; found {len(files)}")
    names: set[str] = set()
    total = 0
    for item in files:
        path = PurePosixPath(item.filename)
        if path.is_absolute() or ".." in path.parts or len(path.parts) > 2:
            raise ValueError(f"unsafe batch archive path: {item.filename!r}")
        if path.suffix.lower() != ".xlsx":
            raise ValueError(f"unexpected batch file type: {item.filename!r}")
        if item.flag_bits & 1:
            raise ValueError(f"encrypted workbook is not accepted: {item.filename!r}")
        key = path.name.casefold()
        if key in names:
            raise ValueError(f"duplicate workbook filename: {path.name!r}")
        names.add(key)
        if item.file_size <= 0 or item.file_size > _MAX_FILE_BYTES:
            raise ValueError(f"unsafe workbook size: {item.filename!r}")
        if item.compress_size and item.file_size / item.compress_size > 100:
            raise ValueError(f"unsafe workbook compression ratio: {item.filename!r}")
        total += item.file_size
    if total > _MAX_TOTAL_BYTES:
        raise ValueError("batch archive uncompressed size exceeds safety limit")
    return sorted(files, key=lambda item: PurePosixPath(item.filename).name.casefold())


def _validate_xlsx_parts(path: Path) -> None:
    try:
        with ZipFile(path) as workbook:
            names = [name.lower() for name in workbook.namelist()]
    except (BadZipFile, OSError) as exc:
        raise ValueError(f"malformed xlsx workbook: {path.name}") from exc
    forbidden = [
        name for name in names
        if "vbaproject" in name or "externallinks/" in name or name.endswith("connections.xml")
    ]
    if forbidden:
        raise ValueError(f"workbook contains forbidden active/external parts: {path.name}")


def ingest_screener_manual_batch(
    *,
    archive_path: str | Path,
    checklist: pd.DataFrame,
    identity_master: pd.DataFrame,
    acquisition_queue: pd.DataFrame,
    official_clock: pd.DataFrame,
    source_directory: str | Path,
    source_observed_at: str,
    ranking_dates: list[date],
    expected_count: int = 50,
    priority_start: int = 1,
) -> ScreenerManualBatchResult:
    """Validate, cache, parse, and PIT-select one manually supplied batch."""

    required_checklist = {
        "priority", "ticker", "company_name", "ISIN", "screener_url",
        "historical_dates_helped", "downloaded",
    }
    missing = sorted(required_checklist - set(checklist.columns))
    if missing:
        raise ValueError(f"checklist missing columns: {missing}")
    expected = checklist.copy(deep=True)
    expected["priority"] = pd.to_numeric(expected["priority"], errors="raise").astype(int)
    priority_end = priority_start + expected_count - 1
    expected = expected.loc[
        expected["priority"].between(priority_start, priority_end)
    ].copy()
    if expected["priority"].tolist() != list(range(priority_start, priority_end + 1)):
        raise ValueError("checklist priorities for this batch are not exactly consecutive")
    expected["ticker"] = expected["ticker"].astype(str).str.strip().str.upper()
    expected["ISIN"] = expected["ISIN"].astype(str).str.strip().str.upper()
    if not expected["ticker"].map(lambda value: bool(_TICKER.fullmatch(value))).all():
        raise ValueError("checklist contains invalid ticker")
    if not expected["ISIN"].map(lambda value: bool(_ISIN.fullmatch(value))).all():
        raise ValueError("checklist contains invalid exact ISIN")
    if expected.duplicated("ticker").any() or expected.duplicated("ISIN").any():
        raise ValueError("checklist batch contains duplicate ticker or ISIN")
    for row in expected.itertuples():
        parsed_url = urlsplit(row.screener_url)
        expected_path = f"/company/{row.ticker}/"
        if (
            parsed_url.scheme != "https"
            or parsed_url.netloc.lower() != "www.screener.in"
            or unquote(parsed_url.path).upper() != expected_path.upper()
            or parsed_url.query
        ):
            raise ValueError(
                f"checklist Screener URL is not the exact standalone ticker path: {row.ticker}"
            )
    expected["file_key"] = expected["company_name"].map(_export_key)
    if expected.duplicated("file_key").any():
        raise ValueError("checklist batch contains ambiguous export filenames")

    identities = identity_master.copy(deep=True).rename(
        columns={"ticker": "master_ticker", "isin": "master_isin", "company": "master_company"}
    )
    identities["master_ticker"] = identities["master_ticker"].astype(str).str.strip().str.upper()
    identities["master_isin"] = identities["master_isin"].astype(str).str.strip().str.upper()
    identities = identities[["master_ticker", "master_isin", "master_company"]].drop_duplicates()
    checked = expected.merge(
        identities,
        left_on=["ticker", "ISIN"], right_on=["master_ticker", "master_isin"],
        how="left", validate="one_to_one",
    )
    if checked["master_company"].isna().any():
        missing_ids = checked.loc[checked["master_company"].isna(), "ticker"].tolist()
        raise ValueError(f"checklist identities absent from exact identity master: {missing_ids}")

    queue = acquisition_queue.copy(deep=True)
    queue["ticker"] = queue["ticker"].astype(str).str.strip().str.upper()
    queue["isin"] = queue["isin"].astype(str).str.strip().str.upper()
    queue_pairs = set(zip(queue["ticker"], queue["isin"]))
    if any((row.ticker, row.ISIN) not in queue_pairs for row in expected.itertuples()):
        raise ValueError("checklist identity is absent from the official-clock acquisition queue")

    source_root = Path(source_directory)
    source_root.mkdir(parents=True, exist_ok=False)
    accepted_root = source_root / "accepted"
    quarantine_root = source_root / "quarantine"
    accepted_root.mkdir()
    quarantine_root.mkdir()
    archive_hash = sha256_file(archive_path)
    file_rows: list[dict[str, object]] = []
    normalized_frames: list[pd.DataFrame] = []
    manifests: list[dict[str, object]] = []
    expected_by_key = checked.set_index("file_key")
    if not expected_by_key.index.is_unique:
        raise ValueError("checklist batch contains ambiguous export filenames")
    with ZipFile(archive_path) as archive:
        members = _validate_zip_members(archive, expected_count)
        actual_keys = {_export_key(PurePosixPath(item.filename).stem) for item in members}
        if actual_keys != set(expected_by_key.index):
            missing_files = sorted(set(expected_by_key.index) - actual_keys)
            unexpected = sorted(actual_keys - set(expected_by_key.index))
            raise ValueError(f"batch/checklist filename mismatch; missing={missing_files}, unexpected={unexpected}")
        for item in members:
            file_name = PurePosixPath(item.filename).name
            key = _export_key(PurePosixPath(file_name).stem)
            target = expected_by_key.loc[key]
            payload = archive.read(item)
            payload_hash = hashlib.sha256(payload).hexdigest()
            cached = source_root / f".{target['ISIN']}__{payload_hash}.pending"
            cached.write_bytes(payload)
            try:
                _validate_xlsx_parts(cached)
                inspection = inspect_screener_historical_workbook(cached)
                legal_name_match = (
                    _legal_name_key(inspection.company)
                    == _legal_name_key(target["master_company"])
                )
                reference_key = str(target.name)
                exact_reference_prefix = (
                    len(reference_key) >= 5
                    and _export_key(inspection.company).startswith(reference_key)
                )
                if not legal_name_match and not exact_reference_prefix:
                    raise ValueError(
                        f"workbook company does not exactly normalize to identity master: "
                        f"{inspection.company!r} != {target['master_company']!r}"
                    )
                identity_method = (
                    "LEGAL_NAME_EXACT_NORMALIZATION"
                    if legal_name_match
                    else "EXACT_SCREENER_REFERENCE_PREFIX_WITH_EXACT_TICKER_ISIN"
                )
                record = {
                    "filename": file_name,
                    "cached_filename": cached.name,
                    "priority": int(target["priority"]),
                    "ticker": target["ticker"],
                    "isin": target["ISIN"],
                    "company": target["master_company"],
                    "workbook_company": inspection.company,
                    "workbook_sha256": payload_hash,
                    "reporting_basis": "STANDALONE",
                    "source_observed_at": source_observed_at,
                    "basis_attestation": (
                        "USER_SUPPLIED_FROM_EXACT_STANDALONE_CHECKLIST_URL; "
                        "filename matched exact checklist row; ISIN/ticker matched identity master "
                        "and official-clock acquisition queue"
                    ),
                    "screener_url": target["screener_url"],
                    "archive_sha256": archive_hash,
                    "contract_version": SCREENER_HISTORICAL_CONTRACT_VERSION,
                    "identity_validation_method": identity_method,
                }
                parsed = parse_screener_historical_workbook(cached, record)
                accepted_path = accepted_root / f"{target['ISIN']}__{payload_hash}.xlsx"
                cached.replace(accepted_path)
                record["cached_filename"] = accepted_path.relative_to(source_root).as_posix()
                normalized_frames.append(parsed)
                manifests.append(record)
                file_rows.append({
                    "priority": int(target["priority"]), "ticker": target["ticker"],
                    "isin": target["ISIN"], "input_filename": file_name,
                    "workbook_company": inspection.company,
                    "identity_master_company": target["master_company"],
                    "workbook_sha256": payload_hash, "workbook_version": inspection.version,
                    "reporting_basis": "STANDALONE", "annual_period_count": len(parsed),
                    "identity_validation_method": identity_method,
                    "file_status": "ACCEPTED", "reason": "",
                })
            except Exception as exc:  # retained as explicit quarantine evidence
                quarantined = quarantine_root / f"{target['ISIN']}__{payload_hash}.xlsx"
                if cached.exists():
                    cached.replace(quarantined)
                file_rows.append({
                    "priority": int(target["priority"]), "ticker": target["ticker"],
                    "isin": target["ISIN"], "input_filename": file_name,
                    "workbook_company": "", "identity_master_company": target["master_company"],
                    "workbook_sha256": payload_hash, "workbook_version": "",
                    "reporting_basis": "UNVERIFIED", "annual_period_count": 0,
                    "identity_validation_method": "FAILED",
                    "file_status": "QUARANTINED", "reason": str(exc),
                })

    file_audit = pd.DataFrame(file_rows).sort_values("priority", kind="stable").reset_index(drop=True)
    normalized = (
        pd.concat(normalized_frames, ignore_index=True).sort_values(
            ["isin", "period_end"], kind="stable"
        ).reset_index(drop=True)
        if normalized_frames else pd.DataFrame()
    )
    if normalized.empty:
        empty = pd.DataFrame()
        return ScreenerManualBatchResult(file_audit, empty, empty, empty, empty, tuple())
    result = build_screener_pit_cohorts(normalized, official_clock, ranking_dates)
    return ScreenerManualBatchResult(
        file_audit=file_audit,
        normalized=result.normalized,
        accepted=result.accepted,
        rejected_periods=result.rejected,
        cohort_summary=result.cohort_summary,
        manifest_records=tuple(sorted(manifests, key=lambda row: int(row["priority"]))),
    )
