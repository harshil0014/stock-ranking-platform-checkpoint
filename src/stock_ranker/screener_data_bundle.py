"""Incremental, exact-identity Screener data-bundle ingestion.

The market-wide exports are current secondary observations.  Company workbooks
provide Screener's adopted standalone historical methodology.  Official
exchange dissemination records remain the sole point-in-time clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import re
import shutil
from typing import Final, Iterable, Mapping, Sequence
from urllib.parse import quote
from zipfile import BadZipFile, ZipFile

import pandas as pd

from .screener_historical_fundamentals import (
    REPORTING_BASIS,
    SCREENER_HISTORICAL_CONTRACT_VERSION,
    build_screener_pit_cohorts,
    inspect_screener_historical_workbook,
    parse_screener_historical_workbook,
    sha256_file,
)
from .screener_manual_batch import _export_key, _legal_name_key, _validate_xlsx_parts


SCREENER_BUNDLE_VERSION: Final = "screener_incremental_exact_isin_bundle_v1"
_ISIN = re.compile(r"^INE[A-Z0-9]{9}$")
_MAX_WORKBOOK_BYTES = 10 * 1024 * 1024
_MAX_ARCHIVE_BYTES = 500 * 1024 * 1024
_VALUE_COLUMNS = ("roce", "debt_to_equity", "current_pat", "prior_pat")
_RANKING_DATES = (
    date(2022, 8, 5), date(2023, 8, 7), date(2024, 8, 7),
    date(2025, 8, 7), date(2026, 8, 21),
)


@dataclass(frozen=True, slots=True)
class ScreenerDataBundleResult:
    market_master: pd.DataFrame
    market_conflicts: pd.DataFrame
    workbook_audit: pd.DataFrame
    normalized_history: pd.DataFrame
    history_conflicts: pd.DataFrame
    pit_selected: pd.DataFrame
    pit_rejected: pd.DataFrame
    pit_summary: pd.DataFrame
    coverage_audit: pd.DataFrame
    missing_history: pd.DataFrame
    next_batch: pd.DataFrame
    summary: Mapping[str, object]


@dataclass(frozen=True, slots=True)
class AcceptedScreenerDataBundle:
    root: Path
    market_master: pd.DataFrame
    normalized_history: pd.DataFrame
    workbook_audit: pd.DataFrame
    summary: Mapping[str, object]
    fingerprint: str


def _text(value: object) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _isin(value: object) -> str:
    result = _text(value).upper()
    return result if _ISIN.fullmatch(result) else ""


def _code(value: object) -> str:
    text = _text(value)
    if re.fullmatch(r"\d+(?:\.0+)?", text):
        return text.split(".", 1)[0]
    return text.upper()


def _canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            + "\n").encode("utf-8")


def _frame_fingerprint(frame: pd.DataFrame) -> str:
    canonical = frame.copy(deep=True).fillna("")
    payload = canonical.to_csv(index=False, lineterminator="\n", float_format="%.17g")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _safe_members(archive: ZipFile) -> list[object]:
    members = [member for member in archive.infolist() if not member.is_dir()]
    total = 0
    seen: set[str] = set()
    accepted: list[object] = []
    for member in members:
        path = PurePosixPath(member.filename)
        if path.is_absolute() or ".." in path.parts or len(path.parts) > 8:
            raise ValueError(f"unsafe archive path: {member.filename!r}")
        if path.suffix.lower() != ".xlsx":
            continue
        if member.flag_bits & 1:
            raise ValueError(f"encrypted workbook is not accepted: {member.filename!r}")
        key = path.as_posix().casefold()
        if key in seen:
            raise ValueError(f"duplicate archive member path: {member.filename!r}")
        seen.add(key)
        if member.file_size <= 0 or member.file_size > _MAX_WORKBOOK_BYTES:
            raise ValueError(f"unsafe workbook size: {member.filename!r}")
        if member.compress_size and member.file_size / member.compress_size > 100:
            raise ValueError(f"unsafe workbook compression ratio: {member.filename!r}")
        total += member.file_size
        accepted.append(member)
    if total > _MAX_ARCHIVE_BYTES:
        raise ValueError("archive workbook payload exceeds safety limit")
    return sorted(accepted, key=lambda item: PurePosixPath(item.filename).as_posix().casefold())


def _prepare_vendor_export(frame: pd.DataFrame, source: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    required = {"Name", "BSE Code", "NSE Code", "ISIN Code", "Industry Group", "Industry"}
    missing = sorted(required - set(frame.columns))
    if missing:
        raise ValueError(f"{source} export missing columns: {missing}")
    work = frame.copy(deep=True)
    work["isin"] = work["ISIN Code"].map(_isin)
    invalid = work.loc[work["isin"].eq("")].copy()
    invalid["conflict_type"] = "INVALID_OR_MISSING_ISIN"
    valid = work.loc[work["isin"].ne("")].copy()
    duplicate_isins = set(valid.loc[valid.duplicated("isin", keep=False), "isin"])
    duplicate_rows = valid.loc[valid["isin"].isin(duplicate_isins)].copy()
    if len(duplicate_rows):
        duplicate_rows["conflict_type"] = "DUPLICATE_ISIN_WITHIN_EXPORT"
    valid = valid.loc[~valid["isin"].isin(duplicate_isins)].copy()
    renamed = {column: f"{source}__{column}" for column in valid.columns if column != "isin"}
    valid = valid.rename(columns=renamed).sort_values("isin", kind="stable").reset_index(drop=True)
    conflicts = pd.concat([invalid, duplicate_rows], ignore_index=True, sort=False)
    if len(conflicts):
        conflicts.insert(0, "source_export", source)
    return valid, conflicts


def merge_screener_market_exports(
    universe: pd.DataFrame,
    operational: pd.DataFrame,
    snapshot: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge market-wide exports only through an exact cleaned-universe ISIN."""

    required = {"ticker", "company", "isin", "primary_exchange", "exchange_security_id"}
    missing = sorted(required - set(universe.columns))
    if missing:
        raise ValueError(f"clean universe missing columns: {missing}")
    clean = universe.copy(deep=True)
    clean["isin"] = clean["isin"].map(_isin)
    if clean["isin"].eq("").any() or clean.duplicated("isin").any():
        raise ValueError("clean universe must contain unique valid exact ISINs")
    op, op_conflicts = _prepare_vendor_export(operational, "operational")
    snap, snap_conflicts = _prepare_vendor_export(snapshot, "snapshot")
    merged = clean.merge(op, on="isin", how="left", validate="one_to_one")
    merged = merged.merge(snap, on="isin", how="left", validate="one_to_one")
    merged["operational_exact_isin_match"] = merged["operational__Name"].notna()
    merged["snapshot_exact_isin_match"] = merged["snapshot__Name"].notna()

    conflict_rows: list[dict[str, object]] = []
    for row in merged.to_dict("records"):
        for field in ("Name", "BSE Code", "NSE Code", "Industry Group", "Industry"):
            left = _text(row.get(f"operational__{field}"))
            right = _text(row.get(f"snapshot__{field}"))
            compare_left = _legal_name_key(left) if field == "Name" else _code(left)
            compare_right = _legal_name_key(right) if field == "Name" else _code(right)
            if left and right and compare_left != compare_right:
                conflict_rows.append({
                    "isin": row["isin"], "ticker": row["ticker"], "field": field,
                    "operational_value": left, "snapshot_value": right,
                    "conflict_type": "CROSS_EXPORT_FIELD_CONFLICT",
                })
    cross = pd.DataFrame(conflict_rows)
    conflict_isins = set(cross["isin"]) if len(cross) else set()
    merged["market_merge_status"] = merged["isin"].map(
        lambda value: "CONFLICT_QUARANTINED" if value in conflict_isins else "ACCEPTED"
    )
    outside: list[pd.DataFrame] = []
    clean_isins = set(clean["isin"])
    for source, prepared in (("operational", op), ("snapshot", snap)):
        rows = prepared.loc[~prepared["isin"].isin(clean_isins)].copy()
        if len(rows):
            rows.insert(0, "source_export", source)
            rows["conflict_type"] = "OUTSIDE_CLEAN_ORDINARY_EQUITY_UNIVERSE"
            outside.append(rows)
    conflicts = pd.concat(
        [item for item in (op_conflicts, snap_conflicts, cross, *outside) if len(item)],
        ignore_index=True, sort=False,
    ) if any(len(item) for item in (op_conflicts, snap_conflicts, cross, *outside)) else pd.DataFrame()
    return (
        merged.sort_values(["primary_exchange", "ticker", "isin"], kind="stable").reset_index(drop=True),
        conflicts.fillna("").sort_values(
            [column for column in ("conflict_type", "source_export", "isin") if column in conflicts],
            kind="stable",
        ).reset_index(drop=True) if len(conflicts) else conflicts,
    )


def _identity_indexes(
    market_master: pd.DataFrame, checklist: pd.DataFrame,
) -> tuple[
    dict[str, set[str]], dict[str, str], dict[str, set[str]],
    dict[str, Mapping[str, object]],
]:
    name_index: dict[str, set[str]] = {}
    code_index: dict[str, set[str]] = {}
    row_index: dict[str, Mapping[str, object]] = {}
    for row in market_master.to_dict("records"):
        isin = row["isin"]
        row_index[isin] = row
        values = [row.get("company"), row.get("operational__Name"), row.get("snapshot__Name")]
        for value in values:
            if _text(value):
                name_index.setdefault(_legal_name_key(value), set()).add(isin)
                name_index.setdefault(_export_key(value), set()).add(isin)
        for value in (
            row.get("ticker"), row.get("exchange_security_id"),
            row.get("operational__NSE Code"), row.get("snapshot__NSE Code"),
            row.get("operational__BSE Code"), row.get("snapshot__BSE Code"),
        ):
            if _code(value):
                code_index.setdefault(_code(value), set()).add(isin)
    checklist_names: dict[str, str] = {}
    if len(checklist):
        for row in checklist.to_dict("records"):
            isin = _isin(row.get("ISIN"))
            if not isin or isin not in row_index:
                continue
            for value in (row.get("company_name"), row.get("ticker")):
                if _text(value):
                    checklist_names[_export_key(value)] = isin
                    checklist_names[_legal_name_key(value)] = isin
    return name_index, checklist_names, code_index, row_index


def _resolve_workbook_identity(
    *, filename: str, workbook_company: str, name_index: Mapping[str, set[str]],
    checklist_names: Mapping[str, str], code_index: Mapping[str, set[str]],
) -> tuple[str, str]:
    stem = PurePosixPath(filename).stem
    keys = {
        _legal_name_key(workbook_company), _export_key(workbook_company),
        _legal_name_key(stem), _export_key(stem),
    }
    candidates: set[str] = set()
    for key in keys:
        candidates.update(name_index.get(key, set()))
    methods: list[str] = []
    if len(candidates) == 1:
        methods.append("EXACT_MASTER_NAME_OR_FILENAME")
    numbered = re.fullmatch(r"\d+_([^_]+)_.+", stem)
    filename_candidates = (
        set(code_index.get(_code(numbered.group(1)), set())) if numbered else set()
    )
    if candidates and filename_candidates:
        candidates &= filename_candidates
    elif not candidates and filename_candidates:
        candidates = filename_candidates
        methods.append("EXACT_NUMBERED_FILENAME_CODE_TO_ISIN")
    checklist_candidates = {checklist_names[key] for key in keys if key in checklist_names}
    if candidates and checklist_candidates:
        candidates &= checklist_candidates
    elif not candidates:
        candidates = checklist_candidates
        if candidates:
            methods.append("EXACT_CHECKLIST_NAME_OR_TICKER")
    if len(candidates) != 1:
        raise ValueError(f"exact identity unresolved; candidates={sorted(candidates)}")
    return next(iter(candidates)), "+".join(methods) or "EXACT_CHECKLIST_INTERSECTION"


def _same_value(left: object, right: object) -> bool:
    if pd.isna(left) and pd.isna(right):
        return True
    try:
        # CSV round trips can move a crore-denominated value by a few binary
        # ulps (for example 8241.819999999998 versus 8241.82).  This tolerance
        # is serialization-only and is far below the workbook's 0.01-crore
        # displayed precision.
        return math.isclose(float(left), float(right), rel_tol=1e-12, abs_tol=1e-9)
    except (TypeError, ValueError):
        return _text(left) == _text(right)


def merge_history_incrementally(
    existing: pd.DataFrame, incoming: pd.DataFrame,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Preserve accepted history and quarantine any disagreeing new observation."""

    old = existing.copy(deep=True)
    new = incoming.copy(deep=True)
    for frame in (old, new):
        for column in ("period_end", "prior_period_end"):
            parsed = pd.to_datetime(frame[column], format="mixed", errors="coerce", utc=True)
            if parsed.isna().any():
                raise ValueError(f"{column}: malformed incremental history date")
            frame[column] = parsed.dt.strftime("%Y-%m-%d")
    key = ["isin", "period_end"]
    conflicts: list[dict[str, object]] = []
    accepted_new: list[pd.Series] = []
    old_by_key = {tuple(row[column] for column in key): row for _, row in old.iterrows()}
    for values, group in new.groupby(key, sort=True, dropna=False):
        variants = []
        for _, row in group.iterrows():
            if not any(all(_same_value(row[col], prior[col]) for col in _VALUE_COLUMNS) for prior in variants):
                variants.append(row)
        existing_row = old_by_key.get(values)
        if existing_row is not None:
            for variant in variants:
                if not all(_same_value(variant[col], existing_row[col]) for col in _VALUE_COLUMNS):
                    conflicts.append({
                        "isin": values[0], "period_end": values[1],
                        "conflict_type": "INCOMING_DISAGREES_WITH_ACCEPTED_HISTORY",
                        "accepted_workbook_sha256": _text(existing_row.get("source_workbook_sha256")),
                        "incoming_workbook_sha256": _text(variant.get("source_workbook_sha256")),
                    })
            continue
        if len(variants) > 1:
            for variant in variants:
                conflicts.append({
                    "isin": values[0], "period_end": values[1],
                    "conflict_type": "CONFLICTING_INCOMING_WORKBOOK_VALUES",
                    "accepted_workbook_sha256": "",
                    "incoming_workbook_sha256": _text(variant.get("source_workbook_sha256")),
                })
            continue
        accepted_new.append(variants[0])
    additions = pd.DataFrame(accepted_new)
    columns = list(dict.fromkeys([*old.columns, *new.columns]))
    combined = pd.concat([old.reindex(columns=columns), additions.reindex(columns=columns)], ignore_index=True)
    combined = combined.sort_values(key, kind="stable").reset_index(drop=True)
    if combined.duplicated(key).any():
        raise ValueError("incremental history contains duplicate ISIN/period keys")
    conflict_frame = pd.DataFrame(conflicts)
    if len(conflict_frame):
        conflict_frame = conflict_frame.sort_values(
            ["isin", "period_end", "incoming_workbook_sha256"], kind="stable"
        ).reset_index(drop=True)
    return combined, conflict_frame


def _historical_help(availability: pd.DataFrame, isin: str) -> list[str]:
    rows = availability.loc[
        availability["isin"].astype(str).str.upper().eq(isin)
        & availability["pit_available"].map(
            lambda value: value is True or str(value).strip().lower() == "true"
        )
    ]
    return sorted(set(rows["ranking_date"].astype(str)))


def build_missing_history_and_next_batch(
    market_master: pd.DataFrame,
    normalized: pd.DataFrame,
    workbook_audit: pd.DataFrame,
    availability: pd.DataFrame,
    *,
    limit: int = 50,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    history_isins = set(normalized["isin"].astype(str)) if len(normalized) else set()
    seen_isins = set(workbook_audit["isin"].astype(str)) if len(workbook_audit) else set()
    rows: list[dict[str, object]] = []
    for item in market_master.to_dict("records"):
        isin = item["isin"]
        if isin in history_isins:
            continue
        helped = _historical_help(availability, isin)
        nse = _code(item.get("operational__NSE Code") or item.get("snapshot__NSE Code"))
        bse = _code(item.get("operational__BSE Code") or item.get("snapshot__BSE Code"))
        reference = nse or bse
        rows.append({
            "ticker": item["ticker"], "company_name": item["company"], "ISIN": isin,
            "primary_exchange": item["primary_exchange"],
            "screener_reference": reference,
            "screener_url": f"https://www.screener.in/company/{quote(reference)}/" if reference else "",
            "historical_dates_helped": ";".join(helped),
            "official_clock_date_count": len(helped),
            "workbook_already_supplied": isin in seen_isins,
            "missing_history_reason": (
                "WORKBOOK_SUPPLIED_BUT_NOT_ACCEPTED" if isin in seen_isins
                else "NO_HISTORICAL_SCREENER_WORKBOOK"
            ),
        })
    missing = pd.DataFrame(rows)
    if not len(missing):
        return missing, missing.copy()
    for target in ("2022-08-05", "2023-08-07", "2024-08-07", "2025-08-07"):
        missing[f"helps_{target}"] = missing["historical_dates_helped"].str.contains(target, regex=False)
    ordering = [f"helps_{target}" for target in ("2022-08-05", "2023-08-07", "2024-08-07", "2025-08-07")]
    missing = missing.sort_values(
        [*ordering, "official_clock_date_count", "ticker", "ISIN"],
        ascending=[False, False, False, False, False, True, True], kind="stable",
    ).reset_index(drop=True)
    candidates = missing.loc[
        ~missing["workbook_already_supplied"]
        & missing["screener_url"].ne("")
        & missing["official_clock_date_count"].gt(0)
    ].head(limit).copy()
    candidates.insert(0, "priority", range(1, len(candidates) + 1))
    candidates["downloaded"] = ""
    next_columns = [
        "priority", "ticker", "company_name", "ISIN", "screener_url",
        "historical_dates_helped", "downloaded",
    ]
    return missing, candidates[next_columns].reset_index(drop=True)


def build_coverage_audit(
    market: pd.DataFrame,
    workbook_audit: pd.DataFrame,
    normalized: pd.DataFrame,
    pit_summary: pd.DataFrame,
) -> pd.DataFrame:
    """Return denominator-explicit source, field, and historical coverage rows."""

    universe_count = len(market)
    rows: list[dict[str, object]] = []

    def add(category: str, field: str, count: int, denominator: int) -> None:
        rows.append({
            "category": category, "field": field, "covered_count": int(count),
            "denominator": int(denominator),
            "coverage_pct": (100.0 * count / denominator) if denominator else 0.0,
        })

    add("IDENTITY", "clean_ordinary_equity_universe", universe_count, universe_count)
    add("SOURCE", "operational_exact_isin", int(market["operational_exact_isin_match"].sum()), universe_count)
    add("SOURCE", "snapshot_exact_isin", int(market["snapshot_exact_isin_match"].sum()), universe_count)
    add("SOURCE", "both_exports_exact_isin", int((
        market["operational_exact_isin_match"] & market["snapshot_exact_isin_match"]
    ).sum()), universe_count)
    add("SOURCE", "cross_export_conflict_free", int(market["market_merge_status"].eq("ACCEPTED").sum()), universe_count)
    logical_fields = sorted({
        column.split("__", 1)[1]
        for column in market.columns
        if column.startswith(("operational__", "snapshot__"))
    })
    for field in logical_fields:
        left = market.get(f"operational__{field}", pd.Series("", index=market.index)).map(_text).ne("")
        right = market.get(f"snapshot__{field}", pd.Series("", index=market.index)).map(_text).ne("")
        add("FIELD_ANY_EXPORT", field, int((left | right).sum()), universe_count)
        add("FIELD_OPERATIONAL", field, int(left.sum()), universe_count)
        add("FIELD_SNAPSHOT", field, int(right.sum()), universe_count)
    accepted_workbooks = workbook_audit.loc[workbook_audit["file_status"].eq("ACCEPTED")]
    add("HISTORY", "supplied_workbook_issuer", accepted_workbooks["isin"].nunique(), universe_count)
    add("HISTORY", "normalized_history_issuer", normalized["isin"].nunique(), universe_count)
    for row in pit_summary.to_dict("records"):
        add("PIT_ELIGIBLE", str(row["ranking_date"]), int(row["pit_fundamental_count"]), universe_count)
    return pd.DataFrame(rows).sort_values(["category", "field"], kind="stable").reset_index(drop=True)


def ingest_screener_data_bundle(
    *,
    archive_paths: Sequence[str | Path],
    operational_csv: str | Path,
    snapshot_csv: str | Path,
    universe_csv: str | Path,
    existing_history_csv: str | Path,
    availability_csv: str | Path,
    checklist_csv: str | Path,
    output_directory: str | Path,
    source_observed_at: str,
    ranking_dates: Sequence[date] = _RANKING_DATES,
) -> ScreenerDataBundleResult:
    """Build one deterministic incremental bundle from all supplied inputs."""

    output = Path(output_directory)
    if output.exists():
        raise FileExistsError(f"output directory already exists: {output}")
    output.mkdir(parents=True)
    cache = output / "workbooks"
    cache.mkdir()

    universe = pd.read_csv(universe_csv, dtype=str, keep_default_na=False)
    universe = universe.loc[
        universe.get("ranking_universe_eligible", "True").astype(str).str.lower().eq("true")
    ].copy()
    operational_raw = pd.read_csv(operational_csv)
    snapshot_raw = pd.read_csv(snapshot_csv)
    market, market_conflicts = merge_screener_market_exports(
        universe, operational_raw, snapshot_raw
    )
    checklist = pd.read_csv(checklist_csv, dtype=str, keep_default_na=False)
    availability = pd.read_csv(availability_csv)
    name_index, checklist_names, code_index, row_index = _identity_indexes(market, checklist)

    audit_rows: list[dict[str, object]] = []
    parsed_frames: list[pd.DataFrame] = []
    seen_payloads: set[str] = set()
    for archive_path in sorted((Path(item) for item in archive_paths), key=lambda path: path.name.casefold()):
        archive_sha = sha256_file(archive_path)
        try:
            archive = ZipFile(archive_path)
        except (BadZipFile, OSError) as exc:
            raise ValueError(f"invalid archive: {archive_path}") from exc
        with archive:
            members = _safe_members(archive)
            for member in members:
                payload = archive.read(member)
                payload_sha = hashlib.sha256(payload).hexdigest()
                filename = PurePosixPath(member.filename).name
                base_audit = {
                    "archive": archive_path.name, "archive_sha256": archive_sha,
                    "archive_member": member.filename, "input_filename": filename,
                    "workbook_sha256": payload_sha,
                }
                if payload_sha in seen_payloads:
                    audit_rows.append({**base_audit, "isin": "", "ticker": "",
                                       "workbook_company": "", "annual_period_count": 0,
                                       "identity_method": "SHA256_DUPLICATE",
                                       "file_status": "DUPLICATE_PAYLOAD", "reason": ""})
                    continue
                seen_payloads.add(payload_sha)
                pending = output / f".{payload_sha}.pending"
                pending.write_bytes(payload)
                resolved_isin = ""
                resolved_ticker = ""
                resolved_company = ""
                resolved_method = "FAILED"
                try:
                    _validate_xlsx_parts(pending)
                    inspection = inspect_screener_historical_workbook(pending)
                    isin, identity_method = _resolve_workbook_identity(
                        filename=filename, workbook_company=inspection.company,
                        name_index=name_index, checklist_names=checklist_names,
                        code_index=code_index,
                    )
                    identity = row_index[isin]
                    resolved_isin = isin
                    resolved_ticker = str(identity["ticker"])
                    resolved_company = inspection.company
                    resolved_method = identity_method
                    record = {
                        "ticker": identity["ticker"], "isin": isin,
                        "company": identity["company"], "workbook_company": inspection.company,
                        "workbook_sha256": payload_sha, "reporting_basis": REPORTING_BASIS,
                        "source_observed_at": source_observed_at,
                        "basis_attestation": (
                            "USER_SUPPLIED_SCREENER_STANDALONE_COMPANY_EXPORT; exact workbook "
                            "identity resolved to cleaned ordinary-equity universe by ISIN-backed "
                            "master/checklist evidence"
                        ),
                    }
                    parsed = parse_screener_historical_workbook(pending, record)
                    target_dir = cache / isin
                    target_dir.mkdir(exist_ok=True)
                    target = target_dir / f"{payload_sha}.xlsx"
                    pending.replace(target)
                    parsed["source_archive"] = archive_path.name
                    parsed["source_archive_sha256"] = archive_sha
                    parsed["source_archive_member"] = member.filename
                    parsed_frames.append(parsed)
                    audit_rows.append({
                        **base_audit, "isin": isin, "ticker": identity["ticker"],
                        "workbook_company": inspection.company,
                        "annual_period_count": len(parsed), "identity_method": identity_method,
                        "file_status": "ACCEPTED", "reason": "",
                    })
                except Exception as exc:
                    quarantine = output / "quarantine"
                    quarantine.mkdir(exist_ok=True)
                    if pending.exists():
                        pending.replace(quarantine / f"{payload_sha}.xlsx")
                    audit_rows.append({
                        **base_audit, "isin": resolved_isin, "ticker": resolved_ticker,
                        "workbook_company": resolved_company, "annual_period_count": 0,
                        "identity_method": resolved_method,
                        "file_status": "QUARANTINED", "reason": str(exc),
                    })

    workbook_audit = pd.DataFrame(audit_rows).sort_values(
        ["archive", "archive_member"], kind="stable"
    ).reset_index(drop=True)
    incoming = pd.concat(parsed_frames, ignore_index=True) if parsed_frames else pd.DataFrame()
    existing = pd.read_csv(existing_history_csv)
    normalized, history_conflicts = merge_history_incrementally(existing, incoming)

    from .screener_historical_fundamentals import official_clock_from_availability
    official_clock = official_clock_from_availability(availability)
    pit = build_screener_pit_cohorts(normalized, official_clock, list(ranking_dates))
    coverage_audit = build_coverage_audit(market, workbook_audit, normalized, pit.cohort_summary)
    missing_history, next_batch = build_missing_history_and_next_batch(
        market, normalized, workbook_audit, availability
    )
    source_hashes = {
        "operational_csv": sha256_file(operational_csv),
        "snapshot_csv": sha256_file(snapshot_csv),
        "universe_csv": sha256_file(universe_csv),
        "existing_history_csv": sha256_file(existing_history_csv),
        "availability_csv": sha256_file(availability_csv),
        "checklist_csv": sha256_file(checklist_csv),
        "archives": {path.name: sha256_file(path) for path in sorted(
            (Path(item) for item in archive_paths), key=lambda item: item.name.casefold()
        )},
    }
    summary: dict[str, object] = {
        "schema_version": SCREENER_BUNDLE_VERSION,
        "source_observed_at": source_observed_at,
        "clean_universe_count": len(market),
        "operational_exact_isin_matches": int(market["operational_exact_isin_match"].sum()),
        "snapshot_exact_isin_matches": int(market["snapshot_exact_isin_match"].sum()),
        "market_conflict_rows": len(market_conflicts),
        "market_conflict_counts": (
            market_conflicts["conflict_type"].value_counts().sort_index().astype(int).to_dict()
            if len(market_conflicts) else {}
        ),
        "archive_count": len(archive_paths),
        "workbooks_attempted": len(workbook_audit),
        "workbooks_accepted": int(workbook_audit["file_status"].eq("ACCEPTED").sum()),
        "workbooks_quarantined": int(workbook_audit["file_status"].eq("QUARANTINED").sum()),
        "duplicate_payloads": int(workbook_audit["file_status"].eq("DUPLICATE_PAYLOAD").sum()),
        "unique_workbook_issuers": int(workbook_audit.loc[
            workbook_audit["file_status"].eq("ACCEPTED"), "isin"
        ].nunique()),
        "incoming_annual_observations": len(incoming),
        "existing_annual_records": len(existing),
        "existing_history_issuers": int(existing["isin"].nunique()),
        "normalized_annual_records": len(normalized),
        "normalized_history_issuers": int(normalized["isin"].nunique()),
        "net_new_annual_records": len(normalized) - len(existing),
        "net_new_history_issuers": int(normalized["isin"].nunique() - existing["isin"].nunique()),
        "history_conflicts": len(history_conflicts),
        "pit_counts": dict(zip(pit.cohort_summary["ranking_date"],
                               pit.cohort_summary["pit_fundamental_count"].astype(int))),
        "missing_history_issuers": len(missing_history),
        "next_batch_count": len(next_batch),
        "source_hashes": source_hashes,
        "frozen_science_changed": False,
    }

    artifacts = {
        "market_master.csv": market,
        "market_conflicts.csv": market_conflicts,
        "workbook_audit.csv": workbook_audit,
        "normalized_history.csv": normalized,
        "history_conflicts.csv": history_conflicts,
        "pit_selected.csv": pit.accepted,
        "pit_rejected.csv": pit.rejected,
        "pit_summary.csv": pit.cohort_summary,
        "coverage_audit.csv": coverage_audit,
        "missing_history.csv": missing_history,
        "next_batch_50.csv": next_batch,
    }
    for name, frame in artifacts.items():
        frame.to_csv(output / name, index=False, encoding="utf-8", lineterminator="\n",
                     float_format="%.17g")
    artifact_hashes = {name: sha256_file(output / name) for name in sorted(artifacts)}
    summary["artifact_hashes"] = artifact_hashes
    summary["bundle_fingerprint"] = hashlib.sha256(_canonical_json({
        "schema_version": SCREENER_BUNDLE_VERSION,
        "source_hashes": source_hashes,
        "artifact_hashes": artifact_hashes,
    })).hexdigest()
    (output / "bundle_summary.json").write_bytes(_canonical_json(summary))
    inventory = [
        {"path": path.relative_to(output).as_posix(), "sha256": sha256_file(path),
         "size": path.stat().st_size}
        for path in sorted(output.rglob("*"))
        if path.is_file() and path.name != "artifact_inventory.json"
    ]
    (output / "artifact_inventory.json").write_bytes(_canonical_json(inventory))
    return ScreenerDataBundleResult(
        market, market_conflicts, workbook_audit, normalized, history_conflicts,
        pit.accepted, pit.rejected, pit.cohort_summary, coverage_audit,
        missing_history, next_batch, summary,
    )


def accept_screener_data_bundle(
    bundle_directory: str | Path, accepted_state_path: str | Path, *,
    allow_quarantined_workbooks: bool = False,
) -> Mapping[str, object]:
    """Validate terminal hashes and atomically publish an accepted-state pointer."""

    bundle = Path(bundle_directory).resolve()
    summary_path = bundle / "bundle_summary.json"
    inventory_path = bundle / "artifact_inventory.json"
    if not summary_path.is_file() or not inventory_path.is_file():
        raise ValueError("bundle lacks terminal summary or inventory")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    for name, expected in summary.get("artifact_hashes", {}).items():
        artifact = bundle / name
        if not artifact.is_file() or sha256_file(artifact) != expected:
            raise ValueError(f"bundle artifact hash mismatch: {name}")
    quarantined = int(summary.get("workbooks_quarantined", 0))
    if summary.get("history_conflicts") != 0:
        raise ValueError("bundle has unresolved historical conflicts")
    if quarantined and not allow_quarantined_workbooks:
        raise ValueError("bundle has quarantined workbooks; explicit acceptance is required")
    state = {
        "schema_version": SCREENER_BUNDLE_VERSION,
        "accepted_bundle_path": bundle.as_posix(),
        "bundle_fingerprint": summary["bundle_fingerprint"],
        "bundle_summary_sha256": sha256_file(summary_path),
        "clean_universe_count": summary["clean_universe_count"],
        "normalized_history_issuers": summary["normalized_history_issuers"],
        "quarantined_workbooks": quarantined,
        "pit_counts": summary["pit_counts"],
    }
    target = Path(accepted_state_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".pending")
    temporary.write_bytes(_canonical_json(state))
    temporary.replace(target)
    return state


def load_accepted_screener_data_bundle(
    accepted_state_path: str | Path,
    *,
    include_history: bool = True,
    include_workbook_audit: bool = True,
) -> AcceptedScreenerDataBundle:
    """Load the accepted bundle after validating its pointer and used artifacts.

    This is a read-only product integration boundary.  It never discovers or
    downloads data, and the exact ISIN rows produced by ingestion remain the
    only join keys downstream.
    """

    state_path = Path(accepted_state_path)
    state = json.loads(state_path.read_text(encoding="utf-8"))
    if state.get("schema_version") != SCREENER_BUNDLE_VERSION:
        raise ValueError("unsupported accepted Screener bundle schema")
    root = Path(str(state.get("accepted_bundle_path", ""))).resolve()
    if state_path.parent.resolve() not in root.parents:
        raise ValueError("accepted Screener bundle escapes its provider store")
    if not root.is_dir():
        raise ValueError("accepted Screener bundle directory is unavailable")
    summary_path = root / "bundle_summary.json"
    if not summary_path.is_file() or sha256_file(summary_path) != state.get("bundle_summary_sha256"):
        raise ValueError("accepted Screener bundle summary hash mismatch")
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    fingerprint = str(state.get("bundle_fingerprint", ""))
    if not fingerprint or summary.get("bundle_fingerprint") != fingerprint:
        raise ValueError("accepted Screener bundle fingerprint mismatch")
    required = ["market_master.csv"]
    if include_history:
        required.append("normalized_history.csv")
    if include_workbook_audit:
        required.append("workbook_audit.csv")
    artifact_hashes = summary.get("artifact_hashes", {})
    for name in required:
        path = root / name
        if not path.is_file() or sha256_file(path) != artifact_hashes.get(name):
            raise ValueError(f"accepted Screener bundle artifact hash mismatch: {name}")
    market = pd.read_csv(root / "market_master.csv", low_memory=False)
    if (len(market) != int(state.get("clean_universe_count", -1))
            or "isin" not in market or market["isin"].duplicated().any()
            or market["isin"].map(_isin).ne(market["isin"].astype(str)).any()):
        raise ValueError("accepted Screener market master identity contract failed")
    history = pd.read_csv(root / "normalized_history.csv", low_memory=False) if include_history else pd.DataFrame()
    audit = pd.read_csv(root / "workbook_audit.csv", low_memory=False) if include_workbook_audit else pd.DataFrame()
    return AcceptedScreenerDataBundle(
        root=root,
        market_master=market,
        normalized_history=history,
        workbook_audit=audit,
        summary=summary,
        fingerprint=fingerprint,
    )
