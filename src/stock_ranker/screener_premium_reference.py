"""Validation and reconciliation for user-supplied Screener Premium exports.

These exports are current secondary reference evidence only.  They have no
official dissemination timestamp and therefore can never satisfy a historical
point-in-time fundamental contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re

import pandas as pd


IDENTITY_COLUMNS = ("Name", "BSE Code", "NSE Code", "ISIN Code", "Industry Group", "Industry")
REFERENCE_COLUMNS = (
    "Return on capital employed", "Debt to equity", "Profit after tax", "Profit growth",
)
REQUIRED_COLUMNS = IDENTITY_COLUMNS + REFERENCE_COLUMNS
ISIN_PATTERN = re.compile(r"^IN[A-Z0-9]{9}[0-9]$")


@dataclass(frozen=True, slots=True)
class ScreenerReferenceResult:
    rows: pd.DataFrame
    conflicts: pd.DataFrame
    manifest: dict[str, object]


def _file_sha256(path: Path) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _text(series: pd.Series) -> pd.Series:
    return series.astype("string").str.strip().replace("", pd.NA)


def validate_screener_export(frame: pd.DataFrame, *, source_label: str) -> pd.DataFrame:
    """Validate identity and relevant values without inventing export timing."""

    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"{source_label}: missing exact columns: {', '.join(missing)}")
    result = frame.copy(deep=True)
    if result.empty:
        raise ValueError(f"{source_label}: export is empty")
    for column in IDENTITY_COLUMNS:
        result[column] = _text(result[column])
    bad_isin = result["ISIN Code"].isna() | ~result["ISIN Code"].str.match(ISIN_PATTERN, na=False)
    if bad_isin.any():
        raise ValueError(f"{source_label}: invalid ISIN rows: {result.index[bad_isin].tolist()[:10]}")
    duplicates = result["ISIN Code"].duplicated(keep=False)
    if duplicates.any():
        values = sorted(result.loc[duplicates, "ISIN Code"].unique().tolist())
        raise ValueError(f"{source_label}: duplicate ISIN values: {values[:10]}")
    for column in REFERENCE_COLUMNS:
        converted = pd.to_numeric(result[column], errors="coerce")
        malformed = result[column].notna() & converted.isna()
        if malformed.any():
            raise ValueError(f"{source_label}: nonnumeric {column} rows: {result.index[malformed].tolist()[:10]}")
        finite = converted.notna() & ~converted.map(lambda value: bool(pd.notna(value) and float('-inf') < value < float('inf')))
        if finite.any():
            raise ValueError(f"{source_label}: non-finite {column} rows: {result.index[finite].tolist()[:10]}")
        result[column] = converted
    return result.sort_values("ISIN Code", kind="stable").reset_index(drop=True)


def reconcile_screener_exports(paths: list[str | Path]) -> ScreenerReferenceResult:
    if not paths:
        raise ValueError("at least one Screener export is required")
    exports: list[tuple[Path, pd.DataFrame]] = []
    sources: list[dict[str, object]] = []
    for raw_path in paths:
        path = Path(raw_path).resolve()
        frame = validate_screener_export(pd.read_csv(path, low_memory=False), source_label=path.name)
        exports.append((path, frame))
        sources.append({"filename": path.name, "sha256": _file_sha256(path), "row_count": len(frame)})

    base = exports[0][1]
    identity = base[list(IDENTITY_COLUMNS)].copy()
    conflict_rows: list[dict[str, object]] = []
    for path, frame in exports[1:]:
        joined = identity.merge(frame[list(IDENTITY_COLUMNS)], on="ISIN Code", how="outer", suffixes=("_base", "_other"), indicator=True)
        if not joined["_merge"].eq("both").all():
            raise ValueError(f"{path.name}: identity universe differs from first export")
        for column in (value for value in IDENTITY_COLUMNS if value != "ISIN Code"):
            left, right = f"{column}_base", f"{column}_other"
            mismatch = joined[left].fillna("").ne(joined[right].fillna(""))
            for row in joined.loc[mismatch, ["ISIN Code", left, right]].itertuples(index=False, name=None):
                conflict_rows.append({"isin": row[0], "field": column, "base_value": row[1], "other_value": row[2], "source": path.name, "conflict_type": "IDENTITY"})

    output = identity.rename(columns={
        "Name": "reference_company", "BSE Code": "reference_bse_code", "NSE Code": "reference_nse_code",
        "ISIN Code": "isin", "Industry Group": "reference_industry_group", "Industry": "reference_industry",
    })
    metric_names = {
        "Return on capital employed": "reference_roce_percent",
        "Debt to equity": "reference_debt_to_equity",
        "Profit after tax": "reference_profit_after_tax",
        "Profit growth": "reference_profit_growth_percent",
    }
    for source_index, (path, frame) in enumerate(exports):
        metric = frame[["ISIN Code", *REFERENCE_COLUMNS]].rename(columns={"ISIN Code": "isin", **metric_names})
        suffix = f"__source_{source_index + 1}"
        metric = metric.rename(columns={name: name + suffix for name in metric_names.values()})
        output = output.merge(metric, on="isin", how="left", validate="one_to_one")
        if source_index:
            for canonical in metric_names.values():
                first = canonical + "__source_1"
                current = canonical + suffix
                both = output[first].notna() & output[current].notna()
                mismatch = both & ~output[first].eq(output[current])
                for row in output.loc[mismatch, ["isin", first, current]].itertuples(index=False, name=None):
                    conflict_rows.append({"isin": row[0], "field": canonical, "base_value": row[1], "other_value": row[2], "source": path.name, "conflict_type": "VALUE"})

    output["evidence_role"] = "USER_SUPPLIED_CURRENT_SECONDARY_REFERENCE"
    output["historical_pit_eligible"] = False
    output["pit_ineligibility_reason"] = "NO_OFFICIAL_DISSEMINATION_TIMESTAMP_OR_HISTORICAL_AVAILABILITY"
    output = output.sort_values("isin", kind="stable").reset_index(drop=True)
    conflicts = pd.DataFrame(conflict_rows, columns=["isin", "field", "base_value", "other_value", "source", "conflict_type"])
    if not conflicts.empty:
        conflicts = conflicts.sort_values(["conflict_type", "isin", "field", "source"], kind="stable").reset_index(drop=True)
    canonical = output.astype(object).where(pd.notna(output), None).to_dict("records")
    fingerprint = sha256((json.dumps(canonical, sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n").encode()).hexdigest()
    manifest: dict[str, object] = {
        "schema_version": "screener_user_export_reference_v1",
        "sources": sources,
        "row_count": len(output),
        "conflict_count": len(conflicts),
        "fingerprint": fingerprint,
        "identity_rule": "EXACT_ISIN_ONLY_NO_FUZZY_MATCHING",
        "historical_pit_eligible": False,
        "canonical_store_admission": False,
        "scientific_boundary": "Current secondary cross-check only; never a filing-availability source or Research V2 promotion authority.",
    }
    return ScreenerReferenceResult(output, conflicts, manifest)


def exact_isin_coverage(reference: pd.DataFrame, company_facts: pd.DataFrame) -> tuple[pd.DataFrame, dict[str, int]]:
    required = {"isin", "ticker", "company", "v2_eligible", "baseline_eligible"}
    missing = sorted(required - set(company_facts.columns))
    if missing:
        raise ValueError(f"company facts missing columns: {', '.join(missing)}")
    selected = company_facts[list(required)].copy()
    matches = selected.merge(reference, on="isin", how="left", indicator=True, validate="one_to_one")
    matches["screener_exact_isin_match"] = matches.pop("_merge").eq("both")
    source_one = [column for column in matches if column.endswith("__source_1")]
    complete = matches[source_one].notna().all(axis=1) if source_one else pd.Series(False, index=matches.index)
    matches["screener_all_reference_metrics"] = matches["screener_exact_isin_match"] & complete
    summary = {
        "company_fact_count": len(matches),
        "exact_isin_match_count": int(matches["screener_exact_isin_match"].sum()),
        "all_reference_metrics_count": int(matches["screener_all_reference_metrics"].sum()),
        "baseline_eligible_reference_complete_count": int((matches["baseline_eligible"].eq(True) & matches["screener_all_reference_metrics"]).sum()),
        "v2_eligible_count": int(matches["v2_eligible"].eq(True).sum()),
        "reference_complete_not_v2_count": int((matches["screener_all_reference_metrics"] & ~matches["v2_eligible"].eq(True)).sum()),
    }
    return matches.sort_values(["ticker", "isin"], kind="stable").reset_index(drop=True), summary
